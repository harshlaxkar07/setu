# Delta Spec: policymaker-dashboard

## Purpose

Gives policymakers an evidence-forward Streamlit dashboard for the Setu MVP: a demand map, cluster cards with visible priority factors, the Region A vs Region B gap comparison, and the Publish Gate review actions — every number explained, every AI-drafted field disclosed.

## ADDED Requirements

### Requirement: Demand map displays clusters by priority tier

The dashboard SHALL render an interactive map (PyDeck) showing each DemandCluster as a marker at its geocoded coordinates, sized and colored by PriorityScore tier using the semantic priority tokens from `files/07-design-tokens.md`. Selecting a marker SHALL make that cluster the dashboard's selected cluster.

#### Scenario: Seeded clusters appear on the map

- **WHEN** the dashboard loads with the seeded Pune-district demo data
- **THEN** the map displays a marker for the Region A (urban ward) cluster and the Region B (rural village) cluster at their geocoded locations
- **AND** each marker's color and size correspond to that cluster's PriorityScore tier

#### Scenario: Selecting a marker focuses the cluster

- **WHEN** the reviewer selects a cluster's marker on the map
- **THEN** that cluster becomes the selected cluster and its cluster card detail is shown

### Requirement: One selection drives map and card detail together

The dashboard SHALL keep exactly one DemandCluster selected at a time, and that selection SHALL drive both the map focus and the card detail panel — never two independent scroll or selection states. On desktop viewports the map and card list SHALL appear side by side; on narrow viewports the card list alone SHALL be shown.

#### Scenario: Card selection focuses the map

- **WHEN** the reviewer selects a cluster from the card list
- **THEN** the map focuses on that cluster's marker
- **AND** the detail panel shows the same cluster — no other cluster remains highlighted

#### Scenario: Narrow viewport falls back to card list

- **WHEN** the dashboard is viewed on a narrow viewport
- **THEN** the card list is displayed without the side-by-side map layout and remains fully usable

### Requirement: Cluster cards expose composition and expandable factors

The dashboard SHALL display each DemandCluster as a card showing its member count, category, representative summary, and PriorityScore with its tier label, plus an expandable factor list containing every PriorityIndicator feeding that score.

#### Scenario: Cluster card content

- **WHEN** a DemandCluster is displayed as a card
- **THEN** the card shows member count, category, representative summary, and the PriorityScore value with its tier label ("High", "Medium", or "Low")

#### Scenario: Expanding the factor list

- **WHEN** the reviewer expands a cluster card's factor list
- **THEN** every PriorityIndicator behind that cluster's PriorityScore is listed as a labeled row in the same view

### Requirement: Priority indicators render as labeled rows

The dashboard SHALL render each PriorityIndicator as a labeled row pairing the factor's name with its value (for example "population affected: 12,400", "distance to nearest functioning source: 4.2 km", "historical investment: low"). Indicators SHALL never be presented only in a tooltip or hidden behind hover-only interactions.

#### Scenario: Region B factor rows

- **WHEN** the Region B cluster's indicators are displayed
- **THEN** each factor appears as a visible name–value row, including population affected, distance to nearest functioning source, and historical investment
- **AND** no indicator is reachable only via a tooltip

### Requirement: No unexplained numbers

Every score, count, or percentage shown on the dashboard SHALL have its contributing factors reachable in the same view (via expand, adjacent card, or inline breakdown). A PriorityScore SHALL be presented with its decomposition into the three weighted components — infrastructure gap (weight 0.5), investment deficit (weight 0.3), complaint volume (weight 0.2), each min-max normalized within category — never as a bare figure.

#### Scenario: PriorityScore breakdown reachable

- **WHEN** a PriorityScore is displayed for any cluster
- **THEN** the reviewer can reach, in the same view without navigating away, the weighted component breakdown (0.5 × gap, 0.3 × investment deficit, 0.2 × volume) and the underlying PriorityIndicator rows

#### Scenario: Demo-flow sweep finds no bare figures

- **WHEN** each dashboard view of the 10-step demo scenario is inspected
- **THEN** no numeric value (score, count, percentage, distance) appears without its contributing factors reachable in that same view

### Requirement: Gap comparison panel proves the equity contrast

The dashboard SHALL provide a gap comparison panel showing Region A (Pune urban ward) and Region B (Pune rural village) side by side: complaint volume, InfrastructureGapScore, historical investment, and resulting PriorityScore rank for each. The panel SHALL make visible that Region B outranks Region A despite lower complaint volume, with the explaining factors shown.

#### Scenario: Region B visibly outranks Region A

