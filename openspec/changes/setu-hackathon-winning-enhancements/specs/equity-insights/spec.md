## Purpose

Makes digital-participation bias visible: surfaces high-need regions that submit few or no complaints, and shows how a complaint-count ranking would differ from Setu's evidence-based ranking.

## ADDED Requirements

### Requirement: Silent regions are identified from infrastructure data alone

The system SHALL compute, for every region profile in each supported category, an infrastructure gap value using the same gap definition as cluster scoring, independent of whether the region has any citizen requests. A region SHALL be classed as a silent region when its gap is in the top configured percentile for the category and its complaint count is at or below a configured low threshold. Each silent region SHALL list the factors that caused the classification (gap, population, facilities in radius, complaint count, and vulnerability or connectivity indicators when available).

#### Scenario: Unreported underserved village is surfaced

- **WHEN** a seeded village has 6,000 residents, 0 health facilities within the service radius and 0 citizen requests
- **THEN** it appears in the silent-regions list for healthcare with its gap, population, facility count of 0 and complaint count of 0 shown

#### Scenario: Well-served region is not silent

- **WHEN** a region has no complaints but 8 facilities within the service radius and a gap below the category median
- **THEN** it does not appear in the silent-regions list

### Requirement: Silent regions are advisory and never auto-published

Silent-region entries SHALL be labelled as data-derived signals, not citizen demand, and SHALL NOT create recommendations or published items without passing through the Publish Gate.

#### Scenario: Silent region shown without recommendation

- **WHEN** the dashboard lists silent regions
- **THEN** each entry is labelled as a data-derived signal and no recommendation is published for it unless a reviewer approves one through the Publish Gate

### Requirement: Ranking comparison shows complaint-count versus Setu ranking

The system SHALL provide, for a selected category, two rankings of the same clusters: one ordered by raw complaint count and one ordered by PriorityScore, with each cluster's position in both and the rank change between them.

#### Scenario: Worked example flips order

- **WHEN** the ranking comparison is shown for water infrastructure on the seeded dataset
- **THEN** Kothrud is ranked first by complaint count, Velhe is ranked first by PriorityScore, and each shows its rank change
