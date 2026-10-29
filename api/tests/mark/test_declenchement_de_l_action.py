"""[.mark] Lots 6 et 7 de correctifs-apres-banc-commun : déclencher l'outil d'action (K8) et le champ conditionnel (D-8).

| Test | La garantie |
|---|---|
| lot 7, condition | un champ sans condition est attendu comme avant ; « rempli » / « vaut » / plusieurs lignes ; la MÊME fonction que les phrases de fin |
| lot 7, garde | un champ dont la condition n'est pas tenue ne manque pas (la garde s'ouvre) ; condition tenue et champ vide : « incomplet » |
| lot 7, « Encore attendu » | la ligne montrée au modèle (vrai chemin du moteur) ne nomme pas le champ inactif |
| lot 7, écran-donnée | le champ des données de l'étape est lu, vide = absent, la forme est celle des fins figées |
| lot 6, libre | position libre (défaut) : rien n'est branché sur le cerveau, la requête est celle d'avant |
| lot 6, conditions | une position ne s'arme que garde complète, outil offert, aucun travail en cours, rien fait pour cette demande ; une donnée corrigée rouvre la garde |
| lot 6, relance | une réplique sans question ni appel est retenue puis relancée UNE fois avec l'appel obligatoire, pour ce tour seulement ; question, appel, porte, travail en cours, demande déjà servie : la réplique passe |
| lot 6, obligatoire | le tour part avec l'appel obligatoire, remis comme avant juste après (vrai moteur : requête du modèle) |
| lot 6, automatique | le code confie lui-même le travail (demande type + valeurs de la fiche), une seule fois ; la conversation reprend, le modèle garde ses outils |
| lot 6, règle de l'humain | autre date (appel du modèle), annulation, donnée corrigée : jamais interceptés |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletion  # noqa: F401
from openai import NOT_GIVEN as OPENAI_NOT_GIVEN
from pipecat.utils.types import NOT_GIVEN

from api.services.groupe.passations import choisir_la_fin, condition_tenue
from api.services.pipecat.reponse_avalee import ATTRIBUT_DECLENCHEUR, RepriseSansFluxMixin
from api.services.travail.reglages import NOM_OUTIL
from api.services.workflow.champs_conditionnels import champs_actifs
from api.services.workflow.declenchement_de_l_action import (
    AUTOMATIQUE,
    DEMANDE_PAR_DEFAUT,
    LIBRE,
    OBLIGATOIRE,
    RELANCE,
    Declencheur,
    action_de_l_etape,
    brancher_le_declenchement,
    choix_de_l_outil,
    demande_type_remplie,
    empreinte,
    noter_l_appel,
    noter_le_declenchement,
    position_de,
)
from api.services.workflow.enveloppe_des_actions import garde_du_noeud
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche, etat_avec_les_indices
from api.tests.mark.test_travail_de_fond import RESULTAT, Appel, _appel_d_outil, _texte
from api.tests.mark.test_verite_des_actions import _Base, _morceau, _reponse

RESERVER = "reserver"
CHAMPS = [
    {"nom": "nom", "type": "string", "origine": "dicte"},
    {"nom": "adresse", "type": "string", "origine": "dicte"},
    {"nom": "contrat_entretien", "type": "string", "origine": "deduit", "valeurs": ["souscrit", "aucun"]},
    {"nom": "mail", "type": "string", "origine": "dicte"},
    {"nom": "rendez_vous", "type": "string", "origine": "deduit", "valeurs": ["confirme"], "rempli_par_outil": RESERVER},
]
CONDITION_MAIL = {"champ": "mail", "si": "contrat_entretien", "vaut": "souscrit"}


def _reglages():
    return ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": CHAMPS,
            "fiche_mode_de_note": "greffier",
            "etiquettes_des_etapes": True,
        }
    )


def _noeud(position=None, champs=("nom", "adresse", "mail"), conditions=(CONDITION_MAIL,), demande_type=None, ident="n1"):
    return SimpleNamespace(
        id=ident,
        name="Étape",
        champs_etape=tuple(champs),
        conditions_de_champs=tuple(conditions),
        declenchement_de_l_action=position,
        demande_type=demande_type,
        verite_des_actions=None,
        is_end=False,
    )


class Banc:
    """Un moteur de fiche, une étape, un agent ; les travaux sont une liste modifiable."""

    def __init__(self, position=None, outil=NOM_OUTIL, fiche=None, **noeud):
        self.fiche = dict(fiche if fiche is not None else {"nom": "Durand", "adresse": "8 rue Pasteur", "contrat_entretien": "aucun"})
        self.moteur = SimpleNamespace(_fiche=_reglages(), _gathered_context=self.fiche, travaux=[], notes_en_cours=set())
        self.noeud = _noeud(position, **noeud)
        self.agent = SimpleNamespace(current_node=self.noeud, llm=SimpleNamespace(), travail=None)
        self.outil = outil

    def declencheur(self, position=None):
        return Declencheur(self.moteur, self.agent, self.noeud, position or self.noeud.declenchement_de_l_action, self.outil)


# --------------------------------------------------------------------------- #
# Lot 7 : le champ conditionnel
# --------------------------------------------------------------------------- #


def test_lot7_un_champ_sans_condition_est_attendu_comme_avant():
    noeud = _noeud(conditions=())
    assert champs_actifs(noeud, {}) == ("nom", "adresse", "mail")
    assert champs_actifs(SimpleNamespace(champs_etape=("a", "b")), {}) == ("a", "b")  # un nœud sans le champ de données
    assert champs_actifs(SimpleNamespace(), {}) == ()


def test_lot7_la_condition_a_la_forme_des_fins_figees_et_la_meme_fonction():
    # « rempli » : pas de valeur ; « vaut » : casse ignorée, liste contenante
    assert condition_tenue("contrat_entretien", None, {"contrat_entretien": "souscrit"})
    assert not condition_tenue("contrat_entretien", "", {"contrat_entretien": ""})
    assert condition_tenue("contrat_entretien", "Souscrit", {"contrat_entretien": "souscrit"})
    assert not condition_tenue("contrat_entretien", "souscrit", {"contrat_entretien": "aucun"})
    assert condition_tenue("x", "a", {"x": ["b", "A"]})
    assert condition_tenue("", None, {})  # sans champ : toujours vraie (la phrase par défaut)
    fins = [{"champ": "contrat_entretien", "vaut": "souscrit", "phrase": "Merci, bon entretien."}, {"phrase": "Au revoir."}]
    assert choisir_la_fin(fins, {"contrat_entretien": "souscrit"}) == "Merci, bon entretien."
    assert choisir_la_fin(fins, {"contrat_entretien": "aucun"}) == "Au revoir."


def test_lot7_le_champ_n_est_attendu_que_si_la_condition_est_tenue():
    noeud = _noeud()
    assert champs_actifs(noeud, {"contrat_entretien": "aucun"}) == ("nom", "adresse")
    assert champs_actifs(noeud, {}) == ("nom", "adresse")  # le champ testé n'est pas encore connu
    assert champs_actifs(noeud, {"contrat_entretien": "souscrit"}) == ("nom", "adresse", "mail")
    deux = _noeud(conditions=(CONDITION_MAIL, {"champ": "mail", "si": "nom", "vaut": None}))
    assert champs_actifs(deux, {"contrat_entretien": "souscrit"}) == ("nom", "adresse")
    assert champs_actifs(deux, {"contrat_entretien": "souscrit", "nom": "D"}) == ("nom", "adresse", "mail")


def test_lot7_la_garde_s_ouvre_quand_le_champ_conditionnel_n_est_pas_attendu():
    banc = Banc()
    assert garde_du_noeud(banc.moteur, banc.noeud) is None  # contrat « aucun » : le mail n'est pas attendu
    banc.fiche["contrat_entretien"] = "souscrit"
    refus = garde_du_noeud(banc.moteur, banc.noeud)
    assert refus and refus["statut"] == "incomplet" and refus["manque"] == ["mail"]
    banc.fiche["mail"] = "d@exemple.fr"
    assert garde_du_noeud(banc.moteur, banc.noeud) is None
    sans = Banc(conditions=())  # sans condition : le mail manque comme avant
    assert garde_du_noeud(sans.moteur, sans.noeud)["manque"] == ["mail"]


def test_lot7_encore_attendu_ne_nomme_pas_le_champ_inactif():
    banc = Banc(fiche={"nom": "Durand", "contrat_entretien": "aucun"})
    actifs = champs_actifs(banc.noeud, banc.fiche)
    texte = etat_avec_les_indices(banc.moteur._fiche, banc.fiche, None, [], actifs)
    assert "Encore attendu : adresse." in texte and "mail" not in texte
    banc.fiche["contrat_entretien"] = "souscrit"
    texte = etat_avec_les_indices(banc.moteur._fiche, banc.fiche, None, [], champs_actifs(banc.noeud, banc.fiche))
    assert "Encore attendu : adresse, mail." in texte


async def test_lot7_le_moteur_montre_au_modele_les_champs_attendus_seulement():
    """Vrai chemin : l'état de la fiche ajouté à la requête du modèle lit les conditions de l'étape."""
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.tests import MockLLMService

    appel = Appel()
    try:
        await appel.monter(source_etapes=[_texte("Bonjour.")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False)
        moteur = appel.engine
        moteur._fiche = _reglages()
        moteur._gathered_context.update(nom="Durand", contrat_entretien="aucun")
        noeud = moteur.active_agent.workflow.nodes["start"]
        noeud.champs_etape = ("nom", "adresse", "mail")
        noeud.conditions_de_champs = (CONDITION_MAIL,)
        moteur.active_agent.current_node = noeud
        llm = MockLLMService(mock_steps=[_texte("Ok.")], chunk_delay=0.001)
        moteur._porter_la_fiche(llm)
        vues = []
        construire = llm.build_chat_completion_params

        def capter(params):
            rendu = construire(params)
            vues.append(rendu)
            return rendu

        llm.build_chat_completion_params = capter
        contexte = LLMContext(messages=[{"role": "user", "content": "Bonjour"}])
        async for _ in await llm.get_chat_completions(contexte):
            pass
        etat = " ".join(str(m.get("content")) for m in vues[-1]["messages"])
        assert "Encore attendu : adresse." in etat and "mail" not in etat
    finally:
        await appel.arreter()


def test_lot7_le_champ_de_donnees_est_lu_et_vide_vaut_absent():
    from api.services.workflow.dto import AgentNodeData, StartCallNodeData, _sanitize_node

    donnees = AgentNodeData.model_validate({"name": "a", "prompt": "p", "conditions_de_champs": [CONDITION_MAIL]})
    assert donnees.conditions_de_champs[0].si == "contrat_entretien" and donnees.conditions_de_champs[0].champ == "mail"
    assert AgentNodeData(name="a", prompt="p").conditions_de_champs is None
    assert StartCallNodeData(name="a", prompt="p").conditions_de_champs is None  # fiabilite-de-la-conversation, C1 : la liste existe aussi sur l'étape de départ (vide = absent)
    propre = _sanitize_node({"type": "agentNode", "data": {"name": "a", "prompt": "p", "conditions_de_champs": []}})
    assert "conditions_de_champs" not in propre["data"]
    garde = _sanitize_node({"type": "agentNode", "data": {"name": "a", "prompt": "p", "conditions_de_champs": [CONDITION_MAIL]}})
    assert garde["data"]["conditions_de_champs"] == [CONDITION_MAIL]


def test_lot7_le_noeud_du_graphe_porte_les_conditions():
    from api.services.workflow.dto import AgentNodeData
    from api.services.workflow.workflow_graph import Node

    donnees = AgentNodeData.model_validate(
        {"name": "a", "prompt": "p", "champs_etape": "nom, mail", "conditions_de_champs": [CONDITION_MAIL]}
    )
    noeud = Node(id="n", node_type="agentNode", data=donnees)
    assert noeud.champs_etape == ("nom", "mail") and noeud.conditions_de_champs == (CONDITION_MAIL,)
    assert Node(id="n", node_type="agentNode", data=AgentNodeData(name="a", prompt="p")).conditions_de_champs == ()


# --------------------------------------------------------------------------- #
# Lot 6 : les données de l'étape
# --------------------------------------------------------------------------- #


def test_lot6_le_menu_est_libre_par_defaut_et_n_est_pas_dans_le_formulaire():
    from api.services.workflow.dto import AgentNodeData, StartCallNodeData, _sanitize_node
    from api.services.workflow.node_specs import get_spec

    for classe in (AgentNodeData, StartCallNodeData):
        donnees = classe(name="a", prompt="p")
        assert donnees.declenchement_de_l_action is None and donnees.demande_type is None
    for nom in ("agentNode", "startCall"):
        noms = {p.name for p in get_spec(nom).properties}
        assert not ({"declenchement_de_l_action", "demande_type", "conditions_de_champs"} & noms)
    propre = _sanitize_node(
        {"type": "agentNode", "data": {"name": "a", "prompt": "p", "declenchement_de_l_action": "libre", "demande_type": "  "}}
    )
    assert "declenchement_de_l_action" not in propre["data"] and "demande_type" not in propre["data"]
    garde = _sanitize_node(
        {"type": "agentNode", "data": {"name": "a", "prompt": "p", "declenchement_de_l_action": "relance", "demande_type": "Réserve {{nom}}"}}
    )
    assert garde["data"]["declenchement_de_l_action"] == "relance" and garde["data"]["demande_type"] == "Réserve {{nom}}"
    with pytest.raises(ValueError):
        AgentNodeData(name="a", prompt="p", declenchement_de_l_action="toujours")


def test_lot6_position_de_ne_connait_que_les_quatre_positions():
    assert position_de(_noeud(None)) == LIBRE
    assert position_de(_noeud("libre")) == LIBRE
    assert position_de(_noeud("n_importe_quoi")) == LIBRE
    assert [position_de(_noeud(p)) for p in (RELANCE, OBLIGATOIRE, AUTOMATIQUE)] == [RELANCE, OBLIGATOIRE, AUTOMATIQUE]


def test_lot6_l_outil_de_l_etape_est_le_travail_de_fond_sinon_l_unique_action():
    assert action_de_l_etape(frozenset({"chercher", "reserver"}), True) == NOM_OUTIL
    assert action_de_l_etape(frozenset({"reserver"}), False) == "reserver"
    assert action_de_l_etape(frozenset({"chercher", "reserver"}), False) is None
    assert action_de_l_etape(frozenset(), False) is None


def test_lot6_la_demande_type_prend_les_valeurs_de_la_fiche():
    fiche = {"nom": "Durand", "adresse": "  8 rue   Pasteur ", "tags": ["a", "b"]}
    assert demande_type_remplie("Réserve pour {{nom}} au {{ adresse }}, {{tags}}, {{inconnu}}.", fiche) == (
        "Réserve pour Durand au 8 rue Pasteur, a, b, ."
    )
    assert demande_type_remplie(None, fiche) == DEMANDE_PAR_DEFAUT
    assert demande_type_remplie("   ", fiche) == DEMANDE_PAR_DEFAUT


def test_lot6_l_empreinte_suit_les_donnees_de_l_etape_et_pas_le_resultat_de_l_action():
    banc = Banc()
    base = empreinte(banc.moteur, banc.noeud)
    banc.fiche["rendez_vous"] = "confirme"  # écrit par l'action : la garde ne se rouvre pas de son fait
    banc.fiche["contrat_entretien"] = "aucun"  # hors liste de l'étape
    assert empreinte(banc.moteur, banc.noeud) == base
    banc.fiche["adresse"] = "9 rue Pasteur"  # donnée corrigée
    assert empreinte(banc.moteur, banc.noeud) != base
    assert empreinte(banc.moteur, _noeud(champs=())) == "[]"


# --------------------------------------------------------------------------- #
# Lot 6 : quand une position s'arme
# --------------------------------------------------------------------------- #


async def test_lot6_s_arme_garde_complete_et_se_tait_sinon():
    banc = Banc(RELANCE)
    d = banc.declencheur()
    assert await d.armer() is True
    del banc.fiche["adresse"]
    assert await d.armer() is False  # la garde refuse : il manque une donnée
    banc.fiche["adresse"] = "8 rue Pasteur"
    banc.fiche["contrat_entretien"] = "souscrit"  # le mail devient attendu (lot 7)
    assert await d.armer() is False
    banc.fiche["mail"] = "d@exemple.fr"
    assert await d.armer() is True


async def test_lot6_aucune_position_ne_s_arme_pendant_un_travail_en_cours():
    for position in (RELANCE, OBLIGATOIRE, AUTOMATIQUE):
        banc = Banc(position)
        banc.moteur.travaux.append(SimpleNamespace(occupe=True))
        assert await banc.declencheur().armer() is False
        banc.moteur.travaux[0].occupe = False
        assert await banc.declencheur().armer() is True


async def test_lot6_aucune_position_ne_s_arme_apres_un_appel_pour_la_meme_demande_une_donnee_corrigee_rouvre():
    for position in (RELANCE, OBLIGATOIRE, AUTOMATIQUE):
        banc = Banc(position)
        d = banc.declencheur()
        assert await d.armer() is True
        noter_l_appel(banc.moteur, banc.agent, NOM_OUTIL)  # le modèle (ou le code) a appelé l'outil
        assert await d.armer() is False
        banc.fiche["adresse"] = "9 rue Pasteur"  # l'appelant corrige son adresse
        assert await d.armer() is True
        noter_le_declenchement(banc.moteur, banc.noeud, NOM_OUTIL)
        assert await d.armer() is False


async def test_lot6_l_appel_d_un_autre_outil_ne_ferme_pas_la_demande():
    banc = Banc(RELANCE)
    noter_l_appel(banc.moteur, banc.agent, "annuler")
    assert await banc.declencheur().armer() is True


async def test_lot6_etape_sans_champ_relance_et_obligatoire_se_taisent_l_automatique_part_a_l_entree():
    for position, attendu in ((RELANCE, False), (OBLIGATOIRE, False), (AUTOMATIQUE, True)):
        banc = Banc(position, champs=(), conditions=())
        assert await banc.declencheur().armer() is attendu
    banc = Banc(AUTOMATIQUE, champs=(), conditions=())
    noter_le_declenchement(banc.moteur, banc.noeud, NOM_OUTIL)
    assert await banc.declencheur().armer() is False  # une seule demande par étape sans champ


async def test_lot6_libre_et_etape_qui_n_est_plus_courante_ne_s_arment_jamais():
    assert await Banc(None).declencheur(LIBRE).armer() is False
    banc = Banc(RELANCE)
    banc.agent.current_node = _noeud(RELANCE, ident="ailleurs")
    assert await banc.declencheur().armer() is False
    banc.agent.current_node = None
    assert await banc.declencheur().armer() is False


async def test_lot6_la_garde_attend_la_note_du_tour_comme_l_outil_le_fait():
    """K2 : la dernière donnée est dite ce tour-ci, la passe du greffier l'écrit pendant que le tour part."""
    banc = Banc(OBLIGATOIRE)
    del banc.fiche["adresse"]

    async def note():
        await asyncio.sleep(0.05)
        banc.fiche["adresse"] = "8 rue Pasteur"

    tache = asyncio.ensure_future(note())
    banc.moteur.notes_en_cours.add(tache)
    assert await banc.declencheur().armer() is True
    await tache