- **WHEN** the gap comparison panel is displayed with the seeded demo data
- **THEN** Region A shows the higher complaint volume and Region B shows the worse InfrastructureGapScore
- **AND** Region B is shown ranked above Region A on PriorityScore
- **AND** the explaining factors are visible, including "0 facilities within service radius" and "low historical investment" for Region B

#### Scenario: Low reporting volume flagged as under-representation signal

- **WHEN** Region B's side of the panel is displayed
- **THEN** its low digital-reporting volume is presented as a possible under-representation signal, not as evidence of low need

### Requirement: Recommendation card cites its evidence

The dashboard SHALL display each Recommendation as a card containing the drafted intervention text and its evidence citations: the DemandCluster it addresses and the specific PriorityIndicators that justified it. A Recommendation SHALL never be shown without its citations reachable in the same view.

#### Scenario: Evidence citations visible

- **WHEN** a Recommendation card is displayed
- **THEN** it shows the intervention text, the cited DemandCluster, and the cited PriorityIndicators
- **AND** the reviewer can trace from the card to the cluster's factor rows without leaving the view

### Requirement: Gate decision actions resume the pipeline

The Recommendation card SHALL offer exactly three reviewer actions on a pending Recommendation — Approve, Reject, and Request changes — and each action SHALL submit the decision to the backend's gate resume endpoint identified by the run's thread id. The decision SHALL be recorded as an Approval (approved / rejected / needs-revision) with reviewer identity and timestamp. The dashboard SHALL NOT publish, dismiss, or alter a Recommendation's state locally without the backend confirming the resumed decision.

#### Scenario: Approve publishes the recommendation

- **WHEN** the reviewer clicks Approve on a pending Recommendation
- **THEN** the decision is sent to the gate resume endpoint with that run's thread id
- **AND** after the backend confirms, the Recommendation appears on the dashboard as published, with the recorded Approval's reviewer and timestamp available

#### Scenario: Reject keeps the recommendation off the published view

- **WHEN** the reviewer clicks Reject on a pending Recommendation
- **THEN** the rejection is sent to the gate resume endpoint and the Recommendation is marked rejected
- **AND** it never appears in the published dashboard view

#### Scenario: Request changes marks needs-revision

- **WHEN** the reviewer clicks Request changes on a pending Recommendation
- **THEN** the decision is recorded as needs-revision via the resume endpoint
- **AND** the Recommendation remains unpublished and visibly awaiting revision, not blended with approved items

#### Scenario: Resume endpoint failure does not fake an outcome

- **WHEN** the resume endpoint is unreachable or returns an error after a decision click
- **THEN** the dashboard shows an error state and the Recommendation remains in its pending state
- **AND** no published or rejected state is displayed optimistically

### Requirement: Pending recommendations are visibly gated

Anything awaiting Publish Gate approval SHALL be displayed in a distinct pending state: an amber badge labeled "Awaiting review" using the `pending-gate` token. Pending items SHALL never be blended in with approved items, and the published view SHALL derive solely from recorded approvals — a pending Recommendation must look distinctly unapproved, not merely absent.

#### Scenario: Pending badge on an ungated recommendation

- **WHEN** a Recommendation is awaiting Publish Gate approval
- **THEN** it is shown with the amber "Awaiting review" badge, visually distinct from every approved item

#### Scenario: Refresh before approval does not publish

- **WHEN** the reviewer refreshes or reopens the dashboard before approving a pending Recommendation
- **THEN** that Recommendation still appears only in its pending state and is absent from the published view

### Requirement: Verification review surface

The dashboard SHALL provide the verification surface for resolved clusters: the simulated "mark resolved" action on a published cluster, visible resolution-state badges ("resolved — unverified" and "resolved — verified", each paired with a text label per the color-only rule), a flagged-mismatch review view, and reviewer decision actions. The flagged view SHALL display the flagged VerificationRecord's original complaint summary side by side with the follow-up submission media. Reviewer decisions (confirm resolved / reject resolution) SHALL be submitted to a dedicated FastAPI verification-review endpoint — mirroring the gate resume pattern of submitting decisions to the backend rather than mutating state in the UI — and SHALL be recorded with reviewer identity and timestamp; the dashboard SHALL NOT clear a flag or change a cluster's verification state locally without backend confirmation. This surface satisfies the verification spec's "Mismatch is flagged for human review and never auto-closed" requirement, which persists the flag until a human records a review decision here.

#### Scenario: Mark resolved shows the unverified badge

- **WHEN** the operator triggers the simulated "mark resolved" button on a published DemandCluster
- **THEN** the backend records the cluster as "resolved — unverified"
- **AND** the dashboard shows the cluster with a "resolved — unverified" badge, visually distinct from "resolved — verified"

