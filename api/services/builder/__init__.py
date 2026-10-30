"""[.mark] Chantier builder-agent-vocal : le moteur du builder d'agent vocal, côté serveur.

Un moteur, deux portes : l'écran de Dograh (route ``/builder``) et Claude Code (serveur MCP) appellent
les MÊMES actions (``actions/``). Rien ici ne publie, ne supprime, n'écrit une recette : le builder
propose, crée des candidats et prépare un brouillon ; le reste est un clic humain.

* ``stock``         : lecture/écriture JSON dans ``organization_configurations`` (aucune migration) ;
* ``bibliotheque/`` : les recettes, versions, statuts, propositions, imports (lot 2) ;
* ``cerveau/``      : la couche d'appel unique sur ``httpx`` (OpenAI compatible, Anthropic) ;
* ``actions/``      : le registre des actions des deux portes ;
* ``moteur``        : la boucle de conversation (flux, cartes, opérations, plafond) ;
* ``contexte``      : l'historique par agent, le compactage, l'état relu sur le disque (B45) ;
* ``correction``    : la correction en plusieurs tours (B37).
"""
