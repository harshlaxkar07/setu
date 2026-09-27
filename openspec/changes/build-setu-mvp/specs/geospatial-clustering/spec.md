## Purpose

Resolves each structured citizen request's informal location mention into coordinates with an explicit geocoding confidence (Locate stage), then groups geocoded requests into DemandClusters by shared category, semantic similarity, and geographic proximity (Cluster stage) — turning individual complaints into the aggregate demand units the rest of the pipeline scores and the dashboard displays.

## ADDED Requirements

### Requirement: Locate resolves informal location mentions to coordinates

The Locate stage SHALL produce a GeocodedRequest from every StructuredRequest by resolving its raw location mention — an informal Hindi/Hinglish phrase such as a village name, a ward reference, or a landmark description like "near the government school" — into geographic coordinates using the Nominatim/OpenStreetMap geocoding service (ADR-006). The GeocodedRequest SHALL reference its source StructuredRequest and SHALL preserve the original location mention text unmodified alongside the resolved coordinates; the raw mention is never overwritten by the resolution.

#### Scenario: Demo-scenario village name resolves to plausible coordinates

- **WHEN** a StructuredRequest whose raw location mention names the seeded Region B village (a real rural village in Pune district) enters the Locate stage
- **THEN** the stage produces a GeocodedRequest whose coordinates fall within Pune district, plausibly at that village
- **AND** the GeocodedRequest references the source StructuredRequest and carries the original mention text unchanged

#### Scenario: Informal landmark phrase resolves rather than defaulting

- **WHEN** a StructuredRequest carries an informal mention such as "near the government school" combined with the seeded Region A ward name
- **THEN** the Locate stage resolves it to coordinates within that ward's area, not to a bare district centroid and not to a geocoding failure

### Requirement: Every GeocodedRequest carries a geocoding ConfidenceLevel

The Locate stage SHALL attach a ConfidenceLevel of high, medium, or flagged to every GeocodedRequest it produces, with a stated reason recorded whenever the level is not high. In this build the ConfidenceLevel at this point in the pipeline is set by the Locate stage itself (geocode confidence) — no Trust stage exists in the hackathon pipeline. An exact, unambiguous resolution SHALL be high; a partial or ambiguous resolution (multiple candidate places, or resolution only to a coarser administrative level than the mention implies) SHALL be medium with the ambiguity stated as the reason. The ConfidenceLevel and its reason SHALL be stored on the GeocodedRequest so downstream stages and the dashboard can surface them — a resolved location is a best-effort geocode, never treated as ground truth without this caveat available.

#### Scenario: Unambiguous geocode is marked high

- **WHEN** the Locate stage resolves a location mention to exactly one matching place at the expected level of detail
- **THEN** the resulting GeocodedRequest carries ConfidenceLevel high

#### Scenario: Ambiguous geocode is marked medium with a reason

- **WHEN** the geocoding service returns multiple plausible candidate places for a location mention
- **THEN** the Locate stage selects a best-effort candidate, sets ConfidenceLevel medium, and records a stated reason describing the ambiguity
- **AND** the reason is retrievable with the GeocodedRequest by downstream consumers

### Requirement: Geocoding failure proceeds flagged, never dropped

When the Locate stage cannot resolve a location mention to coordinates (no result, or the geocoding service is unavailable), the pipeline SHALL NOT discard the request. The stage SHALL still produce a GeocodedRequest — without resolved coordinates — carrying ConfidenceLevel flagged and a stated reason, and that request SHALL proceed to the Cluster stage and remain part of the stored, queryable demand picture for human review. A request with no resolvable location is exactly the kind that must not silently vanish (equity principle: flag, never drop).

#### Scenario: Unresolvable location mention continues flagged

- **WHEN** a StructuredRequest's location mention returns no geocoding result
- **THEN** a GeocodedRequest is still created with ConfidenceLevel flagged and a stated reason (e.g. "location could not be resolved")
- **AND** the request proceeds to the next pipeline stage instead of being dropped
- **AND** the flagged request remains stored and retrievable, with its flag and reason visible to downstream consumers

### Requirement: Geocoding respects the Nominatim rate limit

The system SHALL issue no more than one geocoding request per second to Nominatim, its published usage limit — an accepted demo-only constraint (ADR-006). When multiple requests need geocoding concurrently, calls SHALL be throttled or serialized; no request SHALL be rejected or dropped because of rate limiting.

#### Scenario: Burst of submissions stays within the limit

- **WHEN** several StructuredRequests reach the Locate stage at nearly the same time
- **THEN** the outbound geocoding calls are spaced at no more than one per second
- **AND** every request is eventually geocoded (or flagged per the failure posture) — none is rejected or lost due to throttling

