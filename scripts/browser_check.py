"""Read-only browser regression for both running Setu UIs.

Install Playwright separately from the backend: pip install playwright
Then: playwright install chromium; python scripts/browser_check.py
Use --chrome to use an installed Google Chrome instead.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

TABS = ("Priorities", "Publish Gate", "Trust & trends", "Equity", "Planner",
        "Verification", "Audit")


def check(backend: str, dashboard: str, output: Path, chrome: bool = False) -> dict:
    errors, checks = [], []
    output.mkdir(parents=True, exist_ok=True)

    def watch(page, label):
        page.on("pageerror", lambda e: errors.append(f"{label}: {e}"))
        page.on("console", lambda m: errors.append(f"{label}: {m.text}")
                if m.type == "error" else None)
        page.on("response", lambda r: errors.append(f"{label}: HTTP {r.status} {r.url}")
                if r.status >= 400 else None)

    with sync_playwright() as p:
        browser = p.chromium.launch(**({"channel": "chrome"} if chrome else {}))
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            watch(page, "dashboard")
            page.goto(dashboard)
            page.get_by_role("tab", name="Priorities", exact=True).wait_for()
            for tab in TABS:
                page.get_by_role("tab", name=tab, exact=True).click()
                page.wait_for_timeout(750)
                if page.locator('[data-testid="stException"]').count():
                    errors.append(f"dashboard: exception in {tab}")
                checks.append(f"dashboard tab: {tab}")
            page.screenshot(path=str(output / "dashboard.png"), full_page=True)
            for category in ("Healthcare", "Roads", "Sanitation", "Water", "All categories"):
                page.get_by_label("Category", exact=True).click()
                page.get_by_role("option", name=category, exact=True).click()
                page.wait_for_timeout(750)
                if page.locator('[data-testid="stException"]').count():
                    errors.append(f"dashboard: exception for {category}")
                checks.append(f"category filter: {category}")
            for width, assisted in ((390, False), (1440, False), (390, True)):
                label = f"citizen-{width}-{'assisted' if assisted else 'standard'}"
                citizen = browser.new_page(viewport={"width": width, "height": 900})
                watch(citizen, label)
                url = f"{backend.rstrip('/')}/citizen/" + ("?mode=assisted" if assisted else "")
                citizen.goto(url)
                for language in ("hi", "en", "mr"):
                    citizen.locator(f'.lang-btn[data-lang="{language}"]').click()
                    if citizen.locator("html").get_attribute("lang") != language:
                        errors.append(f"{label}: language did not switch to {language}")
                citizen.reload()
                citizen.locator('.lang-btn[data-lang="mr"]').wait_for()
                if citizen.locator("html").get_attribute("lang") != "mr":
                    errors.append(f"{label}: Marathi choice did not persist")
                if citizen.evaluate("document.documentElement.scrollWidth > innerWidth"):
                    errors.append(f"{label}: horizontal overflow")
                count = citizen.locator("input").count()
                if count != (3 if assisted else 1):
                    errors.append(f"{label}: unexpected input count {count}")
                citizen.screenshot(path=str(output / f"{label}.png"), full_page=True)
                checks.append(label + ": languages, reload, inputs, viewport")
                citizen.close()
        finally:
            browser.close()
    report = {"passed": not errors, "checks": checks, "errors": errors}
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--dashboard", default="http://localhost:8501")
    ap.add_argument("--output", type=Path, default=Path("/tmp/setu-browser-check"))
    ap.add_argument("--chrome", action="store_true")
    args = ap.parse_args()
    result = check(args.backend, args.dashboard, args.output, args.chrome)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
