-- Alternate names (Devanagari, Marathi, common spellings) so Locate can match
-- informal mentions against known regions offline (enhancements design D8).
ALTER TABLE region_profiles
    ADD COLUMN IF NOT EXISTS aliases text[] NOT NULL DEFAULT '{}';
