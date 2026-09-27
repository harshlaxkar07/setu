# Delta Spec: pipeline-orchestration

## Purpose

Wires the eight Setu pipeline stages into one orchestrated graph with typed entity hand-offs, enforces the Publish Gate as a genuine backend halt that is resumable across processes, persists a complete RunTrace for every citizen request, and guarantees that failures halt visibly as retryable runs instead of silently dropping anything.

## ADDED Requirements

### Requirement: Pipeline executes exactly eight stages with typed entity hand-offs

The backend SHALL execute the intake pipeline as a single orchestrated graph of exactly eight stages — Understand, Locate, Cluster, Fuse, Score, Recommend, Publish Gate, Verify — in that order (Verify runs post-resolution, not inline). Each stage SHALL consume and produce the domain entities defined in `files/04-domain-model.md`: CitizenRequest → StructuredRequest (Understand) → GeocodedRequest (Locate) → ClusterMembership on a DemandCluster (Cluster) → DemandCluster with linked InfrastructureFacility rows (Fuse) → InfrastructureGapScore + PriorityIndicators + PriorityScore (Score) → draft Recommendation (Recommend) → Approval (Publish Gate); Verify consumes a VerificationRecord submission and produces a match/mismatch flag. Stage outputs SHALL be validated against these typed contracts before the next stage consumes them; a contract violation SHALL halt the run at that stage rather than pass malformed data downstream.

Stages 1–6 and 8 SHALL run autonomously with no human approval; stage 7 (Publish Gate) is the only gated stage. The graph SHALL contain no Trust stage: in this build, ConfidenceLevel is set by Locate (geocode confidence) and Verify — the glossary's "Trust stage" wording is documented drift being corrected by this change. The pipeline SHALL run inside the single backend service using direct asynchronous calls, with no external queue or worker layer (ADR-007).

#### Scenario: Autonomous run to the gate with typed outputs

- **WHEN** a CitizenRequest is ingested into the pipeline
- **THEN** stages Understand through Recommend execute in order without any human intervention
- **AND** each stage's persisted output is an instance of the entity type declared for that stage (StructuredRequest, GeocodedRequest, ClusterMembership, fused DemandCluster, scores, draft Recommendation)
- **AND** the run suspends at the Publish Gate rather than completing autonomously

#### Scenario: Stage contract violation halts the run

- **WHEN** a stage produces output that fails its typed output contract (for example, an Understand result missing a required category)
- **THEN** the run halts at that stage with the validation error recorded in its RunTrace
- **AND** no downstream stage executes against the malformed output

### Requirement: Publish Gate is enforced in the backend as a durable halt

A draft Recommendation SHALL NOT be readable through any published-recommendation query or dashboard-facing endpoint until a human Approval with decision "approved" has been recorded for it. The gate SHALL be a real suspension of graph execution in the backend, persisted through a durable checkpoint in Postgres (LangGraph interrupt + Postgres checkpointer per the locked decision) — never a UI-side filter. A suspended run SHALL survive backend process restarts without losing state and without auto-publishing.

#### Scenario: Pending recommendation is invisible before approval

- **WHEN** a run is suspended at the Publish Gate and a client queries the published recommendations for the dashboard
- **THEN** the pending Recommendation is absent from the published results
- **AND** it is observable only in an explicit awaiting-review state

#### Scenario: Gate state survives a backend restart

- **WHEN** the backend process restarts while a run is suspended at the Publish Gate
- **THEN** after restart the run is still in the awaiting-approval state, still absent from published results
- **AND** it can still be resumed by its run (thread) identifier with no data loss

### Requirement: Publish Gate is resolved cross-process through a resume endpoint

The backend SHALL expose an HTTP resume endpoint that resolves a suspended Publish Gate by run (thread) identifier. The endpoint SHALL accept a decision of approved, rejected, or needs-revision plus the reviewer's identity, SHALL record an Approval entity with decision, reviewer, and timestamp, and SHALL resume the suspended graph accordingly. This endpoint is the only mechanism that resolves a gate: the dashboard's Approve/Reject controls call it, and gate enforcement SHALL never depend on UI behavior.

#### Scenario: Approval resumes the run and publishes

- **WHEN** the resume endpoint receives decision "approved" with a reviewer identity for a run suspended at the gate
- **THEN** an Approval is recorded with that decision, reviewer, and timestamp
- **AND** the run resumes and completes, and the Recommendation becomes visible as published

#### Scenario: Rejection resolves the gate without publishing

- **WHEN** the resume endpoint receives decision "rejected" for a suspended run
- **THEN** an Approval is recorded with decision rejected, and the run reaches a terminal rejected state
- **AND** the Recommendation never appears in published results
- **AND** the CitizenRequest, DemandCluster, scores, and RunTrace remain persisted (nothing is deleted)

#### Scenario: Resume of a non-suspended run is refused

