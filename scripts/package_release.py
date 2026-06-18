#!/usr/bin/env python3
"""Build a distributable tarball for the operator-system starter kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import date
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCLUDES = {
    ".DS_Store",
    ".git",
    "__pycache__",
    ".pytest_cache",
    "dist",
}


def should_include(path: Path, out_dir: Path) -> bool:
    if path == out_dir or out_dir in path.parents:
        return False
    if any(part in DEFAULT_EXCLUDES for part in path.parts):
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return path.is_file()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_files(out_dir: Path) -> list[Path]:
    return sorted(path for path in PACKAGE_ROOT.rglob("*") if should_include(path, out_dir))


def build_release(version: str, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_path = out_dir / f"operator-system-starter-{version}.tar.gz"
    manifest_path = out_dir / f"operator-system-starter-{version}.manifest.json"
    files = release_files(out_dir.resolve())

    with tarfile.open(archive_path, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=Path(f"operator-system-starter-{version}") / path.relative_to(PACKAGE_ROOT))

    manifest = {
        "name": "operator-system-starter",
        "version": version,
        "archive": archive_path.name,
        "archive_sha256": sha256(archive_path),
        "file_count": len(files),
        "files": [
            {
                "path": path.relative_to(PACKAGE_ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return archive_path, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=date.today().isoformat(), help="Release version string.")
    parser.add_argument("--out", type=Path, default=PACKAGE_ROOT / "dist", help="Output directory.")
    args = parser.parse_args()
    archive_path, manifest_path = build_release(args.version, args.out.resolve())
    print(archive_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
