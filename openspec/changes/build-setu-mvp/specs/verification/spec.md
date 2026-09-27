# Verification

## Purpose

Closes the post-resolution trust loop: after a DemandCluster is marked resolved, citizen follow-up submissions are plausibility-checked against the original complaint, and any mismatch is flagged for human review rather than auto-closed — treating "resolved" as a claim, not a fact, until verified.

## ADDED Requirements

### Requirement: Cluster resolution is a claim pending verification

The system SHALL provide a simulated resolution action (a button, not a government integration) that marks a published DemandCluster as resolved. A resolved cluster SHALL be recorded in a "resolved — unverified" state and SHALL remain unverified until a verification outcome exists. Marking a cluster resolved SHALL NOT close it, delete it, or alter any of its member requests, scores, or the approved Recommendation.

#### Scenario: Marking a cluster resolved

- **WHEN** an operator triggers the simulated "mark resolved" action on a published DemandCluster
- **THEN** the cluster's status becomes "resolved — unverified"
- **AND** the cluster, its member requests, its score breakdown, and its Recommendation remain unchanged and retrievable

#### Scenario: Resolution alone never verifies

- **WHEN** a cluster has been marked resolved and no VerificationRecord for it has a confirmed outcome
- **THEN** the cluster's state remains "resolved — unverified" indefinitely, with no automatic transition to a verified or closed state

### Requirement: Citizen verification prompt after resolution

After a DemandCluster is marked resolved, the citizen surface SHALL present a verification prompt asking for a follow-up photo or voice note, and SHALL present it only for a cluster that has been marked resolved. Before resolution, no verification prompt SHALL appear.

#### Scenario: Prompt appears once the cluster is resolved

- **WHEN** a citizen reopens the chat surface in a conversation whose request belongs to a cluster that has been marked resolved
- **THEN** a verification prompt is shown asking for a follow-up photo or voice note about that cluster's issue

#### Scenario: No prompt before resolution

- **WHEN** a citizen reopens the chat surface in a conversation whose request belongs to a cluster that is published but not marked resolved
- **THEN** no verification prompt is shown

### Requirement: Follow-up submission creates a VerificationRecord

The system SHALL accept a follow-up submission — one or more photos (including a before/after pair) and/or a voice note — referencing a resolved DemandCluster, and SHALL create a VerificationRecord for it. The raw follow-up submission SHALL be stored immutably and never edited, and each VerificationRecord SHALL start with a pending plausibility result until the check completes.

#### Scenario: Photo follow-up accepted

- **WHEN** a citizen uploads a before/after photo pair in that conversation in response to the verification prompt for a resolved cluster
- **THEN** a VerificationRecord is created referencing that cluster, containing the submitted photos unmodified, with a pending plausibility result

#### Scenario: Voice follow-up accepted

- **WHEN** a citizen submits a voice note in that conversation in response to the verification prompt for a resolved cluster
- **THEN** a VerificationRecord is created referencing that cluster with the voice submission stored unmodified and a pending plausibility result

### Requirement: Automated plausibility check against the original complaint

For every VerificationRecord, the system SHALL run an automated plausibility check comparing the follow-up submission against the original complaint's description for that cluster (the cluster's representative summary derived from its member StructuredRequests): photo submissions SHALL be checked with Gemini 2.5 Flash vision, and voice-note submissions SHALL be transcribed locally with Faster-Whisper (model "small") and the transcript compared against the cluster's summary with Gemini 2.5 Flash. A submission containing both photos and a voice note SHALL use the photo (vision) path; the transcript, when present, SHALL be included as additional context. The check SHALL produce exactly one of three outcomes recorded on the VerificationRecord: match, mismatch, or needs human review.

#### Scenario: Plausible follow-up yields match

- **WHEN** the plausibility check compares a follow-up photo showing restored water supply against a cluster whose original complaint describes "no drinking water supply"
- **AND** the check judges the follow-up consistent with the issue having been fixed
- **THEN** the VerificationRecord's result is recorded as "match"

#### Scenario: Outcome is always one of three values

- **WHEN** any plausibility check completes
- **THEN** the VerificationRecord carries exactly one result — match, mismatch, or needs human review — and no other value

### Requirement: Match outcome confirms verification

When a plausibility check returns match, the system SHALL log the VerificationRecord as confirmed, the associated cluster's ConfidenceLevel SHALL remain high, and the cluster SHALL transition to a "resolved — verified" state.

#### Scenario: Confirmed verification

- **WHEN** a VerificationRecord's plausibility result is "match"
- **THEN** the record is logged as confirmed, the cluster's ConfidenceLevel stays high, and the cluster's state becomes "resolved — verified"

### Requirement: Mismatch is flagged for human review and never auto-closed

When a plausibility check returns mismatch or needs human review, the system SHALL flag the VerificationRecord for human review and SHALL NOT close, verify, or auto-approve the cluster. The flag SHALL persist, and the cluster SHALL remain in "resolved — unverified" state, until a human records a review decision. The flagged record SHALL expose the original complaint's summary alongside the follow-up submission so a human can compare them; no automated path SHALL clear the flag. The review surface where the flagged record is displayed and the human review decision is captured is defined by the policymaker-dashboard spec's "Verification review surface" requirement.

#### Scenario: Deliberately mismatched photo pair is flagged

- **WHEN** a citizen uploads a before/after photo pair that does not plausibly show the reported water issue resolved (for example, the "after" photo still shows a dry, cracked pipe)
- **THEN** the plausibility result is "mismatch" and the VerificationRecord is flagged for human review
- **AND** the cluster is not marked verified or closed

#### Scenario: Flag persists until a human decides

- **WHEN** a VerificationRecord is flagged for human review and no human review decision has been recorded
- **THEN** the flag remains active and the cluster remains "resolved — unverified", regardless of elapsed time or further pipeline runs

#### Scenario: Flagged record carries the comparison evidence

- **WHEN** a flagged VerificationRecord is retrieved for review
- **THEN** it provides both the original complaint's summary text and the follow-up submission for side-by-side human comparison

### Requirement: Plausibility check failures default to human review

If the plausibility check fails (for example, a vision API error or rate limit), the system SHALL retry once; if the retry also fails, the VerificationRecord SHALL be recorded as "needs human review" and flagged. A check failure SHALL NEVER produce a match outcome, silently drop the submission, or auto-close the cluster.

#### Scenario: Vision check fails twice

- **WHEN** the plausibility check for a follow-up submission errors on the first attempt and again on the single retry
- **THEN** the VerificationRecord's result is "needs human review", the record is flagged for human review, and the submission is retained

### Requirement: VerificationRecord links to the cluster, not an individual

Every VerificationRecord and its submitted media SHALL be linked to the resolved DemandCluster, not to a named individual. On the policymaker-facing side, no VerificationRecord SHALL expose the submitting citizen's identity; the submitter reference SHALL remain pseudonymous.

#### Scenario: Record is cluster-scoped

- **WHEN** a VerificationRecord is inspected through any policymaker-facing surface or API
- **THEN** it references the DemandCluster it verifies and its submitted media
- **AND** it exposes no name, phone number, account handle, or other identity of the submitting citizen
