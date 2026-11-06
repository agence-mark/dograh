"""[.mark] Builder partie 3, lots 8 et 22 (§ 3 bis du plan) : les ÉTIQUETTES d'objets citées dans un prompt.

Un prompt cite ce qu'il utilise : ``{{outil:…}}``, ``{{etape:…}}``, ``{{agent:…}}``, ``{{equipe:…}}``, ``{{document:…}}``,
``{{phrase:…}}``, ``{{bloc:slug}}`` ou ``{{bloc:slug@v2}}``. Le texte enregistré reste du texte ; un RÉSOLVEUR remplace ces
étiquettes AVANT le moteur des variables (``utils/template_renderer.py``), jamais un second moteur. Aucune table : le
catalogue est calculé à partir des objets qui existent (``catalogue``), « Utilisé dans » par lecture des prompts.

* ``familles``    : pur, sans base (le motif, le découpage d'une clé) ; importé par le moteur, les contrôles, les citations ;
* ``resolution``  : pur, le texte au moment de l'appel à partir d'une ``Table`` ;
* ``table``       : la table d'un appel, lue une fois au départ (seulement les objets cités) ;
* ``catalogue``   : les objets citables d'une organisation, leur état ; le diagnostic des étiquettes d'un brouillon ;
* ``corrections`` : la correction en un clic, écrite dans le brouillon.
"""
