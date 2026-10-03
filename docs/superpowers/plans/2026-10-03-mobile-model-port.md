# Ireland Trails mobile model port Implementation Plan

> **For agentic workers:** Implement each task in order, keeping the asset builder independent from browser calculation code. Work on branch `feat/trails-mobile-model-port` in the isolated Ireland Trails clone.

**Goal:** Make the Ireland Trails app's along-route 4G/5G estimate use the national scenario's per-site heights and CLC+ clutter inputs while retaining continuous route estimates.

**Architecture:** Keep the app static and browser-side. Add a deterministic importer that joins the complete app catalogue to the national height inventory and stages the national CLC+ clutter tiles with their CORINE fallback. Update the route predictor to consume the added height field and align shared propagation settings with the national model.

**Tech Stack:** Python 3 standard library for asset import; browser JavaScript in `dist/index.html`; Node's built-in test runner; PNG static tile assets.

**User decisions (already made):** Keep the continuous per-route estimator; do not expose calculation details or antenna-height labels in the UI; do not run a 10 m grid model.

---

## File map

- Create `scripts/build-mobile-model-assets.py`: deterministic import of site-height values and CLC+ tiles from the local coverage-model checkout into app static assets.
- Modify `dist/index.html`: read the appended site height, pass it to propagation calculation, and load the new CLC+ asset bundle without adding detailed user-facing copy.
- Create a versioned bundle under `dist/data/mobile-model-2026-10-03/` containing the enriched site catalogue, CLC+ clutter tiles, climate input and manifest; leave old assets intact for rollback.
- Modify `scripts/test-mobile-propagation.mjs` and create `scripts/test-mobile-model-assets.py`: cover runtime height use and importer joins/fallbacks.
- Modify `README.md`: update the named clutter source, without adding calculation detail to the interface.

## Task 1: Specify failing asset and estimator checks

**Goal:** Encode the required bundle and height behaviour before changing app code.

**Files:**
- Modify `scripts/test-mobile-propagation.mjs`.
- Create `scripts/test-mobile-model-assets.py`.

**Acceptance Criteria:**
- Tests fail on current assets because site records have no height and current clutter metadata identifies CORINE as primary.
- Importer tests specify exact operator/coordinate join, 30 m fallback for absent estimates, duplicate-key rejection, and omission of planning quotes/status from runtime rows.
- Estimator tests specify that candidate signal calculation receives its site's height and retains the current 4G/5G class and route-summary data shape.

**Verify:** `node --test scripts/test-mobile-propagation.mjs` and `python3 -m unittest scripts/test-mobile-model-assets.py`; both should fail only on not-yet-implemented requirements.

**Steps:** Write one focused assertion per behaviour, run both commands, and record the expected red failures before adding production code.

## Task 2: Build the national-model static assets

**Goal:** Produce a self-contained app-origin catalogue and clutter bundle from the canonical national scenario.

**Files:**
- Create `scripts/build-mobile-model-assets.py`.
- Create `dist/data/mobile-model-2026-10-03/mobile-sites.json`.
- Copy the 57 CLC+ tiles and metadata into `dist/data/mobile-model-2026-10-03/mobile-clutter/`.
- Create the versioned climate input and `mobile-model-metadata.json` manifest.
- Test in `scripts/test-mobile-model-assets.py`.

**Acceptance Criteria:**
- Join every app record to the 7,820-row height inventory using network and rounded-six-decimal WGS84 coordinates; reject duplicate or conflicting source keys.
- Append a finite numeric transmitter height for every site; use 30 m where the source estimate is blank.
- Copy CLC+ scenario 160 m tiles byte-for-byte from the canonical source bundle, retaining its CORINE fallback and sea flags.
- The runtime site catalogue contains no planning quote, application number, proposal status, or workbook content.
- Manifest records source revision, counts, source identifiers and SHA-256 checksums; importer stages output only after all inputs pass validation.

**Verify:** `python3 -m unittest scripts/test-mobile-model-assets.py`; run importer with `--coverage-repo /root/.openclaw/workspace/projects/ireland-mobile-coverage`; parse output and compare site count, coordinate matches, tile names and hashes with inputs.

**Steps:** Implement a pure transformation for catalogue join and bundle verification, add CLI input-root validation, stage outputs in a temporary directory, and atomically replace generated files only after validation succeeds.

## Task 3: Use site heights and CLC+ data in route calculation

**Goal:** Align the browser route estimator with the national scenario's inputs and shared propagation settings.

**Files:**
- Modify `dist/index.html`.
- Test in `scripts/test-mobile-propagation.mjs`.

**Acceptance Criteria:**
- Candidate selection keeps existing network/band behaviour while carrying `transmitterHeightM` from the catalogue (30 m if absent for backward compatibility).
- Diffraction uses the candidate-specific height for its transmitter endpoint; receiver height remains 1.5 m.
- Shared settings match the national model: 42 km 4G, 32 km 5G, at most two candidates per network within 18 dB of the strongest, 48 dB link allowance and 160 m terrain/clutter profile sampling.
- Clutter reader consumes the CLC+ height codes, sea flag and fallback semantics without mixing mismatched asset versions.
- Existing trail sample spacing, continuous dBm, segment classing, caches and 4G/5G controls remain intact. No antenna heights, proposal statuses or crosswalk explanation is added to the interface.

**Verify:** `node --test scripts/test-mobile-propagation.mjs`; compare fixed shared route/site points with the national Python model inputs and confirm expected direction of height/clutter-sensitive results.

**Steps:** Add failing candidate-height and new-clutter cases first; update JavaScript calculation and static data loader; run tests and inspect generated predictions for all four signal classes.

## Task 4: Update source note and integration checks

**Goal:** Ensure maintenance documentation and delivered static data correspond to the new estimator.

**Files:**
- Modify `README.md`.
- Review `dist/data/mobile-model-metadata.json` and `dist/index.html`.

**Acceptance Criteria:**
- README names the CLC+-based input without adding calculation breakdowns to the app UI.
- Both technologies share the versioned bundle; version checks prevent mixing old clutter tiles with new site heights.
- Non-signal trail features remain unaffected.

**Verify:** `node --test scripts/test-mobile-propagation.mjs`; `python3 scripts/test-mobile-model-assets.py`; inspect `git diff --check`, parse generated JSON, check manifest hashes. Inline JavaScript syntax is checked with `node --check`. A full interactive map/browser smoke is not part of the local verification run.

**Steps:** Update only the source description, perform acceptance checks, review final diff for accidental UI copy/data leakage, and report runtime bundle size and remaining parity differences.

## Release boundary

Keep implementation local to the feature branch. Do not push to GitHub or deploy the live Trails app unless Andrew separately asks for publication/deployment.
