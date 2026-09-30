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
6. **Decisions need a signed-in reviewer and land in the decision log.** New decision
   endpoints take the reviewer from the session token and call `audit.append` in the
   same transaction.
7. **Personal details never reach a model.** All model and embedding calls go through
   `app.llm` / `call_gemini`, which mask PII first — don't call a provider directly.

## Development setup

```bash
cp .env.example .env   # add GEMINI_API_KEY, REVIEWERS and SESSION_SECRET (see README)
docker compose up --build
docker compose exec backend python /app/seed/seed.py
```

Run the test suite (includes the equity-invariant test, which must stay green):

```bash
docker compose exec backend pytest tests/ -q
```

- **Schema changes** go in a new, idempotent `db/migrations/NNN_name.sql` (applied at
  backend start) — never edit `db/schema.sql` for an existing database.
- **Fixture store:** `backend/fixtures/` holds genuine recordings for `DEMO_REPLAY`.
  The test suite redirects all fixture writes to a temp directory; never commit mock
  replies there.
- **Test data** uses a `test-` submitter prefix so cleanup can restore the seed.

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
