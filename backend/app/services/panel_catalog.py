"""Panel enrichment catalogue — the profiling question bank.

~50 consumer-profiling attributes used to re-target panelists for future
studies, validated against how real research panels profile members
(Prolific prescreeners, Cint/Dynata profiling attributes). Stored as DATA in
the ``panel_attributes`` table (seeded/synced on startup), so adding the 51st
attribute is a row here — never a schema migration.

Labels are seeded in English + French (the primary markets); de/es/it/pt fall
back to English at read time until translated. ``type``:
  - "single" — pick one (options)
  - "multi"  — pick any (options)
  - "bool"   — yes/no
  - "scale"  — 1..5 agreement (options carry the anchors)

``is_sensitive=True`` marks GDPR special-category data (health, income,
politics, religion) — hidden until the panelist gives explicit consent.
``priority`` orders by re-targeting value (higher first).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.panel import PanelAttribute


def _opt(value: str, en: str, fr: str) -> dict:
    return {"value": value, "label_i18n": {"en": en, "fr": fr}}


def _attr(
    id: str,
    category: str,
    type: str,
    en: str,
    fr: str,
    options: list[dict] | None = None,
    sensitive: bool = False,
    priority: int = 0,
) -> dict:
    return {
        "id": id,
        "category": category,
        "type": type,
        "label_i18n": {"en": en, "fr": fr},
        "options": options or [],
        "is_sensitive": sensitive,
        "priority": priority,
    }


# A reusable 5-point agreement scale.
_SCALE = [
    _opt("1", "Strongly disagree", "Pas du tout d'accord"),
    _opt("2", "Disagree", "Plutôt pas d'accord"),
    _opt("3", "Neutral", "Neutre"),
    _opt("4", "Agree", "Plutôt d'accord"),
    _opt("5", "Strongly agree", "Tout à fait d'accord"),
]


CATALOG: list[dict] = [
    # ── Household & family ────────────────────────────────────────────────
    _attr("household_size", "household", "single", "How many people live in your household (including you)?",
          "Combien de personnes vivent dans votre foyer (vous compris) ?",
          [_opt("1", "Just me", "Juste moi"), _opt("2", "2", "2"), _opt("3", "3", "3"),
           _opt("4", "4", "4"), _opt("5+", "5 or more", "5 ou plus")], priority=70),
    _attr("marital_status", "household", "single", "What's your relationship status?",
          "Quelle est votre situation de couple ?",
          [_opt("single", "Single", "Célibataire"), _opt("partnered", "In a relationship", "En couple"),
           _opt("married", "Married", "Marié(e)"), _opt("divorced", "Divorced / separated", "Divorcé(e) / séparé(e)"),
           _opt("widowed", "Widowed", "Veuf / veuve")], priority=55),
    _attr("children_count", "household", "single", "How many children do you have?",
          "Combien d'enfants avez-vous ?",
          [_opt("0", "None", "Aucun"), _opt("1", "1", "1"), _opt("2", "2", "2"),
           _opt("3+", "3 or more", "3 ou plus")], priority=75),
    _attr("children_ages", "household", "multi", "What are the ages of children in your household?",
          "Quels sont les âges des enfants de votre foyer ?",
          [_opt("none", "No children", "Aucun enfant"), _opt("0-2", "0–2", "0–2"),
           _opt("3-5", "3–5", "3–5"), _opt("6-12", "6–12", "6–12"),
           _opt("13-17", "13–17", "13–17"), _opt("18+", "18+", "18+")], priority=70),
    _attr("household_roles", "household", "multi", "Which of these do you do in your household?",
          "Lesquels de ces rôles assumez-vous dans votre foyer ?",
          [_opt("grocery", "Main grocery shopper", "Responsable des courses"),
           _opt("earner", "Main earner", "Principal revenu"),
           _opt("decisions", "Main decision-maker for big purchases", "Décideur des achats importants")], priority=80),
    _attr("housing_status", "household", "single", "Do you own or rent your home?",
          "Êtes-vous propriétaire ou locataire ?",
          [_opt("own", "Own", "Propriétaire"), _opt("rent", "Rent", "Locataire"),
           _opt("with_family", "Live with family", "Hébergé(e) chez des proches")], priority=60),
    _attr("dwelling_type", "household", "single", "What kind of home do you live in?",
          "Dans quel type de logement vivez-vous ?",
          [_opt("apartment", "Apartment / flat", "Appartement"), _opt("house", "House", "Maison"),
           _opt("other", "Other", "Autre")], priority=40),

    # ── Lifestyle & habits ───────────────────────────────────────────────
    _attr("smoking_status", "lifestyle", "single", "Do you smoke?",
          "Fumez-vous ?",
          [_opt("never", "Never", "Jamais"), _opt("former", "Used to, not anymore", "Ancien fumeur"),
           _opt("occasional", "Occasionally", "Occasionnellement"), _opt("daily", "Daily", "Tous les jours")],
          sensitive=True, priority=75),
    _attr("vaping", "lifestyle", "bool", "Do you vape / use e-cigarettes?",
          "Vapotez-vous (cigarette électronique) ?", sensitive=True, priority=55),
    _attr("alcohol_frequency", "lifestyle", "single", "How often do you drink alcohol?",
          "À quelle fréquence buvez-vous de l'alcool ?",
          [_opt("never", "Never", "Jamais"), _opt("occasionally", "Occasionally", "Occasionnellement"),
           _opt("weekly", "Weekly", "Chaque semaine"), _opt("daily", "Daily", "Tous les jours")],
          sensitive=True, priority=60),
    _attr("diet_type", "lifestyle", "multi", "Do any of these describe your diet?",
          "Votre alimentation correspond-elle à l'un de ces régimes ?",
          [_opt("omnivore", "No restrictions", "Sans restriction"), _opt("vegetarian", "Vegetarian", "Végétarien"),
           _opt("vegan", "Vegan", "Végan"), _opt("pescatarian", "Pescatarian", "Pescétarien"),
           _opt("halal", "Halal", "Halal"), _opt("kosher", "Kosher", "Casher"),
           _opt("gluten_free", "Gluten-free", "Sans gluten")], priority=65),
    _attr("exercise_frequency", "lifestyle", "single", "How often do you exercise?",
          "À quelle fréquence faites-vous du sport ?",
          [_opt("never", "Rarely / never", "Rarement / jamais"), _opt("1-2", "1–2 times a week", "1–2 fois par semaine"),
           _opt("3-4", "3–4 times a week", "3–4 fois par semaine"), _opt("5+", "5+ times a week", "5 fois et plus par semaine")],
          priority=55),
    _attr("fitness_activities", "lifestyle", "multi", "Which activities do you do?",
          "Quelles activités pratiquez-vous ?",
          [_opt("gym", "Gym / weights", "Salle de sport"), _opt("running", "Running", "Course à pied"),
           _opt("yoga", "Yoga / pilates", "Yoga / pilates"), _opt("cycling", "Cycling", "Vélo"),
           _opt("team_sports", "Team sports", "Sports collectifs"), _opt("swimming", "Swimming", "Natation")], priority=45),

    # ── Pets ─────────────────────────────────────────────────────────────
    _attr("has_pets", "pets", "bool", "Do you have any pets?", "Avez-vous des animaux de compagnie ?", priority=70),
    _attr("pet_types", "pets", "multi", "Which pets do you have?",
          "Quels animaux avez-vous ?",
          [_opt("dog", "Dog", "Chien"), _opt("cat", "Cat", "Chat"), _opt("fish", "Fish", "Poissons"),
           _opt("bird", "Bird", "Oiseau"), _opt("reptile", "Reptile", "Reptile"),
           _opt("small_mammal", "Small mammal", "Petit mammifère"), _opt("horse", "Horse", "Cheval")], priority=65),

    # ── Health & wellbeing (sensitive) ───────────────────────────────────
    _attr("health_conditions", "health", "multi", "Do any of these apply to you?",
          "L'un de ces éléments vous concerne-t-il ?",
          [_opt("none", "None of these", "Aucun"), _opt("diabetes", "Diabetes", "Diabète"),
           _opt("hypertension", "High blood pressure", "Hypertension"), _opt("asthma", "Asthma", "Asthme"),
           _opt("allergies", "Allergies", "Allergies"), _opt("skin", "Skin condition", "Problème de peau")],
          sensitive=True, priority=70),
    _attr("vision", "health", "single", "Do you wear glasses or contact lenses?",
          "Portez-vous des lunettes ou des lentilles ?",
          [_opt("no", "No", "Non"), _opt("glasses", "Glasses", "Lunettes"),
           _opt("contacts", "Contact lenses", "Lentilles"), _opt("both", "Both", "Les deux")], priority=40),
    _attr("supplements", "health", "bool", "Do you take vitamins or supplements?",
          "Prenez-vous des vitamines ou compléments alimentaires ?", priority=45),
    _attr("pregnancy_parent", "health", "single", "Does any of these describe you right now?",
          "L'un de ces éléments vous décrit-il actuellement ?",
          [_opt("na", "None", "Aucun"), _opt("trying", "Trying for a baby", "En essai de bébé"),
           _opt("expecting", "Expecting", "Enceinte / en attente"), _opt("new_parent", "New parent (<2y)", "Jeune parent (<2 ans)")],
          sensitive=True, priority=65),

    # ── Financial (sensitive) ────────────────────────────────────────────
    _attr("income_band", "finance", "single", "What's your household's yearly income?",
          "Quel est le revenu annuel de votre foyer ?",
          [_opt("u20", "Under €20k", "Moins de 20 k€"), _opt("20_40", "€20–40k", "20–40 k€"),
           _opt("40_60", "€40–60k", "40–60 k€"), _opt("60_100", "€60–100k", "60–100 k€"),
           _opt("100p", "Over €100k", "Plus de 100 k€"), _opt("prefer_not", "Prefer not to say", "Je préfère ne pas répondre")],
          sensitive=True, priority=85),
    _attr("income_sources", "finance", "multi", "Where does your income come from?",
          "D'où provient votre revenu ?",
          [_opt("salary", "Salary", "Salaire"), _opt("self_employed", "Self-employment", "Travail indépendant"),
           _opt("investments", "Investments", "Investissements"), _opt("benefits", "Benefits", "Aides sociales"),
           _opt("pension", "Pension", "Retraite")], sensitive=True, priority=55),
    _attr("banking_type", "finance", "multi", "Which kinds of bank do you use?",
          "Quels types de banque utilisez-vous ?",
          [_opt("traditional", "Traditional bank", "Banque traditionnelle"),
           _opt("neobank", "Online / neobank (Revolut, N26…)", "Banque en ligne (Revolut, N26…)")], priority=60),
    _attr("investments_owned", "finance", "multi", "Do you hold any of these?",
          "Détenez-vous l'un de ces placements ?",
          [_opt("none", "None", "Aucun"), _opt("stocks", "Stocks / funds", "Actions / fonds"),
           _opt("crypto", "Crypto", "Crypto"), _opt("real_estate", "Real estate", "Immobilier"),
           _opt("pension_fund", "Pension fund", "Épargne retraite")], sensitive=True, priority=65),
    _attr("insurance_held", "finance", "multi", "Which insurance do you have?",
          "Quelles assurances avez-vous ?",
          [_opt("health", "Health", "Santé"), _opt("auto", "Car", "Auto"), _opt("home", "Home", "Habitation"),
           _opt("life", "Life", "Vie"), _opt("travel", "Travel", "Voyage")], priority=55),
    _attr("financial_decision_maker", "finance", "bool", "Are you the main person managing money in your household?",
          "Êtes-vous la personne qui gère principalement l'argent du foyer ?", priority=60),

    # ── Shopping behaviour ───────────────────────────────────────────────
    _attr("grocery_channel", "shopping", "single", "Where do you mainly buy groceries?",
          "Où faites-vous principalement vos courses alimentaires ?",
          [_opt("supermarket", "Supermarket", "Supermarché"), _opt("discounter", "Discounter", "Hard-discount"),
           _opt("online", "Online / delivery", "En ligne / livraison"), _opt("convenience", "Convenience store", "Supérette"),
           _opt("market", "Local market", "Marché")], priority=70),
    _attr("online_shopping_frequency", "shopping", "single", "How often do you shop online?",
          "À quelle fréquence achetez-vous en ligne ?",
          [_opt("never", "Rarely / never", "Rarement / jamais"), _opt("monthly", "Monthly", "Chaque mois"),
           _opt("weekly", "Weekly", "Chaque semaine"), _opt("multi_weekly", "Several times a week", "Plusieurs fois par semaine")],
          priority=70),
    _attr("shopping_channels", "shopping", "multi", "Where do you like to shop?",
          "Où aimez-vous faire vos achats ?",
          [_opt("in_store", "In-store", "En magasin"), _opt("marketplace", "Marketplaces (Amazon…)", "Places de marché (Amazon…)"),
           _opt("brand_sites", "Brand websites", "Sites de marque"), _opt("social", "Social media shops", "Boutiques sur réseaux sociaux")],
          priority=60),
    _attr("purchase_categories", "shopping", "multi", "What do you shop for most?",
          "Quelles catégories achetez-vous le plus ?",
          [_opt("groceries", "Groceries", "Alimentation"), _opt("fashion", "Fashion", "Mode"),
           _opt("electronics", "Electronics", "Électronique"), _opt("beauty", "Beauty", "Beauté"),
           _opt("home", "Home & furniture", "Maison & meubles"), _opt("baby", "Baby & kids", "Bébé & enfants"),
           _opt("pet", "Pet", "Animaux"), _opt("diy", "DIY & garden", "Bricolage & jardin")], priority=75),
    _attr("shopping_style", "shopping", "single", "How would you describe how you shop?",
          "Comment décririez-vous votre façon d'acheter ?",
          [_opt("price", "Always hunting for the best price", "Toujours au meilleur prix"),
           _opt("brand_loyal", "Stick to brands I trust", "Fidèle à mes marques"),
           _opt("research", "Research a lot before buying", "Je compare beaucoup avant d'acheter"),
           _opt("impulse", "Often buy on impulse", "Souvent sur un coup de tête")], priority=65),
    _attr("loyalty_programs", "shopping", "bool", "Do you use store loyalty programs?",
          "Utilisez-vous des programmes de fidélité ?", priority=50),
    _attr("secondhand_resale", "shopping", "bool", "Do you buy or sell second-hand (Vinted, eBay…)?",
          "Achetez-vous ou vendez-vous d'occasion (Vinted, eBay…) ?", priority=55),
    _attr("subscriptions_count", "shopping", "single", "How many paid subscriptions do you have?",
          "Combien d'abonnements payants avez-vous ?",
          [_opt("0", "None", "Aucun"), _opt("1-2", "1–2", "1–2"), _opt("3-5", "3–5", "3–5"),
           _opt("6+", "6 or more", "6 ou plus")], priority=50),

    # ── Brand affinities ─────────────────────────────────────────────────
    _attr("tech_ecosystem", "brands", "single", "Which phone ecosystem do you use?",
          "Quel écosystème de téléphone utilisez-vous ?",
          [_opt("apple", "Apple / iPhone", "Apple / iPhone"), _opt("android", "Android (Samsung, Google…)", "Android (Samsung, Google…)"),
           _opt("mixed", "A mix", "Un mélange")], priority=65),
    _attr("streaming_services", "brands", "multi", "Which streaming services do you pay for?",
          "À quels services de streaming êtes-vous abonné(e) ?",
          [_opt("netflix", "Netflix", "Netflix"), _opt("disney", "Disney+", "Disney+"),
           _opt("prime", "Prime Video", "Prime Video"), _opt("spotify", "Spotify", "Spotify"),
           _opt("appletv", "Apple TV+", "Apple TV+"), _opt("youtube", "YouTube Premium", "YouTube Premium"),
           _opt("none", "None", "Aucun")], priority=60),
    _attr("fashion_brands", "brands", "multi", "Which of these do you shop at?",
          "Chez lesquelles de ces enseignes achetez-vous ?",
          [_opt("zara", "Zara", "Zara"), _opt("hm", "H&M", "H&M"), _opt("uniqlo", "Uniqlo", "Uniqlo"),
           _opt("nike_adidas", "Nike / Adidas", "Nike / Adidas"), _opt("luxury", "Luxury brands", "Marques de luxe"),
           _opt("supermarket_clothes", "Supermarket clothing", "Vêtements de supermarché")], priority=55),
    _attr("car_brand", "brands", "single", "If you drive, what brand is your main car?",
          "Si vous conduisez, quelle est la marque de votre voiture principale ?",
          [_opt("none", "I don't drive", "Je ne conduis pas"), _opt("vw_group", "VW / Audi / Skoda / Seat", "VW / Audi / Skoda / Seat"),
           _opt("french", "Renault / Peugeot / Citroën", "Renault / Peugeot / Citroën"),
           _opt("premium", "BMW / Mercedes / Audi", "BMW / Mercedes / Audi"),
           _opt("asian", "Toyota / Kia / Hyundai…", "Toyota / Kia / Hyundai…"),
           _opt("tesla", "Tesla / EV brand", "Tesla / marque électrique"), _opt("other", "Other", "Autre")], priority=50),

    # ── Technology & devices ─────────────────────────────────────────────
    _attr("devices_owned", "tech", "multi", "Which of these do you own?",
          "Lesquels de ces appareils possédez-vous ?",
          [_opt("smartphone", "Smartphone", "Smartphone"), _opt("laptop", "Laptop", "Ordinateur portable"),
           _opt("tablet", "Tablet", "Tablette"), _opt("smartwatch", "Smartwatch", "Montre connectée"),
           _opt("smart_speaker", "Smart speaker", "Enceinte connectée"), _opt("smart_home", "Smart-home devices", "Objets connectés"),
           _opt("console", "Games console", "Console de jeu"), _opt("vr", "VR headset", "Casque VR")], priority=55),
    _attr("social_platforms", "tech", "multi", "Which social platforms do you use?",
          "Quels réseaux sociaux utilisez-vous ?",
          [_opt("instagram", "Instagram", "Instagram"), _opt("tiktok", "TikTok", "TikTok"),
           _opt("facebook", "Facebook", "Facebook"), _opt("x", "X / Twitter", "X / Twitter"),
           _opt("linkedin", "LinkedIn", "LinkedIn"), _opt("youtube", "YouTube", "YouTube"),
           _opt("snapchat", "Snapchat", "Snapchat"), _opt("reddit", "Reddit", "Reddit")], priority=55),
    _attr("ai_tools_usage", "tech", "single", "Do you use AI tools (ChatGPT, etc.)?",
          "Utilisez-vous des outils d'IA (ChatGPT, etc.) ?",
          [_opt("never", "Never", "Jamais"), _opt("tried", "Tried a few times", "Essayé quelques fois"),
           _opt("regular", "Regularly", "Régulièrement")], priority=50),

    # ── Travel & mobility ────────────────────────────────────────────────
    _attr("travel_frequency", "travel", "single", "How often do you travel for leisure?",
          "À quelle fréquence voyagez-vous pour les loisirs ?",
          [_opt("never", "Rarely / never", "Rarement / jamais"), _opt("1-2", "1–2 trips a year", "1–2 voyages par an"),
           _opt("3-5", "3–5 trips a year", "3–5 voyages par an"), _opt("6+", "6+ trips a year", "6 voyages et plus par an")],
          priority=55),
    _attr("flights_per_year", "travel", "single", "How many flights have you taken in the last year?",
          "Combien de vols avez-vous pris au cours de la dernière année ?",
          [_opt("0", "None", "Aucun"), _opt("1-2", "1–2", "1–2"), _opt("3-5", "3–5", "3–5"),
           _opt("6+", "6 or more", "6 ou plus")], priority=60),
    _attr("travel_type", "travel", "multi", "What kind of travel do you do?",
          "Quel type de voyage faites-vous ?",
          [_opt("leisure", "Leisure", "Loisirs"), _opt("business", "Business", "Affaires")], priority=45),
    _attr("vehicle_fuel", "travel", "single", "What does your main vehicle run on?",
          "Quelle est la motorisation de votre véhicule principal ?",
          [_opt("none", "I don't have a vehicle", "Pas de véhicule"), _opt("petrol", "Petrol", "Essence"),
           _opt("diesel", "Diesel", "Diesel"), _opt("hybrid", "Hybrid", "Hybride"), _opt("ev", "Electric", "Électrique")],
          priority=55),
    _attr("commute_mode", "travel", "single", "How do you mainly get around day-to-day?",
          "Comment vous déplacez-vous principalement au quotidien ?",
          [_opt("car", "Car", "Voiture"), _opt("transit", "Public transport", "Transports en commun"),
           _opt("bike", "Bike / scooter", "Vélo / trottinette"), _opt("walk", "Walk", "À pied"),
           _opt("wfh", "Mostly work from home", "Surtout en télétravail")], priority=45),

    # ── Media ────────────────────────────────────────────────────────────
    _attr("media_consumption", "media", "multi", "How do you consume content?",
          "Comment consommez-vous des contenus ?",
          [_opt("streaming", "Streaming", "Streaming"), _opt("tv", "Live TV", "TV en direct"),
           _opt("podcasts", "Podcasts", "Podcasts"), _opt("news", "News sites", "Sites d'actualité"),
           _opt("print", "Print", "Presse papier"), _opt("radio", "Radio", "Radio"), _opt("gaming", "Gaming", "Jeux vidéo")],
          priority=45),

    # ── Psychographics / values ──────────────────────────────────────────
    _attr("early_adopter", "values", "scale", "I love trying new products before everyone else.",
          "J'adore essayer les nouveaux produits avant tout le monde.", list(_SCALE), priority=50),
    _attr("eco_conscious", "values", "scale", "I try to make environmentally-friendly choices.",
          "J'essaie de faire des choix respectueux de l'environnement.", list(_SCALE), priority=50),
    _attr("price_vs_quality", "values", "scale", "I'll pay more for higher quality.",
          "Je suis prêt(e) à payer plus pour une meilleure qualité.", list(_SCALE), priority=50),

    # ── Sensitive identity (lowest priority, optional) ───────────────────
    _attr("political_leaning", "identity", "single", "Where would you place yourself politically?",
          "Où vous situez-vous politiquement ?",
          [_opt("left", "Left", "Gauche"), _opt("centre", "Centre", "Centre"), _opt("right", "Right", "Droite"),
           _opt("none", "None / apolitical", "Aucun / apolitique"), _opt("prefer_not", "Prefer not to say", "Je préfère ne pas répondre")],
          sensitive=True, priority=25),
    _attr("religion", "identity", "single", "Do you identify with a religion?",
          "Vous identifiez-vous à une religion ?",
          [_opt("none", "None", "Aucune"), _opt("christian", "Christian", "Chrétien"),
           _opt("muslim", "Muslim", "Musulman"), _opt("jewish", "Jewish", "Juif"),
           _opt("hindu", "Hindu", "Hindou"), _opt("buddhist", "Buddhist", "Bouddhiste"),
           _opt("other", "Other", "Autre"), _opt("prefer_not", "Prefer not to say", "Je préfère ne pas répondre")],
          sensitive=True, priority=20),
]


def ensure_attributes_seeded(db: Session) -> int:
    """Idempotently sync the catalogue into ``panel_attributes``.

    Inserts new attributes and refreshes mutable fields (labels, options,
    priority, sensitivity) for existing ones, so editing this file + a deploy
    is enough to evolve the catalogue. Returns the number of rows touched.
    """
    touched = 0
    existing = {a.id: a for a in db.query(PanelAttribute).all()}
    for order, spec in enumerate(CATALOG):
        row = existing.get(spec["id"])
        opts_json = json.dumps(spec["options"], ensure_ascii=False)
        label_json = json.dumps(spec["label_i18n"], ensure_ascii=False)
        if row is None:
            db.add(PanelAttribute(
                id=spec["id"], category=spec["category"], type=spec["type"],
                options=opts_json, label_i18n=label_json,
                is_sensitive=spec["is_sensitive"], priority=spec["priority"],
                sort_order=order, active=True,
            ))
            touched += 1
        else:
            row.category = spec["category"]
            row.type = spec["type"]
            row.options = opts_json
            row.label_i18n = label_json
            row.is_sensitive = spec["is_sensitive"]
            row.priority = spec["priority"]
            row.sort_order = order
            row.active = True
            touched += 1
    db.commit()
    return touched
