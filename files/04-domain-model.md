# 04 — Domain Model: The Object Spine

**Status:** Living document — the canonical data vocabulary. Changes here should be rare once the build starts.
**Depends on:** `01-vision.md` (principles), `00-glossary.md` (term definitions).
**Last updated:** 2026-09-24

---

## Modeling principles

1. **Raw input is immutable.** A CitizenRequest, once ingested, is never edited — only referenced. Corrections happen by creating a new derived object, never by mutating history.
2. **Every derived object cites its source.** A DemandCluster cites its member StructuredRequests. A PriorityIndicator cites the specific InfrastructureDataset rows it used. A Recommendation cites the DemandCluster + score. No object exists without a traceable path back to raw evidence.
3. **Scores are never a single opaque number.** Every PriorityScore decomposes into named PriorityIndicators, each independently visible.
4. **Location is resolved, never assumed.** A StructuredRequest's location is a best-effort geocode with a confidence value — not treated as ground truth without that caveat surfacing in the UI.
5. **Nothing citizen-facing that affects the dashboard bypasses the Publish Gate** (see `05-agent-orchestration.md`).

---

## Entities

### Citizen intake

| Entity | Purpose |
|---|---|
| CitizenRequest | Raw submission: audio file or text, timestamp, channel (voice/WhatsApp/web), submitter reference (pseudonymous). |
| StructuredRequest | Derived from a CitizenRequest by the Understand stage: category, urgency, free-text summary, detected language, raw location mention. |
| GeocodedRequest | A StructuredRequest with resolved coordinates + a geocoding ConfidenceLevel, produced by the Locate stage. |

### Demand & clustering

| Entity | Purpose |
|---|---|
| DemandCluster | Group of GeocodedRequests sharing category + geographic proximity + semantic similarity above threshold. Carries a member count and a representative summary. |
| ClusterMembership | The join: which GeocodedRequest belongs to which DemandCluster, with a similarity score (why it joined). |

### External data

| Entity | Purpose |
|---|---|
| InfrastructureDataset | A registered external data source (population, facility locations, historical investment) with a name, coverage area, and last-updated date. |
| InfrastructureFacility | A single facility record (a hospital, a water point) with location and type — the thing a DemandCluster is compared against for gap analysis. |

### Scoring & recommendation

| Entity | Purpose |
|---|---|
| InfrastructureGapScore | Computed for a DemandCluster's area: population ÷ nearby facility coverage, independent of complaint volume. |
| PriorityIndicator | One named contributing factor (e.g. "population affected: 12,400," "distance to nearest source: 4.2km," "historical investment: low") feeding a PriorityScore. |
| PriorityScore | Composite ranking for a DemandCluster, built transparently from its PriorityIndicators. |
| Recommendation | Generated text + structured intervention type, citing the DemandCluster and the PriorityIndicators that justified it. |

### Trust & verification

| Entity | Purpose |
|---|---|
| ConfidenceLevel | Attached to a StructuredRequest or DemandCluster: high / medium / flagged, with a stated reason if not high. |
| VerificationRecord | A follow-up submission (photo/voice) after a DemandCluster is marked resolved, plus a plausibility-check result (match / mismatch / needs human review). |

### Workflow

| Entity | Purpose |
|---|---|
| RunTrace | Full pipeline execution record for one CitizenRequest: stage inputs/outputs, timing, any errors. |
| Approval | A human's Publish Gate decision on a Recommendation: approved / rejected / needs-revision, with reviewer identity and timestamp. |

---

## The edge vocabulary

```text
CitizenRequest —understood_as→ StructuredRequest —geocoded_as→ GeocodedRequest
GeocodedRequest —member_of→ DemandCluster                    (via ClusterMembership)
DemandCluster —compared_against→ InfrastructureFacility ; —scored_by→ InfrastructureGapScore
InfrastructureGapScore + DemandCluster —feed→ PriorityIndicator —composes→ PriorityScore
PriorityScore —justifies→ Recommendation —requires→ Approval (Publish Gate)
DemandCluster —resolved_with→ VerificationRecord —checked_against→ original StructuredRequest summary
Every stage —traced_in→ RunTrace
```

---

## Worked example: why gap analysis beats raw complaint count

This is the concrete case the whole equity argument rests on — put it directly in the pitch deck.

**Region A (urban):**
- 10 existing water infrastructure points
- Good historical investment
- 500 water-related CitizenRequests → 1 large DemandCluster

**Region B (rural):**
- 0 nearby functioning water points within a reasonable service radius
- Low historical investment
- 20 water-related CitizenRequests → 1 small DemandCluster

**Raw complaint count** ranks Region A far above Region B — the wrong answer.

**InfrastructureGapScore**, computed independently, shows Region B has a severe unmet gap (population ÷ facility coverage is far worse) despite fewer complaints. The PriorityScore, which weighs the gap score alongside — not instead of — complaint volume, correctly surfaces Region B as higher priority, and the dashboard shows *why*: "0 facilities within service radius," "low historical investment," "low digital-reporting volume flagged as a possible under-representation signal," not just a number.

This worked example should be seeded directly into the demo dataset so the dashboard can show this exact contrast live.
