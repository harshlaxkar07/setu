-- Setu data contract (design D3) — build step 1 of files/09-build-plan.md.
-- One database: relational + PostGIS geometry + pgvector embeddings.
-- Extensions are enabled by db/init/01-extensions.sql before this file applies.
-- LangGraph checkpointer tables are created by langgraph-checkpoint-postgres at
-- backend startup (same database, its own tables) — not defined here.

-- ---------------------------------------------------------------- enums

CREATE TYPE channel_type AS ENUM ('voice', 'text', 'whatsapp');
CREATE TYPE confidence_level AS ENUM ('high', 'medium', 'flagged');
CREATE TYPE urgency_level AS ENUM ('high', 'medium', 'low');
CREATE TYPE investment_level AS ENUM ('low', 'medium', 'high');
CREATE TYPE cluster_status AS ENUM
    ('active', 'published', 'resolved_unverified', 'resolved_verified');
CREATE TYPE recommendation_status AS ENUM
    ('pending', 'published', 'rejected', 'needs_revision');
CREATE TYPE approval_decision AS ENUM ('approved', 'rejected', 'needs_revision');
CREATE TYPE verification_result AS ENUM
    ('pending', 'match', 'mismatch', 'needs_human_review');
CREATE TYPE run_status AS ENUM
    ('in_progress', 'awaiting_approval', 'published', 'rejected', 'needs_retry');

-- ---------------------------------------------------------- citizen intake

-- Raw submissions. Immutable: no UPDATE/DELETE path in the API, enforced
-- additionally by the trigger below (citizen-intake spec).
CREATE TABLE citizen_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    channel       channel_type NOT NULL,
    raw_text      text,                    -- text-channel payload
    audio_path    text,                    -- voice-channel payload (media volume path)
    submitter_ref text NOT NULL,           -- pseudonymous per-conversation reference
    submitted_at  timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (raw_text IS NOT NULL OR audio_path IS NOT NULL)
);

CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'citizen_requests is immutable: % not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER citizen_requests_immutable
    BEFORE UPDATE OR DELETE ON citizen_requests
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

-- Derived STT artifact, written before Understand runs — a failed Understand
-- still has the transcription persisted and retries never redo STT (design D3).
CREATE TABLE transcriptions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_request_id uuid NOT NULL REFERENCES citizen_requests(id),
    text               text NOT NULL,
    model              text NOT NULL,      -- e.g. 'faster-whisper-small'
    detected_language  text,
    created_at         timestamptz NOT NULL DEFAULT now()
);

