## Purpose

Keeps Setu vendor-neutral by routing all language-model and embedding calls through one interface whose provider is chosen by configuration.

## ADDED Requirements

### Requirement: Provider selected by configuration

All language-model and embedding calls SHALL go through a single provider interface. The provider SHALL be selected by environment configuration, with Gemini as the default and an OpenAI-compatible endpoint (such as a locally hosted model) as a supported alternative. Switching provider SHALL NOT require code changes.

#### Scenario: Switch to local model

- **WHEN** the operator sets the provider to the OpenAI-compatible option with a local endpoint and restarts the backend
- **THEN** a new text submission is understood using the local endpoint and the run trace records the provider and model used

### Requirement: Provider and model recorded per call

Every run trace stage that calls a model SHALL record the provider name, model name, latency, and token counts when the provider reports them.

#### Scenario: Trace shows provider details

- **WHEN** a reviewer opens the run trace for a request
- **THEN** each AI stage shows the provider, model, latency and token counts where available

### Requirement: Embedding dimension compatibility

When the configured embedding provider produces vectors of a dimension different from the stored vector column, the system SHALL refuse to start clustering with a clear error rather than store incompatible vectors.

#### Scenario: Mismatched embedding dimension

- **WHEN** the configured embedding model returns 1024-dimension vectors and the column is 768-dimension
- **THEN** the backend reports the mismatch at startup and no vectors are written
