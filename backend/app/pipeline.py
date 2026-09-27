"""§7 — LangGraph orchestration: the eight-stage Setu pipeline (design D2).

One graph, one node per stage, typed entity hand-offs carried as row ids in
the graph state (each stage function validates its input rows exist and its
output satisfies the entity contract — a violation raises and halts the run
at that stage). The Publish Gate is a genuine ``interrupt``: the run durably
suspends in the Postgres checkpointer (same database as everything else) and
only ``resume_gate`` — driven by ``POST /api/gate/{thread_id}/resume`` —
moves it. Verify (stage 8) runs post-resolution through this same module
(``run_verify``-style invocation lives with §8), not inline in this graph.

Failure posture (files/05): ``call_gemini`` already retries once; a second
failure raises ``GeminiUnavailable``, the run halts with RunTrace status
``needs_retry``, and the ops endpoints let an operator resume — LangGraph's
checkpoint means completed upstream stages are never re-executed.

Transactions: Track A stages (Understand/Locate/Cluster) commit themselves;
Track B stages (Fuse/Score/Recommend) do not — nodes here commit them. The
finalize node records the Approval and applies every status change in one
transaction, so a crash mid-resume leaves the thread suspended and nothing
half-published.
"""
import uuid
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import db, trace
from app.stages import cluster as cluster_stage
from app.stages import fuse as fuse_stage
from app.stages import locate as locate_stage
from app.stages import recommend as recommend_stage
from app.stages import score as score_stage
from app.stages import understand as understand_stage


class PipelineState(TypedDict, total=False):
    citizen_request_id: str
    structured_request_id: str
    geocoded_request_id: str
    cluster_id: str
    recommendation_id: str
    trace_id: str
    thread_id: str
    gate_resolution: dict  # {"decision": ..., "reviewer": ...} after resume


class NotSuspended(Exception):
    """Resume attempted on a thread that is unknown or not at the gate."""


# --- graph nodes -------------------------------------------------------------

def _understand(state: PipelineState) -> dict:
    with db.pool.connection() as conn:
        with trace.traced_stage(conn, state["trace_id"], "Understand",
                                input_ref=state["citizen_request_id"]) as e:
            sr_id = understand_stage.run(conn, state["citizen_request_id"])
            e["output_ref"] = sr_id
    return {"structured_request_id": sr_id}


def _locate(state: PipelineState) -> dict:
    with db.pool.connection() as conn:
        with trace.traced_stage(conn, state["trace_id"], "Locate",
                                input_ref=state["structured_request_id"]) as e:
            gr_id = locate_stage.run(conn, state["structured_request_id"])
            e["output_ref"] = gr_id
    return {"geocoded_request_id": gr_id}


def _cluster(state: PipelineState) -> dict:
    with db.pool.connection() as conn:
        with trace.traced_stage(conn, state["trace_id"], "Cluster",
                                input_ref=state["geocoded_request_id"]) as e:
            result = cluster_stage.run(conn, state["geocoded_request_id"])
            e["output_ref"] = result["cluster_id"]
            e["similarity"] = result.get("similarity")
            if result.get("alternatives"):
                e["alternatives"] = result["alternatives"]
    return {"cluster_id": result["cluster_id"]}


def _fuse(state: PipelineState) -> dict:
    with db.pool.connection() as conn:
        with trace.traced_stage(conn, state["trace_id"], "Fuse",
                                input_ref=state["cluster_id"]) as e:
            fused = fuse_stage.fuse_cluster(conn, state["cluster_id"])
            conn.commit()  # Track B stages do not commit
            e["output_ref"] = state["cluster_id"]
            e["facility_count"] = fused.get("facility_count")
    return {}


def _score(state: PipelineState) -> dict:
    with db.pool.connection() as conn:
        category = conn.execute(
            "SELECT category FROM demand_clusters WHERE id = %s",
            (state["cluster_id"],),
        ).fetchone()[0]
        with trace.traced_stage(conn, state["trace_id"], "Score",
                                input_ref=state["cluster_id"]) as e:
            score_stage.score_category(conn, category)
            conn.commit()
            e["output_ref"] = f"category:{category}"
    return {}


def _recommend(state: PipelineState) -> dict:
    with db.pool.connection() as conn:
        with trace.traced_stage(conn, state["trace_id"], "Recommend",
                                input_ref=state["cluster_id"]) as e:
            rec_id = recommend_stage.run(
                conn, state["cluster_id"], thread_id=state["thread_id"],
            )
            conn.commit()
            e["output_ref"] = rec_id
    return {"recommendation_id": rec_id}


def _publish_gate(state: PipelineState) -> dict:
    # Durable halt: execution stops HERE until the resume endpoint provides
    # {"decision", "reviewer"}. The value below is what get_state() exposes
    # to inspection while suspended.
    resolution = interrupt({
        "recommendation_id": state["recommendation_id"],
        "cluster_id": state["cluster_id"],
        "awaiting": "publish-gate approval",
    })
    return {"gate_resolution": resolution}


