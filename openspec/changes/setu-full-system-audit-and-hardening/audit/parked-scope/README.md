# Parked scope — NOT part of this change

During planning, workflow agents injected an "API-first analytics platform &
dashboard rework" scope (these six spec drafts, design decisions AD12–AD15,
tasks sections 4–9, BRIEF DoD items 26–48) that was never part of the user's
audit-and-hardening mandate. It was removed from the active artifacts to keep
this change faithful to its brief: audit and harden the EXISTING system, no
rebuilds, no speculative refactors.

The drafts are preserved here because they are substantial and may be wanted
later. If so, they deserve their own change (e.g.
`/opsx:propose setu-analytics-api-platform`) where the scope can be judged on
its merits. Note two factual corrections for any future revival: the dashboard
already consumes ONLY the backend API (design D6 of build-setu-mvp — it has no
DB credentials), and the verification review queue is already API-backed (§8
endpoints); those drafts overstate the current gap.
