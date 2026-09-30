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


def summary_strip(items: list[tuple[str, int, str | None]]) -> str:
    """At-a-glance counts under the header: (label, value, accent) tiles.
    Accent ("high" / "pending") marks tiles that need attention."""
    tiles = []
    for label, value, accent in items:
        cls = f" kpi-{accent}" if accent else ""
        tiles.append(
            f'<div class="kpi{cls}"><div class="kpi-value">{num(value)}</div>'
            f'<div class="kpi-label">{esc(label)}</div></div>'
        )
    return f'<div class="kpi-strip">{"".join(tiles)}</div>'


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
        f'<div class="card-meta">category: {esc(category_label(cluster["category"]))} · '
        f'{volume_line(cluster)} · {status_badge(cluster["status"])} '
        f'{trust_badge(cluster)}</div>'
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
    if entry.get("joined_existing"):
        bits.append('<div class="callout info">joined the recommendation already '
                    "awaiting review (one Publish Gate item per cluster)</div>")
    for flag in entry.get("flags") or []:
        bits.append(f'<div class="callout">⚑ {esc(flag.get("reason"))}</div>')
    for call in entry.get("llm_calls") or []:
        tokens_ = (f' · {call["input_tokens"]}+{call["output_tokens"]} tokens'
                   if call.get("input_tokens") is not None else "")
        masked = call.get("pii_masked") or {}
        pii = (" · personal details masked: " + ", ".join(f"{k} ×{v}" for k, v in masked.items())
               if masked else "")
        how = "replayed" if call.get("replayed") else f'{call.get("latency_ms", 0):.0f} ms'
        bits.append(factor_row("model call",
                               esc(f'{call.get("provider")}/{call.get("model")} · {how}'
                                   f"{tokens_}{pii}")))
    return f'<div class="setu-card">{"".join(bits)}</div>'


# --- enhancements (group 8): analytics, equity, planner, trust, audit --------

CATEGORY_LABELS = {
    "water_infrastructure": "Water", "healthcare": "Healthcare",
    "road_infrastructure": "Roads", "sanitation": "Sanitation",
    "electricity": "Electricity", "education": "Education",
    "transportation": "Transport", "digital_connectivity": "Connectivity",
    "other": "Other",
}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def volume_line(cluster: dict) -> str:
    """Total members AND the volume the score counts — never a silent exclusion."""
    total, counted = cluster["member_count"], cluster.get("counted_volume", cluster["member_count"])
    text = f"members: {num(fmt_int(total))}"
    if counted != total:
        text += (f' · counted: {num(fmt_int(counted))} '
                 f'<span class="badge badge-flag">⚑ {fmt_int(total - counted)} excluded — '
                 "suspected manipulation</span>")
    return text


def trust_badge(cluster: dict) -> str:
    trust = cluster.get("trust") or {}
    open_flags = trust.get("open_request_flags", 0) + trust.get("open_cluster_flags", 0)
    if not open_flags:
        return ""
    return f'<span class="badge badge-flag">⚑ {open_flags} trust flag{"s" if open_flags != 1 else ""} to review</span>'


def map_legend(show_heat: bool, show_silent: bool) -> str:
    parts = ["Marker size and colour = priority tier: "
             + "".join(tier_badge(t) + "&nbsp;" for t in ("High", "Medium", "Low"))]
    if show_heat:
        parts.append('<span class="legend-heat"></span> Demand heat — counted requests')
    if show_silent:
        parts.append('<span class="legend-ring"></span> ◯ Silent region — high need, '
                     "few or no reports (data signal)")
    return '<div class="small-note legend">' + " · ".join(parts) + "</div>"


def silent_region_card(g: dict) -> str:
    factors = "".join(f"<li>{esc(f)}</li>" for f in g["factors"])
    return (
        f'<div class="setu-card silent-card"><div class="card-title">◯ {esc(g["name"])} '
        f'<span class="badge badge-confidence">{esc(category_label(g["category"]))}</span> '
        f'<span class="badge badge-signal">data-derived signal — not citizen demand</span></div>'
        f'<ul class="factor-list">{factors}</ul></div>'
    )


def ranking_table(rows: list[dict]) -> str:
    body = ""
    for r in rows:
        change = r["rank_change"]
        arrow = ("▲ " + str(change) if change > 0 else "▼ " + str(-change) if change < 0 else "—")
        cls = "up" if change > 0 else "down" if change < 0 else ""
        score = f'{r["score"]:.3f}' if r["score"] is not None else "—"
        body += (f'<tr><td>{esc(r["summary"])}</td>'
                 f'<td class="num">{fmt_int(r["complaints"])}</td>'
                 f'<td class="num">#{r["rank_by_complaints"]}</td>'
                 f'<td class="num">#{r["rank_by_score"]} · {score}</td>'
                 f'<td class="num rank-{cls}">{arrow}</td></tr>')
    return ('<table class="setu-table"><thead><tr><th>Cluster</th><th>Complaints</th>'
            "<th>Rank by complaints</th><th>Rank by Setu score</th><th>Change</th>"
            f"</tr></thead><tbody>{body}</tbody></table>")


