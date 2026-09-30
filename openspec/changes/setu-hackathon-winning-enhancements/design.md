## Context

See proposal.md for motivation; requirements are in `specs/`. Current state that shapes the approach:

- **Pipeline**: a linear LangGraph graph (`backend/app/pipeline.py`): understand → locate → cluster → fuse → score → recommend → publish_gate (interrupt) → finalize, checkpointed in Postgres. Stage modules live in `backend/app/stages/`; each node wraps its stage in `trace.traced_stage`.
- **LLM access**: every model call goes through `backend/app/gemini.py::call_gemini` (schema-bound, retry-once, DEMO_REPLAY fixtures keyed on `sha256(stage, prompt)`). Embeddings are produced in `stages/locate.py` with a file cache.
- **Schema**: `db/schema.sql` runs only on a fresh Postgres volume (docker-entrypoint-initdb.d). There is no migration mechanism.
- **Routers** are auto-discovered from `backend/app/routers/`; the dashboard talks only to the backend API (no DB credentials, design D6 of the MVP).
- **Locked**: PriorityScore = 0.5·gap + 0.3·investment_deficit + 0.2·volume (code constants); the Publish Gate is the only publication path; `test_equity_invariant` must stay green.
- **Dashboard** container copies source at build time (no bind mount); the citizen page is bind-mounted and served by the backend.

## Goals / Non-Goals

**Goals:**
- Every new capability works on the existing single-host Docker Compose stack, with no new infrastructure services.
- Every new number on screen is derived from stored data and traceable, as with existing scores.
- The live demo remains replayable offline (DEMO_REPLAY) including the new AI calls.

**Non-Goals:**
- Changing the composite PriorityScore formula or weights. New factors (vulnerability, connectivity, urgency) are shown as context indicators and drive the silent-regions analysis, not the composite.
- React/Next.js dashboard, Redis/Celery, Kubernetes, government SSO, production RBAC beyond configured reviewer accounts.
- WhatsApp/Telegram/SMS channels (the assisted mode and intake API cover channel breadth for this change).

## Decisions

### D1 — Additive SQL migrations applied at backend startup
New tables/columns go in `db/migrations/NNN_name.sql`, applied in order at backend startup and recorded in a `schema_migrations` table; each file is idempotent (`IF NOT EXISTS`, guarded `ALTER TYPE ... ADD VALUE`). `db/schema.sql` stays the base contract.
*Alternative*: edit `schema.sql` and require a volume wipe — rejected: it silently diverges existing environments and loses demo data.

### D2 — Trust as a new pipeline stage between Cluster and Fuse
A `trust` node runs after `cluster` (the "Trust stage" already anticipated in `files/05`). It evaluates three rules — near-duplicate burst (normalised-text hash plus pgvector cosine ≥ threshold within a window, same category), repeat source (conversation_id × cluster × window), and cluster spike (recent arrivals vs baseline) — writing rows to a new `trust_flags` table (`request_id` or `cluster_id`, `rule`, `reason`, `status: open|cleared|confirmed`, reviewer fields). Thresholds are literal constants in `constants.py`, like the scoring weights.
The Score stage's complaint-volume indicator counts members **without an open or confirmed request-level flag**; the formula itself is unchanged. `demand_clusters.member_count` stays the total; the API exposes `counted_volume` alongside.
*Alternative*: detect at intake time — rejected: the cluster assignment and embedding are needed for similarity and spike rules, and a stage keeps it traced and checkpointed.

### D3 — Equity analysis computed on read from region data
Silent regions and the ranking comparison are computed by SQL at request time (`/api/insights/silent-regions`, `/api/insights/ranking`), reusing `fuse.py`'s service-radius and gap helpers so the gap definition cannot drift. `region_profiles` gains `vulnerability_index` (0–1) and `connectivity_index` (0–1) columns and a `centroid`; seed adds villages with zero requests. Thresholds (top percentile, low complaint count) are constants.
*Alternative*: materialise silent-region rows in the pipeline — rejected: they are independent of any request, so there is no pipeline run to attach them to.

### D4 — Planner is read-only simulation plus greedy max-coverage
What-if: compute coverage with an extra virtual facility in a CTE — no writes. Allocation: greedy maximum-coverage over candidate points (cluster and region centroids of the category), each round picking the candidate with the largest marginal newly-covered population. Greedy is within (1 − 1/e) of optimal for max-coverage and fast at this scale.
*Alternative*: ILP solver — rejected: new dependency, no visible benefit at demo scale.

