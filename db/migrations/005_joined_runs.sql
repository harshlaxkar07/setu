-- Gate consolidation (enhancements design D19): a run that joins a cluster's
-- already-pending recommendation records which one, so the gate decision can
-- settle it too. SET NULL keeps traces when test/cleanup removes a draft.
ALTER TABLE run_traces
    ADD COLUMN IF NOT EXISTS joined_recommendation_id uuid
        REFERENCES recommendations(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS run_traces_joined_rec_idx
    ON run_traces (joined_recommendation_id);
