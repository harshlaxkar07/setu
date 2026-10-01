"""Scoped replay policy for evaluation; normal demo replay still allows misses."""
import os
from contextlib import contextmanager
from contextvars import ContextVar

_policy = ContextVar("replay_policy", default=None)


class MissingRecording(RuntimeError):
    """Offline evaluation cannot continue without a genuine recording."""


def enabled() -> bool:
    policy = _policy.get()
    return policy[0] if policy is not None else os.getenv("DEMO_REPLAY", "0") == "1"


def require_recording(kind: str) -> None:
    policy = _policy.get()
    if policy is not None and policy[1]:
        raise MissingRecording(f"Missing {kind} recording; run evaluation live first")


@contextmanager
def mode(*, replay: bool, strict: bool = False):
    token = _policy.set((replay, strict))
    try:
        yield
    finally:
        _policy.reset(token)
