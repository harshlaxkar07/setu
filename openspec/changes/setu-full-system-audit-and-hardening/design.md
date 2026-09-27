# Design: setu-full-system-audit-and-hardening

## Context

See `proposal.md` — Why. This change audits and hardens the implemented `build-setu-mvp` system; it does not rebuild it. The behavioral bar is set elsewhere and is not restated here:

- `audit/BRIEF.md` — the distilled mandate: 21 audit areas, the 25-item Definition of Done, and the evidence home (`audit/`).
- The nine assurance delta specs under `specs/assurance/` — the requirement-level contract for the audit itself (requirements-traceability, api-surface, data-integrity, pipeline-and-concurrency, failure-safety, security-privacy, auditability-observability, ux-accessibility, quality-gates).
- The system under audit: `build-setu-mvp`'s six delta specs, its design decisions D1–D9 (with the dated 2026-09-26 model amendments), `files/00–09`, and `README.md`. Its `tasks.md` (58/66 checked) is treated as a list of claims, never as evidence.

Constraints that shape the approach:

- **Locked decisions stay locked.** D1–D9 are re-verified, not re-litigated. Only concrete, reproduced evidence that a decision is defective can reopen one, and that evidence goes through the findings register first.
- **The audit's subject is a running composed system**: FastAPI backend (owning the LangGraph graph and the Postgres checkpointer), a separate Streamlit process, a static citizen page served at `/citizen`, one Postgres+PostGIS+pgvector database, all under `docker-compose.yml`. Several proofs (restart survival, cross-process gate, fresh-environment) are only meaningful at the docker level.
- **Injection seams already exist in the code** and the audit uses them rather than adding new ones: `call_gemini(..., _caller=)` in `backend/app/gemini.py`; `_transport=` / `_embedder=` on the Locate stage in `backend/app/stages/locate.py`; the `DEMO_REPLAY` / `FIXTURE_DIR` replay layer; container-level start/stop for the database, backend, and dashboard.
- **Hard guardrails**: human-in-the-loop controls are never weakened; tests are never weakened to pass; failures are surfaced, never hidden; fixes are root-cause, no speculative refactors.
- **Free-tier reality**: live Gemini and Nominatim are rate-limited external services; the default automated suite must not depend on them (quality-gates spec, live-vs-mock rules).

## Goals / Non-Goals

**Goals:**

- Define the audit's execution architecture: what runs in what order, how ≥10 scoped review perspectives run without trampling each other, and how their raw observations become deduplicated, severity-classified findings.
- Fix the construction method and storage format of each evidence artifact (RTM, api-inventory, graph-map, findings register, failure matrix, manual checklist, evidence log) so every artifact is diff-checkable against reality, as the specs require.
- Define the test-layer taxonomy and where each new test type lives in `backend/tests/`, so the strengthened suite stays runnable as one documented command.
- Specify technique-level how for the hard proofs: failure injection per dependency, concurrency probes, the security sweep (including git history and XSS), and the live-vs-mock boundary with a controlled-live budget.
- Define the issue lifecycle (findings schema, severity discipline, fix guardrails) and the regression/exit machinery that maps to the Definition of Done.

**Non-Goals:**

- No restating of requirement text — the nine assurance specs are the what; this document is only the how.
- No redesign of the audited system's architecture, schema, pipeline shape, or stack (that is `build-setu-mvp`'s design; changes to it require evidence of defect, per the guardrail above).
- No production-tier machinery for the audit itself: no CI service, no external tracking tools — the findings register and evidence log in `audit/` are the system of record.
- No test-coverage percentage targets. The bar is proof strength per requirement (PROVES/WEAK/MISSING verdicts), not a coverage number.

## Decisions

### AD1 — Execution architecture: inventory first, then parallel scoped passes, then consolidation, then fix waves

**Shape (locked):** the audit runs in five phases; evidence artifacts are append-only across phases.

