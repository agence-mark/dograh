"""[.mark] Builder partie 2, U3 sexies (E73 à E75) : Outils et Intégrations.

Tout vit dans ``definition.config`` des outils (aucune migration) :

* ``parametres`` : emplacement, valeurs permises, défaut d'un paramètre ;
* ``en_tetes`` : en-têtes texte, variable ou secret ;
* ``reponse`` : filtrage et copie dans la fiche ;
* ``simulation`` : réponses simulées, jamais servies en appel réel ;
* ``comportement`` : phrase avant, mode d'exécution, patience, repli ;
* ``essai`` : l'essai de tous les types ;
* ``statistiques`` : calculées à la volée sur les appels ;
* ``mcp`` : serveurs MCP (SSE, en-têtes, réglage par outil, test de connexion) ;
* ``identifiants`` : « utilisé par » et remplacement d'une valeur sans l'afficher.

⛔ Zéro vocabulaire métier. Aucun secret renvoyé ni journalisé.
"""
