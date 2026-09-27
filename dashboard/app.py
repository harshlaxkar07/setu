"""Setu policymaker dashboard (Track B, §6).

Evidence-forward Streamlit surface over the backend read API (never the
database — design D6): PyDeck demand map + cluster cards driven by ONE
selection, PriorityScore breakdowns, the Region A/B gap comparison, the
Publish Gate review actions, and the run trace drawer. Chrome-hiding and
token styling per files/06 + files/07.

State discipline: every render reads fresh API responses; gate and resolve
actions change nothing locally until the backend confirms (no optimism).
"""
import pandas as pd
import pydeck as pdk
import streamlit as st

import api
import components as ui
import tokens

st.set_page_config(page_title="Setu", page_icon="🌉", layout="wide")
st.markdown(f"<style>{tokens.CSS}</style>", unsafe_allow_html=True)
st.markdown(ui.header_bar(), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Data: everything over BACKEND_URL
# --------------------------------------------------------------------------
try:
    clusters = api.get_clusters()
except api.ApiError as exc:
    st.error(f"Cannot reach the Setu backend: {exc}")
    st.stop()

if not clusters:
    st.info("No demand clusters yet — seed the database or submit a request.")
    st.stop()

by_id = {c["id"]: c for c in clusters}


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


# --------------------------------------------------------------------------
# Layout: map | card list, side by side (stacks on narrow viewports)
# --------------------------------------------------------------------------
map_col, cards_col = st.columns([7, 5], gap="medium")

with map_col:
    st.markdown('<div class="section-title">Demand map</div>',
                unsafe_allow_html=True)

    selected = by_id[st.session_state.selected_cluster_id]
    rows = []
    for c in clusters:
        tier = c.get("tier")
        color = tokens.TIER_TOKENS.get(tier, (None, None, tokens.TIER_UNSCORED_RGB))[2]
        # Sized and colored by tier; selected marker gets a stronger alpha ring.
        radius = {"High": 1400, "Medium": 1000, "Low": 700}.get(tier, 600)
        rows.append({
            "id": c["id"], "lat": c["lat"], "lon": c["lon"],
            "color": color + [235 if c["id"] == selected["id"] else 170],
            "radius": radius,
            "label": f"{tier or 'unscored'} · {c['member_count']} members",
            "summary": c.get("representative_summary") or "",
        })
    layer = pdk.Layer(
        "ScatterplotLayer",
        id="clusters",
        data=pd.DataFrame(rows),
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        stroked=True,
        get_line_color=[23, 33, 43, 120],
        line_width_min_pixels=1,
    )
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(
            latitude=selected["lat"], longitude=selected["lon"], zoom=9.2,
        ),
        map_style="light",
        tooltip={"text": "{summary}\n{label}"},
    )

    # Marker click selects the cluster (falls back to card-only selection on
    # Streamlit builds without pydeck selection events).
    try:
        event = st.pydeck_chart(
            deck, on_select="rerun", selection_mode="single-object",
            key="demand_map",
        )
        picked = None
        objects = getattr(getattr(event, "selection", None), "objects", None) or {}
        for objs in objects.values():
            if objs:
                picked = objs[0].get("id")
        if picked and picked in by_id and \
                picked != st.session_state.get("_last_map_pick"):
            st.session_state._last_map_pick = picked
            select_cluster(picked)
            st.rerun()
    except TypeError:
        st.pydeck_chart(deck)

    # Legend: tier color ALWAYS paired with its text label (never color-only).
    legend = "".join(ui.tier_badge(t) + "&nbsp;" for t in ("High", "Medium", "Low"))
    st.markdown(
        f'<div class="small-note">Marker size and color = PriorityScore tier: '
        f"{legend}</div>", unsafe_allow_html=True,
    )

with cards_col:
    st.markdown('<div class="section-title">Demand clusters (ranked)</div>',
                unsafe_allow_html=True)
    for c in clusters:
        is_selected = c["id"] == st.session_state.selected_cluster_id
        st.markdown(ui.cluster_card(c, is_selected), unsafe_allow_html=True)
        if not is_selected:
            st.button(
                "Focus this cluster", key=f"focus_{c['id']}",
                on_click=select_cluster, args=(c["id"],),
            )