# --------------------------------------------------------------------------- #
# Lot 6 : le branchement (libre = rien)
# --------------------------------------------------------------------------- #


def test_lot6_libre_ne_branche_rien_sur_le_cerveau():
    banc = Banc(None)
    llm = SimpleNamespace(get_chat_completions=lambda c: None)
    banc.agent.llm = llm
    avant = dict(vars(llm))
    assert brancher_le_declenchement(banc.moteur, banc.agent, banc.noeud, NOM_OUTIL) == LIBRE
    assert vars(llm) == avant  # ni attribut, ni enveloppe : octet pour octet


def test_lot6_une_position_sans_outil_unique_n_arme_rien():
    banc = Banc(RELANCE)
    assert brancher_le_declenchement(banc.moteur, banc.agent, banc.noeud, None) == LIBRE
    assert getattr(banc.agent.llm, ATTRIBUT_DECLENCHEUR, None) is None


def test_lot6_relance_pose_le_declencheur_sans_envelopper_la_requete_obligatoire_et_automatique_l_enveloppent():
    for position, enveloppe in ((RELANCE, False), (OBLIGATOIRE, True), (AUTOMATIQUE, True)):
        banc = Banc(position)

        async def obtenir(context):
            return "flux"

        llm = SimpleNamespace(get_chat_completions=obtenir)
        banc.agent.llm = llm
        assert brancher_le_declenchement(banc.moteur, banc.agent, banc.noeud, NOM_OUTIL) == position
        assert getattr(llm, ATTRIBUT_DECLENCHEUR).position == position
        assert (llm.get_chat_completions is not obtenir) is enveloppe
    # un retour en « libre » retire le déclencheur
    banc.noeud.declenchement_de_l_action = None
    brancher_le_declenchement(banc.moteur, banc.agent, banc.noeud, NOM_OUTIL)
    assert getattr(banc.agent.llm, ATTRIBUT_DECLENCHEUR) is None


