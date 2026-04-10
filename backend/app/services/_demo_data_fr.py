"""French participant transcripts for the onboarding demo project. Auto-generated fixture content."""

PARTICIPANTS_FR = [
    {
        "display_name": "Amélie D.",
        "email": "amelie.demo@example.com",
        "profession": "Product Manager",
        "age_range": "30-39",
        "country": "France",
        "language": "fr",
        "turns": [
            {
                "question_index": 1,
                "is_follow_up": False,
                "question_text": "Peux-tu me raconter une journée de travail typique ? Quand travailles-tu seule et quand collabores-tu avec ton équipe ?",
                "response_transcript": "Alors, euh, ma journée elle est vraiment coupée en deux parce que mes ingés sont à San Francisco. Donc le matin, entre 8h30 et midi, c'est mon temps à moi. J'écris les specs, je regarde les retours utilisateurs, je prépare les décisions pour l'équipe. Et l'après-midi, à partir de 16h, c'est le créneau où on se chevauche avec la Californie, et là franchement ça devient du ping-pong non-stop. Standups, reviews, des questions qui tombent sur Slack toutes les deux minutes. Donc oui, j'ai un peu l'impression de faire deux métiers dans la même journée, un le matin, tranquille, et l'autre l'après-midi, beaucoup plus chaotique, je dirais.",
            },
            {
                "question_index": 1,
                "is_follow_up": True,
                "question_text": "Tu parles de protéger tes matinées. Comment tu communiques ça à ton équipe ?",
                "response_transcript": "Honnêtement, j'ai mis des blocs dans mon calendrier, « focus time », en rouge, très visible. Mais bon, dans la vraie vie, les gens les respectent à peu près une fois sur deux. Le truc c'est qu'il y a toujours quelqu'un pour dire « c'est juste cinq minutes » et évidemment c'est jamais cinq minutes. Donc ce qui a marché, c'est que j'ai arrêté de l'annoncer sur Slack et j'ai commencé à juste le faire, tu vois, je réponds pas avant onze heures et c'est tout. Au bout de trois semaines les gens se sont adaptés. C'est un peu bête mais annoncer une règle ça change rien, c'est le fait de la tenir qui change les choses.",
            },
            {
                "question_index": 2,
                "is_follow_up": False,
                "question_text": "Quels outils tu utilises pour rester alignée avec ton équipe, et comment ton stack d'outils a évolué jusqu'à aujourd'hui ?",
                "response_transcript": "Ouh là, alors on a Slack pour la discu du quotidien, Linear pour le suivi des tickets, Notion pour la doc, Figma pour les maquettes, Loom quand on veut faire passer un message un peu long sans imposer une réunion. Et Google Meet pour les calls. Donc euh, six outils, minimum. Au début on était sur trois, c'était Slack, Jira et Google Docs. Et puis chaque nouveau responsable arrive avec son outil préféré et voilà, ça s'empile. Le problème c'est pas vraiment qu'on en ait trop, le problème c'est que rien ne parle à rien. Je passe un temps fou à faire des copier-coller d'un outil à l'autre pour que tout le monde voie la même info.",
            },
            {
                "question_index": 2,
                "is_follow_up": True,
                "question_text": "Tu dis que rien ne parle à rien. Tu peux me donner un exemple concret ?",
                "response_transcript": "Ouais, genre typiquement, on prend une décision produit dans un call le mardi, je la note dans Notion, je la copie dans Linear sur le ticket correspondant, et puis trois jours plus tard un ingé me demande sur Slack « au fait on avait décidé quoi pour le flow d'onboarding ? ». Et là je me rends compte que la décision elle est à trois endroits et qu'aucun des trois est l'endroit où il avait cherché. C'est une perte de temps monumentale. J'ai l'impression de passer la moitié de mes journées à être un moteur de recherche humain pour des choses qu'on a déjà tranchées. Franchement c'est ça qui m'épuise le plus, plus que la charge de travail en elle-même.",
            },
            {
                "question_index": 3,
                "is_follow_up": False,
                "question_text": "Raconte-moi un moment récent où tu t'es sentie bloquée ou frustrée en travaillant en équipe. Que s'est-il passé ?",
                "response_transcript": "Alors il y a deux semaines, on devait lancer une nouvelle feature de notifications. Je pensais qu'on avait acté le périmètre la semaine d'avant dans un call avec le lead ingé. Et le jour du kickoff je découvre que lui avait retenu une version différente de la décision, et qu'il avait déjà commencé à coder quelque chose qui correspondait pas du tout à ce que je pensais. Et on s'est retrouvés à devoir re-discuter pendant quarante-cinq minutes, avec six personnes dans la salle, pour re-aligner sur un truc qu'on croyait avoir tranché. Ce qui m'a frustrée c'est que la décision, elle existait nulle part par écrit. On avait juste tous les deux nos souvenirs du call, et nos souvenirs étaient différents.",
            },
            {
                "question_index": 3,
                "is_follow_up": True,
                "question_text": "Est-ce que tu as changé quelque chose après cet incident ?",
                "response_transcript": "Oui, enfin j'ai essayé. Maintenant à la fin de chaque call où on prend une décision, je prends deux minutes pour écrire un mini résumé dans le thread Slack du projet, genre « décision : on fait X, contexte : Y, prochaine étape : Z ». C'est pas glamour mais au moins il y a une trace. Le souci c'est que c'est moi qui le fais, et si je suis pas là ça se fait pas. Donc en vrai c'est pas une solution d'équipe, c'est juste un pansement perso. Ce qu'il faudrait c'est que l'outil le fasse automatiquement, ou que ce soit un réflexe partagé par tout le monde. Mais pour l'instant c'est moi, toute seule, en mode scribe.",
            },
            {
                "question_index": 4,
                "is_follow_up": False,
                "question_text": "Quand tu as besoin de quelque chose d'un collègue dans un autre fuseau horaire, c'est quoi ta méthode ?",
                "response_transcript": "Alors j'ai appris à la dure à jamais envoyer juste « t'as deux minutes ? », parce que le temps qu'ils se réveillent et qu'ils répondent, j'ai déjà perdu huit heures. Donc maintenant j'écris un message super structuré, avec le contexte, ce que je demande précisément, et ce dont j'ai besoin comme réponse, idéalement avec des options genre A, B ou C pour qu'ils aient juste à cocher. Et je l'envoie avant de me coucher. Au final je trouve que ça m'oblige à clarifier ma pensée avant de demander, et du coup les échanges sont beaucoup plus efficaces que quand on est dans le même bureau. C'est un peu paradoxal mais le décalage horaire nous a rendus plus disciplinés.",
            },
            {
                "question_index": 4,
                "is_follow_up": True,
                "question_text": "Tu dis que le décalage vous a rendus plus disciplinés. C'est une bonne chose au final ?",
                "response_transcript": "Honnêtement, oui. Enfin pas tout le temps, hein, il y a des jours où je voudrais juste pouvoir me tourner vers quelqu'un et régler un truc en trente secondes. Mais globalement, le fait qu'on puisse pas juste s'interrompre, ça force à mieux écrire, à mieux documenter, à mieux décider avant de demander. Les équipes colocalisées que je connais, elles ont tendance à improviser beaucoup plus, et du coup à avoir plus de malentendus parce que rien est écrit. Nous on est obligés d'être rigoureux sinon ça marche pas. Donc ouais, je dirais que la contrainte nous a améliorés, même si certains jours c'est vraiment pénible à vivre.",
            },
            {
                "question_index": 5,
                "is_follow_up": False,
                "question_text": "Si tu pouvais faire disparaître un seul problème dans ta manière de bosser en équipe, ce serait quoi et pourquoi ?",
                "response_transcript": "Sans hésiter, le fait que les décisions disparaissent. C'est vraiment ma plus grosse douleur. On passe des heures à débattre, à peser les options, à trancher, et puis trois semaines plus tard personne ne se souvient pourquoi on a fait ce choix, et on refait le même débat. C'est épuisant intellectuellement, et c'est démoralisant aussi parce que tu as l'impression de jamais avancer. Si j'avais une baguette magique, j'aimerais un système où dès qu'une décision est prise, dans un call ou sur Slack ou n'importe où, elle est capturée automatiquement avec son contexte, et elle est retrouvable en deux secondes. Ça changerait complètement notre manière de travailler, j'en suis sûre.",
            },
        ],
    },
    {
        "display_name": "Lucas M.",
        "email": "lucas.demo@example.com",
        "profession": "Designer",
        "age_range": "25-29",
        "country": "France",
        "language": "fr",
        "turns": [
            {
                "question_index": 1,
                "is_follow_up": False,
                "question_text": "Peux-tu me raconter une journée de travail typique ? Quand travailles-tu seul et quand collabores-tu avec ton équipe ?",
                "response_transcript": "Ouais alors moi c'est assez simple, je bosse sur une app mobile grand public, et en gros mes matinées je les passe dans Figma, tout seul, à pousser des écrans, itérer, tester des trucs. Et l'après-midi c'est plutôt les moments où je discute avec les devs, le PM, parfois le copain de Montréal qui est dans la même équipe design. Donc en gros, le matin c'est du solo créatif et l'après-midi c'est du collectif. Mais franchement y a plein de jours où ça se mélange, genre t'es en plein flow et y a un dev qui te ping sur Slack parce qu'il a un doute sur un composant, et du coup tu sors de ton truc et tu reviens plus jamais. C'est la vie du designer quoi.",
            },
            {
                "question_index": 1,
                "is_follow_up": True,
                "question_text": "Tu dis que tu sors de ton flow et tu reviens plus jamais. C'est un vrai problème pour toi ?",
                "response_transcript": "Ah ouais carrément, c'est le truc qui me tue le plus. Genre, un écran un peu complexe ça me prend au moins une heure à bien poser dans ma tête, et si je suis interrompu au bout de vingt minutes, faut que je recommence le process mental de zéro. Du coup j'ai testé de mettre mon Slack en mode « absent » le matin, genre jusqu'à onze heures, mais les gens me pingent quand même. Et là tu te dis, soit je réponds et je perds mon focus, soit je réponds pas et je passe pour celui qui ignore tout le monde. C'est un peu une impasse sociale en fait. Parce que personne veut être le mec relou qui répond pas aux questions.",
            },
            {
                "question_index": 2,
                "is_follow_up": False,
                "question_text": "Quels outils tu utilises pour rester aligné avec ton équipe, et comment ton stack d'outils a évolué jusqu'à aujourd'hui ?",
                "response_transcript": "Alors Figma évidemment pour le design, Slack pour tout le reste de la com, Linear pour le suivi des tickets, Notion pour la doc, et de temps en temps Loom quand je veux expliquer un flow sans me taper un call. On a testé genre dix autres trucs au fil du temps, y a eu une période Miro, une période Whimsical, un moment où le PM voulait qu'on mette tout dans Coda, franchement ça a été un peu le bazar. Du coup maintenant on essaie de limiter, mais c'est dur parce que chaque nouvelle personne qui arrive ramène ses habitudes. Moi ce qui me gave, c'est pas le nombre d'outils, c'est plutôt que les conversations importantes elles sont éclatées entre Slack, les commentaires Figma et les tickets Linear, et on sait plus où regarder.",
            },
            {
                "question_index": 3,
                "is_follow_up": False,
                "question_text": "Raconte-moi un moment récent où tu t'es senti bloqué ou frustré en travaillant en équipe. Que s'est-il passé ?",
                "response_transcript": "Ouais y a un truc qui m'a vraiment saoulé la semaine dernière. J'avais passé genre trois jours sur une refonte de l'écran de profil, j'étais content du résultat, et dans le stand-up du jeudi le lead dev me dit « ah mais attends, t'étais pas au courant qu'on change la brique d'auth le mois prochain ? ». Et non, j'étais pas au courant, parce que la conversation s'était passée dans un call backend auquel j'étais pas invité. Donc en gros j'ai bossé trois jours sur un écran qui allait être obsolète. Et le pire c'est que personne l'avait fait exprès, c'est juste que l'info elle circulait pas. Ça j'ai trouvé ça vraiment démoralisant, parce que c'était du temps et de l'énergie pour rien.",
            },
            {
                "question_index": 3,
                "is_follow_up": True,
                "question_text": "Tu as l'impression que ce genre de truc arrive souvent ?",
                "response_transcript": "Pas tous les jours mais genre une fois par mois c'est sûr. Et chaque fois c'est la même histoire, une info qui a été partagée dans un canal où t'étais pas, ou dans un call auquel t'étais pas invité, et personne pense à te la transmettre parce que pour eux c'est évident. Moi je pense que le vrai problème c'est qu'on a trop misé sur l'async façon « tout le monde lit tout, tout est écrit », et en vrai personne a le temps de tout lire. Y a des moments où franchement un petit call de quinze minutes ça réglerait plus de choses que trois jours de messages Slack. Mais c'est devenu limite ringard de proposer une réu, tu passes pour quelqu'un d'inefficace.",
            },
            {
                "question_index": 4,
                "is_follow_up": False,
                "question_text": "Quand tu as besoin de quelque chose d'un collègue dans un autre fuseau horaire, c'est quoi ta méthode ?",
                "response_transcript": "Alors du coup j'ai un pote designer à Montréal, lui il est six heures derrière. Ma technique c'est genre, je lui enregistre un Loom. Je fais défiler la maquette, j'explique ce que je voudrais, je pose une ou deux questions précises à la fin. Et il regarde ça le matin pour lui, qui est déjà mon après-midi, et il me répond pareil en Loom ou en commentaires Figma. Franchement ça marche super bien, mieux qu'avec des gens qui sont à Paris parfois. Parce que Loom ça t'oblige à être clair, tu peux pas juste partir dans tous les sens comme dans un call en direct. Et lui il peut regarder quand ça l'arrange, mettre pause, revenir. C'est un mode de collaboration que j'ai appris à aimer en fait.",
            },
            {
                "question_index": 4,
                "is_follow_up": True,
                "question_text": "Tu préfères bosser avec lui qu'avec les gens de Paris ? C'est fort comme truc.",
                "response_transcript": "Ouais enfin faut nuancer, hein. Avec les gens de Paris y a plein de trucs cool, on peut aller boire un café, on se connaît mieux humainement. Mais en termes d'efficacité de collaboration pure, avec le copain de Montréal on perd moins de temps. Parce qu'on est obligés d'être carrés. Avec les gens d'ici on se dit toujours « on en parle tout à l'heure », et puis tout à l'heure arrive, on en parle deux minutes entre deux trucs, rien est noté, et le lendemain on se souvient plus. Alors qu'avec lui tout est dans Loom ou dans Figma, et je peux retrouver la conversation trois semaines plus tard. C'est ça que je voulais dire par « plus disciplinés ».",
            },
            {
                "question_index": 5,
                "is_follow_up": False,
                "question_text": "Si tu pouvais faire disparaître un seul problème dans ta manière de bosser en équipe, ce serait quoi et pourquoi ?",
                "response_transcript": "Franchement, moi ce serait la religion du tout-async. J'aimerais qu'on ait le droit de dire « là on a besoin d'un call de vingt minutes » sans se sentir coupable. Parce que là c'est devenu un truc où si tu proposes une réu t'es vu comme quelqu'un qui fait perdre du temps aux autres, et du coup tout le monde préfère écrire des pavés sur Slack qui prennent deux heures à pondre et que personne lit vraiment. Y a des moments où parler cinq minutes en vrai c'est juste plus efficace, et on s'interdit de le faire pour des raisons culturelles un peu bizarres. Donc j'aimerais qu'on retrouve un équilibre sain entre les deux, sans dogme ni dans un sens ni dans l'autre.",
            },
        ],
    },
    {
        "display_name": "Claire B.",
        "email": "claire.demo@example.com",
        "profession": "UX Researcher",
        "age_range": "30-39",
        "country": "Belgique",
        "language": "fr",
        "turns": [
            {
                "question_index": 1,
                "is_follow_up": False,
                "question_text": "Peux-tu me raconter une journée de travail typique ? Quand travailles-tu seule et quand collabores-tu avec ton équipe ?",
                "response_transcript": "Alors mes journées sont assez structurées parce que je gère plusieurs études en parallèle. Le matin je préfère bloquer deux heures pour analyser les données des interviews récentes, c'est un travail qui demande beaucoup de concentration. Ensuite vers dix heures et demie, j'ai en général un ou deux calls avec des product managers qui veulent les résultats d'une étude. L'après-midi, c'est souvent les sessions d'interview elles-mêmes avec des utilisateurs, ou alors la préparation des prochaines. Et comme on a un designer basé à Melbourne, il m'arrive d'avoir un call tard le soir ou très tôt le matin quand on a besoin de se parler en direct. Mais ça reste assez rare, on essaie de faire la plupart des échanges en asynchrone.",
            },
            {
                "question_index": 2,
                "is_follow_up": False,
                "question_text": "Quels outils tu utilises pour rester alignée avec ton équipe, et comment ton stack d'outils a évolué jusqu'à aujourd'hui ?",
                "response_transcript": "On a Slack pour la communication quotidienne, Notion pour la documentation des études, Dovetail pour l'analyse qualitative, Figma pour voir les maquettes en discussion, et Linear pour le suivi produit. Quand je suis arrivée il y a trois ans on était sur Confluence et c'était un peu la jungle, on passait notre temps à chercher des documents. On a migré vers Notion, ce qui a beaucoup aidé au début, mais aujourd'hui je commence à retrouver le même problème, c'est-à-dire que l'information est bien rangée mais personne ne la consulte vraiment. Les gens préfèrent poser la question sur Slack plutôt que de chercher. Donc la vraie difficulté ce n'est pas l'outil, c'est la culture de consultation, et ça c'est beaucoup plus dur à changer.",
            },
            {
                "question_index": 2,
                "is_follow_up": True,
                "question_text": "Tu dis que personne ne consulte la doc. Ça t'affecte particulièrement en tant que chercheuse ?",
                "response_transcript": "Oui, et c'est probablement ma plus grande frustration. Je passe des semaines sur une étude, je produis un rapport détaillé, je présente les résultats dans une réunion, et trois mois plus tard je vois passer une décision produit qui va à l'encontre de ce qu'on avait découvert. Je pose la question, et les gens me disent « ah, on savait pas », ou « on s'en souvenait plus ». Et là je me rends compte que mes rapports, ils sont dans Notion, quelque part, mais personne ne pense à aller les rechercher au moment où ils prennent une décision. Les insights, ils meurent dans le rapport. C'est un problème vraiment structurel de la recherche utilisateur dans les boîtes produits, et je n'ai pas trouvé de solution magique.",
            },
            {
                "question_index": 3,
                "is_follow_up": False,
                "question_text": "Raconte-moi un moment récent où tu t'es sentie bloquée ou frustrée en travaillant en équipe. Que s'est-il passé ?",
                "response_transcript": "Il y a trois semaines, on a lancé une nouvelle fonctionnalité de paiement. Et j'avais fait une étude six mois plus tôt qui montrait très clairement que les utilisateurs avaient besoin d'une confirmation explicite avant certaines transactions. C'était dans mon rapport, c'était documenté. Et à la livraison, la confirmation n'était pas là. J'ai demandé pourquoi, et le PM m'a répondu très honnêtement qu'il n'était pas au courant, parce qu'à l'époque de l'étude il n'était pas encore dans l'équipe. Donc l'information s'est perdue dans la transition. Et on se retrouve à devoir refaire le travail, remonter la décision, alors qu'on avait déjà la réponse. C'est typiquement le genre de situation qui me fait me sentir inutile, parce que mon travail n'a servi à rien.",
            },
            {
                "question_index": 3,
                "is_follow_up": True,
                "question_text": "Tu as l'impression que c'est un problème spécifique à la recherche, ou c'est plus général ?",
                "response_transcript": "C'est plus général je pense, mais ça frappe particulièrement la recherche parce que nos livrables sont denses et ils demandent de l'effort pour être consommés. Une décision prise dans un call, elle disparaît aussi, c'est la même dynamique. Ce que j'ai observé c'est que dans notre boîte, il y a très peu de culture de « mémoire d'équipe ». On accumule des connaissances, mais on n'a pas de rituel pour les rappeler au bon moment. Les gens partent, les gens arrivent, et chaque nouvelle personne recommence un peu de zéro. Je pense que c'est un problème qui n'est pas technique, c'est vraiment une question de pratiques managériales, et ça se règle pas en installant un nouvel outil.",
            },
            {
                "question_index": 4,
                "is_follow_up": False,
                "question_text": "Quand tu as besoin de quelque chose d'un collègue dans un autre fuseau horaire, c'est quoi ta méthode ?",
                "response_transcript": "Avec notre designer à Melbourne, il y a à peu près neuf heures de décalage, donc le chevauchement est très faible. Ce que je fais, c'est que j'écris des messages très précis, en incluant tout le contexte dont il a besoin pour répondre sans avoir à me reposer une question. Je liste ce que je sais, ce dont je ne suis pas sûre, et ce que j'attends de lui, idéalement avec une deadline. Et je joins des liens vers les documents pertinents. Ça prend plus de temps à écrire, mais ça évite les allers-retours qui peuvent durer trois jours si on se rate. Et étonnamment, cette discipline que m'impose le décalage horaire, elle a déteint sur ma façon de communiquer avec les collègues locaux aussi.",
            },
            {
                "question_index": 4,
                "is_follow_up": True,
                "question_text": "C'est intéressant, cette idée que la contrainte a amélioré tes pratiques. Tu peux développer ?",
                "response_transcript": "Oui, en fait je pense que quand tu peux pas juste te tourner vers quelqu'un et lui demander, tu es obligée de formuler ta question clairement, et rien que le fait de la formuler ça te fait parfois trouver la réponse toute seule. Et puis ça oblige à documenter, parce que sinon l'autre personne est paumée. Moi j'ai remarqué que depuis que je bosse avec Melbourne, mes messages Slack avec les gens de Bruxelles sont devenus beaucoup plus structurés aussi. Je fais plus de efforts, je donne plus de contexte, je suis plus explicite. Au final la contrainte du fuseau horaire m'a rendue meilleure communicante, c'est un peu contre-intuitif mais c'est vraiment ce que j'ai observé chez moi et chez d'autres aussi.",
            },
            {
                "question_index": 5,
                "is_follow_up": False,
                "question_text": "Si tu pouvais faire disparaître un seul problème dans ta manière de bosser en équipe, ce serait quoi et pourquoi ?",
                "response_transcript": "Moi ce serait que les insights et les décisions ne se perdent pas. C'est vraiment le cœur de ma frustration, et je pense que c'est le cœur de la frustration de beaucoup de gens. On a des outils pour stocker l'information, mais on n'a pas de mécanisme pour la faire remonter au bon moment. J'aimerais que quand quelqu'un prend une décision produit, les études passées pertinentes soient automatiquement rappelées, ou que quand on débat d'un sujet, l'historique des décisions précédentes soit visible. Parce que là on passe notre temps à redécouvrir des choses qu'on savait déjà. Et ça, ce n'est pas une question de travailler plus, c'est une question de mieux se souvenir collectivement. C'est ça qui changerait vraiment la vie de mon équipe.",
            },
        ],
    },
]

