"""[.mark] Chantier agents-specialises, lot 7 : motif cumulable, porte inconnue, greffier, réouverture,
parcours (A8, K9, K1, K4, n° 361, D91).

| Groupe | Ce qu'il prouve |
|---|---|
| motif cumulable | le greffier écrit un champ cumulatif à liste fermée comme une liste de valeurs de la liste (« ; »), chacune contrôlée, un doublon ignoré ; la fiche le montre comme une liste ; un champ cumulatif sans liste garde le texte concaténé d'avant |
| K1 | une porte écrite au nom d'une autre étape est réécrite vers l'étape de retour au principal (tracée) ; chez le principal, ou sans sortie vers le retour, elle est ignorée comme avant |
| K4 | les règles d'écriture du greffier (refus, adresse entière, non-dit, date relative) sont toujours dans sa consigne ; « refusé » s'écrit sur tout champ non cumulatif (K4 révisé le 21/10) |
| n° 361 | un état OUVERT forcé par le contexte d'essai n'hérite pas de la réouverture des horaires réels |
| parcours | une entrée par (agent, étape) dans l'ordre, rendue « Agent › étape › étape » ; seulement dans un groupe |
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from api.services.groupe.parcours import rendre_le_parcours
from api.services.pipecat.etat_ouverture import (
    FERME,
    OUVERT,
    PARIS,
    PAUSE,
    SUR_RENDEZ_VOUS,
    injecter_etat_ouverture,
)
from api.services.pipecat.greffier import (
    CONSIGNE_GENERIQUE,
    REGLES_D_ECRITURE,
    consigne_du_greffier,
)
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    MODE_GREFFIER,
    ReglagesFiche,
    _propriete,
    cumuler_la_liste,
    ecrire_dans_la_fiche,
    etat_de_la_fiche,
    est_une_liste_cumulative,
    valeurs_d_une_liste,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.workflow_graph import WorkflowGraph, transition_tool_name
from api.tests.mark.test_etat_ouverture import EXEMPLE_D2
from api.tests.mark.test_fiche_montree import _contexte, _mistral
from api.tests.mark.test_greffier import _Modele, _Montage
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
from api.tests.mark.test_passation_clavier import _arete, _noeud
from api.tests.mark.test_passation_rapide_groupe import (
    GROUPE,
    PATCH_OUTILS,
    _monter_groupe,
    _passer,
    _sonnerie,
)
from api.tests.test_agent_transfer import TransferAgentTool

MOTIFS = ["entretien", "panne", "projet"]
CONFIG_MOTIF = {
    "fiche_au_fil_de_leau": True,
    CLE_MODE: MODE_GREFFIER,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {
            "nom": "motif",
            "origine": "deduit",
            "cumulatif": True,
            "valeurs": MOTIFS,
            "description": "Ce que la personne demande",
        },
        {"nom": "note_libre", "origine": "deduit", "cumulatif": True},
        {"nom": "adresse_courriel", "origine": "dicte", "description": "Son courriel"},
        {"nom": "code", "origine": "dicte", "chiffres": 4},
        {"nom": "categorie", "origine": "deduit", "valeurs": ["a", "b"]},
    ],
}


# --------------------------------------------------------------------------- #
# 1. Motif cumulable (A8, K9)
# --------------------------------------------------------------------------- #


def test_les_fonctions_de_liste_controlent_chaque_valeur_et_ignorent_les_doublons():
    assert valeurs_d_une_liste("a ; b;; c ") == ["a", "b", "c"]
    assert valeurs_d_une_liste(["a", " b "]) == ["a", "b"]
    assert valeurs_d_une_liste(None) == [] and valeurs_d_une_liste("  ") == []
    # La forme déclarée gagne (casse, accents), un doublon est ignoré, le hors-liste est écarté.
    assert cumuler_la_liste("entretien", "PANNE ; entretien ; inconnu", MOTIFS) == "entretien ; panne"
    assert cumuler_la_liste(None, ["projet"], MOTIFS) == "projet"
    assert cumuler_la_liste("entretien", "inconnu", MOTIFS) == "entretien"
    assert cumuler_la_liste(None, "inconnu", MOTIFS) == ""


@pytest.mark.asyncio
async def test_le_greffier_cumule_les_motifs_comme_une_liste_de_la_liste():
    """Par la vraie passe du greffier : le point d'écriture unique range chaque valeur de la liste."""
    modele = _Modele(
        {"motif": "entretien"},
        {"motif": "panne ; entretien ; inconnu"},  # un doublon, un hors-liste
        {"motif": "inconnu"},  # rien de valable : refusé, la liste ne bouge pas
        {"motif": "Projet"},
    )
    montage = _Montage(modele, config=CONFIG_MOTIF)
    await montage.passe()
    assert montage.fiche["motif"] == "entretien"
    await montage.passe()
    assert montage.fiche["motif"] == "entretien ; panne"
    await montage.passe()
    assert montage.fiche["motif"] == "entretien ; panne"
    journal = montage.fiche["fiche_journal"]
    assert journal[-1]["champ"] == "motif" and journal[-1]["raison"] == "hors_liste"
    await montage.passe()
    assert montage.fiche["motif"] == "entretien ; panne ; projet"
    assert montage.fiche["extracted_variables"]["motif"] == "entretien ; panne ; projet"


