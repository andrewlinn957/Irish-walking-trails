import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build-mobile-model-assets.py"


class MobileModelAssetBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source_sites = self.root / "sites.json"
        self.height_csv = self.root / "heights.csv"
        self.clutter = self.root / "clutter"
        self.clutter.mkdir()
        self.climate = self.root / "climate.json"
        self.output = self.root / "bundle"
        self.source_sites.write_text(json.dumps({
            "networks": ["Eir", "Three", "Vodafone"],
            "records": [
                [0, -8.0, 53.5, [[900, 60, 3]]],
                [1, -7.0, 52.0, [[800, 58, 1]]],
            ],
        }))
        with self.height_csv.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["network", "longitude", "latitude", "estimatedAntennaHeightM", "sourceQuote", "estimateStatus"])
            writer.writeheader()
            writer.writerow({"network": "Eir", "longitude": "-8.000000", "latitude": "53.500000", "estimatedAntennaHeightM": "18.5", "sourceQuote": "private source detail", "estimateStatus": "proposed_or_replacement"})
            writer.writerow({"network": "Three", "longitude": "-7.000000", "latitude": "52.000000", "estimatedAntennaHeightM": "", "sourceQuote": "another detail", "estimateStatus": "unknown"})
        self.clutter.joinpath("tile.png").write_bytes(b"fixture tile bytes")
        self.clutter.joinpath("metadata.json").write_text(json.dumps({
            "source": "Copernicus Land Monitoring Service CLC+ Backbone 2021",
            "sourceUrl": "https://example.test/clcplus",
            "pixelSizeProjectedM": 160,
            "tileSizePx": 1024,
            "tiles": ["tile.png"],
            "heightCodesM": {"0": "0 m", "5": "5 m", "10": "10 m", "15": "15 m", "20": "20 m"},
            "seaCode": 30,
            "unknownCode": 255,
            "fallback": "CORINE 2018 retained for no-data and outside area",
        }))
        self.climate.write_text(json.dumps({"schema": 1, "sourceUrl": "https://www.itu.int/rec/R-REC-P.1812/en", "deltaN": [[41]]}))

    def run_builder(self, extra_rows=None):
        if extra_rows:
            with self.height_csv.open("a", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["network", "longitude", "latitude", "estimatedAntennaHeightM", "sourceQuote", "estimateStatus"])
                writer.writerows(extra_rows)
        return subprocess.run([
            sys.executable, str(BUILDER),
            "--site-catalogue", str(self.source_sites),
            "--height-inventory", str(self.height_csv),
            "--clutter-source", str(self.clutter),
            "--climate-source", str(self.climate),
            "--output", str(self.output),
            "--source-revision", "fixture-revision",
        ], capture_output=True, text=True)

    def test_exact_site_join_and_default_height_produce_compact_runtime_rows(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = json.loads((self.output / "mobile-sites.json").read_text())
        self.assertEqual(bundle["records"], [
            [0, -8.0, 53.5, [[900, 60, 3]], 18.5],
            [1, -7.0, 52.0, [[800, 58, 1]], 30.0],
        ])
        self.assertNotIn("private source detail", (self.output / "mobile-sites.json").read_text())
        self.assertNotIn("proposed_or_replacement", (self.output / "mobile-sites.json").read_text())

    def test_bundle_copies_clc_tiles_and_versions_all_runtime_inputs(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "mobile-clutter" / "tile.png").read_bytes(), b"fixture tile bytes")
        manifest = json.loads((self.output / "mobile-model-metadata.json").read_text())
        catalogue = json.loads((self.output / "mobile-sites.json").read_text())
        clutter = json.loads((self.output / "mobile-clutter" / "metadata.json").read_text())
        climate = json.loads((self.output / "mobile-climate.json").read_text())
        self.assertEqual(manifest["modelVersion"], "2026-10-03")
        self.assertEqual(manifest["sourceRevision"], "fixture-revision")
        self.assertEqual(catalogue["modelVersion"], manifest["modelVersion"])
        self.assertEqual(clutter["modelVersion"], manifest["modelVersion"])
        self.assertEqual(climate["modelVersion"], manifest["modelVersion"])
        self.assertEqual(manifest["siteCounts"], {"records": 2, "planningHeightEstimates": 1, "defaultHeight": 1})

    def test_duplicate_height_keys_are_rejected_without_writing_bundle(self):
        duplicate = {"network": "Eir", "longitude": "-8.0", "latitude": "53.5", "estimatedAntennaHeightM": "20", "sourceQuote": "", "estimateStatus": "existing_as_described"}
        result = self.run_builder([duplicate])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr.lower())
        self.assertFalse(self.output.exists())

    def test_unmatched_site_is_rejected_without_writing_bundle(self):
        with self.height_csv.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        rows[1]["longitude"] = "-7.000100"
        with self.height_csv.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        result = self.run_builder()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("match", result.stderr.lower())
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