1. **Inventory phase (serial, first).** Build the ground-truth artifacts everything else cites: the RTM skeleton (AD2), `audit/api-inventory.md` (routes auto-discovered from the FastAPI app object — `app.routes` at import, cross-checked against `/openapi.json` on the running stack — never from docs), `audit/graph-map.md` (nodes/edges read from the graph construction in `backend/app/pipeline.py`, including the out-of-graph Verify invocation and the inline intake fallback in `routers/requests.py`), the test-layer inventory (AD3), and the dashboard-value provenance inventory over `dashboard/` — every displayed value mapped to its API source, or flagged as locally computed (feeds the ux-accessibility and auditability passes; DoD-15). Inventory runs are read-only: no fixes, no test edits.
2. **Audit passes (parallel, scoped).** Eleven review perspectives, each with a fixed scope, a fixed artifact to write into, and no authority to fix anything: requirements/RTM, API surface, DB integrity, graph/pipeline, AI+STT+geo behavior, security/privacy, UX/accessibility, reliability/performance, test quality, demo readiness, and the **adversarial critic** — whose brief is to disprove completeness: hunt gate bypasses, hunt untested claims in the other passes' outputs, challenge every manual-checklist entry and every PROVES verdict. Passes may run concurrently because each writes only its own observation log; nothing writes `findings.md` yet. A pass that needs a probe run against the stack records the exact command it ran, so re-execution is mechanical.
3. **Consolidation (serial).** All observation logs merge into candidate findings; duplicates collapse (one finding, many evidence citations); anything not reproducible on a second attempt is demoted to an investigation note (quality-gates spec). Severity is assigned here, once, by the fixed P0–P3 definitions (AD8) — never by the pass that found the issue, which removes the incentive to inflate.
4. **Fix waves by severity.** P0s fix immediately and alone (one fix, one targeted verification, one full regression before the next P0). P1s in small batches per subsystem. P2/P3 batched or explicitly documented-with-rationale. Every fix follows `Requirement → Failure → Root Cause → Fix → Test → Regression` and lands with its proving test in the same commit.
5. **Regression loop until exit.** audit → test → find → fix → targeted retest → full regression → E2E rehearsals → critic re-pass; repeat. The critic re-pass after each wave diffs the suite for weakened assertions (a weakened test is itself a finding). Exit criteria are AD9's.

*Alternative considered:* a single linear deep-dive per subsystem (audit+fix together). Rejected — fixing while auditing biases the auditor toward what is fixable, and a moving codebase invalidates sibling passes' evidence. Inventory-first with read-only passes keeps all evidence dated against one code state per cycle.


### AD2 — RTM construction: source-ordered rows in one Markdown table, statuses earn evidence links

**Format (locked):** `audit/RTM.md` is a single Markdown document, one section per source document (in this order: `files/00`…`files/09`, the six `build-setu-mvp` delta specs, design D1–D9 + amendments, `README.md`), each section a table with columns:

```
| ID | Requirement (condensed) | Source ref | Spec | Implementation | Test | Runtime evidence | Status |
```

- **ID** is stable and source-prefixed (`RTM-F05-012` = `files/05`, 12th row; `RTM-SPEC-CI-003` = citizen-intake spec; `RTM-D2-001` = design decision D2), so findings and evidence-log entries can cite rows permanently.
- **Row harvesting rule:** every SHALL/MUST, every scenario, every numbered definition-of-done item, every locked design mechanism, and every README factual claim becomes a row. Prose that states no verifiable behavior is skipped, and each skipped section is listed once at the bottom of its source's section ("not requirements: …") so completeness is checkable, not assumed.
- **Status vocabulary** is exactly the spec's eight: verified / under-verified / partial / incorrect / missing / conflicting / obsolete / manual-only.
- **Evidence discipline:** a row starts at best `under-verified` (a checked `tasks.md` box is a claim). It becomes `verified` only when the Test or Runtime-evidence cell links to something produced by THIS audit: a named test (`test_gate.py::test_resume_records_single_approval`), a dated `audit/evidence-log.md` entry, or a manual-checklist result. `incorrect`/`missing`/`conflicting` rows must link a findings-register ID; `obsolete` and `manual-only` must link a one-line rationale. The RTM is complete when a `grep` for empty Status/evidence cells returns nothing — the mechanical check the traceability spec demands.
- Conflicts (e.g., the D8-recorded glossary drift: `files/00` "set by the Trust stage" vs. the implemented two-setter reality) get `conflicting` rows citing both sources plus the implementation's actual behavior, resolved through the findings register, never silently harmonized.

