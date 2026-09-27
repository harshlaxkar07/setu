# 05 — Pipeline Orchestration

**Status:** Platform law for the build. Every pipeline stage below is a LangGraph node; this document is the contract between the Intake/Geospatial owner and the Fusion/Dashboard owner.
**Depends on:** `01-vision.md` (principle 4: AI recommends, humans decide), `04-domain-model.md` (entity contracts).
**Last updated:** 2026-09-24

---

## Stages

| # | Stage | Input | Output | Tool class |
|---|---|---|---|---|
| 1 | **Understand** | CitizenRequest (audio/text) | StructuredRequest | Autonomous |
| 2 | **Locate** | StructuredRequest | GeocodedRequest | Autonomous |
| 3 | **Cluster** | GeocodedRequest | ClusterMembership (existing or new DemandCluster) | Autonomous |
| 4 | **Fuse** | DemandCluster | DemandCluster + linked InfrastructureFacility rows | Autonomous |
| 5 | **Score** | Fused DemandCluster | InfrastructureGapScore + PriorityIndicators + PriorityScore | Autonomous |
| 6 | **Recommend** | Scored DemandCluster | Draft Recommendation | Autonomous |
| 7 | **Publish Gate** | Draft Recommendation | Approval (human decision) | **Gated** — the only gate in this pipeline |
| 8 | **Verify** (post-resolution) | VerificationRecord submission | Match/mismatch flag | Autonomous, flags route to human review on mismatch |

**Why only one gate:** per the vision doc's Publish Gate principle, the single quality-critical decision is "should this recommendation reach a policymaker's dashboard." Everything upstream (transcription, classification, clustering, scoring) is mechanical enough to run autonomously — gating every stage would make the demo unusable and adds no real trust, since none of those steps commits anything policymaker-facing on their own.

---

## Tool classes

- **Autonomous:** stages 1-6 and 8 run without human approval. They read, transform, and write intermediate objects (StructuredRequest, DemandCluster, scores) — nothing citizen- or policymaker-facing is exposed yet.
- **Gated:** stage 7, the Publish Gate. A Recommendation cannot become visible on the dashboard without a recorded Approval. This is enforced in the backend (the graph literally halts and waits), not just hidden in the UI — a reviewer refreshing the dashboard before approving must not see the pending recommendation.

## Failure posture

- On a Gemini API failure or rate limit: retry once, then halt that RunTrace and surface it as "needs retry" in a small ops view — never silently drop the CitizenRequest.
- On a geocoding failure (no location resolved): the GeocodedRequest carries a low ConfidenceLevel and proceeds — it still joins the general demand picture, just flagged, rather than being discarded. This matters for the equity principle: a request with no resolvable location is exactly the kind that must not simply vanish.
- On a clustering ambiguity (request could plausibly join two clusters): default to the higher-similarity cluster, log the alternative in the RunTrace for later review — never block the pipeline on this.

## Verification stage detail (the trust bolt-on)

1. A DemandCluster is marked "resolved" (simulated for the demo — a button, not a real government integration).
2. A citizen account uploads a follow-up photo/voice note referencing the same cluster.
3. Gemini (vision-capable) compares the follow-up against the original complaint's description for plausibility — e.g. does a photo of a dry, cracked pipe plausibly match "no drinking water supply"?
4. Match → ConfidenceLevel stays high, VerificationRecord logged as confirmed.
5. Mismatch or low-confidence → flagged for human review, never auto-closed. This is the direct fix for the most-cited real-world failure (officials closing cases without action) — see the researched failure modes referenced in the pitch deck.

## Run trace

Every CitizenRequest's full path through stages 1-8 is logged as a RunTrace: what each stage received, what it produced, and how long it took. For the demo, this doubles as the "explainability" proof — if a judge asks "why did this get a high priority score," the RunTrace is the literal answer, not a post-hoc justification.
