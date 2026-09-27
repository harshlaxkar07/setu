# 09 — Build Plan

**Status:** Living checklist. Update as tasks close.
**Depends on:** All prior docs — this is the execution order, not new decisions.
**Last updated:** 2026-09-24

---

## Build order (do not reorder without a reason)

The MVP demo scenario (`02-scope.md`) only works end to end if the pipeline's data contract is agreed before either half of the team starts writing stage logic. Everything downstream of step 2 can be built in parallel.

1. **Lock the data contract.** Write the Postgres schema for every entity in `04-domain-model.md` — even before any pipeline logic exists. This is the single most important artifact for parallel work: once it's fixed, the two halves of the team stop blocking each other.
2. **Seed the demo dataset.** Population figures, facility locations, historical investment labels for the chosen demo region (`08-data-and-compliance.md` §1) — plus the worked-example Region A/B contrast from `04-domain-model.md`. Do this early; realistic data makes every later demo look better, and finding out the data is wrong on day 3 is expensive.
3. **Split and build in parallel:**
   - **Track A (Intake + Geospatial):** chat widget UI → Faster-Whisper integration → Gemini Understand-stage prompt → Nominatim Locate integration → pgvector Cluster logic.
   - **Track B (Fusion + Dashboard):** InfrastructureGapScore + PriorityIndicator computation against seeded data → Recommendation prompt → Streamlit dashboard shell with tokens applied (`07-design-tokens.md`) → Publish Gate UI.
4. **Wire the LangGraph orchestration** (`05-agent-orchestration.md`) connecting Track A's output to Track B's input — this is the integration point, budget real time for it, it will not just work on the first try.
5. **Build the verification bolt-on** last — it's additive to a working core pipeline, not a blocker for the main demo.
6. **Rehearse the live demo** at least twice before presenting, with the Gemini calls either cached/replayed or confirmed within rate limits for the exact rehearsed path (per ADR-002 in `03-architecture.md`).

## Definition of done, per module

- **Intake:** a real voice recording in Hindi produces a correct StructuredRequest (category, urgency, summary) at least 8/10 times on the demo dataset.
- **Geospatial:** the demo region's informal location mentions ("near the government school," "Ward 14") resolve to plausible coordinates.
- **Fusion/Scoring:** the Region A vs Region B worked example visibly shows Region B outranking Region A despite fewer complaints, with factors shown.
- **Dashboard:** no unexplained numbers anywhere on screen (`06-ui-contract.md` rule 1); Streamlit chrome is fully hidden (`07-design-tokens.md`).
- **Verification:** a deliberately mismatched before/after photo pair gets flagged, not auto-approved.

## Risk register

| Risk | Mitigation |
|---|---|
| Gemini rate limit hit mid-demo | Cache/replay the exact rehearsed demo path's responses as a fallback |
| Faster-Whisper Hindi accuracy too low on the actual demo mic/audio | Test with the real recording setup early, not just clean sample audio |
| Nominatim rate limits or fails to resolve a demo location | Pre-verify every location string used in the demo resolves correctly, well before presenting |
| Streamlit still "looks like Streamlit" despite token work | Budget explicit time for the CSS override pass in `07-design-tokens.md` — this is not incidental polish, it's a stated requirement |
| Two-person team runs out of time for the verification bolt-on | It's explicitly last in the build order and additive — cutting it loses a differentiator but not the core demo |

## Pitch deck cross-references

- Lead with `01-vision.md`'s Core Design Principle (advisory AI, human decision).
- Use `04-domain-model.md`'s worked example as the single most convincing slide — it's concrete, numeric, and proves the equity claim visually.
- Cite the researched failure modes of CPGRAMS (resolution without verification) and PM Gati Shakti (data integration without reasoning) as the gap this platform closes — the verification bolt-on and the Score/Recommend stages are the direct answers to each, respectively.
