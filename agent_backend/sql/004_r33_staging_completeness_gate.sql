-- R33 staging completeness gate.
-- Authority: R33_STAGING_TO_OPERATIONAL_CONTRACT.md + R20 atomic publisher contract.
-- This function is read-only: it validates one staged run/revision and raises on any ambiguity.
-- It does not promote, mutate operational corpus rows, alter visibility, or expose runtime endpoints.
-- DO NOT APPLY TO CLOUD SQL until a separate database-application decision is recorded.

CREATE OR REPLACE FUNCTION assert_staging_complete(
    p_run_id uuid,
    p_source_revision_id text
)
RETURNS void
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_asset_key text;
    v_canonical_id text;
    v_section_count bigint;
    v_chunk_count bigint;
    v_embedding_count bigint;
BEGIN
    IF p_run_id IS NULL OR p_source_revision_id IS NULL OR btrim(p_source_revision_id) = '' THEN
        RAISE EXCEPTION 'staging completeness gate: run_id and source_revision_id are required';
    END IF;

    -- The revision/asset/canonical binding must already exist in the operational metadata plane.
    SELECT sa.asset_key, sa.canonical_id
      INTO v_asset_key, v_canonical_id
      FROM source_revisions sr
      JOIN source_assets sa ON sa.asset_key = sr.asset_key
     WHERE sr.source_revision_id = p_source_revision_id
       AND sr.run_id = p_run_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'staging completeness gate: source revision is not bound to this run';
    END IF;

    SELECT count(*)
      INTO v_section_count
      FROM staging_sections s
     WHERE s.ingestion_run_id = p_run_id
       AND s.source_revision_id = p_source_revision_id;

    IF v_section_count = 0 THEN
        RAISE EXCEPTION 'staging completeness gate: no staged sections';
    END IF;

    SELECT count(*)
      INTO v_chunk_count
      FROM staging_chunks c
     WHERE c.ingestion_run_id = p_run_id
       AND c.source_revision_id = p_source_revision_id;

    IF v_chunk_count = 0 THEN
        RAISE EXCEPTION 'staging completeness gate: no staged chunks';
    END IF;

    -- Sections must be complete and remain inside the exact revision/asset binding.
    IF EXISTS (
        SELECT 1
          FROM staging_sections s
         WHERE s.ingestion_run_id = p_run_id
           AND s.source_revision_id = p_source_revision_id
           AND (
                s.section_id IS NULL OR btrim(s.section_id) = ''
                OR s.asset_key IS NULL OR btrim(s.asset_key) = ''
                OR s.asset_key <> v_asset_key
                OR s.normalized_section_locator IS NULL OR btrim(s.normalized_section_locator) = ''
                OR s.section_ordinal < 1
                OR s.heading_path IS NULL
                OR EXISTS (
                    SELECT 1
                      FROM unnest(s.heading_path) AS heading_part
                     WHERE btrim(heading_part) = ''
                )
           )
    ) THEN
        RAISE EXCEPTION 'staging completeness gate: incomplete or inconsistent staged section';
    END IF;

    -- Every operational source field must already be present in staging. No semantic repair is allowed here.
    IF EXISTS (
        SELECT 1
          FROM staging_chunks c
         WHERE c.ingestion_run_id = p_run_id
           AND c.source_revision_id = p_source_revision_id
           AND (
                c.chunk_id IS NULL OR btrim(c.chunk_id) = ''
                OR c.section_id IS NULL OR btrim(c.section_id) = ''
                OR c.asset_key IS NULL OR btrim(c.asset_key) = ''
                OR c.asset_key <> v_asset_key
                OR c.canonical_id IS NULL OR btrim(c.canonical_id) = ''
                OR c.canonical_id <> v_canonical_id
                OR c.source_type IS NULL OR c.source_type NOT IN ('GOOGLE_DOC', 'HTML', 'SHEET_STRUCTURED')
                OR c.source_title IS NULL OR btrim(c.source_title) = ''
                OR c.heading_path IS NULL
                OR EXISTS (
                    SELECT 1
                      FROM unnest(c.heading_path) AS heading_part
                     WHERE btrim(heading_part) = ''
                )
                OR c.chunk_ordinal < 1
                OR c.chunk_text IS NULL OR btrim(c.chunk_text) = ''
                OR c.chunk_text_sha256 IS NULL OR c.chunk_text_sha256 !~ '^[0-9a-f]{64}$'
                OR c.content_hash IS NULL OR c.content_hash <> c.chunk_text_sha256
                OR c.token_count IS NULL OR c.token_count < 1
                OR c.language IS NULL OR btrim(c.language) = ''
                OR c.content_type IS NULL OR c.content_type NOT IN ('institutional', 'editorial', 'technical', 'reference')
                OR c.access_scope IS NULL OR btrim(c.access_scope) = ''
                OR c.sensitivity IS NULL OR btrim(c.sensitivity) = ''
                OR c.instruction_authority IS NULL OR c.instruction_authority NOT IN ('NONE', 'RAG_REFERENCE_ONLY')
                OR c.domain_authority IS NULL OR btrim(c.domain_authority) = ''
                OR c.source_locator IS NULL
                OR jsonb_typeof(c.source_locator) <> 'object'
                OR c.source_locator = '{}'::jsonb
                OR c.retrieval_enabled IS NULL
                OR (
                    (c.url_key IS NULL AND c.canonical_url_order IS NULL AND c.canonical_url IS NOT NULL)
                    OR (c.url_key IS NULL AND c.canonical_url_order IS NOT NULL)
                    OR (c.url_key IS NOT NULL AND (btrim(c.url_key) = '' OR c.canonical_url_order IS NULL OR c.canonical_url IS NULL))
                    OR (c.canonical_url_order IS NOT NULL AND c.canonical_url_order NOT BETWEEN 1 AND 116)
                    OR (c.canonical_url IS NOT NULL AND c.canonical_url !~ '^https://')
                )
           )
    ) THEN
        RAISE EXCEPTION 'staging completeness gate: incomplete or malformed staged chunk';
    END IF;

    -- A chunk cannot reference a section outside the same run/revision/asset binding.
    IF EXISTS (
        SELECT 1
          FROM staging_chunks c
         WHERE c.ingestion_run_id = p_run_id
           AND c.source_revision_id = p_source_revision_id
           AND NOT EXISTS (
                SELECT 1
                  FROM staging_sections s
                 WHERE s.ingestion_run_id = c.ingestion_run_id
                   AND s.source_revision_id = c.source_revision_id
                   AND s.section_id = c.section_id
                   AND s.asset_key = c.asset_key
           )
    ) THEN
        RAISE EXCEPTION 'staging completeness gate: chunk section binding is broken';
    END IF;

    -- When URL provenance is present, it must match the canonical URL table exactly.
    IF EXISTS (
        SELECT 1
          FROM staging_chunks c
         WHERE c.ingestion_run_id = p_run_id
           AND c.source_revision_id = p_source_revision_id
           AND c.url_key IS NOT NULL
           AND NOT EXISTS (
                SELECT 1
                  FROM canonical_urls u
                 WHERE u.url_key = c.url_key
                   AND u.url_order = c.canonical_url_order
                   AND u.canonical_url = c.canonical_url
           )
    ) THEN
        RAISE EXCEPTION 'staging completeness gate: canonical URL provenance mismatch';
    END IF;

    -- chunk_ordinal is 1..N within each section, with no gaps or duplicates.
    IF EXISTS (
        SELECT 1
          FROM (
                SELECT c.section_id,
                       count(*) AS row_count,
                       count(DISTINCT c.chunk_ordinal) AS distinct_count,
                       min(c.chunk_ordinal) AS min_ordinal,
                       max(c.chunk_ordinal) AS max_ordinal
                  FROM staging_chunks c
                 WHERE c.ingestion_run_id = p_run_id
                   AND c.source_revision_id = p_source_revision_id
                 GROUP BY c.section_id
          ) ordinal_check
         WHERE ordinal_check.min_ordinal <> 1
            OR ordinal_check.max_ordinal <> ordinal_check.row_count
            OR ordinal_check.distinct_count <> ordinal_check.row_count
    ) THEN
        RAISE EXCEPTION 'staging completeness gate: chunk ordinals are not contiguous and one-based';
    END IF;

    -- Embeddings are optional by run profile. If present, they must form one exact model/dimension
    -- set and cover every staged chunk exactly, with no references outside this candidate.
    SELECT count(*)
      INTO v_embedding_count
      FROM staging_chunk_embeddings e
     WHERE e.ingestion_run_id = p_run_id;

    IF v_embedding_count > 0 THEN
        IF EXISTS (
            SELECT 1
              FROM staging_chunk_embeddings e
             WHERE e.ingestion_run_id = p_run_id
               AND NOT EXISTS (
                    SELECT 1
                      FROM staging_chunks c
                     WHERE c.ingestion_run_id = p_run_id
                       AND c.source_revision_id = p_source_revision_id
                       AND c.chunk_id = e.chunk_id
               )
        ) THEN
            RAISE EXCEPTION 'staging completeness gate: embedding references a chunk outside the candidate';
        END IF;

        IF (
            SELECT count(DISTINCT (e.embedding_model, e.dimensions))
              FROM staging_chunk_embeddings e
             WHERE e.ingestion_run_id = p_run_id
        ) <> 1 THEN
            RAISE EXCEPTION 'staging completeness gate: multiple embedding model/dimension sets';
        END IF;

        IF (
            SELECT count(DISTINCT e.chunk_id)
              FROM staging_chunk_embeddings e
             WHERE e.ingestion_run_id = p_run_id
        ) <> v_chunk_count THEN
            RAISE EXCEPTION 'staging completeness gate: embedding coverage is incomplete';
        END IF;
    END IF;
END;
$$;
