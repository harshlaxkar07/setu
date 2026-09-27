# Delta Spec: assurance/ux-accessibility

## Purpose

Guarantees the citizen and policymaker surfaces meet an observable UX and accessibility bar: bilingual consistency, understandable errors, honest loading/empty states, responsive layout, contrast, color-independent meaning, and no raw internals shown to users.

## ADDED Requirements

### Requirement: Citizen-facing clarity

The citizen surface SHALL be verified for: consistent bilingual (Hindi/English) presentation wherever both exist; error messages a non-technical citizen can act on; visible loading feedback for every wait; truthful status wording (never claiming success that has not happened); and mobile-responsive layout.

#### Scenario: Failure explained to a citizen

- **WHEN** a citizen submission fails for any audited reason (network, dependency, validation)
- **THEN** the citizen sees a plain-language, bilingual-consistent explanation of what happened and what to do next — never raw JSON, an HTTP code alone, or a stack trace

### Requirement: Accessibility fundamentals

Both surfaces SHALL be checked for: text contrast meeting a defensible bar for government use, meaning never carried by color alone (tiers, statuses, and map markers also distinguishable by text/shape), keyboard-reachable primary actions, and legible typography at mobile widths.

#### Scenario: Color-independent tiers

- **WHEN** priority tiers or statuses are displayed anywhere (cards, tables, map)
- **THEN** each is identifiable without perceiving color (label, badge text, or pattern)

### Requirement: No raw internals user-facing

No user-visible surface SHALL render raw JSON dumps, Python exceptions, stack traces, or internal identifiers where a human-readable label is expected.

#### Scenario: Backend unavailable

- **WHEN** the backend is unreachable while a user browses either surface
- **THEN** the surface shows a professional "service unavailable" state and recovers when the backend returns
