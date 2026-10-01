"""Import real facilities from OpenStreetMap into a labelled dataset.

    docker compose exec backend python /app/seed/import_osm.py healthcare
    docker compose exec backend python /app/seed/import_osm.py water_infrastructure \
        --bbox 18.2,73.4,18.7,74.0

The synthetic seed stays the scoring default. To score against the imported
data instead, set SCORING_DATASET=openstreetmap in .env and restart the
backend (then re-run seed.py's Fuse/Score pass or submit new requests).
"""
import argparse
import os
import sys

import psycopg

sys.path.insert(0, "/app")
from app.osm_import import (  # noqa: E402
    CATEGORY_TAGS,
    PUNE_DISTRICT_BBOX,
    ImportFailed,
    import_category,
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5434/setu")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("category", choices=sorted(CATEGORY_TAGS))
    parser.add_argument("--bbox", default=",".join(map(str, PUNE_DISTRICT_BBOX)),
                        help="south,west,north,east (default: Pune district)")
    args = parser.parse_args()
    bbox = tuple(float(v) for v in args.bbox.split(","))
    if len(bbox) != 4:
        parser.error("--bbox needs four comma-separated numbers")
    print(f"Querying OpenStreetMap for {args.category} in {bbox} ...")
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            result = import_category(conn, args.category, bbox)
    except ImportFailed as exc:
        print(f"Import failed, nothing written: {exc}")
        return 1
    print(f"Imported {result['facilities']} facilities as dataset {result['dataset_id']} "
          "(source: OpenStreetMap). Scoring still uses the synthetic seed unless "
          "SCORING_DATASET=openstreetmap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
