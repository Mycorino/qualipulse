"""French translations for the project templates defined in ``templates.py``.

Kept in a separate module so the canonical English definitions in
``templates.py`` stay readable. Each entry is a partial dict that gets merged
onto the English template at render time by ``get_localised_template`` — any
field that isn't translated falls back to the English source, which means new
templates ship with a safe default instead of crashing.

When you add a new template, add a translation entry here in the same shape
so French users see French copy. ``questions`` must preserve ``section_index``
and ``question_index`` values — those are load-bearing for downstream
ordering.
"""

from __future__ import annotations


TEMPLATES_FR: dict[str, dict] = {
    "customer-churn": {
        "name": "Étude sur le churn client",
        "description": "Comprenez pourquoi vos clients payants vous quittent. Creusez le moment de bascule, les déclencheurs, et si la rupture produit est réparable.",
        "best_for": "Équipes SaaS confrontées à une hausse du churn ou à une faible rétention",
        "research_objective": "Comprendre les causes profondes du churn client et identifier les leviers les plus actionnables pour améliorer la rétention.",
        "target_audience": "Anciens clients ayant annulé dans les 90 derniers jours, tous niveaux d'abonnement et ancienneté confondus (au moins 1 mois d'usage avant l'annulation).",
        "learning_goals": [
            "Quel a été le moment déclencheur qui les a poussés à annuler ?",
            "Quelles lacunes produit ou service ont contribué à leur décision ?",
            "Qu'est-ce qui les aurait fait rester, s'il y avait quelque chose ?",
        ],
        "screening_questions": [
            {
                "question": "Quand avez-vous annulé votre abonnement ?",
                "options": [
                    "Au cours des 30 derniers jours",
                    "Il y a 1 à 3 mois",
                    "Il y a plus de 3 mois",
                    "Je n'ai pas annulé",
                ],
                "disqualifying_options": ["Il y a plus de 3 mois", "Je n'ai pas annulé"],
            },
        ],
        "questions": [
            {"section_title": "Contexte", "main_question": "Parlez-moi un peu de votre rôle et de l'usage que vous faisiez de notre produit.", "interview_notes": "Échauffement. Laissez-les poser le contexte avec leurs mots.", "desired_learning": "Cas d'usage de base et rôle"},
            {"section_title": "Contexte", "main_question": "Comment avez-vous entendu parler de nous à l'origine et qu'est-ce qui vous a poussé à vous inscrire ?", "interview_notes": "", "desired_learning": "Canal d'acquisition et job-to-be-done initial"},
            {"section_title": "Le moment de bascule", "main_question": "Pouvez-vous me raconter le moment où vous avez décidé d'annuler ? Que s'est-il passé cette semaine-là ?", "interview_notes": "Cherchez l'événement déclencheur. Demandez 'et ensuite ?' jusqu'à avoir toute l'histoire.", "desired_learning": "L'événement déclencheur précis"},
            {"section_title": "Le moment de bascule", "main_question": "Y avait-il des frustrations qui s'accumulaient avant ce moment-là ?", "interview_notes": "", "desired_learning": "Frustrations long terme vs déclencheurs aigus"},
            {"section_title": "Alternatives", "main_question": "Qu'utilisez-vous à la place maintenant, le cas échéant ? Comment ça se passe ?", "interview_notes": "Ne menez pas. Laissez-les nommer librement leurs alternatives.", "desired_learning": "Alternatives concurrentes et avantages perçus"},
            {"section_title": "Alternatives", "main_question": "Qu'est-ce qui vous aurait fait rester ?", "interview_notes": "C'est LA question clé — cherchez des éléments concrets.", "desired_learning": "Leviers de rétention actionnables"},
        ],
    },
    "feature-validation": {
        "name": "Validation de fonctionnalité",
        "description": "Testez si une idée de fonctionnalité résout un vrai problème, avant d'engager la moindre ligne de code.",
        "best_for": "Product managers qui valident une hypothèse avant de construire",
        "research_objective": "Valider si une fonctionnalité envisagée répond à une vraie douleur client et comprendre à quoi ressemblerait la solution idéale selon l'utilisateur.",
        "target_audience": "Utilisateurs actifs du produit ayant vécu le problème ciblé au cours des 30 derniers jours.",
        "learning_goals": [
            "À quelle fréquence et avec quelle intensité les utilisateurs rencontrent-ils ce problème aujourd'hui ?",
            "Quels contournements utilisent-ils et à quel point sont-ils satisfaisants ?",
            "Comment décriraient-ils la solution idéale avec leurs propres mots ?",
        ],
        "screening_questions": [
            {
                "question": "À quelle fréquence utilisez-vous notre produit ?",
                "options": [
                    "Plusieurs fois par jour",
                    "Quelques fois par semaine",
                    "Moins d'une fois par semaine",
                    "J'ai arrêté de l'utiliser",
                ],
                "disqualifying_options": ["J'ai arrêté de l'utiliser"],
            },
        ],
        "questions": [
            {"section_title": "Workflow actuel", "main_question": "Racontez-moi la dernière fois où vous avez fait [tâche concernée]. À quoi ça ressemblait ?", "interview_notes": "Exemple concret et récent. Pas d'hypothétique.", "desired_learning": "Workflow réel actuel"},
            {"section_title": "Workflow actuel", "main_question": "À quel moment ce workflow devient frustrant ou lent pour vous ?", "interview_notes": "", "desired_learning": "Points de douleur précis"},
            {"section_title": "Contournements", "main_question": "Comment gérez-vous ça aujourd'hui ? Des contournements, outils ou astuces pour vous faciliter la vie ?", "interview_notes": "", "desired_learning": "Contournements existants"},
            {"section_title": "Contournements", "main_question": "Dans quelle mesure est-ce satisfaisant ? Qu'est-ce qui manque encore ?", "interview_notes": "", "desired_learning": "Lacunes des solutions actuelles"},
            {"section_title": "Solution idéale", "main_question": "Si vous aviez une baguette magique pour régler ça, que se passerait-il ?", "interview_notes": "Question ouverte. Laissez-les rêver.", "desired_learning": "Leur modèle mental de l'idéal"},
            {"section_title": "Solution idéale", "main_question": "Si on construisait [fonctionnalité envisagée], comment l'utiliseriez-vous ? Est-ce que ça réglerait vraiment le problème ?", "interview_notes": "Décrivez la fonctionnalité brièvement. Ne survendez pas.", "desired_learning": "Adéquation de la solution proposée"},
        ],
    },
    "onboarding-friction": {
        "name": "Étude des frictions d'onboarding",
        "description": "Découvrez où les nouveaux utilisateurs se perdent, se bloquent ou décrochent pendant leurs premières sessions.",
        "best_for": "Équipes produit confrontées à un faible taux d'activation",
        "research_objective": "Identifier les points de friction précis dans l'expérience nouvelle utilisateur qui empêchent d'atteindre leur premier 'aha moment'.",
        "target_audience": "Utilisateurs inscrits au cours des 14 derniers jours, activés ou non.",
        "learning_goals": [
            "Qu'espéraient-ils accomplir durant leur première session ?",
            "Où ont-ils été bloqués, perdus ou confus ?",
            "Qu'est-ce qui les aurait aidés à réussir plus vite ?",
        ],
        "screening_questions": [
            {
                "question": "Quand vous êtes-vous inscrit pour la première fois à notre produit ?",
                "options": [
                    "Au cours des 7 derniers jours",
                    "Il y a 1 à 2 semaines",
                    "Il y a 2 à 4 semaines",
                    "Il y a plus d'un mois",
                ],
                "disqualifying_options": ["Il y a plus d'un mois"],
            },
        ],
        "questions": [
            {"section_title": "Premières impressions", "main_question": "Dites-moi ce qui vous a poussé à vous inscrire. Qu'espériez-vous en faire ?", "interview_notes": "Comprendre le job-to-be-done.", "desired_learning": "Attentes et objectifs initiaux"},
            {"section_title": "Premières impressions", "main_question": "Racontez-moi votre première session. Qu'avez-vous essayé de faire en premier ?", "interview_notes": "Chronologique — premier clic, première action.", "desired_learning": "Chemin initial dans le produit"},
            {"section_title": "Friction", "main_question": "Y a-t-il eu un moment où vous vous êtes senti bloqué ou confus ? Que se passait-il ?", "interview_notes": "Cherchez du concret. 'À quoi ressemblait l'écran ?'", "desired_learning": "Points de friction"},
            {"section_title": "Friction", "main_question": "Qu'avez-vous fait quand vous étiez bloqué ? Vous avez trouvé, demandé de l'aide, ou abandonné ?", "interview_notes": "", "desired_learning": "Autonomie vs abandon"},
            {"section_title": "Première valeur", "main_question": "Y a-t-il eu un moment où le produit a fait 'tilt' — où vous vous êtes dit 'ah oui, c'est utile' ?", "interview_notes": "", "desired_learning": "Aha moment (ou son absence)"},
            {"section_title": "Première valeur", "main_question": "Qu'est-ce qui aurait rendu votre première session plus fluide ou plus rapide ?", "interview_notes": "", "desired_learning": "Idées d'amélioration concrètes"},
        ],
    },
    "pricing-research": {
        "name": "Prix et disposition à payer",
        "description": "Testez comment les clients perçoivent votre prix, ce qu'ils seraient prêts à payer, et quels leviers de valeur justifient quels paliers.",
        "best_for": "Équipes qui retravaillent leur pricing ou lancent une nouvelle offre",
        "research_objective": "Comprendre comment les clients cibles perçoivent notre prix et notre valeur, et identifier le point de prix et l'offre qui maximisent la conversion sans laisser d'argent sur la table.",
        "target_audience": "Prospects ou clients actuels dans votre segment cible avec un besoin actif pour cette catégorie de produit.",
        "learning_goals": [
            "Quelles fonctionnalités ou résultats valorisent-ils le plus ?",
            "Quelle est leur référence mentale de prix pour cette catégorie ?",
            "Où se situe leur résistance au prix et où voient-ils une bonne affaire ?",
        ],
        "screening_questions": [
            {
                "question": "Évaluez-vous ou utilisez-vous actuellement un outil dans cette catégorie ?",
                "options": [
                    "Oui, en évaluation",
                    "Oui, je paye actuellement",
                    "Non, mais intéressé",
                    "Non, pas intéressé",
                ],
                "disqualifying_options": ["Non, pas intéressé"],
            },
        ],
        "questions": [
            {"section_title": "Contexte", "main_question": "Qu'est-ce que votre équipe utilise aujourd'hui pour résoudre [problème], et combien ça vous coûte ?", "interview_notes": "Comprendre le prix de référence.", "desired_learning": "Dépenses et outils existants"},
            {"section_title": "Contexte", "main_question": "Quelle valeur en tirez-vous, avec vos propres mots ?", "interview_notes": "", "desired_learning": "Cadrage de la valeur"},
            {"section_title": "Leviers de valeur", "main_question": "Si vous imaginiez l'outil idéal pour ça, quelles fonctionnalités ou bénéfices compteraient le plus ?", "interview_notes": "Classez par ordre si possible.", "desired_learning": "Hiérarchie de valeur"},
            {"section_title": "Leviers de valeur", "main_question": "Pour lesquelles seriez-vous prêt à payer un premium ? Lesquelles vous paraissent incontournables ?", "interview_notes": "", "desired_learning": "Sensibilité au prix vs premium"},
            {"section_title": "Réaction au prix", "main_question": "Si je vous disais qu'un outil comme ça coûte X € par mois et par utilisateur, quelle serait votre réaction ?", "interview_notes": "Cadre Van Westendorp : trop bas / bon prix / cher / trop cher.", "desired_learning": "Perception du prix"},
            {"section_title": "Réaction au prix", "main_question": "Comment choisiriez-vous entre une offre de base moins chère et une offre pro plus chère ? Qu'y aurait-il dans la pro qui vous ferait basculer ?", "interview_notes": "", "desired_learning": "Déclencheurs de passage à l'offre supérieure"},
        ],
    },
    "product-market-fit": {
        "name": "Validation product-market fit",
        "description": "Validation early-stage : comprenez qui sont vos meilleurs utilisateurs, pour quel job ils vous embauchent, et si la douleur est réelle.",
        "best_for": "Fondateurs en pré-lancement ou early-growth",
        "research_objective": "Valider le segment cible, le job-to-be-done et l'intensité de la douleur pour déterminer s'il existe un vrai product-market fit et quel segment ouvre la voie.",
        "target_audience": "Personnes correspondant au persona cible hypothétique et qui vivent activement le problème que nous pensons résoudre.",
        "learning_goals": [
            "La douleur est-elle assez réelle et fréquente pour qu'on soit prêt à payer ?",
            "Qui est le meilleur client potentiel et pourquoi ?",
            "Que feraient-ils si notre produit n'existait pas ?",
        ],
        "screening_questions": [
            {
                "question": "Au cours du dernier mois, avez-vous personnellement rencontré [problème] ?",
                "options": ["Oui, fréquemment", "Oui, occasionnellement", "Rarement", "Jamais"],
                "disqualifying_options": ["Jamais"],
            },
        ],
        "questions": [
            {"section_title": "Contexte", "main_question": "Parlez-moi de votre rôle et de ce à quoi ressemble une semaine type pour vous.", "interview_notes": "Comprenez leur monde.", "desired_learning": "Rôle et contexte"},
            {"section_title": "Contexte", "main_question": "Quels sont les plus gros défis auxquels vous faites face en ce moment autour de [domaine concerné] ?", "interview_notes": "", "desired_learning": "Points de douleur top-of-mind"},
            {"section_title": "Le problème", "main_question": "Racontez-moi la dernière fois que vous avez dû gérer [problème]. Ça a donné quoi ?", "interview_notes": "Exemple concret récent.", "desired_learning": "Workflow réel"},
            {"section_title": "Le problème", "main_question": "Sur une échelle de 'pénible' à 'rien de grave', à quel point c'est frustrant pour vous ?", "interview_notes": "Cherchez le pourquoi.", "desired_learning": "Intensité de la douleur"},
            {"section_title": "Alternatives", "main_question": "Comment gérez-vous ça aujourd'hui ? Quels outils, processus ou astuces utilisez-vous ?", "interview_notes": "", "desired_learning": "Solutions actuelles"},
            {"section_title": "Alternatives", "main_question": "Avez-vous déjà essayé de payer quelqu'un ou d'acheter un outil pour faire disparaître ce problème ?", "interview_notes": "", "desired_learning": "Historique de disposition à payer"},
            {"section_title": "Adéquation de la solution", "main_question": "Si vous aviez une baguette magique, comment ce problème disparaîtrait-il ?", "interview_notes": "Laissez-les décrire leur idéal.", "desired_learning": "Forme de la solution idéale"},
        ],
    },
    "customer-discovery": {
        "name": "Entretiens de discovery client",
        "description": "Entretiens ouverts pour comprendre le monde de votre client cible, ses douleurs quotidiennes et où votre produit pourrait s'inscrire.",
        "best_for": "Fondateurs et PM qui explorent une nouvelle opportunité",
        "research_objective": "Construire une compréhension profonde du contexte client, des points de douleur, des workflows actuels et des besoins non satisfaits pour orienter le produit et le positionnement.",
        "target_audience": "Personnes correspondant au persona cible hypothétique et prêtes à partager ouvertement leurs workflows et défis.",
        "learning_goals": [
            "À quoi ressemble une journée type pour ce persona ?",
            "Quels sont leurs plus gros besoins non satisfaits dans notre espace problème ?",
            "Quel vocabulaire utilisent-ils pour décrire leur travail et leurs douleurs ?",
        ],
        "screening_questions": [],
        "questions": [
            {"section_title": "Leur monde", "main_question": "Parlez-moi de votre rôle et de votre équipe. Avec qui travaillez-vous au quotidien ?", "interview_notes": "Échauffement et mise en contexte.", "desired_learning": "Rôle et structure d'équipe"},
            {"section_title": "Leur monde", "main_question": "À quoi ressemble une semaine type pour vous ?", "interview_notes": "", "desired_learning": "Texture du workflow"},
            {"section_title": "Points de douleur", "main_question": "Quels sont les aspects les plus difficiles ou frustrants de votre travail aujourd'hui ?", "interview_notes": "", "desired_learning": "Douleurs principales, avec leurs mots"},
            {"section_title": "Points de douleur", "main_question": "Racontez-moi la dernière fois qu'un de ces points vous a vraiment ralenti. Que s'est-il passé ?", "interview_notes": "Histoire concrète.", "desired_learning": "Exemples réels"},
            {"section_title": "Outils et contournements", "main_question": "Quels outils ou processus utilisez-vous pour faire votre travail ? Lesquels adorez-vous, et lesquels vous frustrent ?", "interview_notes": "", "desired_learning": "Stack actuelle"},
            {"section_title": "Outils et contournements", "main_question": "Si vous pouviez changer une chose au fonctionnement de votre équipe, ce serait quoi ?", "interview_notes": "", "desired_learning": "Zones d'opportunité"},
        ],
    },
    "brand-perception": {
        "name": "Perception de marque et messages",
        "description": "Testez comment votre marque, votre accroche et vos messages clés résonnent auprès de votre cible.",
        "best_for": "Marketeurs qui retravaillent un positionnement ou une landing page",
        "research_objective": "Comprendre comment notre audience cible perçoit notre marque et nos messages clés, et identifier quels mots et cadrages résonnent ou tombent à plat.",
        "target_audience": "Personnes correspondant à notre persona cible mais sans opinion préalable forte sur la marque.",
        "learning_goals": [
            "Qu'évoque notre marque dans leur esprit avant et après exposition ?",
            "Quels messages semblent clairs, lesquels semblent confus, lesquels excitent ?",
            "Quels mots utiliseraient-ils pour décrire ce que nous faisons ?",
        ],
        "screening_questions": [
            {
                "question": "Aviez-vous déjà entendu parler de notre marque ?",
                "options": [
                    "Jamais",
                    "Le nom me dit quelque chose",
                    "Oui, je sais ce qu'ils font",
                    "Oui, je suis client",
                ],
                "disqualifying_options": ["Oui, je suis client"],
            },
        ],
        "questions": [
            {"section_title": "Première réaction", "main_question": "Quand je vous dis le nom [marque], qu'est-ce qui vous vient en premier à l'esprit ?", "interview_notes": "Association top-of-mind.", "desired_learning": "Associations spontanées"},
            {"section_title": "Première réaction", "main_question": "À votre avis, que fait cette entreprise, juste à partir du nom ou de ce que vous avez vu ?", "interview_notes": "", "desired_learning": "Catégorie perçue"},
            {"section_title": "Messages", "main_question": "Je vais vous lire une accroche. Dites-moi ce qu'elle vous fait ressentir ou penser : '[ACCROCHE]'", "interview_notes": "Pause après la lecture. Laissez-les réagir.", "desired_learning": "Réception de l'accroche"},
            {"section_title": "Messages", "main_question": "Est-ce que cette accroche rend plus clair ce que fait le produit, ou plus confus ?", "interview_notes": "", "desired_learning": "Clarté"},
            {"section_title": "Cadrage concurrentiel", "main_question": "Si vous deviez décrire ce que nous faisons à un ami, comment feriez-vous ?", "interview_notes": "", "desired_learning": "Formulation naturelle"},
        ],
    },
}


# Localised labels for the goal categories used by match_templates_for_company.
# Keeps the "Matches your goal: X" chip in sync with the rest of the UI copy.
GOAL_LABELS_FR: dict[str, str] = {
    "product_discovery": "discovery produit",
    "feature_validation": "validation de fonctionnalité",
    "customer_retention": "rétention / churn",
    "pricing_research": "pricing",
    "positioning": "positionnement",
    "competitor_research": "recherche concurrentielle",
    "usability_testing": "ergonomie",
    "market_sizing": "dimensionnement du marché",
    "onboarding_optimization": "onboarding",
    "other": "recherche générale",
}


# Localised product-stage labels (English is the default in templates.py).
STAGE_LABELS_FR: dict[str, str] = {
    "idea": "idée",
    "mvp": "MVP",
    "growth": "croissance",
    "scale": "scale-up",
}
