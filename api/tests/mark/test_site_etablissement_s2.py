"""[.mark] Partie 3, lot 15 (SE-29, S-2) : l'en-tête de l'éditeur du site nomme la fiche d'établissement de l'agent.

| Test | Ce qu'il prouve |
|---|---|
| nom | l'emplacement rend le nom de la fiche choisie par l'agent publié |
| sans fiche | un agent sans fiche : ``None`` (l'écran dit « sans lieu »), les fiches ne sont même pas lues |
| illisible | des fiches illisibles ou une fiche inconnue : ``None``, l'éditeur s'ouvre quand même, jamais un nom inventé |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.routes.agents_site import _nom_de_l_etablissement
from api.schemas.etablissements import CatalogueEtablissements, Etablissement

LECTURE = "api.services.etablissements.stockage.lire_etablissements_strict"


def _catalogue() -> CatalogueEtablissements:
    return CatalogueEtablissements(etablissements=[Etablissement(id="site-nord", nom="Agence Nord"), Etablissement(id="site-sud", nom="Agence Sud")])


def _definition(fiche) -> SimpleNamespace:
    return SimpleNamespace(workflow_configurations={"etablissement_id": fiche} if fiche is not None else {})


async def test_le_nom_de_la_fiche_choisie_par_l_agent_publie():
    with patch(LECTURE, new=AsyncMock(return_value=_catalogue())):
        assert await _nom_de_l_etablissement(_definition("site-sud"), 1) == "Agence Sud"
        assert await _nom_de_l_etablissement(_definition(" site-nord "), 1) == "Agence Nord"


async def test_un_agent_sans_fiche_ne_lit_pas_les_fiches():
    lecture = AsyncMock(return_value=_catalogue())
    with patch(LECTURE, new=lecture):
        assert await _nom_de_l_etablissement(_definition(None), 1) is None
        assert await _nom_de_l_etablissement(_definition(""), 1) is None
        assert await _nom_de_l_etablissement(None, 1) is None
    lecture.assert_not_called()


async def test_fiches_illisibles_ou_fiche_inconnue_rendent_rien():
    with patch(LECTURE, new=AsyncMock(side_effect=RuntimeError("base injoignable"))):
        assert await _nom_de_l_etablissement(_definition("site-nord"), 1) is None
    with patch(LECTURE, new=AsyncMock(return_value=_catalogue())):
        assert await _nom_de_l_etablissement(_definition("supprimee"), 1) is None
