# Delta Spec: assurance/requirements-traceability

## Purpose

Guarantees that every meaningful requirement Setu has ever committed to — in `files/00–09`, the six `build-setu-mvp` delta specs, design decisions D1–D9, and the README — carries an independently evidenced verification status in a Requirements Traceability Matrix.

## ADDED Requirements

### Requirement: Complete requirements traceability matrix

The audit SHALL produce an RTM (`audit/RTM.md`) in which every meaningful requirement from the source documents is traced `Requirement → Spec → Implementation → Test → Runtime evidence → Status`, where Status is one of: verified, under-verified, partial, incorrect, missing, conflicting, obsolete, manual-only. Build-time task checkmarks from `build-setu-mvp` MUST NOT be accepted as evidence; every row's status MUST rest on verification performed during this audit.

#### Scenario: Every requirement has an evidenced status

- **WHEN** the RTM is declared complete
- **THEN** no row has an empty, "unknown", or unexplained status, and each non-verified status links to a findings-register entry or a documented rationale

#### Scenario: Checked build task is not accepted as proof

- **WHEN** a requirement's only support is a checked task in `build-setu-mvp` `tasks.md`
- **THEN** the RTM marks it at best under-verified until independent audit evidence (test, runtime probe, or manual check recorded in the evidence log) upgrades it

### Requirement: Conflicts and ambiguities are surfaced, not dropped

The RTM SHALL record requirements that conflict with each other or with implemented behavior as `conflicting`, with both sources cited; ambiguous requirements SHALL be recorded with the interpretation the audit adopted. None may be silently ignored.

#### Scenario: Conflicting sources

- **WHEN** two source documents demand incompatible behavior
- **THEN** the RTM row cites both, records which behavior the implementation exhibits, and the resolution (or explicit deferral) is logged in the findings register
