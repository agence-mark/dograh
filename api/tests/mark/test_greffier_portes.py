"""[.mark] Les portes dans la réponse en mode greffier (chantier greffier-conversation, lot A).

Plan `Labo-agent-vocal/plans/greffier-conversation/`, lot A (décision D5 du 09/10, D2 du 13/10) :
une case par agent, éteinte par défaut, jouée en Postscript ET en greffier. En greffier, le lecteur
de portes (le processeur du Post-scriptum sans la note) prend la porte écrite dans la réponse ; un
seul appel au modèle par changement d'étape.

| Test | Ce qu'il prouve |
|---|---|
| réglage | greffier + case : lue allumée, enregistrée par la vraie route, estampillée ; outil : refusée |
| consigne | le vrai ``_prepare_node`` en greffier : bloc des portes sans séparateur ni note, aucune fonction de porte |
| lecteur | la ligne « → » jamais dite, la porte part au moteur, le JSON jamais dit, une porte inconnue relancée une fois (Q3), une porte en fin de phrase prise (Q4), la trace dans ``portes_lues`` |
| notices | une réponse de l'agent ne touche jamais aux notices du greffier |
| greffier | la ligne « → » n'est jamais relue par le greffier |
| clavier (R1) | par les vraies routes : la porte écrite change d'étape sans appel de fonction, le greffier remplit la fiche, rien de technique n'est affiché ; case éteinte, la même réponse ne change pas d'étape |
"""

import asyncio
from unittest.mock import patch

import pytest

from api.services.pipecat import greffier as module
from api.services.pipecat.greffier import message_du_greffier
from api.services.pipecat.lecteur_de_portes import (
    TRACE_PORTES_LUES,
    LecteurDePortes,
    lecteur_de_portes_du_moteur,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    MODE_GREFFIER,
    MODE_OUTIL,
    Notices,
    ReglagesFiche,
    estampiller_le_mode,
)
from api.services.workflow.porte_parlee import CONSIGNE_DES_PORTES_GREFFIER
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_greffier import _Modele
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer
from api.tests.mark.test_porte_parlee_consigne import _definition, _requete
from api.tests.mark.test_porte_parlee_processeur import (
    PORTES,
    _MontagePortes,
)
from api.tests.mark.test_portes_souples import _messages
from pipecat.tests import MockLLMService

GREFFIER = {**FICHE, CLE_MODE: MODE_GREFFIER}
ALLUMEE = {**GREFFIER, CLE_PORTES_DANS_LA_REPONSE: True}
ESTAMPILLE = {"provider": "mistral", "model": "mistral-large-2512"}


# --------------------------------------------------------------------------- #
# 1. Le réglage
# --------------------------------------------------------------------------- #


def test_en_greffier_la_case_est_lue_allumee_et_eteinte_par_defaut():
    assert ReglagesFiche.depuis(ALLUMEE).portes_dans_la_reponse is True
    assert ReglagesFiche.depuis(GREFFIER).portes_dans_la_reponse is False


def test_en_mode_outil_la_case_reste_eteinte():
    reglages = ReglagesFiche.depuis(
        {**FICHE, CLE_MODE: MODE_OUTIL, CLE_PORTES_DANS_LA_REPONSE: True}
    )
    assert reglages.portes_dans_la_reponse is False


def test_la_route_ecrit_la_case_en_greffier():
    reponse, ecrit = _enregistrer(ALLUMEE)
    assert reponse.status_code == 200, reponse.text
    assert ecrit[CLE_PORTES_DANS_LA_REPONSE] is True


def test_la_route_refuse_la_case_en_mode_outil():
    reponse, ecrit = _enregistrer(
        {**FICHE, CLE_MODE: MODE_OUTIL, CLE_PORTES_DANS_LA_REPONSE: True}
    )
    assert reponse.status_code == 422, reponse.text
    assert ecrit is None


def test_l_estampille_du_greffier_porte_la_case_jouee():
    assert estampiller_le_mode({}, ReglagesFiche.depuis(ALLUMEE)) == {
        CLE_MODE: MODE_GREFFIER,
        CLE_PORTES_DANS_LA_REPONSE: True,
    }
    assert estampiller_le_mode({}, ReglagesFiche.depuis(GREFFIER)) == {
        CLE_MODE: MODE_GREFFIER
    }


