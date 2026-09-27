# Delta Spec: map-api

## Purpose

Provides GeoJSON-compatible geographic contracts for requests, demand clusters, and infrastructure facilities so any map frontend — the current dashboard or a future one — can render Setu's geography directly from the API.

## ADDED Requirements

### Requirement: GeoJSON map endpoints

The system SHALL expose `GET /api/v1/map/requests`, `GET /api/v1/map/clusters`, and `GET /api/v1/map/infrastructure`, each returning an RFC 7946 GeoJSON FeatureCollection (coordinates as [longitude, latitude]) with feature properties sufficient for rendering and drill-down: requests carry category, status, and region; clusters carry cluster id, category, member count, priority score and tier, gap severity indicators, and publication/resolution status; infrastructure features carry facility type and functioning state. Region boundaries SHALL be available as polygon features (on the clusters or a boundaries response) so a frontend can draw them.

#### Scenario: Cluster features are render-ready

- **WHEN** the cluster map endpoint is called on the seeded dataset
- **THEN** it returns valid GeoJSON with one point feature per cluster whose properties include id, category, member count, score, tier, and status — enough to style markers without further API calls

#### Scenario: Valid GeoJSON

- **WHEN** any map response is validated against the GeoJSON schema
- **THEN** it passes, and all coordinates are in [lon, lat] order within valid bounds

### Requirement: Map endpoints share the platform filter contract

Map endpoints SHALL accept the same filter parameters as the analytics endpoints (date range, region, category, status, priority tier where applicable) rather than having one endpoint per UI screen; unsupported values are rejected with validation errors.

#### Scenario: Filtered map

- **WHEN** the requests map is filtered to one region and category
- **THEN** only matching features are returned and the feature count equals the equivalent analytics count under the same filters

### Requirement: Unresolved locations handled honestly

Requests without a resolved geometry SHALL be excluded from map features but reported in the response metadata (count of unmapped items), so maps never plot fabricated coordinates and totals remain reconcilable with analytics counts.

#### Scenario: Ungeocoded requests

- **WHEN** some requests have no resolved location
- **THEN** they appear in the unmapped count, not as features at a default or fabricated position
