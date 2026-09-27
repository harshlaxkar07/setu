"""HTML renderers for the policymaker surface (files/06 component inventory).

Pure functions: data in, token-styled HTML out (rendered via st.markdown with
unsafe_allow_html). All citizen/AI text is escaped; every trust or priority
signal pairs color with a text label and an icon glyph, so a grayscale
rendering still distinguishes every state (task 6.9).
"""
import html
from typing import Any

# Glyphs make tiers/states distinguishable without color (grayscale rule).
TIER_GLYPHS = {"High": "▲", "Medium": "◆", "Low": "▼"}
CONFIDENCE_GLYPHS = {"high": "✓", "medium": "~", "flagged": "⚑"}


def esc(value: Any) -> str:
    return html.escape(str(value)) if value is not None else ""


def num(value: Any) -> str:
    """A numeric value in IBM Plex Mono with tabular figures (files/07)."""
    return f'<span class="num">{esc(value)}</span>'


def fmt_int(value: int | None) -> str:
    return f"{value:,}" if value is not None else "—"


def hindi(text: str) -> str:
    """Hindi/Devanagari content in Noto Sans Devanagari (never Latin fallback)."""
    return f'<span class="hindi">{esc(text)}</span>'


def header_bar() -> str:
    """The one consistent header bar (files/07 §Streamlit, item 5)."""
    return (
        '<div class="setu-header">'
        '<span class="mark">Setu</span>'
        '<span>Policymaker dashboard — demand evidence &amp; publish gate</span>'
        '<span class="register">POLICYMAKER REGISTER</span>'
        "</div>"
    )


def tier_badge(tier: str | None) -> str:
    """Priority tier: color + glyph + text label — never color-only."""
    if tier is None:
        return '<span class="badge badge-confidence">— not scored yet</span>'
    glyph = TIER_GLYPHS.get(tier, "")
    return f'<span class="badge badge-tier-{tier.lower()}">{glyph} {esc(tier)} priority</span>'


def confidence_badge(level: str, reason: str | None) -> str:
    """ConfidenceLevel with its stated reason when below high (spec rule)."""
    glyph = CONFIDENCE_GLYPHS.get(level, "•")
    label = f"{glyph} confidence: {esc(level)}"
    if level != "high" and reason:
        label += f" — {esc(reason)}"
    return f'<span class="badge badge-confidence">{label}</span>'


def ai_marker() -> str:
    """The AI-drafted provenance marker (`ai-provenance` token). Applied ONLY
    to AI-generated fields — never decoratively (spec requirement)."""
    return '<span class="badge badge-ai">✦ AI-drafted</span>'


def pending_badge() -> str:
    """Amber 'Awaiting review' badge, `pending-gate` token (spec requirement)."""
    return '<span class="badge badge-pending">⏳ Awaiting review</span>'


def status_badge(status: str) -> str:
    mapping = {
        "active": ('badge-confidence', '● active'),
        "published": ('badge-published', '✓ published'),
        "resolved_unverified": ('badge-resolved-unverified', '◑ resolved — unverified'),
        "resolved_verified": ('badge-resolved-verified', '✓✓ resolved — verified'),
    }
    cls, label = mapping.get(status, ("badge-confidence", status))
    return f'<span class="badge {cls}">{esc(label)}</span>'


def factor_row(name: str, value_html: str) -> str:
    """One labeled name–value row — indicators are never tooltip-only."""
    return (
        f'<div class="factor-row"><span class="factor-name">{esc(name)}</span>'
        f'<span class="factor-value">{value_html}</span></div>'
    )


def indicator_rows(indicators: list[dict]) -> str:
    """Every PriorityIndicator as a labeled row (spec: labeled rows)."""
    rows = []
    for ind in indicators:
        # value_text already carries the human-readable value with its unit;
        # the bare numeric renders only when no text exists (review finding —
        # avoids "… ≈ 31.4 km away · 31,393.4").
        if ind.get("value_text"):
            value = esc(ind["value_text"])
        elif ind.get("value_numeric") is not None:
            value = num(f"{ind['value_numeric']:,g}")
        else:
            value = "—"
        rows.append(factor_row(ind["name"], value))
    return "".join(rows)


def score_breakdown(score: float, components: dict) -> str:
    """The composite decomposed: 0.5×gap + 0.3×investment + 0.2×volume —
    a PriorityScore is never a bare figure (spec: no unexplained numbers)."""
    w = components["weights"]
    parts = [
        ("infrastructure gap", w["gap"], components["gap_norm"]),
        ("investment deficit", w["investment_deficit"],
         components["investment_deficit_norm"]),
        ("complaint volume", w["volume"], components["volume_norm"]),
    ]
    rows = []
    for label, weight, norm in parts:
        rows.append(factor_row(
            f"{label} (weight {weight})",
            num(f"{weight} × {norm:.3f} = {weight * norm:.3f}"),
        ))
    rows.append(
        f'<div class="factor-row breakdown-total">'
        f'<span class="factor-name">PriorityScore (min-max normalized within category)</span>'
        f'<span class="factor-value">{num(f"{score:.3f}")}</span></div>'
    )
    return f'<div class="breakdown">{"".join(rows)}</div>'


