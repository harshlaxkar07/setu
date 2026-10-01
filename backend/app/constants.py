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

# --- Trust & anti-manipulation (enhancements design D2) --------------------
# Literal constants like the scoring weights: tuned on the seed + demo script.
# Duplicate burst: a request is flagged when at least this many OTHER requests
# in the same cluster, within the window before it, are near-identical to it
# (same normalised text, or embedding cosine >= TRUST_SIMILARITY).
TRUST_BURST_WINDOW_S = 600
TRUST_BURST_MIN_MATCHES = 5
TRUST_SIMILARITY = 0.97
# Repeat source: one pseudonymous conversation id joining one cluster more
# than this many times within the window.
TRUST_REPEAT_WINDOW_S = 3600
TRUST_REPEAT_LIMIT = 3
# Cluster spike: arrivals in the window vs the cluster's own baseline rate.
TRUST_SPIKE_WINDOW_S = 3600
TRUST_SPIKE_MIN_ARRIVALS = 20
TRUST_SPIKE_MULTIPLE = 10.0
TRUST_BASELINE_DAYS = 30

# --- Equity insights (enhancements design D3) -------------------------------
# A region is "silent" for a category when its infrastructure gap is at or
# above this quantile of the category's regions AND it has at most this many
# citizen requests in that category: high need, little or no digital voice.
SILENT_GAP_QUANTILE = 0.5
SILENT_MAX_COMPLAINTS = 5

# --- Impact measurement (enhancements design D9) ----------------------------
# Complaint arrivals are compared over this many days before vs after the
# cluster was marked resolved.
IMPACT_WINDOW_DAYS = 30

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
CATEGORY_ROAD = "road_infrastructure"
CATEGORY_HEALTH = "healthcare"
CATEGORY_OTHER = "other"
CATEGORY_SANITATION = "sanitation"

# Categories Understand may assign (enhancements design D5). Anything else the
# model returns is normalised to "other" — never silently invented.
CATEGORIES = (
    CATEGORY_WATER,
    CATEGORY_ROAD,
    CATEGORY_HEALTH,
    "electricity",
    "sanitation",
    "education",
    "transportation",
    "digital_connectivity",
    CATEGORY_OTHER,
)

# Categories with facility registers the equity analysis runs over (D3).
EQUITY_CATEGORIES = (CATEGORY_WATER, CATEGORY_HEALTH, CATEGORY_ROAD)