NOTABLE_QUOTES_FR = [
    {
        "participant_index": 0,
        "turn_index": 1,
        "text": "annoncer une règle ça change rien, c'est le fait de la tenir qui change les choses",
        "theme_hint": "modelled_behaviour",
    },
    {
        "participant_index": 0,
        "turn_index": 3,
        "text": "J'ai l'impression de passer la moitié de mes journées à être un moteur de recherche humain pour des choses qu'on a déjà tranchées",
        "theme_hint": "decision_capture",
    },
    {
        "participant_index": 0,
        "turn_index": 6,
        "text": "le décalage horaire nous a rendus plus disciplinés",
        "theme_hint": "cross_timezone_health",
    },
    {
        "participant_index": 1,
        "turn_index": 1,
        "text": "soit je réponds et je perds mon focus, soit je réponds pas et je passe pour celui qui ignore tout le monde. C'est un peu une impasse sociale",
        "theme_hint": "focus_time",
    },
    {
        "participant_index": 1,
        "turn_index": 4,
        "text": "c'est devenu limite ringard de proposer une réu, tu passes pour quelqu'un d'inefficace",
        "theme_hint": "tool_sprawl",
    },
    {
        "participant_index": 2,
        "turn_index": 2,
        "text": "Les insights, ils meurent dans le rapport",
        "theme_hint": "decision_capture",
    },
]
