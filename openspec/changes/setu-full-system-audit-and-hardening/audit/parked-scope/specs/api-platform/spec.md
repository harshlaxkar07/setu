# Delta Spec: api-platform

## Purpose

Defines the cross-cutting API contract that makes every frontend-facing endpoint predictable: versioning, filter semantics, pagination and sorting rules, response envelope, error shape, typed schemas, accurate OpenAPI, and integration documentation for future frontends.

## ADDED Requirements

### Requirement: Versioned namespace with preserved compatibility

Frontend-facing analytics, map, cluster, and verification-queue APIs SHALL live under `/api/v1/`. Existing working endpoints (citizen intake `/api/requests/*`, gate, ops, verification, clusters) SHALL keep working: each is either retained as-is, or given a `/api/v1` home with the old path preserved as a documented, deprecated alias with identical behavior. No existing consumer (citizen web, tests, demo scripts) may break without a migrated, tested replacement.

#### Scenario: Old paths still serve

- **WHEN** a pre-existing endpoint that gained a v1 home is called at its original path
- **THEN** it responds identically to the v1 path and its OpenAPI entry marks it deprecated with a pointer to the replacement

### Requirement: Consistent filter contract

All v1 endpoints SHALL use the same filter parameter names and semantics wherever a filter applies: `from_date`/`to_date` (inclusive ISO dates, from ≤ to enforced), `region`, `category`, `status`, `channel`, `language`, `tier`/priority bounds, `verification_status`, `granularity`. Unknown enum values, malformed dates, and inverted ranges SHALL return 422 with the offending parameter named. The same filter applied to different endpoints MUST select the same underlying population.

#### Scenario: Cross-endpoint filter consistency

- **WHEN** the same region + date-range filter is applied to the trend, breakdown, and map endpoints
- **THEN** their totals reconcile (trend sum = breakdown total = map features + unmapped count)

#### Scenario: Invalid filter rejected

- **WHEN** `from_date` is after `to_date`, or `status` is not a documented value
- **THEN** the response is 422 naming the parameter, and no partial/empty 200 is returned

### Requirement: Pagination and sorting rules

List endpoints SHALL implement the platform pagination contract: `page` (1-based) and `page_size` with a documented default and enforced maximum; responses carry total count and page info; `sort_by` restricted to documented fields with `sort_order` asc/desc; every ordering ends with a unique tiebreaker for determinism. List endpoints MUST NOT return the entire table by default.

#### Scenario: Page size capped

- **WHEN** a caller requests a page size above the documented maximum
- **THEN** the endpoint returns 422 (or clamps, if that is the documented behavior) rather than returning an unbounded result

### Requirement: Predictable response envelope and errors

v1 responses SHALL follow a standard envelope: `data` (payload), `meta` (at minimum: generation timestamp and the filters actually applied), and `pagination` on list endpoints. Error responses SHALL keep the platform's single documented error shape across all v1 endpoints, with stable machine-readable content — never stack traces or internal details.

#### Scenario: Envelope everywhere

- **WHEN** any v1 endpoint responds successfully
- **THEN** the body carries `data` and `meta` (plus `pagination` for lists), and `meta.filters` echoes the effective filter values

### Requirement: Typed contracts

Every v1 endpoint SHALL declare a Pydantic response model (no untyped dict responses for frontend-facing contracts), with enums for closed value sets (statuses, tiers, granularities, channels) so they appear as enums in the schema.

#### Scenario: No untyped v1 responses

- **WHEN** the OpenAPI document is inspected
- **THEN** every v1 operation has a concrete response schema with typed fields and enumerated value sets — no bare object/array schemas

### Requirement: OpenAPI is the frontend contract

`/docs` and `/openapi.json` SHALL accurately describe the actual API: every v1 operation has a summary and description, documented status codes (success, validation, not-found, conflict where applicable), request/response schemas, and example payloads for the important endpoints. A frontend developer MUST be able to build against the API from the OpenAPI document plus the integration guide, without reading backend source.

#### Scenario: Contract accuracy check

- **WHEN** documented examples and schemas are exercised against the running API
- **THEN** real responses validate against the documented schemas and status codes

### Requirement: Future-frontend integration documentation

The project SHALL ship integration documentation covering: API base URL and versioning, endpoint groups, authentication assumptions (none yet — explicitly stated, with authorization-ready boundaries noted), filter/pagination/sorting semantics, response envelope and error contract, GeoJSON contracts, workflow mutation endpoints (gate decision, resolve, verification review, retry), OpenAPI location, and local development setup — with no dependency on Streamlit internals.

#### Scenario: New frontend thought experiment

- **WHEN** a developer follows only the integration documentation and OpenAPI
- **THEN** they can retrieve every value the reference dashboard displays and invoke every workflow action it offers