-- One per CitizenRequest, created only by a successful Understand.
CREATE TABLE structured_requests (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_request_id   uuid NOT NULL UNIQUE REFERENCES citizen_requests(id),
    category             text NOT NULL,
    urgency              urgency_level NOT NULL,
    summary              text NOT NULL,
    detected_language    text,
    raw_location_mention text,             -- verbatim, unresolved; may be empty
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- NULL geom = unresolvable location: proceeds flagged, never dropped.
CREATE TABLE geocoded_requests (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    structured_request_id uuid NOT NULL UNIQUE REFERENCES structured_requests(id),
    geom                  geometry(Point, 4326),
    confidence            confidence_level NOT NULL,
    confidence_reason     text,            -- required in practice when not 'high'
    embedding             vector(768),     -- text-embedding-004; cached (design D5)
    created_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (confidence = 'high' OR confidence_reason IS NOT NULL)
);
CREATE INDEX geocoded_requests_geom_idx ON geocoded_requests USING gist (geom);

-- ------------------------------------------------------ demand & clustering

CREATE TABLE demand_clusters (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category               text NOT NULL,
    centroid               geometry(Point, 4326),
    representative_summary text,
    member_count           integer NOT NULL DEFAULT 0,
    status                 cluster_status NOT NULL DEFAULT 'active',
    confidence             confidence_level NOT NULL DEFAULT 'high',
    confidence_reason      text,
    created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX demand_clusters_centroid_idx ON demand_clusters USING gist (centroid);

-- The "why it joined" join table; a request belongs to exactly one cluster.
CREATE TABLE cluster_memberships (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    geocoded_request_id uuid NOT NULL UNIQUE REFERENCES geocoded_requests(id),
    demand_cluster_id   uuid NOT NULL REFERENCES demand_clusters(id),
    similarity_score    numeric,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX cluster_memberships_cluster_idx
    ON cluster_memberships (demand_cluster_id);

-- ----------------------------------------------------------- external data

CREATE TABLE infrastructure_datasets (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    coverage_area text,
    last_updated  date,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE infrastructure_facilities (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id    uuid NOT NULL REFERENCES infrastructure_datasets(id),
    facility_type text NOT NULL,           -- e.g. 'water_point'
    geom          geometry(Point, 4326) NOT NULL,
    functioning   boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX infrastructure_facilities_geom_idx
    ON infrastructure_facilities USING gist (geom);

-- Population + investment per seeded area — the rows indicators cite.
CREATE TABLE region_profiles (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text NOT NULL,
    boundary         geometry(Geometry, 4326),
    population       integer NOT NULL,
    investment_label investment_level NOT NULL,
    dataset_id       uuid NOT NULL REFERENCES infrastructure_datasets(id),
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- --------------------------------------------------- scoring & recommendation

-- InfrastructureGapScore with its traceable inputs. No complaint-volume input.
CREATE TABLE gap_scores (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    demand_cluster_id uuid NOT NULL REFERENCES demand_clusters(id),
    population        integer NOT NULL,
    facility_count    integer NOT NULL,
    gap_value         numeric NOT NULL,
    dataset_citations jsonb NOT NULL DEFAULT '[]',
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- One row per named factor — individually retrievable (modeling principle 3).
CREATE TABLE priority_indicators (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    demand_cluster_id uuid NOT NULL REFERENCES demand_clusters(id),
    name              text NOT NULL,
    value_text        text,
    value_numeric     numeric,
    source_citations  jsonb NOT NULL DEFAULT '[]',
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX priority_indicators_cluster_idx
    ON priority_indicators (demand_cluster_id);

-- Stores the components so the dashboard breakdown and the formula-consistency
-- test read stored data, not recomputation (design D1).
CREATE TABLE priority_scores (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    demand_cluster_id       uuid NOT NULL REFERENCES demand_clusters(id),
    score                   numeric NOT NULL,
    gap_norm                numeric NOT NULL,
    investment_deficit_norm numeric NOT NULL,
    volume_norm             numeric NOT NULL,
    weights                 jsonb NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now()
);

-- Insert refused when citations are missing (fusion-scoring spec): the cluster
-- FK is NOT NULL and indicator citations must be a non-empty array.
CREATE TABLE recommendations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    demand_cluster_id   uuid NOT NULL REFERENCES demand_clusters(id),
    intervention_text   text NOT NULL,
    intervention_type   text NOT NULL,
    indicator_citations jsonb NOT NULL,
    status              recommendation_status NOT NULL DEFAULT 'pending',
    thread_id           text,              -- LangGraph thread suspended at the gate
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(indicator_citations) = 'array'
           AND jsonb_array_length(indicator_citations) > 0)
);

-- The gate record; the published view derives solely from these rows (design D2).
CREATE TABLE approvals (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id uuid NOT NULL REFERENCES recommendations(id),
    decision          approval_decision NOT NULL,
    reviewer          text NOT NULL,
    decided_at        timestamptz NOT NULL DEFAULT now(),
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------- trust & verification

-- Cluster-scoped, pseudonymous; raw media immutable (verification spec).
CREATE TABLE verification_records (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    demand_cluster_id uuid NOT NULL REFERENCES demand_clusters(id),
    media_paths       jsonb NOT NULL DEFAULT '[]',
    voice_path        text,
    submitter_ref     text NOT NULL,
    result            verification_result NOT NULL DEFAULT 'pending',
    flagged           boolean NOT NULL DEFAULT false,
    review_decision   text,               -- 'confirm_resolved' / 'reject_resolution'
    review_reviewer   text,
    reviewed_at       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- workflow

-- The explainability record and the ops-view source. stages: ordered jsonb
-- array of per-stage entries {stage, input_ref, output_ref, duration_ms,
-- error, retried, alternatives}.
CREATE TABLE run_traces (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_request_id uuid NOT NULL REFERENCES citizen_requests(id),
    thread_id          text,
    status             run_status NOT NULL DEFAULT 'in_progress',
    stages             jsonb NOT NULL DEFAULT '[]',
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX run_traces_request_idx ON run_traces (citizen_request_id);
CREATE INDEX run_traces_status_idx ON run_traces (status);
