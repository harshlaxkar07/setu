## Purpose

Gives policymakers a live, navigable analytics surface — heatmap, category and time views, and the equity, planner and impact tools — while keeping every number explainable.

## ADDED Requirements

### Requirement: Live auto-refresh

The dashboard SHALL refresh cluster, recommendation and trust data automatically at a configured interval without losing the selected cluster, the open tab, or unsaved reviewer input.

#### Scenario: New submission appears without reload

- **WHEN** a citizen submits a request that joins an existing cluster while the dashboard is open
- **THEN** the cluster's member count updates within one refresh interval and the reviewer's selected cluster stays selected

### Requirement: Category filter across views

The dashboard SHALL provide a category filter that applies consistently to the map, cluster list, summary counts, trends, ranking comparison and silent regions.

#### Scenario: Filter to healthcare

- **WHEN** a reviewer selects the healthcare category
- **THEN** every view shows only healthcare clusters and regions, and the summary counts reflect the filter

### Requirement: Demand heatmap and gap layer

The map SHALL offer toggleable layers for cluster markers, a demand heatmap weighted by counted (unflagged) volume, and silent regions, with a legend that pairs every colour with a text label.

#### Scenario: Toggle silent regions layer

- **WHEN** a reviewer enables the silent-regions layer
- **THEN** silent regions render with a distinct labelled marker style and a legend entry

### Requirement: Demand trends over time

The dashboard SHALL chart daily or weekly request counts per category, separating flagged from unflagged requests.

#### Scenario: Spam spike visible in trends

- **WHEN** the spam-attack script has run
- **THEN** the trend chart shows the spike as flagged volume distinct from unflagged volume

### Requirement: Views for equity, planner, impact and briefs

The dashboard SHALL expose the ranking comparison, silent regions, investment planner, impact metrics and policy brief download as navigable sections, each showing its inputs and labelling advisory output as advisory.

#### Scenario: Planner from the dashboard

- **WHEN** a reviewer selects a cluster and proposes a facility at its centroid
- **THEN** the dashboard shows the before/after gap and newly covered population labelled as advisory
