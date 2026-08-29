import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

DEFAULT_SYSTEM_PROMPT = """\
You are a professional interviewer conducting a structured qualitative interview. \
Your goal is to explore the participant's experiences, opinions, and insights in depth. \
Follow the interview guide but adapt naturally to the conversation. Ask follow-up \
questions when answers are vague or when interesting themes emerge. Be warm, curious, \
and non-judgmental. Keep questions open-ended. Summarize key points before moving to \
a new section to show active listening. If the participant goes off-topic, gently \
steer them back. Never reveal the full interview guide or your scoring criteria.\
"""


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable in 0024 to allow safe backfill; one Study is auto-created per
    # existing Project. Will become non-nullable in a follow-up migration once
    # all reads have been verified — see roadmap risk #10.
    study_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("studies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Per-language localizations of `name` for participant-facing display only.
    # The canonical `name` stays the researcher's source of truth + identity;
    # this is filled on demand / in the background. Shape: {"fr": "<name>"}.
    name_translations: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    interview_duration_minutes: Mapped[int] = mapped_column(
        Integer, default=20, nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(
        Text, default=DEFAULT_SYSTEM_PROMPT, nullable=False
    )
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    researcher_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    researcher_logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    research_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-language localizations of `research_context` for participant-facing
    # display (shown on the consent screen). Canonical text stays the source of
    # truth. Shape: {"fr": "<text>"}.
    research_context_translations: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Study grounding — what business decision this study will inform
    decision_to_inform: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the researcher needs the answer ("2 weeks", "end of Q2", etc.)
    # Drives email cadence + plan recommendation.
    timeline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # How the researcher will know the study delivered ("trial-to-paid
    # lifts by 5 points", "leadership signs off on the redesign", etc.).
    # Anchors the AI analysis output back to a concrete criterion.
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who we're interviewing for this specific study (overrides company customer_type)
    target_customer_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How many completed interviews this round is aiming for. Advisory target
    # the researcher sets (or the Research Copilot recommends) — drives the
    # Setup sample-size guidance, not a hard gate. Nullable = not yet decided.
    target_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    privacy_policy_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Participant incentive, free text shown verbatim on the landing screen
    # ("€20 voucher, sent within 7 days of approval"). Non-empty switches
    # the study into review mode: completions land as review_status=pending
    # and the Responses tab shows the review + reward queues. Empty = unpaid
    # study, nothing changes.
    incentive_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Participant-facing identity policy for this study:
    #   "standard"  — show researcher_name / logo when set (default, legacy behaviour)
    #   "branded"   — additionally theme the interview page with the brand
    #                 colour + font below (custom_branding entitlement)
    #   "anonymous" — the public interview payload strips company name,
    #                 researcher name and logo entirely (blind study)
    branding_mode: Mapped[str] = mapped_column(
        String(20), default="standard", nullable=False, server_default="standard"
    )
    # Hex "#rrggbb" accent used for buttons/progress on the participant page.
    brand_primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Curated font-stack key (system / humanist / serif / elegant) — resolved
    # to a CSS stack client-side so no external fonts are ever loaded.
    brand_font: Mapped[str | None] = mapped_column(String(30), nullable=True)
    panel_collection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # PF-3: when True (default), the AI moderator opens the interview with a
    # warm-up turn before the first guide question — a low-stakes invitation
    # to get the participant talking. When False, the engine jumps straight
    # to the first guide question (legacy behaviour).
    warmup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="1")
    # Where the socio-demographic questionnaire sits in the participant flow.
    # False (default): after the interview, so nothing stands between the
    # participant and the first question. True: before it, for researchers
    # who need the profile to interpret or segment answers, or who screen on
    # it, and who accept the drop-off that front-loading costs.
    profile_before_interview: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    # Participant conversation transport for this study:
    #   "classic"       — record → Whisper → Claude → TTS turn loop (default)
    #   "realtime_beta" — live voice over the OpenAI Realtime API (WebRTC),
    #                     with Claude still making every interview decision
    #                     through the sideband bridge in
    #                     services/realtime_interview.py. Beta, per-study opt-in.
    interview_mode: Mapped[str] = mapped_column(
        String(20), default="classic", nullable=False, server_default="classic"
    )
    # True when this project was auto-seeded by the onboarding flow as a
    # showcase/example. Demo projects are excluded from the tier project
    # count so they never block a user from creating their real first
    # project, and the UI can render them with a "Demo" badge.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    company = relationship("Company", back_populates="projects")
    study = relationship("Study", back_populates="projects")
    guide_questions = relationship(
        "InterviewGuideQuestion", back_populates="project", cascade="all, delete-orphan"
    )
    interview_links = relationship(
        "InterviewLink", back_populates="project", cascade="all, delete-orphan"
    )
    participants = relationship(
        "Participant", back_populates="project", cascade="all, delete-orphan"
    )
    analyses = relationship(
        "ProjectAnalysis", back_populates="project", cascade="all, delete-orphan",
        order_by="ProjectAnalysis.version.desc()"
    )
    memos = relationship(
        "ProjectMemo", back_populates="project", cascade="all, delete-orphan"
    )
    manual_codes = relationship(
        "ManualCode", back_populates="project", cascade="all, delete-orphan"
    )
    screening_questions = relationship(
        "ScreeningQuestion", back_populates="project", cascade="all, delete-orphan",
        order_by="ScreeningQuestion.sort_order",
    )
    stimuli = relationship(
        "StimulusAsset", back_populates="project", cascade="all, delete-orphan",
        order_by="StimulusAsset.sort_order",
    )

    @property
    def name_translations_dict(self) -> dict:
        try:
            return json.loads(self.name_translations) if self.name_translations else {}
        except (ValueError, TypeError):
            return {}

    def localized_name(self, lang: str | None) -> str:
        """Participant-facing study name in `lang`, falling back to the
        canonical `name` when no translation exists."""
        code = (lang or "").lower()[:2]
        if not code:
            return self.name
        return self.name_translations_dict.get(code) or self.name

    @property
    def research_context_translations_dict(self) -> dict:
        try:
            return json.loads(self.research_context_translations) if self.research_context_translations else {}
        except (ValueError, TypeError):
            return {}

    def localized_research_context(self, lang: str | None) -> str | None:
        """Participant-facing research context in `lang`, falling back to the
        canonical text when no translation exists."""
        code = (lang or "").lower()[:2]
        if not code:
            return self.research_context
        return self.research_context_translations_dict.get(code) or self.research_context


class InterviewGuideQuestion(Base):
    __tablename__ = "interview_guide_questions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str] = mapped_column(String(255), nullable=False)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    main_question: Mapped[str] = mapped_column(Text, nullable=False)
    interview_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    desired_learning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    researcher_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Optional artefact the participant is shown while this question is on
    # screen (concept board, pack shot, written concept). SET NULL rather
    # than CASCADE: deleting an asset must never delete the question that
    # referenced it, it just unsticks the picture.
    stimulus_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stimulus_assets.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    project = relationship("Project", back_populates="guide_questions")
    stimulus = relationship("StimulusAsset", back_populates="questions")


class ScreeningQuestion(Base):
    __tablename__ = "screening_questions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disqualifying_options: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Per-language localizations of `question` + `options` (options aligned by
    # index to the canonical `options` list). The canonical fields stay the
    # source of truth + the stable identity for the disqualification gate;
    # this is display only. Shape: {"fr": {"question": str, "options": [str]}}.
    translations: Mapped[str | None] = mapped_column(Text, nullable=True)

    project = relationship("Project", back_populates="screening_questions")

    @property
    def options_list(self) -> list[str]:
        return json.loads(self.options)

    @property
    def disqualifying_options_list(self) -> list[str]:
        return json.loads(self.disqualifying_options)

    @property
    def translations_dict(self) -> dict:
        try:
            return json.loads(self.translations) if self.translations else {}
        except (ValueError, TypeError):
            return {}

    def localized(self, lang: str | None) -> tuple[str, list[dict]]:
        """Return (question, [{value, label}]) for the given language.

        `value` is always the canonical option (the gate's stable identity);
        `label` is the localized display text, falling back to the canonical
        option when no translation exists or the arrays don't line up.
        """
        canonical = self.options_list
        tr = self.translations_dict.get((lang or "").lower()[:2]) if lang else None
        q = (tr or {}).get("question") or self.question
        tr_opts = (tr or {}).get("options") or []
        opts = [
            {"value": opt, "label": tr_opts[i] if i < len(tr_opts) and tr_opts[i] else opt}
            for i, opt in enumerate(canonical)
        ]
        return q, opts


# What a stimulus can be. "image" covers packaging, ad creative, screenshots
# and mockups; "text" covers a written concept statement or positioning line.
# Video is deliberately out of scope for now: it needs its own player,
# transcoding and bandwidth story on the participant side.
STIMULUS_KINDS = {"image", "text"}


class StimulusAsset(Base):
    """Something the participant is shown before answering a guide question.

    Concept tests, packaging tests and ad-creative reactions all need an
    artefact on screen at a precise moment in the conversation. A stimulus is
    that artefact, owned by the study and attached to zero or more guide
    questions.

    Assets are addressed by URL rather than stored inline: images go through
    the same R2/local-disk path as branding logos (`services.storage.upload_image`),
    so nothing new is needed to serve them.
    """

    __tablename__ = "stimulus_assets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Researcher-facing label ("Pack A", "Concept 2: refill pouch"). Never
    # shown to the participant, so it can carry cell names without priming.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="image")
    # Set for kind="image": the stored public URL.
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Set for kind="text": the concept statement shown verbatim.
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional line rendered under the asset for the participant ("Take a
    # moment to look at this pack"). Participant-facing, so it is localized
    # the same way the rest of the interview chrome is: researcher's words.
    caption: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Researcher's note to the AI interviewer about what this asset is and
    # what to watch for. Never spoken aloud, never shown to the participant.
    # For images this rides alongside the picture itself, which the model
    # also sees, so it is a hint rather than a substitute for looking.
    ai_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    project = relationship("Project", back_populates="stimuli")
    questions = relationship("InterviewGuideQuestion", back_populates="stimulus")

    @property
    def is_image(self) -> bool:
        return self.kind == "image" and bool(self.url)

    def prompt_line(self) -> str:
        """One-line description for the interviewer prompt.

        Kept terse: this lands inside the guide block, which is cached, and
        the model gets the image itself in the message when there is one.
        """
        bits = [f"{self.name}"]
        if self.kind == "text" and self.body:
            body = self.body.strip().replace("\n", " ")
            bits.append(f'concept text shown to the participant: "{body}"')
        elif self.kind == "image":
            bits.append("an image the participant is looking at right now")
        if self.ai_description:
            bits.append(self.ai_description.strip())
        return "; ".join(bits)