# --------------------------------------------------------------------------- #
# 2. La consigne, par le vrai ``_prepare_node``
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_en_greffier_le_bloc_des_portes_est_sans_separateur_ni_note():
    prompt, noms = await _requete("etape", MODE_GREFFIER, True)
    assert "# Les portes de cette étape" in prompt
    debut = prompt.index("# Les portes de cette étape")
    bloc = prompt[debut:]
    assert "|||" not in bloc and "séparateur" not in bloc and "note" not in bloc
    assert CONSIGNE_DES_PORTES_GREFFIER.split("\n")[1] in bloc
    assert "- vers_fin (vers l'étape" in bloc
    assert "vers_fin" not in noms  # la porte n'est plus une fonction


@pytest.mark.asyncio
async def test_en_greffier_case_eteinte_les_portes_restent_des_fonctions():
    prompt, noms = await _requete("etape", MODE_GREFFIER, False)
    assert "# Les portes de cette étape" not in prompt
    assert "vers_fin" in noms


# --------------------------------------------------------------------------- #
# 3. Le lecteur de portes
# --------------------------------------------------------------------------- #


class _MontageGreffier(_MontagePortes):
    def __init__(self, transition: str | None = None):
        super().__init__(ALLUMEE, transition)
        self.notices.derniere = {"a_confirmer": ["nom"]}
        self.processeur = LecteurDePortes(
            reglages=self.reglages,
            fiche=lambda: self.fiche,
            messages=lambda: self.messages,
            attendu=lambda: True,
            portes=self.moteur,
        )

    @property
    def portes_lues(self) -> list[dict]:
        return self.fiche.get(TRACE_PORTES_LUES) or []


class _Relance:
    def __init__(self):
        self.relances = 0

    async def relancer_une_reponse_muette(self):
        self.relances += 1
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["→ vers_panne\nQuelle marque ?"],
        ["→ vers_pa", "nne\nQuelle ", "marque ?"],
        ["Quelle marque ? → vers_panne"],
    ],
    ids=["en-tete", "coupee", "fin-de-phrase-Q4"],
)
async def test_la_ligne_n_est_jamais_dite_la_porte_part_au_moteur(morceaux):
    montage = _MontageGreffier()
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "Quelle marque ?"
    assert "→" not in ordre.dit and "vers_panne" not in ordre.dit
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.moteur.prises[0]["relancer"] is False
    assert montage.portes_lues == [
        {"tour": None, "porte": "vers_panne", "porte_etat": "prise"}
    ]
    # Aucune trace de Post-scriptum, aucune note : le greffier tient la fiche.
    assert montage.traces == []
    assert {k for k in montage.fiche if k != TRACE_PORTES_LUES} == set()


@pytest.mark.asyncio
async def test_sans_porte_la_phrase_part_et_rien_n_est_trace():
    montage = _MontageGreffier()
    ordre = await montage.reponse("Quelle est votre ", "commune ?")
    assert ordre.dit.strip() == "Quelle est votre commune ?"
    assert montage.moteur.prises == []
    assert montage.fiche == {}


@pytest.mark.asyncio
async def test_du_json_n_est_jamais_dit():
    montage = _MontageGreffier()
    ordre = await montage.reponse('Quelle marque ?\n{"motif": "panne"}')
    assert ordre.dit.strip() == "Quelle marque ?"
    assert "{" not in ordre.dit and "motif" not in ordre.dit
    assert "motif" not in montage.fiche


@pytest.mark.asyncio
async def test_les_notices_du_greffier_ne_sont_jamais_touchees():
    montage = _MontageGreffier()
    await montage.reponse("→ vers_panne\nQuelle marque ?")
    await montage.reponse("D'accord.")
    assert montage.notices.derniere == {"a_confirmer": ["nom"]}


@pytest.mark.asyncio
async def test_une_porte_inconnue_sans_phrase_fait_reparler_le_modele_une_fois():
    """Q3 : une porte qui n'existe pas et rien de dit : le modèle reparle (la garde du moteur
    limite à une relance par réplique)."""
    montage = _MontageGreffier()
    relance = _Relance()
    montage.processeur._moteur = relance
    await montage.reponse("→ porte_inventee\n")
    assert [p["nom"] for p in montage.moteur.prises] == ["porte_inventee"]
    assert relance.relances == 1
    assert montage.portes_lues[-1]["porte_etat"] == "inconnue"
    assert montage.portes_lues[-1]["relance_muette"] is True


@pytest.mark.asyncio
async def test_une_porte_seule_fait_reparler_le_modele_dans_l_etape_d_arrivee():
    montage = _MontageGreffier()
    await montage.reponse("→ vers_panne\n")
    assert montage.moteur.prises[0]["relancer"] is True