*Alternative considered:* a CSV/spreadsheet or per-capability RTM files. Rejected — one Markdown file is diffable in review, greppable for the completeness check, and linkable at row granularity; splitting it recreates the "which file owns this requirement" ambiguity the RTM exists to kill.

### AD3 — Test-layer taxonomy and placement in `backend/tests/`

The existing 12 files / 95 tests stay where they are (never deleted, strengthened in place per the quality-gates spec). New audit tests land in layer-named files so the layer inventory maps files to layers mostly one-to-one:

| Layer | Placement | Contents |
|---|---|---|
| unit | existing `test_<stage>.py` files (extended) | pure logic, externals stubbed via the code's own seams |
| integration (real DB) | existing stage tests that touch Postgres + new cases | persistence/geometry/vector/constraint behavior against real Postgres+PostGIS+pgvector, per the live-vs-mock rule |
| API negative matrix | `test_api_matrix.py` (new) | the per-route negative-input matrix from the api-surface spec, parameterized route × case |
| DB invariant | `test_db_invariants.py` (new) | orphans, duplicate memberships, illegal statuses, stale aggregates, partial-write checks; also invoked as the failure campaign's closing accounting check |
| graph | `test_pipeline.py` (extended) + `test_graph_contract.py` (new) | graph-map conformance, per-node contract cells, interrupt/resume, retry-no-reexecution |
| failure injection | `test_failures.py` (new) | the deterministic subset of the failure matrix (AD4) |
| concurrency | `test_concurrency.py` (new) | the probes of AD6 that are runnable in-process |
| security | `test_security.py` (new) | upload caps, hostile filenames, injection probes, pseudonymity key-sweeps, XSS round-trip fixtures |
| E2E scenario | `test_e2e_scenarios.py` (new) | the automatable core of the eight demo-rehearsal scenarios through the real stack |
| dashboard AppTest | `dashboard/tests/test_dashboard_apptest.py` (new — dashboard container, not `backend/tests/`) | Streamlit `AppTest` structural assertions (states, badges, chrome-hiding, degraded payloads) against a stubbed `dashboard/api.py` client |
| manual | `audit/manual-checklist.md` only | genuinely human/hardware checks (AD10) — never a pytest skip |

The automated set is runnable as exactly two documented commands: the backend layers as `docker compose exec backend pytest tests/ -q`, and the dashboard AppTest layer as `docker compose exec dashboard pytest tests/ -q` (with `pytest` and Streamlit's testing extras added to the dashboard image's dev dependencies). The AppTest layer lives in the dashboard container because the backend container deliberately has neither the `streamlit` package nor the `dashboard/` source (build-setu-mvp D6 isolation — the dashboard service shares no code or DB credentials with the backend, and this placement preserves that guarantee rather than mounting `dashboard/` into the backend). "Full suite green" everywhere in this design means both commands green. Docker-orchestration-dependent proofs (container restarts, DB outage, fresh environment) are scripted procedures logged in `audit/evidence-log.md`, not pytest tests, because they must kill the very process pytest would run in.

*Alternative considered:* a `tests/audit/` subtree. Rejected — a second tree invites a second conftest and a drifting invocation; the layer inventory (a table in the evidence log) provides the classification without moving anything.

### AD4 — Failure-injection technique per dependency, and what "safe" means

Each row of the locked failure list (failure-safety spec) is injected at the narrowest seam that produces the real failure shape, and "safe" is defined per scenario as the spec's six dimensions — the notes below fix the *technique*:

