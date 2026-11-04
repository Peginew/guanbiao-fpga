#!/usr/bin/env python3
"""Restore the original GuanBiao PNGs from SHA256-verified Release parts.

Uses only Python's standard library. Existing files with different content are
never overwritten. No pickle, model loading, or external commands are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile


BASE = Path(__file__).resolve().parent
RELEASE_PREFIX = (
    "https://github.com/Peginew/guanbiao-fpga/releases/download/"
    "instrument-images-20261104/"
)
CHUNK = 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(CHUNK), b""):
            digest.update(data)
    return digest.hexdigest()


def safe_relative(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ValueError(f"Unsafe ZIP path: {name!r}")
    pieces = name.split("/")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or any(piece in {"", ".", ".."} for piece in pieces)
        or any(":" in piece for piece in pieces)
        or len(pieces) != 3
        or pieces[0] != "images"
        or pieces[1] not in "ABCDEFGH"
        or len(pieces[1]) != 1
        or not pieces[2].lower().endswith(".png")
    ):
        raise ValueError(f"Unsafe or unexpected image path: {name!r}")
    return path


def destination(root: Path, name: str) -> Path:
    relative = safe_relative(name)
    root = root.resolve()
    target = root.joinpath(*relative.parts)
    # Reject links before any directory creation or file writes.
    for component in [target, *target.parents]:
        if component == root:
            break
        if component.is_symlink():
            raise ValueError(f"Refusing symbolic link: {component}")
    if not target.resolve().is_relative_to(root):
        raise ValueError(f"Path escapes output directory: {name!r}")
    return target


def read_metadata():
    manifest = json.loads((BASE / "image_archive.json").read_text(encoding="utf-8"))
    index_path = BASE / "image_index.json"
    if sha256(index_path) != manifest["image_index_sha256"]:
        raise ValueError("image_index.json SHA256 differs from archive manifest")
    rows = json.loads(index_path.read_text(encoding="utf-8"))["images"]
    expected = {}
    folded = set()
    for row in rows:
        name = row["path"]
        safe_relative(name)
        if name in expected or name.casefold() in folded:
            raise ValueError("Duplicate image path in index")
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("Invalid image SHA256")
        if type(row["bytes"]) is not int or row["bytes"] < 1:
            raise ValueError("Invalid image length")
        expected[name] = row
        folded.add(name.casefold())
    if len(expected) != manifest["image_count"] or len(expected) != 497:
        raise ValueError("Image count differs from manifest")
    parts = manifest["parts"]
    if not parts:
        raise ValueError("No Release parts in manifest")
    for number, part in enumerate(parts, 1):
        name = f"images.zip.part{number:04d}"
        if part["name"] != name or part["url"] != RELEASE_PREFIX + name:
            raise ValueError("Unexpected Release part name or URL")
        if not re.fullmatch(r"[0-9a-f]{64}", part["sha256"]):
            raise ValueError("Invalid Release part SHA256")
        if type(part["bytes"]) is not int or part["bytes"] < 1:
            raise ValueError("Invalid Release part length")
    if sum(part["bytes"] for part in parts) != manifest["archive_bytes"]:
        raise ValueError("Release part lengths do not sum to ZIP length")
    return manifest, expected


def download_archive(manifest, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    for number, part in enumerate(manifest["parts"], 1):
        target = cache / part["name"]
        if target.is_file() and target.stat().st_size == part["bytes"] and sha256(target) == part["sha256"]:
            continue
        request = urllib.request.Request(part["url"], headers={"User-Agent": "GuanBiao-dataset-downloader/1.0"})
        fd, temporary_name = tempfile.mkstemp(prefix=part["name"] + ".", suffix=".download", dir=cache)
        temporary = Path(temporary_name)
        try:
            digest = hashlib.sha256()
            count = 0
            with os.fdopen(fd, "wb") as output, urllib.request.urlopen(request, timeout=120) as response:
                for data in iter(lambda: response.read(CHUNK), b""):
                    count += len(data)
                    if count > part["bytes"]:
                        raise ValueError(f"Part too large: {part['name']}")
                    digest.update(data)
                    output.write(data)
            if count != part["bytes"] or digest.hexdigest() != part["sha256"]:
                raise ValueError(f"Part SHA256/length mismatch: {part['name']}")
            os.replace(temporary, target)
            print(f"Downloaded {number}/{len(manifest['parts'])}: {part['name']}", flush=True)
        finally:
            temporary.unlink(missing_ok=True)
    archive = cache / "images.zip"
    if archive.is_file() and archive.stat().st_size == manifest["archive_bytes"] and sha256(archive) == manifest["archive_sha256"]:
        return archive
    fd, temporary_name = tempfile.mkstemp(prefix="images.", suffix=".assembling", dir=cache)
    temporary = Path(temporary_name)
    try:
        digest = hashlib.sha256()
        count = 0
        with os.fdopen(fd, "wb") as output:
            for part in manifest["parts"]:
                part_path = cache / part["name"]
                part_digest = hashlib.sha256()
                with part_path.open("rb") as source:
                    for data in iter(lambda: source.read(CHUNK), b""):
                        digest.update(data)
                        part_digest.update(data)
                        count += len(data)
                        output.write(data)
                if part_digest.hexdigest() != part["sha256"]:
                    raise ValueError(f"Cached part changed: {part['name']}")
        if count != manifest["archive_bytes"] or digest.hexdigest() != manifest["archive_sha256"]:
            raise ValueError("Assembled ZIP SHA256/length mismatch")
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def verify_archive(archive: Path, manifest, expected):
    if archive.stat().st_size != manifest["archive_bytes"] or sha256(archive) != manifest["archive_sha256"]:
        raise ValueError("ZIP SHA256/length mismatch")
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        names = [member.filename for member in members]
        for name in names:
            safe_relative(name)
        if len(names) != len(expected) or len(set(names)) != len(names) or set(names) != set(expected):
            raise ValueError("ZIP contains missing, duplicate, or unindexed members")
        for member in members:
            row = expected[member.filename]
            mode = member.external_attr >> 16
            if member.is_dir() or stat.S_ISLNK(mode) or member.flag_bits & 1:
                raise ValueError(f"Unsupported ZIP member: {member.filename}")
            if member.compress_type != zipfile.ZIP_STORED or member.file_size != row["bytes"]:
                raise ValueError(f"Image size/method mismatch: {member.filename}")
            digest = hashlib.sha256()
            with bundle.open(member) as stream:
                for data in iter(lambda: stream.read(CHUNK), b""):
                    digest.update(data)
            if digest.hexdigest() != row["sha256"]:
                raise ValueError(f"Image SHA256 mismatch: {member.filename}")


def restore(archive: Path, expected, output_root: Path):
    output_root = output_root.resolve()
    skip = set()
    # Check every existing destination before writing any new image.
    for name, row in expected.items():
        target = destination(output_root, name)
        if target.exists():
            if not target.is_file() or target.stat().st_size != row["bytes"] or sha256(target) != row["sha256"]:
                raise FileExistsError(f"Different existing content; refusing overwrite: {target}")
            skip.add(name)
    restored = 0
    with zipfile.ZipFile(archive) as bundle:
        for name, row in expected.items():
            if name in skip:
                continue
            target = destination(output_root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(prefix=".guanbiao-", suffix=".png.part", dir=target.parent)
            temporary = Path(temporary_name)
            try:
                digest = hashlib.sha256()
                count = 0
                with os.fdopen(fd, "wb") as output, bundle.open(name) as source:
                    for data in iter(lambda: source.read(CHUNK), b""):
                        digest.update(data)
                        count += len(data)
                        output.write(data)
                if count != row["bytes"] or digest.hexdigest() != row["sha256"]:
                    raise ValueError(f"Extracted image differs: {name}")
                # Exclusive create prevents overwriting a destination created
                # after the preflight. Temporary bytes are already verified.
                with target.open("xb") as output, temporary.open("rb") as source:
                    shutil.copyfileobj(source, output, CHUNK)
                restored += 1
            finally:
                temporary.unlink(missing_ok=True)
    return restored, len(skip)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already assembled local images.zip; no network")
    parser.add_argument("--output", type=Path, default=BASE, help="Dataset directory (default: this script's directory)")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "GuanBiao-images-20261104")
    parser.add_argument("--verify-only", action="store_true", help="Verify ZIP and all497 image hashes without extracting")
    args = parser.parse_args()
    manifest, expected = read_metadata()
    archive = args.archive if args.archive is not None else download_archive(manifest, args.cache)
    verify_archive(archive, manifest, expected)
    if args.verify_only:
        print("PASS: ZIP and all497 original PNG hashes verified; no images extracted.")
    else:
        restored, skipped = restore(archive, expected, args.output)
        print(f"PASS: restored {restored}, already present with matching SHA256 {skipped}; total {len(expected)}.")


if __name__ == "__main__":
    main()
