"""[.mark] Le champ « rempli par l'outil » se lit dans la réponse du service, pas dans l'emballage de Dograh.

La question de ce fichier, et elle seule :

    Quand un vrai outil HTTP de Dograh répond (``{"status": "success", "status_code": 200, "data": {...}}``),
    le champ de la fiche que cet outil remplit reçoit-il la valeur de la réponse du service (« confirme »), et un
    service qui répond « echec » en 200 n'écrit-il rien ?

Pourquoi
--------
Run 1475 (20/10/2026, groupe v4 small) : le faux agenda répond ``{"statut": "confirme", "rendez_vous": "confirme"}``,
la réservation est faite et annoncée, mais la fiche refuse « success » (le ``status`` de l'emballage) hors de la liste
(confirme, a_rappeler) : ``rendez_vous`` reste vide. Les tests du lot 1 (G2) passaient des réponses à plat.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.services.workflow.enveloppe_des_actions import (
    envelopper_l_action,
    est_un_echec,
    remplir_par_l_action,
)
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.tools.custom_tool import execute_http_tool

OUTIL = "reserver_entretien"
# La réponse exacte du faux agenda au run 1475.
REPONSE_1475 = {
    "statut": "confirme",
    "rendez_vous": "confirme",
    "date_reservee": "jeudi 22 octobre matin, entre huit heures et treize heures",
}


def _moteur():
    reglages = ReglagesFiche(
        champs=(
            ChampFiche(nom="nom", origine="dicte"),
            ChampFiche(
                nom="rendez_vous",
                origine="deduit",
                valeurs=["confirme", "a_rappeler"],
                rempli_par_outil=OUTIL,
            ),
        )
    )
    return SimpleNamespace(_fiche=reglages, _gathered_context={})


def _emballage(data, status_code=200):
    return {"status": "error" if status_code >= 400 else "success", "status_code": status_code, "data": data}


def test_le_run_1475_ecrit_confirme():
    moteur = _moteur()
    assert remplir_par_l_action(moteur, OUTIL, _emballage(REPONSE_1475)) == ["rendez_vous"]
    assert moteur._gathered_context["rendez_vous"] == "confirme"


def test_sans_la_cle_du_champ_le_statut_de_la_reponse_pas_celui_de_l_emballage():
    moteur = _moteur()
    assert remplir_par_l_action(moteur, OUTIL, _emballage({"statut": "a_rappeler"})) == ["rendez_vous"]
    assert moteur._gathered_context["rendez_vous"] == "a_rappeler"


def test_un_echec_rendu_en_200_n_ecrit_rien():
    moteur = _moteur()
    assert est_un_echec(_emballage({"statut": "echec", "message": "créneau pris"}))
    assert remplir_par_l_action(moteur, OUTIL, _emballage({"statut": "echec"})) == []
    assert "rendez_vous" not in moteur._gathered_context


def test_une_erreur_http_n_ecrit_rien():
    moteur = _moteur()
    assert remplir_par_l_action(moteur, OUTIL, _emballage({"message": "Error in workflow"}, 500)) == []
    assert "rendez_vous" not in moteur._gathered_context


def test_une_reponse_texte_en_json_est_lue():
    moteur = _moteur()
    assert remplir_par_l_action(moteur, OUTIL, _emballage('{"rendez_vous": "confirme"}')) == ["rendez_vous"]


def test_une_reponse_http_qui_ne_dit_rien_n_ecrit_rien():
    """Relecture du 20/10 : un webhook à réponse immédiate (« lancé ») n'écrit jamais « confirme » par défaut."""
    moteur = _moteur()
    for data in ({"message": "Workflow was started"}, [], None, {"raw_response": "ok"}):
        assert remplir_par_l_action(moteur, OUTIL, _emballage(data)) == []
    assert "rendez_vous" not in moteur._gathered_context


def test_une_erreur_rendue_en_200_n_ecrit_rien():
    moteur = _moteur()
    assert remplir_par_l_action(moteur, OUTIL, _emballage({"error": "x"})) == []
    assert "rendez_vous" not in moteur._gathered_context


def test_missing_et_incomplet_sont_des_echecs():
    moteur = _moteur()
    assert est_un_echec({"status": "missing", "manque": ["date"]})
    assert est_un_echec({"statut": "incomplet", "manque": ["prenom"]})
    assert remplir_par_l_action(moteur, OUTIL, {"status": "missing"}) == []


def test_un_texte_mcp_qui_porte_un_emballage_est_lu_dedans():
    moteur = _moteur()
    texte = '{"status_code": 200, "data": {"rendez_vous": "confirme"}}'
    assert remplir_par_l_action(moteur, OUTIL, texte) == ["rendez_vous"]


def test_un_resultat_sans_emballage_se_lit_comme_avant():
    moteur = _moteur()
    assert remplir_par_l_action(moteur, OUTIL, {"statut": "confirme"}) == ["rendez_vous"]


@pytest.mark.asyncio
async def test_r1_par_le_vrai_outil_http_et_l_enveloppe():
    """R1 : la réponse traverse ``execute_http_tool`` (l'emballage réel), puis l'enveloppe des actions ; le modèle
    reçoit le résultat inchangé, la fiche reçoit « confirme »."""
    outil = SimpleNamespace(
        tool_uuid="13bfd46a-test",
        name="reserver_entretien",
        description="Réserve le passage.",
        category="http_api",
        definition={
            "schema_version": 1,
            "type": "http_api",
            "config": {"method": "POST", "url": "https://n8n.example.test/webhook/reserver", "timeout_ms": 5000},
        },
    )
    moteur = _moteur()
    rendus = []

    async def rendre(resultat, *args, **kwargs):
        rendus.append(resultat)

    with patch("api.services.workflow.tools.custom_tool.httpx.AsyncClient") as client:
        reponse = Mock(status_code=200, text="")
        reponse.json.return_value = REPONSE_1475
        session = AsyncMock()
        session.request.return_value = reponse
        client.return_value.__aenter__.return_value = session

        async def action(params):
            await params.result_callback(await execute_http_tool(outil, params.arguments))

        params = SimpleNamespace(result_callback=rendre, arguments={"date": "jeudi 22 octobre"})
        await envelopper_l_action(moteur, OUTIL, action)(params)

    assert rendus and rendus[0]["data"] == REPONSE_1475
    assert moteur._gathered_context["rendez_vous"] == "confirme"
