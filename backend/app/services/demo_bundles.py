"""Demo-bundle fixtures for the /welcome sample-study modal.

The modal used to render i18n template strings dressed up as themes /
quotes / a guide. That's an architectural smell — the "what a study
looks like" surface should match the real product surface.

This module is the first step: backend-served structured bundles that
match the shape of a real ProjectAnalysis + QuoteTag + GuideQuestion
graph. The frontend consumes them through one endpoint and renders
with what is *closer* to the real components. Three industry variants
per locale (EN/FR), routed by ``services/website_intelligence`` /
``Welcome.tsx::pickSampleVariant``.

Follow-up: extract Synthesis / Quotes / Guide subviews from
ProjectDetail.tsx, then render the bundle through THOSE — at that
point the modal becomes a literal mini-version of the real product
surface, automatically improving as ProjectDetail improves.
"""

from __future__ import annotations

from typing import Literal, TypedDict


Variant = Literal["saas", "b2b_specifier", "consumer"]


class _Theme(TypedDict):
    title: str
    finding: str
    quote: str
    speaker: str


class _Quote(TypedDict):
    speaker: str
    text: str
    highlight: str
    code: str
    code_color: str


class _Example(TypedDict):
    name: str
    objective: str
    q1_section: str
    q1_question: str
    q2_section: str
    q2_question: str
    q3_section: str
    q3_question: str


class DemoBundle(TypedDict):
    variant: Variant
    locale: str
    n_participants: int
    completed_label: str
    example: _Example
    themes: list[_Theme]
    quotes: list[_Quote]