- **WHEN** the resume endpoint is called with a run identifier that is unknown or not currently suspended at a Publish Gate
- **THEN** the endpoint returns an error, no Approval is recorded, and no run state changes

### Requirement: Every request produces a persisted RunTrace

Every CitizenRequest processed by the pipeline SHALL have a persisted RunTrace recording, for each executed stage: what the stage received, what it produced, how long it took, and any errors or stage-emitted flags (including retry attempts). The RunTrace SHALL be retrievable by CitizenRequest and by DemandCluster, so that any published score or recommendation can be explained from recorded execution data rather than reconstructed after the fact.

#### Scenario: Completed run has a full trace

- **WHEN** a run completes through the Publish Gate
- **THEN** its RunTrace contains one entry per executed stage, in execution order, each with input and output references and a duration

#### Scenario: Failed run is traced up to the failure

- **WHEN** a run halts on an error at any stage
- **THEN** the RunTrace records the failing stage and the error
- **AND** all entries for previously completed stages remain intact and retrievable

### Requirement: LLM API failures retry once then halt as needs-retry

On a Gemini API failure or rate limit at any stage, the pipeline SHALL retry that call exactly once. If the retry also fails, the run SHALL halt at that stage with status "needs-retry" and SHALL be surfaced in the ops view; the CitizenRequest and all upstream stage outputs SHALL be retained unchanged. No LLM failure may cause a CitizenRequest to be dropped or a run to disappear.

#### Scenario: Transient failure recovers on retry

- **WHEN** a stage's LLM call fails once and the single retry succeeds
- **THEN** the run proceeds normally to completion of that stage
- **AND** the RunTrace records that a retry occurred at that stage

#### Scenario: Persistent failure halts the run visibly

- **WHEN** a stage's LLM call fails and its single retry also fails
- **THEN** the run halts at that stage with status needs-retry
- **AND** the run appears in the ops view identifying the failed stage
- **AND** the CitizenRequest and all prior stage outputs remain persisted

### Requirement: Every accepted request has an observable status and halted runs are operator-retryable

Every accepted CitizenRequest SHALL at all times have an observable pipeline status (such as in-progress, awaiting-approval, published, rejected, or needs-retry). An ops view SHALL list halted needs-retry runs with their failed stage, and an operator SHALL be able to trigger a retry of a halted run that resumes execution from the failed stage using persisted state — without re-submitting the CitizenRequest or re-executing completed upstream stages. No run or request SHALL be deleted or dropped without a recorded human decision.

#### Scenario: No request is unaccounted for

- **WHEN** any number of CitizenRequests have been accepted and the pipeline statuses are listed
- **THEN** every accepted request appears exactly once with a defined status
- **AND** none is absent, regardless of upstream failures

#### Scenario: Operator retry resumes from the failed stage

- **WHEN** an operator triggers a retry on a needs-retry run from the ops view
- **THEN** the pipeline resumes at the stage that failed, without re-executing completed upstream stages
- **AND** on success the run continues normally toward the Publish Gate

### Requirement: Verify stage runs autonomously post-resolution and routes flags to humans

WHEN a VerificationRecord is submitted for a DemandCluster that has been marked resolved, the backend SHALL execute the Verify stage autonomously (no gate) within the same orchestration framework, SHALL record its execution in a RunTrace, and SHALL route any mismatch or needs-review outcome to a flagged-for-human-review state rather than making any automatic change to the cluster's resolution state. (The plausibility-check semantics themselves are specified in the `verification` capability; this capability owns only the stage's invocation, tracing, and flag routing.)

#### Scenario: Verification execution is autonomous, traced, and never auto-closes

- **WHEN** a VerificationRecord is submitted for a resolved DemandCluster
- **THEN** the Verify stage executes without human approval and its execution is recorded in a RunTrace
- **AND** a mismatch or low-confidence outcome results in a flagged-for-review status visible to a human reviewer
- **AND** a mismatch or needs-review outcome leaves the cluster's resolution state unchanged (a match outcome's transition to resolved — verified is owned by the `verification` capability)

### Requirement: The end-to-end demo scenario runs live without manual intervention

With the seeded Pune-district demo dataset loaded and the system running, a single citizen submission SHALL drive the full pipeline live — through stages 1–6 to a suspended Publish Gate, and after one human approval action to a published Recommendation — with no manual data patching, database edits, or service restarts mid-run (the exit bar in `files/02-scope.md`).

#### Scenario: One submission, one approval, one published recommendation

- **WHEN** the rehearsed Hindi water-supply complaint is submitted to the running demo environment
- **THEN** the run reaches the awaiting-approval state automatically, with every intermediate entity persisted
- **AND** after a single approval through the resume endpoint, the Recommendation is available as published together with its complete RunTrace
- **AND** no manual data patching or restart occurred between submission and publication