### D5 — Categories are data plus prompt enumeration
Understand's prompt enumerates the supported categories (`water_infrastructure`, `road_infrastructure`, `healthcare`, `electricity`, `sanitation`, `education`, `other`); `fuse.CATEGORY_FACILITY_TYPES` maps healthcare → `health_facility` and road → `road_access_point`. Seed gains a healthcare equity pair and a road equity pair mirroring the water worked example; the equity-invariant test is parametrised over seeded categories.

### D6 — OSM import is a separate, labelled dataset
`db/seed/import_osm.py` queries Overpass for a bbox and category tag set (`amenity=hospital|clinic|doctors`, `amenity=drinking_water`, `man_made=water_tap|water_well`), writes one `infrastructure_datasets` row (`source='OpenStreetMap'`, `imported_at`) and its facilities in one transaction. Fuse uses the dataset named by `SCORING_DATASET` (default: the synthetic seed dataset), so the worked example cannot change unless the operator opts in.

### D7 — Open language labelling and client-side UI i18n
The Understand schema keeps `detected_language: str` but the prompt asks for the language's English name for any language (mixed → "X-English"/"Hinglish"). Citizen UI strings move to a dictionary in `app.js` (hi, en, mr), selected by a header switch and stored in localStorage (try/catch, as today).

### D8 — Locate fallbacks, and follow-up as a re-locate of the same request
Fallback chain inside Locate: Nominatim on the mention → Nominatim on the mention with suffixes stripped (गाँव/गांव/gaon/gaav/village/ward N) → case-insensitive match against `region_profiles.name` and facility names in the scoring dataset. Each fallback sets confidence `medium` with a reason.
When nothing resolves, the pipeline continues exactly as today (flagged, never dropped). The status endpoint exposes `needs_location: true`; the chat asks once. `POST /api/requests/{id}/location` stores the answer, and a `relocate` routine creates a new geocoded record, reassigns cluster membership in one transaction (recomputing member counts on both clusters), and re-runs fuse/score for the affected categories. If the original run is suspended at the gate, it stays there; the new cluster gets its own recommendation on the next run.
*Alternative*: pause the pipeline at Locate awaiting the answer — rejected: an unanswered question would strand the request, contradicting "never dropped".

### D9 — Impact from timestamps
`demand_clusters` gains `resolved_at`. Impact = requests joining the cluster (membership `created_at`) in `[resolved_at − W, resolved_at)` vs `[resolved_at, resolved_at + W)`, with W = 30 days (constant); partial windows report elapsed days. Gap before/after uses facilities with `created_at` ≤ each boundary. Seed includes one resolved cluster with backdated history.

### D10 — Dashboard: fragments for live refresh, tabs for navigation
Data panels are wrapped in `st.fragment(run_every=REFRESH_S)` so refreshes rerun only the fragment; selection, tab and reviewer inputs live in `st.session_state`. Category filter is a session-state value read by every panel. Map layers: ScatterplotLayer (clusters), HeatmapLayer (counted volume), and a distinct-shape layer for silent regions, each paired with a labelled legend. Trends use Plotly stacked bars (flagged vs unflagged). New tabs: Equity (ranking + silent regions), Planner, Impact; briefs are a download button on the selected cluster.
The dashboard Dockerfile/compose gets a bind mount for source like the backend, so UI edits don't require an image rebuild.

### D11 — Citizen timeline, read-aloud, assisted mode
`GET /api/requests/{id}/timeline` returns ordered stages with `done|current|pending` from existing tables (structured_requests, cluster_memberships, recommendations, approvals, cluster status). Read-aloud uses `window.speechSynthesis` with `lang` from the UI language; hidden when unsupported.
Assisted mode is `/citizen/?mode=assisted`: adds village and households fields; submissions are queued in localStorage with a client-generated `idempotency_key` and flushed on `online` events. The backend adds `channel='assisted'`, `households_represented`, and a unique `idempotency_key` column so a replayed flush returns the existing request instead of duplicating it. An assisted request counts as **one** unit of complaint volume; households are shown as context so a field worker cannot inflate priority.

### D12 — Briefs as print-ready HTML, not server PDF
`GET /api/briefs/{cluster_id}` renders a self-contained HTML page (Noto Sans Devanagari, print CSS, one A4 page) from stored data only; the dashboard offers it as a download, and "Save as PDF" is the browser's print. Draft watermark when the recommendation is not approved.
*Alternative*: server PDF (weasyprint/reportlab) — rejected: heavy system dependencies in the slim image, and Devanagari shaping in Python PDF libraries is unreliable.

### D13 — PII masking at the provider chokepoint
A `pii.mask(text) -> (masked, counts)` function (regex: Indian mobile numbers with optional +91, 12-digit Aadhaar-like numbers with optional spaces, emails, and the token following "my name is / मेरा नाम / माझे नाव") runs inside the provider layer (D16) on every prompt before it leaves the process, so no stage can bypass it. The trace stores masked text and counts. Fixtures record the masked prompt, keeping replay deterministic.

