# Setu (सेतु)

**Bridge citizen voice to evidence-backed development intelligence.**

Setu turns fragmented, multilingual citizen feedback — a Hindi voice note about a
broken water supply, a Marathi message about a washed-out road — into transparent,
evidence-cited prioritization intelligence for policymakers. AI recommends; humans
decide. Every score shows its factors; every "resolved" claim gets verified.

> Setu is **not** "AI decides which government project gets funded." It is:
> *AI turns fragmented, multilingual citizen feedback into transparent, evidence-cited
> development intelligence — so policymakers can see where need is greatest, and why.*

## What it does

| | |
|---|---|
| **Listen** | Voice-first chat page in Hindi, Marathi or English (text too). No name or phone number, ever. Field workers can report for a village with an offline queue (`?mode=assisted`). |
| **Understand** | Local speech-to-text (Faster-Whisper), then an LLM extracts category, urgency, summary, language and the place mentioned. Personal details are masked before any model sees the text. |
| **Locate** | OpenStreetMap geocoding with fallbacks for informal places ("वेल्हे गाँव", "near Aundh Health Centre"); if still unknown, the chat asks once. |
| **Aggregate** | Reports on the same problem nearby join one demand cluster (meaning + distance). |
| **Validate** | Anti-manipulation: duplicate bursts, one source flooding, sudden spikes are **flagged with a reason — never deleted** — and don't count toward priority until a reviewer clears them. |
| **Compare** | Clusters are fused with population, facility and investment data. |
| **Prioritize** | `PriorityScore = 0.5·gap + 0.3·investment_deficit + 0.2·volume` — complaint volume can never outrank the infrastructure gap. |
| **Recommend** | One evidence-cited draft per cluster, held at the **Publish Gate** until a signed-in reviewer decides. |
| **Act & measure** | Resolution is a claim until a citizen follow-up verifies it; impact compares complaints and gap before vs after. |
| **Beyond the queue** | *Silent regions* (high need, no reports), a complaint-count vs Setu ranking comparison, an investment planner, bilingual one-page policy briefs, and a tamper-evident decision log. |

## Architecture

```
citizen-web/   Static chat page (hi/mr/en, voice-first, assisted mode), served by the backend
backend/       FastAPI + LangGraph pipeline:
               Understand → Locate → Cluster → Trust → Fuse → Score → Recommend
               → Publish Gate (durable human interrupt) → Verify
               Postgres checkpointer · provider layer (Gemini or any OpenAI-compatible model)
dashboard/     Streamlit policymaker dashboard (live map, gate, trust, equity, planner, audit)
db/            Postgres + PostGIS + pgvector: base schema, additive migrations, seed data
scripts/       Demo & operator tools (spam attack, share with judges, reviewer passcodes)
openspec/      Specs and change plans
```

One `docker compose up` runs everything. Migrations in `db/migrations/` apply
automatically at backend start.

## Quick start

```bash
cp .env.example .env                    # then fill in GEMINI_API_KEY (see below)
python3 scripts/hash_passcode.py "Demo Reviewer"   # prints a REVIEWERS entry
# paste it into .env as REVIEWERS=..., and set SESSION_SECRET to a long random string:
python3 -c "import secrets; print(secrets.token_hex(32))"
docker compose up --build -d
docker compose exec backend python /app/seed/seed.py   # seed the demo dataset
```

- Citizen chat page: http://localhost:8000/citizen (field workers: `/citizen/?mode=assisted`)
- Policymaker dashboard: http://localhost:8501 — viewing is open; sign in on the
  **Publish Gate** tab to approve, reject or review
- API health: http://localhost:8000/health
- Postgres (host tools): localhost:5434, user `setu`, db `setu`

Run the test suite (the equity-invariant test must stay green for every category):

