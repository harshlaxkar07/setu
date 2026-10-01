-- Trust & anti-manipulation flags (enhancements design D2). A flag never
-- deletes or hides anything: it records a rule, a human-readable reason and a
-- review status. Request-level flags (duplicate_burst, repeat_source) exclude
-- the request from the complaint-volume indicator while open or confirmed;
-- cluster-level flags (cluster_spike) lower the cluster's confidence.
CREATE TABLE IF NOT EXISTS trust_flags (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_request_id uuid REFERENCES citizen_requests(id),
    demand_cluster_id  uuid REFERENCES demand_clusters(id),
    rule               text NOT NULL
        CHECK (rule IN ('duplicate_burst', 'repeat_source', 'cluster_spike')),
    reason             text NOT NULL,
    status             text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'cleared', 'confirmed')),
    reviewer           text,
    reviewed_at        timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (citizen_request_id IS NOT NULL OR demand_cluster_id IS NOT NULL),
    CHECK ((status = 'open') = (reviewer IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS trust_flags_request_rule_idx
    ON trust_flags (citizen_request_id, rule) WHERE citizen_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS trust_flags_cluster_idx ON trust_flags (demand_cluster_id);
