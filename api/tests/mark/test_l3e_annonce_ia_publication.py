"""[.mark] Clôture, lot B (D1, D2) : la ligne « Annonce » de « Prêt à publier » est un contrôle RÉGLABLE (éteint ou prévient), plus un blocage fixe.

| Test | La garantie |
|---|---|
| texte par défaut | la ligne est faite et ne gêne pas la publication |
| annonce éteinte ou vide | le contrôle prévient (jamais ne bloque) et la ligne mène au thème Phrases ; la publication reste possible |
| réglable | « éteint » retire la ligne ; « bloque » n'existe pas pour ce contrôle (réglage refusé) |
| D2 | une voix temps réel sans accueil écrit : le contrôle prévient (rien n'est injecté par le code) ; avec un accueil écrit, rien à dire |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.schemas.publication import ControlesDePublication
from api.services.builder.tests_agent import publication
from api.services.phrases.catalogue import ANNONCE_IA
from api.services.publication import controles
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, monde, sans_les_lignes_de_pret  # noqa: F401
from api.tests.mark.test_builder_tests_agent import banc  # noqa: F401
from api.tests.mark.test_pret_a_publier import _graphe


def _brouillon(configurations):
    return SimpleNamespace(workflow_json=_graphe(), version_number=2, workflow_configurations=configurations)


def _base(**en_plus):
    return sans_les_lignes_de_pret({"moteur_sortie_d_impasse": False, **en_plus})


ETEINTE = {"phrases_regles": [{"motif": ANNONCE_IA, "portee": "agent", "variantes": [], "active": False}]}


async def test_le_texte_par_defaut_est_fait_et_ne_bloque_pas(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    vue = await controles.evaluer(wf, _brouillon(_base()), ORG_CLIENT)
    bloc = next(c for c in vue["controles"] if c["cle"] == "annonce_ia")
    assert (bloc["position"], bloc["statut"], bloc["problemes"]) == ("previent", "ok", [])
    ligne = next(l for l in vue["lignes"] if l["id"] == "annonce_ia")
    assert ligne["etat"] == "fait" and ligne["theme"] == "phrases"
    assert await publication.verifier_avant_publication(wf, _brouillon(_base()), ORG_CLIENT) is None


async def test_une_annonce_eteinte_previent_sans_bloquer_et_la_ligne_mene_au_theme_phrases(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    vue = await controles.evaluer(wf, _brouillon(_base(**ETEINTE)), ORG_CLIENT)
    bloc = next(c for c in vue["controles"] if c["cle"] == "annonce_ia")
    assert bloc["statut"] == "alerte" and vue["bloque"] is False and "off or empty" in bloc["problemes"][0]
    ligne = next(l for l in vue["lignes"] if l["id"] == "annonce_ia")
    assert ligne["theme"] == "phrases" and ligne["etat"] != "fait"
    assert await publication.verifier_avant_publication(wf, _brouillon(_base(**ETEINTE)), ORG_CLIENT) is None  # la publication reste possible


async def test_le_controle_se_regle_eteint_ou_previent_jamais_bloque(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    eteint = _base(**ETEINTE, publication={"controles": {"annonce_ia": "eteint"}})
    vue = await controles.evaluer(wf, _brouillon(eteint), ORG_CLIENT)
    bloc = next(c for c in vue["controles"] if c["cle"] == "annonce_ia")
    assert bloc["position"] == "eteint" and bloc["statut"] == "eteint" and bloc["problemes"] == []
    with pytest.raises(ValueError):
        ControlesDePublication.model_validate({"annonce_ia": "bloque"})


def test_d2_une_voix_temps_reel_sans_accueil_ecrit_previent():
    sans_accueil = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "Accueil", "greeting_type": "audio"}}]}
    avec_accueil = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "Accueil", "greeting_type": "text", "greeting": "Bonjour."}}]}
    assert "Write it in the prompt" in controles._annonce_ia({}, temps_reel=True, graphe=sans_accueil)[0]
    assert controles._annonce_ia({}, temps_reel=True, graphe=avec_accueil) == []
    assert controles._annonce_ia({}, temps_reel=False, graphe=sans_accueil) == []  # hors temps réel, le code dit l'annonce lui-même