#### Scenario: Flagged mismatch displayed with side-by-side evidence

- **WHEN** a VerificationRecord flagged as mismatch (or needs human review) exists for a resolved cluster
- **THEN** the dashboard surfaces the flagged record in a review view showing the original complaint's summary alongside the follow-up submission media (photos and/or voice note) for direct comparison
- **AND** the flag is visibly presented as requiring a human decision, not as a described-only condition

#### Scenario: Reviewer decision is recorded via the backend

- **WHEN** the reviewer records a decision on a flagged VerificationRecord (confirm resolved or reject resolution)
- **THEN** the decision is submitted to the verification-review endpoint and, after backend confirmation, the flag is cleared and the review decision is stored with reviewer identity and timestamp
- **AND** the cluster's state updates accordingly ("resolved — verified" on confirm; it remains "resolved — unverified" on reject), and the recorded decision remains retrievable

#### Scenario: Endpoint failure leaves the flag active

- **WHEN** the verification-review endpoint is unreachable or returns an error after a decision click
- **THEN** the dashboard shows an error state, the flag remains active, and no verified state is displayed optimistically

### Requirement: Run trace drawer exposes the pipeline path

The dashboard SHALL provide an expandable run trace drawer for the selected cluster showing the full pipeline execution: each stage in order (Understand, Locate, Cluster, Fuse, Score, Recommend, Publish Gate), what it received, what it produced, and how long it took.

#### Scenario: Tracing a high priority score

- **WHEN** the reviewer opens the run trace drawer for a selected cluster
- **THEN** the drawer lists every executed stage in pipeline order with its input, output, and duration
- **AND** the reviewer can follow the path from the raw request through scoring to the gated Recommendation

#### Scenario: Stage errors are shown, not omitted

- **WHEN** a stage in the trace recorded an error or retry
- **THEN** the drawer displays that error or retry alongside the stage rather than omitting the stage

### Requirement: AI-generated content carries provenance markers

Every AI-generated field displayed on the dashboard — including representative summaries and Recommendation text — SHALL carry a small, consistent "AI-drafted" marker styled with the `ai-provenance` token, visually distinct from human-entered and raw citizen content. The marker SHALL never be applied decoratively to non-AI content.

#### Scenario: Summary and recommendation are marked

- **WHEN** a cluster's representative summary and a Recommendation's text are displayed
- **THEN** both carry the "AI-drafted" provenance marker

#### Scenario: Raw citizen content is not marked

- **WHEN** raw citizen complaint text or a transcript excerpt is displayed alongside AI-drafted content
- **THEN** the raw content carries no "AI-drafted" marker and the two are visually distinguishable

### Requirement: Trust and priority signals are never color-only

Priority tiers, ConfidenceLevels, and gate states SHALL always pair color with a text label or icon. A non-high ConfidenceLevel SHALL be shown with its stated reason.

#### Scenario: Tier shown with label

- **WHEN** any priority tier is displayed (map legend, card, badge)
- **THEN** the tier color is paired with its text label ("High", "Medium", or "Low")

#### Scenario: Low-confidence cluster shows its reason

- **WHEN** a displayed cluster or request carries a ConfidenceLevel below high (for example, low geocode confidence)
- **THEN** the dashboard shows the level with its stated reason as text, not color alone

### Requirement: Dashboard chrome is hidden and styled by the design tokens

The dashboard SHALL show no Streamlit default chrome — no default header, footer, hamburger menu, or "Made with Streamlit" badge — and SHALL be styled per `files/07-design-tokens.md`: `paper` background, `card` surfaces, `bridge-blue` for primary actions, semantic priority tokens for tiers, Inter for headings and body, IBM Plex Mono (tabular) for every numeric value (scores, counts, coordinates), the 8/16/24/32 px spacing scale, and a single consistent header bar. Dashboard chrome SHALL be in English; any Hindi content (transcripts, citizen text) SHALL render in Noto Sans Devanagari. All text SHALL meet WCAG AA contrast.

#### Scenario: No Streamlit chrome visible

- **WHEN** any dashboard view of the demo scenario is displayed
- **THEN** no Streamlit default header, footer, menu, or "Made with Streamlit" badge is visible anywhere on screen

#### Scenario: Numerics render in tabular monospace

- **WHEN** a PriorityScore, InfrastructureGapScore, member count, or coordinate is displayed
- **THEN** it renders in IBM Plex Mono with tabular figures

#### Scenario: Hindi content renders in Devanagari face

- **WHEN** Hindi text (a transcript or citizen summary) appears on the dashboard
- **THEN** it renders in Noto Sans Devanagari, not a Latin-only fallback substitution
