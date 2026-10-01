-- Baseline marker: proves the runner on an existing volume. Later migrations
-- add the enhancement tables (trust flags, decision log, reviewer data, ...).
COMMENT ON TABLE demand_clusters IS
  'Geographic/categorical aggregate of citizen requests (see files/04).';
