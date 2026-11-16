"""[.mark] SA-38 (M89, appel 2574, « Tester au clavier », Gemma 4) : un texte dit par le code n'est dit qu'UNE fois par tour.

La cause, prouvée sur le contexte de l'appel 2574 (``checkpoint.messages``) : le SECOND exemplaire vient du MODÈLE, jamais du code.

- tour « Zéro six, douze… » : ``finaliser`` (1) rend « Je note le zéro six, douze, douze, douze, douze. Vous réglez comment ? », dit par
  le code (message 28) ; le modèle rappelle ``finaliser`` (2), dont le résultat ne porte plus le numéro (SA-34 a bien retenu
  ``numero_dit``) mais repropose la question (``suggestion`` « Vous réglez comment ? », sans « dit par le code ») ; le modèle répond
  alors « Je note le zéro six, douze, douze, douze, douze. Comment souhaitez-vous régler votre commande ? » (message 31) : il recopie la
  réplique du code qu'il voit dans son historique ;
- tour « Par carte. » : la relecture est dite par le code (message 35), la confirmation dans le même tour est refusée (``suggestion``
  vide, SA-33), et le modèle recopie la relecture entière (message 38) ; la relance d'une réponse coupée n'y est pour rien (le dernier
  résultat ne propose aucun texte : ``texte_du_dernier_outil`` rend ``None``) ;
- tour « Ça marche. » : UN seul appel, « Votre commande est enregistrée … » dit par le code (42), puis le modèle le redit avant
  « Puis-je faire autre chose pour vous ? » (43) malgré la consigne « déjà dit, ne le répète pas ».

Le mécanisme commun, sans un mot de métier :

| Test | Ce qu'il prouve |
|---|---|
| réplique recopiée (×3) | le début de la réplique du modèle qui redit une phrase du code dans ce tour en est retiré ; le reste passe |
| voix | au téléphone, le texte du code n'est pas encore dans le contexte : le registre du moteur suffit |
| sans phrase du code | le flux passe octet pour octet |
| réplique différente | une réplique qui commence comme le code mais diverge passe entière |
| outil rappelé | un résultat dont tout le texte a déjà été dit par le code ne le repropose pas et n'est pas redit à la voix |
| tour suivant | au tour suivant de la personne, le même texte se dit de nouveau |
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from api.services.outils_mark.pour_la_voix import avec_restitution, dire_par_le_code
from api.services.pipecat.reponse_avalee import RepriseSansFluxMixin
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR
from api.tests.mark.test_reponse_avalee import _Base, _Contexte, _morceau

CONSIGNE = (
    "Ce texte a déjà été dit à la personne, mot pour mot : ne le répète pas et n'y ajoute rien. Attends sa réponse. "
    "Si elle conteste ou corrige, ne le défends pas : corrige avec l'outil, puis rappelle-le."
)
NUMERO = "Je note le zéro six, douze, douze, douze, douze. Vous réglez comment ?"
RELECTURE = (
    "Je vous relis : deux Margherita Normale, un tiramisu avec Pistache, une Regina Mega et un Orangina, à emporter, pour mardi "
    "dix-sept novembre à vingt heures, avec deux pizzas, une boisson offerte. Cela fait quarante-sept euros soixante. Vous réglez "
    "quarante-sept euros soixante par carte. C'est bon ?"
)
ENREGISTREE = "Votre commande est enregistrée pour mardi dix-sept novembre à vingt heures."


def _appel(i: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": i, "type": "function", "function": {"name": "finaliser", "arguments": json.dumps(arguments)}}],
    }


def _resultat(i: str, resultat: dict) -> dict:
    return {"role": "tool", "tool_call_id": i, "content": json.dumps(resultat, ensure_ascii=False)}


DIT = {"restitution": "dit_par_le_code", "consigne_de_restitution": CONSIGNE, "deja_dit_par_le_code": True}

# Les messages de l'appel 2574 (checkpoint), au moment où le modèle produit sa réplique fautive.
TOUR_NUMERO = [
    {"role": "user", "content": "06 12 12 12 12."},
    _appel("a", {"telephone": "0612121212"}),
    _resultat("a", {"statut": "INCOMPLETE", "faits": {"numero_retenu_dit": "zéro six, douze, douze, douze, douze"}, "manque": "paiement", **DIT}),
    {"role": "assistant", "content": NUMERO},
    _appel("b", {"telephone": "0612121212"}),
    _resultat("b", {"statut": "INCOMPLETE", "faits": {}, "suggestion": "Vous réglez comment ?", "manque": "paiement"}),
]
TOUR_RELECTURE = [
    {"role": "user", "content": "Par carte."},
    _appel("c", {"moyen": "carte"}),
    _resultat("c", {"statut": "INCOMPLETE", "faits": {"a_confirmer": True}, "manque": "relecture", **DIT}),
    {"role": "assistant", "content": RELECTURE},
    _appel("d", {"confirmer": True}),
    _resultat("d", {"statut": "INCOMPLETE", "faits": {"en_attente_de_la_reponse": True}, "suggestion": "", "manque": "reponse_a_la_relecture"}),
]
TOUR_ENREGISTREE = [
    {"role": "user", "content": "Ça marche."},
    _appel("e", {"confirmer": True}),
    _resultat("e", {"statut": "ENREGISTREE", "faits": {"numero_court": "6"}, **DIT}),
    {"role": "assistant", "content": ENREGISTREE},
]


class _Service(RepriseSansFluxMixin, _Base):
    pass


def _en_morceaux(texte: str, taille: int = 7) -> list[Any]:
    """La réplique du modèle comme un flux : de petits morceaux, puis la fin et le compte de jetons."""
    return [_morceau(texte[i : i + taille]) for i in range(0, len(texte), taille)] + [_morceau(fin="stop"), _morceau(jetons=40)]


async def _dit(messages: list[dict], replique: str, service: _Service | None = None) -> tuple[str, list[Any]]:
    service = service or _Service(_en_morceaux(replique))
    morceaux = [m async for m in await service.get_chat_completions(_Contexte(messages))]
    return "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices), morceaux


# --- La réplique du modèle -------------------------------------------------------------------------------------


async def test_appel_2574_le_numero_recopie_par_le_modele_est_retire_la_question_reste():
    texte, morceaux = await _dit(TOUR_NUMERO, NUMERO.split(" Vous")[0] + " Comment souhaitez-vous régler votre commande ?")
    assert texte == "Comment souhaitez-vous régler votre commande ?"
    assert [m.choices[0].finish_reason for m in morceaux if m.choices][-1] == "stop"
    assert morceaux[-1].usage.completion_tokens == 40  # la fin et le compte passent


async def test_appel_2574_la_relecture_recopiee_entiere_n_est_pas_redite():
    texte, morceaux = await _dit(TOUR_RELECTURE, RELECTURE)
    assert texte == ""
    assert [m.choices[0].finish_reason for m in morceaux if m.choices][-1] == "stop"


async def test_appel_2574_l_enregistrement_redit_est_retire_la_suite_reste():
    texte, _ = await _dit(TOUR_ENREGISTREE, ENREGISTREE + " Puis-je faire autre chose pour vous ?")
    assert texte == "Puis-je faire autre chose pour vous ?"


async def test_au_telephone_le_registre_du_moteur_suffit():
    """Au téléphone, le texte du code entre dans le contexte quand la voix le dit : le cerveau lit le registre du moteur."""
    moteur = _Moteur(tour=4)
    service = _Service(_en_morceaux(ENREGISTREE + " Puis-je faire autre chose pour vous ?"))
    moteur.active_agent = SimpleNamespace(llm=service)
    await dire_par_le_code(moteur, avec_restitution({"statut": "ENREGISTREE", "suggestion": ENREGISTREE}, {"restitution": "dit_par_le_code"}))
    sans_le_texte = [m for m in TOUR_ENREGISTREE if m.get("role") != "assistant" or m.get("tool_calls")]
    texte, _ = await _dit(sans_le_texte, "", service)
    assert texte == "Puis-je faire autre chose pour vous ?"
    moteur._gathered_context[CLE_TOUR] = 5  # la personne a reparlé : plus rien n'est retenu
    service._morceaux = _en_morceaux(ENREGISTREE)
    texte, _ = await _dit([{"role": "user", "content": "Pardon ?"}], "", service)
    assert texte == ENREGISTREE


async def test_sans_phrase_du_code_dans_le_tour_le_flux_passe_octet_pour_octet():
    flux = _en_morceaux(ENREGISTREE + " Autre chose ?")
    _, morceaux = await _dit([*TOUR_ENREGISTREE, {"role": "user", "content": "Non."}], "", _Service(flux))
    assert morceaux == flux


async def test_une_replique_qui_diverge_passe_entiere_et_telle_quelle():
    replique = "Votre commande est bien notée, à demain. Bonne soirée !"
    flux = _en_morceaux(replique)
    texte, morceaux = await _dit(TOUR_ENREGISTREE, "", _Service(flux))
    assert texte == replique and morceaux == flux


async def test_un_appel_d_outil_sans_texte_passe_aussitot():
    from openai.types.chat.chat_completion_chunk import (
        ChatCompletionChunk,
        Choice,
        ChoiceDelta,
        ChoiceDeltaToolCall,
        ChoiceDeltaToolCallFunction,
    )

    morceau = ChatCompletionChunk(
        id="c", created=0, model="m", object="chat.completion.chunk",
        choices=[Choice(index=0, delta=ChoiceDelta(tool_calls=[ChoiceDeltaToolCall(index=0, id="t", type="function", function=ChoiceDeltaToolCallFunction(name="finaliser", arguments="{}"))]), finish_reason=None)],
    )
    flux = [morceau, _morceau(fin="tool_calls")]
    _, morceaux = await _dit(TOUR_ENREGISTREE, "", _Service(flux))
    assert morceaux == flux


# --- Les résultats d'outil -------------------------------------------------------------------------------------


class _Lecture:
    outcome = SimpleNamespace(name="PENDING")


class _Moteur:
    def __init__(self, tour: int = 3) -> None:
        self.dites: list[str] = []
        self._gathered_context: dict[str, Any] = {CLE_TOUR: tour}
        self.phrases = SimpleNamespace(coupures=SimpleNamespace(noter=lambda *a, **k: None))

    async def queue_speech(self, text=None, **_options):
        self.dites.append(text)
        return _Lecture()


def _dit_par_le_code(resultat: dict) -> dict:
    return avec_restitution(resultat, {"restitution": "dit_par_le_code"})


async def test_l_outil_rappele_dans_le_tour_ne_repropose_pas_ce_que_le_code_a_dit():
    moteur = _Moteur()
    await dire_par_le_code(moteur, _dit_par_le_code({"statut": "INCOMPLETE", "suggestion": NUMERO}))
    # Le second appel de l'appel 2574 : la question seule, sans « dit par le code ».
    second = await dire_par_le_code(moteur, {"statut": "INCOMPLETE", "faits": {}, "suggestion": "Vous réglez comment ?", "manque": "paiement"})
    assert "suggestion" not in second and second["deja_dit_par_le_code"] is True
    assert "ne le répète pas" in second["consigne_de_restitution"]
    assert second["faits"] == {} and second["manque"] == "paiement"
    assert moteur.dites == [NUMERO]


async def test_le_meme_texte_dit_par_le_code_rendu_deux_fois_n_est_dit_qu_une_fois():
    moteur = _Moteur()
    for _ in range(2):
        sortie = await dire_par_le_code(moteur, _dit_par_le_code({"statut": "INCOMPLETE", "suggestion": RELECTURE}))
        assert "texte_a_dire" not in sortie and sortie["deja_dit_par_le_code"] is True
    assert moteur.dites == [RELECTURE]


async def test_seules_les_phrases_neuves_partent_a_la_voix():
    moteur = _Moteur()
    await dire_par_le_code(moteur, _dit_par_le_code({"statut": "INCOMPLETE", "suggestion": NUMERO}))
    autre = "Je note le zéro six, treize, treize, treize, treize. Vous réglez comment ?"
    await dire_par_le_code(moteur, _dit_par_le_code({"statut": "INCOMPLETE", "suggestion": autre}))
    assert moteur.dites == [NUMERO, "Je note le zéro six, treize, treize, treize, treize."]


async def test_au_tour_suivant_le_meme_texte_se_dit_de_nouveau():
    moteur = _Moteur()
    await dire_par_le_code(moteur, _dit_par_le_code({"statut": "INCOMPLETE", "suggestion": RELECTURE}))
    moteur._gathered_context[CLE_TOUR] += 1
    await dire_par_le_code(moteur, _dit_par_le_code({"statut": "INCOMPLETE", "suggestion": RELECTURE}))
    assert moteur.dites == [RELECTURE, RELECTURE]


async def test_sans_compteur_de_tours_rien_n_est_retenu():
    moteur = _Moteur()
    moteur._gathered_context = {}
    for _ in range(2):
        await dire_par_le_code(moteur, _dit_par_le_code({"statut": "INCOMPLETE", "suggestion": RELECTURE}))
    assert moteur.dites == [RELECTURE, RELECTURE]  # le comportement d'avant