def test_lot6_le_moteur_nomme_l_outil_unique_de_l_etape_par_l_enveloppe_des_actions():
    from api.services.workflow.declenchement_de_l_action import actions_offertes, commencer_la_liste_des_actions
    from api.services.workflow.enveloppe_des_actions import envelopper_l_action

    banc = Banc(RELANCE)
    commencer_la_liste_des_actions(banc.moteur)
    envelopper_l_action(banc.moteur, RESERVER, lambda p: None, banc.agent)
    envelopper_l_action(banc.moteur, "interne", lambda p: None, banc.agent, garde=False)  # une action interne n'est pas gardée
    assert actions_offertes(banc.moteur) == frozenset({RESERVER})
    commencer_la_liste_des_actions(banc.moteur)
    assert actions_offertes(banc.moteur) == frozenset()


# --------------------------------------------------------------------------- #
# Lot 6 : relance (le vrai mixin)
# --------------------------------------------------------------------------- #


class _Contexte:
    def __init__(self, messages):
        self.messages = messages
        self.tool_choice = NOT_GIVEN
        self.choix_poses = []

    def set_tool_choice(self, choix):
        self.tool_choice = choix
        self.choix_poses.append(choix)


class _ServiceDeChoix(RepriseSansFluxMixin, _Base):
    def get_llm_adapter(self):
        return SimpleNamespace(
            get_llm_invocation_params=lambda context, **k: {"messages": list(context.messages), "tool_choice": context.tool_choice}
        )

    async def get_chat_completions(self, context):
        return await super().get_chat_completions(context)