| Failure | Injection technique | "Safe" means (summary — full contract in failure-safety spec) |
|---|---|---|
| Gemini down / timeout / garbage / 429 / bad key | `_caller=` injection in `call_gemini` raising the exact exception class or returning schema-invalid payloads; bad-key run also done live-at-docker-level once with an invalid `GEMINI_API_KEY` in `.env` | retry exactly once → `needs_retry`; upstream rows untouched; no fabricated row for the failed stage; visible in `GET /api/ops/runs`; citizen poll returns a defined status, never 5xx |
| Nominatim down / empty | `_transport=` injection in Locate raising / returning `[]` | `geom` NULL + `confidence='flagged'` + true reason; run proceeds as flagged solo cluster; **no coordinate is ever fabricated** |
| Missing embedding | `_embedder=` injection returning failure; plus a fixture row with NULL embedding | flagged single-member cluster with reason; similarity matching ignores embedding-less members |
| Whisper/STT failure | monkeypatch `app.stt.transcribe` / corrupt-bytes upload within caps | audio + `citizen_requests` row already persisted and retained; no fabricated transcript; `needs_retry`; retry re-attempts STT only if no transcription committed |
| Malformed media | real HTTP uploads at the boundary (empty, oversized, over-count, garbage bytes) | boundary rejections (400/413) leave zero rows and zero files; in-cap garbage persists immutably and fails downstream through the STT/Verify postures |
| DB outage | `docker compose stop db` around live HTTP calls | no acknowledgment without persistence; gate decision during outage changes nothing; post-restore accounting finds every acknowledged request |
| Backend/dashboard/compose restart during suspended gate | `docker compose restart <service>` / full `down`+`up` with a run suspended at `publish_gate` | suspended run survives, publishes nothing, resumable exactly once; dashboard restart changes no state |
| Missing/corrupt replay fixture | delete/corrupt the keyed file under `FIXTURE_DIR` with `DEMO_REPLAY=1` | miss falls through to live; miss+live-down halts visibly; corrupt fixture never fabricates a response |
| Empty DB | fresh schema, no seed | explicit empty states everywhere; first submission scores via the degenerate-normalization constant, no NaN |
| Duplicate / stale runs | scripted double-submission; suspended run held across later cluster transitions | both-accepted posture recorded as specified; stale approval never regresses later cluster status; 409 on non-suspended resume |

Two rules bind all rows: **(1)** in-process seam injection proves logic; the docker-level variant of the same failure is additionally executed once where the process boundary itself is the claim (restarts, DB outage, bad key at startup) — a mock cannot prove a checkpoint survives a dead process. **(2)** Every row ends with the closing accounting queries (zero-loss check) before the campaign is declared done; the queries and their zero-violation output are the matrix's final entry.

`audit/failure-matrix.md` format: one row per enumerated failure, six dimension columns, each cell citing a test ID or a dated evidence-log procedure — a blank or claim-only cell is by definition an open finding.

### AD5 — Live-vs-mock decision rules, the controlled-live budget, and the DEMO_REPLAY re-proof

**Decision rules (restating the quality-gates boundary as an operating procedure):**

1. Deterministic tests stub Gemini/Nominatim/Whisper at the code's own seams; they never stub Postgres — persistence, geometry, vector, and constraint claims run on the real composed database, always.
2. The default suite invocation must pass with live Gemini and Nominatim unreachable; this is itself an executed check (run the suite with an invalid key and blocked egress once per cycle).
3. **Controlled-live budget:** live external calls happen only in explicitly marked, manually invoked checks (`@pytest.mark.live`, excluded by default), capped per audit cycle at **≤10 live Gemini calls and ≤10 live Nominatim calls** — enough for one end-to-end live sanity pass and the bad-key probe, small enough that the free tier and the 1 req/s throttle are never the flaky element in the audit's own evidence. Every live call spent is logged (date, purpose, outcome) in the evidence log; the budget is a discipline device, not a hard technical limit — exceeding it requires a written reason in the log.
4. **DEMO_REPLAY re-proof (DoD item 19):** executed at docker level, twice per exit claim — the full rehearsed demo path with `DEMO_REPLAY=1` and live Gemini made genuinely unreachable (invalid `GEMINI_API_KEY`), proving completion from `FIXTURE_DIR` with zero outbound calls; then one unrehearsed input in the same state, proving the miss path halts visibly as `needs_retry` rather than answering from a wrong fixture.
5. Anything neither automatable nor live-budgetable is manual only if it survives AD10's automation challenge.

### AD6 — Concurrency probe technique

