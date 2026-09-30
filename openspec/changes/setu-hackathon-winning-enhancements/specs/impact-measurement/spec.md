## Purpose

Closes the governance loop by measuring whether action on a cluster changed the underlying need, comparing the period before and after resolution.

## ADDED Requirements

### Requirement: Before/after impact metrics for resolved clusters

For every cluster that has been marked resolved, the system SHALL report: the complaint arrival rate in a configured window before resolution and the same-length window after; the infrastructure gap before and after (using facility data as of each point); and the verification status. Metrics SHALL be computed from stored timestamps and data, never estimated by an AI model.

#### Scenario: Complaints drop after resolution

- **WHEN** a seeded resolved cluster had 40 requests in the 30 days before resolution and 5 in the 30 days after
- **THEN** the impact view shows 40 before, 5 after, the percentage change, and the verification status

#### Scenario: Too little time since resolution

- **WHEN** a cluster was resolved less than the configured window ago
- **THEN** the after-window metric is shown as partial with the number of elapsed days rather than as a final figure

### Requirement: Impact never implies verification

Impact metrics SHALL be displayed separately from verification status, and a reduction in complaints SHALL NOT change a cluster's verification status.

#### Scenario: Fewer complaints without verification

- **WHEN** complaints fell after resolution but no verification has confirmed it
- **THEN** the cluster still shows "resolved — unverified"
