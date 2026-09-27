# Design: build-setu-mvp

## Context

See `proposal.md` — Why. The planning docs (`files/00`–`09`) are decision-complete: architecture and ADRs in `files/03-architecture.md`, entity spine in `files/04-domain-model.md`, stage contract in `files/05-agent-orchestration.md`, UI contract and tokens in `files/06`/`files/07`, data posture in `files/08`, build order in `files/09`. This is a greenfield build — no code, no schema, no repo scaffolding exists yet. Constraints that shape everything below:

- **Modular monolith** (ADR-004, `files/03`): one FastAPI service, one Postgres+PostGIS+pgvector database, one Streamlit process. The Streamlit dashboard is therefore a *separate OS process* from the backend that owns the LangGraph graph — the Publish Gate must work across that process boundary.
- **Zero budget, fixed window**: Gemini free tier (ADR-002) with real rate limits; Nominatim at 1 req/s (ADR-006); no Redis/Celery (ADR-007); Docker Compose only (ADR-008).
- **Governing principle 2** (`files/01`): complaint volume never overrides InfrastructureGapScore — the scoring formula must guarantee this by construction, and the exit bar (`files/02`) demands the Region A/B contrast be provable live.
- The six delta specs under `openspec/changes/build-setu-mvp/specs/` define the behavioral requirements; this document covers *how* they are met, not what they are.

All decisions below are locked (recorded from the proposal round); alternatives are noted for the record, not for re-litigation.

## Goals / Non-Goals

**Goals:**

- Fix the concrete mechanics the specs leave to design: the PriorityScore formula and its normalization, the cross-process Publish Gate, the full Postgres schema outline, the citizen-web capture path, embedding/caching and the demo-day Gemini fallback, repo/compose topology, and the seeded Pune dataset.
- Lock the data contract first (`files/09` build step 1) so Track A (Intake+Geospatial) and Track B (Fusion+Dashboard) can build in parallel against one schema.
- Make every equity and trust claim mechanically enforced: the volume-cap by construction, the gate as a backend halt, flag-never-drop as schema-level defaults.

**Non-Goals:**

- No auth/RBAC, no Redis/Celery, no real government APIs, no anti-spam detection logic, no production deployment, no multi-category/multi-language beyond the scoped pair (`files/02-scope.md` non-goals; ADR-007).
- No re-derivation of pipeline stage semantics — `files/05-agent-orchestration.md` and the `pipeline-orchestration` delta spec are the contract; this document only adds implementation shape.
- No generalized configuration surface: scoring weights, thresholds, and model choices are constants in code for this build, deliberately.

## Decisions

### D1 — PriorityScore: exact formula, normalization, and the equity invariant test

**Formula (locked):**

```
PriorityScore = 0.5 * gap_norm + 0.3 * investment_deficit_norm + 0.2 * volume_norm
```

- `gap_norm` — InfrastructureGapScore, min-max normalized across all DemandClusters of the same category. Gap itself is `population / facility_coverage` computed with **zero complaint-volume input**; zero facilities in radius maps to the category's maximum gap (a defined sentinel, never a division error).
- `investment_deficit_norm` — historical investment label mapped low→1.0, medium→0.5, high→0.0, then min-max normalized within category.
- `volume_norm` — cluster member count, min-max normalized within category.
- **Degenerate normalization**: when every cluster in a category shares the same raw value for an indicator, its normalized value is the defined constant `0.5` (never NaN, never an error) — required by the fusion-scoring spec's degenerate scenario.

**Why dominance holds by construction:** every normalized term lies in [0, 1], so complaint volume contributes at most 0.2 while the gap term contributes up to 0.5. The weights are literal constants in the scoring module — not env vars, not runtime config — so no deployment or configuration state can ever let volume outweigh gap. This is the structural enforcement of governing principle 2, not a tuning choice.

