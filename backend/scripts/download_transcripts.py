#!/usr/bin/env python3
"""
download_transcripts.py — Download Lenny's Podcast transcripts from the
ChatPRD/lennys-podcast-transcripts GitHub archive.

Downloads the tarball (not git clone — avoids git dependency in Docker build),
extracts into backend/data/raw/episodes/.

Usage:
    python backend/scripts/download_transcripts.py            # idempotent download
    python backend/scripts/download_transcripts.py --refresh   # force re-download
"""

import argparse
import io
import logging
import os
import sys
import tarfile

import requests

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("download_transcripts")

TARBALL_URL = (
    "https://codeload.github.com/ChatPRD/"
    "lennys-podcast-transcripts/tar.gz/refs/heads/main"
)

# Resolve paths relative to the project root (two levels up from this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
RAW_DIR = os.path.join(PROJECT_ROOT, "backend", "data", "raw")
EPISODES_DIR = os.path.join(RAW_DIR, "episodes")


def has_existing_content(directory: str) -> bool:
    """Check if directory already has episode content."""
    if not os.path.isdir(directory):
        return False
    # Check for at least one subdirectory (guest folder)
    for entry in os.listdir(directory):
        if os.path.isdir(os.path.join(directory, entry)):
            return True
    return False


def download_and_extract(force: bool = False) -> int:
    """
    Download the tarball and extract episode transcripts.

    Returns:
        Number of episodes extracted.
    """
    if not force and has_existing_content(EPISODES_DIR):
        # Count existing episodes
        count = sum(
            1
            for entry in os.listdir(EPISODES_DIR)
            if os.path.isdir(os.path.join(EPISODES_DIR, entry))
        )
        logger.info(
            "Episodes directory already has %d episodes. "
            "Use --refresh to force re-download.",
            count,
        )
        return count

    logger.info("Downloading transcript archive from GitHub...")
    try:
        response = requests.get(TARBALL_URL, timeout=120, stream=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to download tarball: %s", exc)
        sys.exit(1)

    total_bytes = int(response.headers.get("content-length", 0))
    logger.info(
        "Download complete (%s bytes). Extracting...",
        f"{total_bytes:,}" if total_bytes else "unknown size",
    )

    # Read full response into memory for tarfile extraction
    tarball_bytes = io.BytesIO(response.content)

    os.makedirs(RAW_DIR, exist_ok=True)

    # The tarball root is "lennys-podcast-transcripts-main/"
    # We want to extract only the episodes/ subtree
    TARBALL_PREFIX = "lennys-podcast-transcripts-main/episodes/"

    episode_count = 0
    extracted_files = 0

    with tarfile.open(fileobj=tarball_bytes, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith(TARBALL_PREFIX):
                continue

            # Remap path: strip the tarball prefix, put under our EPISODES_DIR
            relative_path = member.name[len(TARBALL_PREFIX) :]
            if not relative_path:
                continue

            target_path = os.path.join(EPISODES_DIR, relative_path)

            if member.isdir():
                os.makedirs(target_path, exist_ok=True)
                episode_count += 1
            elif member.isfile():
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                # Extract file content
                source = tar.extractfile(member)
                if source is not None:
                    with open(target_path, "wb") as f:
                        f.write(source.read())
                    extracted_files += 1

    logger.info(
        "Extracted %d episodes (%d files) to %s",
        episode_count,
        extracted_files,
        EPISODES_DIR,
    )
    return episode_count


def main():
    parser = argparse.ArgumentParser(
        description="Download Lenny's Podcast transcripts from GitHub"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-download even if episodes already exist",
    )
    args = parser.parse_args()

    count = download_and_extract(force=args.refresh)
    logger.info("Done. %d episode directories available.", count)


if __name__ == "__main__":
    main()