def test_le_lecteur_n_existe_qu_en_greffier_case_allumee():
    class _Moteur:
        def __init__(self, config):
            self.fiche = ReglagesFiche.depuis(config)
            self._gathered_context = {}
            self.context = None

        def post_scriptum_attendu(self):
            return True

    assert isinstance(lecteur_de_portes_du_moteur(_Moteur(ALLUMEE)), LecteurDePortes)
    assert lecteur_de_portes_du_moteur(_Moteur(GREFFIER)) is None
    assert lecteur_de_portes_du_moteur(_Moteur({**FICHE, CLE_MODE: MODE_OUTIL})) is None
    assert PORTES  # les portes connues du témoin (garde contre un import vide)


# --------------------------------------------------------------------------- #
# 4. Le greffier ne relit jamais une ligne de porte
# --------------------------------------------------------------------------- #


def test_le_greffier_ne_relit_jamais_une_ligne_de_porte():
    reglages = ReglagesFiche.depuis(ALLUMEE)
    message = message_du_greffier(
        reglages,
        {},
        [
            {"role": "user", "content": "c'est pour une panne"},
            {"role": "assistant", "content": "→ vers_etape\nQuelle marque ?"},
        ],
    )
    assert "→" not in message and "vers_etape" not in message
    assert "Agent : Quelle marque ?" in message


# --------------------------------------------------------------------------- #
# 5. Au clavier, par les vraies routes (R1)
# --------------------------------------------------------------------------- #

TOUR_1 = (
    "c'est pour une panne",
    [MockLLMService.create_text_chunks("→ vers_etape\nQuelle marque ?")],
)


def _affiche(charge: dict) -> str:
    return repr(
        [
            ((t.get("assistant_message") or {}).get("text"), t.get("events"))
            for t in charge["session_data"]["turns"]
        ]
    )


@pytest.mark.asyncio
async def test_au_clavier_en_greffier_la_porte_ecrite_change_d_etape(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, ALLUMEE, _definition())
    modele = _Modele({"motif": "panne"})
    with patch.object(module, "service_du_greffier", return_value=(modele, ESTAMPILLE)):
        charge = await _messages(test_client_factory, user, workflow, [TOUR_1])
        # La passe du greffier finit à côté de l'agent ; le tour du clavier l'attend.
        await asyncio.sleep(0)
    point = charge["checkpoint"]
    assert point["current_node_id"] == "etape", point
    affiche = _affiche(charge)
    assert "Quelle marque ?" in affiche, affiche
    assert "→" not in affiche and "|||" not in affiche, affiche
    assert "tool_call" not in affiche, affiche
    assert "'porte_ecrite': 'vers_etape'" in affiche, affiche
    assert point["gathered_context"].get("motif") == "panne", point["gathered_context"]
    assert point["gathered_context"][TRACE_PORTES_LUES][-1]["porte_etat"] == "prise"
    # Le greffier n'a jamais lu la ligne de porte.
    assert all("vers_etape" not in lu for lu in modele.lus), modele.lus


@pytest.mark.asyncio
async def test_au_clavier_en_greffier_case_eteinte_la_meme_reponse_ne_change_pas_d_etape(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, GREFFIER, _definition())
    with patch.object(
        module, "service_du_greffier", return_value=(_Modele({}), ESTAMPILLE)
    ):
        charge = await _messages(test_client_factory, user, workflow, [TOUR_1])
    assert charge["checkpoint"]["current_node_id"] == "start", charge["checkpoint"]


def test_les_notices_ne_sont_pas_celles_du_lecteur():
    """Le lecteur est construit sans notices : ``Notices`` n'est jamais passé."""
    montage = _MontageGreffier()
    assert montage.processeur._notices is None
    assert isinstance(montage.notices, Notices)


@pytest.mark.asyncio
async def test_une_reponse_faite_seulement_de_json_fait_reparler_le_modele():
    """Revue du 13/10 : rien de dit, aucune porte : le modèle reparle (une fois, garde du
    moteur), jamais un tour muet."""
    montage = _MontageGreffier()
    relance = _Relance()
    montage.processeur._moteur = relance
    ordre = await montage.reponse('{"motif": "panne"}')
    assert ordre.dit == ""
    assert relance.relances == 1
    await montage.reponse("Quelle marque ?")
    assert relance.relances == 1  # une phrase dite : aucune relance
