"""Filet des tests du fork : aucune tâche de fond de nos modules ne survit à son test.

La boucle asyncio est partagée par toute la session (``asyncio_default_test_loop_scope=session``).
Une tâche laissée en vie par un test (une veille sur un faux moteur qui n'est jamais clos) tourne
donc pendant tous les tests suivants. Le 20/10/2026, une telle veille a tourné à vide sous un
``asyncio.sleep`` remplacé par un test de l'amont et porté le processus à plus de 100 Go.
"""

import pytest

from api.services.analyse_run import silences
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
