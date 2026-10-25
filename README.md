# Ireland Trail Atlas

An interactive map for people choosing and planning walks in Ireland. Explore Sport Ireland’s registered trails, inspect the terrain, and find useful places, heritage sites and transport near a route.

**[Open Ireland Trail Atlas](https://ireland-trail-atlas.andrewlinn.chatgpt.site)**

## Find a trail

- Browse trails across Ireland, within a selected county, or in the visible map area.
- Search by trail name or county, and filter by activity and registered difficulty grade.
- Sort by name, distance or ascent.
- View route distance, ascent and grade, with trailhead, nearest town, Irish grid reference, dog access, estimated walking time and waymarking details where the register supplies them.
- Open a trail map from Sport Ireland or its linked publisher. The **Maps & guides** section shows the file type and links to publisher updates; trails without a direct file keep a link to their Sport Ireland page.
- Use collapsible browsing and information panels, with layouts for desktop and mobile screens.

## Explore a route

| Feature | What it shows |
| --- | --- |
| Elevation and steepness | An elevation profile, high point and ascent information. Trail sections are coloured green below 5% slope, amber from 5% to below 12%, and red at 12% or above. Registered difficulty and calculated slope are separate measures. |
| 3D terrain | Raised terrain and a tilted map to help read the surrounding relief. |
| Weather | Forecast conditions at the route midpoint, including temperature, precipitation probability and wind. Met Éireann warnings are matched to the route county and include links to official details. |
| Nearby places and access | Sport Ireland activity locations within about 1.5 km of the route, including available amenities, accessibility, opening and access information. |
| Heritage stops | National Monuments Service sites within about 1.5 km, with map locations and visiting information where available. |
| Getting there | Bus and rail stops within 5 km of route ends, with route labels and a link to Transport for Ireland’s journey planner. |
| Nearby photos | Geotagged Wikimedia Commons photographs within 200 m of the route, with creator and licence links. |
| Estimated 4G and 5G | Colours the selected trail by modelled signal strength and summarises the distance in each signal category. |
| Clutter height | Shows the representative land-cover heights used as an input to the route signal model. |

Layers can be switched on and off from the map’s layer menu. Trail grade and amenities are enabled by default; 3D terrain, photos, heritage, transport and mobile estimates are optional.

### GPX routes

Open a GPX file from your device to inspect your own route. The interface also provides GPX export for the selected route. Imported files are read in the browser; the site states that they are not uploaded or saved.

Terrain-derived elevations are estimates. GPX export avoids presenting these estimates as recorded elevations.

### Trail maps and downloads

`dist/data/trail-map-links.json` stores map links by `TrailID`, with each trail’s Sport Ireland page and checked status. It includes direct Sport Ireland attachments plus verified maps, images and selected guides from trail managers and regional publishers. A trail can have several route maps. Links open the publisher’s original file or map page in a new tab; visitors can save a copy from the opened file. Maps retain their publisher’s copyright and terms. Imported GPX routes do not receive registered trail map links.

The index distinguishes a page with no listed map from a page that could not be reached and a trail that still needs checking. `complete` means every trail page has either been checked or marked inaccessible; it does not mean every trail has a published downloadable file.

Current snapshot: all 1,194 trail pages have a recorded status. There are map or guide links for 1,111 trails; 80 pages list no map attachment, and 3 pages could not be reached during the refresh.

To refresh the index, run `python scripts/extend-trail-map-links.py --max-pages 60 --interval 15`. It checks only unprocessed trails, makes one request at a time, waits 15 seconds after each response, and saves each result immediately. It stops on a browser verification request or rate limit, and preserves existing maps.

`scripts/collect-trail-map-candidates.py` and `scripts/collect-trail-map-register-candidates.py` prepare offline candidate lists from checked pages and the official register. `scripts/verify-trail-map-candidates.py` checks one URL at a time and accepts files only when their signatures match the returned file type. It stops checking a host when a verification challenge or rate limit appears. `scripts/sync-trail-map-recoveries.py` saves publisher files, images and map websites in `docs/trail-map-link-recoveries.json` so a later rebuild can retain them. Per-link checks are recorded in `docs/trail-map-download-checks.json`.

For a full source refresh, `scripts/build-trail-map-links.py` can use its cached-only mode or `--allow-unavailable` to record inaccessible pages. Use `--recoveries docs/trail-map-link-recoveries.json` to preserve verified publisher maps when rebuilding.

### Mobile signal estimates

The route estimator combines ComReg’s public 2026 Q1 mobile licence site schedules with terrain, Sentinel-derived CLC+ land cover and ITU-R radio-climatology inputs. It estimates signal continuously along the route rather than assigning a value from the map’s display grid.

Results represent the best modelled link across Eir, Three and Vodafone. When both technology layers are selected, the map uses the stronger estimated category for each route segment.

These are exploratory signal estimates, rather than measured coverage or a guarantee for a particular subscriber. The model uses assumed link-budget and clutter parameters; this README does not claim a complete or independently validated implementation of ITU-R P.1812.

## Data sources

| Data | Source |
| --- | --- |
| Registered trails and activity locations | [Sport Ireland / Get Ireland Active](https://data.gov.ie/dataset/getirelandactive_trailroutes), with [activity locations](https://data.gov.ie/dataset/getirelandactive_activitylocations) |
| Base map | [OpenStreetMap](https://www.openstreetmap.org/copyright) |
| Elevation | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/), using Terrarium tiles |
| Forecast weather | [Open-Meteo](https://open-meteo.com/) |
| County weather warnings | [Met Éireann open data](https://www.met.ie/about-us/specialised-services/open-data) |
| Heritage locations | [National Monuments Service — Monuments to Visit](https://data.gov.ie/dataset/monuments-to-visit-points-of-interest) |
| Bus and rail stops and route labels | [National Transport Authority GTFS](https://data.gov.ie/dataset/nta-gtfs) |
| Photographs | [Wikimedia Commons](https://commons.wikimedia.org/), with individual image credits and licences |
| Mobile site catalogue | [ComReg mobile licence schedules](https://www.comreg.ie/industry/radio-spectrum/licensing/search-licence-type/mobile-licences-2/) |
| Land cover | [Copernicus Land Monitoring Service CLC+ Backbone 2021](https://land.copernicus.eu/en/products/clc-backbone/clc-backbone-2021), with CORINE Land Cover 2018 as a fallback where CLC+ data are unavailable |
| Radio-climatology | [ITU-R P.1812-8 digital products](https://www.itu.int/rec/R-REC-P.1812/en) |

The interface includes source acknowledgements and licence information. Third-party datasets and photographs retain their respective licences.

## Practical limits

- Nearby-place and transport distances are straight-line estimates.
- Transport information comes from a GTFS snapshot labelled valid from 24 September 2026 to 24 September 2027. Check current services before travelling.
- Heritage access can vary, including sites on private land; consult linked visiting information.
- Nearby photographs may show surrounding scenery rather than the path itself.
- Weather represents the route midpoint; warnings apply at county level.
- External maps and data services require a connection. The interface describes a 24-hour browser cache for trail data, with older cached routes available if the source cannot be reached; this is not a complete offline map.
- Imported GPX processing happens locally, while route coordinates are used in external requests for weather, terrain and nearby information.

## Repository contents and snapshot status

This repository is a backup snapshot of the hosted Site, rather than an automatic deployment pipeline.

- `dist/index.html` — static HTML, CSS and JavaScript interface.
- `dist/data/` — derived mobile site, land-cover, climate and transport inputs, including the versioned route-estimator bundle.
- `scripts/build-mobile-sites.py` — builds the mobile site catalogue from ComReg workbooks; requires `openpyxl`.
- `scripts/build-mobile-propagation-data.py` — prepares land-cover tiles and radio-climatology inputs; requires Pillow.
- `scripts/build-mobile-model-assets.py` — assembles a versioned route-estimator bundle from the site catalogue, height inventory and national clutter/climate inputs.
- `scripts/build-mobile-clutter-map.py` — packages the route model's clutter-height raster as a zoomable, transparent XYZ overlay.
- `scripts/test-mobile-propagation.mjs` — verification script for mobile propagation calculations.
- `scripts/test-mobile-model-assets.py` — checks bundle joins and asset integrity.
- Original backup metadata: Site version **27**, source snapshot commit `ab799574ac331782e9e1310009fb8701b71010a5`.

The complete HTML and mobile/transport datasets have been restored from the original source snapshot. To serve the static app locally, run `python -m http.server 8000 --directory dist` from the repository root, then open `http://localhost:8000`. External data services still require an internet connection.

To regenerate the clutter overlay, pass the versioned route-model `mobile-clutter` directory and the national map bounds to `scripts/build-mobile-clutter-map.py`; the output is written alongside that bundle under `mobile-clutter-map/`.

Updating files here does not automatically update the hosted Site.
