# 02 — Scope: Hackathon Build

**Status:** Living document. The single source for what gets built, in what order, for a 2-3 person team.
**Depends on:** `01-vision.md`. Architecture detail in `03-architecture.md`; data model in `04-domain-model.md`.
**Last updated:** 2026-09-24

---

## Posture

2-3 people. Fixed hackathon window. One demo scenario, built completely, rather than many modules built partially. Everything not in the MVP list below is explicitly deferred — deferred is not the same as abandoned, but it does not get touched before the MVP is demo-solid.

**The rule that makes this achievable:** narrow every dimension except the pipeline's completeness. One language pair (Hindi + Hinglish), one category (water supply), one small geographic area (a few wards/villages worth of synthetic + light real data) — but the full loop: voice in, evidence-cited recommendation out, plus the verification bolt-on.

---

## MVP demo scenario

A citizen sends a voice message in Hindi via a WhatsApp-style chat interface:

> "हमारे गाँव में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।"
> ("There has been no proper drinking water supply in our village for several weeks.")

The platform, end to end:

1. **Receives** the voice message through the citizen-facing chat widget.
2. **Transcribes** it (Faster-Whisper, local).
3. **Understands** it — category: water infrastructure, urgency: high, summary generated (Gemini API).
4. **Locates** it — resolves the informal location mention to coordinates (Nominatim/OSM).
5. **Clusters** it against other nearby water-related requests already in the system (pgvector similarity + geographic distance).
6. **Fuses** it with population and existing water-infrastructure data for that area (seeded InfrastructureDataset).
7. **Scores** it — computes an InfrastructureGapScore and PriorityIndicators (population affected, distance to nearest functioning source, historical investment).
8. **Recommends** — generates one evidence-cited potential intervention.
9. **Gates** — a human reviewer (you, playing "policymaker") approves the Recommendation at the Publish Gate.
10. **Publishes** — the DemandCluster, its score breakdown, and the Recommendation appear on the dashboard: a map, a priority card with visible factors, and the recommendation text.

**Then, the verification bolt-on:** simulate marking that cluster "resolved," have a second citizen account upload a before/after photo pair, and show the plausibility check flag a mismatch for human review instead of auto-closing.

This is the whole pitch. Everything else in this document exists to support building this scenario well, not to expand it.

---

## Module breakdown (2-3 person split)

| Module | Owns | Depends on |
|---|---|---|
| **Intake & Understanding** | Chat widget (voice/text), Faster-Whisper transcription, Gemini-based classification/extraction | Nothing — can start immediately with synthetic transcripts |
| **Geospatial & Clustering** | Nominatim geocoding, PostGIS storage, pgvector similarity clustering | Structured output from Intake |
| **Data Fusion & Scoring** | Seeded InfrastructureDataset, InfrastructureGapScore + PriorityIndicator computation, Recommendation generation | DemandClusters from Geospatial module |
| **Dashboard & Verification** | Streamlit + Plotly + PyDeck policymaker view, Publish Gate UI, VerificationRecord flow | Scored, gated output from Fusion module |

A 2-person team merges Intake+Geospatial into one owner and Fusion+Dashboard into the other, with the LangGraph orchestration (see `05-agent-orchestration.md`) as the shared contract between them.

---

## Explicit non-goals (this build)

- Multi-language support beyond Hindi + Hinglish (English optional if time allows; architecture supports more, build does not need to prove it).
- Multiple infrastructure categories beyond water (the pipeline is category-agnostic by design, but only one category needs real demo data).
- Real government dataset integration (Census/SECC/PM Gati Shakti APIs) — seed realistic-looking synthetic data instead; note in the pitch that real integration is a Phase 2 item.
- Anti-spam/coordinated-manipulation detection as a working feature — describe it as designed-for in the architecture doc, don't build detection logic.
- Authentication, RBAC, multi-tenant anything.
- Production deployment (Kubernetes, sovereign infra) — Docker Compose locally or a single free-tier host is sufficient.
- Redis/Celery — skip for hackathon scale; use direct async calls. Reintroduce only if the demo dataset gets large enough to need a queue (it won't).

## Post-hackathon evolution (for the pitch deck, not the build)

- Faster-Whisper → distributed speech service; Gemini free tier → swappable/self-hosted model per data sovereignty needs.
- Synthetic datasets → real Census/SECC + PM Gati Shakti API integration.
- Anti-spam detection module built out per `05-agent-orchestration.md`'s Trust stage design.
- Multi-category, multi-language expansion — architecture already supports this; it's a data/prompt-template problem, not a redesign.
- Impact measurement loop: re-run the pipeline after a project is marked complete, compare before/after complaint volume and InfrastructureGapScore.

## Exit bar (what "demo-ready" means)

- The full 10-step scenario above runs live, start to finish, without manual data patching mid-demo.
- Every number on the dashboard traces to a visible factor — no unexplained scores.
- The Publish Gate is a real click a human makes, not a skipped step.
- The verification mismatch actually gets flagged, not just described.
