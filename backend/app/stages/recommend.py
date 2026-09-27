"""Recommend stage (§5, task 5.7): one evidence-cited draft Recommendation.

Gemini (via the shared schema-bound ``call_gemini`` wrapper) drafts exactly one
intervention — ``intervention_text`` plus a structured ``intervention_type`` —
for a scored DemandCluster, naming the PriorityIndicators that justify it.

Citation enforcement (fusion-scoring spec "Uncited recommendation output is
rejected"):

  - the cluster citation is the NOT NULL ``demand_cluster_id`` FK — a draft
    cannot be stored without it;
  - the model must cite at least one *real* indicator of the cluster; an output
    whose cited indicators are empty or resolve to nothing raises
    ``RecommendationRejected`` and stores nothing (the schema-level CHECK on
    ``recommendations.indicator_citations`` backs this up in the database);
  - a structurally malformed draft (missing fields) fails ``call_gemini``'s
    schema validation before this module ever sees it.

The draft lands in status ``pending`` — publication is the Publish Gate's job
(§7), never this stage's.
"""
from typing import Any

import psycopg
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from app.gemini import call_gemini

# Suggested structured types; the prompt steers to these but any non-empty
# type is accepted (the structure requirement is "typed", not "enum-locked").
INTERVENTION_TYPES = (
    "new_infrastructure",
    "repair_restoration",
    "supply_augmentation",
    "survey_assessment",
)


class RecommendationDraft(BaseModel):
    """Schema bound onto the Gemini call — malformed output fails validation."""

    intervention_text: str = Field(min_length=1)
    intervention_type: str = Field(min_length=1)
    # Names of the PriorityIndicators justifying the draft. Deliberately allowed
    # to be empty at the schema layer so the *citation* rejection is exercised
    # by this stage's own check (and is testable as its own failure path).
    cited_indicators: list[str] = Field(default_factory=list)


class RecommendationRejected(Exception):
    """Draft lacked its indicator citations — rejected, never stored."""


def _load_evidence(conn: psycopg.Connection, cluster_id: str) -> dict[str, Any]:
    """Cluster summary, latest score, and indicators — the prompt's evidence."""
    cluster = conn.execute(
        """SELECT category, representative_summary, member_count
           FROM demand_clusters WHERE id = %s""",
        (cluster_id,),
    ).fetchone()
    if cluster is None:
        raise LookupError(f"demand_cluster {cluster_id} not found")

    score = conn.execute(
        """SELECT score, gap_norm, investment_deficit_norm, volume_norm
           FROM priority_scores WHERE demand_cluster_id = %s
           ORDER BY created_at DESC LIMIT 1""",
        (cluster_id,),
    ).fetchone()
    if score is None:
        raise ValueError(
            f"cluster {cluster_id} has no PriorityScore — run Score before Recommend"
        )

    indicators = conn.execute(
        """SELECT id, name, value_text, value_numeric
           FROM priority_indicators WHERE demand_cluster_id = %s
           ORDER BY created_at""",
        (cluster_id,),
    ).fetchall()
    if not indicators:
        raise ValueError(f"cluster {cluster_id} has no PriorityIndicators to cite")

    return {
        "category": cluster[0],
        "summary": cluster[1],
        "member_count": cluster[2],
        "score": float(score[0]),
        "indicators": [
            {"id": str(i[0]), "name": i[1], "value_text": i[2],
             "value_numeric": float(i[3]) if i[3] is not None else None}
            for i in indicators
        ],
    }


def _build_prompt(evidence: dict[str, Any]) -> str:
    lines = [
        "You are drafting ONE public-infrastructure intervention recommendation "
        "for a district policymaker, grounded ONLY in the evidence below.",
        "",
        f"Demand cluster category: {evidence['category']}",
        f"Representative summary: {evidence['summary']}",
        f"Composite priority score: {evidence['score']:.3f}",
        "",
        "Priority indicators (cite the exact names of those that justify your draft):",
    ]
    for ind in evidence["indicators"]:
        lines.append(f"- {ind['name']}: {ind['value_text'] or ind['value_numeric']}")
    lines += [
        "",
        "Respond with JSON only, matching exactly:",
        '{"intervention_text": "<2-4 sentence concrete intervention>", '
        f'"intervention_type": "<one of {", ".join(INTERVENTION_TYPES)}>", '
        '"cited_indicators": ["<indicator name>", ...]}',
        "cited_indicators MUST list the exact indicator names (from above) that "
        "justify the intervention — an uncited draft is rejected.",
    ]
    return "\n".join(lines)


def run(
    conn: psycopg.Connection,
    cluster_id: str,
    thread_id: str | None = None,
    _caller=None,
) -> str:
    """Draft one cited Recommendation for a scored cluster; return its id.

    ``thread_id`` is set by the orchestrator (§7) when the run is a LangGraph
    thread heading to the Publish Gate. ``_caller`` is passed straight through
    to ``call_gemini`` for test injection — tests never call live Gemini.
    Does not commit; the caller owns the transaction.
    """
    evidence = _load_evidence(conn, cluster_id)

    draft: RecommendationDraft = call_gemini(
        stage="recommend",
        prompt=_build_prompt(evidence),
        schema=RecommendationDraft,
        _caller=_caller,
    )

    # Resolve cited names against the cluster's real indicators (case-insensitive).
    by_name = {ind["name"].lower(): ind for ind in evidence["indicators"]}
    cited = [
        by_name[name.strip().lower()]
        for name in draft.cited_indicators
        if name.strip().lower() in by_name
    ]
    if not cited:
        raise RecommendationRejected(
            f"recommend({cluster_id}): draft cited no valid PriorityIndicators "
            f"(model gave {draft.cited_indicators!r}) — rejected, not stored"
        )

    indicator_citations = [
        {
            "indicator_id": ind["id"],
            "name": ind["name"],
            "value": ind["value_text"] or ind["value_numeric"],
        }
        for ind in cited
    ]

    row = conn.execute(
        """
        INSERT INTO recommendations
            (demand_cluster_id, intervention_text, intervention_type,
             indicator_citations, status, thread_id)
        VALUES (%s, %s, %s, %s, 'pending', %s)
        RETURNING id
        """,
        (cluster_id, draft.intervention_text, draft.intervention_type,
         Json(indicator_citations), thread_id),
    ).fetchone()
    return str(row[0])
