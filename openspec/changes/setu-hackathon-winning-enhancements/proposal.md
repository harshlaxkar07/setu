## Why

The Setu MVP proves the core pipeline (voice → understand → locate → cluster → fuse → score → recommend → Publish Gate → verify) on one category and one scripted scenario. Measured against the full "AI for Digital Public Infrastructure & Governance" problem statement, it leaves visible gaps a judge will probe: no manipulation detection (§12), a single seeded category, no view of underserved regions that never complain (§11), no impact measurement (§16), a single-view dashboard (§15), no policy reports (§14), and claims about provider-swapping, privacy and accuracy that are asserted rather than demonstrated. This change makes Setu well-rounded end to end — from the citizen's phone to the policymaker's brief — and turns each claim into something that can be shown live or measured.

## What Changes

- **Trust & anti-manipulation**: detect duplicate text bursts, repeat submitters, and per-cluster spikes; flag (never delete) with a stated reason and a lowered confidence; a scripted "spam attack" demo that shows flagged volume barely moving the PriorityScore.
- **Equity insights**: a *silent regions* analysis (large infrastructure gap, zero or few complaints) shown as its own map layer, and a side-by-side "rank by complaint count vs rank by Setu" comparison.
- **Investment planner**: a what-if tool — drop a proposed facility, see the recomputed gap and population newly covered — plus a budget allocator that picks N sites to maximise people served. Advisory only; nothing it produces is published without the Publish Gate.
- **More categories & real data**: healthcare and road categories with seeded region data and facility mapping; an importer for real OpenStreetMap facilities (Overpass API) for Pune district as an additional, clearly-labelled dataset.
- **Wider multilingual intake**: Understand accepts and labels any language Whisper/Gemini detect (Marathi, Tamil, Bengali, etc.) instead of Hindi/Hinglish/English only; citizen UI chrome switchable between Hindi, English and Marathi.
- **Informal location resilience**: when geocoding fails, fall back to landmark/facility and region-name lookup; when still unresolved, the citizen chat asks one follow-up location question.
- **Impact measurement**: per-cluster before/after panel (complaint rate and gap score before vs after resolution).
- **Live analytics dashboard**: auto-refresh, demand heatmap, category filter, trend chart, and the new equity/planner/impact views.
- **Citizen experience**: a status timeline per submission (received → understood → grouped → under review → published → resolved), receipts read aloud in the citizen's language, and an assisted-reporting mode for field workers that queues submissions offline and syncs later.
- **Policy briefs**: a one-page bilingual (English + Hindi) brief per cluster, exportable from the dashboard, containing only stored evidence, the score breakdown, and the recommendation with its approval status.
- **Privacy & governance**: PII (phone numbers, Aadhaar-like numbers, emails, names after "my name is") masked before any text reaches an LLM; hash-chained approval log with a verify endpoint; configured reviewer accounts with passcodes replacing the free-text reviewer field.
- **Provider abstraction**: LLM and embedding calls go through one provider interface selectable by environment variable (Gemini default; OpenAI-compatible local endpoint such as Ollama as the second implementation).
- **Evaluation & scale evidence**: a labelled multilingual evaluation set with a harness reporting category, urgency, location and clustering accuracy; a synthetic scale test reporting clustering throughput.

Locked decisions are preserved: the Publish Gate remains the only path to publication; the composite PriorityScore formula and its weights (volume 0.2 < gap 0.5) are unchanged; the equity-invariant test must stay green.

## Capabilities

### New Capabilities

- `trust-anti-manipulation`: detection of duplicate bursts, repeat submitters and cluster spikes; flag-with-reason semantics; spam-attack demo script.
- `equity-insights`: silent-regions analysis and the complaint-count vs Setu ranking comparison.
- `investment-planner`: what-if facility placement and budget-constrained site allocation.
- `multi-category-data`: healthcare and road categories end to end, and the OSM real-facility importer.
- `multilingual-intake`: open language detection/labelling, Marathi UI chrome, informal-location fallbacks and the follow-up location question.
- `impact-measurement`: before/after metrics for resolved clusters.
- `dashboard-analytics`: auto-refresh, heatmap, category filter, trends, and hosting the new equity/planner/impact views.
- `citizen-experience`: status timeline, read-aloud receipts, assisted field-worker mode with offline queue.
- `policy-briefs`: bilingual per-cluster brief export.
- `privacy-governance`: PII masking before LLM calls, hash-chained approval log, configured reviewer accounts.
- `llm-provider-abstraction`: provider interface with Gemini and OpenAI-compatible implementations.
- `evaluation-harness`: labelled evaluation set, accuracy report, and scale test.

### Modified Capabilities

_None under `openspec/specs/` (no capability has been archived yet)._ Where this change extends behaviour first defined in the in-flight `build-setu-mvp` change (citizen-intake, fusion-scoring, policymaker-dashboard), the extension is written as ADDED requirements in the new capabilities above, so the MVP deltas remain unchanged.

## Impact

- **Backend**: new modules for trust detection, equity analysis, planner, impact, briefs, PII masking, audit chain, provider interface; new routes under `/api/insights`, `/api/planner`, `/api/briefs`, `/api/audit`, `/api/requests/{id}/timeline`, `/api/auth`; Understand/Locate stage changes; new tables and columns (migration applied on top of `db/schema.sql`).
- **Database**: new tables for trust flags, audit chain, reviewer accounts, region vulnerability/connectivity attributes, OSM dataset rows; seed extended with healthcare/road data.
- **Dashboard**: new tabs and views; auto-refresh; brief download; reviewer sign-in.
- **Citizen web**: timeline, read-aloud, language switcher, follow-up location prompt, assisted mode with offline queue.
- **Dependencies**: a PDF/HTML brief renderer (e.g. `weasyprint` or HTML-only export), `openai`-compatible client (via `httpx`, no new SDK required); no new infrastructure services (no Redis/Celery).
- **Tests**: new unit and integration tests per capability; the equity-invariant and formula-consistency tests remain and must pass.
- **Assumptions recorded**: the seeded Velhe/Kothrud dataset stays the canonical demo dataset (real OSM data is additive and labelled, so it cannot silently change the worked example); exposing the citizen page publicly for live judge submissions is an opt-in operator script, never automatic; a React rewrite of the dashboard is out of scope.
