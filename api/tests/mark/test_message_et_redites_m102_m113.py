"""[.mark] SA-47, lot 3 (appels 2588 et 2594 : démarcheur, contrôle d'hygiène) : le message d'une personne extérieure, et trois défauts vus avec.

- M102 : ``laisser_un_message`` n'avait que ``objet`` et ``urgence`` : sans numéro affiché, la demande partait sans numéro ; ni nom, ni prénom, ni
  organisme. L'outil prend maintenant le message tel que dit, le prénom et le nom, l'organisme, un numéro ; UN manque à la fois ; le numéro dicté est
  relu par le code une fois, celui qui s'affiche est gardé sans relecture ; le message laissé pose l'issue réglée sur l'outil (réservée).
- M113 : l'outil appelé AVEC ``objet`` rendait ``{"statut": "incomplet", "manque": ["objet message"]}`` : la garde de l'étape (relance de l'action,
  champ ``objet_message`` de la fiche) n'exige plus ce que l'appel de l'outil donne.
- M112 : « Je lui laisse un message pour qu'il vous rappelle » après ce refus n'était pas retenu : la prise au présent ne comptait pas, et le résultat
  de ``signaler_un_probleme`` (« Noté. Ne dis rien… ») cachait le « pas fait ».
- M111 : « Je comprends que vous souhaitez joindre le gérant… » dit deux fois : la réplique du modèle déjà dite dans le tour (avant un outil) se
  redisait après le résultat.

| Test | Ce qu'il prouve |
|---|---|
| un manque à la fois | objet, puis nom et prénom (le manquant seul), puis le numéro seulement s'il ne s'affiche pas ; ce qui est dit est gardé |
| numéro | dicté : relu par le code une fois (dit par le code) ; affiché : gardé sans relecture ; un autre donné : relu ; invalide : redemandé |
| demande écrite | objet tel que dit, prénom, nom, organisme, numéro ; le résumé de l'équipe dit qui appelle |
| issue | posée depuis le réglage de l'outil, réservée au classement ; sans réglage, rien |
| garde (M113) | un champ donné par l'appel de l'outil n'est plus attendu ; un champ que rien ne donne l'est toujours |
| vérité (M112) | la prise au présent est retenue quand l'outil n'a rien fait, même suivie d'un signalement ; rien n'est retenu quand l'outil a fait |
| redite (M111) | une phrase déjà dite par le modèle dans le tour ne se redit pas |
"""

from __future__ import annotations

import pytest
import json
from types import SimpleNamespace

from api.services.apres_appel.rappels import CLE_RAPPEL, resume_du_rappel
from api.services.mots_dits import numero_en_lettres
from api.services.pipecat.reponse_avalee import phrases_dites_par_le_code
from api.services.service_client import action as service
from api.services.workflow.enveloppe_des_actions import (
    envelopper_l_action,
    garde_du_noeud,
)
from api.services.workflow.issue_reservee import codes_reserves
from api.services.workflow.signaler_un_probleme import (
    RESULTAT as RESULTAT_DU_SIGNALEMENT,
)
from api.services.workflow.verite_des_actions import affirmation_sans_outil_fait
from api.tests.mark.test_champs_de_l_etape import _moteur

AFFICHE = "+33612345678"


def _ctx(numero: str | None = AFFICHE, **reglages):
    return SimpleNamespace(fiche={}, appel={"caller_number": numero} if numero else {}, reglages=reglages, organization_id=None, run_id=None)


async def _message(ctx, **arguments):
    return await service.laisser_un_message(arguments, ctx)


# --------------------------------------------------------------------------- #
# M102 : le message
# --------------------------------------------------------------------------- #


