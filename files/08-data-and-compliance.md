# 08 — Data Sources & Compliance Register

**Status:** Living register. Defines what data the demo uses and what a real deployment would need to satisfy — this document is also strong pitch-deck material, since it shows the team thought about trust and privacy beyond the demo.
**Last updated:** 2026-09-24

---

## 1. Demo datasets (hackathon)

| Dataset | Source for the demo | Real-world equivalent (post-hackathon) |
|---|---|---|
| Population / demographics | Synthetic, but proportioned realistically against actual Census 2011 district-level figures for the chosen demo region | Census / SECC data via data.gov.in |
| Water infrastructure facility locations | Seeded manually — a handful of real or realistic-looking points for the demo region | State PHED (Public Health Engineering Department) data, or OSM `amenity=water_point` tags where available |
| Historical investment | Synthetic, low/medium/high labels per seeded region | State budget allocation data, where published |
| Administrative boundaries | OSM boundary polygons for the demo region | Survey of India / state GIS boundary data |

**Honest framing for the pitch:** real government datasets are frequently not machine-readable, not current, or not published at the granularity this platform needs — this is itself one of the documented failure modes of PM Gati Shakti (data standards vary by ministry/state). The demo uses realistic synthetic data and states this openly rather than pretending otherwise.

## 2. Privacy posture

- CitizenRequest submitter identity is pseudonymous — a stable per-conversation reference, never a name or phone number surfaced to the policymaker dashboard.
- Voice recordings are transcribed and then not retained beyond the demo session (documented posture; not a hard requirement to implement retention deletion logic for the hackathon, but state it as the design intent).
- No individual citizen is ever shown on the policymaker surface — only DemandClusters (aggregates). This is a direct extension of the vision doc's "not a surveillance system" principle.
- VerificationRecord photos are handled the same way — linked to the cluster, not to a named individual, on the policymaker-facing side.

## 3. Anti-spam / manipulation detection (designed, not built)

Documented in the architecture as a future Trust-stage addition, not built for the hackathon (see `02-scope.md` non-goals):

- Duplicate/identical submission detection (same device/session submitting near-identical text repeatedly in a short window).
- Coordinated geographic pattern detection (a sudden spike in one small area with low semantic diversity — possibly organized rather than organic).
- Flagged, never deleted — same principle as everywhere else in the platform: suspicious data gets a lower ConfidenceLevel and a stated reason, surfaced for human review.

## 4. Data protection posture for the pitch

- Purpose limitation: citizen data collected for infrastructure prioritization is not repurposed for anything else.
- Minimal PII collection: the platform needs a location and a problem description, not a name or ID.
- A real deployment would need explicit consent capture at first contact and a stated retention policy — noted here as an open item for production, not solved in the hackathon build.

## 5. Review cadence

For the hackathon: N/A — this is a point-in-time register for the demo. For the pitch deck: state that a real deployment would review this register against DPDP Act 2023 obligations before any pilot with real citizen data.
