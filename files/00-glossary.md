# 00 — Glossary

**Status:** Living reference. If a term is used elsewhere with a different meaning, the other doc is wrong — fix it there, not here.
**Last updated:** 2026-09-24

## Brand

| Term | Meaning |
|---|---|
| **Setu** (सेतु) | The platform. "Bridge" — citizen feedback on one bank, policy action on the other. Working name; trademark/domain check pending before external use. |

## Citizen-facing objects

| Term | Meaning |
|---|---|
| CitizenRequest | One raw submission — voice, text, or WhatsApp message — before any AI processing. Immutable once ingested. |
| StructuredRequest | A CitizenRequest after the Understanding stage: category, location, urgency, summary, language — machine-readable, still traces back to the raw submission. |
| DemandCluster | A group of StructuredRequests judged to describe the same underlying problem (same category + nearby location + semantic similarity). The unit planners actually see — never raw individual complaints. |
| ConfidenceLevel | A per-request or per-cluster trust score (high / medium / flagged) set by the **Locate** stage (geocode confidence) and the **Verify** stage (post-resolution plausibility). No Trust stage exists in the current pipeline — it is a post-hackathon addition. Flagged items are never deleted, only surfaced with lower weight and a reason. |
| VerificationRecord | A citizen-submitted follow-up (photo/voice) after a request is marked resolved, plus the system's plausibility check against the original complaint. |

## Data & scoring

| Term | Meaning |
|---|---|
| InfrastructureDataset | Any external dataset joined against citizen demand — Census/SECC demographics, facility locations (hospitals, schools, water points), historical investment records. |
| InfrastructureGapScore | A location's shortfall between existing infrastructure and population need, computed independently of complaint volume — the mechanism that stops urban areas from dominating purely on complaint count. |
| PriorityIndicator | One named, individually-shown factor feeding a region's overall priority (e.g. "population affected," "distance to nearest facility," "historical investment"). Never collapsed into a single unexplained number without its factors shown alongside. |
| PriorityScore | The composite ranking across a category/region, built from PriorityIndicators. Advisory only — see Core Design Principle in `01-vision.md`. |
| Recommendation | A generated, evidence-cited potential intervention (e.g. "evaluate a Primary Health Centre in Ward 17") tied to a specific DemandCluster + InfrastructureGapScore combination. |

## Pipeline & orchestration

| Term | Meaning |
|---|---|
| Pipeline stage | One node in the LangGraph workflow (Understand, Locate, Cluster, Fuse, Score, Recommend, Publish Gate, Verify) — see `05-agent-orchestration.md`. |
| Tool class | **Autonomous** (runs without human approval) / **Gated** (requires human sign-off before effect) — governs every pipeline stage's write actions. |
| Publish Gate | The one mandatory human checkpoint: a Recommendation cannot appear on the policymaker dashboard until a human reviewer approves it. |
| Run trace | The full record of one CitizenRequest's path through the pipeline — every stage's input/output, for auditability and debugging. |

## Delivery

| Term | Meaning |
|---|---|
| Demo scenario | The single, complete, end-to-end flow the hackathon build must prove — defined in `02-scope.md` §MVP. |
| Non-goal | Something explicitly out of scope for the hackathon build, listed to stop time being spent on it. |
