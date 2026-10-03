#!/usr/bin/env python3
"""Build a versioned static mobile-model bundle for the Ireland Trails app."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "2026-10-03"
DEFAULT_COVERAGE_ROOT = ROOT.parent / "ireland-mobile-coverage"
NETWORK_INDEX = {"Eir": 0, "Three": 1, "Vodafone": 2}
HEIGHT_DEFAULT_M = 30.0


def coordinate_key(network: str, longitude: object, latitude: object) -> tuple[int, float, float]:
    if network not in NETWORK_INDEX:
        raise ValueError(f"unknown network in height inventory: {network!r}")
    try:
        lon, lat = float(longitude), float(latitude)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid site coordinate for {network}") from exc
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f"invalid site coordinate for {network}")
    return NETWORK_INDEX[network], round(lon, 6), round(lat, 6)


def build_height_index(rows: list[dict[str, str]]) -> tuple[dict[tuple[int, float, float], float | None], int]:
    result: dict[tuple[int, float, float], float | None] = {}
    estimated = 0
    for row in rows:
        key = coordinate_key(row.get("network", ""), row.get("longitude"), row.get("latitude"))
        if key in result:
            raise ValueError(f"duplicate height inventory key: {key}")
        raw = (row.get("estimatedAntennaHeightM") or "").strip()
        height: float | None = None
        if raw:
            try:
                height = float(raw)
            except ValueError as exc:
                raise ValueError(f"invalid antenna-height estimate at {key}") from exc
            if not math.isfinite(height) or not 1 <= height <= 120:
                raise ValueError(f"antenna-height estimate outside 1–120 m at {key}")
            estimated += 1
        result[key] = height
    return result, estimated


def enrich_site_catalogue(catalogue: dict, height_index: dict[tuple[int, float, float], float | None]) -> tuple[dict, dict[str, int]]:
    if catalogue.get("networks") != ["Eir", "Three", "Vodafone"] or not isinstance(catalogue.get("records"), list):
        raise ValueError("site catalogue has an unexpected schema or network order")
    records = []
    used = set()
    estimated = defaults = 0
    for record in catalogue["records"]:
        if not isinstance(record, list) or len(record) < 4:
            raise ValueError("site catalogue contains an invalid site tuple")
        key = coordinate_key(catalogue["networks"][record[0]], record[1], record[2])
        if key in used:
            raise ValueError(f"duplicate site catalogue key: {key}")
        used.add(key)
        if key not in height_index:
            raise ValueError(f"height inventory has no exact operator/coordinate match for {key}")
        height = height_index[key]
        if height is None:
            height = HEIGHT_DEFAULT_M
            defaults += 1
        else:
            estimated += 1
        records.append([record[0], record[1], record[2], record[3], height])
    if used != set(height_index):
        extras = len(set(height_index) - used)
        raise ValueError(f"height inventory contains {extras} rows that do not match the site catalogue")
    result = dict(catalogue)
    result["modelVersion"] = MODEL_VERSION
    result["heightField"] = "transmitterHeightM"
    result["tupleFields"] = ["networkIndex", "longitude", "latitude", "bands", "transmitterHeightM"]
    result["records"] = records
    return result, {"records": len(records), "planningHeightEstimates": estimated, "defaultHeight": defaults}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read valid JSON from {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path, str]:
    if args.coverage_repo:
        root = args.coverage_repo.resolve()
        climate_path = args.climate_source or root / "model-inputs/mobile-climate.json"
        paths = (
            args.site_catalogue or ROOT / "dist/data/mobile-sites.json",
            args.height_inventory or root / "model-inputs/mobile-site-height-estimates.csv",
            args.clutter_source or root / "research/clcplus-scenario-2026-10-02/mobile-clutter",
            climate_path,
            args.output or ROOT / "dist/data" / f"mobile-model-{MODEL_VERSION}",
        )
        revision = args.source_revision or subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True
        ).stdout.strip()
        return paths[0], paths[1], paths[2], paths[3], paths[4], revision
    if not all([args.site_catalogue, args.height_inventory, args.clutter_source, args.climate_source, args.output]):
        raise ValueError("provide --coverage-repo or all five explicit input/output paths")
    return (args.site_catalogue, args.height_inventory, args.clutter_source,
            args.climate_source, args.output, args.source_revision or "unspecified")


def build_bundle(site_path: Path, height_path: Path, clutter_dir: Path, climate_path: Path,
                 output_dir: Path, source_revision: str) -> dict:
    catalogue = read_json(site_path)
    with height_path.open(newline="", encoding="utf-8") as stream:
        height_rows = list(csv.DictReader(stream))
    if not height_rows or not {"network", "longitude", "latitude", "estimatedAntennaHeightM"}.issubset(height_rows[0]):
        raise ValueError("height inventory is empty or missing required columns")
    height_index, input_estimated = build_height_index(height_rows)
    enriched, counts = enrich_site_catalogue(catalogue, height_index)
    if counts["planningHeightEstimates"] != input_estimated:
        raise ValueError("height estimate count changed during catalogue join")

    clutter_metadata_path = clutter_dir / "metadata.json"
    clutter_metadata = read_json(clutter_metadata_path)
    if "CLC+ Backbone 2021" not in clutter_metadata.get("source", ""):
        raise ValueError("clutter bundle is not the CLC+ Backbone 2021 scenario")
    if clutter_metadata.get("pixelSizeProjectedM") != 160 or clutter_metadata.get("seaCode") != 30:
        raise ValueError("CLC+ clutter grid or sea-code metadata does not match the national scenario")
    tile_names = clutter_metadata.get("tiles")
    if not isinstance(tile_names, list) or not tile_names or len(tile_names) != len(set(tile_names)):
        raise ValueError("CLC+ tile list is empty or contains duplicates")
    tile_paths = []
    for name in tile_names:
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".png"):
            raise ValueError(f"invalid CLC+ tile name: {name!r}")
        tile_path = clutter_dir / name
        if not tile_path.is_file():
            raise ValueError(f"missing CLC+ tile: {tile_path}")
        tile_paths.append(tile_path)
    climate = read_json(climate_path)
    if not isinstance(climate.get("deltaN"), list) or not climate.get("sourceUrl"):
        raise ValueError("climate data has an unexpected schema")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}-", dir=output_dir.parent) as tmp:
        stage = Path(tmp)
        site_out = dict(enriched)
        (stage / "mobile-sites.json").write_text(json.dumps(site_out, separators=(",", ":")), encoding="utf-8")
        climate["modelVersion"] = MODEL_VERSION
        (stage / "mobile-climate.json").write_text(json.dumps(climate, separators=(",", ":")), encoding="utf-8")
        stage_clutter = stage / "mobile-clutter"
        stage_clutter.mkdir()
        clutter_metadata["modelVersion"] = MODEL_VERSION
        (stage_clutter / "metadata.json").write_text(json.dumps(clutter_metadata, separators=(",", ":")), encoding="utf-8")
        for tile_path in tile_paths:
            shutil.copyfile(tile_path, stage_clutter / tile_path.name)
        manifest = {
            "schema": 1,
            "modelVersion": MODEL_VERSION,
            "sourceRevision": source_revision,
            "siteCounts": counts,
            "defaultHeightM": HEIGHT_DEFAULT_M,
            "heightInventorySha256": sha256(height_path),
            "clutterSource": clutter_metadata["source"],
            "clutterSourceUrl": clutter_metadata.get("sourceUrl"),
            "clutterPixelSizeProjectedM": clutter_metadata["pixelSizeProjectedM"],
            "clutterFallback": clutter_metadata.get("fallback"),
            "clutterTiles": [{"name": name, "sha256": sha256(stage_clutter / name)} for name in tile_names],
            "climateSourceUrl": climate["sourceUrl"],
            "siteCatalogueSource": catalogue.get("source"),
        }
        (stage / "mobile-model-metadata.json").write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")
        # The version-specific directory is switched into use by one HTML constant.
        # Per-file atomic replacements keep repeated local builds recoverable.
        for source in stage.rglob("*"):
            if source.is_file():
                relative = source.relative_to(stage)
                target = output_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-repo", type=Path, default=DEFAULT_COVERAGE_ROOT,
                        help="local Ireland-mobile-coverage checkout")
    parser.add_argument("--site-catalogue", type=Path)
    parser.add_argument("--height-inventory", type=Path)
    parser.add_argument("--clutter-source", type=Path)
    parser.add_argument("--climate-source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    try:
        paths = resolve_inputs(args)
        result = build_bundle(*paths)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(paths[4]), "modelVersion": MODEL_VERSION,
                      "siteCounts": result["siteCounts"], "clutterTiles": len(result["clutterTiles"]),
                      "bytes": sum(p.stat().st_size for p in paths[4].rglob("*") if p.is_file())}, indent=2))


if __name__ == "__main__":
    main()
