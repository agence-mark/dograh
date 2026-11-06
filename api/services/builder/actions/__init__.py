"""[.mark] Builder : les actions, communes à l'écran et à Claude Code (voir ``registre``).

Importer ce paquet remplit ``REGISTRE`` (une seule fois, à l'import).
"""

from api.services.builder.actions import (  # noqa: F401 -- l'import inscrit les actions
    bibliotheque,
    construction,
    fiche_et_reglages,
    points_d_entree,
    controle_et_tests,  # lots 5 et 6 : remplit les points d'entree du controle, de l'essai et des tests
)
from api.services.builder.actions import objets  # noqa: F401,E402 -- B48 : les objets de l'agent
from api.services.builder.actions import etiquettes  # noqa: F401,E402 -- U3 (E30) : les étiquettes des agents
from api.services.builder.actions import contexte_client  # noqa: F401,E402 -- lot 3 : après points_d_entree, qu'il remplit
from api.services.builder.actions import dialogue  # noqa: F401,E402 -- U5 (E26) : la carte plan et la carte question
from api.services.builder.actions import methode  # noqa: F401,E402 -- U7 (M2) : builder_methode et builder_conventions pour Claude Code
from api.services.builder.actions import juge  # noqa: F401,E402 -- U6 : juge_a_faire, juge_lire, juge_ecrire pour Claude Code
from api.services.builder.actions import publication  # noqa: F401,E402 -- U11 : contrôles avant publication et attaques
from api.services.builder.actions import rapport_et_tests  # noqa: F401,E402 -- C2 : rapport, dépense, tests lus, correction
from api.services.builder.actions import recettes  # noqa: F401,E402 -- lot M (7) : recette_lire
from api.services.builder.actions import sauvegarde_et_graphe  # noqa: F401,E402 -- lot M : sauvegarde avant modification, rendu du graphe
from api.services.builder.actions import branches  # noqa: F401,E402 -- SA-L3d : branches d'agent et versions des outils
from api.services.builder.actions import groupes  # noqa: F401,E402 -- L5b : le builder lit, crée et règle un groupe d'agents
from api.services.builder.actions import etiquettes_prompt  # noqa: F401,E402 -- lots 8 et 22 : étiquettes d'objets et blocs
from api.services.builder.actions import lecture_fork  # noqa: F401,E402 -- U12 (I1) : lire le fork dans Claude Code
from api.services.builder.actions import appelant_claude_code  # noqa: F401,E402 -- U12 (I1) : l'appelant simulé joué par Claude Code
from api.services.builder.actions import gestes  # noqa: F401,E402 -- N1 : publier, fusionner, archiver... entrés au registre
from api.services.builder.actions import entreprise  # noqa: F401,E402 -- N1 (sous-lot 5) : établissements, phrases, annonce, listes, équipe, campagnes, téléphonie
from api.services.builder.actions import reglages_organisation  # noqa: F401,E402 -- N2 : panne, après l'appel, vérification, planificateur, fenêtre du run, conservation
from api.services.builder.actions import outil_modifier  # noqa: F401,E402 -- N2 : modifier les réglages d'un outil existant
from api.services.builder import sous_agents  # noqa: F401,E402 -- C2 (E96) : l'action deleguer
from api.services.builder.actions.registre import (  # noqa: F401
    REGISTRE,
    Action,
    Contexte,
    executer,
    outils_du_moteur,
)
