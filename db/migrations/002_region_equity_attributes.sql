-- Region attributes for equity analysis (enhancements design D3/D5).
-- vulnerability_index / connectivity_index: 0..1, synthetic but proportioned
-- (higher vulnerability = more deprived; higher connectivity = better digital
-- access). They are CONTEXT indicators: the composite PriorityScore formula
-- is unchanged; they drive the silent-regions analysis and are displayed.
ALTER TABLE region_profiles
    ADD COLUMN IF NOT EXISTS centroid           geometry(Point, 4326),
    ADD COLUMN IF NOT EXISTS settlement_type    text,
    ADD COLUMN IF NOT EXISTS vulnerability_index numeric,
    ADD COLUMN IF NOT EXISTS connectivity_index  numeric;

UPDATE region_profiles SET centroid = ST_Centroid(boundary)
 WHERE centroid IS NULL AND boundary IS NOT NULL;

-- Facility names let Locate resolve landmark mentions ("near Paud PHC").
ALTER TABLE infrastructure_facilities
    ADD COLUMN IF NOT EXISTS name text;

-- Dataset provenance: synthetic seed vs imported real-world data (design D6).
ALTER TABLE infrastructure_datasets
    ADD COLUMN IF NOT EXISTS source      text NOT NULL DEFAULT 'synthetic',
    ADD COLUMN IF NOT EXISTS imported_at timestamptz;
