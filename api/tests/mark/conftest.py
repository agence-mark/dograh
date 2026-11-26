"""Filet des tests du fork : aucune tâche de fond de nos modules ne survit à son test.

La boucle asyncio est partagée par toute la session (``asyncio_default_test_loop_scope=session``).
Une tâche laissée en vie par un test (une veille sur un faux moteur qui n'est jamais clos) tourne
donc pendant tous les tests suivants. Le 20/10/2026, une telle veille a tourné à vide sous un
``asyncio.sleep`` remplacé par un test de l'amont et porté le processus à plus de 100 Go.
"""

import sys
from pathlib import Path

import pytest

# ``scripts/mark`` est à la RACINE du dépôt ; lancés depuis ``api/``, les tests voyaient ``scripts`` sur ``api/scripts`` seul (modules introuvables : ``generer_openapi``,
# ``retirer_delai_modele_panne``). La racine est posée dans ``sys.path`` pour toute la suite.
_RACINE_DU_DEPOT = str(Path(__file__).resolve().parents[3])
if _RACINE_DU_DEPOT not in sys.path:
    sys.path.append(_RACINE_DU_DEPOT)

from api.services.analyse_run import silences  # noqa: E402
from api.services.etablissements import copie
from api.services.travail import retour

# Les registres de tâches de fond tenus au niveau du module par notre code.
_REGISTRES = (
    retour._VEILLES,
    silences._EN_COURS,
    copie._EN_ARRIERE_PLAN,
)


@pytest.fixture(autouse=True)
def _aucune_tache_de_fond_ne_survit():
    yield
    for registre in _REGISTRES:
        for tache in list(registre):
            if not tache.done():
                tache.cancel()

    # [.mark] builder partie 2, U5: the chat's background work (a dict of tasks, not a set).
    from api.services.builder import fil as builder_fil

    for tache in list(builder_fil._TACHES.values()):
        if not tache.done():
            tache.cancel()


@pytest.fixture(autouse=True)
def _sources_des_cerveaux_sur_cle_api_par_defaut(monkeypatch):
    """U12 : en production tout est sur Claude Code au départ ; les tests des autres lots jouent leurs cerveaux sur clé (un faux cerveau,
    aucun appel). Les tests de la source par défaut (``test_sources_u12``) remettent la vraie valeur."""
    from api.services import sources_cerveaux

    monkeypatch.setattr(sources_cerveaux, "DEFAUT", "cle_api")


@pytest.fixture(scope="session", autouse=True)
def _modules_inscrits():
    """Lot 8a (75) : le métier (l'allergie) s'inscrit au démarrage de chaque processus, plus à l'import ; la séance de tests se démarre comme l'API."""
    from api.services.modules import crochets

    crochets.au_demarrage()


# [.mark] builder-agent-vocal : la fixture ``monde`` (base en mémoire) est offerte à tous les tests du builder.
from api.tests.mark.builder_commun import monde  # noqa: E402, F401

# [.mark] Clôture A3 : la base migrée une fois par séance, copiée par ``base_prete`` (fixture de séance, visible de tous les tests de .mark).
from api.tests.mark.test_base_client import base_modele  # noqa: E402, F401