### Requirement: Demo location strings are real, pre-verified Pune district places

Every location string used in the seeded demo dataset and the rehearsed demo scenario SHALL name a real place in Pune district: Region A SHALL be a real urban ward and Region B a real rural village. Each demo location string SHALL be pre-verified to resolve correctly against Nominatim via a repeatable verification check that can run before the demo, so no live geocoding failure can surprise the presentation.

#### Scenario: Seed location verification passes against Nominatim

- **WHEN** the demo-location verification check runs against Nominatim
- **THEN** every seeded demo location string resolves to coordinates within Pune district
- **AND** the Region A string resolves to its urban ward and the Region B string to its rural village
- **AND** any string that fails to resolve is reported by the check before the demo, not discovered live

### Requirement: Cluster assigns requests by category, semantic similarity, and geographic proximity

The Cluster stage SHALL assign a GeocodedRequest to an existing DemandCluster only when all three conditions hold: the request shares the cluster's infrastructure category; the semantic similarity between the request and the cluster exceeds the configured similarity threshold; and the request's coordinates lie within the configured geographic proximity threshold of the cluster. Every assignment SHALL be recorded as a ClusterMembership carrying the computed similarity score — the visible "why it joined." A DemandCluster SHALL carry an accurate member count and a representative summary, and SHALL cite its member requests (every derived object traces back to raw evidence).

#### Scenario: Similar nearby water complaint joins the existing cluster

- **WHEN** a GeocodedRequest categorized as water infrastructure lies within the proximity threshold of an existing water DemandCluster and its semantic similarity to that cluster exceeds the threshold
- **THEN** a ClusterMembership linking the request to that cluster is created with the similarity score recorded on it
- **AND** the cluster's member count reflects the new member

#### Scenario: Region A and Region B never merge

- **WHEN** the seeded dataset's water requests — Region A's urban-ward requests and Region B's rural-village requests, geographically far apart — are clustered
- **THEN** they form two distinct DemandClusters: one large Region A cluster and one small Region B cluster, with member counts matching the seeded data
- **AND** no Region B request holds a ClusterMembership in the Region A cluster, despite semantic similarity (both describe water problems)

#### Scenario: Same location, different category stays apart

- **WHEN** a GeocodedRequest of a different infrastructure category lies within the proximity threshold of an existing water DemandCluster
- **THEN** it is not assigned to that water cluster, regardless of similarity or distance

### Requirement: Unmatched requests start a new DemandCluster

When no existing DemandCluster satisfies all three membership conditions for a GeocodedRequest, the Cluster stage SHALL create a new DemandCluster with that request as its founding member, recorded via a ClusterMembership. The new cluster SHALL carry the request's category, a member count of one, and a representative summary traceable to the founding request. No geocoded request is ever left unassigned by the Cluster stage.

#### Scenario: First complaint from a new area starts a cluster

- **WHEN** a geocoded water request lies beyond the proximity threshold of every existing water DemandCluster
- **THEN** a new DemandCluster is created with that request as its only member
- **AND** the cluster carries member count 1, the water category, and a representative summary traceable to that request

### Requirement: Clustering ambiguity resolves to the higher-similarity cluster with the alternative logged

When a GeocodedRequest satisfies the membership conditions for more than one DemandCluster, the Cluster stage SHALL assign it to the cluster with the higher similarity score, SHALL log the alternative candidate cluster and its similarity score in the request's RunTrace for later review, and SHALL NOT block, halt, or wait for human input on the ambiguity.

#### Scenario: Request qualifying for two clusters joins the closer semantic match

- **WHEN** a geocoded water request satisfies category, proximity, and similarity conditions for two existing DemandClusters, with similarity 0.91 to one and 0.84 to the other
- **THEN** exactly one ClusterMembership is created, in the 0.91-similarity cluster
- **AND** the RunTrace for that request records the 0.84-similarity cluster as the logged alternative, with its score
- **AND** the pipeline proceeds without human intervention

### Requirement: Seed-data embeddings computed once and cached

Semantic similarity SHALL use embeddings from the build's locked embedding source (Gemini `text-embedding-004`). Embeddings for the seeded demo requests SHALL be computed once at seed time and cached in the database's vector store; subsequent pipeline runs SHALL reuse the cached embeddings rather than re-requesting them from the external embedding API. This keeps rehearsals and the live demo within free-tier limits and makes clustering results reproducible across runs.

#### Scenario: Restarted pipeline reuses cached embeddings

- **WHEN** the seeded dataset has been embedded once and the backend is restarted and clustering runs again over the seed data
- **THEN** no new embedding API calls are made for the already-embedded seeded requests
- **AND** the similarity scores computed against seed data are unchanged from the prior run