```bash
docker compose exec backend pytest tests/ -q
```

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio key (free tier) — default model and embeddings |
| `DEMO_REPLAY` | `1` = answer from recorded fixtures first (demo can't be sunk by rate limits) |
| `REVIEWERS` | `Name=<salt>.<hash>;Other=<salt>.<hash>` — create entries with `scripts/hash_passcode.py` |
| `SESSION_SECRET` | Signs reviewer sessions (any long random string) |
| `LLM_PROVIDER` | `gemini` (default) or `openai_compat` for a local / sovereign model |
| `LLM_BASE_URL`, `LLM_MODEL`, `EMBED_MODEL`, `LLM_API_KEY` | For `openai_compat`, e.g. Ollama at `http://host.docker.internal:11434/v1`; embeddings must be 768-dimensional |
| `SCORING_DATASET` | `synthetic` (default seed) or `openstreetmap` after importing real facilities |

## Manual setup items

1. **`GEMINI_API_KEY`** — used for extraction, recommendation drafting, verification
   vision checks and `gemini-embedding-001` (768-dim) embeddings. The free tier has a
   daily limit; record the demo path once and use `DEMO_REPLAY=1`.
2. **Reviewer accounts** — at least one `REVIEWERS` entry, or nobody can approve.
3. **One-time Whisper model download** — the Faster-Whisper `small` model downloads on
   first transcription and persists in the `whisper-models` volume. Do this early.
4. **Record the rehearsed Hindi line on the real demo microphone** and check
   transcription (target: ≥8/10 correct on the demo set).

## Demo script (about 7 minutes)

1. **Citizen** — on a phone-sized window open `/citizen`, switch to मराठी and back,
   hold the mic: *"हमारे गाँव वेल्हे में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।"*
   The receipt appears, then a live timeline: received → understood → **grouped with
   20 others** → under review.
2. **Dashboard** — Velhe's card updates by itself (live refresh). Open **Equity**:
   Kothrud has 25× more complaints, yet Velhe ranks first — and why.
3. **Publish Gate** — sign in, approve. The citizen's timeline moves to *published*
   within seconds. Download the **policy brief** (bilingual, one page).
4. **Spam attack** — `python3 scripts/spam_attack.py --count 300` (run the backend
   with `DEMO_REPLAY=1` so copies replay one recorded reply). **Trust & trends** shows
   the spike as flagged; the cluster counts only unflagged reports; its rank holds;
   one gate item for the whole attack.
5. **Silent regions** — map toggle: villages like Kurunji and Tamhini with no reports
   but no facility at all. **Planner**: 3 health centres → Paud, Pabe, Kurunji,
   13,300 people newly covered.
6. **Impact** — select the resolved Paud sanitation cluster: complaints 40 → 5 after
   resolution, gap 6,000 → 3,000 people per facility, still "resolved — unverified"
   until a citizen confirms.
7. **Audit** — the decision chain verifies intact; any edited decision would be
   reported by entry number.

### Before the demo

1. `python3 db/seed/verify_locations.py` — every demo location resolves live.
2. Reseed: `docker compose exec backend python /app/seed/seed.py` (cached embeddings —
   zero API calls; also clears decision log and test traffic).
3. Rehearse once live (records fixtures), then set `DEMO_REPLAY=1` and
   `docker compose up -d backend`.
4. Optional — let judges report from their own phones: `scripts/share.sh` (needs
   `brew install cloudflared qrencode`; prints a public link and QR code; read the
   privacy note it shows; Ctrl+C stops sharing).

## Operator tools

| Command | What it does |
|---|---|
| `python3 scripts/spam_attack.py --count 300 [--single-source]` | Coordinated-spam demo through the public API |
| `scripts/share.sh` | Temporary public link + QR for the citizen page (opt-in) |
| `python3 scripts/hash_passcode.py "Name"` | Create a reviewer account entry |
| `docker compose exec backend python /app/seed/import_osm.py healthcare` | Import real OpenStreetMap facilities as a labelled dataset |
| `docker compose exec backend python -m eval.run_eval [--replay]` | Accuracy report over the labelled multilingual set |
| `docker compose exec backend python -m eval.scale_test --n 10000` | Clustering throughput (no network, database left unchanged) |

## Evidence

- **Tests:** 216 automated tests, including the equity invariant for water, healthcare
  and roads, a 300-request spam attack end to end, tamper detection on the decision
  log, and concurrency checks on the Publish Gate.
- **Scale:** 10,000 synthetic requests clustered by the real Cluster stage in 68.9 s
  (145 requests/s) on a laptop; 9,742 joined existing clusters, 258 founded new ones.
- **Accuracy:** `backend/eval/dataset.jsonl` holds 56 labelled messages (Hindi,
  Hinglish, English, Marathi; informal places). Run `python -m eval.run_eval` once live
  to produce `eval/report.json` — figures are pending the first live run.

## About the data

The demo dataset is **synthetic but realistic**, and we state that openly. Population
figures are proportioned against Census 2011 Pune-district numbers; facility
locations and investment labels reproduce three equity pairs (water: Kothrud vs Velhe,
healthcare: Aundh vs Paud, roads: Hadapsar vs Ghisar) plus three villages with no
reports at all. Real OpenStreetMap facilities can be imported as a separate, labelled
dataset; scoring uses the seed unless `SCORING_DATASET=openstreetmap`.

## Scoring transparency

```
PriorityScore = 0.5·gap_norm + 0.3·investment_deficit_norm + 0.2·volume_norm
```

Weights are literal code constants. Complaint volume's weight (0.2) is structurally
below the infrastructure-gap weight (0.5), so volume can never override gap — enforced
by construction and by an automated test on every seeded category. Requests flagged as
suspected manipulation are left out of `volume` (and the dashboard says so).

## Privacy & governance

- No name, phone or identity field anywhere; citizens are a random conversation id.
- Phone numbers, Aadhaar-like numbers, emails and self-introduced names are masked
  before any model or embedding call; run traces record the masked text.
- Decisions require a signed-in reviewer; the recorded name comes from the session.
- Every decision is appended to a hash-chained log (`GET /api/audit/verify`).

## License

[MIT](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) to get involved.