### D14 — Hash-chained decision log
`decision_log(seq bigserial, kind, subject_id, decision, reviewer, decided_at, payload jsonb, prev_hash, hash)`. `hash = sha256(canonical_json(entry without hash) || prev_hash)`. Appended in the same transaction as the decision (gate finalize, verification review, trust-flag review), with `SELECT ... FOR UPDATE` on the last row to serialise appends. `GET /api/audit/verify` recomputes and returns `{intact, entries, first_break}`.

### D15 — Configured reviewer accounts with signed session tokens
Reviewers come from `REVIEWERS` in `.env` (`name:scrypt-hash` pairs; a helper script generates hashes). `POST /api/auth/login` verifies with `hashlib.scrypt` and returns an HMAC-signed token (stdlib `hmac`, secret `SESSION_SECRET`, 8-hour expiry). Decision endpoints (gate resume, verification review, trust review, resolve) require `Authorization: Bearer`; the reviewer identity is taken from the token and the request body's reviewer field is ignored. Read endpoints stay open. **BREAKING for API clients**: decision endpoints now reject unauthenticated calls; the dashboard and tests are updated together.
*Alternative*: OIDC/SSO — out of scope (proposal).

### D16 — Provider interface replaces direct Gemini calls
`backend/app/llm/` with a `Provider` protocol (`complete(stage, prompt, schema, image) -> str`, `embed(text) -> list[float]`, `name`, `model`). `GeminiProvider` wraps the existing `_live_call`; `OpenAICompatProvider` uses `httpx` against `/v1/chat/completions` (JSON response format) and `/v1/embeddings`. `call_gemini` becomes a thin alias to `llm.call(...)` so existing stages and tests keep working. Selection: `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `EMBED_MODEL`. Fixture keys stay `sha256(stage, prompt)` for Gemini (backward-compatible with committed fixtures) and include provider+model for others. Startup checks embedding dimension against the 768 column (spec: refuse on mismatch).

### D17 — Evaluation and scale tooling live beside tests
`backend/eval/dataset.jsonl` (≥50 labelled items), `backend/eval/run_eval.py` (runs Understand/Locate/Cluster against a scratch schema, writes `eval/report.json` and prints a table; honours DEMO_REPLAY), `backend/eval/scale_test.py` (synthetic rows with random unit vectors near seeded centroids, times the cluster stage, no network).

### D18 — Live judge access is an explicit operator script
`scripts/share.sh` runs a Cloudflare quick tunnel to the backend and prints the URL and a QR code. It is never started by compose. Documented with the privacy implications.

## Risks / Trade-offs

- [Trust rules produce false positives on genuine mass events (e.g., a real outage)] → flags never delete; reviewers can clear; the dashboard shows total and counted volume side by side; thresholds are constants tuned on the seed.
- [Excluding flagged volume changes existing scores] → seed data has no flags, so the equity and formula tests are unaffected; a new test asserts the exclusion.
- [Auth breaks existing tests and scripts that call decision endpoints] → a test fixture issues a token; update tests in the same task as the auth change.
- [Streamlit fragment + pydeck selection interplay may reset selection] → selection lives in session_state; verify with a browser test before building further panels on it.
- [Gemini free-tier rate limits during eval runs] → eval uses DEMO_REPLAY fixtures after one recorded live pass; the report states whether it was live or replay.
- [Overpass API slow/unavailable at demo time] → import once ahead of time; imported data persists in Postgres; scoring default stays on seed data.
- [Relocate moves a request between clusters after scoring] → done in one transaction with re-fuse/re-score; covered by an integration test.
- [Regex PII masking misses names without a cue phrase] → documented limitation; masking targets structured identifiers plus self-identification phrases; the citizen UI already never asks for names.
- [Scope is large] → tasks are grouped so each group ships independently behind existing behaviour; the equity invariant and full test suite are the regression gate after every group.

## Migration Plan

1. Deploy code; backend applies `db/migrations/*` at startup (idempotent) on the existing volume.
2. Run `docker compose exec backend python /app/seed/seed.py` to add new categories, regions and history (reseed remains idempotent and embedding-cached).
3. Set `REVIEWERS` and `SESSION_SECRET` in `.env`; restart.
4. Rollback: revert code; migrations are additive (new tables/nullable columns), so the previous code runs against the migrated schema unchanged. Enum values added by migrations are harmless to old code.

## Open Questions

- Exact trust thresholds (burst window/count, similarity, spike multiple) — tuned against seed and the demo script during implementation; they do not change the spec or task breakdown.
- Whether to add Tamil/Bengali UI chrome beyond Marathi — additive dictionary entries, deferrable.
