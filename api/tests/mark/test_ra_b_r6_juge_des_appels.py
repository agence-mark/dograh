"""[.mark] RA-B, R6 : le juge des vrais appels reprend de Dograh ce qu'il fait mieux (audit 06 « Ce qu'on reprend »).

Part jugée, durée minimale, répondeurs exclus, réessais bornés avant « non vérifiable », critères du vécu de l'appelant dans la
grille, libellés « allumé mais pas réglé » et ``budget_atteint``. Éteint par défaut ; cerveaux factices, aucun appel réel."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.builder.cerveau import simules
from api.services.builder.cerveau.appel import ErreurCerveau
from api.services.builder.cerveau.factice import CerveauFactice, tour
from api.services.juge import appels, file, passes, tri
from api.services.juge import verdicts as v
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, monde  # noqa: F401 -- la fixture `monde`
from api.tests.mark.test_juge_unifie import (  # noqa: F401 -- la fixture `mondes` et les aides du fichier voisin
    LIGNES,
    _json,
    _juge,
    _run,
    mondes,
)

pytestmark = pytest.mark.asyncio


# --- la part jugée, la durée minimale, les répondeurs -------------------------------------------------------------------


def test_les_reglages_par_defaut_ne_changent_rien_et_les_bornes_tiennent():
    r = tri.lire(None)
    assert (r.part, r.duree_min_s, r.repondeurs_exclus) == (100, 0, False)
    assert tri.lire({"part": 0}).part == 1 and tri.lire({"part": 500}).part == 100
    assert tri.lire({"duree_min_s": -3}).duree_min_s == 0 and tri.lire({"duree_min_s": 99999}).duree_min_s == tri.DUREE_MIN_MAX_S
    assert tri.lire({"part": "x", "duree_min_s": None, "repondeurs_exclus": "oui"}).repondeurs_exclus is False


def test_la_part_jugee_est_stable_pour_un_meme_appel_et_proche_du_taux():
    r = tri.lire({"part": 30})
    runs = [SimpleNamespace(id=i, usage_info={}, gathered_context={}) for i in range(1, 2001)]
    premiers = [tri.decision(x, r)[0] for x in runs]
    assert premiers == [tri.decision(x, r)[0] for x in runs]  # rejuger un appel redonne la même réponse
    assert 0.25 < sum(premiers) / len(premiers) < 0.35
    assert all(tri.decision(x, tri.lire({"part": 100}))[0] for x in runs)


def test_un_appel_trop_court_ou_un_repondeur_n_est_pas_juge_avec_sa_raison():
    r = tri.lire({"duree_min_s": 10, "repondeurs_exclus": True})
    court = SimpleNamespace(id=1, usage_info={"call_duration_seconds": 3}, gathered_context={})
    assert tri.decision(court, r) == (False, "trop_court")
    repondeur = SimpleNamespace(id=2, usage_info={"call_duration_seconds": 40}, gathered_context={"mapped_call_disposition": "voicemail_detected"})
    assert tri.decision(repondeur, r) == (False, "repondeur")
    bon = SimpleNamespace(id=3, usage_info={"call_duration_seconds": 40}, gathered_context={})
    assert tri.decision(bon, r) == (True, None)
    inconnu = SimpleNamespace(id=4, usage_info=None, gathered_context=None)  # durée inconnue : on juge, jamais d'exclusion à l'aveugle
    assert tri.decision(inconnu, r) == (True, None)
    # répondeurs non exclus : jugé comme avant
    assert tri.decision(repondeur, tri.lire({})) == (True, None)


async def test_le_reglage_se_range_par_agent_et_garde_ce_qu_on_ne_touche_pas(mondes):
    await file.regler(ORG_CLIENT, AGENT, True, part=40, duree_min_s=8)
    await file.regler(ORG_CLIENT, AGENT, True, repondeurs_exclus=True)
    lu = await file.lire_reglages(ORG_CLIENT, AGENT)
    assert lu == {"actif": True, "part": 40, "duree_min_s": 8, "repondeurs_exclus": True, "vecu_eteints": []}
    assert await file.juge_des_vrais_appels(ORG_CLIENT, AGENT) is True


async def test_l_apres_appel_ne_juge_pas_un_appel_exclu_et_ecrit_pourquoi(mondes, monkeypatch):
    await file.regler(ORG_CLIENT, AGENT, True, duree_min_s=10)
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k")
    fabrique = AsyncMock()
    monkeypatch.setattr(simules, "cerveau_du_role", fabrique)
    await appels.apres_appel(_run(usage_info={"call_duration_seconds": 3}), ORG_CLIENT)
    assert fabrique.await_count == 0
    assert mondes.ecrits[0][1]["juge"]["etat"] == "trop_court"


# --- les réessais ----------------------------------------------------------------------------------------------------------


async def test_une_erreur_passagere_du_modele_est_reessayee_avant_le_non_verifiable(monkeypatch):
    monkeypatch.setattr(passes, "ATTENTES_DE_REESSAI_S", (0.0, 0.0))
    passagere = ErreurCerveau("indisponible", "busy", reessayable=True)
    cerveau = CerveauFactice(passagere, passagere, tour(_json()))
    rendu = await passes.juger(cerveau, LIGNES, ["Suit le parcours"])
    assert rendu["verdicts"][0]["verdict"] == "reussi" and rendu["reussi"] is True


async def test_apres_les_essais_le_reste_de_la_grille_passe_en_non_verifiable_et_une_erreur_definitive_n_est_pas_reessayee(monkeypatch):
    monkeypatch.setattr(passes, "ATTENTES_DE_REESSAI_S", (0.0, 0.0))
    passagere = ErreurCerveau("indisponible", "busy", reessayable=True)
    cerveau = CerveauFactice(passagere, passagere, passagere)  # 3 essais, aucun ne passe
    rendu = await passes.juger(cerveau, LIGNES, ["A", "B"])
    assert [x["verdict"] for x in rendu["verdicts"]] == ["non_verifiable", "non_verifiable"]
    definitive = CerveauFactice(ErreurCerveau("cle_absente", "no key"))
    rendu = await passes.juger(definitive, LIGNES, ["A"])
    assert rendu["verdicts"][0]["verdict"] == "non_verifiable" and len(definitive.requetes) == 1


# --- la grille : le vécu de l'appelant ---------------------------------------------------------------------------------


async def test_la_grille_porte_les_criteres_du_vecu_de_l_appelant():
    grille = await appels.grille()
    assert all(c in grille for c in v.CRITERES_DU_VECU)
    assert len(v.CRITERES_DU_VECU) == 5 and len(set(grille)) == len(grille)


# --- « allumé mais pas réglé » et le budget, dits à l'écran ----------------------------------------------------------------


async def test_l_etat_du_juge_dit_regle_eteint_ou_sans_cle(mondes, monkeypatch):
    from api.services.juge import etat

    _juge(monkeypatch, modele="openai/juge-m", identifiant="k", actif=True)
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(return_value=CerveauFactice()))
    assert await etat.etat_du_juge(ORG_CLIENT) == "regle"
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(return_value=None))
    assert await etat.etat_du_juge(ORG_CLIENT) == "sans_cle"
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k", actif=False)
    assert await etat.etat_du_juge(ORG_CLIENT) == "eteint"
    _juge(monkeypatch, source="claude_code", actif=False)
    assert await etat.etat_du_juge(ORG_CLIENT) == "regle"  # Claude Code : l'appel attend dans « À juger »


async def test_la_route_rend_les_filtres_et_l_etat_du_juge(mondes, monkeypatch):
    from types import SimpleNamespace as NS

    from api.routes import reglages_agent as route
    from api.tests.mark.builder_commun import utilisateur

    monkeypatch.setattr(route.db_client, "get_workflow", AsyncMock(side_effect=lambda wid, organization_id: NS(id=wid)))
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k", actif=False)
    moi = utilisateur(1, ORG_CLIENT)
    ecrit = await route.regler_le_juge_des_vrais_appels(
        AGENT, route.JugeDesVraisAppels(actif=True, part=25, duree_min_s=5, repondeurs_exclus=True), moi
    )
    assert (ecrit.actif, ecrit.part, ecrit.duree_min_s, ecrit.repondeurs_exclus) == (True, 25, 5, True)
    lu = await route.lire_le_juge_des_vrais_appels(AGENT, moi)
    assert lu.etat_du_juge == "eteint" and lu.part == 25  # allumé sur l'agent, mais le juge du Labo est éteint : l'écran le dit
    # un changement qui ne parle que de l'interrupteur garde les filtres
    ecrit = await route.regler_le_juge_des_vrais_appels(AGENT, route.JugeDesVraisAppels(actif=False), moi)
    assert ecrit.actif is False and ecrit.part == 25
    with pytest.raises(ValueError):
        route.JugeDesVraisAppels(actif=True, part=0)
