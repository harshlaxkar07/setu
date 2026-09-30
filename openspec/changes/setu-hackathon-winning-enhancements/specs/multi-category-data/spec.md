## Purpose

Extends Setu beyond water so the pipeline is demonstrably category-agnostic, and adds real-world facility data as a labelled, additive dataset.

## ADDED Requirements

### Requirement: Healthcare and road categories run end to end

The system SHALL support `healthcare` and `road_infrastructure` categories through Understand, Locate, Cluster, Fuse, Score, Recommend and the Publish Gate, with each category mapped to its facility type (health facilities for healthcare; all-weather road access points for roads) and seeded region data sufficient for scoring.

#### Scenario: Ambulance road complaint is scored

- **WHEN** a citizen submits "The road near our village school has been damaged for months and ambulances cannot reach us properly"
- **THEN** it is categorised as road_infrastructure with high urgency, clustered, scored with named indicators, and a recommendation awaits review at the Publish Gate

#### Scenario: Healthcare cluster scored against health facilities

- **WHEN** a healthcare cluster is fused
- **THEN** only health facilities within the service radius are counted toward its coverage

### Requirement: Real OpenStreetMap facilities can be imported as a labelled dataset

The system SHALL provide an importer that loads facilities for a bounding box from OpenStreetMap into a separate infrastructure dataset whose source is recorded as OpenStreetMap with the import timestamp. Imported facilities SHALL be distinguishable from synthetic seed facilities on the dashboard. The canonical seeded demo dataset SHALL remain the default for scoring unless an operator explicitly selects the imported dataset.

#### Scenario: Import hospitals for Pune district

- **WHEN** an operator runs the importer for healthcare in the Pune district bounding box
- **THEN** a new dataset labelled "OpenStreetMap, imported <timestamp>" contains the returned facilities and the seeded demo scores are unchanged

#### Scenario: Importer unavailable network

- **WHEN** the importer cannot reach the OpenStreetMap service
- **THEN** it exits with a clear error and no partial dataset is left behind

### Requirement: Equity invariant holds for every seeded category

For each seeded category that includes a high-volume well-served region and a low-volume underserved region, the underserved region SHALL have the strictly higher PriorityScore.

#### Scenario: Healthcare equity pair

- **WHEN** the seeded healthcare dataset is scored
- **THEN** the low-complaint underserved village outranks the high-complaint well-served ward
