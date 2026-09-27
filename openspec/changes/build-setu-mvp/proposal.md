# Proposal: build-setu-mvp

## Why

Setu's planning docs (`files/00`–`09`) are decision-complete, but no code exists. This change builds the entire hackathon MVP: the 10-step demo scenario from `files/02-scope.md` — a Hindi voice complaint in, an evidence-cited, human-approved recommendation out on a policymaker dashboard — plus the verification bolt-on. One demo scenario built completely beats many modules built partially; the hackathon window is fixed and the exit bar is already defined.

## What Changes

- New FastAPI backend hosting the LangGraph pipeline (Understand → Locate → Cluster → Fuse → Score → Recommend → Publish Gate → Verify) per `files/05-agent-orchestration.md`, with Postgres + PostGIS + pgvector as the single store (ADR-004).
- New citizen-facing chat page (FastAPI-served HTML/JS, WhatsApp-style, press-and-hold voice via MediaRecorder), bilingual Hindi-primary chrome.
- Faster-Whisper (local, `small` model) speech-to-text; Gemini 2.5 Flash free tier for classification/extraction/recommendation/vision; Gemini `text-embedding-004` for clustering embeddings (seed data embedded once and cached).
- New Streamlit policymaker dashboard (Plotly + PyDeck) styled per `files/07-design-tokens.md` with Streamlit chrome fully hidden; Publish Gate as a real LangGraph interrupt resumed via a FastAPI endpoint (Postgres checkpointer).
- PriorityScore defined concretely: normalized weighted sum `0.5·gap + 0.3·investment-deficit + 0.2·complaint-volume`, volume weight structurally capped below gap weight to enforce governing principle 2, guarded by an automated invariant test on the seeded Region A/B data.
- Seeded demo dataset anchored on **Pune district** (urban ward = Region A, rural village = Region B), realistic synthetic population/facility/investment data per `files/08-data-and-compliance.md` §1.
- Verification bolt-on: resolved-cluster follow-up photo, Gemini-vision plausibility check, mismatch flagged for human review — never auto-closed.
- Open-source scaffolding: MIT license, README, CONTRIBUTING, `.env.example` (`GEMINI_API_KEY`), Docker Compose (ADR-008), `git init`.
- Doc fix carried along: `files/00-glossary.md` says ConfidenceLevel is "set by the Trust stage," but no Trust stage exists in this build — it is set by **Locate** (geocode confidence) and **Verify**; the glossary line and its 7-stage pipeline list need the one-line correction.

Explicit non-goals are unchanged from `files/02-scope.md`: no auth/RBAC, no Redis/Celery, no real government API integration, no anti-spam detection logic, no multi-category/multi-language beyond Hindi + Hinglish, no production deployment.

## Capabilities

### New Capabilities

- `citizen-intake`: chat widget (voice/text), speech-to-text, Understand stage — CitizenRequest → StructuredRequest, submission receipt, immutable raw input.
- `geospatial-clustering`: Locate (Nominatim geocode with confidence) and Cluster (pgvector similarity + PostGIS proximity) stages — StructuredRequest → GeocodedRequest → DemandCluster.
- `fusion-scoring`: Fuse and Score stages — InfrastructureDataset join, InfrastructureGapScore, PriorityIndicators, composite PriorityScore with the dominance-by-construction formula, Recommendation drafting with evidence citations.
- `pipeline-orchestration`: LangGraph graph wiring, Publish Gate interrupt + cross-process resume, RunTrace logging, failure posture (retry-once/halt, flag-never-drop).
- `policymaker-dashboard`: Streamlit dashboard — demand map, cluster cards, priority indicator rows, gap comparison panel, recommendation card with Approve/Reject/Request-changes, pending-gate states, run trace drawer, design-token styling.
- `verification`: post-resolution VerificationRecord flow — citizen follow-up prompt, Gemini-vision plausibility check, match/mismatch/needs-review flagging.

### Modified Capabilities

_None — greenfield; no existing specs._

## Impact

- **New code**: `backend/` (FastAPI + LangGraph + stages), `citizen-web/` (static chat page), `dashboard/` (Streamlit), `db/` (schema/migrations/seed), `docker-compose.yml`, repo scaffolding — all at project root alongside `files/` and `openspec/`.
- **Dependencies**: LangGraph/LangChain, `langchain-google-genai`, Faster-Whisper, psycopg + PostGIS/pgvector images, Streamlit/Plotly/PyDeck, Nominatim (external, 1 req/s — demo-only per ADR-006).
- **External requirements at run time**: a `GEMINI_API_KEY` (free tier), one-time Whisper model download, Docker.
- **Docs**: one-line glossary correction in `files/00-glossary.md` (Trust-stage drift).
- **Risk posture**: unchanged from `files/09-build-plan.md` — cached/replayed Gemini responses for the rehearsed demo path, pre-verified Nominatim location strings, Region A/B invariant test as the equity claim's guard.
