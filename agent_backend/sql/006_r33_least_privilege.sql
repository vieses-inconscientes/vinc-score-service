-- R33 least-privilege runtime capability roles.
-- Authority: R33_ARCHITECTURE_DECISIONS_IDENTITIES_METADATA.md
-- + R33_LEAST_PRIVILEGE_CAPABILITY_MATRIX.md + current R19/R20/R21 implementation.
--
-- This migration creates capability roles only (NOLOGIN). It does NOT create
-- application logins, set passwords, provision secrets, change IAM, populate
-- metadata/corpus, execute publisher/retrieval traffic, or retire the R30 legacy
-- vinc_agent_app/vinc_agent_runtime topology.
--
-- LIVE CLOUD SQL APPLICATION REQUIRES A SEPARATE EXPLICIT AUTHORIZATION.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vinc_agent_ingestion_runtime') THEN
        CREATE ROLE vinc_agent_ingestion_runtime NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vinc_agent_publisher_runtime') THEN
        CREATE ROLE vinc_agent_publisher_runtime NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vinc_agent_retrieval_runtime') THEN
        CREATE ROLE vinc_agent_retrieval_runtime NOLOGIN;
    END IF;
END;
$$;

-- Converge role attributes without creating credentials.
ALTER ROLE vinc_agent_ingestion_runtime
    NOLOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE vinc_agent_publisher_runtime
    NOLOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE vinc_agent_retrieval_runtime
    NOLOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- Reset only the three target capability roles. Existing R30 legacy grants are
-- intentionally untouched until a separately tested transition is authorized.
REVOKE ALL PRIVILEGES ON SCHEMA public
    FROM vinc_agent_ingestion_runtime, vinc_agent_publisher_runtime, vinc_agent_retrieval_runtime;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public
    FROM vinc_agent_ingestion_runtime, vinc_agent_publisher_runtime, vinc_agent_retrieval_runtime;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public
    FROM vinc_agent_ingestion_runtime, vinc_agent_publisher_runtime, vinc_agent_retrieval_runtime;

GRANT USAGE ON SCHEMA public
    TO vinc_agent_ingestion_runtime, vinc_agent_publisher_runtime, vinc_agent_retrieval_runtime;
REVOKE CREATE ON SCHEMA public
    FROM vinc_agent_ingestion_runtime, vinc_agent_publisher_runtime, vinc_agent_retrieval_runtime;

