#!/usr/bin/env python3
"""Build compact, same-origin mobile propagation inputs for Ireland.

The land-cover extract is rendered from the public Copernicus/EEA CLC 2018
MapServer. ITU-R P.1812's supplied median refractivity grids are clipped to
the Irish region used by the route estimator.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CLUTTER_DIR = ROOT / "dist" / "data" / "mobile-clutter"
CLIMATE_FILE = ROOT / "dist" / "data" / "mobile-climate.json"
CLC_SERVICE = "https://image.discomap.eea.europa.eu/arcgis/rest/services/Corine/CLC2018_WM/MapServer"
ITU_ZIP_URL = "https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.1812-8-202509-I!!ZIP-E.zip"

# Values are representative profile-height additions (metres), based on the
# broad P.1812 categories. Five metres is an explicit intermediate estimate
# for low shrub/heath; 30 identifies sea pixels while retaining zero clutter.
CLC_HEIGHT_M = {
    "111": 20, "112": 10, "121": 15, "122": 10, "123": 15, "124": 10,
    "131": 0, "132": 10, "133": 10, "141": 10, "142": 10,
    "211": 0, "212": 0, "213": 0, "221": 0, "222": 5, "223": 0,
    "231": 0, "241": 0, "242": 5, "243": 5, "244": 10,
    "311": 15, "312": 15, "313": 15, "321": 0, "322": 5,
    "323": 5, "324": 10, "331": 0, "332": 0, "333": 0, "334": 0,
    "335": 0, "411": 0, "412": 5, "421": 0, "422": 0, "423": 0,
    "511": 0, "512": 0, "521": 0, "522": 0, "523": 30,
}

EARTH_RADIUS_M = 6378137.0
EXPORT_TILE_PX = 4096
EXPORT_TILE_WORLD_M = EXPORT_TILE_PX * 160
SUBTILE_PX = 1024
SUBTILE_WORLD_M = SUBTILE_PX * 160


def get_bytes(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "IrelandTrailAtlas/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def mercator_xy(lon: float, lat: float) -> tuple[float, float]:
    lat = max(-85.05112878, min(85.05112878, lat))
    return (
        EARTH_RADIUS_M * math.radians(lon),
        EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)),
    )


def dominant_legend_color(image_data: str) -> tuple[int, int, int]:
    image = Image.open(io.BytesIO(base64.b64decode(image_data))).convert("RGBA")
    opaque = [pixel[:3] for pixel in image.getdata() if pixel[3] > 0]
    if not opaque:
        raise ValueError("CLC legend swatch had no visible colour")
    return Counter(opaque).most_common(1)[0][0]


def build_clutter_tiles() -> dict[str, object]:
    CLUTTER_DIR.mkdir(parents=True, exist_ok=True)
    legend = json.loads(get_bytes(f"{CLC_SERVICE}/legend?f=pjson"))
    layers = {item["layerId"]: item for item in legend["layers"]}
    vector_items = layers[0]["legend"]
    raster_items = layers[1]["legend"]
    if len(vector_items) != len(CLC_HEIGHT_M) or len(raster_items) < len(vector_items):
        raise ValueError("Unexpected CORINE legend; review class-to-height mapping")

    rgb_to_height: dict[tuple[int, int, int], int] = {}
    for vector_item, raster_item in zip(vector_items, raster_items):
        code = vector_item["values"][0]
        color = dominant_legend_color(raster_item["imageData"])
        rgb_to_height[color] = CLC_HEIGHT_M[code]
    if len(rgb_to_height) != len(CLC_HEIGHT_M):
        raise ValueError("CLC legend colours are not unique")

    # Include the whole island and the ComReg catalogue's 42 km candidate
    # radius, rounded out to aligned 655.36 km source images.
    xmin, ymin = mercator_xy(-12.6, 50.8)
    xmax, ymax = mercator_xy(-3.3, 56.0)
    ix0, ix1 = math.floor(xmin / EXPORT_TILE_WORLD_M), math.floor(xmax / EXPORT_TILE_WORLD_M)
    iy0, iy1 = math.floor(ymin / EXPORT_TILE_WORLD_M), math.floor(ymax / EXPORT_TILE_WORLD_M)
    image_tiles: list[str] = []
    mapped_pixels = Counter()
    unmapped_pixels = 0
    for iy in range(iy0, iy1 + 1):
        for ix in range(ix0, ix1 + 1):
            left, bottom = ix * EXPORT_TILE_WORLD_M, iy * EXPORT_TILE_WORLD_M
            bbox = f"{left},{bottom},{left + EXPORT_TILE_WORLD_M},{bottom + EXPORT_TILE_WORLD_M}"
            query = urllib.parse.urlencode({
                "bbox": bbox, "bboxSR": "3857", "imageSR": "3857",
                "size": f"{EXPORT_TILE_PX},{EXPORT_TILE_PX}", "format": "png32",
                "transparent": "true", "layers": "show:1", "f": "image",
            })
            png = get_bytes(f"{CLC_SERVICE}/export?{query}")
            source = Image.open(io.BytesIO(png)).convert("RGBA")
            if source.size != (EXPORT_TILE_PX, EXPORT_TILE_PX):
                raise ValueError(f"Unexpected CORINE export dimensions: {source.size}")
            rgba = source.load()
            heights = Image.new("L", source.size, 255)
            out = heights.load()
            unknown_in_tile = 0
            for y in range(EXPORT_TILE_PX):
                for x in range(EXPORT_TILE_PX):
                    red, green, blue, alpha = rgba[x, y]
                    if alpha == 0:
                        continue
                    height = rgb_to_height.get((red, green, blue))
                    if height is None:
                        # The raster palette is categorical; tolerate only
                        # small renderer rounding differences.
                        color = (red, green, blue)
                        nearest, distance2 = min(
                            ((candidate, sum((color[i] - candidate[i]) ** 2 for i in range(3)))
                             for candidate in rgb_to_height), key=lambda item: item[1]
                        )
                        if distance2 > 100:
                            unknown_in_tile += 1
                            continue
                        height = rgb_to_height[nearest]
                    out[x, y] = height
                    mapped_pixels[height] += 1
            if unknown_in_tile:
                raise ValueError(f"{unknown_in_tile} opaque CLC pixels did not match the legend")

            for sub_y in range(EXPORT_TILE_PX // SUBTILE_PX):
                for sub_x in range(EXPORT_TILE_PX // SUBTILE_PX):
                    crop = heights.crop((
                        sub_x * SUBTILE_PX, sub_y * SUBTILE_PX,
                        (sub_x + 1) * SUBTILE_PX, (sub_y + 1) * SUBTILE_PX,
                    ))
                    if crop.getextrema() == (255, 255):
                        continue
                    global_x = ix * 4 + sub_x
                    global_y = iy * 4 + (3 - sub_y)
                    filename = f"{global_x}_{global_y}.png"
                    crop.save(CLUTTER_DIR / filename, compress_level=6)
                    image_tiles.append(filename)
            print(f"CLC source tile {ix},{iy}: {len(png):,} bytes")

    invalid_tiles = []
    for filename in image_tiles:
        try:
            with Image.open(CLUTTER_DIR / filename) as image:
                image.verify()
            if (CLUTTER_DIR / filename).stat().st_size == 0:
                invalid_tiles.append(filename)
        except Exception:
            invalid_tiles.append(filename)
    if invalid_tiles:
        raise ValueError(f"Invalid generated CORINE tiles: {', '.join(invalid_tiles[:5])}")

    metadata = {
        "schema": 1,
        "source": "Copernicus Land Monitoring Service / European Environment Agency, CORINE Land Cover 2018 raster",
        "sourceUrl": "https://land.copernicus.eu/en/products/corine-land-cover/clc2018",
        "serviceUrl": CLC_SERVICE,
        "sourceYear": 2018,
        "crs": "EPSG:3857",
        "pixelSizeProjectedM": 160,
        "tileSizePx": SUBTILE_PX,
        "tileWorldSizeM": SUBTILE_WORLD_M,
        "heightCodesM": {str(value): f"{value} m representative clutter height" for value in [0, 5, 10, 15, 20]},
        "seaCode": 30,
        "unknownCode": 255,
        "clcClassHeightM": CLC_HEIGHT_M,
        "tiles": sorted(image_tiles),
        "pixelCountsByHeightM": {str(key): value for key, value in sorted(mapped_pixels.items())},
        "mappingNote": "Representative heights are estimates mapped from CLC classes to broad ITU-R P.1812 clutter categories. Code 30 marks CLC sea/ocean and contributes zero clutter height.",
    }
    (CLUTTER_DIR / "metadata.json").write_text(json.dumps(metadata, separators=(",", ":")) + "\n")
    print(f"Wrote {len(image_tiles)} compact CORINE subtiles ({sum(mapped_pixels.values()):,} mapped pixels)")
    return metadata


def parse_numeric_grid(data: bytes) -> list[list[float]]:
    return [[float(value) for value in line.split()] for line in data.decode("ascii").splitlines() if line.strip()]


def build_climate_grid(archive_path: Path) -> None:
    if not archive_path.exists():
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(get_bytes(ITU_ZIP_URL))
    with ZipFile(archive_path) as archive:
        dn = parse_numeric_grid(archive.read("DN50.TXT"))
        n0 = parse_numeric_grid(archive.read("N050.TXT"))
        lat = parse_numeric_grid(archive.read("LAT.TXT"))
        lon = parse_numeric_grid(archive.read("LON.TXT"))
    if not all(len(grid) == 121 and all(len(row) == 241 for row in grid) for grid in [dn, n0, lat, lon]):
        raise ValueError("Unexpected ITU P.1812 climatology grid dimensions")

    # Rows 60°N..48°N and columns 342°E..360°E contain Ireland plus margin.
    row_indices = list(range(20, 29))
    col_indices = list(range(228, 241))
    latitudes = [lat[row][0] for row in row_indices]
    longitudes = [lon[0][column] for column in col_indices]
    if latitudes != sorted(latitudes, reverse=True) or longitudes != sorted(longitudes):
        raise ValueError("ITU grid axes are not in the expected order")
    grid = {
        "schema": 1,
        "source": "ITU-R P.1812-8 integral digital products DN50.TXT and N050.TXT",
        "sourceUrl": "https://www.itu.int/rec/R-REC-P.1812/en",
        "gridResolutionDegrees": 1.5,
        "latitudes": latitudes,
        "longitudes": longitudes,
        "deltaN": [[dn[row][column] for column in col_indices] for row in row_indices],
        "n0": [[n0[row][column] for column in col_indices] for row in row_indices],
        "period": "Median annual radio-climatology; source radiosonde analysis 1983–1992",
    }
    CLIMATE_FILE.write_text(json.dumps(grid, separators=(",", ":")) + "\n")
    print(f"Wrote {CLIMATE_FILE.relative_to(ROOT)} ({len(latitudes)} × {len(longitudes)} grid)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--itu-zip", type=Path, default=Path("/tmp/itu-p1812-8.zip"),
                        help="official P.1812 ZIP; downloaded from ITU if the file is absent")
    args = parser.parse_args()
    build_clutter_tiles()
    build_climate_grid(args.itu_zip)


if __name__ == "__main__":
    main()
