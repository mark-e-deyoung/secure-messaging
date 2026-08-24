#!/usr/bin/env python3
"""Write a deterministic content/provenance manifest for a packaged helper.

The manifest intentionally omits wall-clock time and machine-specific absolute
paths so two builds can be compared meaningfully. A release system may wrap it
in a separate timestamped receipt later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = 1
PROTOCOL = "stdio-v1"
TARGET = "win-x64"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_packages(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("package inventory must be a JSON array")
    normalized: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("package inventory entries must be objects")
        name = entry.get("name")
        version = entry.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise ValueError("package inventory requires non-empty name/version strings")
        normalized.append({"name": name, "version": version})
    return sorted(normalized, key=lambda item: item["name"].lower())


def build_manifest(
    bundle_dir: Path,
    source_commit: str,
    source_dirty: bool,
    python_version: str,
    pyinstaller_version: str,
    packages: list[dict[str, str]],
) -> dict:
    if not bundle_dir.is_dir():
        raise ValueError("bundle directory does not exist")
    if not source_commit or any(ch.isspace() for ch in source_commit):
        raise ValueError("source commit must be a non-empty token")

    files: list[dict[str, object]] = []
    for path in sorted((p for p in bundle_dir.rglob("*") if p.is_file()), key=lambda p: p.as_posix().lower()):
        relative = path.relative_to(bundle_dir).as_posix()
        if relative == "build-manifest.json":
            continue
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    helper = next((item for item in files if item["path"].lower() == "secure-messaging-helper.exe"), None)
    if helper is None:
        raise ValueError("bundle does not contain secure-messaging-helper.exe")

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "target": TARGET,
        "source": {
            "commit": source_commit,
            "dirty": bool(source_dirty),
        },
        "build": {
            "python": python_version,
            "pyinstaller": pyinstaller_version,
            "packages": normalize_packages(packages),
        },
        "entrypoint": {
            "path": helper["path"],
            "sha256": helper["sha256"],
            "size": helper["size"],
        },
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-dirty", choices=("true", "false"), required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--pyinstaller-version", required=True)
    parser.add_argument("--packages-json", type=Path, required=True)
    args = parser.parse_args(argv)

    packages = json.loads(args.packages_json.read_text(encoding="utf-8"))
    manifest = build_manifest(
        args.bundle_dir,
        args.source_commit,
        args.source_dirty == "true",
        args.python_version,
        args.pyinstaller_version,
        packages,
    )
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(sha256_file(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
