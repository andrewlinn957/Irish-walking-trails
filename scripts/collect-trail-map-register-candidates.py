#!/usr/bin/env python3
"""Extract explicit publisher map links from the Sport Ireland trail register.

This is an offline pass. It keeps only links whose register label explicitly
offers a downloadable map, then leaves file validation to the paced verifier.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


EXTENSIONS = {".pdf": "pdf", ".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".webp": "webp", ".gif": "gif"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=Path("/tmp/research-routes.json"))
    parser.add_argument("--index", type=Path, default=Path("dist/data/trail-map-links.json"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/trail-register-map-candidates.json"))
    args = parser.parse_args()

    register = json.loads(args.register.read_text())
    index = json.loads(args.index.read_text())
    grouped = {}
    bad = []
    for feature in register.get("features", []):
        attrs = feature.get("attributes", {})
        tid = str(attrs.get("TrailID", ""))
        entry = index["trails"].get(tid)
        if not entry or entry.get("maps"):
            continue
        for raw in (attrs.get("ExternalLinks") or "").split("^"):
            if "|" not in raw:
                continue
            raw_url, label = raw.split("|", 1)
            url = raw_url.strip()
            label = re.sub(r"\s+", " ", label).strip()
            if not re.search(r"downloadable\s+map", label, re.I):
                continue
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or parts.username or parts.password:
                bad.append({"trailId": tid, "url": url, "reason": "invalid URL"})
                continue
            suffix = Path(unquote(parts.path)).suffix.lower()
            fmt = EXTENSIONS.get(suffix)
            if not fmt:
                bad.append({"trailId": tid, "url": url, "reason": "map link has no direct image/PDF extension"})
                continue
            candidate = grouped.setdefault(url, {"url": url, "kind": fmt, "associations": []})
            if not any(a["trailId"] == tid for a in candidate["associations"]):
                candidate["associations"].append({
                    "trailId": tid,
                    "name": entry["name"],
                    "sourcePage": entry["pageUrl"],
                    "title": label or "Download trail map",
                })

    output = {"offlineOnly": True, "candidateCount": len(grouped),
              "associationCount": sum(len(x["associations"]) for x in grouped.values()),
              "excludedNonFileLinks": bad,
              "candidates": sorted(grouped.values(), key=lambda item: item["url"])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: output[k] for k in ("offlineOnly", "candidateCount", "associationCount")}))


if __name__ == "__main__":
    main()