def _finalize(state: PipelineState) -> dict:
    """Record the Approval and apply the decision — one transaction."""
    decision = state["gate_resolution"]["decision"]
    reviewer = state["gate_resolution"]["reviewer"]
    rec_id = state["recommendation_id"]

    with db.pool.connection() as conn:
        with trace.traced_stage(conn, state["trace_id"], "Publish Gate",
                                input_ref=rec_id) as e:
            conn.execute(
                """INSERT INTO approvals (recommendation_id, decision, reviewer)
                   VALUES (%s, %s, %s)""",
                (rec_id, decision, reviewer),
            )
            if decision == "approved":
                conn.execute(
                    "UPDATE recommendations SET status='published' WHERE id=%s",
                    (rec_id,))
                # Activates the dashboard's mark-resolved flow (Track B contract).
                conn.execute(
                    """UPDATE demand_clusters SET status='published'
                       WHERE id=%s AND status='active'""",
                    (state["cluster_id"],))
                run_status = "published"
            elif decision == "rejected":
                conn.execute(
                    "UPDATE recommendations SET status='rejected' WHERE id=%s",
                    (rec_id,))
                run_status = "rejected"  # terminal; nothing deleted
            else:  # needs_revision — unpublished, visibly awaiting revision
                conn.execute(
                    "UPDATE recommendations SET status='needs_revision' WHERE id=%s",
                    (rec_id,))
                run_status = "awaiting_approval"
            conn.execute(
                "UPDATE run_traces SET status=%s WHERE id=%s",
                (run_status, state["trace_id"]))
            conn.commit()
            e["output_ref"] = f"approval:{decision} by {reviewer}"
    return {}


# --- graph assembly ----------------------------------------------------------

def _build_graph():
    g = StateGraph(PipelineState)
    g.add_node("understand", _understand)
    g.add_node("locate", _locate)
    g.add_node("cluster", _cluster)
    g.add_node("fuse", _fuse)
    g.add_node("score", _score)
    g.add_node("recommend", _recommend)
    g.add_node("publish_gate", _publish_gate)
    g.add_node("finalize", _finalize)
    g.add_edge(START, "understand")
    g.add_edge("understand", "locate")
    g.add_edge("locate", "cluster")
    g.add_edge("cluster", "fuse")
    g.add_edge("fuse", "score")
    g.add_edge("score", "recommend")
    g.add_edge("recommend", "publish_gate")
    g.add_edge("publish_gate", "finalize")
    g.add_edge("finalize", END)
    return g


_ckpt_pool: ConnectionPool | None = None
_graph = None


def graph():
    """The compiled graph with its Postgres checkpointer (lazy singleton)."""
    global _ckpt_pool, _graph
    if _graph is None:
        _ckpt_pool = ConnectionPool(
            db.DATABASE_URL, min_size=1, max_size=4,
            kwargs={"autocommit": True, "prepare_threshold": 0,
                    "row_factory": dict_row},
        )
        saver = PostgresSaver(_ckpt_pool)
        saver.setup()  # idempotent
        _graph = _build_graph().compile(checkpointer=saver)
    return _graph


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


# --- entry points ------------------------------------------------------------

def run_pipeline(citizen_request_id: str) -> str:
    """Ingest → gate: run stages 1–6 and suspend at the Publish Gate.

    Returns the thread_id. Any stage failure (including GeminiUnavailable
    after its single retry) halts the run as needs-retry — the CitizenRequest
    and all upstream outputs remain persisted; nothing is dropped.
    """
    thread_id = str(uuid.uuid4())
    with db.pool.connection() as conn:
        trace_id = trace.create_run_trace(conn, citizen_request_id, thread_id)
    try:
        graph().invoke(
            {"citizen_request_id": citizen_request_id,
             "trace_id": trace_id, "thread_id": thread_id},
            _config(thread_id),
        )
        # invoke returns at the interrupt: the run is durably suspended.
        with db.pool.connection() as conn:
            trace.set_status(conn, trace_id, "awaiting_approval")
    except Exception:
        with db.pool.connection() as conn:
            conn.rollback()
            trace.set_status(conn, trace_id, "needs_retry")
    return thread_id


def is_suspended_at_gate(thread_id: str) -> bool:
    """True iff this thread exists and is interrupted at the Publish Gate."""
    state = graph().get_state(_config(thread_id))
    if state is None or not state.next:
        return False
    return bool(state.tasks and any(t.interrupts for t in state.tasks))


def resume_gate(thread_id: str, decision: str, reviewer: str) -> dict:
    """Resolve a suspended gate. The ONLY gate-resolution mechanism (D2).

    Raises NotSuspended (→ 409, no state change) for an unknown or
    non-suspended thread. The Approval row and all status changes happen in
    the finalize node's single transaction.
    """
    if not is_suspended_at_gate(thread_id):
        raise NotSuspended(thread_id)
    graph().invoke(
        Command(resume={"decision": decision, "reviewer": reviewer}),
        _config(thread_id),
    )
    with db.pool.connection() as conn:
        row = conn.execute(
            """SELECT r.id::text, r.status::text FROM recommendations r
               WHERE r.thread_id = %s ORDER BY r.created_at DESC LIMIT 1""",
            (thread_id,),
        ).fetchone()
    return {"recommendation_id": row[0] if row else None,
            "status": row[1] if row else None}


def retry_run(trace_id: str) -> bool:
    """Operator retry of a needs-retry run: resume from the failed stage.

    LangGraph re-invokes from the last checkpoint, so completed upstream
    stages are not re-executed (orchestration spec). Returns True when the
    run reached the gate (or beyond) after the retry.
    """
    with db.pool.connection() as conn:
        row = conn.execute(
            """SELECT thread_id, status::text FROM run_traces WHERE id = %s""",
            (trace_id,),
        ).fetchone()
    if row is None or row[1] != "needs_retry":
        return False
    thread_id = row[0]
    try:
        graph().invoke(None, _config(thread_id))  # None: continue from checkpoint
        with db.pool.connection() as conn:
            trace.set_status(conn, trace_id, "awaiting_approval")
        return True
    except Exception:
        with db.pool.connection() as conn:
            conn.rollback()
            trace.set_status(conn, trace_id, "needs_retry")
        return False
