"""[.mark] Clôture, lot C : chaque critère du vécu de l'appelant est activable un par un, par agent.

| Test | Ce qu'il prouve |
|---|---|
| défaut | rien d'éteint : les cinq critères sont jugés, comme avant |
| réglage | un critère éteint n'est plus dans la grille de CET agent, les autres restent ; un autre agent garde les cinq |
| lecture | un identifiant inconnu ou une valeur illisible est ignoré (jamais une grille vidée par une faute de frappe) |
| moteur | l'après-appel juge avec la grille réduite (ce que reçoit le modèle), pas seulement l'écran |
| route | le schéma de la route refuse un identifiant inconnu (422) et en accepte cinq au plus |
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api.services.builder.cerveau import simules
from api.services.juge import appels, file, passes, tri
from api.services.juge import verdicts as v
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, monde  # noqa: F401
from api.tests.mark.test_juge_unifie import LIGNES, _juge, _run, mondes  # noqa: F401

pytestmark = pytest.mark.asyncio


def test_un_identifiant_par_critere_et_rien_d_eteint_par_defaut():
    assert len(v.IDS_DU_VECU) == len(v.CRITERES_DU_VECU) == 5
    assert tri.lire({}).vecu_eteints == ()
    assert list(v.CRITERES_DU_VECU_PAR_ID.values()) == list(v.CRITERES_DU_VECU)


def test_la_lecture_ignore_l_inconnu_et_l_illisible():
    assert tri.lire({"vecu_eteints": ["boucle", "inconnu", 3, None, "boucle"]}).vecu_eteints == ("boucle",)
    assert tri.lire({"vecu_eteints": "boucle"}).vecu_eteints == ()
    assert tri.lire({"vecu_eteints": {"boucle": True}}).vecu_eteints == ()
    assert tri.lire({"vecu_eteints": ["ecoute", "frustration"]}).vecu_eteints == ("frustration", "ecoute")  # l'ordre des critères


async def test_un_critere_eteint_sort_de_la_grille_de_cet_agent_seulement(mondes):  # noqa: F811
    await file.regler(ORG_CLIENT, AGENT, True, vecu_eteints=["boucle", "blanc"])
    assert (await file.lire_reglages(ORG_CLIENT, AGENT))["vecu_eteints"] == ["blanc", "boucle"]
    reduite = await appels.grille(ORG_CLIENT, AGENT)
    assert v.CRITERES_DU_VECU_PAR_ID["boucle"] not in reduite and v.CRITERES_DU_VECU_PAR_ID["blanc"] not in reduite
    assert all(v.CRITERES_DU_VECU_PAR_ID[i] in reduite for i in ("frustration", "gene_machine", "ecoute"))
    autre = await appels.grille(ORG_CLIENT, AGENT + 1)
    assert all(c in autre for c in v.CRITERES_DU_VECU)  # un autre agent : les cinq
    sans_agent = await appels.grille()
    assert all(c in sans_agent for c in v.CRITERES_DU_VECU)  # sans agent : les cinq
    # ce qu'on ne donne pas reste ; les rallumer tous
    await file.regler(ORG_CLIENT, AGENT, True, part=50)
    assert (await file.lire_reglages(ORG_CLIENT, AGENT))["vecu_eteints"] == ["blanc", "boucle"]
    await file.regler(ORG_CLIENT, AGENT, True, vecu_eteints=[])
    rallumes = await appels.grille(ORG_CLIENT, AGENT)
    assert all(c in rallumes for c in v.CRITERES_DU_VECU)


async def test_l_apres_appel_juge_avec_la_grille_reduite(mondes, monkeypatch):  # noqa: F811
    await file.regler(ORG_CLIENT, AGENT, True, vecu_eteints=["frustration"])
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k")
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(return_value=object()))
    vues = []

    async def juger(cerveau, lignes, grille, **options):
        vues.append(list(grille))
        return {"verdicts": [], "reussi": True}

    monkeypatch.setattr(passes, "juger", juger)
    await appels.apres_appel(_run(), ORG_CLIENT)
    assert vues, "le juge n'a pas été appelé"
    assert v.CRITERES_DU_VECU_PAR_ID["frustration"] not in vues[0]
    assert v.CRITERES_DU_VECU_PAR_ID["boucle"] in vues[0]


def test_le_schema_de_la_route_refuse_un_identifiant_inconnu():
    from pydantic import ValidationError

    from api.routes.reglages_agent import JugeDesVraisAppels

    assert JugeDesVraisAppels(vecu_eteints=["boucle"]).vecu_eteints == ["boucle"]
    with pytest.raises(ValidationError):
        JugeDesVraisAppels(vecu_eteints=["frustre"])
    with pytest.raises(ValidationError):
        JugeDesVraisAppels(vecu_eteints=["boucle"] * 6)
