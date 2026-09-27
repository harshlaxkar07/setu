## Purpose

Citizen-facing intake for Setu: a bilingual, voice-first chat widget that captures Hindi/Hinglish infrastructure complaints as immutable CitizenRequests, transcribes voice locally, and derives a machine-readable StructuredRequest (category, urgency, summary, language, raw location mention) while giving the citizen a plain-language receipt of what was understood.

## ADDED Requirements

### Requirement: Citizen chat widget served as a standalone page

The system SHALL serve the citizen chat widget as a lightweight static HTML/JS web page from the backend HTTP service, independent of the policymaker dashboard application (which is a separate Streamlit process). The widget SHALL present a WhatsApp-style, single-column, mobile-viewport-first conversation layout in which press-and-hold voice recording is the primary input affordance and text entry is the fallback. The citizen surface SHALL expose only the current conversation — never other citizens' submissions and never policymaker-facing data.

#### Scenario: Citizen opens the chat page on a phone-sized viewport

- **WHEN** a citizen opens the chat page URL in a browser at a mobile viewport width
- **THEN** a single-column chat interface renders with a large press-and-hold voice record button as the primary affordance and a text input as the fallback
- **AND** no data belonging to other citizens or to the policymaker dashboard is reachable from the page

#### Scenario: Citizen surface works without the dashboard process

- **WHEN** the policymaker dashboard process is not running but the backend service is
- **THEN** the citizen chat page still loads and accepts voice and text submissions

### Requirement: Press-and-hold voice capture and audio upload

The chat widget SHALL record audio via the browser's media-recording capability while the citizen presses and holds the voice record button, and SHALL upload the recorded audio to the backend when the button is released. The uploaded audio SHALL be stored and linked to exactly one new CitizenRequest with channel `voice`. The sent voice message SHALL appear as a chat bubble with inline audio playback.

#### Scenario: Voice message recorded and submitted

- **WHEN** a citizen presses and holds the voice record button, speaks the demo line "हमारे गाँव में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।", and releases the button
- **THEN** the recorded audio is uploaded to the backend and persisted as a new CitizenRequest with channel `voice`, a timestamp, and the audio payload
- **AND** the citizen's chat history shows the voice message as a bubble with inline playback

#### Scenario: Microphone permission is denied

- **WHEN** the browser denies microphone access to the chat page
- **THEN** the widget shows bilingual (Hindi-primary, English subtitle) guidance that voice is unavailable
- **AND** text submission remains fully usable

### Requirement: Text submission fallback

The chat widget SHALL accept typed text submissions in Hindi (Devanagari) and Hinglish (Latin-script Hindi). Each sent text message SHALL be persisted as a new CitizenRequest with channel `text` and the raw text payload.

#### Scenario: Hinglish text complaint submitted

- **WHEN** a citizen types "paani nahi aa raha hai hamare gaon mein kai hafton se" and sends it
- **THEN** the message is persisted as a new CitizenRequest with channel `text` containing the exact submitted text
- **AND** the message appears in the citizen's chat history

### Requirement: CitizenRequest is persisted before processing and is immutable

The system SHALL persist every submission as a CitizenRequest — raw payload (audio or text), timestamp, channel, and pseudonymous submitter reference — before any transcription or AI processing begins. A persisted CitizenRequest SHALL never be edited or deleted by any pipeline stage or exposed endpoint; all downstream corrections and derivations SHALL be new objects that reference the CitizenRequest. A processing failure after ingestion SHALL never remove or alter the raw CitizenRequest.

#### Scenario: Raw request survives downstream processing unchanged

- **WHEN** the Understand stage completes for a voice CitizenRequest
- **THEN** the stored CitizenRequest's audio payload, timestamp, channel, and submitter reference are byte-for-byte identical to what was persisted at ingestion
- **AND** the derived StructuredRequest is a separate record referencing the CitizenRequest

#### Scenario: No mutation path exists

- **WHEN** any HTTP client attempts to modify or delete an existing CitizenRequest through the backend API
- **THEN** the backend offers no endpoint that performs such an edit or deletion, and the attempt is rejected without changing the stored record

#### Scenario: Transcription or understanding fails after ingestion

- **WHEN** speech-to-text or the language-model extraction fails for a submitted request
- **THEN** the raw CitizenRequest remains persisted and available for reprocessing
- **AND** no StructuredRequest with fabricated default values is produced for it

### Requirement: Pseudonymous, minimal-PII intake

The chat widget SHALL NOT ask the citizen for a name, phone number, or identity document at any point in the submission flow. Each CitizenRequest SHALL carry a stable per-conversation pseudonymous submitter reference so that follow-ups in the same conversation link together without identifying the citizen.

#### Scenario: Submission flow collects no personal identity

- **WHEN** a citizen completes a voice or text submission end to end
- **THEN** no name, phone number, or identity field was requested or captured
- **AND** the stored CitizenRequest contains only a pseudonymous submitter reference as its submitter identity

#### Scenario: Same conversation, same pseudonym

