-- Impact measurement (enhancements design D9): when a cluster was marked
-- resolved, and by whom, so before/after windows are computed from stored
-- timestamps rather than estimated.
ALTER TABLE demand_clusters
    ADD COLUMN IF NOT EXISTS resolved_at timestamptz,
    ADD COLUMN IF NOT EXISTS resolved_by text;
