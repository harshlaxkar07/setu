# 03 — Architecture Overview & ADR Log

**Status:** Living overview; ADR log is append-only.
**Last updated:** 2026-09-24

---

## The four layers

```text
┌─────────────────────────────────────────────────────────────┐
│  CITIZEN SURFACE   WhatsApp-style chat widget (voice/text)   │
│                     — the only citizen-facing layer           │
├─────────────────────────────────────────────────────────────┤
│  ORCHESTRATION      LangGraph pipeline: Understand → Locate  │
│                      → Cluster → Fuse → Score → Recommend    │
│                      → Publish Gate. Governed by (05).        │
├─────────────────────────────────────────────────────────────┤
│  INTELLIGENCE       Gemini API (classification, extraction,  │
│  (derived)           recommendation text) · Faster-Whisper   │
│                      (STT) · pgvector (clustering)            │
├─────────────────────────────────────────────────────────────┤
│  TRANSACTIONAL       PostgreSQL + PostGIS (source of truth:  │
│  (source of truth)   requests, clusters, datasets, scores,   │
│                       recommendations, verification records) │
└─────────────────────────────────────────────────────────────┘
```

**Service boundary (hackathon):** one FastAPI service, one Postgres+PostGIS database, one Streamlit dashboard process. A modular monolith — three services for a 2-3 person team is already too many to operate well during a hackathon window.

**Data flow, end to end:** CitizenRequest → StructuredRequest (Understand) → geocoded StructuredRequest (Locate) → joined into a DemandCluster (Cluster) → InfrastructureGapScore + PriorityIndicators computed (Fuse + Score) → Recommendation drafted (Recommend) → human-approved (Publish Gate) → visible on dashboard.

---

## ADR Log

*Format: Context → Decision → Consequences. Append-only.*

### ADR-001 — LangGraph for pipeline orchestration — **Accepted**
Context: the pipeline has seven distinct stages, each independently testable, with one mandatory human checkpoint (Publish Gate). A single giant LLM prompt can't express that structure or enforce the gate.
Decision: LangGraph, using LangChain for provider abstraction (swap Gemini later without redesigning stage logic).
Consequences: each stage is a node with typed input/output; the Publish Gate is a graph interrupt, not a UI-only convention — the backend actually cannot proceed without it. Small learning overhead is acceptable given the team's existing familiarity with agentic pipelines.

### ADR-002 — Gemini API (free tier) as the initial LLM — **Accepted**
Context: hackathon budget is zero; need structured-output extraction (category, location, urgency, summary) and short recommendation generation.
Decision: Gemini API free tier for all LLM calls; LangChain's provider abstraction means swapping later (self-hosted, sovereign, or another commercial API) touches config, not pipeline logic.
Consequences: rate limits are a real constraint during demo rehearsal — cache/replay known-good responses for the rehearsed demo path so a live rate-limit hit can't sink the presentation.

### ADR-003 — Faster-Whisper for speech-to-text — **Accepted**
Context: voice is the primary citizen input channel per the vision doc; per-request cloud STT costs and network dependency are both risks during a live demo.
Decision: Faster-Whisper running locally. No per-request cost, no network dependency, works offline for rehearsal.
Consequences: model download/setup is a one-time cost early in the build, not something to leave until the night before. Hindi accuracy should be spot-checked against the actual demo audio before relying on it live.

### ADR-004 — PostgreSQL + PostGIS as the single data store — **Accepted**
Context: need relational storage (requests, clusters, datasets) and real geospatial operations (distance, containment within ward/district boundaries) in the same store.
Decision: Postgres + PostGIS extension; pgvector extension in the same database for clustering similarity — one database, not two.
Consequences: no second database to operate during the hackathon; PostGIS's `ST_Distance`/`ST_DWithin` directly power the Cluster stage's geographic-proximity check.

### ADR-005 — Streamlit + Plotly + PyDeck for the dashboard — **Accepted**
Context: the policymaker dashboard needs a map, priority cards, and cluster views, built by a 2-3 person team with limited frontend time.
Decision: Streamlit for the app shell and interactivity, Plotly for charts, PyDeck for the map/heatmap layer.
Consequences: fast to build, but Streamlit's default look reads as "internal tool" unless deliberately styled — see `06-ui-contract.md` and `07-design-tokens.md`, which exist specifically to counter this. "UI has to be very good" is a stated requirement, not a nice-to-have, so token discipline is not optional here even though the framework is quick-and-dirty.

### ADR-006 — Geocoding via Nominatim/OpenStreetMap — **Accepted**
Context: citizens describe locations informally ("near the government school," "Ward 14"); need free, no-API-key geocoding for a demo.
Decision: Nominatim (OSM) for the hackathon; note in the pitch that production would need a paid/rate-limit-friendly provider or a government geocoding service.
Consequences: Nominatim's rate limits (1 req/sec) are fine for a demo, not for real traffic — this is a stated, accepted limitation, not a gap to hide.

### ADR-007 — No queue/cache layer (Redis/Celery) for the hackathon — **Accepted**
Context: `02-scope.md` explicitly defers this; demo data volume is small enough that synchronous/async-await calls are sufficient.
Decision: skip Redis and Celery entirely for the hackathon build. FastAPI's native async handles the pipeline's I/O-bound calls (Gemini, Nominatim, DB).
Consequences: revisit only if a specific demo step becomes visibly slow in rehearsal — add the queue then, not preemptively.

### ADR-008 — Docker Compose for deployment — **Accepted**
Context: team needs a reproducible local environment across 2-3 laptops, possibly one shared demo machine.
Decision: Docker Compose (FastAPI service + Postgres/PostGIS + Streamlit), no Kubernetes.
Consequences: one `docker-compose up` gets any team member to a working environment; production Kubernetes path is a pitch-deck line item, not a build task.
