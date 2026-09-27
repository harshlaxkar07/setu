# 07 — Design Tokens & Visual Language

**Status:** Draft, ratify once the team agrees — but treat as binding once agreed, since inconsistent tokens are the fastest way a Streamlit build looks unfinished.
**Depends on:** `06-ui-contract.md`.
**Last updated:** 2026-09-24

---

## Direction

**Calm civic clarity.** This is a tool a government official trusts with real decisions — not a startup dashboard, not a government portal from 2012. Light surfaces, generous spacing, one clear focal point per screen, data that reads as *evidence* rather than *decoration*.

Two registers, same base palette:
- **Citizen surface:** warmer accent, larger type, rounder shapes — approachable.
- **Policymaker surface:** cooler/neutral accent, tighter density, monospace for every number — precise, auditable.

---

## Color tokens

### Base

| Token | Hex | Use |
|---|---|---|
| `paper` | `#F7F8FA` | App background |
| `card` | `#FFFFFF` | Surfaces |
| `ink` | `#17212B` | Primary text |
| `ink-2` | `#5B6572` | Secondary text |
| `ink-3` | `#8C95A1` | Meta / tertiary |
| `line` | `#E3E7EC` | Hairlines, card borders |

### Brand

| Token | Hex | Use |
|---|---|---|
| `bridge-blue` | `#2B5FA8` | Primary actions, selected states, brand |
| `bridge-blue-deep` | `#1E4478` | Pressed states, header gradient anchor |
| `bridge-blue-soft` | `#E9F0F9` | Selected fills, badges |

### Semantic — reserved, never decorative

| Token | Hex | Meaning |
|---|---|---|
| `priority-high` / `-soft` | `#C2372E` / `#FBE9E7` | Highest priority tier |
| `priority-medium` / `-soft` | `#B26B00` / `#FBF0DC` | Medium priority tier |
| `priority-low` / `-soft` | `#1E7F4F` / `#E4F3EA` | Lower priority tier (still served, not "unimportant") |
| `ai-provenance` | `#0E8C7F` | Marks any AI-drafted field — summary text, recommendation text. Never used decoratively. |
| `pending-gate` | `#B26B00` | The "awaiting Publish Gate approval" badge state |
| `verify-mismatch` | `#C2372E` | VerificationRecord flagged mismatch |

### Accessibility law

WCAG AA minimum on all text. Priority tier is never color-only — always paired with a label ("High," "Medium," "Low") and, ideally, a numeral.

---

## Typography

| Role | Face | Notes |
|---|---|---|
| Headings | **Inter** (or system sans) | Bold, used sparingly — one clear heading per section |
| Body / UI | **Inter** | Regular/medium weight for body text |
| Numeric / scores / counts / coordinates | **IBM Plex Mono**, tabular | Mandatory for PriorityScore values, InfrastructureGapScore, member counts, coordinates — the "this is evidence, not prose" signal from the vision doc |

Devanagari note: if any Hindi text renders in the UI (citizen summaries, transcripts), pair with **Noto Sans Devanagari** — do not rely on a Latin-only font stack silently substituting.

---

## Spacing & shape

- **Spacing scale:** 8 / 16 / 24 / 32px. No off-scale values.
- **Radii:** 12px for cards, 8px for chips/badges. Rounder on the citizen surface (16px) for a softer, more approachable feel.
- **Density:** citizen surface comfortable (large touch targets, ≥44px); policymaker surface compact (denser cards, tighter tables) — mirrors the two-register rule in `06-ui-contract.md`.

## Making Streamlit not look like Streamlit

This is the single highest-leverage UI task for a hackathon judge's first impression:

1. Inject custom CSS to hide Streamlit's default header, footer, and "Made with Streamlit" badge.
2. Override the default font stack to Inter/Plex Mono via `st.markdown` with a `<style>` block, not Streamlit's default theme fonts.
3. Replace default `st.metric` widgets (which look generic) with custom HTML/CSS cards using the tokens above — especially for `cluster_card` and `priority_indicator_row`.
4. Use `st.set_page_config(layout="wide")` and build the map/card split described in `06-ui-contract.md` with columns, not Streamlit's default single-column flow.
5. One consistent header bar across the whole dashboard (logo/name + register indicator), not Streamlit's default page title styling.

## Iconography

Simple, stroke-based icons (Lucide or similar) — no clipart, no stock illustration. A water-drop icon for the water category, a location pin for geocoded requests, a checkmark-in-circle for high confidence — small, consistent, never decorative filler.

## Open items

1. Final font pairing confirmation — spike Inter vs. an Indian-type-friendly alternative if time allows, otherwise Inter is the safe default.
2. Logo/wordmark — a simple bridge-motif mark is enough for a hackathon; do not spend build time on elaborate branding.
