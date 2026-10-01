## Purpose

Keeps the Publish Gate readable and AI usage bounded by holding at most one recommendation awaiting review per demand cluster, however many citizens report the same problem.

## ADDED Requirements

### Requirement: One pending recommendation per cluster

When a request joins a cluster that already has a recommendation awaiting review, the pipeline SHALL NOT draft a new recommendation or open a new Publish Gate item. The request's run SHALL record that it joined the existing pending recommendation and end there. A new recommendation SHALL be drafted only when the cluster has no recommendation awaiting review (none yet, or the previous one was approved, rejected, or sent back for changes).

#### Scenario: Second report joins the pending draft

- **WHEN** a request joins the Velhe cluster while Velhe's recommendation is awaiting review
- **THEN** no new recommendation is drafted, no model call is made for recommendation, the Publish Gate still shows one Velhe item, and the request's run trace records the recommendation it joined

#### Scenario: Fresh draft after a decision

- **WHEN** a request joins a cluster whose previous recommendation was sent back for changes
- **THEN** a new recommendation is drafted and awaits review at the Publish Gate

### Requirement: Joined runs follow the gate decision

When a reviewer decides a recommendation, every run that joined it SHALL take the same resulting status as the run that opened it, so no joined run stays shown as awaiting approval after the decision.

#### Scenario: Approval settles joined runs

- **WHEN** a recommendation that three later runs joined is approved
- **THEN** the opening run and all three joined runs show status published

### Requirement: Concurrent reports cannot open duplicate drafts

Two requests joining the same cluster at the same moment SHALL result in at most one new pending recommendation.

#### Scenario: Simultaneous submissions

- **WHEN** two requests for a cluster with no pending recommendation reach the Recommend stage concurrently
- **THEN** exactly one recommendation is drafted and the other run joins it
