"""[.mark] Builder : le cerveau au choix, par une seule couche d'appel (B4, B46, R0-2).

* ``reglages`` : fournisseur, modèle, clé (par référence au coffre), plafonds ; jamais la clé en clair ;
* ``appel``    : deux formats de fil sur ``httpx`` (compatible OpenAI ; Anthropic Messages), même flux,
                 mêmes erreurs normalisées ;
* ``factice``  : le cerveau des tests (aucun appel réel, aucune dépense).

Le code est agnostique du LLM : le moteur ne connaît que ``Cerveau.tour``.
"""
