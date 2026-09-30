## Purpose

Lets citizens use any language the speech and language models detect, with a switchable UI and resilient handling of informal location descriptions.

## ADDED Requirements

### Requirement: Open language detection and labelling

The Understand stage SHALL record the detected language of every request using a human-readable language name for any language detected, not only Hindi, Hinglish or English. Mixed-language text SHALL be labelled as such (for example "Hinglish" or "Marathi-English").

#### Scenario: Marathi text request

- **WHEN** a citizen submits a Marathi-language water complaint
- **THEN** the structured request records the category, urgency and a detected language of Marathi, and the receipt shows a Marathi language chip

### Requirement: Citizen UI language switch

The citizen interface SHALL offer interface-text languages of at least Hindi, English and Marathi, remembered per device, without requiring the citizen to choose before submitting.

#### Scenario: Switching to Marathi

- **WHEN** a citizen selects Marathi
- **THEN** the welcome message, topic buttons, hints and receipts render in Marathi with English subtitles, and the choice persists on reload

### Requirement: Informal location fallback

When geocoding of the extracted location mention fails, the Locate stage SHALL attempt, in order: matching against known region names including common suffixes such as "gaon", "gaav", "village" or "ward N"; and matching against seeded facility or landmark names. A location resolved by fallback SHALL carry confidence below high with a reason naming the fallback used.

#### Scenario: Village suffix no longer breaks geocoding

- **WHEN** a citizen writes "वेल्हे गाँव में पानी नहीं है"
- **THEN** the request resolves to Velhe with a reason stating a region-name fallback was used, and it joins the Velhe cluster

### Requirement: Follow-up location question

When no location can be resolved, the citizen chat SHALL ask one follow-up question for the village, ward or nearest landmark, and SHALL attach the answer to the same request and re-run location resolution. The request SHALL remain stored and flagged whether or not the citizen answers.

#### Scenario: Citizen answers the follow-up

- **WHEN** a request has no resolvable location and the citizen answers the follow-up with "Velhe"
- **THEN** the same request is re-located to Velhe and continues through the pipeline

#### Scenario: Citizen ignores the follow-up

- **WHEN** the citizen does not answer
- **THEN** the request remains stored with an unresolved-location flag and is never dropped
