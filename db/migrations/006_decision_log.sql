-- Hash-chained decision log (enhancements design D14). Every human decision
-- (Publish Gate, verification review, trust-flag review, mark resolved) is
-- appended in the same transaction as the decision itself. Each entry's hash
-- covers its content and the previous entry's hash, so any later edit or
-- deletion is detectable by GET /api/audit/verify.
CREATE TABLE IF NOT EXISTS decision_log (
    seq         bigserial PRIMARY KEY,
    kind        text NOT NULL,
    subject_id  text NOT NULL,
    decision    text NOT NULL,
    reviewer    text NOT NULL,
    decided_at  timestamptz NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}',
    prev_hash   text NOT NULL,
    hash        text NOT NULL UNIQUE
);

-- Append-only in normal operation (defence in depth; the chain is the proof).
CREATE OR REPLACE FUNCTION decision_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'decision_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS decision_log_append_only ON decision_log;
CREATE TRIGGER decision_log_append_only
    BEFORE UPDATE OR DELETE ON decision_log
    FOR EACH ROW EXECUTE FUNCTION decision_log_append_only();
