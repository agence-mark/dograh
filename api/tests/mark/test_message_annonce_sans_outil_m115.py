"""[.mark] SA-49 (M115, appel de production 2597) : l'action de l'étape annoncée sans que son outil soit appelé, puis la fin.

Groupe 299 -> agent 302, étape « message » (outils : ``laisser_un_message``, deux lectures ; déclenchement « relance », champ ``objet_message``).
La personne (un contrôle d'hygiène) arrive avec son objet déjà dit dans la passation. L'agent répond « C'est entendu, je laisse un message à
l'équipe pour qu'elle vous rappelle au sujet du contrôle d'hygiène de la semaine prochaine. Puis-je faire autre chose pour vous ? » SANS appeler
l'outil ; « Non, c'est tout » -> ``fin`` : le message n'existe pas. Trois mécanismes n'ont rien fait :

1. la vérité des actions : l'étape n'écrit rien (aucun ``rempli_par_outil``), elle n'était pas branchée ; et « je laisse » n'était retenu que
   si un outil du tour avait échoué (M112) : ici, aucun outil d'action dans le tour (seul le passage d'étape, « done ») ;
2. la relance de l'action : trois actions offertes, aucune qui remplit un champ -> ``action_de_l_etape`` rendait ``None`` et la position
   « relance » retombait en « libre » (journalisé) ; elle ne relance pas non plus une réplique qui contient une question, et le greffier n'avait
   pas écrit ``objet_message`` (il a écrit ``motif``) ;
3. la garde de fin ne voit que les outils APPELÉS : un outil jamais appelé ne compte pas.

Le mécanisme (commun, aucun mot de métier) : une action du catalogue peut se déclarer « doit aboutir » (``Action.doit_aboutir``, posé sur
``laisser_un_message``) ; l'unique action « doit aboutir » d'une étape est son action ; une étape qui déclare son action (position autre que
Libre) la pose dans la fiche. La vérité des actions retient alors l'annonce sans appel et relance une fois avec l'appel obligatoire ; la garde
de fin refuse la fin une fois en nommant l'outil (G2 : la seconde passe, la personne qui renonce peut partir).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from api.services.integrations.connectors import catalogue  # noqa: F401  (charge le catalogue)
from api.services.workflow import action_non_aboutie as fin
from api.services.workflow.declenchement_de_l_action import action_de_l_etape
from api.services.workflow.verite_des_actions import (
    CONSIGNE_PRISE_SANS_ACTION,
    RAISON_PRISE_SANS_ACTION,
    VerificateurDeReplique,
    brancher_la_verite_des_actions,
    noter_l_action,
)
from api.tests.mark.test_verite_des_actions import _Base, _morceau, _reponse, _texte
from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE, RepriseSansFluxMixin

OUTIL = "laisser_un_message"

MESSAGES_2597 = [
    {"role": "assistant", "content": "Casa Italia bonjour, je suis Giulia, l'assistante du restaurant. Qu'est-ce que je peux faire pour vous ?"},
    {
        "role": "user",
        "content": "Bonjour, ici madame Leroy de la direction départementale de la protection des populations, je souhaite joindre le gérant "
        "au sujet du contrôle d'hygiène de la semaine prochaine.",
    },
    {"role": "assistant", "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "message", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "t1", "content": json.dumps({"status": "done"})},
]
DIT_2597 = (
    "C'est entendu, je laisse un message à l'équipe pour qu'elle vous rappelle au sujet du contrôle d'hygiène de la semaine prochaine. "
    "Puis-je faire autre chose pour vous ?"
)


def _banc(attendue: str | None = OUTIL):
    fiche: dict = {}
    moteur = SimpleNamespace(_fiche=None, _gathered_context=fiche, reglages_appel={}, active_agent=None)
    fin.poser_l_action_attendue(moteur, attendue)
    noeud = SimpleNamespace(verite_des_actions=None, champs_etape=("objet_message",), is_end=False)
    agent = SimpleNamespace(current_node=noeud, llm=SimpleNamespace(), reglages={})
    moteur.active_agent = agent
    return moteur, agent, noeud


class _Service(RepriseSansFluxMixin, _Base):
    pass


class _Contexte:
    def __init__(self, messages):
        self.messages = messages
        self.tool_choice = None
        self.choix = []

    def set_tool_choice(self, choix):
        self.choix.append(choix)
        self.tool_choice = choix


# -- 1. la vérité des actions -------------------------------------------------------------------------------


async def test_2597_l_annonce_sans_appel_est_retenue_et_relancee_avec_l_outil_obligatoire():
    moteur, agent, _ = _banc()
    retenue = VerificateurDeReplique(moteur, agent, par_les_chiffres=True).controler(DIT_2597, MESSAGES_2597)
    assert retenue is not None and retenue.raison == RAISON_PRISE_SANS_ACTION and retenue.outil == OUTIL, retenue
    assert "je laisse" in retenue.detail.casefold()

    service = _Service([_morceau(DIT_2597), _morceau(fin="stop")], reprise=_reponse("Je m'en occupe."))
    setattr(service, ATTRIBUT_VERITE, VerificateurDeReplique(moteur, agent, par_les_chiffres=True))
    contexte = _Contexte(list(MESSAGES_2597))
    morceaux = [m async for m in await service.get_chat_completions(contexte)]
    assert _texte(morceaux) == "Je m'en occupe."  # la réplique d'origine n'est pas dite
    [requete] = service.requetes
    assert any(m.get("content") == CONSIGNE_PRISE_SANS_ACTION for m in requete["messages"])
    assert {"type": "function", "function": {"name": OUTIL}} in contexte.choix  # l'appel obligatoire, pour la relance


def test_les_autres_tournures_d_annonce_sont_retenues_une_question_non():
    moteur, agent, _ = _banc()
    v = VerificateurDeReplique(moteur, agent, par_les_chiffres=True)
    for dit in ("Je vais lui transmettre votre demande.", "C'est transmis à l'équipe.", "Votre message est bien noté, l'équipe vous rappelle."):
        assert v.controler(dit, MESSAGES_2597) is not None, dit
    assert v.controler("Voulez-vous que je laisse un message à l'équipe ?", MESSAGES_2597) is None
    assert v.controler("Que voulez-vous que l'équipe sache ?", MESSAGES_2597) is None


def test_une_etape_sans_action_declaree_ne_change_pas():
    moteur, agent, _ = _banc(attendue=None)
    assert VerificateurDeReplique(moteur, agent, par_les_chiffres=True).controler(DIT_2597, MESSAGES_2597) is None


def test_un_message_reellement_laisse_ne_declenche_rien():
    moteur, agent, _ = _banc()
    noter_l_action(moteur, OUTIL, {"objet": "contrôle"}, {"statut": "OK", "faits": {"urgence": "normale"}}, {})
    v = VerificateurDeReplique(moteur, agent, par_les_chiffres=True)
    assert v.controler("C'est transmis, l'équipe vous rappelle. Autre chose ?", [{"role": "user", "content": "Leroy, Anne."}]) is None
    assert fin.verifier_la_fin(moteur) is None


def test_l_outil_appele_dans_le_tour_laisse_decider_son_resultat():
    moteur, agent, _ = _banc()
    messages = [
        {"role": "user", "content": "Pour le contrôle."},
        {"role": "assistant", "tool_calls": [{"id": "t2", "type": "function", "function": {"name": OUTIL, "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "t2", "content": json.dumps({"statut": "OK", "faits": {}, "suggestion": ""})},
    ]
    assert VerificateurDeReplique(moteur, agent, par_les_chiffres=True).controler("Je laisse le message à l'équipe.", messages) is None


def test_la_verite_se_branche_sur_une_etape_qui_declare_son_action_et_pas_sur_les_autres():
    moteur, agent, noeud = _banc()
    assert brancher_la_verite_des_actions(moteur, agent, noeud, offre_une_action=False) is True
    assert isinstance(getattr(agent.llm, ATTRIBUT_VERITE), VerificateurDeReplique)
    moteur2, agent2, noeud2 = _banc(attendue=None)
    assert brancher_la_verite_des_actions(moteur2, agent2, noeud2, offre_une_action=False) is False
    assert getattr(agent2.llm, ATTRIBUT_VERITE) is None


# -- 2. l'action de l'étape (la relance s'arme) ---------------------------------------------------------------


def _outil(action: str, config: dict | None = None):
    return SimpleNamespace(category="integration", definition={"config": {"connecteur": "service", "action": action, **(config or {})}})


def test_l_action_du_catalogue_se_declare_doit_aboutir_la_case_de_l_outil_passe_devant():
    assert fin.outil_doit_aboutir(_outil(OUTIL)) is True
    assert fin.outil_doit_aboutir(_outil("infos_pratiques")) is False
    assert fin.outil_doit_aboutir(_outil(OUTIL, {fin.CLE_DE_L_OUTIL: False})) is False


def test_l_unique_action_qui_doit_aboutir_est_l_action_de_l_etape():
    moteur = SimpleNamespace(_fiche=None)
    actions = frozenset({"voir_produit", OUTIL, "infos_pratiques"})
    assert action_de_l_etape(actions, False, moteur) is None  # avant : rien d'inscrit, rien d'armé
    for nom, action in (("voir_produit", "infos_pratiques"), (OUTIL, OUTIL), ("infos_pratiques", "infos_pratiques")):
        fin.inscrire_l_outil(moteur, nom, _outil(action))
    assert action_de_l_etape(actions, False, moteur) == OUTIL
    fin.inscrire_l_outil(moteur, "infos_pratiques", _outil("infos_pratiques", {fin.CLE_DE_L_OUTIL: True}))
    assert action_de_l_etape(actions, False, moteur) is None  # deux : on ne choisit pas pour l'étape


# -- 3. la garde de fin ---------------------------------------------------------------------------------------


def test_2597_la_fin_est_refusee_une_fois_en_nommant_l_outil_puis_passe():
    moteur, _, _ = _banc()
    refus = fin.verifier_la_fin(moteur)
    assert refus is not None and refus["status"] == fin.STATUT_REFUS and refus["outils_a_appeler"] == [OUTIL], refus
    assert fin.verifier_la_fin(moteur) is None  # G2 : la personne qui renonce peut partir


def test_la_fin_passe_sans_action_declaree_ou_quand_l_outil_a_ete_appele():
    moteur, _, _ = _banc(attendue=None)
    assert fin.verifier_la_fin(moteur) is None
    moteur, _, _ = _banc()
    noter_l_action(moteur, OUTIL, {}, {"statut": "INCOMPLETE", "manque": "nom"}, {})
    # appelé (pas abouti) : c'est la garde des actions non abouties qui décide, pas l'action jamais appelée
    assert fin.action_attendue_jamais_appelee(moteur) is None