async def test_m102_un_manque_a_la_fois_et_ce_qui_est_dit_est_garde():
    ctx = _ctx()
    r = await _message(ctx)
    assert (r["statut"], r["manque"]) == ("INCOMPLETE", "objet")
    objet = "Le contrôle d'hygiène de la semaine prochaine, rappeler le gérant."
    r = await _message(ctx, objet=objet, organisme="DDPP")
    assert r["manque"] == "nom" and "prénom" in r["suggestion"] and CLE_RAPPEL not in ctx.fiche
    r = await _message(ctx, prenom="Marie")
    assert r["manque"] == "nom" and r["suggestion"] == "Et votre nom ?"
    r = await _message(ctx, nom="Leroy")  # le numéro s'affiche : jamais demandé, jamais relu
    assert r["statut"] == "OK" and "numero_retenu_dit" not in r["faits"] and "_restitution" not in r
    (entree,) = ctx.fiche[CLE_RAPPEL]
    assert (entree["objet"], entree["prenom"], entree["nom"], entree["organisme"], entree["numero"]) == (objet, "Marie", "Leroy", "DDPP", AFFICHE)
    assert "de : Marie Leroy (DDPP)" in resume_du_rappel(entree) and AFFICHE in resume_du_rappel(entree)


async def test_m102_sans_numero_affiche_le_numero_est_demande_puis_relu_une_fois_par_le_code():
    ctx = _ctx(None)
    r = await _message(ctx, objet="Un devis pour vos menus", prenom="Paul", nom="Martin", organisme="Société Durand")
    assert (r["statut"], r["manque"]) == ("INCOMPLETE", "telephone")
    assert (await _message(ctx, telephone="zéro six douze"))["statut"] == "ARGUMENT_INVALIDE"
    r = await _message(ctx, telephone="06 10 20 30 40")
    dit = numero_en_lettres("+33610203040")
    assert r["statut"] == "OK" and r["suggestion"].startswith(f"Je note le {dit}.") and r["_restitution"] == "dit_par_le_code"
    assert ctx.fiche[CLE_RAPPEL][0]["numero"] == "+33610203040"
    r = await _message(ctx, telephone="0610203040")  # le même numéro redonné : pas relu deux fois
    assert r["statut"] == "OK" and "Je note le" not in r["suggestion"]


async def test_m102_un_autre_numero_que_celui_affiche_est_relu():
    ctx = _ctx()
    r = await _message(ctx, objet="Rappeler sur mon portable", prenom="Marie", nom="Leroy", telephone="0698765432")
    assert r["statut"] == "OK" and r["faits"]["numero_retenu_dit"] == numero_en_lettres("+33698765432")
    assert ctx.fiche[CLE_RAPPEL][0]["numero"] == "+33698765432"


async def test_m102_le_message_laisse_pose_l_issue_reglee_et_reservee():
    ctx = _ctx(call_disposition="message_transmis")
    await _message(ctx, objet="Démarchage", prenom="Luc", nom="Petit")
    assert ctx.fiche["call_disposition"] == "message_transmis"
    sans = _ctx()
    await _message(sans, objet="Démarchage", prenom="Luc", nom="Petit")
    assert "call_disposition" not in sans.fiche
    incomplet = _ctx(call_disposition="message_transmis")
    await _message(incomplet, objet="Démarchage")
    assert "call_disposition" not in incomplet.fiche  # rien n'est laissé : aucune issue
    outil = SimpleNamespace(
        category="integration",
        definition={"config": {"connecteur": "service", "action": "laisser_un_message", "reglages": {"call_disposition": "Message_Transmis"}}},
    )
    assert codes_reserves([outil]) == {"message_transmis"}


# test_m102_le_connecteur_declare_les_parametres_facultatifs : supprimé au lot 6 (D49), la fiche du service a deux cases (``objet``, ``urgent``), prénom et nom reviennent au greffier ; sens repris par partie_1/test_l06_parole.py::test_service_message_une_fois_issue_et_mesure


# --------------------------------------------------------------------------- #
# M113 : la garde de l'étape et les arguments de l'outil
# --------------------------------------------------------------------------- #

CHAMPS_MESSAGE = ("objet_message", "nom")


def _garde_message(fiche):
    from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche

    reglages = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True, "fiche_mode_de_note": "greffier", "fiche_deja_connu": True,
            "fiche_champs": [{"nom": "objet_message", "type": "string", "origine": "deduit"}, {"nom": "nom", "type": "string", "origine": "dicte"}],
        }
    )
    return _moteur(fiche, reglages, CHAMPS_MESSAGE)