# --------------------------------------------------------------------------
# Selected cluster: breakdown, factors, citizen voices, resolve, trace drawer
# --------------------------------------------------------------------------
sel = by_id[st.session_state.selected_cluster_id]
detail = _detail(sel["id"])

st.markdown('<div class="section-title">Selected cluster — evidence</div>',
            unsafe_allow_html=True)
left, right = st.columns([6, 6], gap="medium")

with left:
    if sel.get("score") is not None:
        st.markdown(
            f'<div class="setu-card"><div class="card-title">PriorityScore '
            f'breakdown {ui.tier_badge(sel["tier"])}</div>'
            + ui.score_breakdown(sel["score"], sel["components"])
            + "</div>",
            unsafe_allow_html=True,
        )
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

with right:
    quotes = "".join(
        ui.citizen_quote(s["raw_text"], s.get("detected_language"))
        for s in detail.get("sample_requests", [])
    ) or '<div class="small-note">No raw request texts available.</div>'
    st.markdown(
        '<div class="setu-card"><div class="card-title">Citizen voices '
        '<span class="small-note">(raw submissions — not AI-generated)</span>'
        f"</div>{quotes}</div>",
        unsafe_allow_html=True,
    )

    # Resolution state + the simulated mark-resolved action (§8 seam).
    st.markdown(
        f'<div class="setu-card"><div class="card-title">Resolution state</div>'
        f'{ui.status_badge(sel["status"])}</div>', unsafe_allow_html=True,
    )
    if sel["status"] == "published":
        if st.button("Mark resolved (simulated)", key="resolve_btn"):
            _, err = api.post_mark_resolved(sel["id"])
            if err:
                st.error(f"Mark-resolved failed — nothing changed: {err}")
            else:
                st.success("Cluster recorded as resolved — unverified.")
                st.rerun()
    elif sel["status"] == "active":
        st.markdown(
            '<div class="small-note">Mark-resolved becomes available once the '
            "cluster's recommendation is approved and published.</div>",
            unsafe_allow_html=True,
        )

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
            "orchestrated pipeline (Understand → Locate → Cluster → Fuse → "
            "Score → Recommend → Publish Gate).</div>",
            unsafe_allow_html=True,
        )
    for t in traces:
        st.markdown(
            f'<div class="card-meta">run {ui.num(t["id"][:8])} · status '
            f'{ui.esc(t["status"])} · thread {ui.num(t.get("thread_id") or "—")}'
            "</div>", unsafe_allow_html=True,
        )
        for entry in t.get("stages", []):
            st.markdown(ui.trace_stage_row(entry), unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Gap comparison panel: the Region A vs Region B equity contrast (task 6.5)
# --------------------------------------------------------------------------
st.markdown('<div class="section-title">Gap comparison — complaint volume vs '
            'infrastructure gap</div>', unsafe_allow_html=True)
water = [c for c in clusters if c["category"] == "water_infrastructure"]
if len(water) >= 2:
    region_a = max(water, key=lambda c: c["member_count"])
    region_b = min(water, key=lambda c: c["member_count"])
    st.markdown(
        ui.gap_comparison_panel(
            region_a, region_b, _detail(region_a["id"]), _detail(region_b["id"])
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="small-note">The scoring formula is fixed in code: '
        'complaint volume\'s weight (0.2) is capped below the infrastructure '
        'gap\'s (0.5) by construction — volume can never override gap.</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown('<div class="small-note">Both seeded water clusters are needed '
                'for the comparison panel.</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Recommendations: published (solely from approvals) + awaiting review
# --------------------------------------------------------------------------
st.markdown('<div class="section-title">Recommendations</div>',
            unsafe_allow_html=True)
reviewer = st.text_input("Reviewer identity (recorded with every decision)",
                         value=st.session_state.get("reviewer", "Demo Reviewer"),
                         key="reviewer")

try:
    published = api.get_recommendations("published")
    pending = api.get_recommendations("pending")
    needs_revision = api.get_recommendations("needs_revision")
except api.ApiError as exc:
    published, pending, needs_revision = [], [], []
    st.error(f"Could not load recommendations: {exc}")


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
        "</div>",
        unsafe_allow_html=True,
    )


st.markdown('<div class="section-title" style="font-size:14px">Published '
            '(derived solely from recorded approvals)</div>',
            unsafe_allow_html=True)
if not published:
    st.markdown('<div class="small-note">Nothing published yet — a '
                "recommendation appears here only after a recorded approval."
                "</div>", unsafe_allow_html=True)
for rec in published:
    _recommendation_card(rec, gated=False)

st.markdown('<div class="section-title" style="font-size:14px">Awaiting review '
            "(Publish Gate)</div>", unsafe_allow_html=True)
if not pending:
    st.markdown('<div class="small-note">No drafts awaiting review.</div>',
                unsafe_allow_html=True)
for rec in pending:
    _recommendation_card(rec, gated=True)
    if not rec.get("thread_id"):
        st.markdown('<div class="small-note">This draft has no gate thread yet '
                    "— actions activate when the orchestrated run reaches the "
                    "Publish Gate.</div>", unsafe_allow_html=True)
        continue
    b1, b2, b3 = st.columns(3)
    decision = None
    if b1.button("Approve", key=f"approve_{rec['id']}", type="primary"):
        decision = "approved"
    if b2.button("Reject", key=f"reject_{rec['id']}"):
        decision = "rejected"
    if b3.button("Request changes", key=f"changes_{rec['id']}"):
        decision = "needs_revision"
    if decision:
        # No optimistic state: only a confirmed backend response changes what
        # is displayed; on error the item stays exactly as it was (spec).
        _, err = api.post_gate_decision(rec["thread_id"], decision, reviewer)
        if err:
            st.error(f"Decision NOT recorded — the recommendation remains "
                     f"pending. {err}")
        else:
            st.success(f"Decision '{decision}' recorded by {reviewer}.")
            st.rerun()

# Sent back with Request-changes: unpublished, visibly awaiting revision —
# never blended with approved items (policymaker-dashboard spec).
if needs_revision:
    st.markdown('<div class="section-title" style="font-size:14px">Awaiting '
                "revision (changes requested)</div>", unsafe_allow_html=True)
    for rec in needs_revision:
        _recommendation_card(rec, gated=True)
        st.markdown('<div class="small-note">A reviewer requested changes — '
                    "this draft stays unpublished until revised and "
                    "re-approved.</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Verification review surface (§8 backend pending — 404-tolerant client side)
# --------------------------------------------------------------------------
st.markdown('<div class="section-title">Verification review</div>',
            unsafe_allow_html=True)
flagged, available = api.get_flagged_verifications()
if not available:
    st.markdown(
        '<div class="small-note">Flagged-verification review activates with '
        "the verification bolt-on (§8). Resolution badges above are already "
        "live: resolved clusters show “resolved — unverified” until a "
        "verification confirms them.</div>",
        unsafe_allow_html=True,
    )
elif not flagged:
    st.markdown('<div class="small-note">No flagged verification records.</div>',
                unsafe_allow_html=True)
for record in flagged:
    st.markdown(
        f'<div class="setu-card"><div class="card-title">'
        f'<span class="badge badge-flag">⚑ flagged — needs human review</span> '
        f'cluster {ui.num(record.get("demand_cluster_id", "")[:8])}</div>'
        f'<div class="card-meta">original complaint: '
        f'{ui.esc(record.get("cluster_summary", ""))}</div>'
        f'<div class="card-meta">follow-up media: '
        f'{ui.esc(record.get("media_paths", []))}</div></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    v_decision = None
    if c1.button("Confirm resolved", key=f"vc_{record['id']}", type="primary"):
        v_decision = "confirm_resolved"
    if c2.button("Reject resolution", key=f"vr_{record['id']}"):
        v_decision = "reject_resolution"
    if v_decision:
        _, err = api.post_verification_review(record["id"], v_decision, reviewer)
        if err:
            st.error(f"Review NOT recorded — the flag remains active. {err}")
        else:
            st.success("Review recorded.")
            st.rerun()