async def _jouer(banc, morceaux, reprise=None, messages=None):
    service = _ServiceDeChoix(morceaux, reprise=reprise)
    declencheur = banc.declencheur()
    setattr(service, ATTRIBUT_DECLENCHEUR, declencheur)
    contexte = _Contexte(messages or [{"role": "user", "content": "Voilà mon adresse"}])
    sortie = [m async for m in await service.get_chat_completions(contexte)]
    return service, contexte, sortie


def _dit(sortie):
    return "".join(m.choices[0].delta.content or "" for m in sortie if m.choices)


async def test_k8_une_replique_sans_question_ni_appel_est_retenue_et_relancee_avec_l_appel_obligatoire():
    """Run 1497 et 1519 : « Je réserve le rendez-vous. » dit sans appel, tout est prêt."""
    banc = Banc(RELANCE)
    flux = [_morceau("Je réserve le rendez-vous."), _morceau(fin="stop")]
    service, contexte, sortie = await _jouer(banc, flux, _reponse("..."))
    [requete] = service.requetes
    assert requete["stream"] is False
    assert requete["tool_choice"] == choix_de_l_outil(NOM_OUTIL)
    assert _dit(sortie) == "..."
    # pour ce tour seulement : le contexte est remis comme avant
    assert contexte.tool_choice is NOT_GIVEN and len(contexte.choix_poses) == 2