def test_la_fiche_montre_un_champ_liste_comme_une_liste_et_la_description_le_dit():
    reglages = ReglagesFiche.depuis(CONFIG_MOTIF)
    fiche: dict = {}
    ecrire_dans_la_fiche(fiche, reglages, "motif", "entretien ; panne", source="greffier")
    ecrire_dans_la_fiche(fiche, reglages, "nom", "Dupont", source="greffier", paroles=["Dupont"])
    etat = etat_de_la_fiche(reglages, fiche)
    assert "motif = [entretien, panne]" in etat
    assert "nom = « Dupont »" in etat
    assert "Plusieurs valeurs possibles" in _propriete(reglages.par_nom["motif"])["description"]
    assert "Plusieurs valeurs possibles" not in _propriete(reglages.par_nom["categorie"])["description"]
    assert est_une_liste_cumulative(reglages.par_nom["motif"])
    assert not est_une_liste_cumulative(reglages.par_nom["note_libre"])
    assert not est_une_liste_cumulative(reglages.par_nom["categorie"])


def test_un_champ_a_liste_simple_et_un_cumulatif_sans_liste_gardent_leur_comportement():
    reglages = ReglagesFiche.depuis(CONFIG_MOTIF)
    fiche: dict = {}
    # Liste fermée non cumulative : une seule valeur, « a ; b » reste refusé.
    assert ecrire_dans_la_fiche(fiche, reglages, "categorie", "a ; b", source="greffier").statut == "refuse"
    assert ecrire_dans_la_fiche(fiche, reglages, "categorie", "b", source="greffier").statut == "ecrit"
    # Cumulatif sans liste : le texte concaténé d'avant.
    ecrire_dans_la_fiche(fiche, reglages, "note_libre", "premier souci", source="greffier")
    ecrire_dans_la_fiche(fiche, reglages, "note_libre", "second souci", source="greffier")
    assert fiche["note_libre"] == "premier souci ; second souci"


# --------------------------------------------------------------------------- #
# 2. K4 : la consigne du greffier et « refusé »
# --------------------------------------------------------------------------- #


def test_k4_les_regles_d_ecriture_sont_toujours_dans_la_consigne():
    reglages = ReglagesFiche.depuis(CONFIG_MOTIF)
    for consigne in (None, "Tu tiens la fiche d'un cabinet."):
        texte = consigne_du_greffier(reglages, consigne)
        assert REGLES_D_ECRITURE in texte
        assert texte.index(REGLES_D_ECRITURE) < texte.index("# Les champs de la fiche")
    texte = consigne_du_greffier(reglages, None)
    assert texte.startswith(CONSIGNE_GENERIQUE.rstrip())
    assert "« refusé »" in texte and "e-mail s'écrit entière" in texte
    assert "Rien de non dit ne s'écrit" in texte and "date de l'appel" in texte


@pytest.mark.asyncio
async def test_k4_un_refus_s_ecrit_refuse_sur_tout_champ_non_cumulatif():
    """K4 révisé (21/10, décision d'Evan) : un refus par réplique (D2 écarte un lot de refus), sur un champ
    libre, une liste fermée, un nombre de chiffres ; jamais sur un champ-liste cumulatif (un motif ne se refuse pas)."""
    modele = _Modele({"adresse_courriel": "refusé"}, {"categorie": "refusé"}, {"code": "refusé"}, {"motif": "refusé"})
    montage = _Montage(modele, config=CONFIG_MOTIF)
    for phrase in ("Je préfère ne pas donner mon courriel.", "Ça, je ne le dirai pas.", "Pas de code.", "Je ne dis pas pourquoi."):
        montage.messages.append({"role": "user", "content": phrase})
        await montage.passe()
    assert montage.fiche["adresse_courriel"] == "refusé"
    assert montage.fiche["categorie"] == "refusé" and montage.fiche["code"] == "refusé"
    assert "motif" not in montage.fiche


