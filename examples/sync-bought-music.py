#!/usr/bin/env python3
"""Sync Amazon Music library metadata with local MP3 files.

This script is intentionally metadata-only: it logs into Amazon Music using the
existing `AmazonMusic` client, reads track metadata from the account library,
and compares it against local MP3 filenames.

It does not download, decrypt, or bypass any Amazon controls.
"""

import argparse
import getpass
import json
import os
import re
from pathlib import Path

from amazonmusic import AmazonMusic


MP3_EXTENSIONS = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav"}


def normalize(value):
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def build_key(title, artist):
    return "{}::{}".format(normalize(title), normalize(artist))


def parse_track_document(document):
    title = (
        document.get("title")
        or document.get("trackName")
        or document.get("name")
        or ""
    )
    artist = (
        document.get("artistName")
        or document.get("artist")
        or document.get("albumArtistName")
        or ""
    )
    album = document.get("albumName") or document.get("album") or ""

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "source": "amazon",
        "key": build_key(title, artist),
    }


def extract_online_tracks(search_results):
    tracks = []
    for label, result in search_results:
        if "track" not in label:
            continue

        for item in result.get("documentList", []):
            document = item.get("document", {})
            parsed = parse_track_document(document)
            if parsed["title"]:
                tracks.append(parsed)

    unique = {}
    for track in tracks:
        unique[track["key"]] = track

    return list(unique.values())


def parse_local_filename(path):
    stem = path.stem
    # Common pattern: Artist - Title
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
    else:
        artist, title = "", stem

    return {
        "title": title.strip(),
        "artist": artist.strip(),
        "album": "",
        "path": str(path),
        "source": "local",
        "key": build_key(title, artist),
    }


def scan_local_tracks(base_dir):
    tracks = []
    for path in Path(base_dir).rglob("*"):
        if path.is_file() and path.suffix.lower() in MP3_EXTENSIONS:
            tracks.append(parse_local_filename(path))

    unique = {}
    for track in tracks:
        unique[track["key"]] = track

    return list(unique.values())


def default_credentials():
    email = input("Amazon email: ").strip()
    password = getpass.getpass("Amazon password: ")
    return [email, password]


def main():
    parser = argparse.ArgumentParser(
        description="Compare Amazon Music library tracks to local audio files"
    )
    parser.add_argument(
        "--music-dir",
        required=True,
        help="Path to local music directory to scan",
    )
    parser.add_argument(
        "--output",
        default="amazon-music-sync-report.json",
        help="Report output path (JSON)",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("AMAZON_EMAIL"),
        help="Amazon email (optional; can also use AMAZON_EMAIL env var)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("AMAZON_PASSWORD"),
        help="Amazon password (optional; can also use AMAZON_PASSWORD env var)",
    )

    args = parser.parse_args()

    if args.email and args.password:
        credentials = [args.email, args.password]
    else:
        credentials = default_credentials

    am = AmazonMusic(credentials=credentials)
    search_results = am.search(
        None,
        library_only=True,
        tracks=True,
        albums=False,
        playlists=False,
        artists=False,
        stations=False,
    )

    online_tracks = extract_online_tracks(search_results)
    local_tracks = scan_local_tracks(args.music_dir)

    online_by_key = {t["key"]: t for t in online_tracks}
    local_by_key = {t["key"]: t for t in local_tracks}

    missing_local = [
        t for key, t in online_by_key.items() if key and key not in local_by_key
    ]
    local_only = [
        t for key, t in local_by_key.items() if key and key not in online_by_key
    ]

    report = {
        "summary": {
            "online_track_count": len(online_tracks),
            "local_track_count": len(local_tracks),
            "missing_local_count": len(missing_local),
            "local_only_count": len(local_only),
        },
        "missing_local": sorted(missing_local, key=lambda t: (t["artist"], t["title"])),
        "local_only": sorted(local_only, key=lambda t: (t["artist"], t["title"])),
    }

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("Wrote sync report to {}".format(args.output))
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
