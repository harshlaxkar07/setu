# Setu (सेतु)

**Bridge citizen voice to evidence-backed development intelligence.**

Setu turns fragmented, multilingual citizen feedback — a Hindi voice note about a broken
water supply — into transparent, evidence-cited prioritization intelligence for
policymakers. AI recommends; humans decide. Every score shows its factors; every
"resolved" claim gets verified.

> Setu is **not** "AI decides which government project gets funded." It is:
> *AI turns fragmented, multilingual citizen feedback into transparent, evidence-cited
> development intelligence — so policymakers can see where need is greatest, and why.*

## The demo scenario

A citizen sends a Hindi voice message through a WhatsApp-style chat page:

> "हमारे गाँव में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।"

The pipeline transcribes it locally (Faster-Whisper), understands it (Gemini),
geocodes it (Nominatim), clusters it with similar nearby complaints (pgvector +
PostGIS), fuses it with population/infrastructure data, scores the gap
independently of complaint volume, drafts an evidence-cited recommendation — and
**halts at the Publish Gate** until a human reviewer approves it on the dashboard.
After a cluster is marked resolved, a citizen follow-up photo is plausibility-checked;
a mismatch is flagged for human review, never auto-closed.

## Architecture

```
citizen-web/   Static bilingual chat page (voice-first), served by the backend
backend/       FastAPI + LangGraph pipeline (Understand → Locate → Cluster → Fuse
               → Score → Recommend → Publish Gate → Verify), Postgres checkpointer
dashboard/     Streamlit policymaker dashboard (map, priority cards, gate actions)
db/            Postgres + PostGIS + pgvector schema (the data contract) and seeds
```

One `docker-compose up` runs all three services.

## Quick start

```bash
cp .env.example .env        # then fill in GEMINI_API_KEY (see below)
docker compose up --build -d
docker compose exec backend python /app/seed/seed.py   # seed the demo dataset
```

- Citizen chat page: http://localhost:8000/citizen
- Policymaker dashboard: http://localhost:8501
- API health: http://localhost:8000/health
- Postgres (host tools): localhost:5434, user `setu`, db `setu`

Run the test suite (the equity-invariant test must stay green):

```bash
docker compose exec backend pytest tests/ -q
```

## Manual setup items

These four things are required and cannot be automated:

1. **`GEMINI_API_KEY`** — a Google AI Studio (Gemini API, free tier) key, placed in
   `.env`. Used for classification/extraction (`gemini-3.8-flash`), recommendation
   drafting, verification vision checks, and `gemini-embedding-001` (768-dim)
   embeddings.
2. **First `docker compose up`** — builds the three service images and initializes
   the Postgres + PostGIS + pgvector database from `db/schema.sql`; then run the
   seed command above.
3. **One-time Whisper model download** — the Faster-Whisper `small` model downloads on
   first transcription and persists in the `whisper-models` volume. Do this early,
   not the night before a demo.
4. **Record the rehearsed Hindi demo line on the real demo microphone** — transcription
   accuracy must be validated on the actual recording setup (target: ≥8/10 correct
   StructuredRequests on the demo evaluation set).

## Demo-day checklist

**Rehearsed lines** (the location mention must be the bare verified name — "वेल्हे";
rehearsal showed "वेल्हे गाँव" does not geocode and the request proceeds flagged
into a new unscoreable cluster instead of joining the seeded one):

- Citizen 1 (voice/text): "हमारे गाँव वेल्हे में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।"
- Citizen 2 (contributes before resolution, receives the verification prompt):
  "वेल्हे में पीने के पानी की बहुत समस्या है, कई हफ़्तों से।"

1. `python3 db/seed/verify_locations.py` — every demo location string must exit 0
   against live Nominatim (no live geocoding surprises).
2. Reseed for canonical state: `docker compose exec backend python /app/seed/seed.py`
   (reseeding reuses cached embeddings — zero API calls).
3. Rehearse the 10-step scenario once live — every Gemini/Nominatim/STT response is
   recorded into `backend/fixtures/` automatically.
4. Set `DEMO_REPLAY=1` in `.env` and `docker compose up -d backend` — the rehearsed
   path now replays from fixtures and cannot be sunk by a live rate limit;
   unrehearsed judge questions still reach live Gemini.

## About the data

The demo dataset is **synthetic but realistic**, and we state that openly. Population
figures are proportioned against real Census 2011 Pune-district numbers; facility
locations and investment labels are seeded to reproduce the documented Region A/B
worked example (an urban ward with 10 water points and ~500 complaints vs. a rural
village with 0 water points and ~20 complaints — the village correctly outranks the
ward). Real government dataset integration (Census/SECC, PM Gati Shakti) is a
post-hackathon item; real datasets are frequently not machine-readable or current at
the granularity this platform needs, which is itself part of the problem Setu addresses.

## Scoring transparency

```
PriorityScore = 0.5·gap_norm + 0.3·investment_deficit_norm + 0.2·volume_norm
```

Weights are literal code constants. Complaint volume's weight (0.2) is structurally
below the infrastructure-gap weight (0.5), so volume can never override gap — this is
enforced by construction and guarded by an automated equity-invariant test on the
seeded data.

## License

[MIT](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) to get involved.