-- PostgreSQL functions are executable by PUBLIC by default. R33 does not permit
-- broad direct invocation of the completeness/promotion boundary or trigger helper.
REVOKE EXECUTE ON FUNCTION assert_staging_complete(uuid, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION promote_staging_sections(uuid, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION promote_staging_chunks(uuid, text, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION promote_staging_embeddings(uuid, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION vinc_set_chunks_search_tsv() FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- INGESTION TRUST ZONE
-- OperationalMetadataProjector + run/revision lifecycle + R19 staging.
-- It may prepare a candidate but cannot change operational corpus visibility.
-- ---------------------------------------------------------------------------

-- Governance-derived operational projection. SELECT is required by RETURNING /
-- ON CONFLICT predicates; UPDATE is restricted to fields the projector actually changes.
GRANT SELECT, INSERT ON TABLE canonical_objects TO vinc_agent_ingestion_runtime;
GRANT UPDATE (drive_file_id, canonical_status, agent_index_authorized, domain, access_scope)
    ON TABLE canonical_objects TO vinc_agent_ingestion_runtime;

GRANT SELECT, INSERT ON TABLE corpus_memberships TO vinc_agent_ingestion_runtime;
GRANT UPDATE (enabled)
    ON TABLE corpus_memberships TO vinc_agent_ingestion_runtime;

GRANT SELECT, INSERT ON TABLE source_assets TO vinc_agent_ingestion_runtime;
GRANT UPDATE (source_type)
    ON TABLE source_assets TO vinc_agent_ingestion_runtime;

GRANT SELECT, INSERT ON TABLE canonical_urls TO vinc_agent_ingestion_runtime;
GRANT UPDATE (slug, canonical_url, name)
    ON TABLE canonical_urls TO vinc_agent_ingestion_runtime;

-- Run/revision initialization and validation lifecycle. Ingestion may register
-- invisible candidate revisions, but receives no UPDATE privilege on source_revisions.
GRANT SELECT, INSERT ON TABLE ingestion_runs TO vinc_agent_ingestion_runtime;
GRANT UPDATE (status, validation_gate, finished_at)
    ON TABLE ingestion_runs TO vinc_agent_ingestion_runtime;
GRANT SELECT, INSERT ON TABLE source_revisions TO vinc_agent_ingestion_runtime;

-- R19 enriched staging writer. Predicate reads are needed for DELETE-by-run and
-- later ingestion-side verification; no UPDATE privilege is granted.
GRANT SELECT, INSERT, DELETE ON TABLE staging_sections TO vinc_agent_ingestion_runtime;
GRANT SELECT, INSERT, DELETE ON TABLE staging_chunks TO vinc_agent_ingestion_runtime;
GRANT SELECT, INSERT, DELETE ON TABLE staging_chunk_embeddings TO vinc_agent_ingestion_runtime;

-- ---------------------------------------------------------------------------
-- PUBLISHER TRUST ZONE
-- R20 is the sole normal-runtime visibility-changing boundary.
-- ---------------------------------------------------------------------------

-- SECURITY INVOKER gate/promotion functions read these relations as the caller.
GRANT SELECT ON TABLE
    source_assets,
    source_revisions,
    ingestion_runs,
    canonical_urls,
    staging_sections,
    staging_chunks,
    staging_chunk_embeddings
TO vinc_agent_publisher_runtime;

-- Exact operational replacement DML used by AtomicPublisher.
GRANT SELECT, INSERT, DELETE ON TABLE sections TO vinc_agent_publisher_runtime;
GRANT SELECT, INSERT, DELETE ON TABLE chunks TO vinc_agent_publisher_runtime;
GRANT SELECT, INSERT, DELETE ON TABLE chunk_embeddings TO vinc_agent_publisher_runtime;

-- Publisher can flip only operational_current on revisions and only status on runs.
GRANT UPDATE (operational_current)
    ON TABLE source_revisions TO vinc_agent_publisher_runtime;
GRANT UPDATE (status)
    ON TABLE ingestion_runs TO vinc_agent_publisher_runtime;

-- Direct execution is limited to the gate and row-projection functions used by R20.
GRANT EXECUTE ON FUNCTION assert_staging_complete(uuid, text)
    TO vinc_agent_publisher_runtime;
GRANT EXECUTE ON FUNCTION promote_staging_sections(uuid, text, text)
    TO vinc_agent_publisher_runtime;
GRANT EXECUTE ON FUNCTION promote_staging_chunks(uuid, text, text, text)
    TO vinc_agent_publisher_runtime;
GRANT EXECUTE ON FUNCTION promote_staging_embeddings(uuid, text, text)
    TO vinc_agent_publisher_runtime;

-- vinc_set_chunks_search_tsv() intentionally has no direct runtime EXECUTE grant.
-- Its existing BEFORE trigger must continue to work for publisher INSERT/UPDATE;
-- disposable PostgreSQL preflight proves that behavior after PUBLIC EXECUTE is revoked.

-- ---------------------------------------------------------------------------
-- RETRIEVAL TRUST ZONE
-- R21 PostgresReadModel is structurally read-only.
-- ---------------------------------------------------------------------------

GRANT SELECT ON TABLE
    chunks,
    source_assets,
    source_revisions,
    canonical_objects
TO vinc_agent_retrieval_runtime;

-- No staging, governance-write, publisher-function, DML or DDL privilege is granted.
