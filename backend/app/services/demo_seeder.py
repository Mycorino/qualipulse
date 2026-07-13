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
from app.models.study import Study, StudyAnalysis
from app.models.synthesis import CrossStudySynthesis
from app.models.survey import (
    Survey,
    SurveyLink,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.services._demo_data_en import (
    NOTABLE_QUOTES_EN,
    PARTICIPANTS2_EN,
    PARTICIPANTS_EN,
    QUALITY2_EN,
    QUALITY_EN,
)
from app.services._demo_data_fr import (
    NOTABLE_QUOTES_FR,
    PARTICIPANTS2_FR,
    PARTICIPANTS_FR,
    QUALITY2_FR,
    QUALITY_FR,
)
from app.services.study_provisioning import create_study


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


def _rec(action, rationale, owner_role, horizon, impact, effort, kpi, falsifier) -> dict:
    """Object-shaped recommendation for the demo reports (matches the live
    schema: action / rationale / owner_role / horizon / impact / effort / kpi /
    falsifier). Powers the recommendation cards, the impact×effort matrix, and
    the 30-60-90 plan in the findings PDF."""
    return {
        "action": action,
        "rationale": rationale,
        "owner_role": owner_role,
        "horizon": horizon,
        "impact": impact,
        "effort": effort,
        "kpi": kpi,
        "falsifier": falsifier,
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
                _rec(
                    "Proposer une validation des substitutions à l'avance.",
                    "La fonctionnalité la plus demandée et la plus simple à livrer.",
                    "Produit", "30d", "high", "low",
                    "Taux de commandes sans litige de substitution.",
                    "Serait réfuté si les utilisatrices ignorent l'option et se plaignent quand même des substitutions.",
                ),
                _rec(
                    "Notifier proactivement les ruptures sur les produits récurrents, avec trois alternatives.",
                    "Les ruptures découvertes à la livraison érodent la confiance plus que les frais.",
                    "Produit", "60_90d", "high", "medium",
                    "Baisse des réclamations liées aux ruptures.",
                    "Serait réfuté si les notifications n'améliorent pas la satisfaction post-livraison.",
                ),
                _rec(
                    "Investir dans la fiabilité du créneau plutôt que dans la promotion.",
                    "La fiabilité (modèle Coop@home) crée la fidélité long terme, pas la promo.",
                    "Opérations", "later", "high", "high",
                    "Taux de créneaux tenus.",
                    "Serait réfuté si la fidélité ne bouge pas malgré une fiabilité accrue.",
                ),
                _rec(
                    "Permettre l'export et la portabilité de l'historique d'achats.",
                    "Réduit la peur du switch et aide à capter les clients des enseignes concurrentes.",
                    "Produit", "later", "medium", "medium",
                    "Taux de conversion des nouveaux venus important leur historique.",
                    "Serait réfuté si l'import d'historique n'augmente pas l'acquisition.",
                ),
                _rec(
                    "Cesser de se positionner uniquement sur le prix.",
                    "Les segments aisés paient pour la fiabilité, pas pour la promo.",
                    "Marketing", "30d", "medium", "low",
                    "Rétention des segments à fort panier.",
                    "Serait réfuté si les segments aisés réagissent surtout aux promotions.",
                ),
            ],
            "personas": [
                {
                    "name": "La Fidèle par inertie",
                    "grounded_in": ["Camille D.", "Sophie L."],
                    "one_liner": "Reste par coût de switch et fiabilité, pas par prix.",
                    "segment": "Actives urbaines, usage installé",
                    "goals": ["Gagner du temps sans tout reconfigurer"],
                    "frustrations": ["Ruptures de stock", "Peur de tout refaire ailleurs"],
                    "behaviours": ["Réutilise un panier type chaque semaine"],
                    "primary_job": "Garder une routine de courses qui marche.",
                    "anchor_quote": {"text": q(0)["text"], "participant_identifier": "Camille D."},
                },
                {
                    "name": "L'Optimiseur familial",
                    "grounded_in": ["Romain B.", "Léa M."],
                    "one_liner": "Compare au centime et choisit l'enseigne la moins chère.",
                    "segment": "Budgets serrés (famille nombreuse, étudiante)",
                    "goals": ["Minimiser le coût du panier"],
                    "frustrations": ["Écarts de prix entre enseignes"],
                    "behaviours": ["Compare les prix avant de commander"],
                    "primary_job": "Nourrir le foyer au meilleur prix.",
                    "anchor_quote": {"text": q(2)["text"], "participant_identifier": "Romain B."},
                },
            ],
            "journey": {
                "applicable": True,
                "label": "Choisir et rester fidèle à un service de courses en ligne",
                "stages": [
                    {"name": "Essai", "goal": "Tester un nouveau service", "emotion": 1,
                     "quote": {"text": "", "participant_identifier": ""},
                     "pain": "", "opportunity": "Onboarding simple"},
                    {"name": "Routine", "goal": "Installer son panier type", "emotion": 2,
                     "quote": {"text": "", "participant_identifier": ""},
                     "pain": "", "opportunity": "Portabilité de l'historique"},
                    {"name": "Rupture", "goal": "Recevoir la commande complète", "emotion": -2,
                     "quote": {"text": q(1)["text"], "participant_identifier": "Camille D."},
                     "pain": "Ruptures de stock", "opportunity": "Validation des substitutions"},
                    {"name": "Réévaluation", "goal": "Comparer les enseignes", "emotion": -1,
                     "quote": {"text": q(0)["text"], "participant_identifier": "Camille D."},
                     "pain": "Coût de switch invisible", "opportunity": "Fiabilité du créneau"},
                    {"name": "Fidélisation", "goal": "Rester par fiabilité", "emotion": 1,
                     "quote": {"text": q(3)["text"], "participant_identifier": "Sophie L."},
                     "pain": "", "opportunity": ""},
                ],
            },
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
            _rec(
                "Ship a real pause feature (2–3 months, watchlist preserved).",
                "The most-requested unmet need — three of four cycle in and out around shows.",
                "Product", "60_90d", "high", "high",
                "Reactivation rate of paused vs. cancelled accounts.",
                "Wrong if paused users churn at the same rate as cancelled ones.",
            ),
            _rec(
                "Audit and simplify the cancellation flow.",
                "The friction doesn't prevent churn — it prevents win-back.",
                "Growth", "30d", "high", "low",
                "Re-subscription rate within 6 months of cancelling.",
                "Wrong if win-back is unchanged after removing the dark patterns.",
            ),
            _rec(
                "Time price increases to coincide with flagship releases.",
                "The price-increase email is the single biggest cancellation trigger.",
                "Growth", "now", "medium", "low",
                "Churn in the 30 days after a price-change email.",
                "Wrong if churn spikes regardless of release timing.",
            ),
            _rec(
                "Invest in editorial curation as a differentiator.",
                "A point of view is what makes a service feel like more than a warehouse.",
                "Product", "later", "medium", "high",
                "Retention of light users after the headliner show ends.",
                "Wrong if curated services retain no better than algorithm-only ones.",
            ),
            _rec(
                "Communicate proactively about what's coming (monthly).",
                "Subscribers want to be told what to watch, not left to the algorithm.",
                "Marketing", "30d", "medium", "low",
                "Open + watch-through rate on 'coming soon' comms.",
                "Wrong if proactive comms don't lift engagement between headliners.",
            ),
        ],
        "personas": [
            {
                "name": "The Rotating Renter",
                "grounded_in": ["Priya R.", "Marcus T."],
                "one_liner": "Subscribes for a specific show, then leaves — wants to pause, not cancel.",
                "segment": "Show-driven subscribers",
                "goals": ["Match spending to actual viewing"],
                "frustrations": ["Binary subscribe/cancel", "Cancellation dark patterns"],
                "behaviours": ["Cancels the day the season ends"],
                "primary_job": "Watch what I came for without paying for dead months.",
                "anchor_quote": {"text": q(0)["text"], "participant_identifier": "Priya R."},
            },
            {
                "name": "The Editorial Loyalist",
                "grounded_in": ["Alex K.", "Marcus T."],
                "one_liner": "Stays for a clear point of view or exclusive content, not a generic catalogue.",
                "segment": "Taste- and exclusivity-driven",
                "goals": ["A service with a distinct identity"],
                "frustrations": ["Interchangeable catalogues"],
                "behaviours": ["Leaves when the headliner ends"],
                "primary_job": "Find things worth watching that nobody else has.",
                "anchor_quote": {"text": q(3)["text"], "participant_identifier": "Alex K."},
            },
        ],
        "journey": {
            "applicable": True,
            "label": "Reconsidering a streaming subscription",
            "stages": [
                {"name": "Subscribe", "goal": "Get access to a specific show", "emotion": 1,
                 "quote": {"text": "", "participant_identifier": ""},
                 "pain": "", "opportunity": "Frictionless signup"},
                {"name": "Binge", "goal": "Watch the headliner", "emotion": 2,
                 "quote": {"text": "", "participant_identifier": ""},
                 "pain": "", "opportunity": ""},
                {"name": "Price nudge", "goal": "Decide if it's still worth it", "emotion": -1,
                 "quote": {"text": "", "participant_identifier": ""},
                 "pain": "Price-increase email", "opportunity": "Time increases to releases"},
                {"name": "Cancel", "goal": "Leave cleanly", "emotion": -2,
                 "quote": {"text": q(1)["text"], "participant_identifier": "Priya R."},
                 "pain": "Dark-pattern cancel flow", "opportunity": "Simplify cancellation"},
                {"name": "Dormant", "goal": "Come back for the next show", "emotion": 0,
                 "quote": {"text": q(0)["text"], "participant_identifier": "Priya R."},
                 "pain": "No pause state", "opportunity": "Ship a pause feature"},
            ],
        },
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


