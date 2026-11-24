"""[.mark] Plan final Partie 1, lot 5 (P, n° 119, 120, 123, 129) : la passation lit ses faits en un endroit, ne cache aucune erreur et ne porte aucun mot de métier.

Règles : les visites d'un collègue se comptent en UNE lecture de la trace (``notes.visites_du_collegue``), à comportement égal ; une erreur d'une fonction de passation
qui rend une valeur de repli est écrite au journal avec sa pile (jamais avalée) ; la nature d'un message est un nom public (``nature_du_message``) ; le texte de la
case ``demande`` de l'outil de passage vient du gabarit (config de l'outil), le texte commun n'a aucun mot de métier.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from loguru import logger

from api.services.gabarits import installation as I
from api.services.groupe import notes as N
from api.services.groupe import passations as P
from api.services.workflow import passage_unique as PU
from api.services.workflow import portes_fermees as PF


def _vue_d_avant(gathered, agent_id):
    """L'ancien calcul (deux lectures), gardé ici comme étalon du comportement égal."""
    allers = [
        e for e in gathered.get("passations") or []
        if isinstance(e, dict) and not e.get("refusee") and e.get("issue", "completed") == "completed" and e.get("vers") == agent_id and e.get("raison") != "retour"
    ]
    if not allers:
        return 0
    retours = [
        e for e in gathered.get("passations") or []
        if isinstance(e, dict) and not e.get("refusee") and e.get("issue", "completed") == "completed" and e.get("vers") == agent_id and e.get("raison") == "retour"
    ]
    return len(allers) + len(retours)


def _passation(vers, raison="passer_a_commande", **plus):
    return {"vers": vers, "raison": raison, **plus}


TRACES = [
    {},
    {"passations": []},
    {"passations": [_passation(2)]},
    {"passations": [_passation(2), _passation(2, "retour")]},
    {"passations": [_passation(1, "retour")]},  # un retour vers un agent qu'aucun aller n'a visité (le principal) : pas une visite
    {"passations": [_passation(2), _passation(2, refusee=True), _passation(2, issue="failed"), _passation(3), _passation(2, "retour")]},
    {"passations": [_passation(2, "retour"), _passation(2, "retour")]},
    {"passations": ["pas un dict", _passation(2)]},
]


@pytest.mark.parametrize("trace", TRACES)
def test_les_visites_d_un_collegue_se_comptent_en_une_lecture_a_comportement_egal(trace):
    for agent in (1, 2, 3, 4):
        assert N.visites_du_collegue(trace, agent) == _vue_d_avant(trace, agent)


def _journal(ecrire) -> str:
    lignes: list[str] = []
    sortie = logger.add(lambda m: lignes.append(str(m)), level="DEBUG")
    try:
        ecrire()
    finally:
        logger.remove(sortie)
    return "\n".join(lignes)


def test_une_erreur_de_lecture_de_la_passation_est_ecrite_au_journal_avec_sa_pile():
    """n° 129 : la valeur de repli est rendue, l'erreur n'est plus avalée. Rouge si le journal disparaît."""
    with patch("api.services.integrations.connectors.catalogue.connecteurs", side_effect=RuntimeError("catalogue illisible")):
        sortie = {}
        texte = _journal(lambda: sortie.update(rendue=P.rendre_a_l_action_ouverte({"x": 1}), porteur=P.porteur_de_l_action_ouverte({"x": 1})))
    assert sortie == {"rendue": False, "porteur": None}
    assert "catalogue illisible" in texte and "RuntimeError" in texte

    def noter_sans_dict():
        P.noter_le_porteur(object(), "commande", 3)  # ne lève pas : l'agent n'a pas de fiche
        N.visites_du_collegue(SimpleNamespace(get=lambda *_a: (_ for _ in ()).throw(ValueError("fiche cassée"))), 1)

    assert "fiche cassée" in _journal(noter_sans_dict)


def test_la_nature_d_un_message_est_publique_et_une_erreur_de_lecture_des_messages_se_dit():
    from api.services.pipecat.ordre_outil_puis_parole import APPELANT, RESULTAT, nature_du_message

    assert nature_du_message({"role": "tool"}) == RESULTAT and nature_du_message({"role": "user"}) == APPELANT and nature_du_message("x") is None
    contexte = SimpleNamespace(get_messages=lambda: (_ for _ in ()).throw(RuntimeError("messages illisibles")))
    sortie = {}
    texte = _journal(lambda: sortie.update(second=PF.second_passage(contexte)))
    assert sortie["second"] is False and "messages illisibles" in texte


def test_le_texte_commun_de_la_demande_n_a_aucun_mot_de_metier():
    """n° 123 : le module du passage unique ne nomme ni plat, ni taille, ni boisson."""
    assert "plat" not in PU.DESCRIPTION_DEMANDE and "boisson" not in PU.DESCRIPTION_DEMANDE and "taille" not in PU.DESCRIPTION_DEMANDE


def _outil_de_passage(cible, description="ce que traite le collègue", config=None):
    return SimpleNamespace(name=f"passer_a_l_agent_{cible}", description=description, definition={"config": {"cible": cible, **(config or {})}})


def test_le_texte_de_la_demande_vient_de_la_config_de_l_outil_sinon_du_texte_commun():
    sans = PU.schema([_outil_de_passage("a"), _outil_de_passage("b")])
    assert sans["function"]["parameters"]["properties"]["demande"]["description"] == PU.DESCRIPTION_DEMANDE
    avec = PU.schema([_outil_de_passage("a", config={PU.CLE_DESCRIPTION_DEMANDE: "Le texte du gabarit."}), _outil_de_passage("b")])
    assert avec["function"]["parameters"]["properties"]["demande"]["description"] == "Le texte du gabarit."


async def test_l_installation_pose_le_texte_de_la_demande_du_gabarit_sur_chaque_outil_de_passage():
    from api.services.gabarits.restauration.textes import OUTIL_DE_PASSAGE, outil

    voulu = outil("accueil", OUTIL_DE_PASSAGE)["parameters"]["properties"]["demande"]["description"]
    mis_a_jour = []
    outils = [SimpleNamespace(tool_uuid="u1", description="x", definition={"config": {"workflow_id": 22}}),
              SimpleNamespace(tool_uuid="u2", description="y", definition={"config": {"workflow_id": 33}})]

    async def maj(tool_uuid, organization_id, description, definition):
        mis_a_jour.append((tool_uuid, definition["config"]))

    with patch.object(I.db_client, "get_tools_for_organization", new=AsyncMock(return_value=outils)), patch.object(I.db_client, "update_tool", new=maj):
        await I._passages_de_l_accueil(5, {"accueil": 11, "commande": 22, "reservation": 33})
    assert [u for u, _ in mis_a_jour] == ["u1", "u2"]
    assert all(c[PU.CLE_DESCRIPTION_DEMANDE] == voulu for _, c in mis_a_jour)
    assert [c["cible"] for _, c in mis_a_jour] == ["commande", "reservation"]
