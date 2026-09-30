## Purpose

Turns accuracy and scale claims into measured, reproducible numbers that can be shown and re-run.

## ADDED Requirements

### Requirement: Labelled multilingual evaluation set

The project SHALL include a labelled evaluation set of at least 50 citizen messages spanning Hindi, Hinglish, English and Marathi, all supported categories, and informal location phrasing, each labelled with expected category, urgency, resolved location, and expected cluster.

#### Scenario: Evaluation set coverage

- **WHEN** the evaluation set is loaded
- **THEN** it contains at least 50 items, each of the four languages, and each supported category

### Requirement: Accuracy report

The project SHALL provide a command that runs the evaluation set through Understand, Locate and Cluster and reports accuracy for category, urgency, location resolution and cluster assignment, plus per-language breakdowns, as a machine-readable file and a human-readable summary. The command SHALL support running against recorded fixtures so results are reproducible offline.

#### Scenario: Reproducible offline run

- **WHEN** the evaluation command runs twice in replay mode
- **THEN** both runs report identical accuracy figures

### Requirement: Clustering scale test

The project SHALL provide a scale test that generates a configurable number of synthetic geocoded requests with precomputed embeddings and reports clustering throughput (requests per second) and total time, without calling external services.

#### Scenario: Ten thousand requests

- **WHEN** the scale test runs with 10,000 synthetic requests
- **THEN** it reports total time and requests per second, and makes no external network calls
