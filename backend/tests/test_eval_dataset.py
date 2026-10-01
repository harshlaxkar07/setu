"""Evaluation set coverage (enhancements task 9.1)."""
from collections import Counter

from app.constants import CATEGORIES, EQUITY_CATEGORIES
from eval import dataset


def test_dataset_meets_coverage_requirements():
    items = dataset.load()
    assert len(items) >= 50
    assert len({i["id"] for i in items}) == len(items)
    langs = Counter(i["language"] for i in items)
    assert set(langs) == set(dataset.LANGUAGES) and min(langs.values()) >= 10
    cats = {i["category"] for i in items}
    assert set(EQUITY_CATEGORIES) | {"sanitation"} <= cats  # every seeded category
    assert cats <= set(CATEGORIES)
    assert {i["urgency"] for i in items} <= {"high", "medium", "low"}
    # informal location phrasing and unlocatable messages are both present
    assert any(i["location"] is None for i in items)
    assert any(w in i["text"] for i in items for w in ("गाँव", "gaon", "near", "के पास", "गावात"))
    for i in items:
        if i["cluster"] not in (None, "new"):
            region, cat = i["cluster"].split("/")
            assert region == i["location"] and cat == i["category"]
