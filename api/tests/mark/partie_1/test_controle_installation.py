"""[.mark] Correctifs d'avant le banc (23/11), points de Pierre sur l'installation, la diffusion et la fusion des branches (E).

| Test | Ce qu'il prouve |
|---|---|
| E1 | la porte d'acceptation d'un agent PUBLIÉ (plus de brouillon) lit sa version en ligne : la diffusion n'est plus refusée |
| E2 | une base de retouches installée avant le 22/11 à 20 h 44 (sorties à quatre éléments) ne rend pas l'agent intact « retouché » |
| E4 réglages | une retouche d'un réglage d'étape (délai avant l'accueil, interruption, variables) n'est plus écrasée sans conflit par une version qui change le texte ; une base d'avant ne montre pas de fausse retouche |
| E4 défaire | défaire la fusion d'une branche de diffusion remet la fiche (version du gabarit, base des retouches, attente) comme avant elle |
| E4 outils | l'empreinte figée du gabarit couvre ``outils.json`` à partir de la version 7 ; celle de la version 6 déjà figée en base ne bouge pas |
| E3 | l'empreinte d'un graphe ne compte pas la mise en page (positions, zoom, sélection) ; un texte changé la change |
"""

from __future__ import annotations

from api.db import db_client
from api.services.builder.tests_agent import boucle
from api.services.gabarits import diffusion as D
from api.services.gabarits import installation as I
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.partie_1.test_l17_gabarit import _porte_verte, installe  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401


async def test_e1_la_porte_lit_la_version_en_ligne_d_un_agent_publie(installe):
    from api.routes.workflow import publier_un_agent
    from api.schemas.publication import DemandeDePublication

    await _porte_verte(installe)
    wid = installe.agents["commande"]
    await publier_un_agent(wid, installe.user, DemandeDePublication(forcer=True, raison="textes prouvés au banc B12/B13 (lot 6)"))
    assert await db_client.get_draft_version(wid) is None  # publié : plus de brouillon
    verte, problemes = await D.porte_verte(installe.org, installe.application)
    assert verte, problemes[:3]  # avant : « jamais rejoué » sur un brouillon absent, la diffusion refusée dès la première publication


def test_e2_une_base_a_sorties_de_quatre_elements_se_lit_a_cinq():
    graphe = {"nodes": [{"id": "1", "type": "startCall", "data": {"prompt": "a"}}], "edges": [{"source": "1", "target": "2", "data": {"condition": "c", "fermee_si_action_ouverte": True}}]}
    actuelle = I.forme_de_l_agent(graphe)
    assert len(actuelle["sorties"][0]) == 5
    ancienne = {"noeuds": actuelle["noeuds"], "sorties": [s[:4] for s in actuelle["sorties"]]}  # ce que l'installation écrivait avant le 22/11 à 20 h 44
    assert D.retouches(ancienne, actuelle) == []  # l'agent n'a pas été retouché
    nouvelle = {**actuelle, "sorties": [[*actuelle["sorties"][0][:4], True]]}  # la version 6 pose la garde sur cette sortie
    assert D.fusion_a_trois(ancienne, actuelle, nouvelle) == (["sorties"], [])  # prise, jamais en conflit


def test_e3_l_empreinte_ne_compte_pas_la_mise_en_page():
    graphe = {"nodes": [{"id": "1", "data": {"prompt": "a"}, "position": {"x": 1, "y": 2}}], "edges": [{"source": "1", "target": "2"}], "viewport": {"x": 0, "y": 0, "zoom": 1}}
    enregistre_a_l_ecran = {
        "nodes": [{"id": "1", "data": {"prompt": "a"}, "position": {"x": 99, "y": 7}, "positionAbsolute": {"x": 99, "y": 7}, "selected": True, "measured": {"width": 3, "height": 4}}],
        "edges": [{"source": "1", "target": "2", "selected": True}], "viewport": {"x": 5, "y": 5, "zoom": 0.5},
    }
    configurations = {"a": 1}
    assert boucle.empreinte_du_brouillon(graphe, configurations) == boucle.empreinte_du_brouillon(enregistre_a_l_ecran, configurations)
    change = {**graphe, "nodes": [{"id": "1", "data": {"prompt": "b"}, "position": {"x": 1, "y": 2}}]}
    assert boucle.empreinte_du_brouillon(change, configurations) != boucle.empreinte_du_brouillon(graphe, configurations)
    assert boucle.empreinte_du_brouillon(graphe, {"a": 2}) != boucle.empreinte_du_brouillon(graphe, configurations)


