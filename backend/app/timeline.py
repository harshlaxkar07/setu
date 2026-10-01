"""Citizen-facing submission timeline (enhancements design D11).

Derived entirely from stored state — nothing is marked complete before it
happened. Stages, in order:

  received → understood → grouped → under_review → published → resolved

Each stage is `done`, `current` (the first not-yet-done stage) or `pending`.
Texts are bilingual (Hindi primary, English subtitle) for the chat widget.
"""
from typing import Any

import psycopg

STAGES = [
    ("received", "आपकी बात मिल गई", "Received"),
    ("understood", "हमने आपकी समस्या समझी", "Understood"),
    ("grouped", "आस-पास की शिकायतों के साथ जोड़ा गया", "Grouped with nearby reports"),
    ("under_review", "अधिकारी समीक्षा कर रहे हैं", "Under review by officials"),
    ("published", "सिफ़ारिश प्रकाशित हुई", "Recommendation published"),
    ("resolved", "समस्या हल होने की सूचना", "Reported resolved"),
]


def build(conn: psycopg.Connection, citizen_request_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT cr.created_at, sr.created_at, sr.summary,
                  cm.created_at, dc.id::text, dc.member_count, dc.status::text,
                  dc.centroid IS NOT NULL, dc.resolved_at,
                  (SELECT status::text FROM run_traces
                   WHERE citizen_request_id = cr.id
                   ORDER BY created_at DESC LIMIT 1)
           FROM citizen_requests cr
           LEFT JOIN structured_requests sr ON sr.citizen_request_id = cr.id
           LEFT JOIN geocoded_requests gr ON gr.structured_request_id = sr.id
           LEFT JOIN cluster_memberships cm ON cm.geocoded_request_id = gr.id
           LEFT JOIN demand_clusters dc ON dc.id = cm.demand_cluster_id
           WHERE cr.id = %s""",
        (citizen_request_id,),
    ).fetchone()
    if row is None:
        return None
    (received_at, understood_at, summary, grouped_at, cluster_id, members,
     cluster_status, located, resolved_at, run_status) = row

    rec = None
    if cluster_id:
        rec = conn.execute(
            """SELECT status::text, created_at FROM recommendations
               WHERE demand_cluster_id = %s ORDER BY created_at DESC LIMIT 1""",
            (cluster_id,)).fetchone()

    done: dict[str, Any] = {"received": {"at": received_at}}
    if understood_at:
        done["understood"] = {"at": understood_at}
    if grouped_at and located:
        others = max((members or 1) - 1, 0)
        done["grouped"] = {"at": grouped_at, "others": others,
                           "detail_hi": f"{others} और लोगों की शिकायतों के साथ",
                           "detail_en": f"with {others} others"}
    published_states = ("published", "resolved_unverified", "resolved_verified")
    if cluster_status in published_states or (rec and rec[0] == "published"):
        done["under_review"] = {}
        done["published"] = {}
    if cluster_status in ("resolved_unverified", "resolved_verified"):
        verified = cluster_status == "resolved_verified"
        done["resolved"] = {
            "at": resolved_at, "verified": verified,
            "detail_hi": "पुष्टि हो गई" if verified else "पुष्टि बाक़ी — आपकी राय माँगी जाएगी",
            "detail_en": "verified" if verified else "awaiting verification — we will ask you",
        }

    stages, current_set = [], False
    for key, hi, en in STAGES:
        info = done.get(key)
        if info is not None:
            state = "done"
        elif not current_set:
            state, current_set = "current", True
            info = {}
            if key == "understood" and run_status == "needs_retry":
                info = {"detail_hi": "थोड़ी देर में दोबारा कोशिश होगी",
                        "detail_en": "will be retried shortly"}
            if key == "grouped" and grouped_at and not located:
                info = {"detail_hi": "जगह का नाम बताइए", "detail_en": "waiting for the place name"}
            if key == "under_review" and rec is not None:
                if rec[0] == "needs_revision":
                    info = {"detail_hi": "अधिकारियों ने बदलाव माँगे", "detail_en": "changes requested"}
                elif rec[0] == "rejected":
                    info = {"detail_hi": "इस बार स्वीकृत नहीं हुई", "detail_en": "not approved this time"}
        else:
            state, info = "pending", {}
        stages.append({"key": key, "label_hi": hi, "label_en": en, "state": state,
                       **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                          for k, v in info.items()}})
    return {"request_id": citizen_request_id, "cluster_id": cluster_id,
            "summary": summary, "stages": stages}
