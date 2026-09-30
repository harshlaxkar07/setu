"""Design tokens + the Streamlit chrome-hiding CSS pass (files/07, task 6.1).

Single source of styling truth for the policymaker surface: token values are
Python constants (the map needs them as RGB), and CSS is one injected block —
paper background, card surfaces, bridge-blue actions, semantic priority tokens,
Inter / IBM Plex Mono (tabular) / Noto Sans Devanagari, 8/16/24/32 spacing.
"""

# --- color tokens (files/07-design-tokens.md, verbatim) ----------------------
PAPER = "#F7F8FA"
CARD = "#FFFFFF"
INK = "#17212B"
INK_2 = "#5B6572"
INK_3 = "#8C95A1"
LINE = "#E3E7EC"

BRIDGE_BLUE = "#2B5FA8"
BRIDGE_BLUE_DEEP = "#1E4478"
BRIDGE_BLUE_SOFT = "#E9F0F9"

PRIORITY_HIGH = "#C2372E"
PRIORITY_HIGH_SOFT = "#FBE9E7"
PRIORITY_MEDIUM = "#B26B00"
PRIORITY_MEDIUM_SOFT = "#FBF0DC"
PRIORITY_LOW = "#1E7F4F"
PRIORITY_LOW_SOFT = "#E4F3EA"

AI_PROVENANCE = "#0E8C7F"
PENDING_GATE = "#B26B00"
VERIFY_MISMATCH = "#C2372E"

# Tier → (solid, soft, RGB list for PyDeck fills). Color is NEVER used alone —
# every rendering pairs it with the tier label (spec: never color-only).
TIER_TOKENS = {
    "High": (PRIORITY_HIGH, PRIORITY_HIGH_SOFT, [194, 55, 46]),
    "Medium": (PRIORITY_MEDIUM, PRIORITY_MEDIUM_SOFT, [178, 107, 0]),
    "Low": (PRIORITY_LOW, PRIORITY_LOW_SOFT, [30, 127, 79]),
}
TIER_UNSCORED_RGB = [140, 149, 161]  # ink-3: no score yet

# --- the injected stylesheet --------------------------------------------------
CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+Devanagari:wght@400;500&display=swap');

:root {{
  --paper: {PAPER}; --card: {CARD};
  --ink: {INK}; --ink-2: {INK_2}; --ink-3: {INK_3}; --line: {LINE};
  --bridge-blue: {BRIDGE_BLUE}; --bridge-blue-deep: {BRIDGE_BLUE_DEEP};
  --bridge-blue-soft: {BRIDGE_BLUE_SOFT};
  --priority-high: {PRIORITY_HIGH}; --priority-high-soft: {PRIORITY_HIGH_SOFT};
  --priority-medium: {PRIORITY_MEDIUM}; --priority-medium-soft: {PRIORITY_MEDIUM_SOFT};
  --priority-low: {PRIORITY_LOW}; --priority-low-soft: {PRIORITY_LOW_SOFT};
  --ai-provenance: {AI_PROVENANCE}; --pending-gate: {PENDING_GATE};
  --verify-mismatch: {VERIFY_MISMATCH};
}}

/* ---- chrome-hiding pass: no Streamlit header/footer/menu/badge (files/07) */
#MainMenu {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ display: none !important; }}
footer {{ display: none !important; }}
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stAppDeployButton"],
.stDeployButton, .viewerBadge_container__r5tak,
a[href*="streamlit.io/cloud"] {{ display: none !important; }}

/* ---- base surfaces + type -------------------------------------------- */
html, body, [data-testid="stAppViewContainer"], .stApp {{
  background: var(--paper) !important;
  color: var(--ink);
  font-family: 'Inter', system-ui, sans-serif;
}}
.block-container {{ padding: 24px 32px 32px 32px !important; max-width: 1600px; }}
h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
  font-family: 'Inter', system-ui, sans-serif; color: var(--ink);
}}
p, li, label, .stMarkdown {{ color: var(--ink); }}

/* every numeric value: IBM Plex Mono, tabular figures (spec scenario) */
.num {{
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}}
/* Hindi content: Devanagari face, never a Latin-only fallback */
.hindi {{ font-family: 'Noto Sans Devanagari', 'Inter', sans-serif; }}

