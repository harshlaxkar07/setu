# Delta Spec: assurance/failure-safety

## Purpose

Guarantees that for every injected dependency failure the system's user-visible behavior, persistence, recoverability, and observability are specified and tested — nothing silently lost, nothing fabricated.

## ADDED Requirements

### Requirement: Failure-injection matrix is specified and tested

The audit SHALL produce `audit/failure-matrix.md` covering at minimum: Gemini down/timeout/garbage-output/rate-limited/bad-key, Nominatim down/empty-result, database outage, backend/dashboard/container restarts (including during the gate), malformed media, Whisper/STT failure, missing embedding or fixture, empty database, and duplicate/stale runs. For EACH cell the matrix records: user-visible behavior, database writes, recoverability, whether anything is silently lost, retry safety, and observability — and each cell is backed by an automated test or an explicit manual-checklist entry.

#### Scenario: AI dependency failure never fabricates output

- **WHEN** Gemini is unavailable or returns garbage during any stage
- **THEN** the run fails into an explicit recoverable state (e.g., needs-retry), no fabricated structured data is persisted, and the citizen-visible status reflects a truthful, understandable state

#### Scenario: Geocoding failure is contained

- **WHEN** Nominatim is down or returns no result
- **THEN** the request is preserved with an explicit unresolved-location state, the failure is observable in the trace, and retry is safe

#### Scenario: Empty database

- **WHEN** the system runs against an empty (unseeded) database
- **THEN** every surface renders a professional empty state and every API returns valid, empty-shaped responses — no crashes, no fabricated data

### Requirement: Prefer explicit recoverable failure over silent corruption

For every audited failure path, the system SHALL either complete correctly or fail explicitly and recoverably. Any discovered path that swallows an error, half-writes state, or shows fabricated/stale data as fresh is at least a P1 finding.

#### Scenario: Silent-loss hunt

- **WHEN** each failure-matrix cell is executed
- **THEN** no cell results in a citizen request or state transition disappearing without an observable trace