def test_m113_un_champ_donne_par_l_appel_de_l_outil_n_est_plus_attendu():
    moteur, agent = _garde_message({"nom": "Leroy"})
    assert garde_du_noeud(moteur, agent.current_node) == {"statut": "incomplet", "manque": ["objet message"]}
    assert garde_du_noeud(moteur, agent.current_node, {"objet": "Le contrôle d'hygiène", "urgence": "urgente"}) is None
    assert garde_du_noeud(moteur, agent.current_node, {"objet": "  "}) is not None  # vide : rien n'est donné
    moteur, agent = _garde_message({})
    assert garde_du_noeud(moteur, agent.current_node, {"objet": "x"}) == {"statut": "incomplet", "manque": ["nom"]}


async def test_m113_2594_l_outil_appele_avec_son_objet_s_execute():
    moteur, agent = _garde_message({"nom": "Leroy"})
    executions, rendus = [], []

    async def action(params):
        executions.append(params.arguments)
        await params.result_callback({"statut": "OK"})

    async def rendre(resultat, **_):
        rendus.append(resultat)

    enveloppe = envelopper_l_action(moteur, "laisser_un_message", action, agent)
    await enveloppe(SimpleNamespace(result_callback=rendre, arguments={"objet": "Le contrôle d'hygiène", "urgence": "urgente"}))
    assert executions and rendus[-1] == {"statut": "OK"}


# --------------------------------------------------------------------------- #
# M112 : la vérité des actions
# --------------------------------------------------------------------------- #

REPLIQUE_2594 = "Je lui laisse un message pour qu'il vous rappelle au sujet de ce contrôle prévu la semaine prochaine."


def _tour(*resultats):
    messages = [{"role": "user", "content": "Je souhaite joindre le gérant."}]
    for r in resultats:
        messages.append({"role": "tool", "content": r if isinstance(r, str) else json.dumps(r)})
    return messages


def test_m112_2594_la_prise_au_present_est_retenue_meme_suivie_d_un_signalement():
    messages = _tour({"statut": "incomplet", "manque": ["objet message"]}, json.dumps(RESULTAT_DU_SIGNALEMENT))
    assert affirmation_sans_outil_fait(REPLIQUE_2594, messages) is not None
    for texte in ("Je transmets votre demande au gérant.", "Je vais lui transmettre votre message.", "Je leur transmets votre message."):
        assert affirmation_sans_outil_fait(texte, messages) is not None, texte


def test_m112_rien_n_est_retenu_quand_l_outil_a_fait_ou_pour_une_question():
    assert affirmation_sans_outil_fait(REPLIQUE_2594, _tour({"statut": "OK"})) is None
    assert affirmation_sans_outil_fait(REPLIQUE_2594, _tour()) is None  # aucun outil dans le tour
    assert affirmation_sans_outil_fait("Je lui laisse un message ?", _tour({"statut": "incomplet", "manque": ["objet"]})) is None


# --------------------------------------------------------------------------- #
# M111 : la redite du modèle dans le tour
# --------------------------------------------------------------------------- #


def test_m111_2594_la_phrase_deja_dite_par_le_modele_dans_le_tour_ne_se_redit_pas():
    from api.services.outils_mark.pour_la_voix import empreinte_de_phrase

    deja = "Je comprends que vous souhaitez joindre le gérant concernant le contrôle d'hygiène de la semaine prochaine."
    messages = [
        {"role": "assistant", "content": "Casa bonjour, que puis-je pour vous ?"},
        {"role": "user", "content": "Je souhaite joindre le gérant."},
        {"role": "assistant", "content": deja},
        {"role": "assistant", "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "content": json.dumps({"statut": "incomplet"})},
    ]
    phrases = phrases_dites_par_le_code(SimpleNamespace(), messages)
    assert empreinte_de_phrase(deja) in phrases
    assert empreinte_de_phrase("Casa bonjour, que puis-je pour vous ?") not in phrases  # avant la parole de la personne : un autre tour