def test_k4_une_date_relative_passe_par_le_module_de_date_avec_l_annee_de_l_appel():
    config = {
        "fiche_au_fil_de_leau": True,
        "fiche_champs": [{"nom": "dernier_entretien", "origine": "dicte", "lecteur": "date"}],
    }
    reglages = ReglagesFiche.depuis(config)
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche,
        reglages,
        "dernier_entretien",
        "l'année dernière",
        source="greffier",
        paroles=["Mon dernier entretien, c'était l'année dernière."],
        jour=datetime(2026, 10, 14, 10, 0),
    )
    assert verdict.statut == "ecrit" and fiche["dernier_entretien"] == "2025"


# --------------------------------------------------------------------------- #
# 3. n° 361 : un état forcé par le contexte d'essai vide la réouverture
# --------------------------------------------------------------------------- #

MARDI_13H = datetime(2026, 10, 13, 13, 0, tzinfo=PARIS)


@pytest.mark.parametrize("etat", [OUVERT, SUR_RENDEZ_VOUS])
def test_n361_un_etat_ouvert_force_n_herite_pas_de_la_reouverture_des_horaires(etat):
    reel = injecter_etat_ouverture({}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H)
    assert reel["etat_ouverture"] == PAUSE and reel["reouverture"]  # la réalité : fermé, rouvre à 14 h
    force = injecter_etat_ouverture(
        {"etat_ouverture": etat}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H
    )
    assert force["etat_ouverture"] == etat and force["reouverture"] == ""


def test_n361_un_etat_ferme_force_et_une_reouverture_fournie_sont_gardes():
    ferme = injecter_etat_ouverture(
        {"etat_ouverture": FERME}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H
    )
    assert ferme["etat_ouverture"] == FERME and ferme["reouverture"] == "aujourd'hui à 14 heures"
    donnee = injecter_etat_ouverture(
        {"etat_ouverture": OUVERT, "reouverture": "lundi à 10 heures"},
        {"horaires_ouverture": EXEMPLE_D2},
        maintenant=MARDI_13H,
    )
    assert donnee["reouverture"] == "lundi à 10 heures"
    # Rien de forcé : les horaires décident, comme avant.
    assert injecter_etat_ouverture({}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H)[
        "reouverture"
    ] == "aujourd'hui à 14 heures"


# --------------------------------------------------------------------------- #
# 4. K1 : une porte écrite au nom d'une autre étape rend la main au principal
# --------------------------------------------------------------------------- #


def _specialise_a_trois_etapes() -> dict:
    return {
        "nodes": [
            _noeud("s", "startCall", "qualification", "Tu qualifies."),
            _noeud("c", "agentNode", "coordonnees", "Tu prends les coordonnées."),
            _noeud("r", "agentNode", "retour", "Retour.", retour_au_principal=True),
        ],
        "edges": [_arete("s", "c", "vers_coordonnees"), _arete("c", "r", "vers_retour")],
    }


def _sans_retour() -> dict:
    return {
        "nodes": [
            _noeud("s", "startCall", "accueil", "Tu routes."),
            _noeud("c", "agentNode", "etape", "Une étape."),
            _noeud("f", "endCall", "fin", "Conclure."),
        ],
        "edges": [_arete("s", "c", "vers_etape"), _arete("c", "f", "vers_fin")],
    }


async def _moteur_a(definition, etape, *, note_d_abord=False):
    graphe = WorkflowGraph(ReactFlowDTO.model_validate(definition))
    config = {**CONFIG_ALLUMEE, **({"note_d_abord": True} if note_d_abord else {})}
    engine = PipecatEngine(
        llm=_mistral(),
        context=_contexte(),
        workflow=graphe,
        call_context_vars={},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis(config),
    )
    agent = engine.active_agent
    await engine._prepare_node(agent, graphe.nodes[etape], apply_settings=False)
    agent.current_node = graphe.nodes[etape]
    engine.queue_text_message = AsyncMock(return_value=True)
    engine.end_call_with_reason = AsyncMock()
    agent.queue_frame = AsyncMock()
    return engine


def _nom(etape: str) -> str:
    return transition_tool_name(etape)


@pytest.mark.asyncio
@pytest.mark.parametrize("note_d_abord", [False, True])
async def test_k1_une_porte_au_nom_d_une_autre_etape_est_reecrite_vers_le_retour(note_d_abord):
    engine = await _moteur_a(_specialise_a_trois_etapes(), "c", note_d_abord=note_d_abord)
    # « → qualification » : le nom d'une étape du graphe qui n'est pas une sortie de « coordonnees ».
    assert engine.est_une_porte_de_l_etape(_nom("qualification"))
    assert await engine.prendre_porte_ecrite(_nom("qualification")) == "prise"
    assert engine.active_agent.current_node.name == "retour"
    [trace] = engine._gathered_context["porte_reecrite"]
    assert trace["ecrite"] == _nom("qualification") and trace["etape"] == "coordonnees"
    assert trace["vers"] == "retour"


