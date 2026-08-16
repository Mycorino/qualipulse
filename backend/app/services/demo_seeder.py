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
import uuid
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
from app.models.survey import (
    Survey,
    SurveyLink,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.services._demo_data_en import (
    NOTABLE_QUOTES_EN,
    PARTICIPANTS_EN,
    QUALITY_EN,
)
from app.services._demo_data_fr import (
    NOTABLE_QUOTES_FR,
    PARTICIPANTS_FR,
    QUALITY_FR,
)
from app.services.study_provisioning import create_study


DEMO_PROJECT_NAME = "[Demo] How people choose streaming services"
DEMO_PROJECT_NAME_FR = "[Démo] Courses alimentaires en ligne : habitudes & freins"
# Pre-August-2026 accounts were seeded with an em dash in the FR name; the
# backfill script still needs to recognise them.
LEGACY_DEMO_PROJECT_NAME_FR = "[Démo] Courses alimentaires en ligne — habitudes & freins"

# Participant-facing researcher identity for the demo study, so the branding
# preview and the interview consent card demonstrate the filled-in state.
DEMO_RESEARCHER_NAME = "Consumer Insights Team"
DEMO_RESEARCHER_NAME_FR = "Équipe Études Conso"

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
    "explore the platform with realistic data. It contains ten completed "
    "interviews about how people choose between video streaming services, "
    "a 44-respondent survey using every question type, a mixed-methods "
    "Decision report, a finished AI analysis with two versions, a "
    "researcher codebook, tagged quotes, and project memos. Feel free to "
    "edit anything, archive it, or delete it whenever you're ready to run "
    "your own study — it never counts against your project quota."
)
DEMO_RESEARCH_CONTEXT_FR = (
    "Ceci est un projet de démo que QualiPulse a créé automatiquement pour "
    "que vous puissiez explorer la plateforme avec des données réalistes. "
    "Il contient dix entretiens sur les habitudes de courses alimentaires "
    "en ligne, un sondage de 44 répondants utilisant tous les types de "
    "questions, un rapport de décision mixte, une analyse IA avec deux "
    "versions, un codebook chercheur, des verbatims taggés et des mémos. "
    "Modifiez, archivez ou supprimez quand vous voulez — ce projet ne "
    "compte pas dans votre quota."
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
                "notes": (
                    "Open broad, then anchor on the most recent real decision: "
                    "the last service they added or dropped, and why that week. "
                    "Probe who in the household actually decides. If price comes "
                    "up, get the real monthly figure — don't accept 'it depends'."
                ),
                "researcher": (
                    "Hypothesis from support tickets: subscription decisions are "
                    "household negotiations, not individual picks. Watch for who "
                    "owns the decision."
                ),
            },
        ],
    },
    {
        "section": "Experience",
        "questions": [
            {
                "q": "Walk me through your experience signing up for a new service and what those first few weeks felt like.",
                "learning": "Sign-up friction, content discovery, time-to-value, cancellation flow perception.",
                "notes": (
                    "Keep them in story mode — one named service, one specific "
                    "first week. Probe the first evening: how long until they "
                    "found something to watch? If cancellation comes up "
                    "spontaneously, follow that thread before returning to "
                    "onboarding."
                ),
                "researcher": (
                    "Funnel data shows a drop at profile creation — listen for "
                    "anything that corroborates or kills that."
                ),
            },
        ],
    },
    {
        "section": "Loyalty",
        "questions": [
            {
                "q": "What makes you stay loyal to a service, versus jumping between them?",
                "learning": "Retention drivers, churn triggers, exclusive-content lock-in, price-increase tolerance.",
                "notes": (
                    "Separate loyalty from inertia: ask what would have to "
                    "happen for them to cancel this month. Test price tolerance "
                    "concretely (one more price rise — stay or go?). Note "
                    "whether exclusive titles are named spontaneously; never "
                    "prompt with examples."
                ),
                "researcher": (
                    "Feeds the Q3 pricing review. If price tolerance clusters "
                    "by usage, we segment the offer rather than the price."
                ),
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
                "notes": (
                    "Faites raconter le vrai premier déclencheur (naissance, "
                    "déménagement, télétravail…) plutôt qu'une explication "
                    "générale. Creusez le canal d'entrée : qui leur a montré, "
                    "quelle enseigne en premier, et pourquoi celle-là."
                ),
                "researcher": (
                    "Hypothèse de l'équipe growth : l'entrée se fait par le "
                    "Drive, pas par la livraison. À confirmer ou infirmer."
                ),
            },
        ],
    },
    {
        "section": "Expérience",
        "questions": [
            {
                "q": "Racontez-moi votre dernière expérience de courses en ligne, du moment où vous remplissez le panier jusqu'à ce que vous récupériez les produits. Qu'est-ce qui s'est bien passé, qu'est-ce qui était galère ?",
                "learning": "Frictions de panier, ruptures de stock, qualité produits, livraison vs Drive, service après-vente.",
                "notes": (
                    "Une commande précise — la dernière, pas une moyenne. "
                    "Déroulez chronologiquement : panier, créneau, "
                    "retrait/livraison, après-vente. Aux ruptures de stock, "
                    "demandez ce qu'ils ont fait concrètement (substitution "
                    "acceptée ? passage en magasin ?)."
                ),
                "researcher": (
                    "Les tickets SAV pointent les substitutions imposées comme "
                    "irritant n°1 — vérifier si ça sort spontanément."
                ),
            },
        ],
    },
    {
        "section": "Confiance et retour",
        "questions": [
            {
                "q": "Qu'est-ce qui vous fait revenir vers le même service plutôt que d'en tester un autre ? Et qu'est-ce qui pourrait vous faire abandonner ?",
                "learning": "Moteurs de fidélité, coût de switch, sensibilité prix, seuils de tolérance qualité.",
                "notes": (
                    "Distinguez fidélité et habitude : que devrait-il se passer "
                    "ce mois-ci pour qu'ils changent d'enseigne ? Faites "
                    "estimer le coût de switch perçu (listes, historique, "
                    "habitudes). Ne suggérez pas de seuils — laissez-les "
                    "venir."
                ),
                "researcher": (
                    "Alimente l'arbitrage fiabilité vs acquisition du prochain "
                    "trimestre."
                ),
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


# The researcher codebook is user-visible content — localized like the rest
# of the seed (an EN codebook inside an otherwise fully-French demo was the
# one EN leak in the FR path).
DEMO_CODES_EN = [
    {"name": "Trust signal", "color": "#16a34a"},
    {"name": "Friction", "color": "#dc2626"},
    {"name": "Price concern", "color": "#f59e0b"},
]

DEMO_CODES_FR = [
    {"name": "Signal de confiance", "color": "#16a34a"},
    {"name": "Friction", "color": "#dc2626"},
    {"name": "Sensibilité prix", "color": "#f59e0b"},
]


# Per-language tag plans: list of (notable_quote_index, code_name).
# All three codes are exercised in both languages so the codebook panel
# showcases a worked example, not a half-used one.
DEMO_TAG_PLAN_EN: list[tuple[int, str]] = [
    (0, "Trust signal"),    # Priya — "let me have a pause button" (retention idea)
    (1, "Friction"),        # Priya — dark patterns on cancellation
    (2, "Trust signal"),    # Marcus — exclusive content as loyalty driver
    (3, "Trust signal"),    # Alex — service with a point of view (curation)
    (6, "Friction"),        # Tom — six screens and two guilt trips to cancel NOW
    (10, "Price concern"),  # Victor — price-increase email puts the service on trial
]

DEMO_TAG_PLAN_FR: list[tuple[int, str]] = [
    (0, "Friction"),            # Camille — coût caché du switch
    (1, "Friction"),            # Camille — ruptures, "ils ont jamais tout"
    (2, "Sensibilité prix"),    # Romain — Leclerc moins cher du marché
    (3, "Signal de confiance"), # Sophie — fiabilité de Coop
    (7, "Friction"),            # Fatou — rupture sur le lait du petit
    (9, "Sensibilité prix"),    # Marc — septante euros + frais de livraison
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
                "Sur dix entretiens menés en France, en Belgique et en Suisse, "
                "un schéma clair se dessine : la fidélité aux services de courses "
                "alimentaires en ligne tient moins au prix qu'à un coût de switch "
                "invisible (historique, listes, panier type) et à la fiabilité "
                "perçue. La friction la plus citée est la rupture de stock, qui "
                "érode la confiance plus que les frais de service. Les profils "
                "les plus engagés formulent des demandes de fonctionnalités très "
                "concrètes (validation de substitutions, notifications proactives) "
                "qui restent largement non couvertes par les enseignes. Un "
                "contre-profil existe : les petits paniers (Julien) n'ont rien à "
                "reconstruire et basculent à cinq pour cent d'écart de prix."
            ),
            "themes": [
                {
                    "title": "Le coût de switch invisible verrouille la fidélité",
                    "summary": (
                        "Sept participants sur dix décrivent leur fidélité à "
                        "un service comme un effet d'inertie lié à l'historique "
                        "stocké : panier type, listes, marques préférées. Changer "
                        "d'enseigne, ce serait reconstruire des semaines de "
                        "configuration — « repartir de zéro », dit Élodie. Ce "
                        "coût n'est pas tarifé, ne sort pas dans les enquêtes "
                        "prix, mais il pèse plus que les écarts de tarif sur la "
                        "décision. Il disparaît chez les petits paniers, qui "
                        "n'ont rien à reconstruire."
                    ),
                    "quotes": [q(0), q(11), q(5)],
                    "frequency": "7 participants sur 10",
                },
                {
                    "title": "Les ruptures de stock érodent la confiance plus que les frais",
                    "summary": (
                        "La frustration la plus citée n'est pas le prix de la "
                        "livraison ou du service mais le sentiment que les Drives "
                        "sont sous-stockés : 'ils ont jamais tout'. Sur un produit "
                        "sensible (le lait infantile de Fatou), la rupture n'est "
                        "plus un désagrément mais une rupture de confiance. Une "
                        "fonctionnalité de validation des substitutions à "
                        "l'avance résoudrait presque entièrement le problème "
                        "mais aucune enseigne ne la propose."
                    ),
                    "quotes": [q(1), q(4), q(7)],
                    "frequency": "6 participants sur 10",
                },
                {
                    "title": "La sensibilité prix dépend du profil, pas du service",
                    "summary": (
                        "Romain (famille de cinq) compare au centime près et "
                        "reste chez Leclerc parce que c'est le moins cher ; "
                        "Julien changerait d'enseigne pour cinq pour cent "
                        "d'écart ; Fatou surveille le total à l'euro près. À "
                        "l'autre extrême, Sophie et Anaïs (Genève) paient "
                        "volontiers la fiabilité et la qualité du frais. Les "
                        "enseignes qui se positionnent uniquement sur le prix "
                        "captent un segment, pas le marché."
                    ),
                    "quotes": [q(2), q(6), q(8)],
                    "frequency": "5 participants sur 10",
                },
            ],
            "jobs_to_be_done": [
                {
                    "job": "Quand je commande mes courses chaque semaine, je veux gagner du temps sans sacrifier la qualité, pour rendre du temps aux activités qui comptent vraiment.",
                    "insight": "Le gain de temps est la motivation racine, jamais le prix. Les services qui font perdre du temps (ruptures, retards) sont punis plus fort que ceux qui sont chers.",
                    "frequency": "9 participants sur 10",
                },
                {
                    "job": "Quand je change quelque chose dans ma vie (enfants, déménagement), je veux que mon service de courses s'adapte sans que je doive tout reconfigurer.",
                    "insight": "Le moment du changement de vie est aussi le moment où l'on change de service. C'est là que la concurrence peut gagner ou perdre.",
                    "frequency": "4 participants sur 10",
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
                    "grounded_in": ["Camille D.", "Nadia T.", "Élodie R."],
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
                    "grounded_in": ["Romain B.", "Julien P.", "Fatou D."],
                    "one_liner": "Compare au centime et choisit l'enseigne la moins chère.",
                    "segment": "Budgets serrés, paniers surveillés",
                    "goals": ["Minimiser le coût du panier"],
                    "frustrations": ["Écarts de prix entre enseignes", "Frais de livraison"],
                    "behaviours": ["Compare les prix avant de commander"],
                    "primary_job": "Nourrir le foyer au meilleur prix.",
                    "anchor_quote": {"text": q(2)["text"], "participant_identifier": "Romain B."},
                },
                {
                    "name": "L'Exigeante de la fiabilité",
                    "grounded_in": ["Sophie L.", "Élodie R.", "Anaïs G."],
                    "one_liner": "Paie plus cher sans hésiter tant que le créneau et la qualité tiennent.",
                    "segment": "Organisation millimétrée, qualité d'abord",
                    "goals": ["Un créneau qui ne saute jamais", "Du frais qui tient la semaine"],
                    "frustrations": ["Créneaux annulés", "Frais choisi n'importe comment"],
                    "behaviours": ["Reste des années chez l'enseigne qui livre à l'heure"],
                    "primary_job": "Pouvoir bâtir la semaine sur une livraison fiable.",
                    "anchor_quote": {"text": q(3)["text"], "participant_identifier": "Sophie L."},
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
                     "quote": {"text": q(11)["text"], "participant_identifier": "Élodie R."},
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
            "participant_count": 10,
        }

    # English (streaming) report
    notable = NOTABLE_QUOTES_EN
    participants = PARTICIPANTS_EN

    def q(i: int) -> dict:
        n = notable[i]
        return _build_quote(n["text"], participants[n["participant_index"]]["display_name"], n["turn_index"])

    return {
        "summary": (
            "Across ten interviews in the UK, Ireland, the US, Canada, and "
            "Australia, a consistent pattern emerges: streaming subscribers "
            "behave less like loyal customers and more like rotating "
            "renters. Loyalty is driven by exclusive content and "
            "recommendation quality, not by brand affinity. The biggest "
            "unmet need is a 'pause' state between active and cancelled — "
            "seven of ten participants named or implied it, from Dana's "
            "school-calendar Disney+ cycle to Yuki's explicit 'pause "
            "instead of cancel'. Cancellation friction is widely noticed "
            "and actively damages re-acquisition. Price increases are the "
            "single most common trigger for churn re-evaluation."
        ),
        "themes": [
            {
                "title": "Subscribers want a pause state, not a binary on/off",
                "summary": (
                    "Seven of ten participants described cycling in and out "
                    "of services around specific shows or seasons. The "
                    "current subscribe/cancel binary makes leaving feel "
                    "like a bigger decision than it is, which paradoxically "
                    "increases churn because users cancel decisively rather "
                    "than going dormant. A pause feature was named "
                    "explicitly by two participants (Priya, Yuki) and the "
                    "behaviour it would serve — seasonal or show-driven "
                    "cycling — was described by five more."
                ),
                "quotes": [q(0), q(5), q(4)],
                "frequency": "7 of 10 participants",
            },
            {
                "title": "Cancellation friction is a re-acquisition tax",
                "summary": (
                    "Participants notice and remember cancellation dark "
                    "patterns. The friction doesn't prevent the cancellation "
                    "— it just makes them less likely to come back later. "
                    "This is a particularly costly trade-off given the "
                    "cyclical subscribe-cancel-resubscribe behaviour the "
                    "data reveals: Victor's 'starting from scratch like a "
                    "stranger' captures how re-signup friction compounds "
                    "the original cancellation friction."
                ),
                "quotes": [q(1), q(6), q(7)],
                "frequency": "5 of 10 participants",
            },
            {
                "title": "Loyalty lives at the catalogue, not at the brand",
                "summary": (
                    "Subscribers stay for either exclusive content (NFL "
                    "Sunday Ticket, Premier League football, Marvel/Star "
                    "Wars) or for a service that has a clear editorial "
                    "point of view (Netflix's deep recommendation history, "
                    "Criterion's curation). Generic catalogues blur "
                    "together and lose the moment the headliner show ends "
                    "— Grace's forty minutes of scrolling that ends in a "
                    "rewatch is what an undifferentiated catalogue feels "
                    "like from the inside."
                ),
                "quotes": [q(2), q(3), q(8), q(9)],
                "frequency": "6 of 10 participants",
            },
        ],
        "jobs_to_be_done": [
            {
                "job": "When I want to watch a specific show, I want to subscribe quickly, watch, and leave without feeling guilty, so I can match my spending to my actual viewing.",
                "insight": "Show-driven subscribers are the modal pattern, not the exception. Services that fight this behaviour with retention friction lose them as future returnees.",
                "frequency": "7 of 10 participants",
            },
            {
                "job": "When a service raises my price, I want a moment to evaluate whether it's still worth it, so I don't keep paying out of inertia for something I don't use.",
                "insight": "Price-increase emails are the single most common cancellation trigger — even when the service is still worth what users are paying. Timing the increase right after a flagship release lands could meaningfully reduce churn.",
                "frequency": "6 of 10 participants",
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
                "The most-requested unmet need — seven of ten cycle in and out around shows.",
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
                "grounded_in": ["Priya R.", "Marcus T.", "Dana W.", "Grace A."],
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
                "grounded_in": ["Alex K.", "Marcus T.", "Yuki N."],
                "one_liner": "Stays for a clear point of view or exclusive content, not a generic catalogue.",
                "segment": "Taste- and exclusivity-driven",
                "goals": ["A service with a distinct identity"],
                "frustrations": ["Interchangeable catalogues"],
                "behaviours": ["Leaves when the headliner ends"],
                "primary_job": "Find things worth watching that nobody else has.",
                "anchor_quote": {"text": q(3)["text"], "participant_identifier": "Alex K."},
            },
            {
                "name": "The Bill Auditor",
                "grounded_in": ["Victor M.", "Tom O.", "Sam B."],
                "one_liner": "Tolerates the stack until a price-increase email forces a reckoning.",
                "segment": "Household budget owners",
                "goals": ["Keep the total bill defensible"],
                "frustrations": ["Creeping price increases", "Managing many logins"],
                "behaviours": ["Re-evaluates everything when one price moves"],
                "primary_job": "Pay for what the household actually watches, nothing more.",
                "anchor_quote": {"text": q(10)["text"], "participant_identifier": "Victor M."},
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
                 "quote": {"text": q(10)["text"], "participant_identifier": "Victor M."},
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
        "participant_count": 10,
    }


def _v2_report(lang: str) -> dict:
    base = _v1_report(lang)
    if lang == "fr":
        base["summary"] = (
            "Analyse affinée après revue chercheur. Le coût de switch invisible "
            "est confirmé comme le moteur principal de fidélité — c'est l'angle "
            "qui mérite le plus d'investissement produit. La friction des "
            "ruptures de stock est très actionnable et devrait être la priorité "
            "court terme : six participants sur dix l'ont mentionnée et "
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
            "implied by seven of ten participants — ship it. The "
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
            "Confirmed across seven of ten interviews. Priya and Yuki named "
            "it explicitly; Marcus, Alex, Dana, Grace and Victor all "
            "described the subscribe-cancel-resubscribe cycle it would "
            "solve. This is the strongest retention idea in the dataset — "
            "worth prototyping with the product team before the next "
            "planning round."
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
            "Confirmé sur sept entretiens sur dix. Camille, Nadia et "
            "Élodie le formulent presque mot pour mot ; Romain, Sophie, "
            "Fatou et Anaïs l'impliquent. C'est la mécanique de rétention la plus "
            "puissante du dataset et celle qu'on a le moins activée côté "
            "produit. À tester avec l'équipe produit avant la prochaine "
            "roadmap."
        ),
    },
    {
        "theme_title": "La sensibilité prix dépend du profil, pas du service",
        "status": "needs_evidence",
        "researcher_note": (
            "Schéma de segmentation net — cinq entretiens sur dix — mais "
            "concentré sur des profils qui commandent déjà. Il faudrait "
            "3-4 entretiens supplémentaires sur des segments à plus "
            "faible revenu avant d'en faire une recommandation forte. Le "
            "profil non-utilisateur (Léa) ne nous renseigne pas vraiment "
            "sur ce segment."
        ),
    },
]


DEMO_MEMOS_EN = [
    {
        "type": "general",
        "linked_key": None,
        "content": (
            "First pass through the streaming-services data. The pause-state "
            "finding is the strongest signal — seven of ten participants "
            "either explicitly asked for it (Priya, Yuki) or described the "
            "behaviour it would solve (Marcus, Alex, Dana, Grace, Victor). "
            "Worth flagging to product before the next quarterly planning "
            "round."
        ),
    },
    {
        "type": "theme_note",
        "linked_key": "Cancellation friction is a re-acquisition tax",
        "content": (
            "Priya's line about NOW — 'I'm more reluctant to resubscribe "
            "[...] because I remember how annoying leaving was' — is the "
            "most quotable on this theme, and Tom describes the same "
            "hesitation. The behavioural insight is that the friction tax "
            "falls on re-acquisition, not on retention. Worth modelling "
            "lifetime value with and without simplified cancellation."
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
            "switch invisible est le signal le plus net : sept "
            "participants sur dix le décrivent presque dans les mêmes "
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


# ── Hybrid demo: a full quantitative survey + Decision report ───────────────
#
# The demo Study ships with an interview track *and* a survey, so a new user
# lands on a genuine mixed-methods Study — the instrument-mix badge reads
# "Hybrid" and the Report tab has a real Decision report — not an
# interview-only project. The survey content is mono-language like the rest
# of the seed, and the instrument deliberately exercises EVERY question type
# the product supports (mc_single, mc_multi, likert 5-pt, likert 7-pt with a
# reverse-coded item, nps, open_text, short_text) so the demo doubles as a
# showcase of the survey builder. All report copy is hand-authored (same
# approach as the ProjectAnalysis reports above) so seeding never makes an
# AI call.

DEMO_SURVEY_NAME = "Streaming habits: quick pulse"
DEMO_SURVEY_NAME_FR = "Courses en ligne : sondage éclair"

# Pre-August-2026 accounts were seeded with em dashes in the survey names;
# the backfill script still needs to recognise them.
LEGACY_DEMO_SURVEY_NAME = "Streaming habits — quick pulse"
LEGACY_DEMO_SURVEY_NAME_FR = "Courses en ligne — sondage éclair"

# Per-language survey plan — a ten-question instrument that uses every
# question type the product supports: frequency (mc_single), current stack
# (mc_multi), stack size (mc_single), a three-item 5-point likert battery
# (value-for-money, price-rise tolerance, and a reverse-coded friction item),
# a 7-point satisfaction likert, recommendation (NPS 0–10), an open
# churn-trigger question (open_text) and a forced-choice "keep one"
# (short_text).
#
# `questions` defines the instrument; `cohorts` defines who answers what.
# Each cohort carries a per-question answer plan that is cycled over the
# cohort's `count` responses (None = respondent skipped the question). The
# `services` and `stack_size` plans share a cycle length so each simulated
# respondent's stack count matches their stated stack size. The
# distributions are chosen so the hand-authored survey signals in
# `_survey_signals` quote numbers the analytics layer actually reproduces
# (as rendered, one decimal):
#   EN — heavy NPS mean 9.2 / light 4.1; value 4.2 vs 2.4; price-rise
#        cancel-intent 2.2 vs 4.4; satisfaction 6.2 vs 3.2; Netflix in
#        38/44 stacks and 17/26 "keep one" answers.
#   FR — régulières NPS 9,2 / occasionnelles 4,6 ; qualité-prix 4,2 vs 2,4 ;
#        intention d'arrêt sur hausse 2,2 vs 4,4 ; satisfaction 6,2 vs 3,2 ;
#        Carrefour Drive dans 26/44 paniers et 10/26 réponses « à garder ».
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
            "key": "stack_size", "type": "mc_single",
            "prompt": "How many paid streaming services does your household pay for right now?",
            "config": {"choices": [
                {"id": "one", "label": "Just one"},
                {"id": "two", "label": "Two"},
                {"id": "three", "label": "Three"},
                {"id": "four_plus", "label": "Four or more"},
            ], "randomize": False, "has_other": False},
        },
        {
            "key": "value", "type": "likert",
            "prompt": "The catalogue on my main service is worth what I pay for it.",
            "config": {"scale": 5, "anchors": ["Strongly disagree", "Strongly agree"],
                       "reverse_coded": False},
        },
        {
            "key": "price_rise", "type": "likert",
            "prompt": "If my main service raised its price again this year, I would cancel.",
            "config": {"scale": 5, "anchors": ["Strongly disagree", "Strongly agree"],
                       "reverse_coded": False},
        },
        {
            "key": "browse", "type": "likert",
            "prompt": "I often scroll for a long time without finding anything I actually want to watch.",
            "config": {"scale": 5, "anchors": ["Strongly disagree", "Strongly agree"],
                       "reverse_coded": True},
        },
        {
            "key": "satisfaction", "type": "likert",
            "prompt": "Overall, how satisfied are you with your main streaming service?",
            "config": {"scale": 7, "anchors": ["Very dissatisfied", "Very satisfied"],
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
        {
            "key": "must_keep", "type": "short_text",
            "prompt": "If you could only keep one streaming service, which one would it be?",
            "config": {"max_chars": 60},
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
                # Same cycle length as `services` so each respondent's stated
                # stack size matches the stack they ticked above.
                "stack_size": ["three", "two", "three", "two"],
                "value": [5, 4, 4, 5, 4, 3],
                "price_rise": [2, 3, 2, 1, 3, 2],
                "browse": [2, 3, 2, 4, 2],
                "satisfaction": [6, 7, 6, 5, 7, 6],
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
                # Full-length like `churn` — a short_text answer is optional,
                # so the skips (None) keep the sample believable.
                "must_keep": [
                    "Netflix", None, "Netflix", "Disney+", None, "Netflix",
                    "HBO Max", None, "Netflix", None, "Netflix", "Disney+",
                    None, "Netflix", None, "Prime Video", "Netflix", None,
                    "Netflix", "Disney+", None, "Netflix", None, "Netflix",
                    "HBO Max", None,
                ],
            },
        },
        {
            "id": "light", "count": 18,
            "answers": {
                "freq": ["weekly", "monthly", "weekly"],
                "services": [["netflix"], ["prime"], ["netflix", "prime"]],
                "stack_size": ["one", "one", "two"],
                "value": [2, 3, 2, 3, 2],
                "price_rise": [5, 4, 5, 4, 4],
                "browse": [4, 4, 5, 3, 4],
                "satisfaction": [3, 4, 2, 4, 3],
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
                "must_keep": [
                    "Netflix", None, "Prime Video", "Netflix", None,
                    "Netflix", None, "Prime Video", None, "Netflix", None,
                    "Netflix", "Prime Video", None, "Netflix", None, None,
                    "Netflix",
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
            "key": "stack_size", "type": "mc_single",
            "prompt": "Combien d'enseignes différentes utilisez-vous régulièrement pour vos courses en ligne ?",
            "config": {"choices": [
                {"id": "une", "label": "Une seule"},
                {"id": "deux", "label": "Deux"},
                {"id": "trois", "label": "Trois"},
                {"id": "quatre_plus", "label": "Quatre ou plus"},
            ], "randomize": False, "has_other": False},
        },
        {
            "key": "value", "type": "likert",
            "prompt": "Le service de mon enseigne principale vaut ce qu'il me coûte.",
            "config": {"scale": 5, "anchors": ["Pas du tout d'accord", "Tout à fait d'accord"],
                       "reverse_coded": False},
        },
        {
            "key": "price_rise", "type": "likert",
            "prompt": "Si les frais de service ou de livraison augmentaient encore, j'arrêterais les courses en ligne.",
            "config": {"scale": 5, "anchors": ["Pas du tout d'accord", "Tout à fait d'accord"],
                       "reverse_coded": False},
        },
        {
            "key": "browse", "type": "likert",
            "prompt": "Je dois souvent compléter ma commande en magasin à cause des produits manquants.",
            "config": {"scale": 5, "anchors": ["Pas du tout d'accord", "Tout à fait d'accord"],
                       "reverse_coded": True},
        },
        {
            "key": "satisfaction", "type": "likert",
            "prompt": "Globalement, quelle est votre satisfaction vis-à-vis de votre enseigne principale ?",
            "config": {"scale": 7, "anchors": ["Très insatisfait·e", "Très satisfait·e"],
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
        {
            "key": "must_keep", "type": "short_text",
            "prompt": "Si vous ne deviez garder qu'une seule enseigne de courses en ligne, laquelle ?",
            "config": {"max_chars": 60},
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
                # Même longueur de cycle que `services` : la taille de stack
                # déclarée colle aux enseignes cochées par la même répondante.
                "stack_size": ["deux", "deux", "trois", "une"],
                "value": [5, 4, 4, 5, 4, 3],
                "price_rise": [2, 3, 2, 1, 3, 2],
                "browse": [3, 2, 4, 3, 2],
                "satisfaction": [6, 7, 6, 5, 7, 6],
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
                # Full-length comme `churn` — réponse facultative, les None
                # gardent l'échantillon crédible.
                "must_keep": [
                    "Carrefour Drive", None, "Carrefour Drive", "Picard", None,
                    "Carrefour Drive", "Leclerc Drive", None, "Carrefour Drive",
                    None, "Carrefour Drive", "Picard", None, "Carrefour Drive",
                    None, "Carrefour Drive", "Amazon Fresh", None,
                    "Carrefour Drive", "Picard", None, "Carrefour Drive", None,
                    "Carrefour Drive", "Leclerc Drive", None,
                ],
            },
        },
        {
            "id": "occasionnelles", "count": 18,
            "answers": {
                "freq": ["une_fois", "moins", "une_fois"],
                "services": [["leclerc"], ["amazon"], ["leclerc", "coop"]],
                "stack_size": ["une", "une", "deux"],
                "value": [2, 3, 2, 3, 2],
                "price_rise": [5, 4, 5, 4, 4],
                "browse": [4, 5, 4, 3, 5],
                "satisfaction": [3, 4, 2, 4, 3],
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
                "must_keep": [
                    "Leclerc Drive", None, "Amazon Fresh", "Leclerc Drive",
                    None, "Leclerc Drive", None, "Amazon Fresh", None,
                    "Leclerc Drive", None, "Leclerc Drive", "Coop@home", None,
                    "Leclerc Drive", None, None, "Leclerc Drive",
                ],
            },
        },
    ],
}


def _survey_signals(lang: str) -> list[str]:
    """The four hand-authored survey-signal summaries the Decision report keys
    to qualitative themes.

    Order: [0] recommendation gap, [1] value-tracks-usage, [2] anchor service,
    [3] open churn triggers. Every number is reproduced exactly by the
    analytics layer from the seeded cohort plans above — if you change a plan,
    re-derive these figures (means shown as the analytics layer rounds them,
    one decimal).
    """
    if lang == "fr":
        return [
            (
                "Les occasionnelles notent leur enseigne 4,6 sur l'échelle de "
                "recommandation 0–10 contre 9,2 pour les régulières — un écart "
                "de plus de quatre points sur la même question (n=44)."
            ),
            (
                "L'accord qualité-prix suit la fréquence d'usage : 4,2 sur 5 "
                "chez les régulières contre 2,4 chez les occasionnelles — "
                "l'item de satisfaction en 7 points dessine le même écart "
                "(6,2 contre 3,2)."
            ),
            (
                "Carrefour Drive apparaît dans 26 des 44 paniers (59 %) et "
                "reste l'enseigne que 10 répondantes sur 26 garderaient s'il "
                "ne fallait en garder qu'une."
            ),
            (
                "Dans les réponses libres « qu'est-ce qui vous ferait "
                "abandonner ? » (18 réponses sur 44), les ruptures de stock et "
                "les substitutions imposées dominent chez les régulières ; les "
                "frais ne mènent que chez les occasionnelles."
            ),
        ]
    return [
        (
            "Light streamers score their main service 4.1 on the 0–10 "
            "recommendation scale against 9.2 for heavy streamers — a "
            "five-point split on the same question (n=44)."
        ),
        (
            "Catalogue-value agreement follows usage: 4.2 out of 5 among "
            "heavy streamers vs 2.4 among light — and the 7-point "
            "satisfaction item shows the same shape (6.2 vs 3.2)."
        ),
        (
            "Netflix appears in 38 of 44 household stacks (86%) and is the "
            "one service 17 of 26 respondents would keep if forced to choose "
            "just one."
        ),
        (
            "In the open \u201cwhat would make you cancel?\u201d answers (18 of 44 "
            "answered), finishing a show and planned resubscription dominate "
            "among light streamers; price alone leads only when paired with a "
            "dead catalogue month."
        ),
    ]



def _decision_integration(lang: str) -> dict:
    """Hand-authored ``decision_v1`` integration layer for the demo Study.

    This is what a real "generate analysis" now produces (approach B): the
    interview themes come from the refined ``ProjectAnalysis`` (``_v2_report``),
    the survey charts from the seeded dashboards, and THIS layer keys each survey
    signal to a qualitative theme + states the verdict and the open gaps. So the
    demo's ``report.html`` renders the canonical Decision-report superset on
    first login, not the legacy Quantified-Themes document.

    The survey-signal strings come from :func:`_survey_signals`, the single
    source of truth for the demo's survey numbers, so the joint display can
    never drift from the charts above it. ``theme_title`` values are copied
    verbatim from ``_v2_report`` so the joint display lines up with the
    interview themes the reader just read.
    """
    # [NPS/recommendation gap, value-tracks-usage, anchor service, churn trigger]
    sig = _survey_signals(lang)

    if lang == "fr":
        return {
            "schema": "decision_v1",
            "verdict": (
                "Investir d'abord sur l'expérience de rupture de stock "
                "(validation des substitutions à l'avance) plutôt que sur le "
                "prix : c'est la friction la plus citée chez les détractrices, "
                "le premier motif d'abandon dans les réponses libres, et le "
                "seul levier corroboré par les deux méthodes. Réserve : le coût "
                "de switch n'est pas encore chiffré — le sondage de suivi doit "
                "précéder tout investissement lourd."
            ),
            "confidence": "supported",
            "joint_display": [
                {
                    "theme_title": "Le coût de switch invisible verrouille la fidélité",
                    "survey_signal": sig[2],
                    "confidence": "supported",
                    "counter_evidence": (
                        "Leclerc Drive ancre déjà 12 des 18 paniers "
                        "occasionnels — l'ancrage peut refléter l'offre locale "
                        "autant qu'une fidélité construite."
                    ),
                },
                {
                    "theme_title": "Les ruptures de stock érodent la confiance plus que les frais",
                    "survey_signal": sig[0],
                    "confidence": "supported",
                    "counter_evidence": (
                        "Un entretien sur dix (profil petit panier) relativise : "
                        "quand la commande fait quinze produits, il n'y a rien à "
                        "reconstruire et une rupture se rattrape en magasin."
                    ),
                },
                {
                    "theme_title": "La sensibilité prix dépend du profil, pas du service",
                    "survey_signal": sig[1],
                    "confidence": "directional",
                    "counter_evidence": (
                        "Le questionnaire ne distingue pas « je paie trop cher » "
                        "de « je n'utilise pas assez » — l'écart peut refléter la "
                        "fréquence d'usage."
                    ),
                },
            ],
            "gaps": [
                "Le coût de switch (temps de reconstruction des listes et de "
                "l'historique) n'est pas encore chiffré — impossible de fixer un "
                "seuil de bascule.",
                "Le questionnaire et les entretiens couvrent la même population "
                "mais pas la même fenêtre temporelle.",
                "Aucune donnée sur l'efficacité réelle d'une validation des "
                "substitutions — à tester avant tout déploiement.",
            ],
        }

    return {
        "schema": "decision_v1",
        "verdict": (
            "Ship a pause state before touching price: a planned, show-driven "
            "cancellation is the dominant churn trigger in the open responses, "
            "the recommendation gap between light and heavy streamers is the "
            "clearest quantitative signal, and it's the one lever both methods "
            "corroborate. Caveat: the cost of re-acquiring a lapsed subscriber "
            "isn't yet quantified — the follow-up survey should precede any "
            "heavy build."
        ),
        "confidence": "supported",
        "joint_display": [
            {
                "theme_title": "Subscribers want a pause state, not a binary on/off",
                "survey_signal": sig[3],
                "confidence": "supported",
                "counter_evidence": (
                    "The survey can't tell a genuine pause-seeker from someone "
                    "who would have churned anyway — intent isn't behaviour."
                ),
            },
            {
                "theme_title": "Cancellation friction is a re-acquisition tax",
                "survey_signal": sig[0],
                "confidence": "supported",
                "counter_evidence": (
                    "Two of ten interviewees barely track their subscriptions "
                    "at all (“my card just gets charged”) — friction may be "
                    "invisible to the least engaged segment."
                ),
            },
            {
                "theme_title": "Loyalty lives at the catalogue, not at the brand",
                "survey_signal": sig[2],
                "confidence": "directional",
                "counter_evidence": (
                    "Netflix anchors 12 of 18 light-streamer stacks too — "
                    "anchoring may reflect market ubiquity rather than earned "
                    "loyalty."
                ),
            },
        ],
        "gaps": [
            "The cost of re-acquiring a lapsed subscriber vs. the cost of a "
            "pause save-offer is unmeasured — we can't price the trade-off yet.",
            "Survey and interviews cover the same population but not the same "
            "time window.",
            "No evidence on how well a pause state actually retains — needs an "
            "A/B before any heavy build.",
        ],
    }


def _seed_demo_survey(
    db: Session, study: Study, company_id: str, lang: str, now: datetime
) -> Survey:
    """Add a published eight-question survey with 44 completed responses to the
    demo Study, so the Study reads as a true hybrid (survey + interviews)."""
    cfg = DEMO_SURVEY_FR if lang == "fr" else DEMO_SURVEY_EN
    fielding_start = now - timedelta(days=9)
    fielding_end = now - timedelta(days=2)

    survey = Survey(
        id=str(uuid.uuid4()),
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

    question_by_key: dict[str, SurveyQuestion] = {}
    for i, q_plan in enumerate(cfg["questions"]):
        question = SurveyQuestion(
            id=str(uuid.uuid4()),
            survey_id=survey.id,
            sort_order=i,
            type=q_plan["type"],
            prompt=q_plan["prompt"],
            is_required=q_plan["type"] not in ("open_text", "short_text"),
            config=json.dumps(q_plan.get("config") or {}),
        )
        db.add(question)
        question_by_key[q_plan["key"]] = question

    link = SurveyLink(
        id=str(uuid.uuid4()),
        survey_id=survey.id,
        token=secrets.token_urlsafe(32),
        is_active=True,
        is_anonymous=False,
        created_at=now - timedelta(days=10),
    )
    db.add(link)

    n = 0
    for cohort in cfg["cohorts"]:
        answers = cohort["answers"]
        for i in range(cohort["count"]):
            n += 1
            started = fielding_start + timedelta(hours=n * 3)
            # Client-side id so answers can reference the response without a
            # per-row flush — with 44 responses the round-trips to a remote
            # Postgres were the bulk of prod seeding time.
            response = SurveyResponse(
                id=str(uuid.uuid4()),
                survey_id=survey.id,
                company_id=company_id,
                link_id=link.id,
                started_at=started,
                completed_at=started + timedelta(minutes=4),
            )
            db.add(response)
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
        demo_researcher_name = DEMO_RESEARCHER_NAME_FR
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
        demo_codes = DEMO_CODES_FR
        quality_keys = [
            "camille", "romain", "lea", "sophie",
            "nadia", "julien", "fatou", "marc", "elodie", "anais",
        ]
        researcher_context = (
            "Revue de la v1 avec l'équipe. Coût de switch = l'asset à "
            "défendre. La friction des ruptures de stock est le fix immédiat. "
            "La sensibilité prix demande plus de données avant d'investir."
        )
    else:
        demo_name = DEMO_PROJECT_NAME
        demo_researcher_name = DEMO_RESEARCHER_NAME
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
        demo_codes = DEMO_CODES_EN
        quality_keys = [
            "priya", "marcus", "jen", "alex",
            "dana", "tom", "yuki", "sam", "grace", "victor",
        ]
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
        # Match the ten seeded interviews so the plan reads consistently, and
        # fill the researcher identity so the branding preview shows the
        # participant-facing state rather than an empty form.
        target_participants=10,
        researcher_name=demo_researcher_name,
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
                    interview_notes=item.get("notes", ""),
                    desired_learning=item["learning"],
                    researcher_notes=item.get("researcher"),
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
    for idx, c in enumerate(demo_codes):
        code = ManualCode(
            id=str(uuid.uuid4()),
            project_id=project.id,
            name=c["name"],
            color=c["color"],
            sort_order=idx,
        )
        db.add(code)
        code_by_name[c["name"]] = code

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
        # Client-side ids for the participant and turns so the whole cast can
        # be inserted without per-participant flushes (see the survey seeder).
        participant = Participant(
            id=str(uuid.uuid4()),
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

        turns: list[InterviewTurn] = []
        for t_idx, turn in enumerate(data["turns"]):
            q_idx_zero_based = max(0, int(turn.get("question_index", 1)) - 1)
            interview_turn = InterviewTurn(
                id=str(uuid.uuid4()),
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
        return participant, turns

    seeded_participants: list[tuple[Participant, list[InterviewTurn]]] = []
    for i, p_data in enumerate(participants_data):
        q_key = quality_keys[i] if i < len(quality_keys) else None
        # Ten interviews spread across the fieldwork window (9 → 2.25 days
        # ago) — every participant completes BEFORE the analyses below are
        # "generated", so the version history stays chronologically honest.
        result = add_participant(
            p_data,
            days_ago=9 - i * 0.75,
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

    # Analysis v1 — ai_discovery. Generated after the last interview
    # (2.25 days ago) so the version history postdates all the data it cites.
    v1 = ProjectAnalysis(
        project_id=project.id,
        version=1,
        version_label="ai_discovery",
        status="ready",
        participant_count=10,
        report=json.dumps(_v1_report(lang)),
        share_token=secrets.token_urlsafe(32),
        generated_at=now - timedelta(days=1.5),
        created_at=now - timedelta(days=1.5),
    )
    db.add(v1)
    db.flush()

    # Analysis v2 — researcher_refined
    v2 = ProjectAnalysis(
        project_id=project.id,
        version=2,
        version_label="researcher_refined",
        status="ready",
        participant_count=10,
        report=json.dumps(_v2_report(lang)),
        parent_version_id=v1.id,
        researcher_context=researcher_context,
        generated_at=now - timedelta(days=0.75),
        created_at=now - timedelta(days=0.75),
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
            # decision_v1: the canonical Decision-report superset. report.html
            # composes the qual themes from the ProjectAnalysis above + the
            # survey charts + this integration layer (verdict/joint display/gaps).
            report=json.dumps(_decision_integration(lang)),
            generated_at=now - timedelta(hours=6),
            created_at=now - timedelta(hours=6),
        )
    )

    db.commit()
    db.refresh(project)
    return project
