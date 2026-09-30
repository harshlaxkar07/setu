## Purpose

Helps policymakers reason about where to invest by simulating the effect of proposed facilities on infrastructure gaps and by suggesting sites that maximise people served within a budget, strictly as advisory analysis.

## ADDED Requirements

### Requirement: What-if facility placement

The system SHALL accept a proposed facility (category and coordinates) and return, without persisting any change to real facility data, the regions and clusters whose facility coverage would change, their gap before and after, and the population newly within the service radius.

#### Scenario: Proposed water point in Velhe

- **WHEN** a planner proposes a water point at the Velhe cluster centroid
- **THEN** the response shows Velhe's facility count changing from 0 to 1, its gap before and after, the newly covered population, and no facility row is added to the stored dataset

#### Scenario: Proposal outside all regions

- **WHEN** a planner proposes a facility at coordinates with no region or cluster within the service radius
- **THEN** the response states that no population is newly covered and returns no error

### Requirement: Budget-constrained site allocation

The system SHALL, given a category and a number of facilities N, return up to N suggested sites chosen to maximise total population newly covered, with each site's newly covered population, the regions it serves, and the cumulative total. Candidate sites SHALL be drawn from cluster centroids and region centroids of that category. Each suggestion SHALL state that it is advisory.

#### Scenario: Allocate three health centres

- **WHEN** a planner asks for 3 healthcare sites
- **THEN** up to 3 sites are returned in order of marginal population covered, each with its newly covered population and served regions, a cumulative total, and an advisory label

### Requirement: Planner output cannot publish

Planner results SHALL NOT create, modify, or publish recommendations, clusters, or facilities.

#### Scenario: Planner run leaves published state unchanged

- **WHEN** a planner runs any number of what-if or allocation requests
- **THEN** the set of published recommendations and stored facilities is identical before and after