@pytest.mark.asyncio
async def test_k1_la_vraie_porte_et_le_nom_de_l_etape_de_retour_ne_sont_pas_des_reecritures():
    engine = await _moteur_a(_specialise_a_trois_etapes(), "c")
    assert await engine.prendre_porte_ecrite("vers_retour") == "prise"
    assert engine.active_agent.current_node.name == "retour"
    assert "porte_reecrite" not in engine._gathered_context


@pytest.mark.asyncio
@pytest.mark.parametrize("nom", ["porte_qui_n_existe_pas", "coordonnees"])
async def test_k1_un_nom_inconnu_ou_l_etape_en_cours_reste_ignore(nom):
    engine = await _moteur_a(_specialise_a_trois_etapes(), "c")
    assert not engine.est_une_porte_de_l_etape(_nom(nom))
    assert await engine.prendre_porte_ecrite(_nom(nom)) == "inconnue"
    assert engine.active_agent.current_node.name == "coordonnees"
    assert "porte_reecrite" not in engine._gathered_context


@pytest.mark.asyncio
async def test_k1_chez_le_principal_ou_sans_sortie_vers_le_retour_la_porte_reste_ignoree():
    # Le principal n'a aucune étape de retour : comme avant.
    principal = await _moteur_a(_sans_retour(), "c")
    assert await principal.prendre_porte_ecrite(_nom("accueil")) == "inconnue"
    assert principal.active_agent.current_node.name == "etape"
    # Un spécialisé dont l'étape en cours n'a pas de sortie vers le retour (l'étape de départ).
    depart = await _moteur_a(_specialise_a_trois_etapes(), "s")
    assert await depart.prendre_porte_ecrite(_nom("retour")) == "inconnue"
    assert depart.active_agent.current_node.name == "qualification"
    assert "porte_reecrite" not in depart._gathered_context


# --------------------------------------------------------------------------- #
# 5. Parcours (agent, étape)
# --------------------------------------------------------------------------- #


def test_le_parcours_se_rend_agent_puis_etapes_et_reecrit_l_agent_quand_il_change():
    entrees = [
        {"agent": "Accueil", "agent_id": 1, "etape": "qualification"},
        {"agent": "Entretien", "agent_id": 2, "etape": "qualification"},
        {"agent": "Entretien", "agent_id": 2, "etape": "coordonnees"},
        {"agent": "Accueil", "agent_id": 1, "etape": "qualification"},
    ]
    assert rendre_le_parcours(entrees) == (
        "Accueil › qualification › Entretien › qualification › coordonnees › Accueil › qualification"
    )
    assert rendre_le_parcours([]) == ""
    assert rendre_le_parcours([{"agent_id": 7, "etape": "x"}]) == "Agent 7 › x"


@pytest.mark.asyncio
async def test_le_parcours_garde_l_ordre_entre_deux_agents_qui_ont_une_etape_du_meme_nom(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(GROUPE)
    engine = harness.engine
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await engine.set_node("start")
            await _passer(harness, 99)
            await _passer(harness, 1)
        entrees = engine._gathered_context["parcours_etapes"]
        assert [(e["agent"], e["etape"]) for e in entrees] == [
            ("Reception", "Accueil Start"),
            ("Billing", "Specialise Start"),
            ("Reception", "Accueil Start"),
        ]
        assert engine._gathered_context["parcours"] == (
            "Reception › Accueil Start › Billing › Specialise Start › Reception › Accueil Start"
        )
        # ``nodes_visited`` ne change pas : une entrée par NOM d'étape, comme avant.
        assert engine._gathered_context["nodes_visited"] == ["Accueil Start", "Specialise Start"]
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_un_agent_seul_ne_recoit_aucune_cle_de_parcours(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(None)
    engine = harness.engine
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await engine.set_node("start")
            await _passer(harness, 99)
        assert "parcours" not in engine._gathered_context
        assert "parcours_etapes" not in engine._gathered_context
        assert engine._gathered_context["nodes_visited"]
    finally:
        await harness.stop()


def test_les_cles_du_groupe_sont_reservees_a_la_fiche():
    from api.schemas.fiche_agent import NOMS_RESERVES

    assert {"parcours", "parcours_etapes", "porte_reecrite", "passations", "transferts_humains"} <= NOMS_RESERVES
