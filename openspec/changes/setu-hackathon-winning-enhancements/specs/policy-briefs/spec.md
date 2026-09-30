## Purpose

Produces a forwardable, evidence-only policy brief for a cluster so officials can share Setu's analysis outside the dashboard without losing its provenance.

## ADDED Requirements

### Requirement: Bilingual per-cluster policy brief

The system SHALL generate, for a selected cluster, a one-page brief in English and Hindi containing: the cluster summary, location, category, member and counted volume, every priority indicator with its value, the score breakdown, the recommendation text with its AI-drafted marker, and the recommendation's approval status with reviewer and time when approved. The brief SHALL contain no data that is not stored for that cluster.

#### Scenario: Brief for an approved recommendation

- **WHEN** a reviewer downloads the brief for Velhe after its recommendation was approved
- **THEN** the brief shows every indicator and the score breakdown, the recommendation marked AI-drafted, and "approved by <reviewer> at <time>" in both languages

### Requirement: Unapproved briefs are marked as drafts

A brief for a cluster whose recommendation is not approved SHALL be watermarked as a draft awaiting review on every page.

#### Scenario: Brief before approval

- **WHEN** a brief is downloaded while the recommendation is awaiting review
- **THEN** it is visibly marked "Draft — awaiting review" in both languages