_BUNDLES: dict[Variant, dict[str, DemoBundle]] = {
    "saas": {
        "en": {
            "variant": "saas",
            "locale": "en",
            "n_participants": 25,
            "completed_label": "Completed last week",
            "example": {
                "name": "Why new signups never run their first interview",
                "objective": "Understand what stops trial users from launching their first study so we know which onboarding friction to fix first.",
                "q1_section": "CONTEXT",
                "q1_question": "Walk me through what you were trying to do the first time you logged in.",
                "q2_section": "MOMENT OF DROP-OFF",
                "q2_question": "Was there a moment you thought \"this isn't for me right now\"? Tell me about it.",
                "q3_section": "WHAT WOULD HAVE HELPED",
                "q3_question": "If you could have skipped one step, which one would it have been?",
            },
            "themes": [
                {
                    "title": "\"I didn't know who I'd interview\"",
                    "finding": "12 of 25 stalled before launching because they hadn't lined up participants. They expected the tool to find people for them.",
                    "quote": "I assumed there'd be a panel I could just send it to. When I realised I had to bring my own list, I closed the tab.",
                    "speaker": "Maya, PM at a 40-person SaaS",
                },
                {
                    "title": "The first study felt high-stakes",
                    "finding": "Trial users described the first study as \"my one shot.\" They over-edited the question guide and never sent it.",
                    "quote": "I rewrote those five questions seven times. I was sure I was going to waste my participants' time.",
                    "speaker": "Jonas, founder, B2B fintech",
                },
                {
                    "title": "Voice felt risky without seeing the output",
                    "finding": "Users who didn't see a sample transcript before launching were 3x more likely to abandon. The AI felt opaque.",
                    "quote": "I didn't know what the AI would actually do once people started talking. I needed to see one finished interview before trusting it.",
                    "speaker": "Lina, UX researcher at a marketplace",
                },
            ],
            "quotes": [
                {
                    "speaker": "Maya, PM",
                    "text": "I assumed there'd be a panel I could just send it to. When I realised I had to bring my own list, I closed the tab.",
                    "highlight": "I had to bring my own list",
                    "code": "Participant-sourcing gap",
                    "code_color": "#4f46e5",
                },
                {
                    "speaker": "Jonas, founder",
                    "text": "I rewrote those five questions seven times. I was sure I was going to waste my participants' time.",
                    "highlight": "I was sure I was going to waste my participants' time",
                    "code": "First-study anxiety",
                    "code_color": "#0ea5e9",
                },
                {
                    "speaker": "Lina, researcher",
                    "text": "I needed to see one finished interview before trusting it. The AI felt like a black box.",
                    "highlight": "see one finished interview before trusting it",
                    "code": "Transparency requirement",
                    "code_color": "#10b981",
                },
            ],
        },
        "fr": {
            "variant": "saas",
            "locale": "fr",
            "n_participants": 25,
            "completed_label": "Terminée la semaine dernière",
            "example": {
                "name": "Pourquoi les nouveaux inscrits ne lancent jamais leur premier entretien",
                "objective": "Comprendre ce qui empêche les utilisateurs en essai de lancer leur première étude, pour savoir quel frein d'onboarding traiter en priorité.",
                "q1_section": "CONTEXTE",
                "q1_question": "Racontez-moi ce que vous essayiez de faire la première fois que vous vous êtes connecté·e.",
                "q2_section": "MOMENT D'ABANDON",
                "q2_question": "Y a-t-il eu un moment où vous vous êtes dit « ce n'est pas pour moi maintenant » ? Parlez-moi de ça.",
                "q3_section": "CE QUI AURAIT AIDÉ",
                "q3_question": "Si vous aviez pu sauter une étape, laquelle ?",
            },
            "themes": [
                {
                    "title": "« Je ne savais pas qui interviewer »",
                    "finding": "12 sur 25 ont calé avant de lancer car ils n'avaient pas de participants. Ils s'attendaient à ce que l'outil les trouve pour eux.",
                    "quote": "Je pensais qu'il y aurait un panel à qui je pouvais juste l'envoyer. Quand j'ai compris qu'il fallait amener ma propre liste, j'ai fermé l'onglet.",
                    "speaker": "Maya, PM dans une SaaS de 40 personnes",
                },
                {
                    "title": "La première étude semblait à enjeu",
                    "finding": "Les utilisateurs en essai décrivaient la première étude comme « leur seule chance ». Ils sur-éditaient le guide et ne l'envoyaient jamais.",
                    "quote": "J'ai réécrit ces cinq questions sept fois. J'étais sûr que j'allais faire perdre du temps aux participants.",
                    "speaker": "Jonas, fondateur, fintech B2B",
                },
                {
                    "title": "Le vocal semblait risqué sans voir le rendu",
                    "finding": "Les utilisateurs qui n'avaient pas vu un exemple de transcription avant de lancer abandonnaient 3 fois plus. L'IA semblait opaque.",
                    "quote": "Je ne savais pas ce que l'IA allait vraiment faire une fois que les gens commenceraient à parler. Il me fallait voir un entretien fini avant de lui faire confiance.",
                    "speaker": "Lina, UX researcher dans une marketplace",
                },
            ],
            "quotes": [
                {
                    "speaker": "Maya, PM",
                    "text": "Je pensais qu'il y aurait un panel à qui je pouvais juste l'envoyer. Quand j'ai compris qu'il fallait amener ma propre liste, j'ai fermé l'onglet.",
                    "highlight": "il fallait amener ma propre liste",
                    "code": "Sourcing participants",
                    "code_color": "#4f46e5",
                },
                {
                    "speaker": "Jonas, fondateur",
                    "text": "J'ai réécrit ces cinq questions sept fois. J'étais sûr que j'allais faire perdre du temps aux participants.",
                    "highlight": "j'allais faire perdre du temps aux participants",
                    "code": "Anxiété première étude",
                    "code_color": "#0ea5e9",
                },
                {
                    "speaker": "Lina, researcher",
                    "text": "Il me fallait voir un entretien fini avant de lui faire confiance. L'IA semblait être une boîte noire.",
                    "highlight": "voir un entretien fini avant de lui faire confiance",
                    "code": "Exigence de transparence",
                    "code_color": "#10b981",
                },
            ],
        },
    },
    "b2b_specifier": {
        "en": {
            "variant": "b2b_specifier",
            "locale": "en",
            "n_participants": 22,
            "completed_label": "Completed 3 weeks ago",
            "example": {
                "name": "Why architects pick one specification database over another",
                "objective": "Understand the moment architects choose which product database to trust for a project, so we know which credibility signals matter most.",
                "q1_section": "CONTEXT",
                "q1_question": "Walk me through the last project where you had to specify a product you hadn't used before. What was the trigger?",
                "q2_section": "DECISION MOMENT",
                "q2_question": "What made you trust one source over another when comparing options? Tell me about a specific moment.",
                "q3_section": "WHAT BREAKS THE CHOICE",
                "q3_question": "When have you walked away from a product you'd otherwise have specified? Why?",
            },
            "themes": [
                {
                    "title": "Reference projects beat brochures every time",
                    "finding": "18 of 22 architects said a built example near their site weighed more than any technical sheet — but only 2 said brands made finding one easy.",
                    "quote": "If I can't find a project like mine where it's already been installed, I move on. I'm not the first person to test it on a client.",
                    "speaker": "Anne, architect, mid-sized firm",
                },
                {
                    "title": "BIM-ready or it doesn't get specified",
                    "finding": "If the BIM object wasn't downloadable in under a minute, the product dropped out of the shortlist. Brand recognition didn't save it.",
                    "quote": "I'm not going to model it myself. If their Revit file isn't there, I pick the competitor whose file is.",
                    "speaker": "Marc, BIM coordinator, design-build firm",
                },
                {
                    "title": "The client's compliance officer has veto power",
                    "finding": "Architects pre-filter for certifications because the legal/compliance team will kill the spec late if missing. They route around products that look risky.",
                    "quote": "I learned the hard way — picked the better product, compliance threw it out at month four. Now I sort by certification first.",
                    "speaker": "Sophie, architect, public-sector work",
                },
            ],
            "quotes": [
                {
                    "speaker": "Anne, architect",
                    "text": "If I can't find a project like mine where it's already been installed, I move on. I'm not the first person to test it on a client.",
                    "highlight": "I'm not the first person to test it on a client",
                    "code": "Reference-project gating",
                    "code_color": "#4f46e5",
                },
                {
                    "speaker": "Marc, BIM coordinator",
                    "text": "I'm not going to model it myself. If their Revit file isn't there, I pick the competitor whose file is.",
                    "highlight": "I pick the competitor whose file is",
                    "code": "BIM availability",
                    "code_color": "#0ea5e9",
                },
                {
                    "speaker": "Sophie, architect",
                    "text": "I learned the hard way — picked the better product, compliance threw it out at month four. Now I sort by certification first.",
                    "highlight": "Now I sort by certification first",
                    "code": "Compliance pre-filter",
                    "code_color": "#10b981",
                },
            ],
        },
        "fr": {
            "variant": "b2b_specifier",
            "locale": "fr",
            "n_participants": 22,
            "completed_label": "Terminée il y a 3 semaines",
            "example": {
                "name": "Pourquoi les architectes choisissent une base de spécifications plutôt qu'une autre",
                "objective": "Comprendre le moment où l'architecte choisit la base produit en laquelle il a confiance, pour savoir quels signaux de crédibilité comptent vraiment.",
                "q1_section": "CONTEXTE",
                "q1_question": "Racontez-moi le dernier projet où vous avez dû spécifier un produit que vous ne connaissiez pas. Qu'est-ce qui a déclenché ?",
                "q2_section": "MOMENT DE DÉCISION",
                "q2_question": "Qu'est-ce qui vous a fait préférer une source plutôt qu'une autre en comparant ? Parlez-moi d'un moment précis.",
                "q3_section": "CE QUI CASSE LE CHOIX",
                "q3_question": "Quand avez-vous abandonné un produit que vous auriez sinon spécifié ? Pourquoi ?",
            },
            "themes": [
                {
                    "title": "Les références projets battent les brochures",
                    "finding": "18 architectes sur 22 ont dit qu'un exemple bâti près de leur site comptait plus que toute fiche technique — mais seulement 2 ont trouvé ça facile à dénicher.",
                    "quote": "Si je ne trouve pas un projet comme le mien où ça a déjà été installé, je passe. Je ne suis pas là pour tester un produit sur un client.",
                    "speaker": "Anne, architecte, cabinet mid-size",
                },
                {
                    "title": "BIM-ready ou pas spécifié",
                    "finding": "Si l'objet BIM ne se téléchargeait pas en moins d'une minute, le produit sortait du shortlist. La notoriété de la marque ne le sauvait pas.",
                    "quote": "Je ne vais pas le modéliser moi-même. Si leur fichier Revit n'y est pas, je prends le concurrent dont le fichier y est.",
                    "speaker": "Marc, BIM coordinator, agence design-build",
                },
                {
                    "title": "Le service conformité du client a un droit de veto",
                    "finding": "Les architectes pré-filtrent sur les certifications parce que le service juridique tuera la spec en fin de course si manquant. Ils contournent les produits qui semblent risqués.",
                    "quote": "J'ai appris à mes dépens — choisi le meilleur produit, la conformité l'a sorti au quatrième mois. Maintenant je trie par certification d'abord.",
                    "speaker": "Sophie, architecte, marchés publics",
                },
            ],
            "quotes": [
                {
                    "speaker": "Anne, architecte",
                    "text": "Si je ne trouve pas un projet comme le mien où ça a déjà été installé, je passe. Je ne suis pas là pour tester un produit sur un client.",
                    "highlight": "tester un produit sur un client",
                    "code": "Filtrage par référence",
                    "code_color": "#4f46e5",
                },
                {
                    "speaker": "Marc, BIM coordinator",
                    "text": "Je ne vais pas le modéliser moi-même. Si leur fichier Revit n'y est pas, je prends le concurrent dont le fichier y est.",
                    "highlight": "je prends le concurrent dont le fichier y est",
                    "code": "Disponibilité BIM",
                    "code_color": "#0ea5e9",
                },
                {
                    "speaker": "Sophie, architecte",
                    "text": "J'ai appris à mes dépens — choisi le meilleur produit, la conformité l'a sorti au quatrième mois. Maintenant je trie par certification d'abord.",
                    "highlight": "je trie par certification d'abord",
                    "code": "Pré-filtrage conformité",
                    "code_color": "#10b981",
                },
            ],
        },
    },
    "consumer": {
        "en": {
            "variant": "consumer",
            "locale": "en",
            "n_participants": 28,
            "completed_label": "Completed 2 weeks ago",
            "example": {
                "name": "Why first-time buyers abandon the cart at shipping",
                "objective": "Understand what tips buyers from \"interested\" to \"forget it\" in the last 60 seconds of checkout, so we know which friction to remove first.",
                "q1_section": "CONTEXT",
                "q1_question": "Tell me about the last time you put something in a cart and didn't buy it. What were you trying to do?",
                "q2_section": "THE TIPPING POINT",
                "q2_question": "What was the exact moment you thought \"actually, no\"? Walk me through it.",
                "q3_section": "WHAT WOULD HAVE WORKED",
                "q3_question": "If they'd done one thing differently, would you have bought? Which thing?",
            },
            "themes": [
                {
                    "title": "Shipping cost surprise is the killer, not the amount",
                    "finding": "16 of 28 abandoned not because shipping was high, but because it appeared only at the final step. Even €4.99 felt like a trap when revealed late.",
                    "quote": "It wasn't the five euros. It was that I'd spent ten minutes choosing and they'd been hiding it from me the whole time.",
                    "speaker": "Élise, urban professional, monthly online shopper",
                },
                {
                    "title": "Account creation = exit",
                    "finding": "Forced account creation at checkout closed the tab for 10 of 28 — half explicitly said \"I'll come back later,\" and none did.",
                    "quote": "Why do I need an account to buy a t-shirt? I came to spend money, not to sign up for a relationship.",
                    "speaker": "Tom, occasional buyer",
                },
                {
                    "title": "Trust collapses without familiar payment options",
                    "finding": "Buyers expected Apple Pay / PayPal as escape hatches when the brand was new to them. Missing them = perceived sketchiness, not just inconvenience.",
                    "quote": "I'd never heard of them. If they don't take PayPal I assume my card info goes who-knows-where.",
                    "speaker": "Camille, first-time buyer from social ad",
                },
            ],
            "quotes": [
                {
                    "speaker": "Élise, shopper",
                    "text": "It wasn't the five euros. It was that I'd spent ten minutes choosing and they'd been hiding it from me the whole time.",
                    "highlight": "they'd been hiding it from me the whole time",
                    "code": "Late-reveal trust break",
                    "code_color": "#4f46e5",
                },
                {
                    "speaker": "Tom, buyer",
                    "text": "Why do I need an account to buy a t-shirt? I came to spend money, not to sign up for a relationship.",
                    "highlight": "not to sign up for a relationship",
                    "code": "Forced-account friction",
                    "code_color": "#0ea5e9",
                },
                {
                    "speaker": "Camille, first-time buyer",
                    "text": "I'd never heard of them. If they don't take PayPal I assume my card info goes who-knows-where.",
                    "highlight": "my card info goes who-knows-where",
                    "code": "Trust signal: payment options",
                    "code_color": "#10b981",
                },
            ],
        },
        "fr": {
            "variant": "consumer",
            "locale": "fr",
            "n_participants": 28,
            "completed_label": "Terminée il y a 2 semaines",
            "example": {
                "name": "Pourquoi les nouveaux acheteurs abandonnent leur panier aux frais de port",
                "objective": "Comprendre ce qui fait basculer l'acheteur de « intéressé » à « tant pis » dans les 60 dernières secondes du checkout, pour savoir quel frein retirer en premier.",
                "q1_section": "CONTEXTE",
                "q1_question": "Racontez-moi la dernière fois que vous avez mis quelque chose dans un panier sans acheter. Qu'est-ce que vous cherchiez à faire ?",
                "q2_section": "LE MOMENT DE BASCULE",
                "q2_question": "À quel moment exact vous êtes-vous dit « en fait, non » ? Décrivez-moi la scène.",
                "q3_section": "CE QUI AURAIT MARCHÉ",
                "q3_question": "S'ils avaient fait une chose différemment, vous auriez acheté ? Laquelle ?",
            },
            "themes": [
                {
                    "title": "La surprise sur les frais de port, pas le montant",
                    "finding": "16 sur 28 ont abandonné non pas parce que les frais étaient élevés, mais parce qu'ils n'apparaissaient qu'à l'étape finale. Même 4,99 € semblait un piège quand révélé tard.",
                    "quote": "C'était pas les cinq euros. C'est que j'avais passé dix minutes à choisir et ils me l'avaient caché tout du long.",
                    "speaker": "Élise, jeune active, acheteuse en ligne mensuelle",
                },
                {
                    "title": "Création de compte = fermeture d'onglet",
                    "finding": "La création de compte forcée au checkout a fait fermer l'onglet à 10 sur 28 — la moitié a dit « je reviendrai plus tard », personne n'est revenu.",
                    "quote": "Pourquoi je dois créer un compte pour acheter un t-shirt ? Je viens dépenser de l'argent, pas m'engager dans une relation.",
                    "speaker": "Tom, acheteur occasionnel",
                },
                {
                    "title": "La confiance s'effondre sans moyens de paiement familiers",
                    "finding": "Les acheteurs attendent Apple Pay / PayPal comme sortie de secours quand la marque leur est inconnue. Leur absence = perception louche, pas juste inconfort.",
                    "quote": "Je ne les connaissais pas. S'ils ne prennent pas PayPal je me dis que ma CB part on ne sait où.",
                    "speaker": "Camille, premier achat suite à pub sociale",
                },
            ],
            "quotes": [
                {
                    "speaker": "Élise, acheteuse",
                    "text": "C'était pas les cinq euros. C'est que j'avais passé dix minutes à choisir et ils me l'avaient caché tout du long.",
                    "highlight": "ils me l'avaient caché tout du long",
                    "code": "Révélation tardive",
                    "code_color": "#4f46e5",
                },
                {
                    "speaker": "Tom, acheteur",
                    "text": "Pourquoi je dois créer un compte pour acheter un t-shirt ? Je viens dépenser de l'argent, pas m'engager dans une relation.",
                    "highlight": "pas m'engager dans une relation",
                    "code": "Friction compte forcé",
                    "code_color": "#0ea5e9",
                },
                {
                    "speaker": "Camille, premier achat",
                    "text": "Je ne les connaissais pas. S'ils ne prennent pas PayPal je me dis que ma CB part on ne sait où.",
                    "highlight": "ma CB part on ne sait où",
                    "code": "Signal confiance : paiement",
                    "code_color": "#10b981",
                },
            ],
        },
    },
}


def get_demo_bundle(variant: str, locale: str) -> DemoBundle:
    """Fetch a demo bundle, falling back to (saas, en) when the requested
    variant or locale is unknown."""
    variant_dict = _BUNDLES.get(variant)  # type: ignore[arg-type]
    if variant_dict is None:
        variant_dict = _BUNDLES["saas"]
    bundle = variant_dict.get(locale)
    if bundle is None:
        bundle = variant_dict.get("en") or _BUNDLES["saas"]["en"]
    return bundle
