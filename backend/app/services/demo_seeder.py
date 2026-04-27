"""Seed a showcase demo project for new users.

This seeds a single research project that demonstrates QualiPulse features
so a new user can explore the platform with realistic data before running
their own study. Seeding is mono-language: an English company gets the
streaming-services topic with four EN participants, a French company gets
the online-grocery topic with four FR participants.

- One interview link so the link manager has content
- A screening question with a disqualifying option
- Four completed participants in the company's language, with adaptive
  follow-ups, varied demographics, and a realistic quality spread
  (1 low / 1 good / 2 strong)
- A manual codebook with three codes and tagged quotes
- A finished AI analysis (v1 = ai_discovery) with verbatim quotes, plus a
  refined v2 (researcher_refined) showing the iterative analysis flow
- Two theme annotations (confirmed / needs_evidence) on v2
- Three project memos (general + theme-linked + tension-linked)

The fixture content lives in `_demo_data_fr.py` and `_demo_data_en.py` so the
seeder logic stays readable. The seeder is idempotent at the call site via
`Company.demo_seeded_at` and via a name match in the on-demand router endpoint.

Topics — chosen because they're universally familiar and use real, well-known
consumer brands:
- EN: How people choose between video streaming services (Netflix, Disney+,
  Prime Video, HBO Max, Apple TV+, etc.).
- FR: Habitudes de courses alimentaires en ligne (Carrefour Drive, Picard,
  La Belle Vie, Leclerc Drive, Coop@home, Amazon Fresh, etc.).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.coding import ManualCode, QuoteTag
from app.models.company import Company
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.memo import ProjectMemo
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.services._demo_data_en import NOTABLE_QUOTES_EN, PARTICIPANTS_EN, QUALITY_EN
from app.services._demo_data_fr import NOTABLE_QUOTES_FR, PARTICIPANTS_FR, QUALITY_FR


DEMO_PROJECT_NAME = "[Demo] How people choose streaming services"
DEMO_PROJECT_NAME_FR = "[Démo] Courses alimentaires en ligne — habitudes & freins"

DEMO_RESEARCH_OBJECTIVE = (
    "Understand how consumers decide which video streaming services to "
    "subscribe to, stay with, or cancel — and identify the moments in the "
    "subscription lifecycle that build loyalty or trigger churn."
)
DEMO_RESEARCH_OBJECTIVE_FR = (
    "Comprendre comment les consommateurs choisissent leurs services de "
    "courses alimentaires en ligne, ce qui les fait revenir vers la même "
    "enseigne, et les frictions qui pourraient les pousser à abandonner."
)

DEMO_RESEARCH_CONTEXT = (
    "This is a demo project that QualiPulse seeded automatically so you can "
    "explore the platform with realistic data. It contains four completed "
    "interviews about how people choose between video streaming services, "
    "a finished AI analysis with two versions, a researcher codebook, "
    "tagged quotes, and project memos. Feel free to edit anything, archive "
    "it, or delete it whenever you're ready to run your own study — it never "
    "counts against your project quota."
)
DEMO_RESEARCH_CONTEXT_FR = (
    "Ceci est un projet de démo que QualiPulse a créé automatiquement pour "
    "que vous puissiez explorer la plateforme avec des données réalistes. "
    "Il contient quatre entretiens sur les habitudes de courses alimentaires "
    "en ligne, une analyse IA avec deux versions, un codebook chercheur, "
    "des verbatims taggués et des mémos. Modifiez, archivez ou supprimez "
    "quand vous voulez — ce projet ne compte pas dans votre quota."
)

DEMO_WELCOME_MESSAGE = (
    "Hi, thanks for taking the time to chat with us! This is a short, "
    "informal conversation about how you choose, use, and sometimes cancel "
    "video streaming services. There are no right or wrong answers — we're "
    "just curious how you actually think about it."
)
DEMO_WELCOME_MESSAGE_FR = (
    "Bonjour, merci de prendre le temps de discuter avec nous ! C'est une "
    "conversation courte et informelle sur la façon dont vous faites vos "
    "courses alimentaires en ligne, ce qui vous plaît, ce qui vous agace. "
    "Il n'y a pas de bonnes ou mauvaises réponses."
)

DEMO_GUIDE: list[dict] = [
    {
        "section": "Discovery",
        "questions": [
            {
                "q": "How do you decide which streaming services to subscribe to right now?",
                "learning": "Decision criteria, trade-offs, household-vs-solo dynamics, role of price vs content.",
            },
        ],
    },
    {
        "section": "Experience",
        "questions": [
            {
                "q": "Walk me through your experience signing up for a new service and what those first few weeks felt like.",
                "learning": "Sign-up friction, content discovery, time-to-value, cancellation flow perception.",
            },
        ],
    },
    {
        "section": "Loyalty",
        "questions": [
            {
                "q": "What makes you stay loyal to a service, versus jumping between them?",
                "learning": "Retention drivers, churn triggers, exclusive-content lock-in, price-increase tolerance.",
            },
        ],
    },
]

DEMO_GUIDE_FR: list[dict] = [
    {
        "section": "Découverte",
        "questions": [
            {
                "q": "Comment avez-vous commencé à faire vos courses alimentaires en ligne, et qu'est-ce qui vous a poussé à essayer ?",
                "learning": "Déclencheur initial, canal d'entrée, rôle des contraintes de vie (enfants, télétravail).",
            },
        ],
    },
    {
        "section": "Expérience",
        "questions": [
            {
                "q": "Racontez-moi votre dernière expérience de courses en ligne, du moment où vous remplissez le panier jusqu'à ce que vous récupériez les produits. Qu'est-ce qui s'est bien passé, qu'est-ce qui était galère ?",
                "learning": "Frictions de panier, ruptures de stock, qualité produits, livraison vs Drive, service après-vente.",
            },
        ],
    },
    {
        "section": "Confiance et retour",
        "questions": [
            {
                "q": "Qu'est-ce qui vous fait revenir vers le même service plutôt que d'en tester un autre ? Et qu'est-ce qui pourrait vous faire abandonner ?",
                "learning": "Moteurs de fidélité, coût de switch, sensibilité prix, seuils de tolérance qualité.",
            },
        ],
    },
]


def _flat_main_questions(guide: list[dict] | None = None) -> list[str]:
    flat: list[str] = []
    for section in (guide or DEMO_GUIDE):
        for item in section["questions"]:
            flat.append(item["q"])
    return flat


DEMO_SCREENING_QUESTION = {
    "question": "Have you subscribed to at least one paid video streaming service in the last 12 months?",
    "options": ["Yes, more than one", "Yes, just one", "No"],
    "disqualifying_options": ["No"],
}

DEMO_SCREENING_QUESTION_FR = {
    "question": "Avez-vous fait au moins une commande de courses alimentaires en ligne au cours des 12 derniers mois ?",
    "options": ["Oui, régulièrement", "Oui, une ou deux fois", "Non"],
    "disqualifying_options": ["Non"],
}


DEMO_CODES = [
    {"name": "Trust signal", "color": "#16a34a"},
    {"name": "Friction", "color": "#dc2626"},
    {"name": "Price concern", "color": "#f59e0b"},
]


# Per-language tag plans: list of (notable_quote_index, code_name).
DEMO_TAG_PLAN_EN: list[tuple[int, str]] = [
    (0, "Trust signal"),    # Priya — "let me have a pause button" (retention idea)
    (1, "Friction"),        # Priya — dark patterns on cancellation
    (2, "Trust signal"),    # Marcus — exclusive content as loyalty driver
    (3, "Trust signal"),    # Alex — service with a point of view (curation)
]

DEMO_TAG_PLAN_FR: list[tuple[int, str]] = [
    (0, "Friction"),        # Camille — coût caché du switch
    (1, "Friction"),        # Camille — ruptures, "ils ont jamais tout"
    (2, "Price concern"),   # Romain — Leclerc moins cher du marché
    (3, "Trust signal"),    # Sophie — fiabilité de Coop
]


# ── AI analysis report ──────────────────────────────────────────────────────

def _build_quote(text: str, participant_name: str, q_idx: int) -> dict:
    return {
        "text": text,
        "participant_display_name": participant_name,
        "turn_index": q_idx,
    }


def _v1_report(lang: str) -> dict:
    if lang == "fr":
        notable = NOTABLE_QUOTES_FR
        participants = PARTICIPANTS_FR

        def q(i: int) -> dict:
            n = notable[i]
            return _build_quote(n["text"], participants[n["participant_index"]]["display_name"], n["turn_index"])

        return {
            "summary": (
                "Sur quatre entretiens menés en France, en Belgique et en Suisse, "
                "un schéma clair se dessine : la fidélité aux services de courses "
                "alimentaires en ligne tient moins au prix qu'à un coût de switch "
                "invisible (historique, listes, panier type) et à la fiabilité "
                "perçue. La friction la plus citée est la rupture de stock, qui "
                "érode la confiance plus que les frais de service. Les utilisatrices "
                "les plus engagées formulent des demandes de fonctionnalités très "
                "concrètes (validation de substitutions, notifications proactives) "
                "qui restent largement non couvertes par les enseignes."
            ),
            "themes": [
                {
                    "title": "Le coût de switch invisible verrouille la fidélité",
                    "summary": (
                        "Trois participantes sur quatre décrivent leur fidélité à "
                        "un service comme un effet d'inertie lié à l'historique "
                        "stocké : panier type, listes, marques préférées. Changer "
                        "d'enseigne, ce serait reconstruire des semaines de "
                        "configuration. Ce coût n'est pas tarifé, ne sort pas dans "
                        "les enquêtes prix, mais il pèse plus que les écarts de "
                        "tarif sur la décision."
                    ),
                    "quotes": [q(0), q(3)],
                    "frequency": "3 utilisatrices sur 4",
                },
                {
                    "title": "Les ruptures de stock érodent la confiance plus que les frais",
                    "summary": (
                        "La frustration la plus citée n'est pas le prix de la "
                        "livraison ou du service mais le sentiment que les Drives "
                        "sont sous-stockés : 'ils ont jamais tout'. Les "
                        "utilisatrices encaissent un détour en magasin et "
                        "commencent à comparer les enseignes. Une fonctionnalité "
                        "de validation des substitutions à l'avance résoudrait "
                        "presque entièrement le problème mais aucune enseigne "
                        "ne la propose."
                    ),
                    "quotes": [q(1)],
                    "frequency": "2 utilisatrices sur 4",
                },
                {
                    "title": "La sensibilité prix dépend du profil, pas du service",
                    "summary": (
                        "Romain (famille de cinq) compare au centime près et "
                        "reste chez Leclerc parce que c'est le moins cher. "
                        "Sophie (Genève, profession libérale) ne regarde pas "
                        "le prix et paie volontiers la fiabilité. Camille "
                        "(active urbaine) déclare ne pas avoir comparé. Les "
                        "enseignes qui se positionnent uniquement sur le prix "
                        "captent un segment, pas le marché."
                    ),
                    "quotes": [q(2)],
                    "frequency": "2 utilisatrices sur 4",
                },
            ],
            "jobs_to_be_done": [
                {
                    "job": "Quand je commande mes courses chaque semaine, je veux gagner du temps sans sacrifier la qualité, pour rendre du temps aux activités qui comptent vraiment.",
                    "insight": "Le gain de temps est la motivation racine, jamais le prix. Les services qui font perdre du temps (ruptures, retards) sont punis plus fort que ceux qui sont chers.",
                    "frequency": "4 utilisatrices sur 4",
                },
                {
                    "job": "Quand je change quelque chose dans ma vie (enfants, déménagement), je veux que mon service de courses s'adapte sans que je doive tout reconfigurer.",
                    "insight": "Le moment du changement de vie est aussi le moment où les utilisatrices changent de service. C'est là que la concurrence peut gagner ou perdre.",
                    "frequency": "2 utilisatrices sur 4",
                },
            ],
            "tensions": [
                {
                    "tension": "Fiabilité vs flexibilité",
                    "detail": (
                        "Les utilisatrices veulent des créneaux fiables (Sophie) "
                        "ET la possibilité de passer quand elles veulent "
                        "(Camille avec le Drive). Aucune enseigne ne combine "
                        "vraiment les deux — le Drive est flexible mais "
                        "incertain sur le stock, la livraison est fiable mais "
                        "rigide sur l'horaire."
                    ),
                },
                {
                    "tension": "Confiance dans la sélection vs gain de temps",
                    "detail": (
                        "Plusieurs participantes déclarent ne pas vouloir "
                        "qu'un livreur choisisse leurs fruits et légumes, ce "
                        "qui les pousse vers le Drive. Mais le Drive n'élimine "
                        "pas le problème : c'est le préparateur qui choisit. "
                        "La promesse de gain de temps de la livraison est "
                        "limitée par cette friction de confiance."
                    ),
                },
            ],
            "recommendations": [
                "Proposer un système de validation des substitutions à l'avance — la fonctionnalité la plus demandée et la plus simple à livrer.",
                "Notifier proactivement les ruptures sur les produits récurrents avec trois alternatives suggérées, plutôt que de les découvrir à la livraison.",
                "Investir dans la fiabilité du créneau (modèle Coop@home) plutôt que dans la communication promotionnelle — c'est ce qui crée la fidélité long terme.",
                "Permettre l'export ou la portabilité de l'historique d'achats pour réduire la peur du switch et capter les clients d'enseignes concurrentes.",
                "Ne pas se positionner uniquement sur le prix : les segments aisés paient pour la fiabilité, pas pour la promo.",
            ],
            "confidence": "high",
            "participant_count": 4,
        }

    # English (streaming) report
    notable = NOTABLE_QUOTES_EN
    participants = PARTICIPANTS_EN

    def q(i: int) -> dict:
        n = notable[i]
        return _build_quote(n["text"], participants[n["participant_index"]]["display_name"], n["turn_index"])

    return {
        "summary": (
            "Across four interviews in the UK, US, Canada, and Australia, a "
            "consistent pattern emerges: streaming subscribers behave less "
            "like loyal customers and more like rotating renters. Loyalty is "
            "driven by exclusive content and recommendation quality, not by "
            "brand affinity. The biggest unmet need is a 'pause' state "
            "between active and cancelled — every participant either named "
            "or implied it. Cancellation friction is widely noticed and "
            "actively damages re-acquisition. Price increases are the single "
            "most common trigger for churn re-evaluation."
        ),
        "themes": [
            {
                "title": "Subscribers want a pause state, not a binary on/off",
                "summary": (
                    "Three of four participants described cycling in and out "
                    "of services around specific shows. The current "
                    "subscribe/cancel binary makes leaving feel like a "
                    "bigger decision than it is, which paradoxically "
                    "increases churn because users cancel decisively rather "
                    "than going dormant. A pause feature was named "
                    "explicitly by one participant and implied by two more."
                ),
                "quotes": [q(0)],
                "frequency": "3 of 4 participants",
            },
            {
                "title": "Cancellation friction is a re-acquisition tax",
                "summary": (
                    "Participants notice and remember cancellation dark "
                    "patterns. The friction doesn't prevent the cancellation "
                    "— it just makes them less likely to come back later. "
                    "This is a particularly costly trade-off given the "
                    "cyclical subscribe-cancel-resubscribe behaviour the "
                    "data reveals."
                ),
                "quotes": [q(1)],
                "frequency": "2 of 4 participants",
            },
            {
                "title": "Loyalty lives at the catalogue, not at the brand",
                "summary": (
                    "Subscribers stay for either exclusive content (NFL "
                    "Sunday Ticket, Marvel/Star Wars, HBO catalogue) or for "
                    "a service that has a clear editorial point of view "
                    "(Netflix's deep recommendation history, Criterion's "
                    "curation). Generic catalogues blur together and lose "
                    "the moment the headliner show ends."
                ),
                "quotes": [q(2), q(3)],
                "frequency": "3 of 4 participants",
            },
        ],
        "jobs_to_be_done": [
            {
                "job": "When I want to watch a specific show, I want to subscribe quickly, watch, and leave without feeling guilty, so I can match my spending to my actual viewing.",
                "insight": "Show-driven subscribers are the modal pattern, not the exception. Services that fight this behaviour with retention friction lose them as future returnees.",
                "frequency": "3 of 4 participants",
            },
            {
                "job": "When a service raises my price, I want a moment to evaluate whether it's still worth it, so I don't keep paying out of inertia for something I don't use.",
                "insight": "Price-increase emails are the single most common cancellation trigger — even when the service is still worth what users are paying. Timing the increase right after a flagship release lands could meaningfully reduce churn.",
                "frequency": "3 of 4 participants",
            },
        ],
        "tensions": [
            {
                "tension": "Algorithm vs editorial taste",
                "detail": (
                    "Participants who use Netflix daily love its algorithm "
                    "because it has years of behavioural data on them. "
                    "Participants who try smaller services want curation "
                    "and a point of view. The newer services are trying to "
                    "be Netflix without the data advantage, and pleasing "
                    "neither audience."
                ),
            },
            {
                "tension": "Bundling convenience vs subscription overload",
                "detail": (
                    "Bundles (Disney+/Hulu/ESPN, YouTube TV) reduce "
                    "decision fatigue and create lock-in. But participants "
                    "are also acutely aware of how stacked subscriptions "
                    "have made streaming more expensive than the cable "
                    "they replaced. Bundling solves the operator's "
                    "retention problem and creates the user's budget "
                    "problem."
                ),
            },
        ],
        "recommendations": [
            "Ship a real pause feature (2-3 months, watchlist preserved) — the most-requested unmet need, and a strong retention play.",
            "Audit and simplify the cancellation flow. The friction does not prevent churn; it prevents win-back.",
            "Time price increases to coincide with flagship releases, not dead months — the price-increase email is the single biggest cancellation trigger.",
            "Invest in editorial curation as a differentiator, not just algorithmic recommendations. A 'point of view' is what makes a service feel like more than a warehouse.",
            "Communicate proactively about what's coming (monthly newsletter style) rather than relying on the algorithm to surface new content. Subscribers want to be told what to watch.",
        ],
        "confidence": "high",
        "participant_count": 4,
    }


def _v2_report(lang: str) -> dict:
    base = _v1_report(lang)
    if lang == "fr":
        base["summary"] = (
            "Analyse affinée après revue chercheur. Le coût de switch invisible "
            "est confirmé comme le moteur principal de fidélité — c'est l'angle "
            "qui mérite le plus d'investissement produit. La friction des "
            "ruptures de stock est très actionnable et devrait être la priorité "
            "court terme : trois utilisatrices sur quatre l'ont mentionnée et "
            "une fonctionnalité simple (validation des substitutions) résoudrait "
            "le problème. Le thème de la sensibilité prix mérite plus de données "
            "— il est segmenté de façon nette par profil et il faudrait des "
            "entretiens supplémentaires sur des segments à plus faible revenu "
            "avant d'en faire une recommandation prioritaire."
        )
    else:
        base["summary"] = (
            "Refined after researcher review. The pause-state finding is the "
            "strongest retention insight in the dataset and is named or "
            "implied by three of four participants — ship it. The "
            "cancellation-friction theme is confirmed and immediately "
            "actionable. The catalogue-vs-curation theme is high-confidence "
            "for the smaller services but needs more evidence before we "
            "recommend Netflix-scale changes; their algorithm advantage may "
            "still outweigh the curation pull for their core users."
        )
    base["confidence"] = "high"
    return base


DEMO_ANNOTATIONS_EN = [
    {
        "theme_title": "Subscribers want a pause state, not a binary on/off",
        "status": "confirmed",
        "researcher_note": (
            "Confirmed across three of four interviews. Priya named it "
            "explicitly, Marcus implied it (subscribing-then-cancelling "
            "around specific shows), Alex described the same cycle. This "
            "is the strongest retention idea in the dataset — worth "
            "prototyping with the product team before the next planning "
            "round."
        ),
    },
    {
        "theme_title": "Loyalty lives at the catalogue, not at the brand",
        "status": "needs_evidence",
        "researcher_note": (
            "True for the smaller services but Netflix is doing fine with "
            "an algorithm-only approach for its core users. Need 3-4 more "
            "interviews specifically with heavy Netflix users to know "
            "whether curation matters at scale or only for the long tail. "
            "Don't over-rotate on the Criterion comparison."
        ),
    },
]

DEMO_ANNOTATIONS_FR = [
    {
        "theme_title": "Le coût de switch invisible verrouille la fidélité",
        "status": "confirmed",
        "researcher_note": (
            "Confirmé sur trois entretiens sur quatre. Camille et Sophie "
            "le formulent presque mot pour mot, Romain l'implique. C'est "
            "la mécanique de rétention la plus puissante du dataset et "
            "celle qu'on a le moins activée côté produit. À tester avec "
            "l'équipe produit avant la prochaine roadmap."
        ),
    },
    {
        "theme_title": "La sensibilité prix dépend du profil, pas du service",
        "status": "needs_evidence",
        "researcher_note": (
            "Schéma de segmentation clair mais basé sur seulement quatre "
            "personnes. Il faudrait 3-4 entretiens supplémentaires sur "
            "des segments à plus faible revenu avant d'en faire une "
            "recommandation forte. Le profil étudiant (Léa) n'utilise "
            "pas le service donc ne nous renseigne pas vraiment sur ce "
            "segment."
        ),
    },
]


DEMO_MEMOS_EN = [
    {
        "type": "general",
        "linked_key": None,
        "content": (
            "First pass through the streaming-services data. The pause-state "
            "finding is the strongest signal — three of four participants "
            "either explicitly asked for it (Priya) or described the "
            "behaviour it would solve (Marcus, Alex). Worth flagging to "
            "product before the next quarterly planning round."
        ),
    },
    {
        "type": "theme_note",
        "linked_key": "Cancellation friction is a re-acquisition tax",
        "content": (
            "Priya's quote about Hulu specifically — 'I'm more reluctant to "
            "resubscribe to specifically because I remember how annoying "
            "leaving was' — is the most quotable line on this theme. The "
            "behavioural insight is that the friction tax falls on "
            "re-acquisition, not on retention. Worth modelling lifetime "
            "value with and without simplified cancellation."
        ),
    },
    {
        "type": "tension_note",
        "linked_key": "Bundling convenience vs subscription overload",
        "content": (
            "Marcus's framing of the family bill — 'this is more than my "
            "parents paid for cable in the nineties' — is the line to "
            "watch. The streaming-vs-cable narrative is starting to "
            "invert in subscriber memory, which is a real long-term "
            "brand risk for the category. Worth tracking quantitatively "
            "in the next survey wave."
        ),
    },
]

DEMO_MEMOS_FR = [
    {
        "type": "general",
        "linked_key": None,
        "content": (
            "Premier passage sur les données courses en ligne. Le coût de "
            "switch invisible est le signal le plus net : trois "
            "utilisatrices sur quatre le décrivent presque dans les mêmes "
            "termes, et c'est probablement le levier de rétention le moins "
            "exploité par les enseignes. À sortir lors du prochain comité "
            "produit."
        ),
    },
    {
        "type": "theme_note",
        "linked_key": "Les ruptures de stock érodent la confiance plus que les frais",
        "content": (
            "Le verbatim de Camille 'ils ont jamais tout' résume le "
            "sentiment partagé. La fonctionnalité de validation des "
            "substitutions à l'avance résoudrait quasi entièrement le "
            "problème et n'existe nulle part — c'est une opportunité "
            "produit nette. À chiffrer côté supply chain pour comprendre "
            "pourquoi les Drives sont structurellement sous-stockés."
        ),
    },
    {
        "type": "tension_note",
        "linked_key": "Confiance dans la sélection vs gain de temps",
        "content": (
            "Tension intéressante : les utilisatrices veulent gagner du "
            "temps mais refusent de déléguer le choix des produits frais. "
            "Le Drive contourne le problème en théorie mais le reproduit "
            "côté préparateur. Une piste serait de filmer ou photographier "
            "les fruits et légumes au moment de la préparation — à tester "
            "en pilote sur un magasin avant de généraliser."
        ),
    },
]


# ── Seeder ──────────────────────────────────────────────────────────────────


def seed_demo_project(db: Session, company_id: str) -> Project:
    """Create and persist the full showcase demo project for `company_id`.

    Returns the created Project. The seeder is fully self-contained — it does
    not commit until everything is built, so a partial failure rolls back
    cleanly. The caller is responsible for setting `Company.demo_seeded_at`
    after success if it wants idempotency.

    Seeding is mono-language: the company's ``preferred_language`` (default
    "en") drives the entire project — scaffolding, guide, screening,
    participants, codes, analysis, annotations, and memos are all in that
    language. EN companies get a streaming-services topic; FR companies get
    an online-grocery topic.
    """
    now = datetime.now(timezone.utc)

    company = db.query(Company).filter(Company.id == company_id).first()
    lang = (getattr(company, "preferred_language", None) or "en").strip().lower()[:2]
    if lang not in ("en", "fr"):
        lang = "en"

    if lang == "fr":
        demo_name = DEMO_PROJECT_NAME_FR
        demo_welcome = DEMO_WELCOME_MESSAGE_FR
        demo_objective = DEMO_RESEARCH_OBJECTIVE_FR
        demo_context = DEMO_RESEARCH_CONTEXT_FR
        demo_guide = DEMO_GUIDE_FR
        demo_screening = DEMO_SCREENING_QUESTION_FR
        participants_data = PARTICIPANTS_FR
        notable_quotes = NOTABLE_QUOTES_FR
        quality_map = QUALITY_FR
        tag_plan = DEMO_TAG_PLAN_FR
        annotations = DEMO_ANNOTATIONS_FR
        memos = DEMO_MEMOS_FR
        quality_keys = ["camille", "romain", "lea", "sophie"]
        researcher_context = (
            "Revue de la v1 avec l'équipe. Coût de switch = l'asset à "
            "défendre. La friction des ruptures de stock est le fix immédiat. "
            "La sensibilité prix demande plus de données avant d'investir."
        )
    else:
        demo_name = DEMO_PROJECT_NAME
        demo_welcome = DEMO_WELCOME_MESSAGE
        demo_objective = DEMO_RESEARCH_OBJECTIVE
        demo_context = DEMO_RESEARCH_CONTEXT
        demo_guide = DEMO_GUIDE
        demo_screening = DEMO_SCREENING_QUESTION
        participants_data = PARTICIPANTS_EN
        notable_quotes = NOTABLE_QUOTES_EN
        quality_map = QUALITY_EN
        tag_plan = DEMO_TAG_PLAN_EN
        annotations = DEMO_ANNOTATIONS_EN
        memos = DEMO_MEMOS_EN
        quality_keys = ["priya", "marcus", "jen", "alex"]
        researcher_context = (
            "Reviewed v1 with the team. Pause-state is the headline retention "
            "insight — protect it. Cancellation friction is the immediate fix. "
            "Catalogue-vs-curation theme needs more evidence before scaling."
        )

    project = Project(
        company_id=company_id,
        name=demo_name,
        language=lang,
        interview_duration_minutes=25,
        welcome_message=demo_welcome,
        research_objective=demo_objective,
        research_context=demo_context,
        is_demo=True,
        created_at=now - timedelta(days=10),
    )
    db.add(project)
    db.flush()

    # Guide questions
    sort_order = 0
    for section_index, section in enumerate(demo_guide):
        for question_index, item in enumerate(section["questions"]):
            db.add(
                InterviewGuideQuestion(
                    project_id=project.id,
                    section_index=section_index,
                    section_title=section["section"],
                    question_index=question_index,
                    main_question=item["q"],
                    interview_notes="",
                    desired_learning=item["learning"],
                    sort_order=sort_order,
                )
            )
            sort_order += 1

    # Screening question
    db.add(
        ScreeningQuestion(
            project_id=project.id,
            sort_order=0,
            question=demo_screening["question"],
            options=json.dumps(demo_screening["options"]),
            disqualifying_options=json.dumps(demo_screening["disqualifying_options"]),
        )
    )

    # Interview link
    link = InterviewLink(
        project_id=project.id,
        token=secrets.token_urlsafe(32),
        is_active=True,
        created_at=now - timedelta(days=10),
    )
    db.add(link)
    db.flush()

    # Manual codes
    code_by_name: dict[str, ManualCode] = {}
    for idx, c in enumerate(DEMO_CODES):
        code = ManualCode(
            project_id=project.id,
            name=c["name"],
            color=c["color"],
            sort_order=idx,
        )
        db.add(code)
        code_by_name[c["name"]] = code
    db.flush()

    # Helper to add a participant and their turns.
    def add_participant(
        data: dict,
        days_ago: float,
        edit_first_turn: bool = False,
        quality: dict | None = None,
    ) -> tuple[Participant, list[InterviewTurn]]:
        started = now - timedelta(days=days_ago)
        completed_at = started + timedelta(minutes=22)
        q = quality or {}
        participant = Participant(
            link_id=link.id,
            project_id=project.id,
            display_name=data["display_name"],
            email=data["email"],
            profession=data["profession"],
            age_range=data["age_range"],
            country=data["country"],
            email_verified=True,
            status="completed",
            started_at=started,
            completed_at=completed_at,
            quality_score=q.get("quality_score", 0.80),
            quality_label=q.get("quality_label", "good"),
            quality_summary=q.get("quality_summary"),
            quality_strengths=json.dumps(q["quality_strengths"]) if "quality_strengths" in q else None,
            quality_issues=json.dumps(q["quality_issues"]) if "quality_issues" in q else None,
            avg_response_words=q.get("avg_response_words"),
            short_answer_pct=q.get("short_answer_pct"),
        )
        db.add(participant)
        db.flush()

        turns: list[InterviewTurn] = []
        for t_idx, turn in enumerate(data["turns"]):
            q_idx_zero_based = max(0, int(turn.get("question_index", 1)) - 1)
            interview_turn = InterviewTurn(
                participant_id=participant.id,
                turn_index=t_idx,
                question_index=q_idx_zero_based,
                is_follow_up=bool(turn.get("is_follow_up", False)),
                follow_up_index=0,
                question_text=turn["question_text"],
                response_transcript=turn["response_transcript"],
                manually_edited=(edit_first_turn and t_idx == 0),
                edited_at=(now - timedelta(days=days_ago - 0.1)) if (edit_first_turn and t_idx == 0) else None,
                created_at=started + timedelta(minutes=t_idx * 3),
            )
            db.add(interview_turn)
            turns.append(interview_turn)
        db.flush()
        return participant, turns

    seeded_participants: list[tuple[Participant, list[InterviewTurn]]] = []
    for i, p_data in enumerate(participants_data):
        q_key = quality_keys[i] if i < len(quality_keys) else None
        result = add_participant(
            p_data,
            days_ago=8 - i * 2,
            edit_first_turn=(i == 0),
            quality=quality_map.get(q_key) if q_key else None,
        )
        seeded_participants.append(result)

    # Quote tags
    for notable_idx, code_name in tag_plan:
        quote = notable_quotes[notable_idx]
        participant, turns = seeded_participants[quote["participant_index"]]
        if quote["turn_index"] >= len(turns):
            continue
        turn = turns[quote["turn_index"]]
        text = quote["text"]
        if not turn.response_transcript:
            continue
        start = turn.response_transcript.find(text)
        if start < 0:
            continue
        end = start + len(text)
        db.add(
            QuoteTag(
                turn_id=turn.id,
                manual_code_id=code_by_name[code_name].id,
                selected_text=text,
                start_index=start,
                end_index=end,
                created_by="demo",
            )
        )

    # Analysis v1 — ai_discovery
    v1 = ProjectAnalysis(
        project_id=project.id,
        version=1,
        version_label="ai_discovery",
        status="ready",
        participant_count=4,
        report=json.dumps(_v1_report(lang)),
        share_token=secrets.token_urlsafe(32),
        generated_at=now - timedelta(days=3),
        created_at=now - timedelta(days=3),
    )
    db.add(v1)
    db.flush()

    # Analysis v2 — researcher_refined
    v2 = ProjectAnalysis(
        project_id=project.id,
        version=2,
        version_label="researcher_refined",
        status="ready",
        participant_count=4,
        report=json.dumps(_v2_report(lang)),
        parent_version_id=v1.id,
        researcher_context=researcher_context,
        generated_at=now - timedelta(days=1),
        created_at=now - timedelta(days=1),
    )
    db.add(v2)
    db.flush()

    # Annotations on v2
    for ann in annotations:
        db.add(
            AnalysisThemeAnnotation(
                analysis_id=v2.id,
                theme_title=ann["theme_title"],
                status=ann["status"],
                researcher_note=ann["researcher_note"],
            )
        )

    # Memos
    for memo in memos:
        db.add(
            ProjectMemo(
                project_id=project.id,
                type=memo["type"],
                linked_key=memo["linked_key"],
                content=memo["content"],
                created_by="demo",
            )
        )

    db.commit()
    db.refresh(project)
    return project
