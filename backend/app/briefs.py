"""Bilingual per-cluster policy brief (enhancements design D12).

A self-contained, print-ready HTML page (one A4 sheet; "Save as PDF" from the
browser) built ONLY from data stored for the cluster: summary, location,
category, volumes, every priority indicator, the score breakdown, and the
latest recommendation with its approval status. Headings, labels and status
statements are in English and Hindi; stored text (summary, indicator values,
the AI-drafted recommendation) is shown as stored — nothing is generated or
translated here. Anything not approved carries a draft watermark.
"""
import html
from datetime import datetime, timezone
from typing import Any

import psycopg

from app.stages.fuse import region_for_cluster

CATEGORY_HI = {
    "water_infrastructure": "पानी", "road_infrastructure": "सड़क",
    "healthcare": "स्वास्थ्य सेवा", "sanitation": "सफ़ाई", "electricity": "बिजली",
    "education": "शिक्षा", "transportation": "यातायात",
    "digital_connectivity": "इंटरनेट/नेटवर्क", "other": "अन्य",
}
INDICATOR_HI = {
    "population affected": "प्रभावित आबादी",
    "distance to nearest functioning source": "निकटतम चालू सुविधा की दूरी",
    "historical investment": "पिछला निवेश",
    "complaint volume": "शिकायतों की संख्या",
    "possible under-representation signal": "संभावित कम-प्रतिनिधित्व संकेत",
}


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _bi(en: str, hi: str) -> str:
    return f'{_e(en)} <span class="hi">/ {_e(hi)}</span>'


