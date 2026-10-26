"""[.mark] fiabilite-de-la-conversation, lot C : ne plus redemander (C1 à C4).

| Test | La garantie |
|---|---|
| C1, données | l'étape de départ reçoit la liste des champs et les conditions (mêmes mixins que l'étape d'agent) ; vide = absent, le JSON d'un agent qui n'en a pas ne change pas ; le graphe les lit |
| C1, écran | le catalogue des nœuds (écran et MCP) offre « Step field labels » sur l'étape de départ, juste après le prompt ; la fixture de l'écran est celle du serveur |
| C2, formule | sous une sortie : « la première chose qui manque est : … , sauf si elle vient de te le donner » ; « rien ne manque, pas de question » ; champ conditionnel actif ou non ; étape d'arrivée sans liste : rien ; case éteinte : rien |
| C2, accueil | l'accueil se tait sur le collègue (aucune sortie ne mène à un autre agent) ; le collègue voit son « Encore attendu » grâce à la liste de son étape de départ (C1) |
| C2, vrai chemin | le moteur monte la ligne dans le bloc d'état de chaque requête, avant la dernière parole de l'appelant : jamais dans le prompt système ni dans l'historique |
| C3 | « incomplet » : la garde attend la passe du greffier du dernier tour (délai borné) puis recalcule (run 1522 rejoué : adresse dite au tour même) ; rien ne manque : aucune attente ; sans greffier : comme avant |
| C4 | un numéro de huit chiffres lu au tour même : la consigne « il manque des chiffres » est dans la requête de CE tour ; numéro complet, ou dit en deux fois : rien ; pas de redite d'une notice déjà montrée |
"""

from __future__ import annotations

import asyncio
import copy
import re
from types import SimpleNamespace

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.services.workflow.dto import (
    ReactFlowDTO,
    StartCallNodeData,
    sanitize_workflow_definition,
)
from api.services.workflow.enveloppe_des_actions import (
    DELAI_DE_LA_PASSE_DU_DERNIER_TOUR,
    garde_du_noeud_apres_les_notes,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_TOUR,
    CONSIGNE_CHIFFRES_MANQUANTS,
    Notices,
    ReglagesFiche,
    etat_avec_les_indices,
    inserer_l_etat,
    montrer_la_fiche,
)
from api.services.workflow.node_specs import all_specs
from api.services.workflow.sorties_de_l_etape import (
    LIGNE_PREMIERE_CHOSE,
    LIGNE_RIEN_NE_MANQUE,
    lignes_des_sorties,
    sorties_de,
)
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_clavier_porte_la_fiche import DEFINITION
from api.tests.mark.test_declenchement_de_l_action import CONDITION_MAIL, _reglages
from api.tests.mark.test_travail_de_fond import Appel, _texte  # noqa: F401


# --------------------------------------------------------------------------- #
# C1 : la liste des champs de l'étape de départ
# --------------------------------------------------------------------------- #


def test_c1_l_etape_de_depart_prend_la_liste_et_les_conditions():
    donnees = StartCallNodeData.model_validate(
        {"name": "Accueil", "prompt": "p", "champs_etape": "nom, adresse, mail", "conditions_de_champs": [CONDITION_MAIL]}
    )
    assert donnees.champs_etape == "nom, adresse, mail"
    assert donnees.conditions_de_champs[0].champ == "mail"
    vide = StartCallNodeData(name="Accueil", prompt="p")
    assert vide.champs_etape is None and vide.conditions_de_champs is None


def test_c1_le_nettoyage_garde_la_liste_et_ecarte_le_vide():
    definition = copy.deepcopy(DEFINITION)
    depart = next(n for n in definition["nodes"] if n["id"] == "start")
    depart["data"]["champs_etape"] = "nom, adresse"
    depart["data"]["conditions_de_champs"] = [CONDITION_MAIL]
    propre = next(n for n in sanitize_workflow_definition(definition)["nodes"] if n["id"] == "start")
    assert propre["data"]["champs_etape"] == "nom, adresse"
    assert propre["data"]["conditions_de_champs"][0]["champ"] == "mail"
    depart["data"]["champs_etape"] = "  "
    depart["data"]["conditions_de_champs"] = []
    propre = next(n for n in sanitize_workflow_definition(definition)["nodes"] if n["id"] == "start")
    assert "champs_etape" not in propre["data"] and "conditions_de_champs" not in propre["data"]


