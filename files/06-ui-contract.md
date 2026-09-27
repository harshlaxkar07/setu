# 06 — UI Contract

**Status:** Living contract. Two surfaces, one visual language (`07-design-tokens.md`).
**Last updated:** 2026-09-24

---

## Rules

1. **No unexplained numbers.** Any score, count, or percentage on screen must have its contributing factors reachable in the same view (expand, hover, or adjacent card) — never a bare figure with no "why."
2. **Trust signals are never color-only.** ConfidenceLevel and priority tier always pair color with a label or icon — accessibility and honesty both demand it.
3. **The Publish Gate is a real, visible action**, not a passive state. A pending Recommendation must look distinctly "awaiting approval," not just absent.
4. **Streamlit's default chrome is hidden.** Custom CSS strips the default Streamlit header/footer/hamburger; the app reads as a purpose-built product, not a notebook demo. This is non-negotiable given the stated "UI has to be very good" requirement — see `07-design-tokens.md` for the exact treatment.
5. **Two registers:** **citizen-facing** (warm, reassuring, minimal text, large touch targets, voice-first) and **policymaker-facing** (neutral/formal, data-dense, precise, evidence-forward). A component never crosses registers.

## Component inventory

### Citizen surface (chat widget)

| Component | Purpose |
|---|---|
| `chat_bubble` | Citizen or system message; citizen bubbles support voice playback inline |
| `voice_record_button` | Large, thumb-friendly, press-and-hold to record — the primary input affordance |
| `language_indicator` | Small, non-intrusive chip showing detected language, auto-updates per message |
| `submission_receipt` | Confirms a request was received, with a plain-language summary of what was understood ("We understood: water supply issue, high urgency") — this is the citizen's own trust signal, mirroring the transparency given to policymakers |
| `verification_prompt` | Appears only when a cluster the citizen contributed to is marked resolved; asks for a follow-up photo/voice note |

### Policymaker surface (dashboard)

| Component | Purpose |
|---|---|
| `demand_map` | PyDeck map, DemandClusters as sized/colored markers by PriorityScore tier |
| `cluster_card` | One DemandCluster: member count, category, representative summary, PriorityScore, expandable factor list |
| `priority_indicator_row` | One named factor + its value, always shown as a labeled row, never buried in a tooltip |
| `gap_comparison_panel` | Side-by-side view for the worked example (`04-domain-model.md`) — Region A vs Region B, complaint count vs gap score, visually proving the equity point |
| `recommendation_card` | Draft intervention text, evidence citations (which cluster, which indicators), Approve/Reject/Request-changes actions |
| `pending_gate_badge` | Distinct visual state for anything awaiting Publish Gate approval — amber, labeled "Awaiting review," never silently blended in with approved items |
| `verification_flag` | Appears when a VerificationRecord mismatch is detected; shows the original complaint text next to the follow-up submission for human comparison |
| `run_trace_drawer` | Expandable, developer/judge-facing: shows the full pipeline path for a selected cluster — the explainability proof for Q&A |

## Layout

- **Citizen surface:** single-column, mobile-viewport-first, large text, minimal chrome. Think WhatsApp, not a form.
- **Policymaker surface:** map + card list side by side on desktop; card list only on narrow viewports. One DemandCluster selected at a time drives both the map focus and the card detail panel — never two independent scroll states fighting each other.

## Provenance disclosure

Every AI-generated field (summary, recommendation text) carries a small, consistent "AI-drafted" marker distinct from human-entered or raw-citizen text. This is a direct application of the vision doc's transparency principle and a good judge-facing detail — it shows the team thought about disclosure, not just capability.
