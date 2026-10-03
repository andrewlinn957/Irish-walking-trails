#!/usr/bin/env python3
"""Build a compact XYZ raster overlay from the model's representative clutter-height grid."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

WEB_MERCATOR_HALF_WORLD_M = 20037508.342789244
OUTPUT_TILE_SIZE = 256
PALETTE = {
    0: (244, 211, 94, 150),
    5: (142, 201, 119, 165),
    10: (76, 153, 111, 175),
    15: (54, 112, 139, 185),
    20: (111, 68, 145, 195),
}


def build(source: Path, output: Path, bounds: list[float], min_zoom: int = 5, max_zoom: int = 10) -> dict:
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    tile_size_m = float(metadata["tileWorldSizeM"])
    pixel_size_m = float(metadata["pixelSizeProjectedM"])
    source_tile_px = int(metadata["tileSizePx"])
    if not math.isclose(tile_size_m / source_tile_px, pixel_size_m):
        raise ValueError("clutter tile dimensions do not match their metadata")

    source_tiles = {}
    for name in metadata["tiles"]:
        tile_x, tile_y = map(int, Path(name).stem.split("_"))
        # The route estimator reads the red channel of the stored RGBA codes.
        # Converting to luminance would turn (height, 10, 10) into false values.
        image = Image.open(source / name).convert("RGBA")
        if image.size != (source_tile_px, source_tile_px):
            raise ValueError(f"unexpected tile dimensions: {name}")
        source_tiles[(tile_x, tile_y)] = np.asarray(image)[:, :, 0]

    west, south, east, north = map(float, bounds)
    min_x = math.floor(min(tile_x for tile_x, _ in source_tiles) * tile_size_m)
    max_y = max(tile_y for _, tile_y in source_tiles)
    mosaic_width = (max(tile_x for tile_x, _ in source_tiles) - min(tile_x for tile_x, _ in source_tiles) + 1) * source_tile_px
    mosaic_height = (max_y - min(tile_y for _, tile_y in source_tiles) + 1) * source_tile_px
    source_mosaic = np.full((mosaic_height, mosaic_width), int(metadata["unknownCode"]), dtype=np.uint8)
    for (tile_x, tile_y), values in source_tiles.items():
        col = int((tile_x * source_tile_px) - (min_x / pixel_size_m))
        row = ((max_y + 1 - tile_y) * source_tile_px) - source_tile_px
        source_mosaic[row:row + source_tile_px, col:col + source_tile_px] = values

    rgba = np.zeros((256, 256, 4), dtype=np.uint8)
    codes = np.asarray([0, 5, 10, 15, 20, 30, 255], dtype=np.uint8)
    palette = np.asarray([*PALETTE.values(), (0, 0, 0, 0), (0, 0, 0, 0)], dtype=np.uint8)
    if not np.array_equal(codes, np.array([*PALETTE.keys(), 30, 255], dtype=np.uint8)):
        raise AssertionError("palette codes are not ordered as expected")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temp_dir:
        stage = Path(temp_dir)
        tile_count = 0
        for zoom in range(min_zoom, max_zoom + 1):
            map_tile_m = (2 * WEB_MERCATOR_HALF_WORLD_M) / (2 ** zoom)
            min_tx = max(0, int(math.floor((WEB_MERCATOR_HALF_WORLD_M + _lon_to_x(west)) / map_tile_m)))
            max_tx = min(2 ** zoom - 1, int(math.floor((WEB_MERCATOR_HALF_WORLD_M + _lon_to_x(east)) / map_tile_m)))
            min_ty = max(0, int(math.floor((WEB_MERCATOR_HALF_WORLD_M - _lat_to_y(north)) / map_tile_m)))
            max_ty = min(2 ** zoom - 1, int(math.floor((WEB_MERCATOR_HALF_WORLD_M - _lat_to_y(south)) / map_tile_m)))
            xs = np.arange(OUTPUT_TILE_SIZE, dtype=np.float64)
            for tile_x in range(min_tx, max_tx + 1):
                world_x = -WEB_MERCATOR_HALF_WORLD_M + (tile_x + (xs + 0.5) / OUTPUT_TILE_SIZE) * map_tile_m
                source_cols = np.floor(world_x / pixel_size_m - min_x / pixel_size_m).astype(np.int64)
                for tile_y in range(min_ty, max_ty + 1):
                    ys = np.arange(OUTPUT_TILE_SIZE, dtype=np.float64)
                    world_y = WEB_MERCATOR_HALF_WORLD_M - (tile_y + (ys + 0.5) / OUTPUT_TILE_SIZE) * map_tile_m
                    source_rows = np.floor((max_y + 1) * source_tile_px - world_y / pixel_size_m).astype(np.int64)
                    valid_rows = (source_rows >= 0) & (source_rows < mosaic_height)
                    valid_cols = (source_cols >= 0) & (source_cols < mosaic_width)
                    values = np.full((OUTPUT_TILE_SIZE, OUTPUT_TILE_SIZE), int(metadata["unknownCode"]), dtype=np.uint8)
                    row_positions = np.flatnonzero(valid_rows)
                    col_positions = np.flatnonzero(valid_cols)
                    if row_positions.size and col_positions.size:
                        values[np.ix_(row_positions, col_positions)] = source_mosaic[np.ix_(source_rows[row_positions], source_cols[col_positions])]
                    colors = np.zeros((OUTPUT_TILE_SIZE, OUTPUT_TILE_SIZE, 4), dtype=np.uint8)
                    for code, color in PALETTE.items():
                        colors[values == code] = color
                    # Sea and no-data remain transparent; values 0–20 are the same codes used by the route model.
                    tile_dir = stage / str(zoom) / str(tile_x)
                    tile_dir.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(colors, mode="RGBA").save(tile_dir / f"{tile_y}.png", optimize=True)
                    tile_count += 1
        for path in stage.rglob("*"):
            if path.is_file():
                relative = path.relative_to(stage)
                target = output / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    result = {
        "schema": 1,
        "modelVersion": metadata.get("modelVersion"),
        "source": metadata.get("source"),
        "sourceUrl": metadata.get("sourceUrl"),
        "bounds": [west, south, east, north],
        "minZoom": min_zoom,
        "maxZoom": max_zoom,
        "tileSize": OUTPUT_TILE_SIZE,
        "heightColors": {str(code): {"heightM": code, "rgba": list(color)} for code, color in PALETTE.items()},
        "transparentCodes": [int(metadata["seaCode"]), int(metadata["unknownCode"])],
        "tileCount": tile_count,
        "tilesTemplate": "{z}/{x}/{y}.png",
    }
    (output / "metadata.json").write_text(json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8")
    return result


def _lon_to_x(longitude: float) -> float:
    return 6378137.0 * math.radians(longitude)


def _lat_to_y(latitude: float) -> float:
    latitude = max(-85.05112878, min(85.05112878, latitude))
    return 6378137.0 * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="versioned mobile-clutter directory")
    parser.add_argument("--output", type=Path, required=True, help="XYZ output directory")
    parser.add_argument("--bounds", type=float, nargs=4, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"),
                        help="map extent in WGS84 degrees")
    parser.add_argument("--min-zoom", type=int, default=5)
    parser.add_argument("--max-zoom", type=int, default=10)
    args = parser.parse_args()
    result = build(args.source, args.output, args.bounds, args.min_zoom, args.max_zoom)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
