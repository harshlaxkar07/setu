## 1. Foundations

- [x] 1.1 Add the migration runner (D1): `db/migrations/` applied in order at backend startup, recorded in `schema_migrations`; verify by restarting the backend twice on the existing volume and confirming each migration is recorded once and startup logs no errors
- [x] 1.2 Add dashboard source bind mount in `docker-compose.yml` (D10) and verify a CSS edit in `dashboard/tokens.py` appears after `docker compose restart dashboard` without a rebuild
- [x] 1.3 Introduce `backend/app/llm/` with the `Provider` protocol, `GeminiProvider` wrapping the existing live call, and `call_gemini` as an alias (D16); verify the full existing test suite passes unchanged and committed fixtures still replay with `DEMO_REPLAY=1`
- [x] 1.4 Add `OpenAICompatProvider` (chat completions JSON mode + embeddings via httpx), env selection, provider/model/latency/token fields in trace entries, and the startup embedding-dimension check; verify with unit tests using a mocked HTTP transport, including the dimension-mismatch refusal
- [x] 1.5 Implement `pii.mask` (D13) and call it inside the provider layer for every prompt; verify unit tests for Indian mobile numbers (with/without +91), spaced/unspaced 12-digit numbers, emails, and "मेरा नाम / my name is" cues, and an integration test showing the trace stores masked text

## 2. Multi-category data and language

- [ ] 2.1 Extend Understand's prompt to enumerate supported categories and label any detected language (D5, D7); verify with fixture-backed tests for a road/ambulance message (road_infrastructure, high urgency) and a Marathi message (detected_language "Marathi")
- [x] 2.2 Map healthcare and road categories to facility types in Fuse and extend seed with a healthcare equity pair and a road equity pair plus zero-request villages carrying `vulnerability_index`/`connectivity_index` (migration for the new region columns and `centroid`); verify reseed is idempotent and runs with zero embedding API calls on the second run
- [x] 2.3 Parametrise the equity-invariant test over every seeded category; verify it passes for water, healthcare and road
- [x] 2.4 Implement the Locate fallback chain (suffix stripping, region-name and facility-name matching, medium confidence with reason) (D8); verify tests showing "वेल्हे गाँव" resolves to Velhe and joins the seeded Velhe cluster
- [x] 2.5 Add `db/seed/import_osm.py` (D6) and `SCORING_DATASET` selection in Fuse; verify with a recorded Overpass response that a labelled dataset is created in one transaction, seeded scores are unchanged by default, and a network failure leaves no partial dataset

## 3. Trust and anti-manipulation

- [x] 3.1 Migration for `trust_flags`; implement the three rules as a `trust` stage and insert the node between cluster and fuse in the graph (D2); verify unit tests per rule including the "5 similar complaints over 5 days are not flagged" negative case
- [x] 3.2 Make the Score stage's complaint-volume indicator count only unflagged requests and expose `counted_volume` in cluster APIs; verify a test where injected flagged requests leave the PriorityScore unchanged, and the formula-consistency and equity tests still pass
- [x] 3.3 Add trust review endpoints (clear/confirm) recording reviewer and time; verify clearing restores the request to counted volume on the next scoring run
- [x] 3.5 One pending recommendation per cluster (D19): advisory-locked check in the Recommend node, `joined` path to END, `run_traces.joined_recommendation_id`, finalize settles joined runs; verify pipeline tests that a second request joins without a model call, approval publishes all joined traces, a post-revision request drafts afresh, and two concurrent runs yield one draft
- [x] 3.4 Add `scripts/spam_attack.py` submitting through the public intake API; verify running it with 300 requests against Kothrud produces flags visible via the cluster API and does not change Kothrud's rank

## 4. Privacy and governance

- [x] 4.1 Implement reviewer accounts and signed session tokens (D15): `REVIEWERS`/`SESSION_SECRET` config, `scripts/hash_passcode.py`, `POST /api/auth/login`; verify tests for correct login, wrong passcode, and expired/forged tokens
- [x] 4.2 Require a valid token on gate resume, verification review, trust review and resolve, taking reviewer identity from the token; update existing tests with a token fixture; verify unauthenticated decision calls return 401 and the full suite passes
- [x] 4.3 Migration for `decision_log`; append chained entries in the same transaction as each decision and add `GET /api/audit/verify` (D14); verify a test that tampers with a stored entry and gets it reported as the first break, and a concurrency test with parallel approvals leaves an intact chain

## 5. Equity insights, planner and impact (backend)