/* ---- the one consistent header bar ------------------------------------ */
.setu-header {{
  background: linear-gradient(90deg, var(--bridge-blue-deep), var(--bridge-blue));
  color: #FFFFFF; border-radius: 12px;
  padding: 16px 24px; margin-bottom: 16px;
  display: flex; align-items: baseline; gap: 16px;
}}
.setu-header .mark {{ font-size: 22px; font-weight: 700; letter-spacing: 0.3px; }}
.setu-header .register {{
  font-size: 12px; font-weight: 500; color: var(--bridge-blue-soft);
  border: 1px solid rgba(255,255,255,0.35); border-radius: 8px; padding: 2px 8px;
}}

/* ---- cards ------------------------------------------------------------ */
.setu-card {{
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 16px; margin-bottom: 16px;
}}
.setu-card.selected {{ border: 2px solid var(--bridge-blue); background: var(--bridge-blue-soft); }}
.card-title {{ font-weight: 600; font-size: 15px; margin-bottom: 8px; }}
.card-meta {{ color: var(--ink-2); font-size: 13px; }}

/* ---- badges: color ALWAYS paired with a text label --------------------- */
.badge {{
  display: inline-block; border-radius: 8px; padding: 2px 8px;
  font-size: 12px; font-weight: 600; line-height: 18px;
}}
.badge-tier-high {{ background: var(--priority-high-soft); color: var(--priority-high); }}
.badge-tier-medium {{ background: var(--priority-medium-soft); color: var(--priority-medium); }}
.badge-tier-low {{ background: var(--priority-low-soft); color: var(--priority-low); }}
.badge-pending {{ background: var(--priority-medium-soft); color: var(--pending-gate);
                  border: 1px solid var(--pending-gate); }}
.badge-published {{ background: var(--priority-low-soft); color: var(--priority-low); }}
.badge-ai {{ background: rgba(14,140,127,0.10); color: var(--ai-provenance);
             border: 1px solid var(--ai-provenance); font-weight: 500; }}
.badge-confidence {{ background: var(--bridge-blue-soft); color: var(--bridge-blue-deep); }}
.badge-flag {{ background: var(--priority-high-soft); color: var(--verify-mismatch);
               border: 1px solid var(--verify-mismatch); }}
.badge-resolved-unverified {{ background: var(--priority-medium-soft);
                              color: var(--priority-medium); }}
.badge-resolved-verified {{ background: var(--priority-low-soft);
                            color: var(--priority-low); }}

/* ---- labeled factor rows (never tooltip-only) --------------------------- */
.factor-row {{
  display: flex; justify-content: space-between; gap: 16px;
  padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 13px;
}}
.factor-row:last-child {{ border-bottom: none; }}
.factor-name {{ color: var(--ink-2); }}
.factor-value {{ text-align: right; color: var(--ink); }}

/* ---- score breakdown ---------------------------------------------------- */
.breakdown {{ background: var(--paper); border-radius: 8px; padding: 8px 16px;
              margin-top: 8px; }}
.breakdown .factor-row {{ border-bottom: 1px dashed var(--line); }}
.breakdown-total {{ font-weight: 600; }}

/* ---- gap comparison panel ------------------------------------------------ */
.gap-panel {{ display: flex; gap: 16px; }}
.gap-col {{ flex: 1; background: var(--card); border: 1px solid var(--line);
            border-radius: 12px; padding: 16px; }}
.gap-col.winner {{ border: 2px solid var(--priority-high); }}
.gap-rank {{ font-size: 13px; font-weight: 700; margin-bottom: 8px; }}
.callout {{ background: var(--priority-high-soft); color: var(--priority-high);
            border-radius: 8px; padding: 8px; font-size: 12px; font-weight: 600;
            margin-top: 8px; }}
.callout.info {{ background: var(--bridge-blue-soft); color: var(--bridge-blue-deep);
                 font-weight: 500; }}

/* citizen voice quotes: raw content, deliberately NOT AI-marked */
.citizen-quote {{ background: var(--paper); border-left: 3px solid var(--ink-3);
                  border-radius: 0 8px 8px 0; padding: 8px 16px; margin: 8px 0;
                  font-size: 13px; color: var(--ink-2); }}