def test_c1_le_graphe_lit_la_liste_de_l_etape_de_depart():
    definition = copy.deepcopy(DEFINITION)
    depart = next(n for n in definition["nodes"] if n["id"] == "start")
    depart["data"]["champs_etape"] = "nom, adresse"
    graphe = WorkflowGraph(ReactFlowDTO.model_validate(definition))
    assert graphe.nodes["start"].champs_etape == ("nom", "adresse")


def test_c1_le_catalogue_offre_la_liste_sur_l_etape_de_depart_apres_le_prompt():
    specs = {s.name: s for s in all_specs()}
    noms = [p.name for p in specs["startCall"].properties]
    assert noms[noms.index("prompt") + 1] == "champs_etape"
    assert "conditions_de_champs" not in noms  # comme sur l'étape d'agent : hors du formulaire généré


# --------------------------------------------------------------------------- #
# C2 : sous chaque sortie, la première chose qui manque
# --------------------------------------------------------------------------- #


def _etape(*champs, conditions=()):
    return SimpleNamespace(name="La", champs_etape=tuple(champs), conditions_de_champs=tuple(conditions), out_edges=[])


def _lignes(fiche, arrivee, reglages=None):
    return lignes_des_sorties(reglages or _reglages(), fiche, [("porte_a", arrivee)])


def test_c2_un_seul_champ_manquant_est_nomme_avec_la_formule_du_plan():
    lignes = _lignes({"nom": "Durand"}, _etape("nom", "adresse"))
    assert lignes == [LIGNE_PREMIERE_CHOSE.format(sortie="porte_a", champ="adresse")]
    assert lignes[0].endswith("sauf si elle vient de te le donner.")


def test_c2_la_premiere_seulement_pas_toute_la_liste():
    ligne = _lignes({}, _etape("nom", "adresse"))[0]
    assert "est : nom," in ligne and "adresse" not in ligne


def test_c2_rien_ne_manque_pas_de_question():
    assert _lignes({"nom": "Durand", "adresse": "8 rue Pasteur"}, _etape("nom", "adresse")) == [
        LIGNE_RIEN_NE_MANQUE.format(sortie="porte_a")
    ]


def test_c2_un_champ_conditionnel_n_est_attendu_que_si_la_condition_est_tenue():
    arrivee = _etape("nom", "mail", conditions=[CONDITION_MAIL])
    inactive = {"nom": "Durand", "contrat_entretien": "aucun"}
    assert _lignes(inactive, arrivee) == [LIGNE_RIEN_NE_MANQUE.format(sortie="porte_a")]
    active = {"nom": "Durand", "contrat_entretien": "souscrit"}
    assert _lignes(active, arrivee) == [LIGNE_PREMIERE_CHOSE.format(sortie="porte_a", champ="mail")]


def test_c2_une_etape_d_arrivee_sans_liste_ne_recoit_rien_et_la_case_eteinte_non_plus():
    assert _lignes({}, _etape()) == []
    eteinte = ReglagesFiche(champs=_reglages().champs, etiquettes=False)
    assert _lignes({}, _etape("nom"), eteinte) == []


def test_c2_ce_que_le_modele_vient_de_lire_au_tour_meme_ne_manque_pas():
    # une commune lue et sûre par un module au tour même (trace), pas encore dans la fiche du greffier
    reglages = ReglagesFiche(
        champs=(ChampFiche(nom="nom", origine="dicte"), ChampFiche(nom="commune", origine="dicte", lecteur="commune")),
        etiquettes=True,
    )
    fiche = {
        "nom": "Durand",
        CLE_TOUR: 2,
        "communes_verifiees": [{"tour": 2, "statut": "sure", "commune_retenue": {"nom": "Creil", "codes_postaux": ["60100"]}}],
    }
    assert lignes_des_sorties(reglages, fiche, [("porte_a", _etape("nom", "commune"))]) == [
        LIGNE_RIEN_NE_MANQUE.format(sortie="porte_a")
    ]


