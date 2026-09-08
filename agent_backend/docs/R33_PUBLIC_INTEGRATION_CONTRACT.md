# R33 — Public integration contract

Status: architecture frozen for implementation; **not public deployment authorization**.

## Canonical site route

- Product name: `V'inC Agent`
- Reserved WordPress route: `https://viesesinconscientes.org/vinc-agent/`
- Slug: `vinc-agent`
- WordPress type: Page
- Publication state: reserved / not published

The existing 116 published URLs remain unchanged. The route is reserved in the URL authority as an R33 future route until the page is actually created and released.

## Separation invariant

The R30 service `vinc-agent-internal-beta` remains private. R33 must not turn it into the Internet-facing service.

Target topology:

```text
Browser
  -> https://viesesinconscientes.org/vinc-agent/
  -> WordPress/Elementor client
  -> vinc-agent-public-gateway (future separate public surface)
  -> authenticated service-to-service call
  -> vinc-agent-internal-beta (private)
  -> PublicAgentBoundary
  -> policy PUBLICO + CORPUS_PUBLICO
```

Forbidden topology:

```text
Browser -> database / OpenAI / Secret Manager / service-account credential
```

## Public gateway contract

Logical service name: `vinc-agent-public-gateway`.

Future public operation:

- Method: `POST`
- API path: `/v1/query`
- Request JSON: `{ "query_text": "..." }`
- The caller cannot supply `requester_scope`, `target_corpus`, canonical IDs, model/provider, retrieval modes, database configuration, policy hashes or credentials.
- Application mapping must use the already-tested `PublicAgentRequest` / `PublicAgentResponse` boundary from R32.
- Response may contain only the R32 public projection: `status`, `text`, `citations`, `abstention_code`.
- No provider/model name, internal reason, source revision ID, content hash, query/filter/evidence/answer/context hash or secret may be returned.

HTTP controls required before public release:

- allow only the canonical site origin unless another origin is separately authorized;
- strict methods and content type;
- bounded request body and timeout;
- rate limiting / anti-abuse control;
- no-store responses;
- generic public errors;
- no credentials in browser JavaScript.

Concrete thresholds belong to implementation/red-team evidence and are not invented by this architecture record.

## Gateway -> internal service contract

Future private operation on the receiving service:

- Method: `POST`
- Internal API path: `/internal/v1/query`
- Receiver: `vinc-agent-internal-beta`
- Receiver remains IAM-protected and `public_access=False`.
- Caller must use a dedicated user-managed service account with only the minimum invocation permission on the receiving service.
- Authentication must use a Google-signed OIDC ID token with the receiving service URL as audience (or an explicitly configured custom audience later).
- The public gateway does not receive database, OpenAI, Drive, corpus-governance or Secret Manager credentials.
- If the internal service keeps Cloud Run ingress=`internal`, service-to-service traffic must be routed through a VPC path recognized as internal.

The internal operation must accept only the already-public contract (`query_text`) and must construct/execute `PublicAgentBoundary`; it must not expose `CopilotRequest` directly.

## WordPress / Elementor responsibility

WordPress/Elementor is a presentation client only. It must not:

- choose scope/corpus;
- store service-account credentials;
- store provider/database secrets;
- call OpenAI directly;
- call Cloud SQL directly;
- bypass `PublicAgentBoundary`;
- alter global header/footer merely to make the technical integration work.

Initial integration target is the dedicated reserved page `/vinc-agent/`. Global navigation can be changed only as a separate launch decision.

## Gates before any Internet opening

1. Reserved route recorded in URL authority.
2. Gateway and internal private endpoint implemented and tested with no public IAM change.
3. Service-to-service authentication verified.
4. Origin/method/body/error controls verified.
5. R34 adversarial/red-team suite passes.
6. Privacy/transparency review completed.
7. Only then may R35 consider production/public access.
