# Ireland Trail Atlas

An interactive map for people choosing and planning walks in Ireland. Explore Sport Ireland’s registered trails, inspect the terrain, and find useful places, heritage sites and transport near a route.

**[Open Ireland Trail Atlas](https://ireland-trail-atlas.andrewlinn.chatgpt.site)**

## Find a trail

- Browse trails across Ireland, within a selected county, or in the visible map area.
- Search by trail name or county, and filter by activity and registered difficulty grade.
- Sort by name, distance or ascent.
- View route distance, ascent and grade, with trailhead, nearest town, Irish grid reference, dog access, estimated walking time and waymarking details where the register supplies them.
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

Layers can be switched on and off from the map’s layer menu. Trail grade and amenities are enabled by default; 3D terrain, photos, heritage, transport and mobile estimates are optional.

### GPX routes

Open a GPX file from your device to inspect your own route. The interface also provides GPX export for the selected route. Imported files are read in the browser; the site states that they are not uploaded or saved.

Terrain-derived elevations are estimates. GPX export avoids presenting these estimates as recorded elevations.

### Mobile signal estimates

The route estimator combines ComReg’s public 2026 Q1 mobile licence site schedules with terrain, CORINE land cover and ITU-R radio-climatology inputs. It uses licensed LTE/NR bands and maximum EIRP, terrain path sampling and P.1812-related diffraction calculations, including delta-Bullington diffraction, with a receiver height of 1.5 m.

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
| Land cover | [Copernicus / EEA CORINE Land Cover 2018](https://land.copernicus.eu/en/products/corine-land-cover/clc2018) |
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
- `dist/data/` — derived mobile site, land-cover, climate and transport inputs.
- `scripts/build-mobile-sites.py` — builds the mobile site catalogue from ComReg workbooks; requires `openpyxl`.
- `scripts/build-mobile-propagation-data.py` — prepares land-cover tiles and radio-climatology inputs; requires Pillow.
- `scripts/test-mobile-propagation.mjs` — verification script for mobile propagation calculations.
- Original backup metadata: Site version **27**, source snapshot commit `ab799574ac331782e9e1310009fb8701b71010a5`.

**Known snapshot issue:** the checked-in `dist/index.html`, `dist/data/mobile-sites.json` and `dist/data/transit-stops.geojson` each stop at 200,000 bytes. The HTML ends inside a JavaScript expression, and both data files contain incomplete JSON. This snapshot therefore needs the complete original files restored before it can run locally. The functionality described above is documented from the interface and code present in the snapshot; it is not a claim that this checkout is currently runnable.

Updating files here does not automatically update the hosted Site.