def _graphe_deux_etapes():
    definition = copy.deepcopy(DEFINITION)
    definition["nodes"].insert(
        1,
        {"id": "etape", "type": "agentNode", "position": {"x": 0, "y": 100},
         "data": {"name": "Etape", "prompt": "Tu poses la question.", "champs_etape": "nom, adresse"}},
    )
    definition["edges"].append(
        {"id": "start-etape", "source": "start", "target": "etape",
         "data": {"label": "vers_etape", "condition": "Quand il faut."}}
    )
    return WorkflowGraph(ReactFlowDTO.model_validate(definition))


def test_c2_les_sorties_sont_celles_des_portes_vers_des_etapes_du_meme_agent():
    graphe = _graphe_deux_etapes()
    sorties = sorties_de(graphe.nodes["start"], graphe)
    assert [nom for nom, _ in sorties] == [a.get_function_name() for a in graphe.nodes["start"].out_edges]
    assert "vers_etape" in [nom for nom, _ in sorties]
    # une fin ne déclare aucune liste : rien à dire sous cette sortie
    lignes = lignes_des_sorties(_reglages(), {"nom": "Durand"}, sorties)
    assert lignes == [LIGNE_PREMIERE_CHOSE.format(sortie="vers_etape", champ="adresse")]


def test_c2_le_collegue_voit_son_encore_attendu_grace_a_la_liste_de_son_etape_de_depart():
    # C1 : l'étape de départ du collègue porte sa liste ; l'accueil, lui, se tait (aucune sortie ne mène à un autre agent)
    from api.services.workflow.champs_conditionnels import champs_actifs

    definition = copy.deepcopy(DEFINITION)
    depart = next(n for n in definition["nodes"] if n["id"] == "start")
    depart["data"]["champs_etape"] = "nom, adresse"
    collegue = WorkflowGraph(ReactFlowDTO.model_validate(definition))
    fiche = {"nom": "Durand"}
    texte = etat_avec_les_indices(_reglages(), fiche, None, [], champs_actifs(collegue.nodes["start"], fiche))
    assert "Encore attendu : adresse." in texte
    accueil = WorkflowGraph(ReactFlowDTO.model_validate(copy.deepcopy(DEFINITION)))
    assert lignes_des_sorties(_reglages(), fiche, sorties_de(accueil.nodes["start"], accueil)) == []


def test_c2_l_etat_porte_la_ligne_apres_encore_attendu_et_la_case_eteinte_ne_change_rien():
    graphe = _graphe_deux_etapes()
    sorties = sorties_de(graphe.nodes["start"], graphe)
    fiche = {"nom": "Durand"}
    texte = etat_avec_les_indices(_reglages(), fiche, None, [], (), True, sorties)
    assert "Sortie vers_etape : là-bas, la première chose qui manque est : adresse" in texte
    eteinte = ReglagesFiche(champs=_reglages().champs, etiquettes=False)
    sans = etat_avec_les_indices(eteinte, fiche, None, [], (), True, sorties)
    assert "Sortie" not in (sans or "")
    assert etat_avec_les_indices(_reglages(), fiche, None, [], ()) == etat_avec_les_indices(_reglages(), fiche, None, [], (), True, ())


class _Service:
    """Un service de conversation minimal : la requête est celle du contexte."""

    def __init__(self):
        self.requetes = []

    async def get_chat_completions(self, context):
        self.requetes.append(self.build_chat_completion_params({"messages": list(context.messages)}))
        return iter(())

    def build_chat_completion_params(self, params):
        return {"model": "m", **params}


