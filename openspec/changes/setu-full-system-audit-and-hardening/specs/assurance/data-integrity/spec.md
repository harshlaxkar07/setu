# Delta Spec: assurance/data-integrity

## Purpose

Guarantees the database can be trusted as the system of record: invariants hold under all tested operations, reseeding is reproducible, and synthetic seed data is always distinguishable from live data.

## ADDED Requirements

### Requirement: Database invariants are tested

The audit SHALL implement automated invariant checks proving: no orphan rows (memberships, verifications, traces referencing missing parents), no duplicate cluster memberships, no impossible status values or illegal status combinations, no stale derived data (cluster aggregates inconsistent with member rows), and no partial writes surviving a failed multi-step operation.

#### Scenario: Invariant suite on a populated database

- **WHEN** the invariant suite runs after the full test and demo workload
- **THEN** every invariant passes, and any violation identifies the offending rows in its failure message

#### Scenario: Failed multi-step operation leaves no partial state

- **WHEN** a pipeline stage or API operation that writes multiple rows is interrupted by an injected failure mid-way
- **THEN** the database contains either the complete result or none of it, and the failure is observable

### Requirement: Reseed reproducibility

Running the documented reseed procedure repeatedly SHALL be re-proven to produce equivalent state each time (same entity counts, same cluster structure, same scores), and the procedure MUST be runnable from a fresh environment.

#### Scenario: Double reseed

- **WHEN** the reseed procedure runs twice from scratch
- **THEN** both runs yield equivalent database state by the documented equivalence checks

### Requirement: Seed data distinguishable from live data

Synthetic seed data SHALL be identifiable as synthetic by inspection of stored data (marker, naming convention, or documented provenance), so no displayed statistic can silently mix fabricated and real records without that being detectable.

#### Scenario: Auditor separates seed from live rows

- **WHEN** an auditor inspects any table containing both seeded and live-submitted rows
- **THEN** a documented, queryable criterion separates the two populations
