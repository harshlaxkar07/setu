# Delta Spec: policymaker-dashboard

## Purpose

The policymaker dashboard is Setu's decision-support surface: it presents citizen demand, geography, infrastructure gaps, explainable priorities, workflow state, resolution, and verification to government users — as a reference client of the platform APIs.

Note: although the proposal lists this capability under Modified Capabilities, the requirements below are expressed as ADDED relative to the empty main spec (build-setu-mvp is unarchived); they extend — not replace — build-setu-mvp's delta requirements for this capability.

## ADDED Requirements

### Requirement: Dashboard is a pure API client

The dashboard SHALL obtain every displayed value from the versioned backend APIs (`Streamlit → FastAPI → services → PostgreSQL`) and SHALL NOT: query the database directly, recalculate backend-owned values (priority score, factor contributions, tiers, ranks, gap values, region assignment), or hard-code business constants (weights, thresholds, service radii) that the backend already owns. Backend-owned values currently derived in the frontend — per-factor `weight × norm` contributions, region A/B selection, #1/#2 ranking, zero-facility and low-investment callouts, tier styling inputs — SHALL come from API fields. Purely presentational concerns (colors, layout, number formatting, label translation) MAY remain in the frontend.

#### Scenario: Business values come from the API

- **WHEN** the dashboard renders a score breakdown, region comparison, ranking, or gap callout
- **THEN** every number and classification shown is present verbatim in an API response consumed by that view

#### Scenario: Backend disappears

- **WHEN** the dashboard process is removed from the stack
- **THEN** every value it displayed remains obtainable from documented API endpoints (proven by the correctness tests targeting APIs, not Streamlit)

### Requirement: Professional information architecture

The dashboard SHALL be organized into clear sections — Executive Overview (KPI cards, key trends, priority summary), Citizen Demand (trends, categories, channels), Geographic Demand (map with filters and density/size cues), Infrastructure Gaps (facilities, underserved regions, demand-vs-need), Priority & Recommendations (ranking with explainable factors), Workflow (pipeline stages, pending gate actions, failures), Resolution (status and trends), and Verification (verified/pending/flagged) — with drill-down `Overview → Region → Cluster → Evidence` rather than one giant screen of graphs.

#### Scenario: Drill-down path

- **WHEN** a policymaker starts at the overview and selects a region, then a cluster
- **THEN** each step narrows to consistent, API-backed detail, ending at cluster evidence (citizen voices, indicators, score factors, verification evidence)

### Requirement: Every visualization answers a policymaker question

Each chart SHALL exist only if it answers a stated policymaker question, with a traceable chain `Question → Metric → Source → API → Visualization → Test`. Tables are first-class: clusters, high-priority areas, pending gate actions, flagged verifications, and pipeline failures SHALL be presented as filterable, sortable, paginated tables with drill-down. No visualization may present fabricated, padded, or frontend-invented data; displayed statistics derive from real application/database state or explicitly identified synthetic demo data.

#### Scenario: Chart traceability audit

- **WHEN** the shipped chart set is reviewed
- **THEN** each chart maps to a documented question, metric definition, API endpoint, and correctness test, and charts without decision value are absent

### Requirement: Professional empty, loading, and error states

The dashboard SHALL handle: no data (zero requests, zero clusters, no flagged reviews) with informative empty states; loading with visible progress; backend unavailable or malformed responses with a human-readable service message and safe recovery. Python exceptions and raw stack traces MUST never render to users.

#### Scenario: Backend down

- **WHEN** the backend is unreachable while the dashboard loads or refreshes
- **THEN** the dashboard shows a clear unavailable message (not an exception) and recovers on retry once the backend returns

#### Scenario: Zero-data sections

- **WHEN** a section's API returns valid empty data
- **THEN** the section renders an explanatory empty state instead of crashing, hiding silently, or showing placeholder numbers

### Requirement: Dashboard numbers are correct

Every important KPI and chart value displayed SHALL be verified by automated tests comparing the backing API result against independently computed database state (controlled fixtures with hand-derivable expectations), including with filters applied. A visually correct dashboard with incorrect numbers is a failed dashboard.

#### Scenario: KPI equals its definition

- **WHEN** the correctness suite runs against fixture data
- **THEN** each dashboard KPI's backing API value equals the independently computed expected value, and each tested filter changes the result exactly as the definition prescribes
