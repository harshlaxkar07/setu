-- Assisted field-worker channel (enhancements design D11). A field worker
-- files a report on behalf of residents: the village and number of
-- households are recorded — never any resident's name or phone. The client
-- sends an idempotency key per queued report so an offline queue that
-- flushes twice still creates each request exactly once.
ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'assisted';

ALTER TABLE citizen_requests
    ADD COLUMN IF NOT EXISTS assisted_village       text,
    ADD COLUMN IF NOT EXISTS households_represented integer
        CHECK (households_represented IS NULL OR households_represented > 0),
    ADD COLUMN IF NOT EXISTS idempotency_key        text;

CREATE UNIQUE INDEX IF NOT EXISTS citizen_requests_idempotency_idx
    ON citizen_requests (idempotency_key) WHERE idempotency_key IS NOT NULL;
