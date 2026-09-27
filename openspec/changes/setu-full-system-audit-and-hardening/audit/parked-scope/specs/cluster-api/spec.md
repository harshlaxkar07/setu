# Delta Spec: cluster-api

## Purpose

Makes demand clusters a first-class, versioned resource: a paginated, filterable, deterministically sorted list plus a detail view carrying everything an independent frontend needs to display and explain a cluster.

## ADDED Requirements

### Requirement: Paginated cluster list

The system SHALL expose `GET /api/v1/clusters` supporting: pagination (page/page_size with a documented safe maximum), filtering (region, category, priority range or tier, cluster status, verification state, creation date range), explicit sorting (`sort_by` over documented fields, `sort_order`), and deterministic total ordering (a unique tiebreaker so identical requests always return identical pages). List items carry id, representative summary, category, region, centroid, member count, score, tier, status, and confidence.

#### Scenario: Deterministic pagination

- **WHEN** the same list request is issued repeatedly against unchanged data
- **THEN** the same items appear on the same pages in the same order, and no item is skipped or duplicated across page boundaries

#### Scenario: Filter validation

- **WHEN** an unsupported sort field, invalid priority range, or unknown status is supplied
- **THEN** the endpoint returns a validation error naming the parameter, not a 500 or silently ignored filter

### Requirement: Cluster detail sufficient for an independent frontend

The system SHALL expose `GET /api/v1/clusters/{cluster_id}` returning full cluster detail: id, representative summary, category, region, centroid, member count, first and latest member submission timestamps, confidence and reason, gap block (population, facility counts, gap value, citations), priority score with normalized factors, weights and per-factor contributions, priority indicators (including under-representation and volume signals), recommendation and its status, workflow/publication state, verification state, and sample citizen voices. A frontend MUST be able to render the full cluster drill-down — including WHY the score is what it is — from this response without recalculating any backend-owned value.

#### Scenario: Detail explains the score

- **WHEN** the detail endpoint is called for a scored cluster
- **THEN** the response contains the score, each factor's normalized value, weight, and contribution, and the indicators behind them — matching the stored scoring data exactly

#### Scenario: Malformed and unknown identifiers

- **WHEN** the detail endpoint is called with a non-UUID string or an unknown UUID
- **THEN** it returns 422 (malformed) or 404 (unknown) with a structured error — never a 500