async def test_k8_la_relance_n_est_faite_qu_une_fois_et_une_relance_vide_laisse_passer_la_replique():
    banc = Banc(RELANCE)
    flux = [_morceau("Je réserve le rendez-vous."), _morceau(fin="stop")]
    service, _, sortie = await _jouer(banc, flux, _reponse(""))
    assert len(service.requetes) == 1 and _dit(sortie) == "Je réserve le rendez-vous."
    service, _, sortie = await _jouer(banc, flux, None)
    assert _dit(sortie) == "Je réserve le rendez-vous."


async def test_k8_une_question_une_porte_ou_un_appel_passent_tels_quels():
    banc = Banc(RELANCE)
    for texte in ("Quelle est votre adresse ?", "Merci. → retour"):
        service, _, sortie = await _jouer(banc, [_morceau(texte), _morceau(fin="stop")], _reponse("jamais"))
        assert service.requetes == [] and _dit(sortie) == texte
    flux = [_morceau("Je lance."), _morceau(outil=NOM_OUTIL), _morceau(fin="tool_calls")]
    service, _, sortie = await _jouer(banc, flux, _reponse("jamais"))
    assert service.requetes == [] and sortie == flux


async def test_k8_garde_incomplete_travail_en_cours_ou_demande_servie_la_replique_passe():
    flux = [_morceau("D'accord."), _morceau(fin="stop")]
    banc = Banc(RELANCE)
    del banc.fiche["adresse"]
    service, _, sortie = await _jouer(banc, flux, _reponse("jamais"))
    assert service.requetes == [] and _dit(sortie) == "D'accord."
    banc = Banc(RELANCE)
    banc.moteur.travaux.append(SimpleNamespace(occupe=True))
    service, _, _ = await _jouer(banc, flux, _reponse("jamais"))
    assert service.requetes == []
    banc = Banc(RELANCE)
    noter_l_appel(banc.moteur, banc.agent, NOM_OUTIL)
    service, _, _ = await _jouer(banc, flux, _reponse("jamais"))
    assert service.requetes == []


