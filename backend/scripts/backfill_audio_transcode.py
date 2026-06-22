"""One-off backfill: transcode existing participant recordings to MP3.

Recordings captured before the cross-browser-playback fix are stored as
webm/opus (or ogg), which Safari/iOS cannot decode. This script walks every
`InterviewTurn` whose `audio_recording_url` points at a non-playable format,
downloads the original from storage, transcodes it to MP3, uploads the MP3,
and repoints the turn's URL at the new file.

Safe to re-run: turns already on a playable format are skipped, so a second
pass only touches whatever failed the first time. The original files are left
in storage (orphaned) rather than deleted — cheap insurance against a bad run.

Usage (from backend/, with prod env vars loaded so it hits the real DB + R2):

    # Dry run — report what WOULD change, touch nothing:
    python -m scripts.backfill_audio_transcode --dry-run

    # Real run:
    python -m scripts.backfill_audio_transcode

    # Limit the batch (useful for a first cautious pass):
    python -m scripts.backfill_audio_transcode --limit 25

Requires ffmpeg on PATH (present in the backend Docker image). Run it as a
Cloud Run job built from the backend image, or locally with prod DATABASE_URL
+ R2_* env vars exported.
"""

import argparse
import os
import sys

from sqlalchemy import select

# Allow running both as `python -m scripts.backfill_audio_transcode` and directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.interview import InterviewTurn  # noqa: E402
from app.services.storage import (  # noqa: E402
    download_audio,
    storage_key_from_url,
    upload_audio,
)
from app.services.transcode import needs_transcode, transcode_to_mp3  # noqa: E402


def _ext_from_url(url: str) -> str:
    path = url.split("?", 1)[0]
    return os.path.splitext(path)[1] or ".webm"


def run(dry_run: bool, limit: int | None, participant_id: str | None) -> int:
    db = SessionLocal()
    converted = skipped = failed = 0
    try:
        stmt = select(InterviewTurn).where(InterviewTurn.audio_recording_url.isnot(None))
        if participant_id:
            stmt = stmt.where(InterviewTurn.participant_id == participant_id)
        turns = db.execute(stmt).scalars().all()
        scope = f" for participant {participant_id}" if participant_id else ""
        print(f"Scanning {len(turns)} turns with a recording URL{scope}...")

        for turn in turns:
            url = turn.audio_recording_url
            ext = _ext_from_url(url)
            if not needs_transcode(ext):
                continue  # already mp3/m4a/etc.

            if limit is not None and converted >= limit:
                print(f"Reached --limit {limit}; stopping.")
                break

            key = storage_key_from_url(url)
            if not key:
                print(f"  ! turn {turn.id}: cannot derive storage key from {url!r} — skipped")
                skipped += 1
                continue

            if dry_run:
                print(f"  [dry-run] turn {turn.id}: would transcode {key}")
                converted += 1
                continue

            try:
                original = download_audio(key)
            except Exception as e:
                print(f"  ! turn {turn.id}: download failed for {key}: {e} — skipped")
                failed += 1
                continue

            mp3 = transcode_to_mp3(original, ext)
            if not mp3:
                print(f"  ! turn {turn.id}: transcode failed for {key} — skipped")
                failed += 1
                continue

            new_key = os.path.splitext(key)[0] + ".mp3"
            new_url = upload_audio(mp3, new_key)
            turn.audio_recording_url = new_url
            db.commit()
            converted += 1
            print(f"  ✓ turn {turn.id}: {key} -> {new_key}")

        print(
            f"\nDone. converted={converted} failed={failed} "
            f"skipped(no-key)={skipped} {'(dry-run, nothing written)' if dry_run else ''}"
        )
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Transcode legacy participant recordings to MP3.")
    ap.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")
    ap.add_argument("--limit", type=int, default=None, help="Max recordings to convert this run.")
    ap.add_argument("--participant", default=None, help="Restrict to a single participant id.")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run, limit=args.limit, participant_id=args.participant))