async def test_c2_vrai_chemin_la_ligne_est_dans_la_requete_avant_la_derniere_parole_jamais_dans_l_historique():
    graphe = _graphe_deux_etapes()
    service = _Service()
    fiche = {"nom": "Durand"}
    montrer_la_fiche(
        service,
        _reglages(),
        lambda: fiche,
        None,
        lambda: (),
        lambda: True,
        lambda: sorties_de(graphe.nodes["start"], graphe),
    )
    contexte = SimpleNamespace(messages=[
        {"role": "system", "content": "Tu es l'accueil."},
        {"role": "user", "content": "Bonjour"},
    ])
    await service.get_chat_completions(contexte)
    messages = service.requetes[-1]["messages"]
    assert "Tu es l'accueil." == messages[0]["content"]  # le prompt système n'a pas bougé
    assert messages[-1] == {"role": "user", "content": "Bonjour"}
    assert "Sortie vers_etape" in messages[-2]["content"]
    assert len(contexte.messages) == 2  # rien dans l'historique


# --------------------------------------------------------------------------- #
# C3 : la garde attend la passe du dernier tour avant de répondre « incomplet »
# --------------------------------------------------------------------------- #


class _Greffier:
    def __init__(self, fiche, ecrit=None):
        self.fiche, self.ecrit, self.delais = fiche, ecrit or {}, []

    async def rattraper(self, delai):
        self.delais.append(delai)
        await asyncio.sleep(0)
        self.fiche.update(self.ecrit)
        return True


def _moteur_gardien(fiche, greffier=None):
    return SimpleNamespace(
        _fiche=_reglages(), _gathered_context=fiche, notes_en_cours=set(), greffier=greffier,
    )


async def test_c3_run_1522_l_adresse_dite_au_tour_meme_est_attendue_puis_la_garde_s_ouvre():
    fiche = {"nom": "Durand"}
    greffier = _Greffier(fiche, {"adresse": "8 rue Pasteur"})
    noeud = _etape("nom", "adresse")
    assert await garde_du_noeud_apres_les_notes(_moteur_gardien(fiche, greffier), noeud) is None
    assert greffier.delais == [DELAI_DE_LA_PASSE_DU_DERNIER_TOUR]  # attente bornée, une seule fois


async def test_c3_si_la_passe_n_apporte_rien_la_garde_reste_incomplete_et_nomme_ce_qui_manque():
    fiche = {"nom": "Durand"}
    greffier = _Greffier(fiche)
    refus = await garde_du_noeud_apres_les_notes(_moteur_gardien(fiche, greffier), _etape("nom", "adresse"))
    assert refus is not None and refus["statut"] == "incomplet" and refus["manque"] == ["adresse"]
    assert len(greffier.delais) == 1


async def test_c3_rien_ne_manque_aucune_attente():
    fiche = {"nom": "Durand", "adresse": "8 rue Pasteur"}
    greffier = _Greffier(fiche)
    assert await garde_du_noeud_apres_les_notes(_moteur_gardien(fiche, greffier), _etape("nom", "adresse")) is None
    assert greffier.delais == []


async def test_c3_le_declenchement_avant_le_tour_n_attend_pas_la_passe_du_dernier_tour():
    # Revue du 26/10 (R-3, décision d'Evan) : avant chaque requête, le déclenchement lit la garde ; la passe du dernier
    # tour n'est attendue que par la garde de l'action elle-même. Le tour ordinaire ne prend plus de silence en plus.
    fiche = {"nom": "Durand"}
    greffier = _Greffier(fiche, {"adresse": "8 rue Pasteur"})
    refus = await garde_du_noeud_apres_les_notes(_moteur_gardien(fiche, greffier), _etape("nom", "adresse"), dernier_seulement=True)
    assert refus["manque"] == ["adresse"]
    assert greffier.delais == []


async def test_c3_sans_greffier_la_garde_est_celle_d_avant():
    fiche = {"nom": "Durand"}
    refus = await garde_du_noeud_apres_les_notes(_moteur_gardien(fiche, None), _etape("nom", "adresse"))
    assert refus["manque"] == ["adresse"]


# --------------------------------------------------------------------------- #
# C4 : « il manque des chiffres » au tour même
# --------------------------------------------------------------------------- #


def _reglages_numero():
    return ReglagesFiche(
        champs=(
            ChampFiche(nom="nom", origine="dicte"),
            ChampFiche(nom="numero_dicte", origine="dicte", chiffres=10),
        ),
        etiquettes=True,
        indices_des_modules=True,
    )


ETAPE_NUMERO = ("nom", "numero_dicte")