async def test_k8_une_donnee_corrigee_rouvre_la_relance():
    flux = [_morceau("D'accord."), _morceau(fin="stop")]
    banc = Banc(RELANCE)
    noter_l_appel(banc.moteur, banc.agent, NOM_OUTIL)
    banc.fiche["adresse"] = "9 rue Pasteur"
    service, _, _ = await _jouer(banc, flux, _reponse("Je lance."))
    assert len(service.requetes) == 1


async def test_k8_libre_obligatoire_et_automatique_ne_relancent_jamais():
    flux = [_morceau("Je réserve."), _morceau(fin="stop")]
    for position in (None, OBLIGATOIRE, AUTOMATIQUE):
        banc = Banc(position)
        service = _ServiceDeChoix(flux, reprise=_reponse("jamais"))
        setattr(service, ATTRIBUT_DECLENCHEUR, banc.declencheur(position or LIBRE))
        contexte = _Contexte([{"role": "user", "content": "x"}])
        assert [m async for m in await service.get_chat_completions(contexte)] == flux
        assert service.requetes == []


async def test_k8_la_relance_s_ajoute_a_la_verite_des_actions_sans_la_remplacer():
    """La case « vérité des actions » garde sa retenue (date inventée) ; la relance vient après."""
    from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE
    from api.services.workflow.verite_des_actions import CONSIGNE_DATE, VerificateurDeReplique

    banc = Banc(RELANCE)
    service = _ServiceDeChoix([_morceau("Le 9 novembre."), _morceau(fin="stop")], reprise=_reponse("Je vérifie."))
    setattr(service, ATTRIBUT_VERITE, VerificateurDeReplique(banc.moteur, banc.agent))
    setattr(service, ATTRIBUT_DECLENCHEUR, banc.declencheur())
    contexte = _Contexte([{"role": "user", "content": "x"}])
    sortie = [m async for m in await service.get_chat_completions(contexte)]
    [requete] = service.requetes
    assert _dit(sortie) == "Je vérifie."
    assert any(CONSIGNE_DATE == m.get("content") for m in requete["messages"])  # la retenue de la vérité des actions
    assert requete["tool_choice"] is NOT_GIVEN  # elle n'impose pas d'outil


# --------------------------------------------------------------------------- #
# Lot 6 : obligatoire et automatique, par le vrai moteur
# --------------------------------------------------------------------------- #