- [x] 5.1 Implement `GET /api/insights/silent-regions` and `GET /api/insights/ranking` (D3) reusing Fuse's gap helpers; verify tests that the seeded zero-request village appears as silent with its factors, a well-served region does not, and the water ranking comparison shows Kothrud first by count and Velhe first by score
- [x] 5.2 Implement `POST /api/planner/whatif` and `POST /api/planner/allocate` (D4); verify tests that a proposed water point at Velhe changes its facility count 0→1 without writing any facility row, allocation returns sites in descending marginal coverage, and published state is identical before and after planner calls
- [x] 5.3 Migration for `demand_clusters.resolved_at`; set it on resolve; implement `GET /api/clusters/{id}/impact` (D9) and seed one resolved cluster with backdated history; verify tests for full-window before/after counts, partial-window reporting, and that impact never changes verification status

## 6. Citizen experience

- [x] 6.1 Implement `GET /api/requests/{id}/timeline` and `needs_location` in status (D11, D8); verify tests covering a request grouped with others awaiting review, and a published then resolved request
- [x] 6.2 Implement `POST /api/requests/{id}/location` and the relocate routine (D8); verify an integration test that moves a flagged request into the Velhe cluster in one transaction with correct member counts on both clusters and re-scored categories
- [x] 6.3 Citizen UI: status timeline under each receipt, follow-up location question, and read-aloud buttons with speechSynthesis (hidden when unsupported); verify in a browser at 390px and 1440px that the timeline advances after a dashboard approval and no network request carries read-aloud text
- [x] 6.4 Citizen UI i18n dictionary (hi/en/mr) with header switch persisted in localStorage; verify every visible string switches to Marathi and persists on reload
- [x] 6.5 Assisted mode: migration for `channel='assisted'`, `households_represented`, unique `idempotency_key`; `/citizen/?mode=assisted` UI with offline queue and visible count; verify a browser test that 4 requests captured offline submit exactly once when back online and a replayed flush returns the existing request ids

## 7. Policy briefs

- [x] 7.1 Implement `GET /api/briefs/{cluster_id}` print-ready bilingual HTML (D12) with the draft watermark when unapproved; verify tests that the brief contains every stored indicator, the score breakdown and approval reviewer/time, contains the draft mark before approval, and renders on one A4 page in a headless browser print

## 8. Dashboard analytics

- [x] 8.1 Wrap data panels in `st.fragment(run_every=...)` with selection, tab, category filter and reviewer session in session_state (D10); verify in a browser that a new citizen submission updates the member count within one interval while the selected cluster and open tab stay put
- [x] 8.2 Reviewer sign-in panel; decision buttons disabled when signed out; token passed on decision calls; verify signed-out viewers see recommendations without actions and a signed-in approval records the account name
- [x] 8.3 Category filter applied to map, list, summary strip and trends; map layer toggles (clusters, heatmap on counted volume, silent regions) with labelled legend; verify grayscale screenshots still distinguish every layer and tier
- [x] 8.4 Trends chart (flagged vs unflagged per day, per category) and total vs counted volume on cluster cards with trust-flag badges and clear/confirm actions; verify after `spam_attack.py` the spike renders as flagged volume
- [x] 8.5 Equity tab (ranking comparison + silent regions list), Planner tab (what-if on selected cluster + allocation for N sites, labelled advisory), Impact panel on resolved clusters, and brief download button; verify each view in a browser against the seeded data with no Streamlit exceptions
- [x] 8.6 Audit panel showing chain status from `/api/audit/verify`; verify it reports intact after demo decisions

## 9. Evaluation, scale and demo operations

- [ ] 9.1 Author `backend/eval/dataset.jsonl` with ≥50 labelled items across Hindi, Hinglish, English and Marathi, all seeded categories, and informal locations; verify a loader test asserts the coverage requirements
- [ ] 9.2 Implement `backend/eval/run_eval.py` writing `report.json` and a summary table with per-language breakdowns; run once live to record fixtures, then twice in replay; verify both replay runs report identical figures
- [ ] 9.3 Implement `backend/eval/scale_test.py` for 10,000 synthetic requests with no network access; verify it reports total time and requests/second with networking disabled in the container
- [ ] 9.4 Add `scripts/share.sh` (Cloudflare quick tunnel + QR code, opt-in only) and document privacy implications in the README; verify the printed URL serves the citizen page from a phone
- [ ] 9.5 Update README (features, new env vars, reviewer setup, eval results, demo script with spam attack and planner) and CONTRIBUTING; verify every command in the README runs as written on a fresh clone

## 10. Regression and rehearsal

- [ ] 10.1 Run the full backend test suite and the browser checks for both UIs; verify zero failures, the equity invariant green for every category, and no console or Streamlit exceptions
- [ ] 10.2 Rehearse the extended demo end to end twice (voice in → timeline → gate approval with sign-in → brief download → spam attack → equity tab → planner → resolution → impact → audit verify) with DEMO_REPLAY off, then once with it on; verify each run completes without manual data patching
