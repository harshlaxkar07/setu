## Purpose

Makes the citizen side trustworthy and accessible: visible progress for each submission, spoken receipts for low-literacy users, and an assisted mode for field workers in low-connectivity areas.

## ADDED Requirements

### Requirement: Submission status timeline

The citizen chat SHALL show, for each submission, a timeline of stages — received, understood, grouped with N others, under review, published, resolved — derived from stored state, updating while the page is open. Stages not yet reached SHALL be shown as pending, never as complete.

#### Scenario: Timeline after grouping

- **WHEN** a submission has been understood and joined a cluster of 20 requests but its recommendation awaits review
- **THEN** the timeline shows received, understood, and "grouped with 19 others" as complete, "under review" as current, and published and resolved as pending

### Requirement: Read-aloud receipts

The citizen chat SHALL offer a control on each receipt and system message that reads the message aloud in the interface language using on-device speech synthesis, with no audio sent to a server.

#### Scenario: Receipt read aloud in Hindi

- **WHEN** a citizen taps the speaker control on a Hindi receipt
- **THEN** the receipt is spoken in Hindi by the device, and no network request carries the text

#### Scenario: No speech support on device

- **WHEN** the device has no speech synthesis support
- **THEN** the speaker control is hidden and nothing else changes

### Requirement: Assisted field-worker mode

The citizen interface SHALL provide an assisted mode in which a field worker records requests on behalf of residents, tagging each with a village name and the number of households represented, without collecting any resident's name or phone number. Requests captured offline SHALL be queued on the device and submitted when connectivity returns, each submitted exactly once, with a visible queue count.

#### Scenario: Offline capture then sync

- **WHEN** a field worker records 4 requests while offline and connectivity later returns
- **THEN** the queue count shows 4 while offline, all 4 are submitted once online, the queue count returns to 0, and no request is duplicated

#### Scenario: Assisted requests are labelled

- **WHEN** an assisted request is shown on the dashboard
- **THEN** it is labelled as assisted and shows the households-represented count