**Invariant test:** a dedicated automated test (`test_equity_invariant`) runs the Score stage over the seeded Pune data and asserts `PriorityScore(Region B) > PriorityScore(Region A)` **strictly**. It runs in the standard test suite against the seeded database and fails the suite on violation. It is the executable form of the worked example in `files/04-domain-model.md` and the "Fusion/Scoring definition of done" in `files/09`. A companion test asserts the stored score equals the formula recomputed from the stored PriorityIndicators within float tolerance (no drift between score and shown factors — UI rule 1's backend guarantee).

*Alternative considered:* runtime-configurable weights with a validation rule `w_volume < w_gap`. Rejected — a validation rule can be edited; a constant cannot. The hackathon build gains nothing from tunability and loses the "by construction" claim.

### D2 — Publish Gate across the Streamlit → FastAPI process boundary

**Mechanism (locked):** LangGraph `interrupt` at the Publish Gate node, persisted by the **Postgres checkpointer** (`langgraph-checkpoint-postgres`) into the same database as everything else. Each pipeline run is a LangGraph thread; its `thread_id` is stored on the RunTrace row.

**Flow:**

1. Stages 1–6 run inside the FastAPI process (async, no queue — ADR-007). The graph reaches the Publish Gate node and interrupts; the checkpointer durably persists the suspended state in Postgres. The Recommendation row exists in status `pending`.
2. The Streamlit dashboard (separate process) polls the backend's read API. **The published-recommendations query filters on a recorded `approvals` row with decision `approved`** — pending items are only visible through the explicit awaiting-review endpoint, badged per the UI contract.
3. Approve / Reject / Request-changes in Streamlit are plain HTTP calls to `POST /api/gate/{thread_id}/resume` with `{decision, reviewer}`. The endpoint records the Approval row, then resumes the LangGraph thread from its Postgres checkpoint with the decision as the resume value. This endpoint is the **only** gate-resolution mechanism.
4. On `approved`, the resumed graph marks the Recommendation `published`; on `rejected`, terminal `rejected`; on `needs-revision`, it stays unpublished and visibly awaiting revision. Resume of an unknown or non-suspended `thread_id` returns 409 with no state change.

**Why the dashboard cannot show an unapproved recommendation:** enforcement lives in two backend layers, neither in the UI — (a) the graph literally cannot proceed past the interrupt without a resume call, surviving backend restarts via the Postgres checkpoint; (b) the dashboard-facing published query is derived solely from Approval rows. Streamlit renders what the API returns; a reviewer refreshing before approving gets a payload that simply does not contain the pending item in published results. The UI cannot fake a state the backend never emitted, and the spec's "resume endpoint failure" scenario falls out naturally: no confirmed response, no local state change.

*Alternative considered:* status-column-only gating (no real interrupt). Rejected — ADR-001's rationale is that the gate is a graph-level halt, not a convention; a status column alone cannot make the pipeline *unable* to proceed.

### D3 — Postgres schema outline (build step 1: the data contract)

One database, extensions `postgis` + `pgvector`. Every entity in `files/04-domain-model.md` maps to a table; naming below is the contract both tracks build against. (Types abbreviated; all tables get `id UUID PK`, `created_at timestamptz`.)

| Table | Key columns | Notes |
|---|---|---|
| `citizen_requests` | `channel` (voice/text/whatsapp), `raw_text`, `audio_path`, `submitter_ref` (pseudonymous), `submitted_at` | **Immutable**: no UPDATE/DELETE path in the API; enforced additionally by a row-level trigger rejecting UPDATE/DELETE. |
| `transcriptions` | `citizen_request_id FK`, `text`, `model`, `detected_language` | Derived STT artifact linked to the CitizenRequest, written when STT succeeds and **before** Understand runs (citizen-intake spec) — so a failed/`needs-retry` Understand still has the transcription persisted, and retries never redo STT. |
| `structured_requests` | `citizen_request_id FK`, `category`, `urgency`, `summary`, `detected_language`, `raw_location_mention` | One per CitizenRequest, created only by a successful Understand; reads the transcription from `transcriptions`, does not store it. |
| `geocoded_requests` | `structured_request_id FK`, `geom geometry(Point,4326) NULL`, `confidence` (high/medium/flagged), `confidence_reason`, `embedding vector(768)` | NULL geom = unresolvable location, proceeds flagged. Embedding cached here (see D5). |
| `demand_clusters` | `category`, `centroid geometry(Point,4326)`, `representative_summary`, `member_count`, `status` (active/published/resolved_unverified/resolved_verified), `confidence`, `confidence_reason` | Member count maintained on membership insert. |
| `cluster_memberships` | `geocoded_request_id FK`, `demand_cluster_id FK`, `similarity_score` | The "why it joined" join table. |
| `infrastructure_datasets` | `name`, `coverage_area`, `last_updated` | Registered seed sources. |
| `infrastructure_facilities` | `dataset_id FK`, `facility_type`, `geom geometry(Point,4326)`, `functioning bool` | PostGIS `ST_DWithin` powers the Fuse radius join. |
| `region_profiles` | `name`, `boundary geometry`, `population int`, `investment_label` (low/medium/high), `dataset_id FK` | Population + investment per seeded area (the InfrastructureDataset rows indicators cite). |
| `gap_scores` | `demand_cluster_id FK`, `population int`, `facility_count int`, `gap_value numeric`, `dataset_citations jsonb` | InfrastructureGapScore with its traceable inputs. |
| `priority_indicators` | `demand_cluster_id FK`, `name`, `value_text`, `value_numeric`, `source_citations jsonb` | One row per named factor — individually retrievable, per modeling principle 3. |
| `priority_scores` | `demand_cluster_id FK`, `score numeric`, `gap_norm`, `investment_deficit_norm`, `volume_norm`, `weights jsonb` | Stores the components so the dashboard breakdown and the formula-consistency test read stored data, not recomputation. |
| `recommendations` | `demand_cluster_id FK`, `intervention_text`, `intervention_type`, `indicator_citations jsonb`, `status` (pending/published/rejected/needs_revision), `thread_id` | Insert is refused if cluster or indicator citations are missing (spec: uncited output rejected). |
| `approvals` | `recommendation_id FK`, `decision` (approved/rejected/needs_revision), `reviewer`, `decided_at` | The gate record; published view derives from this. |
| `verification_records` | `demand_cluster_id FK`, `media_paths jsonb`, `voice_path`, `submitter_ref`, `result` (pending/match/mismatch/needs_human_review), `flagged bool`, `review_decision` | Cluster-scoped, pseudonymous; raw media immutable. |
| `run_traces` | `citizen_request_id FK`, `thread_id`, `status` (in_progress/awaiting_approval/published/rejected/needs_retry), `stages jsonb[]` (per-stage input ref, output ref, duration, error, retry, alternatives) | Retrievable by request and by cluster; the explainability record and the ops-view source. |
| *(LangGraph checkpointer tables)* | managed by `langgraph-checkpoint-postgres` | Same database, own schema — no second store to operate. |

ConfidenceLevel is an attribute (enum + reason columns) on `geocoded_requests`, `demand_clusters`, not a table — matching `files/04`'s "attached to" wording.

### D4 — Citizen-web architecture (static page → upload → pipeline trigger)

**Locked:** `citizen-web/` is a static HTML/JS/CSS page (no framework, no build step) served by FastAPI via `StaticFiles` at `/citizen` — *not* Streamlit. Bilingual chrome: Hindi (Devanagari, Noto Sans Devanagari) primary, smaller English subtitles; citizen register tokens from `files/07` (16px radii, ≥44px targets, warm accent).

**Capture path:**

1. Press-and-hold on the record button → `MediaRecorder` (`audio/webm;codecs=opus`) starts; release → stop, assemble Blob.
2. `POST /api/requests/voice` (multipart) with the audio and a `conversation_id` — a client-generated UUID kept in the page (the stable pseudonymous submitter reference; no name/phone ever requested). Text fallback posts to `/api/requests/text`.
3. The backend persists the CitizenRequest **first** (raw audio to a local volume path, row inserted), then kicks off the LangGraph run as an async task. Ingestion never waits on the pipeline — a downstream failure cannot lose the raw request.
4. The page polls `GET /api/requests/{id}/status` for the receipt: once Understand completes, it renders the submission-receipt bubble (understood category + urgency, AI-drafted marker) and the per-message language chip. Polling over WebSockets: fewer moving parts, and a 1–2 s receipt latency is fine for the demo.
5. The verification prompt (post-resolution) rides the same poll: the status payload includes any resolved cluster this `conversation_id` contributed to, and the page then offers the photo/voice follow-up upload to `POST /api/verification/{cluster_id}`.
6. **Demo sequencing note (verification bolt-on):** because the prompt is delivered only to conversations that contributed to the resolved cluster, the second demo citizen conversation must **first submit a contributing water complaint into the Region B cluster** (a rehearsed message that joins that cluster) *before* the cluster is marked resolved. Its status poll then carries the verification prompt, and the before/after photo pair upload of `files/02`'s verification bolt-on is reachable live (tasks 8.2 and 9.7 rehearse exactly this order).

*Alternative considered:* Streamlit for the citizen surface too. Rejected — Streamlit cannot deliver a WhatsApp-register mobile chat with MediaRecorder press-and-hold; a static page is less code, not more.

### D5 — Embeddings, caching, and the Gemini rate-limit fallback

- **Embeddings (locked, amended 2026-09-26):** originally `text-embedding-004`, but the live API returns 404 for it (Google retired the model); the build uses its successor **`gemini-embedding-001` at `output_dimensionality=768`** via `langchain-google-genai` — same `vector(768)` column, same cosine semantics, no other change. Seed-data embeddings are computed **once, at seed time**, by the seed script and stored in `geocoded_requests.embedding` (pgvector). Pipeline runs and rehearsals reuse cached vectors — clustering is reproducible and free-tier-safe; a backend restart triggers zero re-embedding calls (spec scenario). Only a genuinely new live submission costs one embedding call.
- **LLM (locked, amended 2026-09-26):** originally Gemini 2.5 Flash, but the live API returns 404 for new users and names **`gemini-3.8-flash`** as its successor — the build uses that for Understand extraction, Recommend drafting, and Verify vision; no other change. `GEMINI_API_KEY` from `.env` (`.env.example` committed). Structured output via LangChain's schema-bound calls; a malformed extraction fails the stage contract rather than passing garbage downstream.
- **Failure posture:** retry once, then halt the run as `needs-retry` in the ops view (per `files/05` and the orchestration spec) — never drop.
- **Demo-day fallback (ADR-002):** a **cached-replay layer** in front of the Gemini client. During rehearsal, responses for the exact rehearsed inputs are recorded to a fixture store (JSON on disk, keyed by stage + input hash). A `DEMO_REPLAY=1` env flag makes the client consult the fixture store first and fall through to live Gemini only on a miss. The rehearsed 10-step path therefore cannot be sunk by a live rate limit, while unrehearsed judge questions still hit the live model. The replay layer wraps the client — pipeline logic is identical in both modes.

### D6 — Repo layout and Docker Compose topology

**Layout (locked), at project root alongside `files/` and `openspec/`; MIT license; `git init` during apply:**

```
backend/        FastAPI app, LangGraph graph + stages, Gemini/Whisper/Nominatim clients,
                gate resume endpoint, static mount for citizen-web, tests (incl. equity invariant)
citizen-web/    static chat page: index.html, app.js, styles.css (tokens from files/07)
dashboard/      Streamlit app, custom-CSS chrome kill, token stylesheet, API client
db/             schema.sql (D3 contract), seed/ (seed script + fixtures), migrations
docker-compose.yml
LICENSE  README.md  CONTRIBUTING.md  .env.example  .gitignore
```

**Compose services (ADR-008):**

| Service | Image / build | Ports | Notes |
|---|---|---|---|
| `db` | `postgis/postgis` + pgvector (init SQL enables both extensions) | 5432 | Volume for data; healthcheck gates the others. |
| `backend` | `backend/Dockerfile` | 8000 | Serves API + `/citizen`; runs Faster-Whisper locally (model dir mounted as a volume so the one-time download persists); audio/media volume. |
| `dashboard` | `dashboard/Dockerfile` | 8501 | Streamlit; talks to `backend:8000` only — no direct DB access, so the gate cannot be bypassed by a dashboard query. |

Nominatim stays the public endpoint (1 req/s throttle in the Locate client) — self-hosting it is out of scope. One `docker-compose up` after `cp .env.example .env` + key fill is the entire environment.

### D7 — Seeded dataset design: the Pune Region A/B contrast

**Locked:** demo region is **Pune district**; Region A = a real urban Pune ward, Region B = a real rural Pune village. Every demo location string must be a real place **pre-verified against Nominatim** by a repeatable check script (`db/seed/verify_locations.py`) run before seeding and before the demo — no live geocoding surprise.

Seed contents (per `files/08` §1 and the worked example in `files/04`):

- **Region A (urban ward):** 10 functioning water InfrastructureFacility points within the service radius, `investment_label = high`, population proportioned against Census 2011 Pune urban figures, ~500 synthetic water CitizenRequests → one large DemandCluster.
- **Region B (rural village):** 0 functioning water points in radius, `investment_label = low`, realistic village population, ~20 synthetic water CitizenRequests → one small DemandCluster.
- Region profiles, facility rows, and dataset registrations carry citations so Fuse/Score outputs trace to seed rows.
- The seed script computes and caches all embeddings (D5), builds the two clusters, and leaves the database in the state the invariant test (D1), the gap-comparison panel, and the live demo all run against. Synthetic-but-realistic is stated openly in the README/pitch per `files/08`'s honest framing.
- Region B's low complaint volume is additionally seeded with the "possible under-representation signal" indicator so the dashboard scenario in the policymaker spec renders from real data.

### D8 — ConfidenceLevel provenance and the glossary drift (recorded correction)

**Locked decision 9:** in this build, ConfidenceLevel is set by exactly two stages — **Locate** (geocode confidence: high/medium/flagged with reason) and **Verify** (post-resolution plausibility outcomes). **No Trust stage exists in the hackathon pipeline.** `files/00-glossary.md` currently says ConfidenceLevel is "set by the Trust stage" and implies a 7-stage list — that is documented drift, not a requirement: the glossary line (and its pipeline-stage list) gets the one-line correction as part of this change (proposal "Doc fix carried along"). The Trust stage remains a *post-hackathon* design item (`files/02` evolution list, `files/08` §3 anti-spam design) — designed-for, not built.

### D9 — Speech-to-text

**Locked:** Faster-Whisper running locally in the backend container, model `small`, audio never leaves the host (ADR-003; privacy posture in `files/08`). Upgrade path is `medium` **only** if the 8/10 Hindi accuracy bar from `files/09`'s intake definition-of-done fails on the real demo recordings — no other STT change is in scope. Model files live on a mounted volume; the one-time download is a documented README setup step, done early per ADR-003.

## Risks / Trade-offs

- **[Streamlit polling means gate-state latency]** → The dashboard reads state via HTTP polls, so a just-approved item may lag a second or two. Acceptable: correctness is backend-enforced (D2); staleness can only *under*-show, never leak a pending item. A manual refresh affordance covers the demo.
- **[Postgres checkpointer + interrupt is the least-rehearsed integration]** → `files/09` step 4 already budgets real time for orchestration wiring; a thin integration test (suspend → restart backend container → resume by thread_id) is part of the orchestration tasks, run before the dashboard depends on it.
- **[Min-max normalization is cohort-sensitive]** → Adding clusters changes normalized values, so scores shift as data grows. Fine for the demo cohort; the invariant test pins the property that matters. Noted as a production refinement (fixed reference scales), not a hackathon fix.
- **[Faster-Whisper `small` Hindi accuracy on the real mic]** → Risk register item; mitigation is early testing with the actual demo recording setup, the `medium` upgrade path (D9), and a pre-transcribed fallback fixture on the replay path (D5) so a live STT stumble cannot kill the rehearsed demo.
- **[Nominatim availability/rate limits at demo time]** → All demo strings pre-verified and their geocode results cacheable via the same fixture approach as D5; the 1 req/s throttle is enforced in the client. Live failure degrades to flagged-not-dropped by the Locate failure posture.
- **[Gemini free-tier limits during judge Q&A (unrehearsed inputs)]** → Replay covers the rehearsed path only; a live rate limit on a novel input halts visibly as needs-retry (never a silent drop) — an honest, spec-covered failure mode rather than a crash.
- **[No dashboard→DB isolation beyond convention]** → The dashboard container gets the backend URL, not DB credentials, so the "cannot see unapproved" property doesn't rest on Streamlit code discipline. Trade-off: every dashboard feature needs a backend read endpoint; acceptable at this scale.

## Migration Plan

Greenfield — no existing system to migrate. Apply order mirrors `files/09`:

1. Scaffold repo (D6 layout, MIT license, `.env.example`, `git init`), compose file, containers build.
2. Land `db/schema.sql` (D3) — the data contract that unblocks parallel tracks — plus the checkpointer schema.
3. Seed script + Nominatim pre-verification check + cached embeddings (D7, D5).
4. Tracks A and B in parallel per `files/09` step 3; LangGraph wiring + gate integration test next; verification bolt-on last.
5. Rollback story: drop the database volume and re-run seed — everything derived is reproducible from seeds; raw demo recordings are the only non-regenerable asset (kept outside the volume).

Manual setup items (README): `GEMINI_API_KEY`, first `docker-compose up`, one-time Whisper model download, recording the rehearsed Hindi voice line on the real demo mic.

## Open Questions

- **Exact clustering thresholds** (similarity cutoff, proximity radius, and the Fuse service radius): constants to tune against the seeded data during rehearsal; the specs pin the behaviors (A/B never merge, same-category-only, ambiguity → higher similarity), not the numeric values.
- **Concrete Region A ward / Region B village name strings**: any real Pune ward/village pair that passes the pre-verification check (D7) works; final strings are chosen when the check first runs, before seeding.
- **Devanagari-friendly heading font spike** (`files/07` open item 1): Inter is the committed default; the spike happens only if time allows and changes CSS only.