def cluster_card(cluster: dict, selected: bool) -> str:
    """cluster_card: member count, category, summary, score + tier label."""
    score = cluster.get("score")
    score_html = (
        f'{num(f"{score:.3f}")} {tier_badge(cluster.get("tier"))}'
        if score is not None else tier_badge(None)
    )
    summary = esc(cluster.get("representative_summary") or "")
    return (
        f'<div class="setu-card{" selected" if selected else ""}">'
        f'<div class="card-title">{summary} {ai_marker()}</div>'
        f'<div class="card-meta">category: {esc(cluster["category"])} · '
        f'members: {num(fmt_int(cluster["member_count"]))} · '
        f'{status_badge(cluster["status"])}</div>'
        f'<div style="margin-top:8px">PriorityScore: {score_html}</div>'
        f'<div style="margin-top:8px">{confidence_badge(cluster["confidence"], cluster.get("confidence_reason"))}</div>'
        "</div>"
    )


def citizen_quote(raw_text: str, language: str | None) -> str:
    """Raw citizen content: Devanagari face, NO AI marker (provenance rule)."""
    chip = f' <span class="small-note">({esc(language)})</span>' if language else ""
    return f'<div class="citizen-quote">{hindi(raw_text)}{chip}</div>'


def gap_comparison_panel(region_a: dict, region_b: dict,
                         a_detail: dict, b_detail: dict) -> str:
    """gap_comparison_panel: Region A vs B side by side, proving the equity
    contrast — B outranks A despite ~25× lower complaint volume."""
    ranked = sorted(
        [region_a, region_b],
        key=lambda c: c.get("score") or 0.0, reverse=True,
    )
    ranks = {c["id"]: i + 1 for i, c in enumerate(ranked)}

    def col(cluster: dict, detail: dict) -> str:
        gap = cluster.get("gap") or {}
        rank = ranks[cluster["id"]]
        score = cluster.get("score") or 0.0
        rows = [
            factor_row("complaint volume",
                       num(fmt_int(cluster["member_count"])) + " requests"),
            factor_row("InfrastructureGapScore",
                       num(f"{gap.get('gap_value', 0):,.0f}")
                       + f" (population {num(fmt_int(gap.get('population')))} ÷ "
                         f"facility coverage {num(gap.get('facility_count', '—'))})"),
            factor_row("facilities within service radius",
                       num(gap.get("facility_count", "—"))),
            factor_row("historical investment", esc(_investment_of(detail))),
            factor_row("PriorityScore rank",
                       num(f"#{rank}") + " · score " + num(f"{score:.3f}")),
        ]
        callouts = []
        if gap.get("facility_count") == 0:
            callouts.append('<div class="callout">0 facilities within service radius</div>')
        if _investment_of(detail) == "low":
            callouts.append('<div class="callout">low historical investment</div>')
        under = _indicator(detail, "possible under-representation signal")
        if under:
            callouts.append(
                f'<div class="callout info">Under-representation signal: '
                f"{esc(under.get('value_text'))}</div>"
            )
        winner = ' winner' if rank == 1 else ''
        name = esc(cluster.get("representative_summary") or "")
        return (
            f'<div class="gap-col{winner}">'
            f'<div class="gap-rank">Rank {num(f"#{rank}")} — {tier_badge(cluster.get("tier"))}</div>'
            f'<div class="card-title">{name} {ai_marker()}</div>'
            f'{"".join(rows)}{"".join(callouts)}</div>'
        )

    return f'<div class="gap-panel">{col(region_a, a_detail)}{col(region_b, b_detail)}</div>'


def _indicator(detail: dict, name: str) -> dict | None:
    for ind in detail.get("indicators", []):
        if ind["name"] == name:
            return ind
    return None


def _investment_of(detail: dict) -> str:
    ind = _indicator(detail, "historical investment")
    return (ind or {}).get("value_text") or "—"


def recommendation_citations(citations: list[dict]) -> str:
    rows = [factor_row(c.get("name", "indicator"), esc(c.get("value", "")))
            for c in citations]
    return "".join(rows)


def trace_stage_row(entry: dict) -> str:
    """One run-trace stage: stage, input, output, duration, error, alternatives."""
    bits = [
        f'<div class="card-title">{esc(entry.get("stage", "?"))}'
        + (f' — {num(str(entry.get("duration_ms")) + " ms")}'
           if entry.get("duration_ms") is not None else "")
        + "</div>"
    ]
    for key, label in (("input_ref", "input"), ("output_ref", "output")):
        if entry.get(key):
            bits.append(factor_row(label, num(entry[key])))
    if entry.get("error"):
        bits.append(f'<div class="callout">error: {esc(entry["error"])}</div>')
    if entry.get("retried"):
        bits.append('<div class="callout info">retried once</div>')
    if entry.get("alternatives"):
        bits.append(factor_row("alternatives considered",
                               esc(entry["alternatives"])))
    return f'<div class="setu-card">{"".join(bits)}</div>'
