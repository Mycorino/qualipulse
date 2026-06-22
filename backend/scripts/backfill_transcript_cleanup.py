"""One-off backfill: run the ASR sense-check on existing transcripts.

The cleanup pass normally fires when an interview completes. Participants that
finished *before* this feature shipped have no `cleaned_response`, so this
script walks them and runs the same pass. Idempotent: turns already stamped
with `cleaned_at` (or hand-edited) are skipped, so re-running only does the
remaining work.

Usage (from backend/, with prod env so it hits the real DB + Anthropic):

    python -m scripts.backfill_transcript_cleanup --dry-run            # report only
    python -m scripts.backfill_transcript_cleanup                       # run all
    python -m scripts.backfill_transcript_cleanup --participant <id>    # one participant
    python -m scripts.backfill_transcript_cleanup --limit 25           # cap participants

Requires ANTHROPIC_API_KEY. Run as a Cloud Run job from the backend image, or
locally with prod DATABASE_URL + ANTHROPIC_API_KEY exported.
"""

import argparse
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.interview import InterviewTurn, Participant  # noqa: E402
from app.services.transcript_cleanup import cleanup_participant  # noqa: E402


def run(dry_run: bool, limit: int | None, participant_id: str | None) -> int:
    db = SessionLocal()
    done = 0
    try:
        if participant_id:
            pids = [participant_id]
        else:
            # Participants with at least one un-cleaned, non-edited transcript turn.
            stmt = (
                select(InterviewTurn.participant_id)
                .where(
                    InterviewTurn.response_transcript.isnot(None),
                    InterviewTurn.cleaned_at.is_(None),
                    InterviewTurn.manually_edited.is_(False),
                )
                .distinct()
            )
            pids = [r[0] for r in db.execute(stmt).all()]

        print(f"{len(pids)} participant(s) with transcripts to sense-check"
              f"{' (dry-run)' if dry_run else ''}.")
        for pid in pids:
            if limit is not None and done >= limit:
                print(f"Reached --limit {limit}; stopping.")
                break
            if dry_run:
                n = (
                    db.query(InterviewTurn)
                    .filter(
                        InterviewTurn.participant_id == pid,
                        InterviewTurn.response_transcript.isnot(None),
                        InterviewTurn.cleaned_at.is_(None),
                        InterviewTurn.manually_edited.is_(False),
                    )
                    .count()
                )
                print(f"  [dry-run] participant {pid}: would sense-check {n} turn(s)")
            else:
                cleanup_participant(pid, db)
                print(f"  ✓ participant {pid}")
            done += 1
        print(f"\nDone. participants processed={done}"
              f"{' (dry-run, nothing written)' if dry_run else ''}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backfill ASR sense-check on existing transcripts.")
    ap.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")
    ap.add_argument("--limit", type=int, default=None, help="Max participants to process this run.")
    ap.add_argument("--participant", default=None, help="Restrict to a single participant id.")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run, limit=args.limit, participant_id=args.participant))
