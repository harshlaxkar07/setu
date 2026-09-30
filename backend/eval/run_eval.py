"""Accuracy report over the labelled evaluation set (enhancements task 9.2).

    docker compose exec backend python -m eval.run_eval            # live
    docker compose exec backend python -m eval.run_eval --replay   # offline

Each item runs through the REAL Understand and Locate stages (model, geocoder,
embeddings — or their recorded fixtures with --replay), then the cluster it
would join is predicted with the Cluster stage's own candidate query,
read-only, so evaluation never creates clusters. Scored per item:

  category  Understand's category == label
  urgency   Understand's urgency == label (a human judgement; report it as such)
  location  resolved point lies in the labelled region (or, for a message that
            names no place, the request is correctly left unlocated)
  cluster   predicted seeded cluster (or "new") == label

Writes eval/report.json and prints a table with per-language breakdowns. All
rows the run creates (submitter prefix "eval-") are removed afterwards.
A live run records fixtures, so a following --replay run is reproducible.
"""
import argparse
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from eval import dataset  # noqa: E402

REPORT = Path(__file__).parent / "report.json"
METRICS = ("category", "urgency", "location", "cluster")


def _cluster_label(conn, cluster_id: str) -> str:
    row = conn.execute(
        """SELECT rp.name, dc.category FROM demand_clusters dc
           JOIN region_profiles rp ON ST_Contains(rp.boundary, dc.centroid)
           WHERE dc.id = %s ORDER BY rp.name LIMIT 1""", (cluster_id,)).fetchone()
    return f"{row[0]}/{row[1]}" if row else f"unlabelled:{cluster_id[:8]}"


def evaluate_item(conn, item: dict, prefix: str, *, understand_caller=None,
                  transport=None, embedder=None) -> dict:
    from app.stages import cluster, locate, understand

    out = {"id": item["id"], "language": item["language"], "expected": {
        k: item[k] for k in ("category", "urgency", "location", "cluster")}}
    (cr,) = conn.execute(
        """INSERT INTO citizen_requests (channel, raw_text, submitter_ref)
           VALUES ('text', %s, %s) RETURNING id""",
        (item["text"], f"{prefix}{item['id']}")).fetchone()
    conn.commit()
    try:
        sr = understand.run(conn, str(cr), _caller=understand_caller)
    except Exception as exc:
        conn.rollback()
        out["error"] = f"understand failed: {exc}"[:200]
        out["correct"] = {m: False for m in METRICS}
        return out
    category, urgency, language = conn.execute(
        "SELECT category, urgency::text, detected_language FROM structured_requests WHERE id=%s",
        (sr,)).fetchone()
    gr = locate.run(conn, sr, _transport=transport, _embedder=embedder)
    has_geom, confidence, reason = conn.execute(
        "SELECT geom IS NOT NULL, confidence::text, confidence_reason "
        "FROM geocoded_requests WHERE id=%s", (gr,)).fetchone()
    region = None
    if has_geom:
        row = conn.execute(
            """SELECT rp.name FROM region_profiles rp, geocoded_requests gr
               WHERE gr.id = %s AND ST_Contains(rp.boundary, gr.geom)
               ORDER BY ST_Distance(rp.centroid, gr.geom) LIMIT 1""", (gr,)).fetchone()
        region = row[0] if row else "outside seeded regions"
    predicted_cluster = None
    if has_geom:
        candidates = cluster._candidates(conn, gr, category)
        predicted_cluster = _cluster_label(conn, candidates[0][0]) if candidates else "new"

    exp = item
    out["predicted"] = {"category": category, "urgency": urgency, "location": region,
                        "cluster": predicted_cluster, "detected_language": language,
                        "location_confidence": confidence, "location_reason": reason}
    out["correct"] = {
        "category": category == exp["category"],
        "urgency": urgency == exp["urgency"],
        "location": (region == exp["location"]) if exp["location"] else not has_geom,
        "cluster": predicted_cluster == exp["cluster"],
    }
    return out


