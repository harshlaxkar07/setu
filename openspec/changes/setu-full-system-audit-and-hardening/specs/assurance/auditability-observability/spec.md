# Delta Spec: assurance/auditability-observability

## Purpose

Guarantees an auditor can answer, from stored data alone, why every visible decision happened — and that failed pipeline executions are reconstructable from persisted traces.

## ADDED Requirements

### Requirement: Auditor questions answerable from stored data

For any demand cluster, the audit SHALL demonstrate that stored data answers: why this cluster exists (member requests and similarity evidence), why this score (persisted components, normalizations, and weights), which data contributed (citations/indicators), what was AI-generated versus deterministic, who approved publication and when, when each state change happened, and what evidence supported verification. Any question answerable only from code inspection or human memory is a finding.

#### Scenario: Score explainability from persistence

- **WHEN** an auditor selects any scored cluster
- **THEN** the stored score components, normalized factors, weights, and contributing indicators fully reproduce the displayed score without recomputation from source code defaults

#### Scenario: Approval provenance

- **WHEN** an auditor inspects any published recommendation
- **THEN** the stored record shows the reviewer, the decision, and the decision time

### Requirement: Failed runs are reconstructable

Every failed or retried pipeline execution SHALL be reconstructable from persisted traces: which stage failed, with what error class, what had completed before it, and what state the run is in now. The audit MUST NOT add meaningless log noise to achieve this.

#### Scenario: Post-mortem without a debugger

- **WHEN** a run fails during any stage with the system otherwise healthy
- **THEN** the stored trace identifies the failing stage, the error, prior completed stages, and the current recoverable status
