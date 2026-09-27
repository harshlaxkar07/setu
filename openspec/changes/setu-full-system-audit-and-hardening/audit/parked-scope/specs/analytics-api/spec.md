# Delta Spec: analytics-api

## Purpose

Provides the versioned, read-only analytics contracts that make Setu an API-first platform: every KPI, trend, breakdown, comparison, and operational statistic a decision-support frontend needs, with defined calculations and no unexplained numbers.

## ADDED Requirements

### Requirement: Executive overview KPIs

The system SHALL expose `GET /api/v1/analytics/overview` returning the executive KPI set as typed fields. At minimum: total requests, new requests (within a stated window), requests currently processing, successfully structured requests, successfully geocoded requests, requests needing retry/manual intervention, total demand clusters, clusters by status (active, published, resolved-unverified, resolved-verified), flagged verification cases, high-priority clusters (by the server's published tier thresholds), and zero-facility infrastructure-gap clusters. Derived rates (average complaints per cluster, geocoding success rate, AI processing success rate, verification success rate, resolution rate) SHALL be included only with explicitly defined numerator and denominator, and time metrics (average processing time, time to publication, time to resolution) SHALL be included only where reliable timestamps exist for them. Every KPI field MUST have a documented definition, data source, and calculation; no field may exist that cannot be explained.

#### Scenario: KPIs match database state

- **WHEN** the overview endpoint is called against a known database state
- **THEN** every KPI equals the value of its documented definition computed independently against the same state

#### Scenario: Empty system

- **WHEN** the overview endpoint is called against an empty database
- **THEN** it returns 200 with zero counts and null (not fabricated or divide-by-zero) rates

### Requirement: Complaint trend time series

The system SHALL expose `GET /api/v1/analytics/complaints/trend` returning chart-ready time series of request counts bucketed by `granularity` (day, week, month), filterable by date range, region, category, status, and channel. Buckets within the requested range with no data SHALL be returned as explicit zeros so a line chart renders without client-side gap-filling.

#### Scenario: Daily trend with filters

- **WHEN** a daily trend is requested for a date range and one category
- **THEN** the response contains one point per day in the range, each equal to the count of matching requests submitted that day

#### Scenario: Invalid granularity or range

- **WHEN** an unsupported granularity or a from-date later than the to-date is supplied
- **THEN** the endpoint returns a validation error identifying the offending parameter, not a 500 or empty data

### Requirement: Complaint breakdowns

The system SHALL expose complaint/request breakdowns — by category, status, submission channel (text vs voice), detected language (where available), region, processed-vs-failed/retry, and clustered-vs-unclustered — as structured counts with percentage shares, under the same filter contract as the trend endpoint.

#### Scenario: Channel breakdown

- **WHEN** the breakdown endpoint is called grouped by channel
- **THEN** counts per channel sum to the filtered total and each share is the count divided by that total

### Requirement: Category analytics

The system SHALL expose per-category analytics: request counts, percentage distribution, trend over time, active cluster counts, and priority distribution per category, sufficient for ranked bar and trend charts without frontend aggregation.

#### Scenario: Category distribution sums

- **WHEN** category analytics are requested
- **THEN** per-category counts sum to the total request count under the same filters

### Requirement: Region comparison

The system SHALL expose per-region comparison metrics using the backend's canonical spatial region assignment: population and investment label (from stored region profiles), request count, cluster count, facility counts (total and functioning), infrastructure-gap values, priority summaries, resolution counts, and verification outcomes. Per-population rates SHALL be exposed only for regions with a stored population denominator and MUST be labeled with their basis. The seeded Kothrud/Velhe equity contrast MUST be directly demonstrable from this endpoint (low-population, zero-facility Velhe outranking high-volume Kothrud).

#### Scenario: Equity contrast visible

- **WHEN** the region comparison is requested on the seeded dataset
- **THEN** Velhe shows fewer requests but zero facilities, a larger gap, a low investment label, and a higher priority score than Kothrud

### Requirement: Priority analytics with explainable factors

The system SHALL expose priority analytics: a ranked listing of clusters by priority score, the factor breakdown for each (gap, investment-deficit, and volume normalized components with their weights, plus under-representation indicators where present), tier distribution, and per-region priority comparison. The backend is the sole source of score and tier computation; responses MUST carry enough factor detail that a frontend can explain WHY a cluster is high priority without recalculating anything.

#### Scenario: Score is explainable from the response alone

- **WHEN** the priority ranking is requested
- **THEN** each entry carries the score, each normalized factor, its weight, and its weighted contribution, and the weighted contributions reproduce the stored score

### Requirement: Infrastructure-gap analytics

The system SHALL expose infrastructure-gap analytics distinguishing demand volume from infrastructure need: per cluster and per region — facility counts (total and functioning), gap values with population basis, investment labels, and demand (request/member counts) side by side, so high-complaint-volume areas and high-infrastructure-need areas are separable.

#### Scenario: Volume versus need separable

- **WHEN** gap analytics are requested on the seeded dataset
- **THEN** the response shows Kothrud as high-demand/low-gap and Velhe as low-demand/high-gap without any frontend computation

### Requirement: Pipeline analytics

The system SHALL expose pipeline/workflow analytics: counts of requests at each meaningful stage of the processing funnel (received, understood, located, embedded, clustered, gap-analysed, scored, recommended, awaiting publish gate, published, resolved, verified — as derivable from stored traces and statuses), counts of failed and needs-retry runs, pending gate actions, and processing latency statistics where per-stage durations are recorded. Each request MUST be counted once per funnel position regardless of how many trace rows it has.

#### Scenario: Funnel counts are deduplicated

- **WHEN** a request has multiple trace rows (e.g., an added verification trace)
- **THEN** pipeline funnel counts still count that request exactly once at its furthest stage

#### Scenario: Bottleneck visibility

- **WHEN** runs are failing or awaiting the gate
- **THEN** failed, needs-retry, and pending-gate counts identify the stuck stage without reading raw traces

### Requirement: Resolution and verification analytics

The system SHALL expose resolution analytics (clusters open, published, resolved-unverified, resolved-verified; resolution trends where transition timestamps exist) and verification analytics (verification records by result — pending, match, mismatch, needs-human-review — flagged counts, human decisions confirmed/rejected, and trends where timestamps permit). No SLA or duration claim may be derived from timestamps that do not actually record the transition in question.

#### Scenario: Verification outcome distribution

- **WHEN** verification analytics are requested
- **THEN** counts by result and by human decision match the verification records in the database under the same filters

### Requirement: System health counters are sanitized and separated

The system SHALL expose operational health analytics (successful/failed AI stages, needs-retry counts, geocoding failures, transcription failures, verification-check failures, recent pipeline error classes) separately from policymaker analytics, and these responses MUST NOT contain secrets, API keys, prompt contents, stack traces, or internal credentials — error information is limited to stage, class, and timestamp.

#### Scenario: Sanitized error reporting

- **WHEN** recent pipeline errors are requested after real failures
- **THEN** each entry names the stage, error class, and time — never a stack trace, prompt body, or secret

### Requirement: Every analytics metric is defined and tested

Every metric exposed by this capability SHALL have: an exact written definition (source tables, calculation, filters honored), a documented API field, and an automated correctness test that computes the expected value independently from controlled fixture data rather than snapshotting API output.

#### Scenario: Metric audit

- **WHEN** the KPI definition table is compared against the API surface
- **THEN** every exposed field appears in the table with definition, calculation, test reference, and UI label, and no undocumented field exists
