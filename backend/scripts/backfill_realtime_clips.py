"""Backfill: cut per-turn answer clips for realtime interviews already recorded.

Live-voice interviews store one session recording per browser connection
(`realtime_recording_segments`) and stamp every turn with its answer's span
inside that file. The incremental slicer cuts those spans into per-turn mp3
clips + Whisper sentence segments as the recording is uploaded, but
interviews recorded before it existed (or whose uploads pre-date the fix)
still show only the session players. This walks their stored segments and
runs the same slicer over each one, so the Responses view gains the classic
per-turn players and highlighting retroactively.

Idempotent: turns that already carry a clip are skipped, so a re-run only
touches what is still missing.

Usage (from backend/, with prod env vars loaded so it hits the real DB + R2):

    # Everything still missing clips, report only:
    python -m scripts.backfill_realtime_clips --dry-run

    # One participant, by id or by (case-insensitive) display name:
    python -m scripts.backfill_realtime_clips --participant <uuid>
    python -m scripts.backfill_realtime_clips --name Joe

Requires ffmpeg + ffprobe on PATH (present in the backend Docker image).
Run it as a Cloud Run job built from the backend image, or locally with
prod DATABASE_URL + R2_* + OPENAI_API_KEY (Whisper segments) exported.
"""

import argparse
import os
import sys

from sqlalchemy import func, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.interview import (  # noqa: E402
    InterviewTurn,
    Participant,
    RealtimeRecordingSegment,
)


def _ext_from_url(url: str) -> str:
    path = url.split("?", 1)[0]
    return os.path.splitext(path)[1] or ".mp3"


def find_participants(db, participant_id: str | None, name: str | None) -> list:
    """Realtime participants that still have turns without a clip."""
    stmt = (
        select(Participant)
        .join(RealtimeRecordingSegment, RealtimeRecordingSegment.participant_id == Participant.id)
        .distinct()
    )
    if participant_id:
        stmt = stmt.where(Participant.id == participant_id)
    if name:
        stmt = stmt.where(func.lower(Participant.display_name) == name.strip().lower())
    return list(db.execute(stmt).scalars().all())


def missing_turns(db, participant_id: str) -> list:
    return list(
        db.execute(
            select(InterviewTurn).where(
                InterviewTurn.participant_id == participant_id,
                InterviewTurn.audio_recording_url.is_(None),
                InterviewTurn.answer_offset_seconds.isnot(None),
                InterviewTurn.answer_end_seconds.isnot(None),
                InterviewTurn.response_transcript.isnot(None),
            )
        ).scalars().all()
    )


def run(db, *, participant_id: str | None = None, name: str | None = None, dry_run: bool = False) -> dict:
    """Slice every stored segment of the matching participants. Returns
    counts; the real work is delegated to the incremental slicer."""
    from app.services.realtime_slices import slice_turn_clips
    from app.services.storage import download_audio, storage_key_from_url

    participants = find_participants(db, participant_id, name)
    summary = {"participants": 0, "segments": 0, "missing": 0, "sliced": 0, "failed": 0}
    for participant in participants:
        missing = missing_turns(db, participant.id)
        if not missing:
            continue
        summary["participants"] += 1
        summary["missing"] += len(missing)
        segments = (
            db.query(RealtimeRecordingSegment)
            .filter(RealtimeRecordingSegment.participant_id == participant.id)
            .order_by(RealtimeRecordingSegment.created_at)
            .all()
        )
        wanted = {t.audio_segment_key for t in missing}
        print(
            f"{participant.id} ({participant.display_name or 'anonymous'}): "
            f"{len(missing)} turn(s) without a clip across {len(segments)} segment(s)"
        )
        for segment in segments:
            if segment.segment_key not in wanted:
                continue
            summary["segments"] += 1
            if dry_run:
                print(f"  would slice segment {segment.segment_key} from {segment.url}")
                continue
            key = storage_key_from_url(segment.url)
            if not key:
                print(f"  segment {segment.segment_key}: cannot map url to a storage key, skipped")
                summary["failed"] += 1
                continue
            try:
                data = download_audio(key)
            except Exception as exc:  # noqa: BLE001
                print(f"  segment {segment.segment_key}: download failed ({exc})")
                summary["failed"] += 1
                continue
            # The recording is complete: cut every remaining span, no
            # end-of-file margin.
            n = slice_turn_clips(
                participant.id, data, segment.segment_key, _ext_from_url(segment.url), completed=True
            )
            summary["sliced"] += n
            print(f"  segment {segment.segment_key}: {n} clip(s) cut")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--participant", help="participant id")
    parser.add_argument("--name", help="participant display name (case-insensitive)")
    parser.add_argument("--dry-run", action="store_true", help="report only, touch nothing")
    args = parser.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        summary = run(db, participant_id=args.participant, name=args.name, dry_run=args.dry_run)
    finally:
        db.close()
    print(
        f"{'DRY RUN: ' if args.dry_run else ''}{summary['participants']} participant(s), "
        f"{summary['missing']} turn(s) missing clips, {summary['segments']} segment(s) "
        f"{'to process' if args.dry_run else 'processed'}, {summary['sliced']} clip(s) cut, "
        f"{summary['failed']} failure(s)"
    )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
