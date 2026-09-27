# Delta Spec: verification

## Purpose

Verification closes Setu's loop: citizens submit evidence that a published intervention actually happened, an AI plausibility check triages it, and human reviewers decide flagged cases — with resolution state never auto-closing on a mismatch.

Note: although the proposal lists this capability under Modified Capabilities, the requirements below are expressed as ADDED relative to the empty main spec (build-setu-mvp is unarchived); they extend — not replace — build-setu-mvp's delta requirements for this capability.

## ADDED Requirements

### Requirement: Versioned review-queue API

The system SHALL expose the human-review queue under `/api/v1/verifications`: a paginated listing filterable by review state — pending review, mismatch, needs-human-review, confirmed, rejected — where each entry carries the verification record id, the cluster's representative summary and category, submitted evidence references (photo count, voice-note presence), the AI plausibility result and its reason, relevant timestamps (submitted, reviewed), current review status, the human decision where made, and the reviewer where applicable. Pseudonymity is preserved: no submitter identity is exposed.

#### Scenario: Filtered queue

- **WHEN** the queue is requested with a review-state filter
- **THEN** only records in that state are returned, with counts matching the database under the same filter

#### Scenario: Case detail sufficiency

- **WHEN** a reviewer opens a flagged case from the queue
- **THEN** the API data shown includes the cluster context, the evidence submitted, the AI result and reason, and the timestamps — enough to decide without database access

### Requirement: Mismatch never auto-closes resolution

A verification whose AI plausibility result is mismatch SHALL flag the record for human review and SHALL NOT transition the cluster to `resolved_verified` or any closed state without an explicit human decision. No automated path — pipeline retry, re-run, or subsequent verification processing — may close a mismatched case.

#### Scenario: Mismatch holds prior state and enters the review queue

- **WHEN** the AI plausibility check returns mismatch for a submitted verification
- **THEN** the cluster remains in its prior status, the verification record is flagged for human review, and the case appears in the needs-human-review queue until a human reviewer decides it

### Requirement: Review decisions are backend-controlled

All review mutations SHALL go through the backend API; no frontend may mutate verification or cluster state directly in the database. The API enforces: only reviewable records accept decisions, exactly one decision per record (subsequent attempts receive a conflict response), the decision, reviewer, and time are persisted, and cluster status transitions triggered by decisions are executed by the backend's single transition path.

#### Scenario: Decision through the API only

- **WHEN** a reviewer confirms or rejects a flagged verification via the dashboard
- **THEN** the change is applied by the backend endpoint, recorded with reviewer and timestamp, and reflected in subsequent queue and cluster reads

#### Scenario: Second decision rejected

- **WHEN** a decision is submitted for an already-reviewed record
- **THEN** the API returns a conflict and the original decision stands