def _fiche_avec_numero(tour, *chiffres_par_tour):
    return {
        CLE_TOUR: tour,
        "nombres_lus": [{"tour": t, "type": "telephone", "ecrit": e, "statut": "sure"} for t, e in chiffres_par_tour],
    }


def test_c4_huit_chiffres_lus_au_tour_meme_la_consigne_est_dans_la_requete_de_ce_tour():
    fiche = _fiche_avec_numero(4, (4, "06 22 33 44"))
    messages = [{"role": "user", "content": "zéro six vingt-deux trente-trois quarante-quatre"}]
    texte = etat_avec_les_indices(_reglages_numero(), fiche, None, messages, ETAPE_NUMERO)
    assert CONSIGNE_CHIFFRES_MANQUANTS.format(champs="numero_dicte") in texte


def test_c4_numero_complet_ou_dit_en_deux_fois_rien():
    complet = _fiche_avec_numero(4, (4, "06 22 33 44 55"))
    messages = [{"role": "user", "content": "x"}]
    assert "il manque des chiffres" not in (etat_avec_les_indices(_reglages_numero(), complet, None, messages, ETAPE_NUMERO) or "")
    en_deux_fois = _fiche_avec_numero(5, (4, "06 22 33"), (5, "44 55 66 7"))
    assert "il manque des chiffres" not in (etat_avec_les_indices(_reglages_numero(), en_deux_fois, None, messages, ETAPE_NUMERO) or "")


def test_c4_rien_de_lu_a_ce_tour_ou_champ_deja_rempli_ou_case_eteinte_rien():
    messages = [{"role": "user", "content": "x"}]
    ancien = _fiche_avec_numero(6, (4, "06 22 33 44"))
    assert "il manque des chiffres" not in (etat_avec_les_indices(_reglages_numero(), ancien, None, messages, ETAPE_NUMERO) or "")
    rempli = {**_fiche_avec_numero(4, (4, "06 22 33 44")), "numero_dicte": "0622334455"}
    assert "il manque des chiffres" not in (etat_avec_les_indices(_reglages_numero(), rempli, None, messages, ETAPE_NUMERO) or "")
    eteinte = ReglagesFiche(champs=_reglages_numero().champs, etiquettes=True, indices_des_modules=False)
    assert "il manque des chiffres" not in (
        etat_avec_les_indices(eteinte, _fiche_avec_numero(4, (4, "06 22 33 44")), None, messages, ETAPE_NUMERO) or ""
    )


def test_c4_une_notice_deja_montree_n_est_pas_redite():
    fiche = _fiche_avec_numero(4, (4, "06 22 33 44"))
    notices = Notices(derniere={"consigne": CONSIGNE_CHIFFRES_MANQUANTS.format(champs="numero_dicte")})
    texte = etat_avec_les_indices(_reglages_numero(), fiche, notices, [{"role": "user", "content": "x"}], ETAPE_NUMERO)
    assert texte.count("il manque des chiffres") == 1  # celle de la note, pas une seconde


def test_c4_seuls_les_champs_de_l_etape_un_numero_juste_ne_fait_rien_redemander_ailleurs():
    # Revue du 26/10 (R-1) : dix chiffres justes lus, un champ vide de quatorze chiffres d'une autre étape.
    reglages = ReglagesFiche(
        champs=(
            ChampFiche(nom="numero_dicte", origine="dicte", chiffres=10),
            ChampFiche(nom="identifiant_entreprise", origine="dicte", chiffres=14),
        ),
        etiquettes=True,
        indices_des_modules=True,
    )
    fiche = {**_fiche_avec_numero(4, (4, "06 22 33 44 55")), "numero_dicte": ""}
    messages = [{"role": "user", "content": "zéro six vingt-deux trente-trois quarante-quatre cinquante-cinq"}]
    assert "il manque des chiffres" not in (etat_avec_les_indices(reglages, fiche, None, messages, ("numero_dicte",)) or "")
    assert "il manque des chiffres" in (
        etat_avec_les_indices(reglages, fiche, None, messages, ("identifiant_entreprise",)) or ""
    ), "le champ de l'étape reste candidat"