def cleanup(conn, prefix: str) -> None:
    ids = "SELECT id FROM citizen_requests WHERE submitter_ref LIKE %s"
    pat = prefix + "%"
    conn.rollback()
    conn.execute(f"""DELETE FROM geocoded_requests WHERE structured_request_id IN
                     (SELECT id FROM structured_requests WHERE citizen_request_id IN ({ids}))""",
                 (pat,))
    conn.execute(f"DELETE FROM structured_requests WHERE citizen_request_id IN ({ids})", (pat,))
    conn.execute(f"DELETE FROM run_traces WHERE citizen_request_id IN ({ids})", (pat,))
    conn.execute("ALTER TABLE citizen_requests DISABLE TRIGGER citizen_requests_immutable")
    conn.execute("DELETE FROM citizen_requests WHERE submitter_ref LIKE %s", (pat,))
    conn.execute("ALTER TABLE citizen_requests ENABLE TRIGGER citizen_requests_immutable")
    conn.commit()


def summarise(results: list[dict]) -> dict:
    def rate(rows, metric):
        return round(sum(r["correct"][metric] for r in rows) / len(rows), 3) if rows else None

    by_lang = defaultdict(list)
    for r in results:
        by_lang[r["language"]].append(r)
    return {
        "items": len(results),
        "errors": sum(1 for r in results if "error" in r),
        "overall": {m: rate(results, m) for m in METRICS},
        "by_language": {lang: {"items": len(rows), **{m: rate(rows, m) for m in METRICS}}
                        for lang, rows in sorted(by_lang.items())},
    }


def run(*, replay: bool, limit: int | None = None, report_path: Path = REPORT,
        **stage_overrides) -> dict:
    previous_replay = os.environ.get("DEMO_REPLAY")
    if replay:
        os.environ["DEMO_REPLAY"] = "1"
    try:
        return _run(replay=replay, limit=limit, report_path=report_path,
                    **stage_overrides)
    finally:  # never leak replay mode into the rest of the process
        if previous_replay is None:
            os.environ.pop("DEMO_REPLAY", None)
        else:
            os.environ["DEMO_REPLAY"] = previous_replay


def _run(*, replay: bool, limit: int | None, report_path: Path,
         **stage_overrides) -> dict:
    from app import llm
    items = dataset.load()[:limit] if limit else dataset.load()
    prefix = f"eval-{uuid.uuid4().hex[:8]}-"
    start = time.monotonic()
    results = []
    with psycopg.connect(db.DATABASE_URL) as conn:
        try:
            for item in items:
                results.append(evaluate_item(conn, item, prefix, **stage_overrides))
        finally:
            cleanup(conn, prefix)
    provider = llm.get_provider()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "replay (recorded fixtures)" if replay else "live",
        "provider": f"{provider.name}/{provider.model}",
        "seconds": round(time.monotonic() - start, 1),
        "summary": summarise(results),
        "results": results,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def print_table(report: dict) -> None:
    s = report["summary"]
    print(f"\nSetu evaluation — {s['items']} items, {report['mode']}, "
          f"{report['provider']}, {report['seconds']} s, errors: {s['errors']}")
    print(f"{'':12}{'category':>10}{'urgency':>10}{'location':>10}{'cluster':>10}")
    rows = [("overall", s["overall"])] + [
        (f"{k} ({v['items']})", v) for k, v in s["by_language"].items()]
    for name, m in rows:
        print(f"{name:12}" + "".join(f"{(m[k] or 0) * 100:>9.0f}%" for k in METRICS))
    print(f"\nFull per-item results: {REPORT}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Setu accuracy report")
    ap.add_argument("--replay", action="store_true",
                    help="use recorded fixtures (reproducible, offline)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    print_table(run(replay=args.replay, limit=args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