def _fiche_du_moteur(moteur, noeud, position, demande_type=None, **fiche):
    moteur._fiche = _reglages()
    moteur._gathered_context.update({"nom": "Durand", "adresse": "8 rue Pasteur", "contrat_entretien": "aucun", **fiche})
    noeud.champs_etape = ("nom", "adresse", "mail")
    noeud.conditions_de_champs = (CONDITION_MAIL,)
    noeud.declenchement_de_l_action = position
    noeud.demande_type = demande_type


def _capter_les_choix(llm):
    choix = []
    construire = llm.build_chat_completion_params

    def capter(params):
        choix.append(params.get("tool_choice", OPENAI_NOT_GIVEN))
        return construire(params)

    llm.build_chat_completion_params = capter
    return choix


@pytest.fixture
async def appel():
    a = Appel()
    try:
        yield a
    finally:
        await a.arreter()


async def test_k8_obligatoire_le_tour_part_avec_l_appel_obligatoire_puis_le_choix_est_remis(appel):
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": "Réserve."}, "call_confier"),
            _texte("Je m'en occupe."),
            _texte("Voilà."),
        ],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    moteur = appel.engine
    noeud = moteur.active_agent.workflow.nodes["start"]
    _fiche_du_moteur(moteur, noeud, OBLIGATOIRE)  # contrat « aucun » : le mail n'est pas attendu, tout est prêt
    choix = _capter_les_choix(moteur.active_agent.llm)
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    assert choix[0] == choix_de_l_outil(NOM_OUTIL)
    assert all(c is OPENAI_NOT_GIVEN for c in choix[1:])  # pour un seul tour : jamais deux tours de suite
    assert len(appel.travaux()) == 1


async def test_k8_obligatoire_ne_s_arme_pas_quand_une_donnee_attendue_manque(appel):
    await appel.monter(
        source_etapes=[_texte("Quelle est votre adresse ?")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False
    )
    moteur = appel.engine
    noeud = moteur.active_agent.workflow.nodes["start"]
    _fiche_du_moteur(moteur, noeud, OBLIGATOIRE, contrat_entretien="souscrit")  # le mail est attendu et manque
    choix = _capter_les_choix(moteur.active_agent.llm)
    await appel.ouvrir()
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 1)
    assert choix and all(c is OPENAI_NOT_GIVEN for c in choix)
    assert appel.travaux() == []


async def test_k8_libre_la_requete_est_celle_d_avant(appel):
    await appel.monter(
        source_etapes=[_texte("Je regarde.")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False
    )
    moteur = appel.engine
    llm = moteur.active_agent.llm
    _fiche_du_moteur(moteur, moteur.active_agent.workflow.nodes["start"], None)
    choix = _capter_les_choix(llm)
    await appel.ouvrir()
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 1)
    assert choix and all(c is OPENAI_NOT_GIVEN for c in choix)
    assert getattr(llm, ATTRIBUT_DECLENCHEUR, None) is None
    assert not getattr(llm, "_mark_declenchement_des_tours", False)


