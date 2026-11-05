"""[.mark] Chantier builder-agent-vocal : le moteur du builder d'agent vocal, côté serveur.

Un moteur, deux portes : l'écran de Dograh (route ``/builder``) et Claude Code (serveur MCP) appellent
les MÊMES actions (``actions/``). Partie 3, N1 : le builder peut tout faire, c'est la permission qui décide (``modes`` :
famille de l'action, mode du chat, rôle de la personne, carte d'autorisation que la personne clique).

* ``stock``         : lecture/écriture JSON dans ``organization_configurations`` (aucune migration) ;
* ``bibliotheque/`` : les recettes, versions, statuts, propositions, imports (lot 2) ;
* ``cerveau/``      : la couche d'appel unique sur ``httpx`` (OpenAI compatible, Anthropic) ;
* ``actions/``      : le registre des actions des deux portes ;
* ``moteur``        : la boucle de conversation (flux, cartes, opérations, plafond) ;
* ``contexte``      : l'historique par agent, le compactage, l'état relu sur le disque (B45) ;
* ``correction``    : la correction en plusieurs tours (B37) ;
* ``modes``         : les quatre modes du chat et la demande ponctuelle (N1).
"""