# ── Hybrid demo: a sibling survey + Quantified Themes report ────────────────
#
# The demo Study ships with an interview track *and* a quick-pulse survey, so
# a new user lands on a genuine mixed-methods Study — the instrument-mix badge
# reads "Hybrid" and the Report tab has a real Quantified Themes report — not
# an interview-only project. The survey content is mono-language like the rest
# of the seed. The Quantified Themes report is hand-authored (same approach as
# the ProjectAnalysis reports above) so seeding never makes an AI call.

DEMO_SURVEY_NAME = "Streaming habits — quick pulse"
DEMO_SURVEY_NAME_FR = "Courses en ligne — pouls rapide"

# Per-language survey plan — a real stat questionnaire, not a two-question
# pulse: frequency (mc_single), current stack (mc_multi), value-for-money
# (likert 1–5), recommendation (NPS 0–10) and an open churn-trigger question.
#
# `questions` defines the instrument; `cohorts` defines who answers what.
# Each cohort carries a per-question answer plan that is cycled over the
# cohort's `count` responses (None = respondent skipped the question). The
# distributions are chosen so the hand-authored Quantified Themes report
# quotes numbers the analytics layer actually reproduces:
#   EN — heavy NPS mean 9.1 / light 4.1; likert 4.2 vs 2.4; Netflix in 38/44.
#   FR — régulières NPS 9,1 / occasionnelles 4,6 ; Carrefour Drive dans 26/44.
DEMO_SURVEY_EN = {
    "name": DEMO_SURVEY_NAME,
    "questions": [
        {
            "key": "freq", "type": "mc_single",
            "prompt": "Which best describes how much you stream?",
            "config": {"choices": [
                {"id": "daily", "label": "Every day"},
                {"id": "most_days", "label": "Most days"},
                {"id": "weekly", "label": "A few times a week"},
                {"id": "monthly", "label": "A few times a month or less"},
            ], "randomize": False, "has_other": False},
        },
        {
            "key": "services", "type": "mc_multi",
            "prompt": "Which paid streaming services does your household currently have?",
            "config": {"choices": [
                {"id": "netflix", "label": "Netflix"},
                {"id": "prime", "label": "Prime Video"},
                {"id": "disney", "label": "Disney+"},
                {"id": "hbo", "label": "HBO Max"},
                {"id": "apple", "label": "Apple TV+"},
            ], "randomize": False, "has_other": False},
        },
        {
            "key": "value", "type": "likert",
            "prompt": "The catalogue on my main service is worth what I pay for it.",
            "config": {"scale": 5, "anchors": ["Strongly disagree", "Strongly agree"],
                       "reverse_coded": False},
        },
        {
            "key": "nps", "type": "nps",
            "prompt": "How likely are you to recommend your main streaming service to a friend?",
            "config": {},
        },
        {
            "key": "churn", "type": "open_text",
            "prompt": "What would make you cancel your main service tomorrow?",
            "config": {"max_chars": 500, "ai_cluster": False},
        },
    ],
    "cohorts": [
        {
            "id": "heavy", "count": 26,
            "answers": {
                "freq": ["daily", "daily", "most_days"],
                "services": [
                    ["netflix", "disney", "prime"],
                    ["netflix", "hbo"],
                    ["netflix", "prime", "apple"],
                    ["netflix", "disney"],
                ],
                "value": [5, 4, 4, 5, 4, 3],
                "nps": [9, 10, 8, 9, 10, 9, 8, 10],
                # Full-length plan (one slot per respondent) so every open
                # answer in the sample is unique — no cycled duplicates.
                "churn": [
                    "A big price rise with nothing new to watch.",
                    None,
                    "If they lost the shows my family watches every week.",
                    None, None,
                    "Ads showing up on the plan I already pay for.",
                    None, None,
                    "Another price increase right after the last one.",
                    None, None,
                    "If the recommendations stopped being good, I'd drift off.",
                    None, None, None,
                    "Losing 4K on the family plan while keeping the price.",
                    None, None,
                    "If my kids' profiles stopped working on trips.",
                    None, None, None,
                    "Honestly, not much — it's the default in our house.",
                    None, None, None,
                ],
            },
        },
        {
            "id": "light", "count": 18,
            "answers": {
                "freq": ["weekly", "monthly", "weekly"],
                "services": [["netflix"], ["prime"], ["netflix", "prime"]],
                "value": [2, 3, 2, 3, 2],
                "nps": [4, 3, 5, 2, 6, 4, 5, 4],
                "churn": [
                    "Honestly I only keep it for one show — the day it ends, I cancel.",
                    "The price keeps creeping up and I barely watch.",
                    None,
                    "Nothing left to watch after I finish the series I came for.",
                    None,
                    "I already plan to cancel and resubscribe when the next season drops.",
                    None,
                    "Any price rise at all — it's already borderline for how little I use it.",
                    None,
                    "The catalogue feels the same as everywhere else.",
                    "I mostly watch YouTube anyway.",
                    None,
                    "When the football season ends, so does my subscription.",
                    None,
                    "Seeing it on my bank statement is usually the trigger.",
                    None,
                    "A month with nothing new in my genres.",
                    None,
                ],
            },
        },
    ],
}
DEMO_SURVEY_FR = {
    "name": DEMO_SURVEY_NAME_FR,
    "questions": [
        {
            "key": "freq", "type": "mc_single",
            "prompt": "À quelle fréquence faites-vous vos courses alimentaires en ligne ?",
            "config": {"choices": [
                {"id": "chaque_semaine", "label": "Chaque semaine"},
                {"id": "deux_trois", "label": "Deux à trois fois par mois"},
                {"id": "une_fois", "label": "Environ une fois par mois"},
                {"id": "moins", "label": "Moins souvent"},
            ], "randomize": False, "has_other": False},
        },
        {
            "key": "services", "type": "mc_multi",
            "prompt": "Quelles enseignes utilisez-vous pour vos courses en ligne ?",
            "config": {"choices": [
                {"id": "carrefour", "label": "Carrefour Drive"},
                {"id": "leclerc", "label": "Leclerc Drive"},
                {"id": "picard", "label": "Picard"},
                {"id": "amazon", "label": "Amazon Fresh"},
                {"id": "coop", "label": "Coop@home"},
            ], "randomize": False, "has_other": False},
        },
        {
            "key": "value", "type": "likert",
            "prompt": "Le service de mon enseigne principale vaut ce qu'il me coûte.",
            "config": {"scale": 5, "anchors": ["Pas du tout d'accord", "Tout à fait d'accord"],
                       "reverse_coded": False},
        },
        {
            "key": "nps", "type": "nps",
            "prompt": "Quelle est la probabilité que vous recommandiez votre enseigne principale ?",
            "config": {},
        },
        {
            "key": "churn", "type": "open_text",
            "prompt": "Qu'est-ce qui vous ferait abandonner les courses en ligne demain ?",
            "config": {"max_chars": 500, "ai_cluster": False},
        },
    ],
    "cohorts": [
        {
            "id": "regulieres", "count": 26,
            "answers": {
                "freq": ["chaque_semaine", "chaque_semaine", "deux_trois"],
                "services": [
                    ["carrefour", "picard"],
                    ["carrefour", "leclerc"],
                    ["carrefour", "picard", "amazon"],
                    ["carrefour"],
                ],
                "value": [5, 4, 4, 5, 4, 3],
                "nps": [9, 10, 8, 9, 10, 9, 8, 10],
                # Full-length plan (one slot per respondent) so every open
                # answer in the sample is unique — no cycled duplicates.
                "churn": [
                    "Une commande avec trop de produits manquants, encore une fois.",
                    None,
                    "Des substitutions imposées sans me demander mon avis.",
                    None, None,
                    "Si les créneaux fiables disparaissaient.",
                    None, None,
                    "Une hausse des frais de préparation sans amélioration du service.",
                    None, None,
                    "Des fruits et légumes choisis n'importe comment.",
                    None, None, None,
                    "Si je devais refaire toutes mes listes après un changement de site.",
                    None, None,
                    "Un service client injoignable quand une commande se passe mal.",
                    None, None, None,
                    "Franchement pas grand-chose, c'est devenu notre routine du mercredi.",
                    None, None, None,
                ],
            },
        },
        {
            "id": "occasionnelles", "count": 18,
            "answers": {
                "freq": ["une_fois", "moins", "une_fois"],
                "services": [["leclerc"], ["amazon"], ["leclerc", "coop"]],
                "value": [2, 3, 2, 3, 2],
                "nps": [5, 4, 6, 4, 5, 4, 6, 3],
                "churn": [
                    "Les frais de livraison — dès que ça dépasse le prix du bus, j'y vais moi-même.",
                    "Trop de ruptures de stock, je finis toujours par devoir passer en magasin.",
                    None,
                    "Le minimum de commande est trop haut pour mon panier.",
                    None,
                    "Recevoir des produits presque périmés une fois de plus.",
                    None,
                    "Les créneaux jamais disponibles le soir même.",
                    None,
                    "Payer des frais pour un service que je n'utilise qu'une fois par mois.",
                    "Une appli trop lente pour un panier de dix articles.",
                    None,
                    "Je préfère choisir mes produits frais moi-même.",
                    None,
                    "Le drive près du travail a fermé, ça ne vaut plus le détour.",
                    None,
                    "Un abonnement obligatoire me ferait fuir tout de suite.",
                    None,
                ],
            },
        },
    ],
}


