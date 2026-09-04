"""Interviewer benchmark: measure a prompt or guard change on a REAL transcript.

Three modes, from backend/ with the usual env (DATABASE_URL etc.):

    # 1. Export one interview (guide + every turn) to JSON. Run against prod
    #    as a Cloud Run job or with prod DATABASE_URL exported locally.
    python -m scripts.interviewer_bench export <participant_id> > joe.json

    # 2. Teacher-forced replay: for each participant answer, seed a scratch
    #    SQLite DB with the real history up to that point, freeze the clock at
    #    the moment the answer landed, and ask process_interview_turn (the full
    #    engine: prompt, pacing guards, caps) what it would say next. Needs
    #    ANTHROPIC_API_KEY; about thirty cents for a 25-turn interview. Run it
    #    once per code state you want to compare.
    python -m scripts.interviewer_bench replay joe.json baseline
    #    ...edit the prompt / guards...
    python -m scripts.interviewer_bench replay joe.json revised

    # 3. Blind pairwise judge (Opus, five-criterion qualitative-interviewing
    #    rubric: heard / depth / craft / neutrality / voice) plus deterministic
    #    counters (follow-up rate, verdict openers, length).
    python -m scripts.interviewer_bench judge baseline revised

Replay outputs land in bench_<name>.json next to the export. The judge's
per-step "why" lines are the useful part: read them, they name the exact
move a skilled interviewer would have made instead. Scores from a single
run move by about 0.2 points between judge runs, so treat anything smaller
as noise and look at the per-step verdicts.
"""

import datetime as dt
import json
import os
import random
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_FIELDS = (
    "name", "language", "interview_duration_minutes", "research_objective", "decision_to_inform",
    "target_customer_description", "research_context", "system_prompt", "warmup_enabled",
)

RUBRIC = """You are a senior qualitative research methodologist (depth interviewing, Kvale/Brinkmann, Spradley, JTBD switch interviews) auditing an AI voice interviewer.
You see the guide topic, its learning goal, the question that was asked, the participant's answer, and TWO candidate next lines (spoken aloud). Score EACH candidate 1-5 on:
1. heard: shows the participant they were listened to by referencing the specific content of THEIR answer (their words, their example), without judging it. 1 = ignores the answer / generic; 3 = labels it ("that point is useful"); 5 = picks up their exact words or detail.
2. depth: follows the thread when the answer holds an unexplored hook (a story, a claim, an emotion, a loaded term, a workaround); moves to a new topic only when the topic is saturated. 1 = abandons a rich answer for a new topic; 5 = exactly the probe a skilled interviewer would ask next (or a justified transition).
3. craft: one open, non-leading, single-concept question; episodic/behavioural framing ("last time", "walk me through", "what did you do") over opinion; ends with the question.
4. neutrality: no praise, no agreement, no evaluation, no summarising the answer back as a verdict.
5. voice: natural spoken length and rhythm (under ~30 words, no preamble stacking), sounds like a person, not a form.
Then say which candidate a skilled qualitative interviewer would rather have said (A, B, or tie) and why in one sentence.
Answer ONLY with JSON: {"A": {"heard":n,"depth":n,"craft":n,"neutrality":n,"voice":n}, "B": {...}, "prefer": "A"|"B"|"tie", "why": "..."}"""

CRITERIA = ("heard", "depth", "craft", "neutrality", "voice")


