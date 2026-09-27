# Delta Spec: assurance/quality-gates

## Purpose

Defines the audit's own machinery: the test-quality bar, the severity workflow, the regression-loop exit criteria, demo rehearsals, the fresh-environment proof, and documentation accuracy — the gates this change must pass to be done.

## ADDED Requirements

### Requirement: Test-quality bar

Every feature's tests SHALL be audited against the question "does this test PROVE the requirement?". Status-200-only tests, over-mocked tests that cannot fail on real defects, and snapshot tests that merely freeze current behavior SHALL be strengthened or replaced — never deleted to hide behavior. The suite MUST be layered: unit → integration (real Postgres/PostGIS/pgvector) → API → DB invariants → graph → failure injection → E2E → genuinely-manual checklist.

#### Scenario: Weak test found

- **WHEN** the test audit identifies a test that passes while its requirement is violated
- **THEN** the test is replaced by one that fails on the violation, and the register records the upgrade

### Requirement: Severity workflow and exit criteria

Findings SHALL be classified P0 (corruption/security/gate-bypass), P1 (broken core behavior or scoring), P2 (edge/reliability/UX/auditability), P3 (polish), without inflation or deflation, in `audit/findings.md`. Each confirmed defect follows `Requirement → Failure → Root Cause → Fix → Test → Regression`. The change is done only when P0 = 0, P1 = 0, and every P2/P3 is fixed or documented with rationale, with the full regression suite green.

#### Scenario: Regression loop

- **WHEN** a fix lands for any finding
- **THEN** the targeted test passes, the full suite passes, and affected E2E scenarios re-pass before the finding closes

### Requirement: Demo rehearsals and fresh-environment proof

The full demo story SHALL be rehearsed repeatedly with evidence: happy path, equity case (Velhe outranks Kothrud), AI failure, location failure, restart-around-gate, verification match, mismatch, and human review. A fresh environment (clean clone → documented steps → working app with seed) SHALL be proven; any undocumented step is a documentation defect. Replay mode MUST be proven with live Gemini unavailable.

#### Scenario: Fresh clone

- **WHEN** the documented setup runs on a machine with only the documented prerequisites
- **THEN** the full stack starts, seeds, and passes the demo rehearsal without undocumented intervention

### Requirement: Definition-of-Done checklist gated by citations

Every Definition-of-Done item in `audit/BRIEF.md` (the DoD-25 block) SHALL be checked only with a citation to existing evidence — an RTM row, a named test, a findings-register entry, or a dated evidence-log entry — that substantiates the item without further searching. An unchecked item in either DoD block SHALL keep the change incomplete.

#### Scenario: DoD item checked without evidence

- **WHEN** the exit review inspects a checked DoD item
- **THEN** the item carries a citation to an RTM row, named test, findings record, or dated evidence-log entry that substantiates it, or the item is unchecked and the change remains incomplete

### Requirement: DoD checklist completion

The change SHALL be closed only when all 25 Definition-of-Done items from the audit brief are checked, and each item SHALL be checked only with a citation — an RTM row, a named test, a findings-register record, or a dated evidence-log entry — that substantiates it without further searching. An item with no such citation remains unchecked.

#### Scenario: Uncited DoD item

- **WHEN** the exit review finds a checked DoD item whose citation is missing or does not substantiate the claim
- **THEN** the item is unchecked and the change cannot exit until substantiating evidence is produced and cited

### Requirement: Finding reproducibility

A suspected defect SHALL enter the findings register only after a second, independent reproduction. A suspicion that cannot be reproduced twice SHALL be recorded as an investigation note — not a finding — with the observation, the reproduction attempts, and why it remains open.

#### Scenario: Unreproducible suspicion

- **WHEN** a suspected defect fails a second reproduction attempt
- **THEN** it is recorded as an investigation note rather than a register finding, and no fix is driven from it

### Requirement: Exit evidence freshness

Every piece of evidence cited at the exit gate — regression runs, E2E rehearsals, DoD citations — SHALL be dated after the last code change. Evidence predating any subsequent code change is stale and MUST be regenerated before exit.

#### Scenario: Stale exit evidence

- **WHEN** a code change lands after the evidence supporting an exit criterion was produced
- **THEN** that evidence is regenerated and re-dated before the criterion counts toward exit

### Requirement: Live-vs-mock boundary and controlled-live budget

The default test suite SHALL be green with live external services (Gemini, Nominatim) unreachable: deterministic tests mock external services, while integration tests use real Postgres/PostGIS/pgvector. Tests that make controlled live calls SHALL be explicitly marked, run under a defined budget, and log each live call; DEMO_REPLAY MUST be proven with live Gemini unavailable. Manual checks are reserved for genuinely human-hardware/visual items only.

#### Scenario: Live services unreachable

- **WHEN** the default suite runs with Gemini and Nominatim unreachable
- **THEN** it passes, and only tests explicitly marked as controlled-live are skipped or gated, with their live calls budgeted and logged when they do run

### Requirement: Documentation truth

README and CONTRIBUTING SHALL match actual behavior, using precise language (MVP, demo-ready, simulated, synthetic data, production-readiness gap) and making no unearned certification or compliance claims. The manual-only checklist MUST contain only genuinely human-verifiable items.

#### Scenario: Docs versus reality diff

- **WHEN** each documented claim, command, and behavior is executed or verified
- **THEN** every one matches reality or is corrected