/* ---- buttons: bridge-blue primary --------------------------------------- */
.stButton > button {{
  border: 1px solid var(--line); border-radius: 8px;
  background: var(--card); color: var(--ink);
  font-family: 'Inter', sans-serif; font-weight: 500;
}}
.stButton > button:hover {{ border-color: var(--bridge-blue); color: var(--bridge-blue); }}
.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {{
  background: var(--bridge-blue); border-color: var(--bridge-blue); color: #FFFFFF !important;
}}
[data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primaryFormSubmit"] p {{ color: #FFFFFF !important; }}
.stButton > button[kind="primary"]:hover {{ background: var(--bridge-blue-deep); }}

/* expanders read as cards, not default Streamlit chrome */
[data-testid="stExpander"] {{
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
}}
[data-testid="stExpander"] summary {{ font-weight: 600; color: var(--ink); }}

.section-title {{ font-size: 16px; font-weight: 700; margin: 24px 0 8px 0; }}
.section-sub {{ font-weight: 500; color: var(--ink-2); }}
/* ---- enhancements: tables, legend, silent regions, audit ---------------- */
.setu-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.setu-table th {{ text-align: left; color: var(--ink-2); font-weight: 600;
                  border-bottom: 1px solid var(--line); padding: 6px 8px; }}
.setu-table td {{ border-bottom: 1px solid var(--line); padding: 6px 8px; vertical-align: top; }}
.rank-up {{ color: var(--priority-low); font-weight: 600; }}
.rank-down {{ color: var(--priority-high); font-weight: 600; }}
.badge-signal {{ background: #EEF1F4; color: var(--ink-2); font-weight: 500; }}
.silent-card {{ border-left: 4px solid var(--bridge-blue-deep); }}
.factor-list {{ margin: 4px 0 0 18px; padding: 0; font-size: 13px; color: var(--ink-2); }}
.legend {{ line-height: 26px; }}
.legend-heat {{ display: inline-block; width: 22px; height: 10px; border-radius: 5px;
                background: linear-gradient(90deg, #F2C98B, #C2372E); vertical-align: middle; }}
.legend-ring {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%;
                border: 2px solid var(--bridge-blue-deep); vertical-align: middle; }}
.audit-ok {{ background: var(--priority-low-soft); color: var(--priority-low); font-weight: 600; }}
.audit-broken {{ background: var(--priority-high-soft); color: var(--priority-high); font-weight: 700; }}
.live-dot {{ font-size: 12px; color: var(--priority-low); text-align: right; }}
.signed-in {{ background: var(--priority-low-soft); color: var(--priority-low);
              border-radius: 8px; padding: 8px 16px; font-size: 13px; margin-top: 4px; }}

/* ---- summary strip ------------------------------------------------------ */
.kpi-strip {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
              gap: 16px; margin-bottom: 8px; }}
.kpi {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px;
        padding: 12px 16px; }}
.kpi-value {{ font-size: 24px; font-weight: 600; line-height: 1.2; }}
.kpi-label {{ font-size: 12px; color: var(--ink-2); margin-top: 2px; }}
.kpi-high {{ border-left: 4px solid var(--priority-high); }}
.kpi-high .kpi-value {{ color: var(--priority-high); }}
.kpi-pending {{ border-left: 4px solid var(--pending-gate); }}
.kpi-pending .kpi-value {{ color: var(--pending-gate); }}
@media (max-width: 1100px) {{
  .kpi-strip {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
}}
@media (max-width: 700px) {{
  .kpi-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}

/* ---- tabs: section navigation ------------------------------------------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 8px; border-bottom: 1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ font-family: 'Inter', sans-serif; font-weight: 600;
                                 font-size: 14px; padding: 8px 16px; color: var(--ink-2); }}
.stTabs [aria-selected="true"] {{ color: var(--bridge-blue) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: var(--bridge-blue) !important; }}
.stTabs [data-baseweb="tab"] p {{ font-weight: 600; font-size: 14px; }}
.small-note {{ color: var(--ink-3); font-size: 12px; }}
"""
