# Contributing to Setu

Thanks for your interest! Setu is a hackathon-born open-source project; contributions
are welcome.

## Ground rules (from the project's governing principles)

1. **No PriorityScore without its factors shown.** Any change that surfaces a number
   must keep its contributing factors reachable in the same view.
2. **Complaint volume never overrides InfrastructureGapScore.** The scoring weights are
   code constants on purpose — PRs making them runtime-configurable will be declined.
3. **Flag, never silently drop.** Suspicious/failed data gets a lower ConfidenceLevel
   and a stated reason; nothing is deleted without a human decision.
4. **The Publish Gate is backend-enforced.** Nothing policymaker-facing may bypass the
   LangGraph interrupt + Approval record path.
5. **Raw citizen input is immutable.** Corrections are new derived objects.

## Development setup

```bash
cp .env.example .env   # add your GEMINI_API_KEY
docker compose up --build
```

Run the test suite (includes the equity-invariant test, which must stay green):

```bash
docker compose exec backend pytest
```

## Workflow

- The project plans changes with [OpenSpec](openspec/) — significant behavior changes
  should update the relevant spec under `openspec/specs/` via a change proposal.
- Keep PRs small and single-purpose; reference the requirement or scenario your change
  serves.
- Match the existing code style; every module has type hints and docstrings on public
  functions.

## Reporting issues

Open a GitHub issue with reproduction steps. For anything touching citizen data
handling or privacy posture, tag it `privacy` — those get priority review.
