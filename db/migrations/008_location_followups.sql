-- Location follow-up answers (enhancements design D8). The citizen's original
-- raw_location_mention is never modified; the answer is stored beside it.
CREATE TABLE IF NOT EXISTS location_followups (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    citizen_request_id uuid NOT NULL REFERENCES citizen_requests(id),
    answer             text NOT NULL,
    resolved           boolean NOT NULL,
    resolution_reason  text,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS location_followups_request_idx
    ON location_followups (citizen_request_id);