def export(participant_id: str) -> None:
    from app.database import SessionLocal
    from app.models.interview import Participant

    db = SessionLocal()
    p = db.query(Participant).filter(Participant.id == participant_id).first()
    if p is None:
        sys.exit(f"participant {participant_id} not found")
    pr = p.project
    out = {
        "project": {k: getattr(pr, k, None) for k in PROJECT_FIELDS},
        "guide": [
            {
                "section_index": q.section_index, "section_title": q.section_title,
                "question_index": q.question_index, "main_question": q.main_question,
                "interview_notes": q.interview_notes, "desired_learning": q.desired_learning,
                "researcher_notes": q.researcher_notes, "deprecated": bool(q.deprecated_at),
            }
            for q in sorted(pr.guide_questions, key=lambda q: (q.section_index, q.question_index))
        ],
        "participant": {
            "started_at": str(p.started_at), "completed_at": str(p.completed_at),
            "profession": p.profession, "age_range": p.age_range, "country": p.country,
            "preferred_language": getattr(p, "preferred_language", None),
        },
        "turns": [
            {
                "turn_index": t.turn_index, "question_index": t.question_index,
                "is_follow_up": bool(t.is_follow_up), "question_text": t.question_text,
                "response_transcript": t.response_transcript, "created_at": str(t.created_at),
            }
            for t in sorted(p.turns, key=lambda t: t.turn_index)
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    db.close()


def replay(export_path: str, variant: str, max_steps: int | None = None) -> None:
    here = os.path.dirname(os.path.abspath(export_path))
    os.environ["DATABASE_URL"] = f"sqlite:///{here}/bench_{variant}.db"
    os.environ.setdefault("INTERVIEW_DEFER_TTS", "true")
    os.environ.setdefault("OPENAI_API_KEY", "")
    os.environ.setdefault("SECRET_KEY", "bench")
    from app.database import Base, engine, SessionLocal
    import app.models  # noqa: F401
    from app.models.company import Company
    from app.models.project import Project, InterviewGuideQuestion
    from app.models.interview import InterviewLink, Participant, InterviewTurn
    from app.services import interview_engine as ie

    data = json.load(open(export_path))
    P, G, T = data["project"], data["guide"], data["turns"]
    parse = dt.datetime.fromisoformat
    lang = data["participant"].get("preferred_language") or None

    def seed(upto: int):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        c = Company(name="Bench", email="bench@example.com", password_hash="x", email_verified=True)
        db.add(c)
        db.flush()
        pr = Project(company_id=c.id, **{k: P.get(k) for k in PROJECT_FIELDS if k != "warmup_enabled"})
        if P.get("warmup_enabled") is not None:
            pr.warmup_enabled = P["warmup_enabled"]
        db.add(pr)
        db.flush()
        for i, q in enumerate(G):
            if q.get("deprecated"):
                continue
            db.add(InterviewGuideQuestion(
                project_id=pr.id, section_index=q["section_index"], section_title=q["section_title"],
                question_index=q["question_index"], main_question=q["main_question"],
                interview_notes=q["interview_notes"], desired_learning=q["desired_learning"],
                researcher_notes=q["researcher_notes"], sort_order=i,
            ))
        link = InterviewLink(project_id=pr.id, token=f"bench-{upto}", is_active=True)
        db.add(link)
        db.flush()
        p = Participant(
            link_id=link.id, project_id=pr.id, status="in_progress",
            started_at=parse(data["participant"]["started_at"]), preferred_language=lang,
            display_name="Participant", profession=data["participant"]["profession"],
            age_range=data["participant"]["age_range"], country=data["participant"]["country"],
        )
        db.add(p)
        db.flush()
        fu: dict = {}
        for t in T[: upto + 1]:
            idx = 0
            if t["is_follow_up"]:
                fu[t["question_index"]] = fu.get(t["question_index"], 0) + 1
                idx = fu[t["question_index"]]
            db.add(InterviewTurn(
                participant_id=p.id, turn_index=t["turn_index"], question_index=t["question_index"],
                is_follow_up=t["is_follow_up"], follow_up_index=idx, question_text=t["question_text"],
                response_transcript=t["response_transcript"] if t["turn_index"] < upto else None,
                created_at=parse(t["created_at"]),
            ))
        db.commit()
        return db, p.id

    results = []
    last = len(T) - 2 if max_steps is None else min(len(T) - 2, max_steps)
    for i in range(0, last):  # answer turn i, the engine produces turn i+1; stop before the final check
        answer = T[i]["response_transcript"]
        if not answer:
            continue
        now = parse(T[i + 1]["created_at"])

        class Frozen(dt.datetime):
            @classmethod
            def utcnow(cls):
                return now

        ie.datetime = Frozen
        db, pid = seed(i)
        try:
            r = ie.process_interview_turn(pid, audio_path=None, audio_url=None, db=db, transcript_override=answer, spoken_live=True)
            produced, is_fu, qi = r["question_text"], r["is_follow_up"], r["question_index"]
        except Exception as e:  # noqa: BLE001
            produced, is_fu, qi = f"ERROR {e}", None, None
        db.close()
        qidx = T[i]["question_index"]
        topic = G[qidx]["main_question"] if 0 <= qidx < len(G) else "(warm-up/closing)"
        learning = (G[qidx]["desired_learning"] or "") if 0 <= qidx < len(G) else ""
        results.append({
            "step": i, "question": T[i]["question_text"], "answer": answer,
            "actual_next": T[i + 1]["question_text"], "actual_is_follow_up": T[i + 1]["is_follow_up"],
            "produced": produced, "is_follow_up": is_fu, "question_index": qi, "topic": topic, "learning": learning,
        })
        print(f"[{i}] fu={is_fu} q{qi}: {produced}", flush=True)
    out = os.path.join(here, f"bench_{variant}.json")
    json.dump(results, open(out, "w"), ensure_ascii=False, indent=1)
    print("saved", len(results), "->", out)


def _counters(rows: dict) -> str:
    meta = sum(
        1 for r in rows.values()
        if re.match(r"^(That|This|The) .{3,60}(useful|clear|stands? out|makes sense|helpful|interesting|telling|striking)", r["produced"])
    )
    fu = sum(1 for r in rows.values() if r["is_follow_up"])
    words = statistics.mean(len(r["produced"].split()) for r in rows.values())
    return f"follow-up rate {fu}/{len(rows)}, verdict openers {meta}/{len(rows)}, avg {words:.0f} words"


def judge(a_name: str, b_name: str, here: str = ".") -> None:
    import anthropic

    client = anthropic.Anthropic()
    A = {r["step"]: r for r in json.load(open(os.path.join(here, f"bench_{a_name}.json")))}
    B = {r["step"]: r for r in json.load(open(os.path.join(here, f"bench_{b_name}.json")))}
    scores = {a_name: [], b_name: []}
    prefs = {a_name: 0, b_name: 0, "tie": 0}
    whys = []
    for step in sorted(set(A) & set(B)):
        ra, rb = A[step], B[step]
        if ra["produced"].startswith("ERROR") or rb["produced"].startswith("ERROR"):
            continue
        order = [(a_name, ra["produced"]), (b_name, rb["produced"])]
        random.shuffle(order)
        prompt = (
            f"GUIDE TOPIC: {ra['topic']}\nLEARNING GOAL: {ra['learning']}\n\n"
            f"QUESTION ASKED: {ra['question']}\nPARTICIPANT ANSWER: {ra['answer']}\n\n"
            f"CANDIDATE A: {order[0][1]}\nCANDIDATE B: {order[1][1]}"
        )
        msg = client.messages.create(
            model="claude-opus-4-8", max_tokens=600, system=RUBRIC,
            messages=[{"role": "user", "content": prompt}],
        )
        m = re.search(r"\{.*\}", msg.content[0].text, re.S)
        j = json.loads(m.group(0))
        for label, (name, _) in zip("AB", order):
            scores[name].append(j[label])
        if j["prefer"] in ("A", "B"):
            prefs[order["AB".index(j["prefer"])][0]] += 1
        else:
            prefs["tie"] += 1
        winner = order["AB".index(j["prefer"])][0] if j["prefer"] in ("A", "B") else "tie"
        whys.append((step, winner, j["why"]))
    print(f"\n=== {a_name}: {_counters(A)}\n=== {b_name}: {_counters(B)}\n")
    print(f"{'criterion':<12}{a_name:>12}{b_name:>12}")
    for c in CRITERIA:
        print(f"{c:<12}{statistics.mean(s[c] for s in scores[a_name]):>12.2f}{statistics.mean(s[c] for s in scores[b_name]):>12.2f}")
    print(f"{'TOTAL':<12}{statistics.mean(sum(s.values()) for s in scores[a_name]):>12.2f}{statistics.mean(sum(s.values()) for s in scores[b_name]):>12.2f}")
    print("preferred:", prefs)
    for step, winner, why in whys:
        print(f"  [{step}] -> {winner}: {why}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "export" and len(sys.argv) == 3:
        export(sys.argv[2])
    elif mode == "replay" and len(sys.argv) in (4, 5):
        replay(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) == 5 else None)
    elif mode == "judge" and len(sys.argv) == 4:
        judge(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