async def test_k8_automatique_le_code_confie_lui_meme_le_travail_avec_la_demande_type_et_la_fiche(appel):
    await appel.monter(
        source_etapes=[_texte("Je regarde."), _texte("Voilà, c'est fait.")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    moteur = appel.engine
    noeud = moteur.active_agent.workflow.nodes["start"]
    _fiche_du_moteur(moteur, noeud, AUTOMATIQUE, demande_type="Réserve un créneau pour {{nom}} au {{adresse}}.")
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    [travail] = appel.travaux()
    assert travail["demande"].startswith("Réserve un créneau pour Durand au 8 rue Pasteur.")
    assert "- nom : Durand" in travail["demande"] and "- adresse : 8 rue Pasteur" in travail["demande"]  # K11
    assert travail["declenche_par"] == AUTOMATIQUE
    # le modèle n'a eu aucun outil à appeler pour cela ; il annonce le résultat à son arrivée
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 2)
    assert not [m for m in appel.messages() if m.get("role") == "tool"]
    # une seule fois pour cette demande
    d = moteur.active_agent.llm.mark_declencheur
    assert await d.armer() is False
    await d.avant_le_tour(SimpleNamespace(set_tool_choice=lambda c: None))
    assert len(appel.travaux()) == 1


async def test_k8_automatique_la_conversation_reprend_apres_le_resultat_le_modele_garde_ses_outils(appel):
    """Règle de l'humain : « autre date » après le résultat. Le modèle confie lui-même une nouvelle demande, le code
    ne l'intercepte pas et ne lance rien de son côté."""
    await appel.monter(
        source_etapes=[
            _texte("Je regarde."),
            _appel_d_outil(NOM_OUTIL, {"demande": "Cherche plutôt un autre jour."}, "call_autre"),
            _texte("Je cherche un autre jour."),
            _texte("Jeudi, alors."),
        ],
        fond_etapes=[_texte(RESULTAT), _texte("Autre jour : jeudi.")],
        outils_du_fond=False,
    )
    moteur = appel.engine
    noeud = moteur.active_agent.workflow.nodes["start"]
    _fiche_du_moteur(moteur, noeud, AUTOMATIQUE)
    await appel.ouvrir()
    await appel.attendre(lambda: len(appel.travaux()) == 2 and all(t["remis"] for t in appel.travaux()))
    premier, second = appel.travaux()
    assert premier["declenche_par"] == AUTOMATIQUE
    assert "declenche_par" not in second and second["demande"].startswith("Cherche plutôt un autre jour.")
    outils = [m for m in appel.messages() if m.get("role") == "tool"]
    assert len(outils) == 1  # le seul appel d'outil de la conversation est celui du modèle


async def test_k8_automatique_sans_les_champs_pret_n_est_pas_lance(appel):
    await appel.monter(source_etapes=[_texte("Quel est votre nom ?")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False)
    moteur = appel.engine
    noeud = moteur.active_agent.workflow.nodes["start"]
    _fiche_du_moteur(moteur, noeud, AUTOMATIQUE)
    del moteur._gathered_context["nom"]
    await appel.ouvrir()
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 1)
    await asyncio.sleep(0.2)
    assert appel.travaux() == []


async def test_k8_automatique_une_donnee_corrigee_ne_relance_pas_une_demande_de_meme_texte(appel):
    """Règle de l'humain, révisée par fiabilite-de-la-conversation (B1, B2, décision D-5) : l'appelant corrige son
    adresse. Le travail en cours n'est jamais doublé ; une fois fini, la demande type est de même texte (la fiche
    n'entre pas dans la règle « demande identique », run 1950) : elle n'est pas relancée, le résultat reste connu.
    Le modèle garde ses outils pour une demande autrement écrite."""
    await appel.monter(
        source_etapes=[_texte("Je regarde."), _texte("Voilà."), _texte("Je regarde de nouveau."), _texte("Voilà.")],
        fond_etapes=[_texte(RESULTAT), _texte("Autre résultat.")],
        outils_du_fond=False,
    )
    moteur = appel.engine
    noeud = moteur.active_agent.workflow.nodes["start"]
    _fiche_du_moteur(moteur, noeud, AUTOMATIQUE)
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux())
    d = moteur.active_agent.llm.mark_declencheur
    moteur._gathered_context["adresse"] = "9 rue Pasteur"
    if moteur.active_agent.travail.occupe:
        assert await d.armer() is False  # un travail est en cours : rien ne part
    await moteur.active_agent.travail.attendre()
    await d.lancer_automatiquement()
    assert len(appel.travaux()) == 1
    assert "- adresse : 8 rue Pasteur" in appel.travaux()[0]["demande"]
    assert appel.travaux()[0]["redemandes"] >= 1


async def test_k8_relance_le_moteur_pose_le_declencheur_sur_l_etape_qui_offre_confier(appel):
    await appel.monter(source_etapes=[_texte("Bonjour.")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False)
    moteur = appel.engine
    noeud = moteur.active_agent.workflow.nodes["start"]
    _fiche_du_moteur(moteur, noeud, RELANCE)
    await appel.ouvrir()
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 1)
    declencheur = getattr(moteur.active_agent.llm, ATTRIBUT_DECLENCHEUR)
    assert declencheur.position == RELANCE and declencheur.outil == NOM_OUTIL
    assert not getattr(moteur.active_agent.llm, "_mark_declenchement_des_tours", False)  # la relance n'enveloppe pas la requête


# --------------------------------------------------------------------------- #
# Figeage (Evan, 29/10) : après un échec du travail de l'étape, plus de relance par le code
# --------------------------------------------------------------------------- #


async def test_figeage_aucune_position_ne_s_arme_apres_un_echec_du_travail_de_l_etape():
    from api.services.travail.demande_identique import CLE_ETAPE, identifiant_de_l_etape

    for position in (RELANCE, OBLIGATOIRE, AUTOMATIQUE):
        banc = Banc(position)
        d = banc.declencheur()
        etape = identifiant_de_l_etape(banc.noeud, banc.agent)
        banc.fiche["travaux"] = [{CLE_ETAPE: "autre", "statut": "echec"}]
        assert await d.armer() is True  # l'échec d'une autre étape ne compte pas
        banc.fiche["travaux"].append({CLE_ETAPE: etape, "statut": "echec"})
        assert await d.armer() is False
        banc.fiche["adresse"] = "9 rue Pasteur"  # la fiche retouchée ne réarme pas (banc v12, E9)
        assert await d.armer() is False
        banc.fiche["travaux"].append({CLE_ETAPE: etape, "statut": "fait"})  # l'agent a relancé et réussi
        assert await d.armer() is True
