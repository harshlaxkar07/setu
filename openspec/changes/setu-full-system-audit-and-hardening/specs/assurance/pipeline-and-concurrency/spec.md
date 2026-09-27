# Delta Spec: assurance/pipeline-and-concurrency

## Purpose

Guarantees the implemented LangGraph pipeline provably matches the intended eight-stage contract and that interruption, resumption, restarts, and concurrent or duplicate operations never corrupt state.

## ADDED Requirements

### Requirement: Implemented graph matches the intended contract

The audit SHALL derive the implemented graph (nodes, edges, interrupts, retry policies, per-node inputs/outputs/side-effects/persistence) from code into `audit/graph-map.md` and diff it against the intended eight-stage contract. Unreachable nodes, undocumented transitions, unsafe retries, and state lost across restart are findings.

#### Scenario: Graph diff is clean or explained

- **WHEN** the derived graph is compared with the intended contract
- **THEN** every divergence is either fixed or recorded as a classified finding with rationale

### Requirement: Interrupt, resume, and restart are independently re-verified

The audit SHALL re-verify, with its own tests: suspension at the Publish Gate persists across backend restart; resume after restart completes correctly; a run interrupted mid-stage either resumes safely or fails observably as needs-retry — never silently loses the citizen request.

#### Scenario: Restart around the gate

- **WHEN** the backend restarts while a run is suspended awaiting gate approval
- **THEN** the run remains resumable and a subsequent gate decision completes it correctly

### Requirement: Duplicate and concurrent operations are safe

Duplicate gate decisions, repeated resume calls, double verification reviews, concurrent citizen submissions, and concurrent review actions SHALL each be tested; the outcome MUST be one applied action plus explicit rejection (e.g., 409) of the rest — never double-applied state or corruption.

#### Scenario: Duplicate gate decision

- **WHEN** two gate decisions for the same suspended thread are submitted (sequentially duplicated or concurrently)
- **THEN** exactly one decision takes effect and the other receives an explicit conflict response, with the database reflecting a single approval

#### Scenario: Double verification review

- **WHEN** a second review decision is submitted for an already-reviewed verification record
- **THEN** it is rejected with a conflict response and the original decision is unchanged
