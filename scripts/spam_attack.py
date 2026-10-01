#!/usr/bin/env python3
"""Live demo: a coordinated spam attack against one cluster.

Submits COUNT near-identical complaints through the PUBLIC intake API — the
same door citizens use, no database access — so the audience can watch Setu's
Trust stage flag the burst (with reasons) while the cluster's PriorityScore
barely moves and nothing is deleted.

    python3 scripts/spam_attack.py                    # 300 requests at Kothrud
    python3 scripts/spam_attack.py --count 50 --place Hadapsar
    python3 scripts/spam_attack.py --single-source    # one "user" flooding

Tip: run the backend with DEMO_REPLAY=1 so identical texts replay one recorded
Understand response instead of spending the model quota on each copy.
Standard library only: runs from any machine with Python 3.
"""
import argparse
import json
import sys
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

TEMPLATE = "{place} में पीने का पानी कई दिनों से नहीं आ रहा, तुरंत टैंकर भेजो"


def _http_post(base_url: str, path: str, body: dict) -> int:
    req = urllib.request.Request(
        base_url.rstrip("/") + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status


def attack(*, count: int, place: str, single_source: bool = False,
           source_prefix: str = "spam-demo-", workers: int = 8,
           post=None, base_url: str = "http://localhost:8000") -> dict:
    """Submit `count` copies; returns {"accepted": n, "failed": n, "seconds": s}.
    `post(path, body) -> status` is injectable (tests use the ASGI client)."""
    post = post or (lambda path, body: _http_post(base_url, path, body))
    one_source = f"{source_prefix}{uuid.uuid4()}"
    text = TEMPLATE.format(place=place)

    def submit(i: int) -> bool:
        cid = one_source if single_source else f"{source_prefix}{uuid.uuid4()}"
        # Trailing punctuation varies, as copy-paste campaigns do; the Trust
        # stage normalises it away.
        body = {"text": text + ("!" * (i % 3)), "conversation_id": cid}
        try:
            return post("/api/requests/text", body) == 201
        except Exception:
            return False

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(submit, range(count)))
    accepted = sum(results)
    return {"accepted": accepted, "failed": count - accepted,
            "seconds": round(time.monotonic() - start, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", type=int, default=300)
    ap.add_argument("--place", default="Kothrud")
    ap.add_argument("--single-source", action="store_true",
                    help="all copies from one pseudonymous id (repeat-source rule)")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    print(f"Submitting {args.count} near-identical complaints about {args.place} "
          f"to {args.base_url} ...")
    out = attack(count=args.count, place=args.place, single_source=args.single_source,
                 workers=args.workers, base_url=args.base_url)
    print(f"Accepted {out['accepted']}, failed {out['failed']} in {out['seconds']} s.")
    print("Watch the dashboard: trust flags appear as the pipeline processes them;"
          " counted volume stays put.")
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
