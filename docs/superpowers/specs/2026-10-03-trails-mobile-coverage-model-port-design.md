# Ireland Trails mobile coverage model port

Date: 3 October 2026
Status: Design for user review; no application implementation changes yet.

## Goal

Update the Ireland Trails app's existing along-route 4G/5G estimator so it uses the same national model inputs and settings as the current high-resolution Ireland coverage scenario, while preserving its existing trail interaction, continuous signal estimate, segment colouring and route summaries.

The app must not add explanatory UI about how transmitter heights or clutter values are calculated. Keep the existing brief signal-estimate caveat; detailed provenance belongs in source/data metadata, not the trail interface.

## Current state

The app is a static browser application. Its `dist/index.html` loads a compact ComReg Q1 2026 site catalogue, terrain tiles, a CORINE-derived 160 m clutter tile set and P.1812 climatology. It samples route locations at roughly 140 m, profiles paths at 160 m, and calculates route-level signal estimates in the browser. Current site records do not include transmitter height. The map's separate national model uses planning-derived height estimates on 1,601 of 7,820 operator-site records and a 30 m fallback for the others, plus a CLC+ Backbone 2021 160 m clutter layer with CORINE fallback.

The national map exports categorical class PNGs rather than a continuous dBm surface. Sampling those images would discard the route estimator's continuous values and is not the selected design.

## Recommended architecture

Keep the browser-side, on-demand route estimator. Promote its static input assets and calculation settings to the national scenario:

1. Extend the site-catalogue build step to join each operator-site record to the national height inventory by operator and exact site coordinates. Add only the numeric estimated transmitter height to the compact runtime record; use the existing 30 m default when the inventory has no estimate. Do not publish planning quotes or application details in the runtime catalogue.
2. Replace the app's CORINE-primary clutter tile bundle with the existing 160 m CLC+ scenario tile bundle. Preserve its class-to-height crosswalk, CORINE no-data/outside-Ireland fallback and sea-path handling. Keep the app's same-origin static loading and cache behaviour.
3. Align the route calculation's site selection, frequency/EIRP choice, transmitter heights, receiver height, distance caps, candidate limits, link allowance, clutter handling and diffraction calculation with the national model wherever those parameters are common. Retain route-specific sampling at the existing spacing: it already samples at approximately the national grid's ground spacing, while the input layers do not support a 10 m route prediction.
4. Keep per-technology route results and their current display/summary behaviour. The visible interface should not expose a height value, proposal status, crosswalk or additional calculation description.
5. Record source versions, asset checksums, the model run/source revision and default/estimated record counts in a machine-readable data manifest for maintenance and reproducibility. Do not present these details in user-facing copy.

## Alternatives considered

- **Sample the national coverage PNGs along each trail.** This is simpler and avoids duplicating propagation logic, but yields only discrete map classes, not the current continuous dBm estimates; it also couples trail predictions to raster pixel lookup and the strongest-network/operator layers available in those PNGs. Not recommended.
- **Move route prediction to a server.** This could centralise model code and avoid shipping input tiles, but adds service availability, latency and deployment dependencies to a currently static app. It is unnecessary for the present site and data volumes. Not recommended.

## Data flow and failure handling

At build time, create a self-contained static bundle from the canonical coverage-model height inventory, CLC+ clutter tiles and matching metadata. At runtime, load the site catalogue, CLC+ clutter tiles and climatology from the app origin, compute only points on the selected route, and cache the result using the existing route/technology caches.

The bundle must be versioned as a unit. If an input is missing, corrupt, has an unexpected schema, or fails to load, do not silently combine new and old clutter/model inputs. Preserve the app's existing recoverable error state and allow retry. Existing route selection and non-mobile map layers must remain unaffected.

## Acceptance criteria

- 4G and 5G trail estimates still produce continuous signal values, segment colours and route summaries using the existing UI controls.
- The app uses the same per-record transmitter-height scenario, 160 m CLC+ clutter values and CORINE fallback as the national run; unestimated sites retain the model's 30 m default.
- Candidate selection and propagation settings common to both implementations are aligned, with any unavoidable route-specific differences documented in the internal manifest/report.
- The runtime bundle contains no planning descriptions, private material or per-application quotes.
- No height/status/crosswalk details are added to user-facing labels or explanatory copy. The existing general estimate caveat remains.
- App startup, trail loading and non-signal layers continue to work if the signal-data bundle is unavailable.
- No 10 m grid run, handset calibration, live deployment or public repository push is included in this integration without separate approval.

## Verification plan

Before release, validate the generated asset schema, site count and coordinate join; check CLC+ tile coverage and missing-data fallback against the source bundle; compare the browser implementation and national Python model at a fixed set of shared site/route points; and exercise 4G/5G route display, summary, cache and failed-asset recovery in a browser. Report model differences and runtime asset size. Deployment is a separate step after review.

## Scope boundaries

This work ports the current deterministic scenario; it does not establish accuracy against real handset signal. It does not add operator-specific per-sector antenna geometry, signal calibration, physical observations, a finer national grid or new explanatory copy.