def impact_panel(impact: dict) -> str:
    if not impact.get("available"):
        return (f'<div class="setu-card"><div class="card-title">Impact</div>'
                f'<div class="small-note">{esc(impact.get("reason", ""))}</div></div>')
    window = impact["window_days"]
    after_label = (f"after (partial — {impact['after_window_elapsed_days']:.0f} of {window} days)"
                   if impact["after_window_partial"] else f"{window} days after")
    rows = [
        factor_row(f"complaints, {window} days before resolution",
                   num(fmt_int(impact["complaints_before"]))),
        factor_row(f"complaints, {after_label}", num(fmt_int(impact["complaints_after"]))),
    ]
    if impact.get("change_pct") is not None:
        rows.append(factor_row("change", num(f'{impact["change_pct"]:+.1f}%')))
    gap = impact.get("gap")
    if gap:
        def g(v):
            return f"{v:,.0f} people per facility" if v else "no facility in radius"
        rows.append(factor_row("facilities in radius (before → after)",
                               num(f'{gap["facilities_before"]} → {gap["facilities_after"]}')))
        rows.append(factor_row("gap before → after",
                               esc(f'{g(gap["gap_before"])} → {g(gap["gap_after"])}')))
    return (f'<div class="setu-card"><div class="card-title">Impact after resolution</div>'
            f'{"".join(rows)}<div class="small-note">{esc(impact["note"])}</div></div>')


RULE_LABELS = {"duplicate_burst": "Duplicate burst", "repeat_source": "Repeat source",
               "cluster_spike": "Cluster spike"}


def trust_flag_card(flag: dict) -> str:
    text = (f'<div class="citizen-quote">{hindi(flag["raw_text"])}</div>'
            if flag.get("raw_text") else "")
    return (f'<div class="setu-card"><div class="card-title">'
            f'<span class="badge badge-flag">⚑ {esc(RULE_LABELS.get(flag["rule"], flag["rule"]))}</span> '
            f'{esc(flag.get("cluster_summary") or "")}</div>'
            f'<div class="card-meta">{esc(flag["reason"])}</div>{text}</div>')


def planner_whatif(out: dict) -> str:
    if not out["affected_regions"] and not out["affected_clusters"]:
        return ('<div class="setu-card">No region or cluster lies within the service '
                "radius of this location — nobody newly covered.</div>")
    rows = ""
    for r in out["affected_regions"]:
        before = ("no facility" if r["uncovered_before"]
                  else f'{r["gap_before"]:,.0f} per facility')
        rows += (f'<tr><td>{esc(r["region"])}</td><td class="num">{r["facilities_before"]} → '
                 f'{r["facilities_after"]}</td><td>{esc(before)} → '
                 f'{r["gap_after"]:,.0f} per facility</td>'
                 f'<td class="num">{fmt_int(r["newly_covered_population"])}</td></tr>')
    return (f'<div class="setu-card"><div class="card-title">Newly covered: '
            f'{num(fmt_int(out["newly_covered_population"]))} people</div>'
            '<table class="setu-table"><thead><tr><th>Region</th><th>Facilities</th>'
            f'<th>Gap</th><th>Newly covered</th></tr></thead><tbody>{rows}</tbody></table>'
            f'<div class="small-note">{esc(out["advisory"])}</div></div>')


def planner_allocation(out: dict) -> str:
    if not out["sites"]:
        return '<div class="setu-card">Every reachable region is already covered.</div>'
    rows = "".join(
        f'<tr><td class="num">{i + 1}</td><td>{esc(s["label"])}</td>'
        f'<td>{esc(", ".join(s["regions_served"]))}</td>'
        f'<td class="num">{fmt_int(s["newly_covered_population"])}</td>'
        f'<td class="num">{fmt_int(s["cumulative_population"])}</td></tr>'
        for i, s in enumerate(out["sites"]))
    left = (f'<div class="small-note">Still uncovered: {esc(", ".join(out["still_uncovered"]))}</div>'
            if out["still_uncovered"] else "")
    return ('<div class="setu-card"><table class="setu-table"><thead><tr><th>#</th><th>Site</th>'
            "<th>Serves</th><th>Newly covered</th><th>Cumulative</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>{left}"
            f'<div class="small-note">{esc(out["advisory"])}</div></div>')


def audit_status(result: dict) -> str:
    if result["intact"]:
        return (f'<div class="setu-card audit-ok">✓ Decision chain intact — '
                f'{num(fmt_int(result["entries"]))} entries verified. Any edit or deletion of a '
                "recorded decision would break the chain here.</div>")
    brk = result["first_break"]
    return (f'<div class="setu-card audit-broken">⚠ Decision chain BROKEN at entry '
            f'{num(brk["seq"])}: {esc(brk["reason"])}</div>')


def trends_figure(rows: list[dict]):
    """Stacked daily bars: counted (bridge blue) vs flagged (amber). Two
    series → legend always shown; palette validated (CVD ΔE 23.3)."""
    import plotly.graph_objects as go

    days = sorted({r["day"] for r in rows})
    counted = {d: 0 for d in days}
    flagged = {d: 0 for d in days}
    for r in rows:
        counted[r["day"]] += r["counted"]
        flagged[r["day"]] += r["flagged"]
    fig = go.Figure()
    fig.add_bar(x=days, y=[counted[d] for d in days], name="Counted requests",
                marker_color="#2B5FA8", marker_line_color="#FFFFFF", marker_line_width=1,
                hovertemplate="%{x|%d %b}: %{y} counted<extra></extra>")
    fig.add_bar(x=days, y=[flagged[d] for d in days], name="⚑ Flagged (excluded)",
                marker_color="#B26B00", marker_line_color="#FFFFFF", marker_line_width=1,
                hovertemplate="%{x|%d %b}: %{y} flagged<extra></extra>")
    fig.update_layout(
        barmode="stack", bargap=0.25, height=280, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, sans-serif", color="#5B6572", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(showgrid=False, linecolor="#E3E7EC"),
        yaxis=dict(gridcolor="#EEF1F4", zeroline=False, title="requests per day"),
        hovermode="x unified",
    )
    return fig
