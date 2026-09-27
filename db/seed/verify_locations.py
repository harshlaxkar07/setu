#!/usr/bin/env python3
"""Pre-verify every demo location string against Nominatim (design D7).

Resolves candidate Region A (urban Pune ward) and Region B (rural Pune village)
strings, picks the first candidate of each that geocodes inside Pune district,
verifies the informal demo mentions built from them, and writes the final
selection to db/seed/locations.json for the seed script.

Run before seeding and again shortly before the demo (task 9.4) — no live
geocoding surprise. Respects Nominatim's 1 req/s limit. Stdlib only.

Exit 0: every string resolved (coordinates printed). Exit 1: failures listed.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "setu-demo-verification/0.1 (hackathon prototype)"

# Pune district rough bounding box (lat, lon).
PUNE_BBOX = (17.9, 73.2, 19.4, 75.2)

# Candidates, most-preferred first. Region A: real urban Pune ward.
# Region B: real rural village in Pune district.
CANDIDATES_A = [
    "Kothrud, Pune, Maharashtra, India",
    "Aundh, Pune, Maharashtra, India",
    "Hadapsar, Pune, Maharashtra, India",
]
CANDIDATES_B = [
    "Velhe, Pune, Maharashtra, India",
    "Kondhur, Mulshi, Pune, Maharashtra, India",
    "Ghera Sinhgad, Pune, Maharashtra, India",
]

_last_call = 0.0


def geocode(query: str):
    """One Nominatim lookup, throttled to <=1 req/s. Returns (lat, lon) or None."""
    global _last_call
    wait = 1.1 - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    url = f"{NOMINATIM}?{urllib.parse.urlencode({'q': query, 'format': 'jsonv2', 'limit': 3})}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    _last_call = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            results = json.load(resp)
    except Exception as exc:  # network / HTTP failure is a reportable outcome
        print(f"  ERROR querying Nominatim for {query!r}: {exc}")
        return None
    for r in results:
        lat, lon = float(r["lat"]), float(r["lon"])
        if PUNE_BBOX[0] <= lat <= PUNE_BBOX[2] and PUNE_BBOX[1] <= lon <= PUNE_BBOX[3]:
            return lat, lon, r.get("display_name", "")
    return None


def pick(label: str, candidates: list[str]):
    for cand in candidates:
        hit = geocode(cand)
        if hit:
            print(f"[{label}] {cand}  ->  ({hit[0]:.5f}, {hit[1]:.5f})  {hit[2]}")
            return cand, hit
        print(f"[{label}] {cand}  ->  no Pune-district resolution, trying next")
    return None, None


def main() -> int:
    failures = []

    region_a, hit_a = pick("Region A / urban ward", CANDIDATES_A)
    region_b, hit_b = pick("Region B / rural village", CANDIDATES_B)
    if not region_a:
        failures.append("no Region A candidate resolved")
    if not region_b:
        failures.append("no Region B candidate resolved")

    informal = []
    if region_a and region_b:
        # The informal mentions the demo rehearses (geospatial spec: landmark
        # phrase resolves rather than defaulting). The Locate stage composites
        # mention + region context the same way.
        informal = [
            f"government school, {region_a}",
            region_a.split(",")[0] + ", Pune",          # bare ward mention
            region_b.split(",")[0] + " village, Pune district",
        ]
        for s in informal:
            hit = geocode(s)
            if hit:
                print(f"[informal] {s}  ->  ({hit[0]:.5f}, {hit[1]:.5f})")
            else:
                failures.append(f"informal string failed: {s!r}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1

    out = Path(__file__).parent / "locations.json"
    out.write_text(json.dumps({
        "region_a": {"query": region_a, "lat": hit_a[0], "lon": hit_a[1]},
        "region_b": {"query": region_b, "lat": hit_b[0], "lon": hit_b[1]},
        "informal_mentions": informal,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2, ensure_ascii=False))
    print(f"\nAll strings verified. Selection written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
