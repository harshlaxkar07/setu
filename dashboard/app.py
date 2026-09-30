"""Setu policymaker dashboard (Track B, §6; enhancements group 8).

Evidence-forward Streamlit surface over the backend read API (never the
database — design D6): PyDeck demand map + cluster cards driven by ONE
selection, PriorityScore breakdowns, the Publish Gate review actions and the
run trace drawer; plus (enhancements) live refresh, a category filter across
every view, map layers (clusters / demand heat / silent regions), trust flags
and trends, equity insights, the investment planner, impact after
resolution, policy-brief download and the audit-chain status.

State discipline: every render reads fresh API responses; decisions change
nothing locally until the backend confirms (no optimism). Live refresh
re-renders only when the backend's data fingerprint changes, so the selected
cluster, open tab, filter and any typing survive it.
"""
from datetime import datetime

import pandas as pd
import pydeck as pdk
import streamlit as st

import api
import components as ui
import tokens

REFRESH_S = 5
EQUITY_CATEGORIES = ("water_infrastructure", "healthcare", "road_infrastructure")

st.set_page_config(page_title="Setu", page_icon="🌉", layout="wide")
st.markdown(f"<style>{tokens.CSS}</style>", unsafe_allow_html=True)
st.markdown(ui.header_bar(), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Live refresh (enhancements D10): poll a cheap fingerprint, rerun on change.
# --------------------------------------------------------------------------
@st.fragment(run_every=REFRESH_S)
def live_refresh() -> None:
    version = api.get_version()
    previous = st.session_state.get("_data_version")
    st.session_state._data_version = version
    if previous is not None and version is not None and version != previous:
        st.rerun()  # whole app: fresh data, same selection/tab/filter
    stamp = datetime.now().strftime("%H:%M:%S")
    state = "● Live" if version else "○ Backend unreachable"
    st.markdown(f'<div class="live-dot">{state} · checked {stamp}</div>',
                unsafe_allow_html=True)


live_refresh()

# --------------------------------------------------------------------------
# Data: everything over BACKEND_URL
# --------------------------------------------------------------------------
try:
    all_clusters = api.get_clusters()
except api.ApiError as exc:
    st.error(f"Cannot reach the Setu backend: {exc}")
    st.stop()

if not all_clusters:
    st.info("No demand clusters yet — seed the database or submit a request.")
    st.stop()


def _detail(cluster_id: str) -> dict:
    """Cluster detail (indicators, breakdown, samples) — cached per rerun."""
    cache = st.session_state.setdefault("_detail_cache", {})
    if cluster_id not in cache:
        try:
            cache[cluster_id] = api.get_cluster(cluster_id)
        except api.ApiError as exc:
            st.error(f"Could not load cluster detail: {exc}")
            cache[cluster_id] = {"indicators": [], "sample_requests": []}
    return cache[cluster_id]


st.session_state.pop("_detail_cache", None)  # always render fresh data

try:
    published = api.get_recommendations("published")
    pending = api.get_recommendations("pending")
    needs_revision = api.get_recommendations("needs_revision")
    recs_error = None
except api.ApiError as exc:
    published, pending, needs_revision = [], [], []
    recs_error = str(exc)
flagged, verification_available = api.get_flagged_verifications()
try:
    open_flags = api.get_trust_flags("open")
except api.ApiError:
    open_flags = []


# --------------------------------------------------------------------------
# Reviewer session (enhancements D15): decisions need a signed-in reviewer;
# viewing never does. The backend records the account name from the token.
# --------------------------------------------------------------------------
def session_token() -> str | None:
    return (st.session_state.get("session") or {}).get("token")


def signed_in_as() -> str | None:
    return (st.session_state.get("session") or {}).get("reviewer")


def decide(call, *args):
    """Run a decision call with the session token; a 401 ends the session."""
    try:
        return call(*args, session_token())
    except api.SessionExpired as exc:
        st.session_state.pop("session", None)
        return None, f"your reviewer session ended ({exc}) — sign in again"


def sign_in_note(what: str = "record decisions") -> None:
    if not signed_in_as():
        st.markdown(f'<div class="small-note">Sign in on the Publish Gate tab to {what}.'
                    "</div>", unsafe_allow_html=True)


def reviewer_panel() -> None:
    """Sign-in form, or who is signed in with a sign-out button."""
    who = signed_in_as()
    if who:
        c1, c2 = st.columns([5, 1])
        c1.markdown(f'<div class="signed-in">Signed in as <b>{ui.esc(who)}</b> — '
                    "your name is recorded with every decision.</div>",
                    unsafe_allow_html=True)
        if c2.button("Sign out", key="sign_out"):
            st.session_state.pop("session", None)
            st.rerun()
        return
    names = api.configured_reviewers()
    if not names:
        st.warning("No reviewer accounts are configured, so decisions cannot be "
                   "recorded. Add REVIEWERS to .env (see README) and restart.")
        return
    with st.form("sign_in", clear_on_submit=True):
        st.markdown('<div class="card-title">Reviewer sign-in</div>'
                    '<div class="small-note">Viewing is open to everyone; '
                    "approving, rejecting and reviewing require a reviewer "
                    "account.</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([3, 3, 1])
        name = c1.selectbox("Reviewer", names, key="sign_in_name")
        passcode = c2.text_input("Passcode", type="password", key="sign_in_pass")
        c3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if c3.form_submit_button("Sign in", type="primary"):
            session, err = api.login(name, passcode)
            if err:
                st.error(err)
            else:
                st.session_state.session = session
                st.rerun()


# --------------------------------------------------------------------------
# Category filter (enhancements D10): one choice drives every view below.
# --------------------------------------------------------------------------
categories = sorted({c["category"] for c in all_clusters})
ALL = "All categories"
filter_col, _ = st.columns([2, 5])
choice = filter_col.selectbox(
    "Category", [ALL] + categories, key="category_filter",
    format_func=lambda c: c if c == ALL else ui.category_label(c))
category = None if choice == ALL else choice
clusters = [c for c in all_clusters if category is None or c["category"] == category]
if not clusters:
    st.info("No clusters in this category yet.")
    st.stop()
by_id = {c["id"]: c for c in clusters}
cluster_ids = set(by_id)


def in_filter(cluster_id: str | None) -> bool:
    return category is None or cluster_id in cluster_ids


# --------------------------------------------------------------------------
# Summary strip: what needs attention, at a glance (filtered)
# --------------------------------------------------------------------------
pending_f = [r for r in pending if in_filter(r.get("demand_cluster_id"))]
published_f = [r for r in published if in_filter(r.get("demand_cluster_id"))]
open_flags_f = [f for f in open_flags if in_filter(f.get("cluster_id"))]
flagged_f = [r for r in flagged if in_filter(r.get("demand_cluster_id"))]
st.markdown(ui.summary_strip([
    ("Demand clusters", len(clusters), None),
    ("High priority", sum(1 for c in clusters if c.get("tier") == "High"),
     "high" if any(c.get("tier") == "High" for c in clusters) else None),
    ("Awaiting review", len(pending_f), "pending" if pending_f else None),
    ("Published", len(published_f), None),
    ("Trust flags to review", len(open_flags_f), "pending" if open_flags_f else None),
    ("Flagged verifications", len(flagged_f), "high" if flagged_f else None),
]), unsafe_allow_html=True)

# Static labels (counts live in the strip above) so the open tab survives reruns.
(tab_priorities, tab_gate, tab_trust, tab_equity, tab_planner, tab_verify,
 tab_audit) = st.tabs(["Priorities", "Publish Gate", "Trust & trends", "Equity",
                       "Planner", "Verification", "Audit"])

# --------------------------------------------------------------------------
# Single selection drives map AND card detail (spec requirement)
# --------------------------------------------------------------------------
if "selected_cluster_id" not in st.session_state or \
        st.session_state.selected_cluster_id not in by_id:
    st.session_state.selected_cluster_id = clusters[0]["id"]  # top-ranked


def select_cluster(cluster_id: str) -> None:
    st.session_state.selected_cluster_id = cluster_id
    # Reset the map widget's persisted pick so re-clicking the same marker
    # after a card-button selection still registers (review finding).
    st.session_state.pop("demand_map", None)
    st.session_state.pop("_last_map_pick", None)


def silent_regions() -> list[dict]:
    try:
        cats = [category] if category in EQUITY_CATEGORIES else (
            [] if category else list(EQUITY_CATEGORIES))
        out = []
        for c in cats:
            out += api.get_silent_regions(c)
        return out
    except api.ApiError:
        return []


with tab_priorities:
    map_col, cards_col = st.columns([7, 5], gap="medium")

    with map_col:
        st.markdown('<div class="section-title">Demand map</div>',
                    unsafe_allow_html=True)
        t1, t2, t3 = st.columns(3)
        show_clusters = t1.toggle("Clusters", value=True, key="layer_clusters")
        show_heat = t2.toggle("Demand heat", value=False, key="layer_heat")
        show_silent = t3.toggle("Silent regions", value=True, key="layer_silent")

        selected = by_id[st.session_state.selected_cluster_id]
        layers = []
        if show_heat:
            layers.append(pdk.Layer(
                "HeatmapLayer", id="heat",
                data=pd.DataFrame([{"lat": c["lat"], "lon": c["lon"],
                                    "weight": c.get("counted_volume", c["member_count"])}
                                   for c in clusters if c["lat"] is not None]),
                get_position=["lon", "lat"], get_weight="weight",
                radius_pixels=70, intensity=1.2, threshold=0.05,
                color_range=[[242, 201, 139], [230, 160, 90], [214, 110, 60],
                             [194, 55, 46]],
            ))
        if show_silent:
            silent = silent_regions()
            if silent:
                # One ring per region (a region can be silent in several categories).
                rings = {}
                for g in silent:
                    r = rings.setdefault(g["name"], {
                        "lat": g["lat"], "lon": g["lon"], "cats": [],
                        "label": f"{g['population']:,} residents · "
                                 f"{g['complaints']} reports"})
                    r["cats"].append(ui.category_label(g["category"]))
                layers.append(pdk.Layer(
                    "ScatterplotLayer", id="silent",
                    data=pd.DataFrame([{
                        "lat": r["lat"], "lon": r["lon"],
                        "summary": f"◯ Silent region: {name} — {', '.join(r['cats'])}",
                        "label": r["label"] + " (data signal, not citizen demand)"}
                        for name, r in rings.items()]),
                    get_position=["lon", "lat"], get_radius=2000,
                    filled=False, stroked=True, get_line_color=[30, 68, 120, 220],
                    line_width_min_pixels=3, pickable=True,
                ))
        if show_clusters:
            rows = []
            for c in clusters:
                if c["lat"] is None:
                    continue
                tier = c.get("tier")
                color = tokens.TIER_TOKENS.get(tier, (None, None, tokens.TIER_UNSCORED_RGB))[2]
                radius = {"High": 1400, "Medium": 1000, "Low": 700}.get(tier, 600)
                rows.append({
                    "id": c["id"], "lat": c["lat"], "lon": c["lon"],
                    "color": color + [235 if c["id"] == selected["id"] else 170],
                    "radius": radius,
                    "label": f"{tier or 'unscored'} · {c['member_count']} members",
                    "summary": c.get("representative_summary") or "",
                })
            layers.append(pdk.Layer(
                "ScatterplotLayer", id="clusters", data=pd.DataFrame(rows),
                get_position=["lon", "lat"], get_fill_color="color",
                get_radius="radius", pickable=True, stroked=True,
                get_line_color=[23, 33, 43, 120], line_width_min_pixels=1,
            ))
        deck = pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=selected["lat"] or 18.45, longitude=selected["lon"] or 73.75,
                zoom=8.6),
            map_style="light",
            tooltip={"text": "{summary}\n{label}"},
        )
        # Marker click selects the cluster (falls back to card-only selection on
        # Streamlit builds without pydeck selection events).
        try:
            event = st.pydeck_chart(deck, on_select="rerun",
                                    selection_mode="single-object", key="demand_map")
            picked = None
            objects = getattr(getattr(event, "selection", None), "objects", None) or {}
            for objs in (objects.get("clusters") or [],):
                if objs:
                    picked = objs[0].get("id")
            if picked and picked in by_id and \
                    picked != st.session_state.get("_last_map_pick"):
                st.session_state._last_map_pick = picked
                select_cluster(picked)
                st.rerun()
        except TypeError:
            st.pydeck_chart(deck)
        # Legend: every colour/shape paired with its text label (never colour-only).
        st.markdown(ui.map_legend(show_heat, show_silent), unsafe_allow_html=True)

    with cards_col:
        st.markdown('<div class="section-title">Demand clusters (ranked)</div>',
                    unsafe_allow_html=True)
        for c in clusters:
            is_selected = c["id"] == st.session_state.selected_cluster_id
            st.markdown(ui.cluster_card(c, is_selected), unsafe_allow_html=True)
            if not is_selected:
                st.button("Focus this cluster", key=f"focus_{c['id']}",
                          on_click=select_cluster, args=(c["id"],))

    # ----------------------------------------------------------------------
    # Selected cluster: breakdown, factors, voices, resolution, impact, brief
    # ----------------------------------------------------------------------
    sel = by_id[st.session_state.selected_cluster_id]
    detail = _detail(sel["id"])

    st.markdown('<div class="section-title">Selected cluster — evidence: '
                f'<span class="section-sub">{ui.esc(sel.get("representative_summary") or "")}'
                '</span></div>', unsafe_allow_html=True)
    left, right = st.columns([6, 6], gap="medium")

    with left:
        if sel.get("score") is not None:
            st.markdown(
                f'<div class="setu-card"><div class="card-title">PriorityScore '
                f'breakdown {ui.tier_badge(sel["tier"])}</div>'
                + ui.score_breakdown(sel["score"], sel["components"])
                + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="setu-card">Not scored yet.</div>',
                        unsafe_allow_html=True)
        with st.expander("Priority factors — every indicator behind this score",
                         expanded=True):
            st.markdown(ui.indicator_rows(detail.get("indicators", [])),
                        unsafe_allow_html=True)
            st.markdown(
                '<div class="small-note">Each factor is stored individually with '
                "its source citations; the composite above recomputes exactly from "
                "these rows (verified by the automated formula-consistency test)."
                "</div>", unsafe_allow_html=True)
        try:
            brief = api.get_brief_html(sel["id"])
            st.download_button(
                "⬇ Download policy brief (bilingual, one page — open and print to PDF)",
                data=brief, file_name=f"setu-brief-{sel['id'][:8]}.html",
                mime="text/html", key=f"brief_{sel['id']}", use_container_width=True)
        except api.ApiError as exc:
            st.caption(f"Policy brief unavailable: {exc}")

    with right:
        quotes = "".join(
            ui.citizen_quote(s["raw_text"], s.get("detected_language"))
            + (f'<div class="small-note">field-worker report · '
               f'{ui.fmt_int(s.get("households"))} households represented</div>'
               if s.get("channel") == "assisted" else "")
            for s in detail.get("sample_requests", [])
        ) or '<div class="small-note">No raw request texts available.</div>'
        st.markdown(
            '<div class="setu-card"><div class="card-title">Citizen voices '
            '<span class="small-note">(raw submissions — not AI-generated)</span>'
            f"</div>{quotes}</div>", unsafe_allow_html=True)

        # Resolution state + the simulated mark-resolved action (§8 seam).
        st.markdown(
            f'<div class="setu-card"><div class="card-title">Resolution state</div>'
            f'{ui.status_badge(sel["status"])}</div>', unsafe_allow_html=True)
        if sel["status"] == "published":
            if st.button("Mark resolved (simulated)", key="resolve_btn",
                         disabled=not signed_in_as(),
                         help=None if signed_in_as() else
                         "Sign in on the Publish Gate tab to record this"):
                _, err = decide(api.post_mark_resolved, sel["id"])
                if err:
                    st.error(f"Mark-resolved failed — nothing changed: {err}")
                else:
                    st.success("Cluster recorded as resolved — unverified.")
                    st.rerun()
        elif sel["status"] == "active":
            st.markdown(
                '<div class="small-note">Mark-resolved becomes available once the '
                "cluster's recommendation is approved and published.</div>",
                unsafe_allow_html=True)
        if sel["status"] in ("resolved_unverified", "resolved_verified"):
            try:
                st.markdown(ui.impact_panel(api.get_impact(sel["id"])),
                            unsafe_allow_html=True)
            except api.ApiError as exc:
                st.caption(f"Impact unavailable: {exc}")

    # Run trace drawer (task 6.8) — full pipeline path for the selected cluster.
    with st.expander("Run trace — pipeline path for this cluster's requests"):
        try:
            traces = api.get_cluster_trace(sel["id"])
        except api.ApiError as exc:
            traces = []
            st.error(f"Trace unavailable: {exc}")
        if not traces:
            st.markdown(
                '<div class="small-note">No pipeline runs traced yet for this '
                "cluster — traces appear when live submissions run through the "
                "orchestrated pipeline (Understand → Locate → Cluster → Trust → Fuse "
                "→ Score → Recommend → Publish Gate).</div>", unsafe_allow_html=True)
        for t in traces:
            st.markdown(
                f'<div class="card-meta">run {ui.num(t["id"][:8])} · status '
                f'{ui.esc(t["status"])} · thread {ui.num(t.get("thread_id") or "—")}'
                "</div>", unsafe_allow_html=True)
            for entry in t.get("stages", []):
                st.markdown(ui.trace_stage_row(entry), unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Publish Gate: awaiting review first, then sent back, then published
# --------------------------------------------------------------------------


def _published_badge(rec: dict) -> str:
    """Published badge carrying the recorded approval's reviewer + timestamp."""
    a = rec.get("approval") or {}
    return (
        '<span class="badge badge-published">✓ published — approved by '
        f'{ui.esc(a.get("reviewer", "?"))} at {ui.esc(a.get("decided_at", "?"))}'
        "</span>"
    )


def _recommendation_card(rec: dict, gated: bool) -> None:
    """recommendation_card: AI-drafted text + citations (+ gate actions)."""
    badge = ui.pending_badge() if gated else _published_badge(rec)
    st.markdown(
        f'<div class="setu-card"><div class="card-title">'
        f'{ui.esc(rec["intervention_type"].replace("_", " "))} {ui.ai_marker()} '
        f"{badge}</div>"
        f'<div>{ui.esc(rec["intervention_text"])}</div>'
        f'<div class="card-meta" style="margin-top:8px">addresses cluster: '
        f'{ui.esc(rec["cluster_summary"])}</div>'
        f'<div class="card-title" style="margin-top:8px">Evidence citations</div>'
        f'{ui.recommendation_citations(rec["indicator_citations"])}'
        "</div>", unsafe_allow_html=True)


with tab_gate:
    reviewer_panel()
    if recs_error:
        st.error(f"Could not load recommendations: {recs_error}")

    st.markdown('<div class="section-title" style="margin-top:8px">Awaiting review '
                "(Publish Gate)</div>", unsafe_allow_html=True)
    if not pending_f:
        st.markdown('<div class="small-note">No drafts awaiting review.</div>',
                    unsafe_allow_html=True)
    for rec in pending_f:
        _recommendation_card(rec, gated=True)
        if not rec.get("thread_id"):
            st.markdown('<div class="small-note">This draft has no gate thread yet '
                        "— actions activate when the orchestrated run reaches the "
                        "Publish Gate.</div>", unsafe_allow_html=True)
            continue
        b1, b2, b3 = st.columns(3)
        locked = not signed_in_as()
        decision = None
        if b1.button("Approve", key=f"approve_{rec['id']}", type="primary",
                     disabled=locked):
            decision = "approved"
        if b2.button("Reject", key=f"reject_{rec['id']}", disabled=locked):
            decision = "rejected"
        if b3.button("Request changes", key=f"changes_{rec['id']}", disabled=locked):
            decision = "needs_revision"
        if decision:
            # No optimistic state: only a confirmed backend response changes what
            # is displayed; on error the item stays exactly as it was (spec).
            out, err = decide(api.post_gate_decision, rec["thread_id"], decision)
            if err:
                st.error(f"Decision NOT recorded — the recommendation remains "
                         f"pending. {err}")
            else:
                st.success(f"Decision '{decision}' recorded by {out['reviewer']}.")
                st.rerun()

    # Sent back with Request-changes: unpublished, visibly awaiting revision —
    # never blended with approved items (policymaker-dashboard spec).
    revision_f = [r for r in needs_revision if in_filter(r.get("demand_cluster_id"))]
    if revision_f:
        st.markdown('<div class="section-title" style="font-size:14px">Awaiting '
                    "revision (changes requested)</div>", unsafe_allow_html=True)
        for rec in revision_f:
            _recommendation_card(rec, gated=True)
            st.markdown('<div class="small-note">A reviewer requested changes — '
                        "this draft stays unpublished until revised and "
                        "re-approved.</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-title" style="font-size:14px">Published '
                '(derived solely from recorded approvals)</div>',
                unsafe_allow_html=True)
    if not published_f:
        st.markdown('<div class="small-note">Nothing published yet — a '
                    "recommendation appears here only after a recorded approval."
                    "</div>", unsafe_allow_html=True)
    for rec in published_f:
        _recommendation_card(rec, gated=False)

# --------------------------------------------------------------------------
# Trust & trends: daily arrivals (flagged vs counted) and flags to review
# --------------------------------------------------------------------------
with tab_trust:
    st.markdown('<div class="section-title">Requests per day — last 60 days</div>',
                unsafe_allow_html=True)
    try:
        trend_rows = api.get_trends(category)
    except api.ApiError as exc:
        trend_rows = []
        st.error(f"Trends unavailable: {exc}")
    if trend_rows:
        st.plotly_chart(ui.trends_figure(trend_rows), use_container_width=True,
                        config={"displayModeBar": False}, key="trends_chart")
        with st.expander("Table view"):
            st.dataframe(pd.DataFrame(trend_rows)[["day", "category", "counted", "flagged"]]
                         .rename(columns={"category": "category (raw)"}),
                         hide_index=True, use_container_width=True)
    else:
        st.markdown('<div class="small-note">No requests in this period.</div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="section-title">Trust flags to review</div>'
                '<div class="small-note">Flags never delete anything. Flagged '
                "requests are left out of the complaint-volume indicator until a "
                "reviewer clears them; confirmed manipulation stays excluded.</div>",
                unsafe_allow_html=True)
    sign_in_note("clear or confirm flags")
    if not open_flags_f:
        st.markdown('<div class="small-note">No open trust flags.</div>',
                    unsafe_allow_html=True)
    for flag in open_flags_f[:50]:
        st.markdown(ui.trust_flag_card(flag), unsafe_allow_html=True)
        c1, c2, _ = st.columns([2, 2, 5])
        locked = not signed_in_as()
        verdict = None
        if c1.button("Clear — legitimate", key=f"tclear_{flag['id']}", disabled=locked):
            verdict = "clear"
        if c2.button("Confirm manipulation", key=f"tconf_{flag['id']}", disabled=locked):
            verdict = "confirm"
        if verdict:
            _, err = decide(api.post_trust_review, flag["id"], verdict)
            if err:
                st.error(f"Review NOT recorded — the flag stays open. {err}")
            else:
                st.rerun()
    if len(open_flags_f) > 50:
        st.caption(f"Showing 50 of {len(open_flags_f)} open flags.")

# --------------------------------------------------------------------------
# Equity: complaint count vs Setu ranking, the worked example, silent regions
# --------------------------------------------------------------------------
with tab_equity:
    rank_cat = category if category in EQUITY_CATEGORIES else "water_infrastructure"
    st.markdown(f'<div class="section-title">Ranking by complaint count vs by Setu score — '
                f'{ui.esc(ui.category_label(rank_cat))}</div>'
                '<div class="small-note">Counting complaints favours well-connected '
                "areas. Setu ranks by infrastructure gap and historical investment "
                "first; complaint volume is capped at 20% of the score.</div>",
                unsafe_allow_html=True)
    try:
        st.markdown(ui.ranking_table(api.get_ranking(rank_cat)), unsafe_allow_html=True)
    except api.ApiError as exc:
        st.error(f"Ranking unavailable: {exc}")

    same_cat = [c for c in all_clusters if c["category"] == rank_cat and c["lat"] is not None]
    if len(same_cat) >= 2:
        st.markdown('<div class="section-title">Gap comparison — complaint volume vs '
                    'infrastructure gap</div>', unsafe_allow_html=True)
        region_a = max(same_cat, key=lambda c: c["member_count"])
        region_b = min(same_cat, key=lambda c: c["member_count"])
        st.markdown(ui.gap_comparison_panel(region_a, region_b, _detail(region_a["id"]),
                                            _detail(region_b["id"])),
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="small-note">The scoring formula is fixed in code: '
            "complaint volume's weight (0.2) is capped below the infrastructure "
            "gap's (0.5) by construction — volume can never override gap.</div>",
            unsafe_allow_html=True)

    st.markdown('<div class="section-title">Silent regions — high need, few or no '
                "reports</div><div class=\"small-note\">Found from population and "
                "facility data alone. They are signals for officials to investigate, "
                "not citizen demand, and nothing is published for them without the "
                "Publish Gate.</div>", unsafe_allow_html=True)
    silent_list = silent_regions()
    if not silent_list:
        st.markdown('<div class="small-note">No silent regions for this category.</div>',
                    unsafe_allow_html=True)
    cols = st.columns(2)
    for i, g in enumerate(silent_list):
        cols[i % 2].markdown(ui.silent_region_card(g), unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Planner: what-if facility placement and budget allocation (advisory)
# --------------------------------------------------------------------------
with tab_planner:
    st.markdown('<div class="section-title">Investment planner</div>'
                '<div class="small-note">Advisory simulation — nothing here creates '
                "facilities, clusters or recommendations.</div>", unsafe_allow_html=True)
    plan_cat = st.selectbox(
        "Facility type", EQUITY_CATEGORIES, key="plan_cat",
        index=EQUITY_CATEGORIES.index(category) if category in EQUITY_CATEGORIES else 0,
        format_func=lambda c: {"water_infrastructure": "Water point",
                               "healthcare": "Health centre",
                               "road_infrastructure": "All-weather road access"}[c])
    w_col, a_col = st.columns(2, gap="large")
    with w_col:
        st.markdown('<div class="card-title">What if we build one here?</div>',
                    unsafe_allow_html=True)
        sites = {f"Cluster: {c['representative_summary']}": (c["lat"], c["lon"])
                 for c in all_clusters if c["category"] == plan_cat and c["lat"] is not None}
        try:
            for g in api.get_silent_regions(plan_cat):
                sites[f"Silent region: {g['name']}"] = (g["lat"], g["lon"])
        except api.ApiError:
            pass
        site = st.selectbox("Proposed location", list(sites), key="plan_site")
        if st.button("Simulate", key="plan_whatif", type="primary") and site:
            lat, lon = sites[site]
            out, err = api.post_whatif(plan_cat, lat, lon)
            st.session_state.plan_whatif_out = (err, out)
        if "plan_whatif_out" in st.session_state:
            err, out = st.session_state.plan_whatif_out
            if err:
                st.error(err)
            elif out["category"] == plan_cat:
                st.markdown(ui.planner_whatif(out), unsafe_allow_html=True)
    with a_col:
        st.markdown('<div class="card-title">Where should N new facilities go?</div>',
                    unsafe_allow_html=True)
        n = st.slider("Number of facilities", 1, 10, 3, key="plan_n")
        if st.button("Suggest sites", key="plan_allocate", type="primary"):
            out, err = api.post_allocate(plan_cat, n)
            st.session_state.plan_alloc_out = (err, out)
        if "plan_alloc_out" in st.session_state:
            err, out = st.session_state.plan_alloc_out
            if err:
                st.error(err)
            elif out["category"] == plan_cat:
                st.markdown(ui.planner_allocation(out), unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Verification review surface (§8)
# --------------------------------------------------------------------------
with tab_verify:
    if flagged_f:
        sign_in_note("record verification reviews")
    if not verification_available:
        st.markdown(
            '<div class="small-note">Flagged-verification review activates with '
            "the verification bolt-on (§8). Resolution badges on the Priorities tab "
            "are already live: resolved clusters show “resolved — unverified” until a "
            "verification confirms them.</div>", unsafe_allow_html=True)
    elif not flagged_f:
        st.markdown('<div class="small-note">No flagged verification records.</div>',
                    unsafe_allow_html=True)
    for record in flagged_f:
        st.markdown(
            f'<div class="setu-card"><div class="card-title">'
            f'<span class="badge badge-flag">⚑ flagged — needs human review</span> '
            f'cluster {ui.num(record.get("demand_cluster_id", "")[:8])}</div>'
            f'<div class="card-meta">original complaint: '
            f'{ui.esc(record.get("cluster_summary", ""))}</div>'
            f'<div class="card-meta">follow-up media: '
            f'{ui.esc(record.get("media_paths", []))}</div></div>',
            unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        locked = not signed_in_as()
        v_decision = None
        if c1.button("Confirm resolved", key=f"vc_{record['id']}", type="primary",
                     disabled=locked):
            v_decision = "confirm_resolved"
        if c2.button("Reject resolution", key=f"vr_{record['id']}", disabled=locked):
            v_decision = "reject_resolution"
        if v_decision:
            _, err = decide(api.post_verification_review, record["id"], v_decision)
            if err:
                st.error(f"Review NOT recorded — the flag remains active. {err}")
            else:
                st.success("Review recorded.")
                st.rerun()

# --------------------------------------------------------------------------
# Audit: the hash-chained decision log (enhancements D14)
# --------------------------------------------------------------------------
with tab_audit:
    st.markdown('<div class="section-title">Decision log integrity</div>',
                unsafe_allow_html=True)
    try:
        st.markdown(ui.audit_status(api.get_audit_verify()), unsafe_allow_html=True)
        log = api.get_audit_log(30)
        if log:
            st.markdown('<div class="section-title" style="font-size:14px">Latest '
                        "decisions</div>", unsafe_allow_html=True)
            st.dataframe(
                pd.DataFrame([{"#": e["seq"], "when": e["decided_at"],
                               "decision": f'{e["kind"].replace("_", " ")}: {e["decision"]}',
                               "reviewer": e["reviewer"], "hash": e["hash"][:12] + "…"}
                              for e in log]),
                hide_index=True, use_container_width=True)
    except api.ApiError as exc:
        st.error(f"Audit unavailable: {exc}")
