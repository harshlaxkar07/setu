# Tasks: setu-full-system-audit-and-hardening

Execution follows design AD1: inventories first (read-only), then parallel scoped audit passes, consolidation, then severity-ordered fix waves. Evidence conventions: AD8 findings schema, AD11 evidence log. Nothing in phases 1–3 fixes anything.

## 1. Inventory phase (read-only ground truth)

- [ ] 1.1 Build the RTM skeleton in `audit/RTM.md` per AD2 (all sources harvested, IDs assigned, every row starting at best `under-verified`); verify completeness by the mechanical check — grep for empty Status/evidence cells returns nothing, and each source section lists its skipped-prose remainder
- [ ] 1.2 Build `audit/api-inventory.md` from `app.routes` at import, cross-checked against `/openapi.json` on the running stack; verify the route sets match exactly and every route has method, path, purpose, contract, and consumers recorded
- [ ] 1.3 Build `audit/graph-map.md` from the graph construction in `backend/app/pipeline.py` (including the out-of-graph Verify invocation and inline intake fallback); verify by diffing against the intended eight-stage contract with every divergence listed
- [ ] 1.4 Build the test-layer inventory (AD3 table: existing 12 files / 95 tests mapped to layers, with per-test PROVES/WEAK/MISSING verdict columns to be filled by pass 2.9); verify every existing test file appears exactly once
- [ ] 1.5 Build the dashboard-value provenance inventory in `audit/frontend-logic-inventory.md` over `dashboard/`: every displayed value, aggregation, score/rank/callout derivation, hard-coded constant, region inference, and map rule in `app.py`/`components.py`, each mapped to its API source or flagged as locally computed (feeds the ux-accessibility and auditability passes; DoD-15); verify the known local computations are all captured (score `weight × norm` math, region A/B by member count, #1/#2 ranking, zero-facility/low-investment callouts, weight prose, tier/radius map rules)
- [ ] 1.6 Create the evidence scaffolding: `audit/evidence-log.md` (AD11 dated-entry format), `audit/findings.md` headed by the literal AD8 record template, `audit/failure-matrix.md` skeleton (one row per AD4 failure × six dimension columns), and `audit/passes/` with one named observation-log file per section-2 pass; verify all files exist with their locked format headers

## 2. Audit passes (parallel, scoped, read-only — observations only, no fixes)

- [ ] 2.1 Requirements/RTM pass (→ `audit/passes/rtm.md`): walk every RTM row against implementation and tests, recording status + evidence candidates; verify no row is left `under-verified` without either an upgrade path or an observation-log entry
- [ ] 2.2 API-surface pass (→ `audit/passes/api-surface.md`): run the negative-input matrix (valid/invalid/missing/wrong-type/empty/malformed/nonexistent-id/duplicate/oversized/unexpected-media/dependency-failure) against every inventoried route on the running stack, recording actual status codes and bodies (known suspects: invalid-UUID 500s on cluster routes, unvalidated `status` on ops runs); additionally enumerate every HTTP call issued by `dashboard/` and `citizen-web/`, verify each targets an inventoried route with a matching contract, and flag inventoried routes with no consumer as orphan candidates; verify every route × applicable-case cell has a recorded observation, plus one observation per UI call and per consumer-less route
- [ ] 2.3 DB-integrity pass (→ `audit/passes/db-integrity.md`): probe orphans, duplicate memberships, illegal statuses, stale aggregates, partial writes, cascade/rollback behavior, reseed determinism, and seed-vs-live distinguishability (a documented, queryable criterion separating seeded rows from live-submitted rows) on the real database; verify each data-integrity spec requirement has observations recorded
- [ ] 2.4 Graph/pipeline pass (→ `audit/passes/graph.md`): verify per-node contracts, interrupt/resume, retry semantics, and checkpoint survival against `audit/graph-map.md`; verify every divergence from 1.3 has a disposition recorded
- [ ] 2.5 AI/STT/geo behavior pass (→ `audit/passes/ai-stt-geo.md`): schema validation, malformed-output handling, replay layer, hallucination boundaries, noisy/short/empty audio, ambiguous/invalid locations, throttle and cache behavior; verify observations cover every functional-inventory item in BRIEF area 2 for these stages
- [ ] 2.6 Security/privacy pass per AD7 (→ `audit/passes/security.md`): secrets sweep (tree + full git history), SQL call-site classification, both-sided XSS sweep (35 `unsafe_allow_html` sites + citizen DOM), exposure/hygiene checks, pseudonymity sweep; verify every AD7 sweep has a recorded result including the negative ones
- [ ] 2.7 UX/accessibility pass (→ `audit/passes/ux.md`) over both surfaces (bilingual consistency, error/loading/empty states, contrast, color-independence, responsive layout, raw-internals hunt); verify observations map to every ux-accessibility spec requirement
- [ ] 2.8 Reliability/performance pass (→ `audit/passes/reliability.md`): N+1s, redundant external calls, missing timeouts, blocking operations — measured, with only material items recorded; verify each recorded item carries its measurement
- [ ] 2.9 Test-quality pass (→ `audit/passes/test-quality.md`): fill the PROVES/WEAK/MISSING verdict for every existing test (status-200-only and over-mocked hunts, mutation spot-checks on PROVES verdicts); verify the 1.4 inventory has no empty verdict cells
- [ ] 2.10 Demo-readiness pass (→ `audit/passes/demo.md`): dry-run the eight rehearsal scenarios recording every rough edge; verify each scenario has a dated observation entry
- [ ] 2.11 Adversarial critic pass (→ `audit/passes/critic.md`): attempt gate bypasses, attack sibling passes' PROVES verdicts and manual-checklist candidates, hunt untested claims; verify the critic's log explicitly addresses each other pass's output
- [ ] 2.12 Auditability/observability pass (→ `audit/passes/auditability.md`): for a sample of published clusters, answer each auditor question of the auditability-observability spec (why this cluster, why this score, which data contributed, what was AI vs deterministic, who approved and when, what evidence verified resolution) with a recorded SQL query over stored data alone — no recomputation from source-code defaults — and reconstruct one real failed run (stage, error class, prior completed stages, current status) from persisted traces without a debugger; any question answerable only from code inspection is recorded as an observation; verify every auditability-observability spec scenario has a recorded demonstration or observation

## 3. Consolidation and severity

- [ ] 3.1 Merge all observation logs into `audit/findings.md` per AD8 (dedupe, one finding many citations, unreproducible items demoted to investigation notes); verify every observation is either in a finding, an investigation note, or explicitly closed as not-an-issue
- [ ] 3.2 Assign P0–P3 severities once, by the fixed definitions, and sequence fix waves; verify no finding lacks a severity and the register parses against the AD8 template

## 4. Fix waves from the findings register (AD1 phase 4, AD8 guardrails)

- [ ] 4.1 Fix all P0 findings, one at a time (fix + proving test + full regression each); verify register shows every P0 `fixed-verified` with regression evidence
- [ ] 4.2 Fix all P1 findings in small per-subsystem batches; verify register shows every P1 `fixed-verified` and the full suite green after each batch
- [ ] 4.3 Resolve all P2/P3 findings (fix or documented-accepted with rationale); verify no register entry remains `open`
- [ ] 4.4 Add delta specs to this change for any fix that changed spec-level behavior of a `build-setu-mvp` capability (AD8 spec-coupling rule); verify each such fix cites its delta spec and `openspec validate --strict` passes

## 5. Failure-injection campaign (AD4)

- [ ] 5.1 Implement `test_failures.py` covering the deterministic matrix rows (Gemini down/timeout/garbage/429/bad-key, Nominatim down/empty, missing embedding, STT failure, malformed media, missing/corrupt replay fixture, empty DB, duplicate/stale runs) via the code's own seams; verify every deterministic matrix cell cites a passing test
- [ ] 5.2 Execute the docker-level procedures (DB outage around live calls, backend/dashboard/compose restarts around a suspended gate, bad key at startup) with dated evidence-log entries; verify every process-boundary matrix cell cites its procedure entry
- [ ] 5.3 Run the closing zero-loss accounting queries; verify `audit/failure-matrix.md` is complete — no blank or claim-only cell — and the accounting output shows zero violations

## 6. Concurrency and idempotency probes (AD6)

- [ ] 6.1 Implement `test_concurrency.py` (parallel HTTP probes: submission floods N≥10, two-writer races on gate resume/resolve/review/retry, repeated-resume soak with 20 sequential re-resumes, double verification) plus DB-level two-connection interleaving tests for the guarded transitions; verify each probe shows exactly-one-winner + 409 losers + legal final state, with post-state invariant queries recorded
- [ ] 6.2 Implement `test_db_invariants.py` (orphans, duplicate memberships, illegal statuses, stale aggregates, partial writes, and seed-vs-live distinguishability — the documented queryable criterion cleanly partitions seeded rows from live-submitted rows) and run it as the campaign's closing check; verify green on the post-campaign database, including after the demo workload
- [ ] 6.3 Execute the double-reseed check: two from-scratch reseeds compared by the documented equivalence checks (entity counts, cluster structure, scores), deciding and documenting the exact-vs-float-tolerance rule per the design open question at the first run; verify both reseed results and the documented rule land as dated evidence-log entries
- [ ] 6.4 Implement auditability/observability assertions (extending `test_db_invariants.py` or a dedicated module): stored score components and weights reproduce displayed scores without recomputation, approvals carry reviewer + decision + timestamp, and a failed run's persisted trace identifies stage, error class, prior completed stages, and current status; verify green and cited from the evidence log against the auditability-observability spec

## 7. Security hardening and test strengthening (from pass 2.6/2.9 findings)

- [ ] 7.1 Implement `test_security.py` (upload caps and hostile filenames, injection probes, XSS round-trips through citizen text/reviewer/AI-drafted fixture fields asserted inert in the dashboard AppTest layer (dashboard container, per AD3), pseudonymity sweeps); verify every AD7 probe row cites a passing test or dated procedure
- [ ] 7.2 Implement `test_api_matrix.py` parameterized route × negative-case from the api-surface spec,; verify every inventoried route has its applicable matrix cases passing (422/404/409/413 as documented, never 500)
- [ ] 7.3 Strengthen or replace every WEAK-verdict test from pass 2.9 (never deleted, never weakened); verify the test-layer inventory shows no remaining WEAK verdict without a register-documented rationale
- [ ] 7.4 Implement `test_graph_contract.py` + extend `test_pipeline.py` for graph-map conformance, interrupt/resume, retry-without-reexecution; verify every graph-map node/edge/interrupt claim cites a test
- [ ] 7.5 Write the production-gap security register (auth/RBAC, TLS, rate limiting, WAF, tenancy, retention/deletion, consent — each with its risk and production expectation, stated as explicit gaps, never claimed solved) and classify every 2.6 sweep match as live → P0 fixed with rotation, or dev-only → documented accepted local-dev scope (compose DB password as accepted local-dev scope); verify the register exists and no sweep match is unclassified

## 8. E2E, rehearsals, and environment proofs (AD5, quality-gates spec)

- [ ] 8.1 Implement `test_e2e_scenarios.py` automating the core of the eight rehearsal scenarios (happy path, equity case, AI failure, location failure, restart-around-gate scripted portion, verification match/mismatch/human review); verify all pass through the real stack
- [ ] 8.2 Execute the full eight-scenario demo rehearsal matrix at least twice with dated evidence-log entries, most recent passing (the Publish Gate approval in each rehearsal is a real human click, not automated); verify each scenario has ≥2 recorded executions
- [ ] 8.3 Execute the DEMO_REPLAY re-proof per AD5 (full demo with live Gemini genuinely unreachable, then the unrehearsed-input miss path halting visibly); verify both evidence-log entries with zero outbound calls in the first
- [ ] 8.4 Run the default suite once with an invalid key and blocked egress; verify it passes, proving zero live dependencies
- [ ] 8.5 Fresh-environment proof: clean clone → documented steps → seeded working stack → rehearsal; verify any undocumented step became a documentation fix and the final walkthrough is clean
- [ ] 8.6 Run the controlled-live sanity pass inside the AD5 budget: one end-to-end live Gemini/Nominatim run plus the live bad-key probe, via `@pytest.mark.live` checks excluded from the default invocation; verify the evidence-log budget ledger records date/purpose/outcome for every live call (≤10 Gemini, ≤10 Nominatim per cycle) with a written reason for any excess
- [ ] 8.7 Author `audit/manual-checklist.md` per AD10 (only genuinely human/hardware checks — real-device press-and-hold, real-microphone Hindi capture, Devanagari glyph and grayscale perception — each entry critic-challenged with could-a-test-verify-this, failed challenges converted to automated tests; executable-as-written format); verify every entry survived the critic challenge or was converted
- [ ] 8.8 (manual — requires a human with real devices) Execute every manual-checklist entry: pass/fail + date + checker signature per entry, failures filed as register findings; verify no entry lacks a signed result
- [ ] 8.9 (bounded process) For every finding registered after the section-4 waves (from the failure-injection, concurrency, security, E2E, and rehearsal campaigns), re-enter the AD1 loop: consolidate and severity-classify per the 3.1–3.2 rules, fix per the 4.x wave discipline with full regression per wave, and re-run the affected campaign checks; verify exit when the register shows no open P0/P1, every P2/P3 is fixed-verified or documented-accepted, and the last loop iteration's evidence is dated after its last code change

## 9. Documentation truthing and exit gate (AD9)

- [ ] 9.1 Update README/CONTRIBUTING to match audited reality (precise MVP/demo/simulated/synthetic language, production-readiness gaps incl. the 7.5 security gap register); verify the docs-versus-reality diff — every documented claim and command executed or verified
- [ ] 9.2 Complete `audit/RTM.md` statuses; verify the mechanical completeness check passes and every non-verified status links its finding or rationale
- [ ] 9.3 Reconcile `audit/frontend-logic-inventory.md` against the final dashboard: every displayed value's source documented (an API field, or a documented-presentational computation) and every chart's Question → Metric → Source chain recorded; verify no displayed number remains unexplained (DoD-15)
- [ ] 9.4 Run the adversarial critic re-pass over the final state (suite diff for weakened assertions, evidence dating, manual-checklist challenge); verify the critic's log shows no unresolved objection
- [ ] 9.5 Complete the DoD checklist — all 25 items, each checked only with a citation to an RTM row, named test, findings record, or dated evidence-log entry — in `audit/evidence-log.md`; verify P0=0, P1=0, no open P2/P3, one full-suite green run via the two documented commands of AD3 dated after the last code change, and every DoD citation resolves
