# Delta Spec: assurance/security-privacy

## Purpose

Guarantees the MVP-scoped defensive security and privacy bar: secrets hygiene, upload restrictions, injection/XSS resistance, exposure review, log hygiene, and end-to-end pseudonymity — with production-tier items documented as explicit gaps rather than pretended solved.

## ADDED Requirements

### Requirement: Secrets hygiene across repo and history

The audit SHALL sweep the working tree AND git history for secrets (API keys, credentials, tokens). Any live secret found is a P0: rotated, removed, and the incident recorded. Development-only credentials (e.g., local compose DB passwords) are reviewed and documented as accepted local-dev scope.

#### Scenario: History sweep

- **WHEN** the secret sweep runs over all tracked files and full git history
- **THEN** no live secret is present, and every match is classified (live → P0 fix; dev-only → documented)

### Requirement: Upload and input hardening

All upload endpoints SHALL be verified to enforce type, size, and path restrictions (no path traversal, no unrestricted media types, documented size limits actually enforced), and all user-supplied text rendered on HTML-capable surfaces (including Streamlit `unsafe_allow_html` components) SHALL be proven XSS-safe with hostile-input tests.

#### Scenario: Hostile upload

- **WHEN** an oversized, wrong-type, or path-traversal-named file is uploaded to any media endpoint
- **THEN** it is rejected with a safe error and nothing is written outside the designated media area

#### Scenario: Script injection through citizen text

- **WHEN** a citizen submission contains HTML/JS payloads that later render on the dashboard or citizen surfaces
- **THEN** the payload is neutralized (escaped or stripped) on every rendering surface

### Requirement: Exposure, error, and log hygiene

The audit SHALL verify: error responses and UI errors leak no stack traces, SQL, internal paths, or secrets; logs contain no secrets or raw personal data beyond the pseudonymous design; Docker/DB network exposure matches the documented local-dev scope; personally-identifying data is absent end-to-end (pseudonymous `submitter_ref` only). API and system-health endpoints MUST NOT expose secrets, prompt contents containing sensitive data, API keys, stack traces, or internal credentials.

#### Scenario: Error leakage probe

- **WHEN** each route is driven to failure (bad input, dependency down, internal error)
- **THEN** the response body and UI rendering contain no stack trace, SQL fragment, secret, or internal path

### Requirement: Production-tier gaps stated honestly

Security controls out of MVP scope (auth/RBAC, TLS, rate limiting, WAF, tenancy) SHALL be documented as explicit production-readiness gaps — never claimed as present.

#### Scenario: Gap register

- **WHEN** the security review concludes
- **THEN** a written register lists each out-of-scope control with its risk and production expectation
