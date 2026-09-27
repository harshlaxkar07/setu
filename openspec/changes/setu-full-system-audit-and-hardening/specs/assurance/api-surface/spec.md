# Delta Spec: assurance/api-surface

## Purpose

Guarantees the HTTP surface is fully known and hardened: every route inventoried, every route tested against a negative-input matrix, no orphan endpoints, and no UI action calling a missing or broken endpoint.

## ADDED Requirements

### Requirement: Complete route inventory

The audit SHALL auto-discover every FastAPI route from the application (not from documentation) and record it in `audit/api-inventory.md` with method, path, purpose, request/response contract, and consumers. Routes present in code but absent from the inventory, or vice versa, constitute audit failures.

#### Scenario: Inventory matches the live app

- **WHEN** the route set extracted from the running app is compared with `audit/api-inventory.md`
- **THEN** the two sets are identical

### Requirement: Per-route negative-input matrix

Every route SHALL be tested against the negative-input matrix applicable to it: valid input, invalid input, missing fields, wrong types, empty payloads, malformed payloads, nonexistent IDs, duplicate submissions, oversized payloads, unexpected media types, and dependency failure. Each case MUST produce a correct HTTP status and a safe, structured error body — never a stack trace, secret, or partial DB write.

#### Scenario: Nonexistent resource

- **WHEN** any route is called with a syntactically valid but nonexistent identifier
- **THEN** it returns 404 with a structured error body and no state change

#### Scenario: Malformed payload

- **WHEN** any mutating route receives a malformed or wrong-typed payload
- **THEN** it returns 422 (or the documented 4xx), writes nothing to the database, and leaks no internal detail

### Requirement: No orphan or dangling endpoints

The audit SHALL verify that every endpoint has at least one real consumer (UI, pipeline, seed, test, or documented external contract) and that every UI action resolves to an existing, working endpoint. Orphans are removed or documented; dangling UI calls are P1 findings.

#### Scenario: UI action resolves

- **WHEN** each dashboard or citizen-web action that issues an HTTP call is enumerated
- **THEN** each targets an existing route whose contract matches what the UI sends and renders
