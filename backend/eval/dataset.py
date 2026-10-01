"""Labelled evaluation set loader (enhancements task 9.1, design D17).

Each line of dataset.jsonl:
  id        stable item id
  language  hi | hinglish | en | mr  (the message's actual language)
  text      the citizen message, verbatim
  category  expected Understand category
  urgency   expected urgency (high | medium | low) — a human judgement
  location  expected region name, or null when the message names no place
  cluster   "<Region>/<category>" for a seeded cluster it should join,
            "new" when it should found a new cluster, null when unlocatable
"""
import json
from pathlib import Path

PATH = Path(__file__).parent / "dataset.jsonl"
LANGUAGES = ("hi", "hinglish", "en", "mr")


def load(path: Path = PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