**Technique (locked):** real parallel HTTP against the running composed backend — `httpx.AsyncClient` with `asyncio.gather` (or a thread pool for sync clients), N≥10 for submission floods, N=2 racing writers for decision races — never mocked concurrency, because the claims under test are DB-transaction and endpoint-guard claims. Each probe is: **fire in parallel → collect every response → run the post-state invariant queries → record both in the evidence log.**

- The probes and their invariants are AD6's list, which starts from the pipeline-and-concurrency spec's concurrent-operations requirement (simultaneous submissions; conflicting/duplicate gate resumes; repeated resume of decided threads; double verification submission; racing review actions) and adds two design-level probes the spec does not enumerate: racing resolve calls and racing operator retries (the N≥10 submission-flood floor is likewise this design's floor, not a spec number). The design also adds the **repeated-resume soak**: the same suspended thread resumed once successfully, then hammered with 20 sequential re-resumes asserting 409 + zero new `approvals` rows each time.
- **Atomic-transition checks:** every guarded status move (`active→published`, `published→resolved_unverified`, review-decision recording, retry kick) is probed by the two-racing-writers pattern and judged by "exactly one winner, loser gets 409, exactly one recording row, final status legal". Where a race is hard to hit reliably over HTTP, the same two-writer race is additionally staged at the DB layer inside a test using two connections and explicit transaction interleaving — the HTTP probe proves the deployed behavior, the DB-level test pins it deterministically for regression.
- Violated invariants are P0 state-corruption findings by definition; a probe that cannot demonstrate the race (both orders tried, no interleaving achieved) is recorded as attempted-with-method, not silently dropped.

### AD7 — Security review method: sweeps + probes, git-history included, XSS proven in the rendered surface

The security-privacy spec fixes the requirements; the method is **inventory-sweep first, live-probe second**, both recorded:

- **Secrets:** pattern scan (`AIza…`, `PRIVATE KEY`, bearer/OAuth shapes, `password=`/`_KEY=` with non-placeholder values) over the working tree **and** full git history (`git log --all -p`); plus the `.env`-never-added check (`git log --all --diff-filter=A --name-only`). If the audited checkout has no git history at execution time, that fact is itself recorded in the evidence log and the sweep runs against whatever history exists wherever the repo is version-controlled — the sweep is never silently skipped. Any live credential found: P0, remediation includes rotation at the issuer, never deletion-in-a-new-commit alone.
- **SQL:** exhaustive classification of every `execute(` call site under `backend/app/` and `db/seed/` (static / constant-fragment / interpolation) — the inventory is the proof; boundary injection probes (`' OR '1'='1`, `; DROP TABLE …`, `UNION SELECT` via text body, `conversation_id`, `status` filter, path ids) confirm inertness live.
- **XSS, Streamlit surface:** two-sided proof. *Sweep side:* all `unsafe_allow_html=True` call sites in `dashboard/app.py` / `dashboard/components.py` (35 at audit start) inventoried, every interpolated value traced to source and classified escaped/literal/unproven — an unescaped API-sourced interpolation is at minimum P1. *Round-trip side:* hostile markup (`<script>`, `<img src=x onerror=…>`) planted at every ingress that reaches those renders — citizen text via `POST /api/requests/text`, `reviewer` via the gate resume, and controlled fixtures for AI-drafted fields (`representative_summary`, `intervention_text`, indicator `value_text`, `confidence_reason`, trace `error`) — then the rendered output asserted inert via `AppTest` rendered-body assertions in the dashboard AppTest layer (`dashboard/tests/`, per AD3 — the planting side lives in `backend/tests/test_security.py`; the render-side assertion cannot run in the backend container) (the markup appears escaped, no raw tag), with one scripted browser walkthrough confirming the same in a real render. Code reading alone never closes an XSS row.
- **XSS, citizen DOM:** source sweep of `citizen-web/app.js`/`index.html` for `innerHTML`/`insertAdjacentHTML`/`document.write` with dynamic input (target: zero), plus a round-trip: a status-poll payload whose fields carry markup, asserted to land as literal text nodes.
- **Exposure/hygiene:** compose port inventory vs. the reviewed set, dashboard-container env check (no DB credentials — the D6 guarantee), `docker history` secret scan, full-scenario log capture grepped for the key, DB password, every `submitter_ref`, and raw citizen texts.
- Production-tier items (auth/RBAC, TLS, rate limiting, retention deletion, consent) are documented as explicit README gaps — never "fixed" into scope, never claimed solved.

### AD8 — Issue lifecycle: findings schema, severity discipline, fix guardrails

- **Single register:** `audit/findings.md`, append-only. Record schema (per the quality-gates spec, fixed here as the literal template every entry uses):

  ```
  ## F-### — <finding statement>
  - Severity: P0|P1|P2|P3 (history: <prior> → <new>, rationale — only if reclassified)
  - Evidence: <exact command/query/test + observed output>
  - RTM/Spec ref: <RTM row id and/or assurance spec requirement>
  - Root cause:
  - Fix: <commit/description> | Not fixed — rationale:
  - Verification: <test or repeatable procedure that now passes and would have failed before>
  - Status: open | fixed-verified | documented-accepted
  ```

- **Severity bar (no inflation, no deflation):** P0 = corruption, security exposure, any gate bypass; P1 = broken core functionality or incorrect scoring; P2 = edge/reliability/UX/auditability gaps; P3 = polish. Assigned once at consolidation (AD1) by the fixed definitions; reclassification keeps the prior severity visible with rationale. Unreproducible suspicions never enter the register — they live as investigation notes with what was attempted.
- **Fix guardrails:** root cause only; the proving test lands with the fix; no fix may weaken an assertion, skip a test, widen a tolerance, remove a human-in-the-loop control, or reopen a locked decision without register evidence; a fix that breaks a previously green test spawns its own finding and the original test stays intact. Findings are never deleted — closure is only by filling Fix + Verification.
- **Spec coupling (explicit):** delta specs for existing `build-setu-mvp` capabilities (citizen-intake, geospatial-clustering, fusion-scoring, pipeline-orchestration, …) are added to THIS change **only when a confirmed, register-recorded fix changes spec-level behavior** of that capability — at that moment, as part of the fix wave, keeping artifacts coherent. Pure hardening (a stronger test, an escaped render, a tightened guard that the existing spec already implies) adds no delta spec.

**Pre-registered candidate findings** (spotted during planning; they enter consolidation as ordinary unconfirmed observations, no privileged status): (a) `/api/ops/runs` LEFT-JOINs `run_traces`, so a request with multiple traces produces duplicate rows — each request should appear exactly once at its latest status; (b) invalid (non-UUID) ids on cluster routes can surface as 500s instead of 4xx parameter validation; (c) `db/seed/seed.py` labels some Devanagari templates "Hinglish" (first-character `isascii()` heuristic on formatted text), a mislabeled detected-language in seed data.

### AD9 — Regression and exit criteria: the DoD gate

- **Regression cadence:** targeted verification per fix; full suite per fix wave; the eight-scenario E2E rehearsal matrix and the critic re-pass per loop iteration. Exit evidence must be dated after the last code change (quality-gates spec).
- **Exit =** all of, simultaneously: P0 = 0, P1 = 0; every P2/P3 fixed-verified or documented-accepted; one full-suite green run via the two documented commands of AD3, executed back-to-back against the same code state; all eight rehearsal scenarios with ≥2 recorded executions, most recent passing; fresh-environment walkthrough clean; and the **DoD checklist** complete: all 25 items of `audit/BRIEF.md`'s Definition of Done gated exactly per the quality-gates spec's "Definition-of-Done checklist gated by citations" requirement — each item checked only with a citation to existing evidence (an RTM row, a named test, a findings record, or a dated evidence-log entry) that substantiates it without further searching. The completed checklist lives in `audit/evidence-log.md`.
- Reaching green by weakening anything is defined as non-exit, and the critic's before/after suite diff is the enforcement mechanism.

### AD10 — Manual-verification boundary and walkthrough scripts

- **Boundary rule:** `audit/manual-checklist.md` contains only checks requiring human perception or physical hardware — Devanagari glyph fidelity (no tofu), real-device press-and-hold and audio playback, on-screen legibility/grayscale perception, visual chrome absence, physical-size layout fidelity, the real-microphone Hindi capture. Everything with a feasible `AppTest`/DOM/computed check is automated instead, and the adversarial critic explicitly challenges every entry with "could a test verify this?" — entries that fail the challenge are converted and the conversion recorded.
- **Entry format (locked):** surface/URL, device or viewport, required demo-data state, ordered actions, expected observation, pass/fail + date + checker, and a one-line cannot-automate justification. The test of the format is the spec's own: a person unfamiliar with the codebase can execute it as written.
- Manual results are evidence: referenced from the evidence log, failures filed as findings, and `manual-only` RTM rows cite their checklist entry.

### AD11 — Evidence log as the audit's journal

`audit/evidence-log.md` is the single chronological journal every other artifact cites for anything executed rather than written: dated entries with the exact command/procedure, environment mode (live vs `DEMO_REPLAY`, seeded vs empty), observed output summary, and what the entry evidences (RTM row, DoD item, matrix cell, rehearsal scenario). Rationale: the specs repeatedly require that a later reader re-verify claims "from the citation alone"; one journal with stable dated entries makes every citation a pointer instead of a paraphrase, and makes the "evidence dated after the last code change" exit check a mechanical scan.

## Risks / Trade-offs

- **[Scope sprawl — 21 audit areas can expand without bound]** → The severity bar is the throttle: only register findings drive work; P2/P3 may exit as documented-accepted with rationale; performance work is explicitly limited to what materially affects reliability or demo UX; the controlled-live budget caps external-service exploration; the critic attacks completeness of *evidence*, not breadth of *ambition*.
- **[Fix-induced regression — hardening breaks the working demo]** → Fix waves are severity-ordered and small; full regression per wave; a fix that reddens a green test becomes its own finding with the test kept intact.
- **[Flaky live services poison evidence]** → The default suite has zero live dependencies (enforced by an actual run with egress blocked); live calls are budgeted, marked, and logged; the rehearsed demo path is proven on replay with live Gemini unreachable, so no exit criterion depends on a third-party service being up.
- **[Parallel audit passes drift against a changing codebase]** → Passes are read-only and run against a fixed code state per cycle; fixes happen only after consolidation; each loop iteration re-dates its evidence.
- **[Concurrency probes are nondeterministic]** → HTTP probes prove deployed behavior; DB-level two-connection interleaving tests pin the same race deterministically for regression; probes that fail to achieve interleaving are recorded as attempted-with-method rather than counted as passes.
- **[Docker-level procedures can't live in pytest, risking "tested" claims that were never run]** → Every docker-level proof is a scripted procedure with a dated evidence-log entry, cited from the failure matrix or DoD checklist; a matrix cell citing nothing is by definition an open finding, so an unrun procedure is visible, not silent.
- **[Auditor bias — the audit is executed by the same agent family that built the system]** → Structural countermeasures: build-time checkmarks inadmissible as evidence (RTM rule), the adversarial critic pass whose only brief is disproof, mutation spot-checks for PROVES verdicts, and independent recomputation (hand-computed scoring cases, KPI-vs-fixture checks) rather than trusting stored outputs.

## Migration Plan

Not a deployment — the audit operates on the existing docker-compose stack. Operational sequencing:

1. Phase 1 inventories land first (RTM skeleton, api-inventory, graph-map, test-layer and frontend-logic inventories) — all read-only.
2. Audit passes and consolidation produce the initial findings register; fix waves then proceed P0 → P1 → P2/P3 with the regression cadence of AD9.
3. Rollback story for fixes: every fix is a discrete commit paired with its proving test; reverting a fix reverts its commit and reopens its finding (Status back to open) — the register, being append-only, records both directions.
4. The change is complete only at AD9's exit gate; archiving remains a separate decision (`build-setu-mvp` stays unarchived as the requirement baseline throughout).

## Open Questions

- **Exact parameters of the concurrency soak** (submission-flood N beyond AD6's ≥10 floor, repeat counts for the resume soak): tuned during execution against observed flake rates; the specs pin the invariants, and this design pins the floor — the specs carry no load numbers.
- **Whether the repeated-reseed equivalence check compares scores exactly or within float tolerance** for embedding-order-dependent values: decided when the first double-reseed runs, documented with the equivalence checks in the evidence log either way.
