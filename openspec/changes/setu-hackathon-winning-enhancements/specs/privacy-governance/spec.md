## Purpose

Reduces exposure of personal data to AI providers and makes human decisions attributable and tamper-evident.

## ADDED Requirements

### Requirement: PII masked before any LLM or embedding call

Before citizen text or a transcription is sent to any language or embedding model, the system SHALL replace phone numbers, Aadhaar-like 12-digit numbers, email addresses, and names introduced by self-identifying phrases (for example "my name is", "मेरा नाम") with typed placeholders. The raw text SHALL remain stored only in the citizen request record; the masked text SHALL be what is recorded in the run trace as sent.

#### Scenario: Phone number never reaches the model

- **WHEN** a citizen writes "मेरा नाम सुनीता है, फ़ोन 9876543210, वेल्हे में पानी नहीं है"
- **THEN** the text sent to the model contains placeholders for the name and phone number, the location and complaint are preserved, and the run trace records the masked text

### Requirement: Hash-chained decision log

Every Publish Gate decision, verification review, and trust-flag review SHALL be appended to a decision log in which each entry stores a hash over its content and the previous entry's hash. The system SHALL expose a verification check that recomputes the chain and reports the first broken entry, if any.

#### Scenario: Intact chain verifies

- **WHEN** the chain verification runs after several decisions
- **THEN** it reports the chain as intact with the entry count

#### Scenario: Tampered entry detected

- **WHEN** a stored decision's reviewer or decision is altered directly in the database
- **THEN** the chain verification reports the altered entry as the first break

### Requirement: Configured reviewer accounts

Decision actions on the dashboard SHALL require a signed-in reviewer from a configured list of reviewer accounts with passcodes. The recorded reviewer identity SHALL come from the signed-in account, not from free text. Read-only viewing SHALL remain available without sign-in.

#### Scenario: Unsigned user cannot approve

- **WHEN** a viewer who is not signed in opens the Publish Gate
- **THEN** recommendations are visible but approve, reject and request-changes actions are unavailable, and the backend rejects a decision request without a valid reviewer session

#### Scenario: Wrong passcode

- **WHEN** a reviewer enters an incorrect passcode
- **THEN** sign-in fails with a clear message and no session is created
