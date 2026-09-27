# Audit Brief — setu-full-system-audit-and-hardening

Distilled execution mandate for this change. The planning artifacts (specs,
design, tasks) formalize this; the apply phase executes it. The system under
audit is the implemented `build-setu-mvp` MVP — do NOT rebuild it; locked
decisions (see that change's design.md D1–D9 and `files/03` ADRs) stay locked
unless concrete evidence shows one defective.

## Posture

- A checked task in build-setu-mvp is a claim, not proof: every requirement is
  re-verified INDEPENDENTLY against the implementation during this audit.
- "95/95 passed" is an input, not a conclusion — test QUALITY is itself audited.
- Government-facing bar: correctness, reproducibility, explainability,
  auditability, data integrity, privacy, human oversight, graceful
  degradation — WITHOUT enterprise complexity unjustified by MVP scope.
- Prefer explicit recoverable failure over silent corruption, everywhere.
- Fixes address root causes; never weaken tests to pass, never hide failures,
  never remove human-in-the-loop controls, no speculative refactors.

## Audit areas (phase map)

1. **Requirements traceability (RTM)** — every meaningful requirement from
   `files/00–09`, the six build-setu-mvp delta specs, design D1–D9, README:
   `Requirement → Spec → Implementation → Test → Runtime evidence → Status`.
   Statuses: verified / under-verified / partial / incorrect / missing /
   conflicting / obsolete / manual-only. No unexplained status at the end.
2. **Functional inventory** — citizen surface (text/voice/Hindi/receipt/
   status/verification prompts/bilingual/mobile), AI understanding (schema
   validation, malformed output, retries, replay, hallucination boundaries),
   STT (noisy/short/empty/invalid audio, model cache), geospatial (ambiguous/
   invalid locations, throttle, cached geocodes, PostGIS radius math),
   clustering (thresholds, joins vs new clusters, reproducibility), gap
   analysis (independent recomputation), priority scoring (independent
   hand-calculated cases incl. zero/missing/extreme values; equity dominance
   proof), recommendations (evidence grounding), Publish Gate (bypass hunt,
   duplicate/concurrent/stale actions), dashboard (every number traced to
   source), verification lifecycle (mismatch NEVER auto-closes).
3. **API audit** — auto-discover every FastAPI route; per-route matrix: valid/
   invalid/missing/wrong-type/empty/malformed/nonexistent-id/duplicate/
   oversized/unexpected-media/dependency-failure; orphan endpoints; UI actions
   pointing at missing endpoints.
4. **DB & data integrity** — constraints/indexes/nullability/geometry/vector
   dims/status enums; invariants: no orphans, no duplicate membership, no
   impossible status, no stale derived data, no partial writes; cascade and
   rollback behavior; repeated reseed reproducibility; seed data
   distinguishable from real data.
5. **LangGraph audit** — draw implemented graph from code, diff against the
   intended eight-stage contract; per-node input/output/side-effects/retry/
   persistence; interruption/resumption repeatedly; unreachable nodes, unsafe
   retry, state loss after restart.
6. **Failure injection** — Gemini (down/timeout/garbage/rate-limit/bad key),
   Nominatim (down/empty), DB outage, restarts (backend/dashboard/container
   during gate), malformed media, Whisper failure, missing embedding/fixture,
   empty DB, duplicate/stale runs. For EACH: user-visible behavior, DB writes,
   recoverability, silent loss, safe retry, observability.
7. **Security & privacy** (defensive, MVP-scoped) — secrets in repo/git
   history, key exposure, upload restrictions (type/size/path), injection/SQL/
   XSS (`unsafe_allow_html` surfaces!), CORS, error leakage, Docker/DB
   exposure, log hygiene, pseudonymity end-to-end; production-infrastructure
   items documented as gaps, not pretended solved.
8. **Auditability** — an auditor can answer: why this cluster, why this score,
   which data contributed, what was AI vs deterministic, who approved, when
   states changed, what evidence verified resolution.
9. **Observability** — a failed pipeline execution is reconstructable from
   stored traces/logs; no meaningless log noise added.
10. **UX & accessibility** — both surfaces, citizen-first: bilingual
    consistency, error/loading/empty states, responsive layout, contrast,
    color-independence, no raw JSON/errors shown to users.
11. **Performance & reliability** — measured, not guessed: N+1s, redundant
    Gemini/embedding calls, missing timeouts, blocking ops; only fixes that
    materially affect reliability or demo UX.
12. **Concurrency & idempotency** — simultaneous submissions, duplicate gate
    actions, repeated resume, double verification, concurrent review, restart
    mid-processing: no state corruption.
13. **Test-suite audit** — per feature: does the test PROVE the requirement?
    Kill/replace status-200-only and over-mocked tests; layered suite (unit →
    integration → API → DB → graph → failure → E2E → manual).
14. **Independent review passes** — ≥10 scoped reviewers (requirements, API,
    DB, graph, AI/STT/geo, security, UI/a11y, reliability, test quality, demo
    readiness) + adversarial critic trying to DISPROVE completeness; findings
    consolidated, deduplicated.
15. **Severity** — P0 corruption/security/gate-bypass; P1 broken core or
    scoring; P2 edge/reliability/UX/auditability; P3 polish. No inflation.
16. **Fix strategy** — per confirmed defect: Requirement → Failure → Root
    Cause → Fix → Test → Regression. Preserve working functionality.
17. **Regression loop** — audit → test → find → fix → targeted retest → full
    regression → E2E → critic; repeat until P0=0, P1=0, P2/P3 fixed or
    documented with rationale.
18. **Live-vs-mock boundary** — deterministic tests mock; integration tests
    use real Postgres/PostGIS/pgvector; controlled live Gemini/Nominatim only
    where genuinely useful; DEMO_REPLAY proven with live Gemini unavailable;
    manual = genuinely human-hardware/visual only.
19. **Demo rehearsals** — full story repeatedly: happy path, equity case, AI
    failure, location failure, restart-around-gate, verification match,
    mismatch, human review.
20. **Fresh environment** — documented path from clean clone; any undocumented
    step is a documentation defect.
21. **Documentation** — README complete and precise; honest language (MVP,
    demo-ready, simulated, synthetic, production-readiness gap); no
    unearned certification claims.

## Definition of Done for the future apply (all 25, evidence-backed)

1 RTM complete · 2 every functionality tested · 3 every route inventoried +
tested · 4 DB invariants tested · 5 graph transitions/interrupt/resume tested ·
6 scoring independently verified · 7 equity dominance proven · 8 Gemini
failure safe · 9 Nominatim failure safe · 10 STT failure safe · 11 gate not
bypassable via normal paths · 12 restart/recovery verified · 13 mismatch never
auto-closes · 14 security findings fixed or documented · 15 dashboard numbers
traceable · 16 citizen errors understandable · 17 full regression green ·
18 E2E demo scenarios pass · 19 replay works without live Gemini · 20 fresh
env follows docs · 21 P0=0 · 22 P1=0 · 23 P2/P3 documented · 24 manual list
genuine · 25 README matches reality.


## Evidence home

All audit outputs live under `openspec/changes/setu-full-system-audit-and-hardening/audit/`:
`RTM.md`, `api-inventory.md`, `graph-map.md`, `findings.md` (the severity
register), `failure-matrix.md`, `manual-checklist.md`, `evidence-log.md`,
`kpi-definitions.md` (the KPI definition table, design AD14),
`frontend-logic-inventory.md` (the business-logic-in-frontend inventory over
`dashboard/`, phase-1 per design AD1), and `passes/` (the per-pass observation
logs from the parallel audit passes, design AD1 phase 2).