def _quanti_report(lang: str) -> dict:
    """Hand-authored Quantified Themes report for the demo Study.

    Matches the QuantifiedThemeReport schema (app/schemas/study.py). Anchor
    quotes are pulled verbatim from NOTABLE_QUOTES so they survive the
    interview-evidence verification the real analysis service applies.
    """
    if lang == "fr":
        notable = NOTABLE_QUOTES_FR
        return {
            "executive_summary": (
                "Un questionnaire en cinq questions (n=44) et quatre "
                "entretiens approfondis convergent : la fidélité aux "
                "enseignes de courses en ligne tient à un coût de switch "
                "invisible, pas au prix. Les clientes régulières notent leur "
                "enseigne 9,1 sur 10 en recommandation et 4,2 sur 5 en "
                "rapport qualité-prix ; les occasionnelles tombent à 4,6 et "
                "2,4. Carrefour Drive sert d'enseigne d'ancrage (26 paniers "
                "sur 44) et les ruptures de stock sont la friction qui fait "
                "basculer les notes — les réponses libres annoncent un "
                "abandon opérationnel, pas tarifaire."
            ),
            "verdict": (
                "Investir d'abord sur l'expérience de rupture de stock "
                "(validation des substitutions à l'avance) plutôt que sur le "
                "prix : c'est la friction la plus citée chez les détractrices, "
                "le premier motif d'abandon dans les réponses libres, et le "
                "seul levier corroboré par les deux méthodes. Réserve : le "
                "coût de switch n'est pas encore chiffré — le sondage de "
                "suivi doit précéder tout investissement lourd."
            ),
            "themes": [
                {
                    "title": "Les clientes occasionnelles recommandent deux fois moins leur enseigne",
                    "survey_signal": {
                        "summary": (
                            "Les clientes occasionnelles donnent une note de "
                            "recommandation moyenne de 4,6, contre 9,1 pour "
                            "les clientes régulières — un écart de 4,5 points "
                            "sur la même échelle."
                        ),
                        "n": 18,
                        "percentage": None,
                        "segment_label": "Clientes occasionnelles",
                        "segment_over_index": None,
                    },
                    "interview_evidence": {
                        "x_of_y": "3 sur 4",
                        "interview_count": 3,
                        "anchor_quote": notable[1]["text"],
                        "segments_mentioned": [],
                    },
                    "counter_evidence": (
                        "Une participante sur quatre (profil petits paniers) "
                        "se dit indifférente aux ruptures et ne regarde que "
                        "le total — un segment purement prix existe, mais "
                        "reste minoritaire dans les deux sources."
                    ),
                    "recommendation": {
                        "kind": "product",
                        "action": (
                            "Proposer une validation des substitutions à "
                            "l'avance pour désamorcer la friction des "
                            "ruptures de stock."
                        ),
                        "rationale": (
                            "La rupture de stock est la friction la plus "
                            "citée en entretien et le meilleur candidat pour "
                            "remonter la note des clientes occasionnelles."
                        ),
                        "success_test": (
                            "La note de recommandation des clientes "
                            "occasionnelles dépasse 6/10 à la vague "
                            "suivante, à tarification constante."
                        ),
                    },
                    "confidence": "supported",
                },
                {
                    "title": "Le rapport qualité-prix perçu suit l'usage, pas les tarifs",
                    "survey_signal": {
                        "summary": (
                            "À l'affirmation « le service vaut ce qu'il me "
                            "coûte », les régulières répondent 4,2 sur 5 en "
                            "moyenne, les occasionnelles 2,4 — alors que les "
                            "deux groupes paient les mêmes frais."
                        ),
                        "n": 44,
                        "percentage": None,
                        "segment_label": None,
                        "segment_over_index": None,
                    },
                    "interview_evidence": {
                        "x_of_y": "2 sur 4",
                        "interview_count": 2,
                        "anchor_quote": notable[2]["text"],
                        "segments_mentioned": [],
                    },
                    "counter_evidence": (
                        "Le questionnaire ne distingue pas « je paie trop "
                        "cher » de « je n'utilise pas assez » — l'écart peut "
                        "refléter la fréquence d'usage plutôt qu'un jugement "
                        "sur les tarifs."
                    ),
                    "recommendation": {
                        "kind": "marketing",
                        "action": (
                            "Cibler les occasionnelles avec la valeur d'usage "
                            "(créneaux fiables, listes, gain de temps) plutôt "
                            "qu'avec des promotions prix."
                        ),
                        "rationale": (
                            "Le déficit de valeur perçue vient de l'usage, "
                            "pas du tarif — une promo ne le comble pas."
                        ),
                        "success_test": (
                            "La note qualité-prix des occasionnelles remonte "
                            "au-dessus de 3/5 après une campagne usage, sans "
                            "baisse de prix."
                        ),
                    },
                    "confidence": "supported",
                },
                {
                    "title": "Une enseigne d'ancrage, des compléments qui tournent",
                    "survey_signal": {
                        "summary": (
                            "Carrefour Drive apparaît dans 26 paniers sur 44 "
                            "(59 %) et dans la totalité des paniers des "
                            "régulières ; le foyer moyen combine 2 enseignes."
                        ),
                        "n": 44,
                        "percentage": 59.1,
                        "segment_label": None,
                        "segment_over_index": None,
                    },
                    "interview_evidence": {
                        "x_of_y": "3 sur 4",
                        "interview_count": 3,
                        "anchor_quote": notable[0]["text"],
                        "segments_mentioned": [],
                    },
                    "counter_evidence": (
                        "Les occasionnelles n'ont pas d'enseigne d'ancrage "
                        "(Leclerc et Amazon Fresh se partagent leurs paniers) "
                        "— l'ancrage est peut-être la conséquence de la "
                        "régularité, pas sa cause."
                    ),
                    "recommendation": {
                        "kind": "product",
                        "action": (
                            "Rendre l'historique et les listes portables pour "
                            "attaquer l'ancrage des enseignes concurrentes — "
                            "et défendre le sien par la fiabilité."
                        ),
                        "rationale": (
                            "L'ancrage tient aux actifs accumulés ; celui qui "
                            "abaisse la barrière d'import capte les foyers "
                            "multi-enseignes."
                        ),
                        "success_test": (
                            "Les foyers qui importent une liste concurrente "
                            "passent au moins 2 commandes dans le mois qui "
                            "suit."
                        ),
                    },
                    "confidence": "supported",
                },
                {
                    "title": "L'abandon annoncé est opérationnel, pas tarifaire",
                    "survey_signal": {
                        "summary": (
                            "Dans les réponses libres « qu'est-ce qui vous "
                            "ferait abandonner ? », ruptures, substitutions "
                            "imposées et créneaux dominent chez les "
                            "régulières ; les frais n'arrivent en tête que "
                            "chez les occasionnelles."
                        ),
                        "n": 18,
                        "percentage": None,
                        "segment_label": "Réponses libres",
                        "segment_over_index": None,
                    },
                    "interview_evidence": {
                        "x_of_y": "2 sur 4",
                        "interview_count": 2,
                        "anchor_quote": notable[3]["text"],
                        "segments_mentioned": [],
                    },
                    "counter_evidence": (
                        "Les réponses libres sont peu nombreuses (18) et "
                        "déclaratives — un motif d'abandon déclaré n'est pas "
                        "un abandon observé."
                    ),
                    "recommendation": {
                        "kind": "next_research",
                        "action": (
                            "Croiser ces motifs déclarés avec une étude de "
                            "sortie auprès de clientes réellement parties."
                        ),
                        "rationale": (
                            "Seule la comparaison déclaré/observé dira si la "
                            "fiabilité est bien le levier anti-churn n°1."
                        ),
                        "success_test": (
                            "L'étude de sortie retrouve les ruptures et "
                            "substitutions comme déclencheur majoritaire des "
                            "départs réels."
                        ),
                    },
                    "confidence": "directional",
                },
            ],
            "gaps": [
                "Le poids économique du coût de switch est décrit par les "
                "participantes mais jamais chiffré.",
                "L'échantillon ne contient que des clientes actives — les "
                "défections réelles ne sont connues que par ouï-dire "
                "(biais de survivance).",
                "Les sous-groupes (26 régulières, 18 occasionnelles) sont "
                "sous le seuil n=30 : leurs écarts sont rapportés en "
                "moyennes, jamais en pourcentages.",
            ],
            "methodology_note": (
                "Questionnaire : 5 questions (fréquence, enseignes, "
                "qualité-prix, recommandation, question ouverte), 44 réponses "
                "complètes recueillies sur 7 jours. Entretiens : 4 complétés. "
                "Conformément au contrat méthodologique, les pourcentages ne "
                "sont affichés qu'à n≥30 ; les sous-groupes en deçà sont "
                "rapportés en moyennes et effectifs. La confiance reflète "
                "l'accord entre le signal du questionnaire et les entretiens."
            ),
            "generated_with_survey_count": 1,
            "generated_with_response_count": 44,
            "generated_with_interview_count": 4,
        }

    notable = NOTABLE_QUOTES_EN
    return {
        "executive_summary": (
            "A five-question survey (n=44) and four in-depth interviews "
            "point the same direction: streaming loyalty is thin, "
            "concentrated, and rented by the show. Heavy streamers rate "
            "their main service 9.1 on the 0–10 recommendation scale and "
            "4.2 of 5 on value-for-money; light streamers drop to 4.1 and "
            "2.4. Netflix anchors 38 of 44 household stacks (86%), the rest "
            "of the stack rotates, and the open answers describe planned, "
            "show-driven cancellation rather than dissatisfaction. The "
            "clearest product opening is a pause state between subscribed "
            "and cancelled."
        ),
        "verdict": (
            "Build the pause state before touching catalogue spend: it is "
            "the only intervention corroborated by both methods, it matches "
            "the planned churn the open answers describe, and it converts "
            "decisive light-streamer churn into dormancy. Caveat: which "
            "exclusives actually drive heavy-streamer renewal is not yet "
            "sized — run the follow-up survey before committing catalogue "
            "budget."
        ),
        "themes": [
            {
                "title": "Light streamers are far less likely to recommend their main service",
                "survey_signal": {
                    "summary": (
                        "Light streamers gave their main service an average "
                        "recommendation score of 4.1, against 9.1 for heavy "
                        "streamers — a 5-point split on the same scale."
                    ),
                    "n": 18,
                    "percentage": None,
                    "segment_label": "Light streamers",
                    "segment_over_index": None,
                },
                "interview_evidence": {
                    "x_of_y": "3 of 4",
                    "interview_count": 3,
                    "anchor_quote": notable[0]["text"],
                    "segments_mentioned": [],
                },
                "counter_evidence": (
                    "One interviewee in four keeps a single year-round "
                    "subscription and never rotates — a loyal-by-inertia "
                    "profile a pause state would not move."
                ),
                "recommendation": {
                    "kind": "product",
                    "action": (
                        "Build a pause state so light streamers can stay "
                        "subscribed between the shows they come back for."
                    ),
                    "rationale": (
                        "Light streamers churn decisively because the only "
                        "exit is a full cancel; a dormant tier converts a "
                        "lost subscriber into a paused one."
                    ),
                    "success_test": (
                        "Light streamers offered a pause option show a "
                        "measurably lower full-cancel rate over the next "
                        "quarter."
                    ),
                },
                "confidence": "supported",
            },
            {
                "title": "Perceived value tracks usage, not price",
                "survey_signal": {
                    "summary": (
                        "On “the catalogue is worth what I pay”, heavy "
                        "streamers average 4.2 of 5; light streamers 2.4 — "
                        "both groups pay the same prices."
                    ),
                    "n": 44,
                    "percentage": None,
                    "segment_label": None,
                    "segment_over_index": None,
                },
                "interview_evidence": {
                    "x_of_y": "3 of 4",
                    "interview_count": 3,
                    "anchor_quote": notable[2]["text"],
                    "segments_mentioned": [],
                },
                "counter_evidence": (
                    "The survey cannot separate “too expensive” from “I "
                    "barely use it” — the value gap may be a usage gap "
                    "wearing price language."
                ),
                "recommendation": {
                    "kind": "marketing",
                    "action": (
                        "Time price changes and win-back offers to high-watch "
                        "months instead of discounting flatly — the value "
                        "deficit is usage-driven, not price-driven."
                    ),
                    "rationale": (
                        "A discount cannot fix a value score that collapses "
                        "when usage does; timing can."
                    ),
                    "success_test": (
                        "Price changes sequenced after flagship releases show "
                        "measurably lower cancellation than mid-lull changes."
                    ),
                },
                "confidence": "supported",
            },
            {
                "title": "Households anchor on one service; the rest of the stack rotates",
                "survey_signal": {
                    "summary": (
                        "Netflix appears in 38 of 44 household stacks (86%) "
                        "and in every heavy-streamer stack; the average "
                        "household holds 2 paid services."
                    ),
                    "n": 44,
                    "percentage": 86.4,
                    "segment_label": None,
                    "segment_over_index": None,
                },
                "interview_evidence": {
                    "x_of_y": "3 of 4",
                    "interview_count": 3,
                    "anchor_quote": notable[3]["text"],
                    "segments_mentioned": [],
                },
                "counter_evidence": (
                    "Anchor status may be an artefact of catalogue size "
                    "rather than loyalty — no interviewee described choosing "
                    "the anchor; they inherited it."
                ),
                "recommendation": {
                    "kind": "product",
                    "action": (
                        "Compete for the rotating second slot, not the "
                        "anchor slot: make joining-for-one-show and leaving "
                        "gracefully a first-class flow."
                    ),
                    "rationale": (
                        "The anchor slot is locked; the second slot turns "
                        "over constantly and rewards the service that "
                        "welcomes returners."
                    ),
                    "success_test": (
                        "Resubscription rate among lapsed subscribers rises "
                        "measurably after simplifying the return flow."
                    ),
                },
                "confidence": "supported",
            },
            {
                "title": "Stated cancellation is planned and show-driven, not dissatisfied",
                "survey_signal": {
                    "summary": (
                        "In the open “what would make you cancel?” answers, "
                        "finishing a show and planned resubscription dominate "
                        "among light streamers; price alone leads only when "
                        "paired with a dead catalogue month."
                    ),
                    "n": 18,
                    "percentage": None,
                    "segment_label": "Open answers",
                    "segment_over_index": None,
                },
                "interview_evidence": {
                    "x_of_y": "2 of 4",
                    "interview_count": 2,
                    "anchor_quote": notable[1]["text"],
                    "segments_mentioned": [],
                },
                "counter_evidence": (
                    "Only 18 respondents answered the open question, and "
                    "stated churn intent is not observed churn."
                ),
                "recommendation": {
                    "kind": "next_research",
                    "action": (
                        "Run exit interviews with actually-churned "
                        "subscribers to test whether real cancellations "
                        "follow the planned, show-driven pattern."
                    ),
                    "rationale": (
                        "Only a stated-vs-observed comparison can confirm "
                        "the churn mechanics before product bets on them."
                    ),
                    "success_test": (
                        "Exit interviews date most real cancellations to a "
                        "show ending or a mistimed price event, not to "
                        "service dissatisfaction."
                    ),
                },
                "confidence": "directional",
            },
        ],
        "gaps": [
            "Which exclusive titles drive renewal is suggested by the "
            "interviews but not sized.",
            "The sample contains only current subscribers — churned users' "
            "cancellation triggers are known only second-hand "
            "(survivorship bias).",
            "Cohort cuts (26 heavy, 18 light) sit below the n=30 threshold: "
            "their gaps are reported as averages, never as percentages.",
        ],
        "methodology_note": (
            "Survey: 5 questions (frequency, current stack, value-for-money, "
            "recommendation, open churn trigger), 44 completed responses "
            "fielded over 7 days. Interviews: 4 completed, 7–9 turns each. "
            "Per the methodology contract, percentages are shown only at "
            "n≥30; cohort cuts below that threshold are reported as averages "
            "and counts. Confidence reflects agreement between the survey "
            "signal and the interview evidence."
        ),
        "generated_with_survey_count": 1,
        "generated_with_response_count": 44,
        "generated_with_interview_count": 4,
    }


