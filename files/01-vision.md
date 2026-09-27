# 01 — Vision: Setu

**Status:** Living document. Written once before the build, referenced constantly during it.
**Owner:** Team.
**Last updated:** 2026-09-24

---

## The problem in one paragraph

Citizens across India report infrastructure problems constantly — but through fragmented channels (CPGRAMS, state helplines, WhatsApp, surveys), in every language, with no way to tell if 1,000 people just reported the same pothole or 1,000 different problems. Existing systems either collect complaints and let officials mark them "resolved" with no verification (CPGRAMS), or integrate infrastructure data across ministries without reasoning over it (PM Gati Shakti). Nobody closes the loop from citizen voice to an explainable, evidence-backed recommendation — and nobody checks whether "resolved" actually happened.

## The thesis

**1. Consolidation beats collection.** A thousand raw complaints are noise. One DemandCluster with a cited InfrastructureGapScore is signal. Setu's core value is turning volume into an explainable ranked list — not just ingesting more channels.

**2. Objective data must sit beside citizen demand, never behind it.** Complaint volume alone systematically favours urban, digitally-connected populations. Every PriorityScore is computed against population, existing infrastructure, and historical investment — not complaint count alone. This is the single design decision that makes the platform *equitable* rather than just *aggregative*.

**3. Trust is earned by showing the "why," and by checking the "after."** Two separate trust problems exist in every incumbent system: (a) policymakers don't know why a region ranked high, and (b) citizens don't know if a "resolved" complaint was actually fixed. Setu answers both — PriorityIndicators are always shown individually, and VerificationRecords close the loop after action is claimed.

**4. AI recommends; humans decide.** No pipeline stage auto-commits a funding decision. The Publish Gate is non-negotiable. This is both an ethical stance and a trust-building one — see the Core Design Principle below.

---

## Governing principles

1. **No PriorityScore without its factors shown.** A single unexplained number is not acceptable output at any stage.
2. **Complaint volume never overrides InfrastructureGapScore.** A high-complaint, well-served urban area does not outrank a low-complaint, underserved rural one — see the worked example in `04-domain-model.md`.
3. **Flag, never silently drop.** Suspicious or duplicate-seeming requests get a lower ConfidenceLevel and a stated reason. Nothing is deleted without a human decision.
4. **The Publish Gate is the only mutation door for anything policymaker-facing.** No Recommendation reaches the dashboard without a human reviewer's sign-off, full stop.
5. **Citizen-facing intake must work without literacy or a smartphone app.** Voice-first, WhatsApp-first. A web form is a fallback channel, not the primary one.
6. **Verification closes the loop.** "Resolved" is a claim, not a fact, until a citizen follow-up or automated plausibility check confirms it.
7. **Every recommendation cites its evidence.** A reviewer (or an auditor, later) must be able to trace any Recommendation back to the specific DemandCluster and InfrastructureDataset rows that produced it.

## Core Design Principle

Setu is **not** positioned as:
> "AI decides which government project gets funded."

Setu **is** positioned as:
> "AI turns fragmented, multilingual citizen feedback into transparent, evidence-cited development intelligence — so policymakers can see where need is greatest, and why."

Every architectural and UI decision downstream of this document defers to that distinction. It is the line that keeps the platform advisory, auditable, and trustworthy rather than an opaque scoring black box.

## What Setu is not

- Not a chatbot bolted onto a complaint form.
- Not a system that auto-approves or auto-funds anything.
- Not a general-purpose grievance tracker — it exists specifically to turn demand into *prioritization intelligence*, not to replace CPGRAMS-style case management.
- Not a surveillance system — no individual citizen profiling; DemandClusters are geographic/categorical aggregates, not people-tracking.
- Not tied to one state's administrative hierarchy or one language — see `02-scope.md` for the Digital Public Good framing.

## Naming

**Setu** (सेतु — bridge). Working name for the hackathon build; not diligence-checked for trademark/domain conflicts.