def _agent(prompt: str, **reglages) -> dict:
    return {"nodes": [{"id": "1", "type": "startCall", "data": {"prompt": prompt, "allow_interrupt": True, **reglages}}], "edges": []}


def test_e4_une_retouche_de_reglage_d_etape_n_est_plus_ecrasee_sans_conflit():
    installe_ = I.forme_de_l_agent(_agent("texte v5"))
    retouche = I.forme_de_l_agent(_agent("texte v5", delayed_start=True, delayed_start_duration=3))  # le restaurateur a posé un délai avant l'accueil
    nouvelle = I.forme_de_l_agent(_agent("texte v6"))  # la version 6 change le texte
    assert D.retouches(installe_, retouche) == ["noeud:1"]
    prendre, conflits = D.fusion_a_trois(installe_, retouche, nouvelle)
    assert conflits == ["noeud:1"] and prendre == []  # avant : le nœud entier de la v6 écrasait le délai, sans conflit
    # intact : la version est prise
    assert D.fusion_a_trois(installe_, installe_, nouvelle) == (["noeud:1"], [])


def test_e4_une_base_d_avant_les_reglages_ne_montre_pas_de_fausse_retouche():
    actuelle = I.forme_de_l_agent(_agent("texte v5", delayed_start=True))
    ancienne = {"noeuds": {i: {k: v for k, v in n.items() if k != "reglages"} for i, n in actuelle["noeuds"].items()}, "sorties": actuelle["sorties"]}
    assert D.retouches(ancienne, actuelle) == []


async def test_e4_defaire_la_fusion_remet_la_fiche_comme_avant(installe):
    wid = installe.application["workflow_id"]
    org = installe.org
    avant = await db_client.application_de(org, wid)
    version_avant, base_avant = avant["gabarit_version"], (avant.get("retouches") or {}).get("base")
    etape = next(e for e, w in avant["agents"].items() if not e.startswith("_") and w == wid)
    retouches = dict(avant.get("retouches") or {})
    retouches["en_attente"] = {"version": version_avant + 1, "trous": dict(avant["trous"]), "etapes": {etape: {"branche_id": 4242, "forme": {"noeuds": {}, "sorties": []}}}}
    await db_client.ecrire_l_application(org, wid, retouches=retouches)

    assert await D.noter_la_fusion(org, wid, 4242) is True
    fusionnee = await db_client.application_de(org, wid)
    assert fusionnee["gabarit_version"] == version_avant + 1 and fusionnee["retouches"]["base"][etape] == {"noeuds": {}, "sorties": []}

    assert await D.noter_le_defaire(org, wid, 4242) is True
    defaite = await db_client.application_de(org, wid)
    assert defaite["gabarit_version"] == version_avant  # avant : restait à la version diffusée
    assert (defaite["retouches"].get("base") or {}).get(etape) == (base_avant or {}).get(etape)
    assert defaite["retouches"]["en_attente"]["etapes"][etape]["branche_id"] == 4242  # la diffusion attend de nouveau cette branche
    assert await D.noter_le_defaire(org, wid, 4242) is False  # rejouable : rien de plus


def test_e4_l_empreinte_du_gabarit_couvre_les_outils_a_partir_de_la_version_7():
    from api.services.gabarits import gabarit as G

    d, t, r = {"x": 1}, {"a": "b"}, {"y": 2}
    assert G._empreinte(d, t, r, 6, "outils-1") == G._empreinte(d, t, r, 6, "outils-2")  # la version 6, figée en base, garde son empreinte
    assert G._empreinte(d, t, r, 7, "outils-1") != G._empreinte(d, t, r, 7, "outils-2")  # la suivante : un outil changé sans nouvelle version est refusé
    assert G._empreinte(d, t, r, 6, "outils-1") == G._empreinte(d, t, r, 6)  # sans outil versé, comme avant
    assert G.charger().empreinte == G.charger().empreinte