def _seed_demo_survey(
    db: Session, study: Study, company_id: str, lang: str, now: datetime
) -> Survey:
    """Add a published five-question survey with 44 completed responses to the
    demo Study, so the Study reads as a true hybrid (survey + interviews)."""
    cfg = DEMO_SURVEY_FR if lang == "fr" else DEMO_SURVEY_EN
    fielding_start = now - timedelta(days=9)
    fielding_end = now - timedelta(days=2)

    survey = Survey(
        study_id=study.id,
        company_id=company_id,
        name=cfg["name"],
        role="standalone",
        status="live",
        fielding_started_at=fielding_start,
        fielding_ended_at=fielding_end,
        created_at=now - timedelta(days=10),
    )
    db.add(survey)
    db.flush()

    question_by_key: dict[str, SurveyQuestion] = {}
    for i, q_plan in enumerate(cfg["questions"]):
        question = SurveyQuestion(
            survey_id=survey.id,
            sort_order=i,
            type=q_plan["type"],
            prompt=q_plan["prompt"],
            is_required=q_plan["type"] not in ("open_text", "short_text"),
            config=json.dumps(q_plan.get("config") or {}),
        )
        db.add(question)
        question_by_key[q_plan["key"]] = question
    db.flush()

    link = SurveyLink(
        survey_id=survey.id,
        token=secrets.token_urlsafe(32),
        is_active=True,
        is_anonymous=False,
        created_at=now - timedelta(days=10),
    )
    db.add(link)
    db.flush()

    n = 0
    for cohort in cfg["cohorts"]:
        answers = cohort["answers"]
        for i in range(cohort["count"]):
            n += 1
            started = fielding_start + timedelta(hours=n * 3)
            response = SurveyResponse(
                survey_id=survey.id,
                company_id=company_id,
                link_id=link.id,
                started_at=started,
                completed_at=started + timedelta(minutes=4),
            )
            db.add(response)
            db.flush()
            for key, question in question_by_key.items():
                plan = answers.get(key)
                if not plan:
                    continue
                value = plan[i % len(plan)]
                if value is None:
                    continue  # respondent skipped this (optional) question
                answer = SurveyResponseAnswer(
                    response_id=response.id,
                    question_id=question.id,
                    answered_at=started + timedelta(minutes=2),
                )
                if question.type == "mc_single":
                    answer.value_choice_ids = json.dumps([value])
                elif question.type == "mc_multi":
                    answer.value_choice_ids = json.dumps(list(value))
                elif question.type in ("likert", "nps"):
                    answer.value_numeric = float(value)
                else:  # open_text / short_text
                    answer.value_text = value
                db.add(answer)
    db.flush()
    return survey


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

    # Sprint 15: the demo project belongs to a Study like any other project.
    demo_study = create_study(db, company_id, demo_name)

    project = Project(
        company_id=company_id,
        study_id=demo_study.id,
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

    # Hybrid layer: a sibling quick-pulse survey + a Quantified Themes report,
    # so the demo Study reads as a real mixed-methods effort, not an
    # interview-only project.
    _seed_demo_survey(db, demo_study, company_id, lang, now)
    db.add(
        StudyAnalysis(
            study_id=demo_study.id,
            version=1,
            status="ready",
            report=json.dumps(_quanti_report(lang)),
            generated_at=now - timedelta(hours=6),
            created_at=now - timedelta(hours=6),
        )
    )

    # Cross-study synthesis showcase: a sibling exit-interview study plus a
    # ready decision memo across both, so a new account can experience the
    # full arc — interviews → per-study analysis → cross-study decision memo —
    # without running a single real interview.
    second_study = _seed_second_demo_study(db, company_id, lang, now)
    db.add(
        CrossStudySynthesis(
            company_id=company_id,
            name=DEMO_MEMO_NAME_FR if lang == "fr" else DEMO_MEMO_NAME,
            decision_question=DEMO_MEMO_QUESTION_FR if lang == "fr" else DEMO_MEMO_QUESTION,
            study_ids=json.dumps([demo_study.id, second_study.id]),
            status="ready",
            report=json.dumps(_memo_report(lang)),
            language=lang,
            generated_at=now - timedelta(hours=2),
            created_at=now - timedelta(hours=2),
        )
    )

    db.commit()
    db.refresh(project)
    return project


# ═══════════════════════════════════════════════════════════════════════════
# Demo study #2 + cross-study decision memo
#
# A second, leaner demo study (3 exit interviews, one ready analysis) whose
# real purpose is to make the cross-study synthesis demoable on day one:
# the seeded CrossStudySynthesis memo cites both studies by name, corroborates
# them where they agree and surfaces one deliberate conflict. All memo
# evidence quotes are verbatim substrings of the seeded transcripts — same
# integrity bar as the per-study analyses.
# ═══════════════════════════════════════════════════════════════════════════

DEMO2_PROJECT_NAME = "[Demo] Why subscribers cancel — exit interviews"
DEMO2_PROJECT_NAME_FR = "[Démo] Pourquoi ils quittent le drive — entretiens de sortie"

DEMO2_OBJECTIVE = (
    "Understand the precise moment subscribers decide to cancel a streaming "
    "service, what triggered it, and what — if anything — would have kept them."
)
DEMO2_OBJECTIVE_FR = (
    "Comprendre le moment précis où les clients arrêtent de commander leurs "
    "courses en ligne, ce qui l'a déclenché, et ce qui aurait pu les retenir."
)

DEMO2_WELCOME = (
    "Thanks for talking to us! You recently cancelled a streaming subscription — "
    "we'd love to hear the honest story of how that happened. There are no wrong "
    "answers; we're interested in the real moment, not the polite version."
)
DEMO2_WELCOME_FR = (
    "Merci de nous accorder ce moment ! Vous avez récemment arrêté de commander "
    "vos courses en ligne — racontez-nous honnêtement comment ça s'est passé. "
    "Il n'y a pas de mauvaise réponse : c'est le vrai moment qui nous intéresse."
)

DEMO2_GUIDE: list[dict] = [
    {
        "section": "The moment of cancellation",
        "questions": [
            {
                "q": "Walk me through the last streaming service you cancelled — what happened that week?",
                "learning": "The concrete trigger event, its timing, and how long the decision had been latent.",
            },
            {
                "q": "What, if anything, could the service have done to keep you?",
                "learning": "Save-offer receptivity, pause/step-down demand, perceived silence at the exit.",
            },
        ],
    },
    {
        "section": "Looking back",
        "questions": [
            {
                "q": "How do you feel about that service now — would you ever go back?",
                "learning": "Win-back conditions, whether history/profiles still bind them, emotional residue.",
            },
        ],
    },
]

DEMO2_GUIDE_FR: list[dict] = [
    {
        "section": "Le moment de l'abandon",
        "questions": [
            {
                "q": "Racontez-moi la dernière fois que vous avez arrêté de commander vos courses en ligne — que s'est-il passé ?",
                "learning": "L'événement déclencheur concret, son timing, et depuis combien de temps la décision couvait.",
            },
            {
                "q": "Qu'est-ce que l'enseigne aurait pu faire pour vous garder ?",
                "learning": "Réceptivité aux offres de rétention, demande de validation des substitutions, silence perçu au départ.",
            },
        ],
    },
    {
        "section": "Avec le recul",
        "questions": [
            {
                "q": "Que faudrait-il pour que vous y retourniez ?",
                "learning": "Conditions de retour, poids de l'historique/des listes, résidu émotionnel.",
            },
        ],
    },
]

DEMO_MEMO_NAME = "[Demo] Retention vs acquisition — decision memo"
DEMO_MEMO_NAME_FR = "[Démo] Fiabilité vs acquisition — mémo de décision"

DEMO_MEMO_QUESTION = (
    "Should next quarter's roadmap prioritise retention features (pause, "
    "cancel-flow, win-back) or acquisition content spend?"
)
DEMO_MEMO_QUESTION_FR = (
    "Faut-il investir la prochaine roadmap dans la fiabilité (stocks, "
    "substitutions, créneaux) ou dans l'acquisition promotionnelle ?"
)


def _study2_report(lang: str) -> dict:
    """Hand-authored v1 analysis for demo study #2 — quotes are verbatim
    substrings of PARTICIPANTS2 transcripts (enforced by tests)."""
    if lang == "fr":
        return {
            "summary": (
                "Trois entretiens de sortie racontent la même mécanique : "
                "l'abandon du drive ne vient pas d'une lassitude diffuse mais "
                "d'un incident précis — rupture massive, substitution ratée, "
                "hausse des frais — qui fait basculer une insatisfaction "
                "latente. L'historique (listes, panier type) retarde le départ "
                "de plusieurs mois, et aucune des trois n'a fait l'objet de la "
                "moindre tentative de rétention au moment de partir."
            ),
            "themes": [
                {
                    "title": "L'abandon suit un incident précis, pas une lassitude",
                    "summary": (
                        "Nadia (8 produits manquants sur 30), Julien (substitution "
                        "sur un produit de santé) et Marta (frais passés de 0 à 7 €) "
                        "datent tous leur départ d'un événement identifiable. "
                        "L'insatisfaction couvait, mais c'est l'incident qui décide."
                    ),
                    "quotes": [
                        _build_quote("La goutte d'eau, c'est la commande où il manquait huit produits sur trente.", "Nadia K.", 1),
                        _build_quote("Une substitution ratée sur le lait de mon fils, ça ne pardonne pas.", "Julien P.", 1),
                        _build_quote("C'était les frais qui montaient, tout simplement.", "Marta S.", 1),
                    ],
                    "frequency": "3 participants sur 3",
                    "disconfirming_evidence": "",
                },
                {
                    "title": "Les listes et l'historique retardent le départ de plusieurs mois",
                    "summary": (
                        "Julien est resté trois mois après l'incident déclencheur, "
                        "Nadia encaissait les déceptions — dans les deux cas parce "
                        "que recréer listes et panier type ailleurs coûte des "
                        "semaines. L'historique est l'actif de rétention réel, et "
                        "il est aujourd'hui non exportable et non valorisé."
                    ),
                    "quotes": [
                        _build_quote("ce qui m'a retenu si longtemps, c'est mes listes. Tout recréer ailleurs, c'est une soirée entière", "Julien P.", 1),
                        _build_quote("je restais parce que tout était configuré, mes listes, mon panier type du mercredi, deux ans d'habitudes", "Nadia K.", 1),
                    ],
                    "frequency": "2 participants sur 3",
                    "disconfirming_evidence": "Marta, petits paniers bimensuels, ne mentionne aucun attachement à un historique — le levier est absent du segment solo.",
                },
                {
                    "title": "Une sortie silencieuse : personne ne tente de retenir",
                    "summary": (
                        "Aucun des trois départs n'a déclenché la moindre réaction "
                        "de l'enseigne — pas d'offre, pas de mail, pas de question. "
                        "Nadia, elle-même logisticienne, souligne qu'un client "
                        "hebdomadaire qui s'arrête net devrait déclencher un appel."
                    ),
                    "quotes": [
                        _build_quote("personne n'a cherché à me retenir. Pas un mail, rien.", "Nadia K.", 2),
                    ],
                    "frequency": "3 participants sur 3",
                    "disconfirming_evidence": "",
                },
            ],
            "jobs_to_be_done": [
                {
                    "job": "Quand une commande tourne mal, je veux être prévenue et pouvoir arbitrer avant le retrait, pour ne pas découvrir le problème avec un enfant dans le siège auto.",
                    "insight": "Ce n'est pas l'incident qui fait partir, c'est de le subir sans préavis ni contrôle. La notification pré-retrait transforme un churn en simple déception.",
                    "frequency": "2 participants sur 3",
                },
            ],
            "tensions": [
                {
                    "tension": "Calcul froid vs rupture de confiance",
                    "detail": (
                        "Marta part sur un calcul (frais/panier) et reviendrait si "
                        "le calcul redevient bon ; Julien part sur une rupture de "
                        "confiance (le lait de son fils) et exige une preuve durable. "
                        "Les deux churns demandent des réponses opposées — tarifaire "
                        "pour l'un, produit pour l'autre."
                    ),
                },
            ],
            "recommendations": [
                _rec(
                    "Notifier ruptures et substitutions AVANT le retrait, avec arbitrage client ligne par ligne.",
                    "Le déclencheur n°1 des deux abandons famille.",
                    "Produit", "30d", "high", "medium",
                    "Taux d'abandon des clients notifiés vs non notifiés.",
                    "Serait invalidé si les clients notifiés churnaient autant que les non-notifiés.",
                ),
                _rec(
                    "Rendre les listes exportables et importables.",
                    "L'actif qui retient est aussi la barrière au retour.",
                    "Produit", "60_90d", "medium", "medium",
                    "Friction à la recréation des listes au retour.",
                    "Serait invalidé si les clients revenus recréent leurs listes sans friction mesurable.",
                ),
                _rec(
                    "Déclencher une rétention sur tout client hebdomadaire inactif depuis 3 semaines.",
                    "Aucun des trois départs n'a déclenché de tentative de rétention.",
                    "CRM", "now", "high", "low",
                    "Réactivation des contactés vs non-contactés.",
                    "Serait invalidé si le taux de réactivation des contactés n'excède pas celui des non-contactés.",
                ),
            ],
            "confidence": "medium",
            "confidence_rationale": "N=3 avec des récits précis et datés, mais un seul segment solo et aucune cliente encore active pour contraster.",
            "participant_count": 3,
        }

    return {
        "summary": (
            "Three exit interviews tell one mechanical story: cancellation is "
            "not a slow drift but a dated event — a price email landing in a "
            "dead content month, an annual budget review, a wage-driven "
            "trade-off. Accumulated watch history postpones the decision for "
            "months, and none of the three exits triggered any save attempt "
            "from the service."
        ),
        "themes": [
            {
                "title": "Cancellation is a dated event, not a drift",
                "summary": (
                    "Daniel cancelled the night a price email landed in the week "
                    "he'd finished his only show; Fatima the afternoon her budget "
                    "spreadsheet made the creeping price visible; Tom while the "
                    "kettle boiled after a two-euro increase. All three name the "
                    "date; none describes a gradual decision."
                ),
                "quotes": [
                    _build_quote("The price email landed the same week I finished the only thing I was watching. I cancelled that night.", "Daniel O.", 1),
                    _build_quote("It was the price going up, simple as.", "Tom W.", 1),
                ],
                "frequency": "3 of 3 participants",
                "disconfirming_evidence": "",
            },
            {
                "title": "Watch history postpones the exit for months",
                "summary": (
                    "Fatima delayed a cancellation she wanted for months because "
                    "the history 'felt like a diary'; Daniel says his tuned "
                    "recommendations were what kept him so long. The asset that "
                    "retains is invisible in the product and evaporates at exit."
                ),
                "quotes": [
                    _build_quote("I'd been meaning to cancel for months, but my watch history felt like a diary I didn't want to throw away.", "Fatima B.", 1),
                    _build_quote("What kept me so long was my profile honestly, the recommendations finally understood me", "Daniel O.", 1),
                ],
                "frequency": "2 of 3 participants",
                "disconfirming_evidence": "Tom, watching on a shared laptop with rotating logins, attaches no value to history at all — the lever may not exist for the youngest segment.",
            },
            {
                "title": "The exit is silent — nobody works the save",
                "summary": (
                    "None of the three cancellations triggered an offer, a pause "
                    "proposal, or even a targeted goodbye. Daniel — a sales "
                    "manager — was explicitly waiting for a save offer that never "
                    "came; Fatima notes win-back marketing will now cost more "
                    "than the discount that would have kept her."
                ),
                "quotes": [
                    _build_quote("Nobody asked me to stay. Not even a we're-sorry-to-see-you-go discount.", "Daniel O.", 2),
                    _build_quote("If they'd let me freeze it for the summer I'd still be a customer.", "Fatima B.", 2),
                ],
                "frequency": "3 of 3 participants",
                "disconfirming_evidence": "",
            },
        ],
        "jobs_to_be_done": [
            {
                "job": "When a service stops earning its fee, I want to step away without losing what I've built, so I can come back later without starting over.",
                "insight": "All three describe the exit as a break, not an ending — but the product only offers a binary cancel that destroys the accumulated value.",
                "frequency": "2 of 3 participants",
            },
        ],
        "tensions": [
            {
                "tension": "No hard feelings vs point of principle",
                "detail": (
                    "Tom leaves and returns purely on price and shows — 'no hard "
                    "feelings'. Daniel could afford the increase but cancelled on "
                    "principle the night the email mistimed. Price-led churn and "
                    "principle-led churn need different saves: a cheaper tier for "
                    "one, better timing and acknowledgement for the other."
                ),
            },
        ],
        "recommendations": [
            _rec(
                "Test a save offer at the cancel step (discount or pause).",
                "All three exits were silent and at least two were winnable.",
                "Growth", "30d", "high", "low",
                "Save-offer acceptance rate in an A/B test.",
                "Wrong if save-offer acceptance stays under 5% in an A/B test.",
            ),
            _rec(
                "Introduce a pause/step-down state that preserves history and profiles.",
                "The accumulated history is the asset that retains — and it evaporates at exit.",
                "Product", "60_90d", "high", "high",
                "Resume rate of paused accounts vs. cold win-backs.",
                "Wrong if paused accounts resume at no higher rate than cold win-backs.",
            ),
            _rec(
                "Never send price-increase emails into a subscriber's low-watch month.",
                "Sequence them after flagship releases instead.",
                "Growth", "now", "medium", "low",
                "Interaction between price-email timing and trailing watch time.",
                "Wrong if churn shows no interaction between price emails and trailing watch time.",
            ),
        ],
        "confidence": "medium",
        "confidence_rationale": "N=3 with precise, dated narratives, but all three are churned subscribers — no active-subscriber contrast group.",
        "participant_count": 3,
    }


def _memo_report(lang: str) -> dict:
    """Hand-authored cross-study decision memo. supporting_studies use the
    exact seeded study names; evidence quotes are verbatim transcript
    substrings from either study."""
    if lang == "fr":
        s1, s2 = DEMO_PROJECT_NAME_FR, DEMO2_PROJECT_NAME_FR
        return {
            "decision": DEMO_MEMO_QUESTION_FR,
            "verdict": (
                "Investir la roadmap dans la fiabilité. Les deux études convergent "
                "sur le même mécanisme : la fidélité tient à un actif accumulé "
                "(listes, historique, habitudes) et se rompt sur un incident "
                "opérationnel — jamais sur une offre concurrente mieux disante. "
                "La réserve principale : le segment des petits paniers (personnes "
                "seules) churne sur les frais, pas sur la fiabilité, et resterait "
                "mal servi par cet investissement."
            ),
            "summary": (
                "Sept entretiens sur deux études racontent une fidélité par inertie "
                "d'actifs : les clientes restent parce que tout est configuré, et "
                "partent quand un incident (rupture massive, substitution ratée) "
                "brise la confiance sans préavis ni contrôle. La validation des "
                "substitutions apparaît dans les deux études comme la demande la "
                "plus concrète et la moins servie du marché."
            ),
            "key_findings": [
                {
                    "finding": "L'incident opérationnel déclenche le départ ; le prix ne fait que le timer",
                    "detail": (
                        "L'étude de sortie date chaque abandon d'un incident précis "
                        "(ruptures, substitution) ; l'étude d'usage montre que les "
                        "ruptures érodent la confiance plus que les frais. Le prix "
                        "n'apparaît comme déclencheur que sur le segment solo."
                    ),
                    "supporting_studies": [s1, s2],
                    "evidence": "« La goutte d'eau, c'est la commande où il manquait huit produits sur trente. » (Entretiens de sortie — Nadia K.)",
                    "strength": "strong",
                },
                {
                    "finding": "Les listes et l'historique sont l'actif de rétention réel — et la barrière au retour",
                    "detail": (
                        "Les deux études indépendamment : le coût de switch invisible "
                        "verrouille la fidélité (étude d'usage) et retarde le départ "
                        "de plusieurs mois (étude de sortie). Le même actif, non "
                        "exportable, empêche ensuite les churnées de revenir."
                    ),
                    "supporting_studies": [s1, s2],
                    "evidence": "« ce qui m'a retenu si longtemps, c'est mes listes. Tout recréer ailleurs, c'est une soirée entière » (Entretiens de sortie — Julien P.)",
                    "strength": "strong",
                },
                {
                    "finding": "La validation des substitutions est le correctif le plus demandé des deux échantillons",
                    "detail": (
                        "Demande explicite et récurrente dans l'étude d'usage, cause "
                        "racine du churn famille dans l'étude de sortie. C'est une "
                        "fonctionnalité logicielle, pas un chantier logistique."
                    ),
                    "supporting_studies": [s1, s2],
                    "evidence": "« Me laisser valider les substitutions, tout simplement. » (Entretiens de sortie — Julien P.)",
                    "strength": "moderate",
                },
                {
                    "finding": "L'écart d'engagement est désormais chiffré : 4,5 points de recommandation",
                    "detail": (
                        "Le questionnaire (n=44) met des chiffres sur le schéma "
                        "des entretiens : les régulières notent leur enseigne "
                        "9,1 sur 10 en recommandation et 4,2 sur 5 en "
                        "qualité-prix ; les occasionnelles tombent à 4,6 et "
                        "2,4 à frais identiques. La moitié à risque de la "
                        "base est identifiable avant de partir."
                    ),
                    "supporting_studies": [s1],
                    "evidence": "Les occasionnelles notent leur enseigne 4,6 sur 10 en recommandation contre 9,1 pour les régulières — questionnaire de l'étude d'usage, n=44.",
                    "strength": "moderate",
                },
                {
                    "finding": "Carrefour Drive sert d'ancrage — la régularité et l'ancrage vont ensemble",
                    "detail": (
                        "Carrefour Drive apparaît dans 26 paniers sondés sur 44 "
                        "(59 %) et dans la totalité des paniers des régulières ; "
                        "aucune occasionnelle ne l'utilise. Le foyer moyen "
                        "combine 2 enseignes — la fidélité se joue sur "
                        "l'enseigne d'ancrage, le reste tourne."
                    ),
                    "supporting_studies": [s1],
                    "evidence": "Carrefour Drive apparaît dans 26 des 44 paniers sondés et dans la totalité des paniers des clientes régulières — questionnaire, n=44.",
                    "strength": "moderate",
                },
            ],
            "conflicts": [
                {
                    "topic": "Le rôle du prix",
                    "detail": (
                        "L'étude d'usage conclut que la sensibilité prix dépend du "
                        "profil (Romain compare au centime, Sophie paie la fiabilité) ; "
                        "l'étude de sortie ne trouve le prix comme déclencheur que "
                        "chez Marta (petits paniers). Réconciliation la plus plausible : "
                        "le prix segmente la clientèle mais ne déclenche l'abandon que "
                        "là où l'actif accumulé est faible."
                    ),
                },
                {
                    "topic": "La fidélité déclarée survivrait-elle à un incident ?",
                    "detail": (
                        "Le questionnaire lit 26 répondantes sur 44 comme des "
                        "promotrices installées ; mais toutes les clientes de "
                        "l'étude de sortie étaient d'anciennes régulières. "
                        "Réconciliation la plus plausible : la recommandation "
                        "mesure la satisfaction du moment, pas la résilience à "
                        "l'incident — une promotrice churne aussi quand une "
                        "commande tourne mal sans préavis."
                    ),
                },
            ],
            "gaps": [
                "Aucune cliente encore active et satisfaite dans l'étude de sortie — le contraste churn/rétention repose sur deux échantillons différents.",
                "Le segment personnes seules / petits paniers n'est représenté que par une participante.",
                "L'économie du win-back (coût de reconquête vs coût de rétention) n'est chiffrée dans aucune des deux études.",
            ],
            "recommendations": [
                "Livrer la validation des substitutions avant tout investissement promo — demande n°1 des deux études. Serait invalidé si l'usage de la fonctionnalité restait marginal chez les clientes à risque.",
                "Notifier ruptures et incidents avant le retrait — transforme le déclencheur de churn en simple déception. Serait invalidé si les clientes notifiées churnaient autant.",
                "Étudier une offre petits paniers avant de conclure que la fiabilité suffit — le segment solo churne sur les frais. Serait invalidé si le churn solo restait stable après un tarif adapté.",
            ],
            "confidence": "medium",
            "confidence_rationale": "Deux études qualitatives convergentes (7 entretiens au total) et un questionnaire de 44 réponses ; confiances individuelles élevée et moyenne, mais aucune donnée longitudinale ne relie l'intention déclarée au churn observé.",
        }

    s1, s2 = DEMO_PROJECT_NAME, DEMO2_PROJECT_NAME
    return {
        "decision": DEMO_MEMO_QUESTION,
        "verdict": (
            "Prioritise retention features. Both studies independently surface "
            "the same mechanism — subscribers are held by accumulated value "
            "(history, profiles, tuned recommendations) and lost at a mistimed "
            "price event — and every element of that mechanism is within product "
            "control, unlike acquisition content whose effect ends with each "
            "finale. Biggest caveat: the youngest, login-sharing segment attaches "
            "no value to history, so retention features won't move that cohort."
        ),
        "summary": (
            "Seven interviews across two studies converge: streaming loyalty is "
            "rented, not owned. Subscribers rotate around shows, stay for "
            "accumulated history, and churn decisively when a price email lands "
            "in a low-watch month. All three exits in the cancellation study were "
            "silent — no save offer, no pause, no goodbye — and a pause state is "
            "the single most requested missing feature in both samples."
        ),
        "key_findings": [
            {
                "finding": "A pause state would intercept decisive cancellations",
                "detail": (
                    "The usage study surfaced pause as the top unmet need (named "
                    "or implied by 3 of 4); in the exit study, two of three "
                    "churned subscribers state unprompted that a freeze would "
                    "have kept them. The demand exists on both sides of the "
                    "cancel event."
                ),
                "supporting_studies": [s1, s2],
                "evidence": "\"If they'd let me freeze it for the summer I'd still be a customer.\" (Exit interviews — Fatima B.)",
                "strength": "strong",
            },
            {
                "finding": "Price emails set the timing of churn, not its cause",
                "detail": (
                    "Both studies find price increases to be the dominant trigger "
                    "— but only when they land in a dead content month. The cause "
                    "is accumulated low usage; the email merely dates the decision."
                ),
                "supporting_studies": [s1, s2],
                "evidence": "\"The price email landed the same week I finished the only thing I was watching. I cancelled that night.\" (Exit interviews — Daniel O.)",
                "strength": "strong",
            },
            {
                "finding": "Watch history is the invisible retention asset",
                "detail": (
                    "The usage study's most loyal behaviour and the exit study's "
                    "longest-postponed cancellations share one driver: years of "
                    "watch history and tuned recommendations that would be lost. "
                    "The product neither surfaces this value nor preserves it at exit."
                ),
                "supporting_studies": [s1, s2],
                "evidence": "\"I'd been meaning to cancel for months, but my watch history felt like a diary I didn't want to throw away.\" (Exit interviews — Fatima B.)",
                "strength": "moderate",
            },
            {
                "finding": "The engagement split is now quantified: a 5-point NPS gap",
                "detail": (
                    "The five-question survey (n=44) puts numbers on the "
                    "interview pattern: heavy streamers average 9.1 on the "
                    "0–10 recommendation scale and 4.2 of 5 on value-for-money; "
                    "light streamers average 4.1 and 2.4 at identical prices. "
                    "The at-risk half of the base is identifiable before it "
                    "churns."
                ),
                "supporting_studies": [s1],
                "evidence": "Light streamers average 4.1 of 10 on recommendation against 9.1 for heavy streamers — usage-study survey, n=44.",
                "strength": "moderate",
            },
            {
                "finding": "The anchor slot is locked; churn happens in the rotating slot",
                "detail": (
                    "Netflix appears in 38 of 44 surveyed household stacks "
                    "(86%) while the average stack holds two services. The "
                    "retention battle is over the rotating second slot — "
                    "which is where every cancellation in the exit study "
                    "took place."
                ),
                "supporting_studies": [s1, s2],
                "evidence": "Netflix anchors 38 of 44 surveyed households; the observed cancellations all hit the rotating, non-anchor slot.",
                "strength": "moderate",
            },
        ],
        "conflicts": [
            {
                "topic": "Does the catalogue retain?",
                "detail": (
                    "The usage study concludes loyalty lives at the catalogue "
                    "(exclusives, curation); yet in the exit interviews, nobody "
                    "cites catalogue at the moment of cancelling — only price "
                    "events and silence. Most plausible reconciliation: catalogue "
                    "sets the level of willingness to pay, while operational "
                    "moments (price emails, dead months) set the timing of churn. "
                    "Both matter, but only the second is being mismanaged."
                ),
            },
            {
                "topic": "How big is the loyal segment?",
                "detail": (
                    "The survey reads 26 of 44 respondents (59%) as heavy, "
                    "promoter-grade streamers — a majority-loyal base. The "
                    "interviews, including the exit study, describe even "
                    "engaged subscribers as rotating renters. Most plausible "
                    "reconciliation: heavy usage predicts advocacy, not "
                    "immunity — promoters still cancel when a price email "
                    "lands in a dead month."
                ),
            },
        ],
        "gaps": [
            "No never-subscribers in either sample — acquisition questions are only answered from the subscriber side.",
            "Single-market pricing context per participant; bundle-heavy telco markets are unrepresented.",
            "Win-back economics (cost of re-acquiring a silent churner vs cost of a save offer) are unquantified in both studies.",
        ],
        "recommendations": [
            "Ship a pause state (2-3 months, history and profiles frozen) before the next price change. Would be wrong if paused accounts resume at no higher rate than cold win-backs.",
            "Sequence price increases to land within two weeks of a flagship release, never in dead months. Would be wrong if churn cohorts show no interaction between price emails and trailing watch time.",
            "Add a save step to the cancel flow (pause proposal or targeted offer) — every observed exit was silent. Would be wrong if save acceptance stays under 5% in an A/B test.",
        ],
        "confidence": "medium",
        "confidence_rationale": "Two converging qualitative studies (7 interviews total) plus a 44-response survey; individual confidences high and medium, but no longitudinal churn data ties stated intent to observed behaviour.",
    }


def _seed_second_demo_study(db: Session, company_id: str, lang: str, now: datetime):
    """Seed the exit-interview sibling study (3 participants, 1 ready analysis).

    Returns the created Study. Leaner than the flagship demo on purpose —
    its job is to make the cross-study memo demoable, not to duplicate the
    full researcher-workflow showcase.
    """
    if lang == "fr":
        name = DEMO2_PROJECT_NAME_FR
        objective = DEMO2_OBJECTIVE_FR
        welcome = DEMO2_WELCOME_FR
        guide = DEMO2_GUIDE_FR
        participants_data = PARTICIPANTS2_FR
        quality_map = QUALITY2_FR
        quality_keys = ["nadia", "julien", "marta"]
    else:
        name = DEMO2_PROJECT_NAME
        objective = DEMO2_OBJECTIVE
        welcome = DEMO2_WELCOME
        guide = DEMO2_GUIDE
        participants_data = PARTICIPANTS2_EN
        quality_map = QUALITY2_EN
        quality_keys = ["daniel", "fatima", "tom"]

    study = create_study(db, company_id, name)
    project = Project(
        company_id=company_id,
        study_id=study.id,
        name=name,
        language=lang,
        interview_duration_minutes=15,
        welcome_message=welcome,
        research_objective=objective,
        is_demo=True,
        created_at=now - timedelta(days=6),
    )
    db.add(project)
    db.flush()

    sort_order = 0
    for section_index, section in enumerate(guide):
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

    link = InterviewLink(
        project_id=project.id,
        token=secrets.token_urlsafe(32),
        is_active=True,
        created_at=now - timedelta(days=6),
    )
    db.add(link)
    db.flush()

    for i, data in enumerate(participants_data):
        started = now - timedelta(days=5 - i)
        q = quality_map.get(quality_keys[i], {})
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
            completed_at=started + timedelta(minutes=14),
            quality_score=q.get("quality_score", 0.75),
            quality_label=q.get("quality_label", "good"),
            quality_summary=q.get("quality_summary"),
            quality_strengths=json.dumps(q["quality_strengths"]) if "quality_strengths" in q else None,
            quality_issues=json.dumps(q["quality_issues"]) if "quality_issues" in q else None,
            avg_response_words=q.get("avg_response_words"),
            short_answer_pct=q.get("short_answer_pct"),
        )
        db.add(participant)
        db.flush()
        for t_idx, turn in enumerate(data["turns"]):
            db.add(
                InterviewTurn(
                    participant_id=participant.id,
                    turn_index=t_idx,
                    question_index=max(0, int(turn.get("question_index", 1)) - 1),
                    is_follow_up=bool(turn.get("is_follow_up", False)),
                    follow_up_index=0,
                    question_text=turn["question_text"],
                    response_transcript=turn["response_transcript"],
                    created_at=started + timedelta(minutes=t_idx * 3),
                )
            )

    db.add(
        ProjectAnalysis(
            project_id=project.id,
            version=1,
            version_label="ai_discovery",
            status="ready",
            participant_count=len(participants_data),
            report=json.dumps(_study2_report(lang)),
            generated_at=now - timedelta(days=2),
            created_at=now - timedelta(days=2),
        )
    )
    db.flush()
    return study
