## Purpose

Turns a DemandCluster into explainable prioritization intelligence: the Fuse stage joins the cluster with seeded infrastructure, population, and investment data; the Score stage computes an InfrastructureGapScore, named PriorityIndicators, and a composite PriorityScore whose construction guarantees complaint volume never overrides infrastructure gap; the Recommend stage drafts one evidence-cited Recommendation.

## ADDED Requirements

### Requirement: Fuse stage joins infrastructure context onto a DemandCluster

The Fuse stage SHALL, for a given DemandCluster, produce a fused cluster record linking: (a) every InfrastructureFacility of the cluster's category within the defined service radius of the cluster's location, (b) the population figure for the cluster's area, and (c) the historical investment label (low/medium/high) for the cluster's area — all drawn from the seeded InfrastructureDataset. Each linked value SHALL cite the InfrastructureDataset rows it came from, so the join is traceable back to source data. A cluster with zero facilities in radius SHALL still fuse successfully, recording a facility count of zero rather than failing or being dropped.

#### Scenario: Urban cluster fuses with nearby facilities

- **WHEN** the Fuse stage runs on the seeded Region A (urban Pune ward) DemandCluster, whose area contains 10 water infrastructure points within the service radius
- **THEN** the fused cluster record links all 10 InfrastructureFacility rows, the Region A population figure, and the Region A investment label, each citing the InfrastructureDataset rows used

#### Scenario: Cluster with no facilities in radius still fuses

- **WHEN** the Fuse stage runs on the seeded Region B (rural Pune village) DemandCluster, whose area has 0 functioning water points within the service radius
- **THEN** fusion completes without error, the fused record shows a facility count of 0, and the cluster proceeds to the Score stage

### Requirement: InfrastructureGapScore is computed independently of complaint volume

The system SHALL compute an InfrastructureGapScore for every fused DemandCluster as population divided by facility coverage for the cluster's area. Complaint volume (cluster member count) SHALL NOT be an input to the InfrastructureGapScore. A facility coverage of zero SHALL yield the maximum (most severe) gap score for the category, never a division error or a dropped cluster.

#### Scenario: Equal areas with different complaint counts get equal gap scores

- **WHEN** two fused DemandClusters have identical population and facility coverage but member counts of 500 and 20 respectively
- **THEN** both clusters receive the same InfrastructureGapScore

#### Scenario: Zero facility coverage yields the most severe gap

- **WHEN** the Score stage computes the gap for the Region B cluster, which has 0 facilities within the service radius
- **THEN** Region B's InfrastructureGapScore is the maximum gap value among seeded water-category clusters, and no error is raised

### Requirement: PriorityIndicators are named, valued, and individually recorded

The Score stage SHALL record, for every scored DemandCluster, a set of named PriorityIndicators, each stored as a separate retrievable factor with a human-readable name and a value. The set SHALL include at minimum: population affected, distance to nearest functioning facility (or facility coverage), historical investment level, and complaint volume. Each PriorityIndicator SHALL cite the InfrastructureDataset rows or cluster data it was derived from. The system SHALL NOT expose a PriorityScore whose contributing PriorityIndicators cannot be retrieved with it.

#### Scenario: Scored cluster exposes its named factors

- **WHEN** the Score stage completes for the Region B cluster
- **THEN** the stored result includes individually retrievable PriorityIndicators such as "population affected", "distance to nearest functioning source", "historical investment: low", and "complaint volume", each with its value and source citation

#### Scenario: No score without factors

- **WHEN** any consumer requests a cluster's PriorityScore through the backend API
- **THEN** the response includes the full list of that cluster's PriorityIndicators alongside the composite number

### Requirement: Composite PriorityScore uses the locked dominance-by-construction formula

The system SHALL compute PriorityScore = 0.5 × gap_norm + 0.3 × investment_deficit_norm + 0.2 × volume_norm, where each term is the corresponding indicator min-max normalized across all DemandClusters of the same category. Investment deficit SHALL be derived from the historical investment label such that lower investment produces a higher deficit value. The weights are fixed constants in the scoring implementation — the complaint-volume weight (0.2) is capped below the gap weight (0.5) by construction, not by runtime configuration — so complaint volume can never override the InfrastructureGapScore contribution. When all clusters in a category share the same value for an indicator, its normalized value SHALL be a defined constant (not NaN or an error).

#### Scenario: Score matches the formula on seeded data

- **WHEN** the Score stage runs over the seeded water-category clusters
- **THEN** each cluster's stored PriorityScore equals 0.5 × gap_norm + 0.3 × investment_deficit_norm + 0.2 × volume_norm computed from its stored PriorityIndicators, within floating-point tolerance

#### Scenario: Degenerate normalization is defined

- **WHEN** every water-category cluster has the same historical investment label
- **THEN** the investment_deficit_norm term is a defined constant for all of them and scoring completes without error

### Requirement: Region B outranks Region A on the seeded demo data (equity invariant)

On the seeded Pune district demo dataset — Region A (urban ward: 10 facilities in radius, high historical investment, large complaint cluster of ~500 requests) and Region B (rural village: 0 facilities in radius, low historical investment, small complaint cluster of ~20 requests) — the system SHALL rank Region B's DemandCluster strictly above Region A's by PriorityScore. An automated invariant test SHALL assert this ordering against the seeded data and SHALL fail the test suite if Region A ever outranks Region B.

#### Scenario: Gap analysis beats raw complaint count

- **WHEN** the pipeline scores both seeded Pune clusters
- **THEN** Region B's PriorityScore is strictly greater than Region A's, despite Region A having roughly 25× the complaint volume

#### Scenario: Invariant is guarded by an automated test

- **WHEN** the test suite runs against the seeded demo database
- **THEN** a dedicated invariant test asserts PriorityScore(Region B) > PriorityScore(Region A) and the suite fails if the assertion does not hold

### Requirement: Recommend stage generates one evidence-cited draft Recommendation

The Recommend stage SHALL generate, for a scored DemandCluster, exactly one draft Recommendation consisting of intervention text and a structured intervention type. The Recommendation SHALL cite the DemandCluster it addresses and the specific PriorityIndicators that justify it, so a reviewer can trace it back to the cluster and dataset rows that produced it. A Recommendation lacking its cluster citation or indicator citations SHALL be rejected as invalid rather than stored. The Recommendation SHALL be produced in draft (unpublished) status; publication is outside this capability.

#### Scenario: Recommendation for the rural cluster cites its evidence

- **WHEN** the Recommend stage runs on the scored Region B cluster
- **THEN** it stores one draft Recommendation whose citations include the Region B DemandCluster and the indicators that justified it (for example zero facilities within service radius and low historical investment), with a structured intervention type

#### Scenario: Uncited recommendation output is rejected

- **WHEN** the Recommend stage produces output that omits the DemandCluster citation or the justifying PriorityIndicators
- **THEN** the system rejects the output as invalid and does not store it as a Recommendation
