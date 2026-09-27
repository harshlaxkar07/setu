# Proposal: setu-full-system-audit-and-hardening

## Why

The Setu MVP (`build-setu-mvp`, 58/66 tasks, 95/95 tests green) was built and verified *by its builders as they built it*. For a government-facing decision-support system, that is a claim, not evidence: checked tasks were verified at build time by the same process that wrote them, several verifications were AppTest/API-level proxies for human-facing behavior, test quality itself has never been audited, and no adversarial pass has tried to *disprove* completeness. This change plans the independent, evidence-producing audit — requirements traceability, functional/API/DB/graph inventories, failure injection, security and privacy review, concurrency probes, test-quality audit, multi-perspective reviews with an adversarial critic — followed by root-cause fixes, regression loops, and honest documentation, until the 25-point Definition of Done in `audit/BRIEF.md` is met with evidence.


## What Changes

- **No rebuild.** The architecture, stack, and locked decisions of `build-setu-mvp` (design D1–D9, ADRs in `files/03`) remain unchanged unless the audit produces concrete evidence a decision is defective. Human-in-the-loop controls are never weakened.
- **Evidence artifacts** created under this change's `audit/` directory: a Requirements Traceability Matrix over `files/00–09` + the six build-setu-mvp delta specs + design + README; a full FastAPI route inventory; an implemented-vs-intended LangGraph map; a severity-classified findings register (P0–P3); a failure-injection matrix; an evidence log; a genuine manual-only checklist.
- **New tests** wherever the audit finds coverage that does not *prove* its requirement: independent hand-computed scoring cases, DB invariant tests, per-route negative matrices, failure-injection tests, concurrency/idempotency probes, gate-bypass hunts, E2E scenario suites. Weak tests (status-200-only, over-mocked) are strengthened or replaced — never deleted to hide behavior.
- **Fixes for every confirmed defect**, root-cause first, each following `Requirement → Failure → Root Cause → Fix → Test → Regression`; P0/P1 must reach zero, P2/P3 fixed or explicitly documented with rationale.
- **Hardening where evidence demands it**: upload/input validation, XSS-safe rendering on `unsafe_allow_html` surfaces, error-message hygiene, secrets/git-history sweep, observability gaps (reconstructable failed runs), citizen-facing error clarity, accessibility fixes.
- **Documentation truthing**: README/CONTRIBUTING match actual behavior; precise language (MVP, demo-ready, simulated, synthetic data, production-readiness gap); no unearned certification claims.
- Repeated demo rehearsals (happy path, equity case, dependency failures, restart-around-gate, verification match/mismatch/human-review) and a fresh-environment proof are part of the exit bar, not afterthoughts.

Out of scope: production deployment, auth/RBAC, real government data integration, new product features, technology replacements, performance micro-optimization not tied to reliability or demo experience.

## Capabilities

### New Capabilities

- `assurance/requirements-traceability`: the RTM — every meaningful source requirement carries an evidenced status; conflicts and ambiguities documented, none silently ignored.
- `assurance/api-surface`: every HTTP route inventoried and tested against the negative-input matrix; no orphan endpoints; no UI action calling a missing/broken endpoint.
- `assurance/data-integrity`: DB invariants tested (no orphans, no duplicate memberships, no impossible statuses, no stale derived data, no partial writes); reseed reproducibility re-proven; seed data distinguishable from live data.
- `assurance/pipeline-and-concurrency`: implemented graph provably matches the intended eight-stage contract; interrupt/resume/restart re-verified independently; duplicate and concurrent operations (gate clicks, resumes, verifications, submissions) never corrupt state.
- `assurance/failure-safety`: the failure-injection matrix — for every injected dependency failure the system's user-visible behavior, persistence, recoverability, and observability are specified and tested; nothing silently lost or fabricated.
- `assurance/security-privacy`: MVP-scoped defensive bar — secrets hygiene (repo + git history), upload restrictions, injection/XSS sweep, exposure review, log hygiene, end-to-end pseudonymity; production-tier items documented as explicit gaps.
- `assurance/auditability-observability`: the auditor questions (why this cluster/score/approval, what was AI vs deterministic, when did state change, what evidence verified) answerable from stored data; failed executions reconstructable.
- `assurance/ux-accessibility`: citizen and policymaker surfaces meet the observable UX bar — bilingual consistency, understandable errors, loading/empty states, responsive layout, contrast, color-independent meaning, no raw JSON/stack traces user-facing.
- `assurance/quality-gates`: the audit's own machinery — test-quality bar, P0–P3 severity workflow, regression loop exit criteria, demo-rehearsal matrix, fresh-environment proof, documentation accuracy.

### Modified Capabilities

_None declared upfront._ The audit intentionally starts evidence-first: if a confirmed fix changes spec-level behavior of an existing `build-setu-mvp` capability (citizen-intake, geospatial-clustering, fusion-scoring, pipeline-orchestration, policymaker-dashboard, verification), a delta spec for that exact capability path is added to THIS change at that point, keeping artifacts coherent with the fluid workflow model.

## Impact

- **Code**: targeted fixes and new tests across `backend/`, `citizen-web/`, `dashboard/`, `db/`; no structural rewrites. Test suite grows in proof-strength, not just count.
- **Artifacts**: `audit/` evidence directory in this change; possible delta specs for existing capabilities as findings dictate; README/CONTRIBUTING updates.
- **Baseline**: `build-setu-mvp` remains unarchived; its delta specs are the requirement baseline the RTM traces against (main `openspec/specs/` is still empty — syncing/archiving it is a separate, later decision, not part of this change).
- **Runtime**: audit runs against the existing docker-compose stack; live Gemini/Nominatim used only in controlled, explicitly-marked checks; `DEMO_REPLAY` proof repeated with live Gemini unavailable.
- **Risk**: main risks are audit-scope sprawl and fix-induced regression — bounded by the severity workflow, the regression loop, and the locked-decision guardrail (see design).
