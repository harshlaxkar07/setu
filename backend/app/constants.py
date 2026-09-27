"""Setu constants — deliberately literal, not configuration (design D1/Non-Goals).

The scoring weights are code constants BY CONSTRUCTION: complaint volume's
weight is capped below the infrastructure-gap weight so volume can never
override gap (governing principle 2). Do not make these runtime-configurable.
"""

# --- Scoring (design D1, locked) -------------------------------------------
WEIGHT_GAP = 0.5
WEIGHT_INVESTMENT_DEFICIT = 0.3
WEIGHT_VOLUME = 0.2
assert WEIGHT_VOLUME < WEIGHT_GAP, "volume weight must stay below gap weight"

# Normalized value used when every cluster in a category shares the same raw
# indicator value (degenerate min-max normalization — never NaN).
DEGENERATE_NORM = 0.5

# Investment label → deficit value (lower investment = higher deficit).
INVESTMENT_DEFICIT = {"low": 1.0, "medium": 0.5, "high": 0.0}

# --- Geospatial -------------------------------------------------------------
# Service radius: facilities within this distance of a cluster centroid count
# toward its coverage (Fuse stage and seed facility placement use the same value).
SERVICE_RADIUS_M = 2000

# Cluster stage: geographic proximity threshold for joining an existing cluster.
CLUSTER_PROXIMITY_M = 3000

# Cluster stage: minimum cosine similarity to join an existing cluster.
CLUSTER_SIMILARITY_THRESHOLD = 0.60

# --- Models (design D5/D9, locked) ------------------------------------------
# D5 originally locked gemini-2.5-flash; the live API retired it for new users
# (404, 2026-09-26) and names gemini-3.8-flash as the successor.
GEMINI_MODEL = "gemini-3.8-flash"
# D5 originally locked text-embedding-004, but Google retired it (404 from the
# live API, 2026-09-26); gemini-embedding-001 at output_dimensionality=768 is
# the drop-in successor — same vector(768) column, same cosine semantics.
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM = 768
WHISPER_MODEL = "small"

# --- Domain -----------------------------------------------------------------
CATEGORY_WATER = "water_infrastructure"
