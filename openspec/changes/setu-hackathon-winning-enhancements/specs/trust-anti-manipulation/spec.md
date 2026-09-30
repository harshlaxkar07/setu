## Purpose

Protects prioritization from manipulation by detecting coordinated or repetitive submissions and flagging them with a stated reason and lowered confidence, never deleting them.

## ADDED Requirements

### Requirement: Near-duplicate submission bursts are flagged

The system SHALL flag a citizen request as a suspected duplicate burst when, within a configured time window, at least a configured number of other requests in the same category have text similarity at or above a configured threshold to it. A flagged request SHALL be retained, SHALL carry a trust flag with a human-readable reason naming the rule and the count of matching requests, and SHALL NOT be deleted or hidden from reviewers.

#### Scenario: Burst of near-identical texts is flagged

- **WHEN** 50 requests with near-identical water-complaint text arrive for the same ward within 10 minutes
- **THEN** each request after the burst threshold carries a trust flag whose reason names the duplicate-burst rule and the number of matching requests, and all 50 requests remain stored

#### Scenario: Independent similar complaints are not flagged

- **WHEN** 5 requests with similar text about the same village arrive spread across 5 days
- **THEN** none of them carries a duplicate-burst trust flag

### Requirement: Repeat submissions from one pseudonymous source are flagged

The system SHALL flag requests when a single conversation identifier submits more than a configured number of requests to the same cluster within a configured window. The flag reason SHALL state the submission count and window. The conversation identifier SHALL remain pseudonymous; no personal identifier SHALL be introduced to support this rule.

#### Scenario: One source floods a cluster

- **WHEN** one conversation identifier submits 12 requests joining the same cluster within one hour and the configured limit is 3
- **THEN** the requests beyond the limit carry a repeat-source trust flag stating "12 submissions in 1 hour from one source"

### Requirement: Sudden cluster spikes are flagged at cluster level

The system SHALL flag a demand cluster when its member arrivals in a recent window exceed a configured multiple of its baseline arrival rate. The cluster confidence SHALL be lowered from high and its confidence reason SHALL describe the spike (window, count, and baseline).

#### Scenario: Cluster spike lowers confidence

- **WHEN** a cluster that averaged 2 new members per day receives 300 new members in one hour
- **THEN** the cluster's confidence is lowered below high and its confidence reason describes the spike with the observed count and the baseline

### Requirement: Flagged volume does not inflate priority

Requests carrying a duplicate-burst or repeat-source trust flag SHALL NOT be counted in the complaint-volume indicator used by the PriorityScore. The dashboard SHALL show both the total member count and the counted (unflagged) volume, so the exclusion is visible rather than silent.

#### Scenario: Spam attack barely moves the score

- **WHEN** 300 near-identical requests are injected into a cluster by the spam-attack demo script
- **THEN** the cluster's complaint-volume indicator counts only unflagged requests, the cluster's PriorityScore changes by no more than the contribution of those unflagged requests, and the dashboard shows total members and counted volume side by side

### Requirement: Reviewers can clear or confirm trust flags

A signed-in reviewer SHALL be able to mark a trust flag as cleared (legitimate) or confirmed (manipulation). Clearing a flag SHALL restore the request's contribution to complaint volume. Every clear or confirm action SHALL be recorded with the reviewer identity and timestamp.

#### Scenario: Reviewer clears a false positive

- **WHEN** a reviewer clears the duplicate-burst flag on a request
- **THEN** the request is counted in complaint volume on the next scoring run and the action is recorded with the reviewer and time

### Requirement: Spam-attack demonstration script

The project SHALL provide a script that injects a configurable number of near-identical requests into a named cluster through the public intake API, so the detection and its effect can be demonstrated live without direct database writes.

#### Scenario: Running the demo script

- **WHEN** an operator runs the spam-attack script with a count of 300 against the Kothrud cluster
- **THEN** 300 requests are submitted through the intake API and the dashboard shows the resulting trust flags within one refresh cycle