def load(conn: psycopg.Connection, cluster_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT dc.category, dc.representative_summary, dc.member_count,
                  dc.status::text, dc.confidence::text, dc.confidence_reason,
                  ST_Y(dc.centroid), ST_X(dc.centroid),
                  ps.score, ps.gap_norm, ps.investment_deficit_norm, ps.volume_norm,
                  ps.weights
           FROM demand_clusters dc
           LEFT JOIN LATERAL (SELECT * FROM priority_scores WHERE demand_cluster_id = dc.id
                              ORDER BY created_at DESC LIMIT 1) ps ON true
           WHERE dc.id = %s""", (cluster_id,)).fetchone()
    if row is None:
        return None
    (category, summary, members, status, confidence, reason, lat, lon,
     score, gap_n, inv_n, vol_n, weights) = row
    indicators = conn.execute(
        """SELECT name, value_text, value_numeric FROM priority_indicators
           WHERE demand_cluster_id = %s ORDER BY name""", (cluster_id,)).fetchall()
    counted = next((float(v) for n, _, v in indicators if n == "complaint volume" and v is not None),
                   None)
    rec = conn.execute(
        """SELECT r.id::text, r.intervention_text, r.intervention_type, r.status::text,
                  r.indicator_citations, a.reviewer, a.decided_at
           FROM recommendations r
           LEFT JOIN LATERAL (SELECT reviewer, decided_at FROM approvals
                              WHERE recommendation_id = r.id AND decision = 'approved'
                              ORDER BY decided_at DESC LIMIT 1) a ON true
           WHERE r.demand_cluster_id = %s
           ORDER BY r.created_at DESC LIMIT 1""", (cluster_id,)).fetchone()
    region = region_for_cluster(conn, cluster_id)["name"] if lat is not None else None
    return {
        "id": cluster_id, "category": category, "summary": summary, "members": members,
        "counted": int(counted) if counted is not None else members, "status": status,
        "confidence": confidence, "confidence_reason": reason, "region": region,
        "lat": lat, "lon": lon,
        "score": float(score) if score is not None else None,
        "components": None if score is None else {
            "gap": (weights["gap"], float(gap_n)),
            "investment_deficit": (weights["investment_deficit"], float(inv_n)),
            "volume": (weights["volume"], float(vol_n))},
        "indicators": [{"name": n, "text": t, "value": v} for n, t, v in indicators],
        "recommendation": None if rec is None else {
            "id": rec[0], "text": rec[1], "type": rec[2], "status": rec[3],
            "citations": rec[4], "approved_by": rec[5], "approved_at": rec[6]},
    }


def render(data: dict[str, Any]) -> str:
    rec = data["recommendation"]
    approved = bool(rec and rec["approved_by"] and rec["status"] == "published")
    cat_hi = CATEGORY_HI.get(data["category"], data["category"])
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    ind_rows = "".join(
        f"<tr><td>{_bi(i['name'], INDICATOR_HI.get(i['name'], i['name']))}</td>"
        f"<td>{_e(i['text'] if i['text'] else i['value'])}</td></tr>"
        for i in data["indicators"])
    if data["components"]:
        labels = {"gap": ("Infrastructure gap", "बुनियादी ढाँचे की कमी"),
                  "investment_deficit": ("Investment deficit", "निवेश की कमी"),
                  "volume": ("Complaint volume", "शिकायतों की संख्या")}
        brk = "".join(
            f"<tr><td>{_bi(*labels[k])}</td><td class='num'>{w} × {n:.3f} = {w * n:.3f}</td></tr>"
            for k, (w, n) in data["components"].items())
        brk += (f"<tr class='total'><td>{_bi('PriorityScore', 'प्राथमिकता स्कोर')}</td>"
                f"<td class='num'>{data['score']:.3f}</td></tr>")
    else:
        brk = f"<tr><td colspan='2'>{_bi('Not scored yet', 'अभी स्कोर नहीं हुआ')}</td></tr>"

    if rec is None:
        rec_html = f"<p class='muted'>{_bi('No recommendation drafted yet.', 'अभी कोई सिफ़ारिश तैयार नहीं हुई।')}</p>"
    else:
        if approved:
            status = _bi(f"Approved by {rec['approved_by']} on "
                         f"{rec['approved_at']:%d %b %Y, %H:%M UTC}",
                         f"{rec['approved_by']} द्वारा {rec['approved_at']:%d-%m-%Y} को स्वीकृत")
        else:
            state = {"pending": ("Awaiting review", "समीक्षा बाक़ी"),
                     "needs_revision": ("Changes requested", "बदलाव माँगे गए"),
                     "rejected": ("Not approved", "स्वीकृत नहीं")}.get(
                         rec["status"], (rec["status"], rec["status"]))
            status = _bi(*state)
        cited = ", ".join(_e(c.get("name")) for c in (rec["citations"] or []))
        rec_html = (
            f"<p class='ai'>✦ AI-drafted / AI द्वारा तैयार — {_e(rec['type'].replace('_', ' '))}</p>"
            f"<p class='rec'>{_e(rec['text'])}</p>"
            f"<p class='muted'>{_bi('Evidence cited', 'उद्धृत प्रमाण')}: {cited}</p>"
            f"<p class='status {'ok' if approved else 'draft'}'>{status}</p>")

    location = data["region"] or "—"
    coords = (f" ({data['lat']:.4f}, {data['lon']:.4f})" if data["lat"] is not None else "")
    excluded = data["members"] - data["counted"]
    volume = f"{data['members']:,}"
    if excluded:
        volume += f" ({data['counted']:,} counted; {excluded:,} excluded as suspected manipulation)"
    watermark = "" if approved else (
        "<div class='watermark'>DRAFT — AWAITING REVIEW<br>ड्राफ़्ट — समीक्षा बाक़ी</div>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Setu policy brief — {_e(data['summary'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;600&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>
  @page {{ size: A4; margin: 13mm 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Inter, 'Noto Sans Devanagari', sans-serif; color: #17212B;
         font-size: 10.5pt; line-height: 1.35; margin: 0; }}
  .hi {{ font-family: 'Noto Sans Devanagari', sans-serif; color: #5B6572; font-weight: 400; }}
  header {{ border-bottom: 3px solid #2B5FA8; padding-bottom: 6px; margin-bottom: 10px;
            display: flex; justify-content: space-between; align-items: flex-end; }}
  header .mark {{ font-size: 18pt; font-weight: 700; color: #1E4478; }}
  header .meta {{ font-size: 8.5pt; color: #5B6572; text-align: right; }}
  h1 {{ font-size: 14pt; margin: 4px 0 2px; }}
  h2 {{ font-size: 11pt; color: #1E4478; margin: 12px 0 4px;
        border-bottom: 1px solid #E3E7EC; padding-bottom: 2px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 3px 4px; border-bottom: 1px dashed #E3E7EC; vertical-align: top; }}
  td:first-child {{ width: 42%; color: #5B6572; }}
  .num {{ font-family: 'IBM Plex Mono', monospace; }}
  tr.total td {{ font-weight: 700; border-bottom: none; color: #17212B; }}
  .facts td:first-child {{ width: 30%; }}
  .ai {{ color: #0E8C7F; font-weight: 600; font-size: 9pt; margin: 2px 0; }}
  .rec {{ font-size: 11pt; margin: 4px 0; }}
  .muted {{ color: #5B6572; font-size: 9pt; margin: 2px 0; }}
  .status {{ font-weight: 700; margin: 6px 0 0; padding: 4px 8px; border-radius: 6px;
             display: inline-block; }}
  .status.ok {{ background: #E4F3EA; color: #1E7F4F; }}
  .status.draft {{ background: #FBF0DC; color: #B26B00; }}
  footer {{ margin-top: 12px; font-size: 8pt; color: #8C95A1; border-top: 1px solid #E3E7EC;
            padding-top: 4px; }}
  .watermark {{ position: fixed; top: 38%; left: 0; right: 0; text-align: center;
                font-size: 34pt; font-weight: 700; color: rgba(178, 107, 0, 0.13);
                transform: rotate(-24deg); pointer-events: none; line-height: 1.2; }}
</style></head>
<body>
{watermark}
<header>
  <div><div class="mark">Setu <span class="hi">/ सेतु</span></div>
       <div class="muted">{_bi('Policy brief — evidence-backed development intelligence', 'नीति सार — प्रमाण-आधारित विकास जानकारी')}</div></div>
  <div class="meta">{_bi('Generated', 'तैयार')}: {generated}<br>{_bi('Cluster', 'समूह')}: <span class="num">{_e(data['id'][:8])}</span></div>
</header>
<h1>{_e(data['summary'])}</h1>
<table class="facts">
  <tr><td>{_bi('Location', 'स्थान')}</td><td>{_e(location)}{_e(coords)}</td></tr>
  <tr><td>{_bi('Category', 'श्रेणी')}</td><td>{_e(data['category'].replace('_', ' '))} <span class="hi">/ {_e(cat_hi)}</span></td></tr>
  <tr><td>{_bi('Citizen requests', 'नागरिक शिकायतें')}</td><td class="num">{_e(volume)}</td></tr>
  <tr><td>{_bi('Data confidence', 'डेटा विश्वसनीयता')}</td><td>{_e(data['confidence'])}{(' — ' + _e(data['confidence_reason'])) if data['confidence_reason'] else ''}</td></tr>
</table>
<h2>{_bi('Priority indicators', 'प्राथमिकता संकेतक')}</h2>
<table>{ind_rows}</table>
<h2>{_bi('Score breakdown', 'स्कोर का विवरण')}</h2>
<table>{brk}</table>
<h2>{_bi('Recommendation', 'सिफ़ारिश')}</h2>
{rec_html}
<footer>
  {_bi('Advisory: AI recommends, authorised officials decide. Every figure above is stored evidence for this cluster; the recommendation text is shown exactly as drafted.',
       'सलाहकारी: AI सुझाव देता है, निर्णय अधिकृत अधिकारी लेते हैं। ऊपर के सभी आँकड़े इस समूह के संग्रहीत प्रमाण हैं; सिफ़ारिश का पाठ जैसा तैयार हुआ वैसा ही दिखाया गया है।')}
</footer>
</body></html>"""