- **WHEN** the same citizen sends a second message in the same conversation
- **THEN** both CitizenRequests carry the same pseudonymous submitter reference

### Requirement: Local speech-to-text transcription

The system SHALL transcribe voice CitizenRequests locally using Faster-Whisper with the `small` model — audio SHALL NOT be sent to any external speech-to-text service. The transcription SHALL be stored as a derived artifact linked to the CitizenRequest and passed to the Understand stage. If Hindi transcription accuracy fails the 8-of-10 bar on the demo evaluation set (per the build plan's intake definition of done), the model SHALL be upgraded to `medium`; no larger change is in scope.

#### Scenario: Demo Hindi voice line transcribed locally

- **WHEN** the demo voice recording "हमारे गाँव में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।" is ingested
- **THEN** a Hindi transcription capturing the drinking-water complaint is produced by the local Faster-Whisper model without any network call carrying the audio off the host
- **AND** the transcription is stored linked to the CitizenRequest

#### Scenario: Intake accuracy bar on the demo dataset

- **WHEN** the 10 real Hindi voice recordings of the demo evaluation set are each run through transcription and the Understand stage
- **THEN** at least 8 of 10 yield a StructuredRequest with correct category, urgency, and summary

### Requirement: Understand stage derives a StructuredRequest

The system SHALL derive exactly one StructuredRequest from each CitizenRequest's text or transcription using the configured LLM (Gemini 2.5 Flash), extracting: category, urgency, a free-text summary, detected language, and the raw location mention as spoken or typed (unresolved — geocoding belongs to the Locate stage). The StructuredRequest SHALL reference its source CitizenRequest. An absent location mention SHALL NOT prevent the StructuredRequest from being produced. Demo inputs SHALL mention only real Pune-district places pre-verified for the demo dataset.

#### Scenario: Demo voice line understood

- **WHEN** the Understand stage processes the transcription of the demo line, which names a pre-verified rural village in Pune district
- **THEN** a StructuredRequest is produced with category "water infrastructure", urgency "high", a summary describing the multi-week drinking-water outage, detected language Hindi, and the village name captured verbatim as the raw location mention
- **AND** the StructuredRequest references the source CitizenRequest

#### Scenario: Hinglish text understood

- **WHEN** the Understand stage processes a Hinglish text CitizenRequest about a water problem
- **THEN** the StructuredRequest carries detected language Hinglish and a correct water-category classification

#### Scenario: Submission without any location mention

- **WHEN** a submission describes a water problem but names no place
- **THEN** a StructuredRequest is still produced with its raw location mention empty
- **AND** the request is not discarded by the intake stage

### Requirement: Submission receipt with plain-language understood-summary

After the Understand stage completes, the chat widget SHALL show the citizen a submission receipt confirming the request was received, containing a plain-language restatement of what was understood (at minimum category and urgency, e.g. "हमने समझा: पानी की समस्या, ज़रूरी" / "We understood: water supply issue, high urgency"). The receipt's AI-generated summary text SHALL carry the consistent "AI-drafted" provenance marker, distinct from the citizen's own messages.

#### Scenario: Receipt after a successful voice submission

- **WHEN** the demo voice complaint completes the Understand stage
- **THEN** the chat shows a receipt bubble stating, in plain Hindi with an English subtitle, that a water supply issue of high urgency was understood
- **AND** the AI-generated summary portion carries the "AI-drafted" provenance marker

#### Scenario: Receipt reflects what was actually extracted

- **WHEN** the Understand stage classifies a submission with a different category or urgency than the demo line
- **THEN** the receipt restates that submission's own extracted category and urgency, not fixed template values

### Requirement: Per-message language indicator

The chat widget SHALL display a small, non-intrusive language chip showing the detected language for each processed message, updating per message rather than per conversation.

#### Scenario: Language chip follows each message

- **WHEN** a citizen sends a Hindi voice message followed by a Hinglish text message in the same conversation
- **THEN** the first message's chip shows Hindi and the second message's chip shows Hinglish

### Requirement: Bilingual Hindi-primary chrome in the citizen register

All chat-widget chrome (labels, buttons, prompts, guidance, receipts) SHALL be bilingual with Hindi (Devanagari script) primary and smaller English subtitles. Devanagari text SHALL render in Noto Sans Devanagari — never a silent Latin-only fallback. The widget SHALL follow the citizen register of the design system: warm accent, large type, rounded shapes (16px radii on the citizen surface), touch targets at least 44px, minimal chrome, and no policymaker-register components.

#### Scenario: Chrome renders bilingually with correct fonts

- **WHEN** the chat page loads
- **THEN** every chrome label shows Hindi in Devanagari as the primary text with a smaller English subtitle
- **AND** Devanagari text renders in Noto Sans Devanagari

#### Scenario: Touch targets meet the citizen-register minimum

- **WHEN** the rendered page's interactive controls (voice record button, send button) are measured
- **THEN** each has a hit area of at least 44px in both dimensions, with the voice record button visibly the largest affordance
