"""[.mark] builder partie 3, L3e sous-lot 3 : le garde-fou URGENCE. Réflexe R1 : il traverse la VRAIE route (``preparer_la_requete`` du vrai moteur,
la même au téléphone, dans le widget, en campagne et au clavier), pas une doublure.

| Test | La garantie |
|---|---|
| doit se déclencher | une phrase de détresse ou d'urgence médicale : la phrase du catalogue est dite avec le numéro, le déclenchement est noté, le modèle reçoit une notice |
| ne doit pas se déclencher | des phrases banales (dont des tournures qui y ressemblent) : rien n'est dit, rien n'est noté, la requête passe telle quelle |
| éteint par défaut | sans l'interrupteur de Sécurité, même une détresse ne déclenche rien ; aucun processeur n'est posé autour du cerveau |
| une fois par appel | la phrase n'est dite qu'une fois, le déclenchement est noté à chaque fois |
| réglages | numéro et mots de l'agent ; la phrase éteinte au catalogue : le modèle donne lui-même le numéro |
| aucun modèle | le garde-fou ne lit que des mots (aucun appel de modèle) |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext

from api.services.phrases.catalogue import MOTIFS, URGENCE_VITALE
from api.services.pipecat import avant_la_requete
from api.services.pipecat.speech_playback import PlaybackOutcome
from api.services.securite import marques, urgence
from api.services.workflow.pipecat_engine import PipecatEngine

DOIT_DECLENCHER = [
    "Au secours, mon mari ne respire plus !",
    "Je crois que ma mère fait un malaise, elle est tombée.",
    "Il a perdu connaissance dans la cuisine",
    "J'ai une douleur dans la poitrine, je pense à une crise cardiaque",
    "Elle saigne beaucoup, il y a du sang partout",
    "Je n'arrive plus à respirer",
    "Je veux mourir, je ne tiens plus",
    "Il faut appeler le SAMU tout de suite",
    "Please call an ambulance, he is not breathing",
    "My father had a stroke",
]
NE_DOIT_PAS_DECLENCHER = [
    "Bonjour, je voudrais prendre rendez-vous mardi à quinze heures pour un contrôle de ma chaudière.",
    "Mon téléphone ne répond plus depuis ce matin, pouvez-vous regarder ?",
    "Je vais mourir de rire avec votre histoire de devis",
    "J'ai bien reçu votre mail, merci. C'est urgent pour vendredi quand même.",
    "Mon voisin a un chien qui aboie, ça me stresse un peu",
    "Je voudrais un devis pour un ravalement de façade",
    "Est-ce que vous pouvez m'aider à changer mon rendez-vous ?",
    "Can you help me with my invoice?",
    "",
]


@pytest.mark.parametrize("phrase", DOIT_DECLENCHER)
def test_une_detresse_ou_une_urgence_medicale_est_reconnue(phrase):
    assert urgence.detecter(phrase) is not None, phrase


@pytest.mark.parametrize("phrase", NE_DOIT_PAS_DECLENCHER)
def test_une_phrase_banale_ne_declenche_rien(phrase):
    assert urgence.detecter(phrase) is None, phrase


def test_les_mots_de_l_agent_s_ajoutent_et_se_normalisent():
    assert urgence.detecter("C'est la CHÈVRE qui s'est échappée", ["chèvre"]) == "mot_de_l_agent"
    assert urgence.detecter("rien de spécial", ["chèvre"]) is None


def _moteur(workflow, reglages):
    moteur = PipecatEngine(workflow=workflow, llm=SimpleNamespace(queue_frame=AsyncMock()), context=LLMContext(), call_context_vars={})
    moteur.call_worker = SimpleNamespace(queue_frame=AsyncMock())
    moteur.active_agent.reglages = reglages
    dites: list[str] = []

    async def parole(texte=None, **options):
        dites.append(texte)
        return SimpleNamespace(outcome=PlaybackOutcome.PLAYED, text=texte, wait=AsyncMock(), done=True)

    moteur.queue_speech = parole
    return moteur, dites


def _tour(*paroles):
    messages = []
    for i, p in enumerate(paroles):
        messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": p})
    return LLMContext(messages=messages)


async def _requete(moteur, contexte):
    return await avant_la_requete.preparer_la_requete(moteur, SimpleNamespace(), LLMContextFrame(context=contexte))


def _securite(**garde):
    return {"securite_conversation": {"garde_urgence": {"actif": True, **garde}}}


@pytest.mark.asyncio
async def test_une_detresse_dit_la_phrase_avec_le_numero_note_le_declenchement_et_previent_le_modele(simple_workflow):
    moteur, dites = _moteur(simple_workflow, _securite())
    historique = _tour("Au secours, mon mari ne respire plus !")
    trame = await _requete(moteur, historique)
    assert len(dites) == 1 and "112" in dites[0] and "{{" not in dites[0]
    assert dites[0] == MOTIFS[URGENCE_VITALE].variantes_defaut[0].replace("{{numero}}", "112")
    (marque,) = moteur._gathered_context[marques.CLE]
    assert marque["couche"] == "urgence" and marque["nom"] == "urgence" and marque["detail"] == "appel_a_l_aide"
    envoye = [m["content"] for m in trame.context.get_messages()]
    assert any(c.startswith("[Garde-fou urgence]") and "ne répète pas" in c for c in envoye)
    assert len(historique.get_messages()) == 1  # l'historique partagé n'est pas touché


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase", NE_DOIT_PAS_DECLENCHER[:4])
async def test_une_phrase_banale_passe_telle_quelle_sans_rien_dire_ni_noter(simple_workflow, phrase):
    moteur, dites = _moteur(simple_workflow, _securite())
    contexte = _tour(phrase)
    trame = await _requete(moteur, contexte)
    assert dites == [] and marques.CLE not in moteur._gathered_context
    assert trame.context is contexte


@pytest.mark.asyncio
async def test_eteint_par_defaut_meme_une_detresse_ne_declenche_rien_et_aucun_processeur_n_est_pose(simple_workflow):
    moteur, dites = _moteur(simple_workflow, None)
    await _requete(moteur, _tour("Au secours, il ne respire plus"))
    assert dites == [] and marques.CLE not in moteur._gathered_context
    moteur.active_agent.llm = SimpleNamespace()
    assert avant_la_requete.autour_du_cerveau(moteur, moteur.active_agent) == (None, None)


@pytest.mark.asyncio
async def test_allume_le_garde_fou_est_pose_autour_du_cerveau_seul(simple_workflow):
    moteur, _ = _moteur(simple_workflow, _securite())
    moteur.active_agent.llm = SimpleNamespace()
    avant, apres = avant_la_requete.autour_du_cerveau(moteur, moteur.active_agent)
    assert avant is not None and apres is not None


@pytest.mark.asyncio
async def test_la_phrase_n_est_dite_qu_une_fois_par_appel_mais_chaque_declenchement_est_note(simple_workflow):
    moteur, dites = _moteur(simple_workflow, _securite())
    await _requete(moteur, _tour("Au secours !"))
    suite = await _requete(moteur, _tour("Au secours !", "Je suis là, que se passe-t-il ?", "Il ne respire toujours pas, il est inconscient"))
    assert len(dites) == 1
    assert len(moteur._gathered_context[marques.CLE]) == 2
    assert any("ne répète pas" in m["content"] for m in suite.context.get_messages())


@pytest.mark.asyncio
async def test_le_numero_et_les_mots_sont_ceux_de_l_agent(simple_workflow):
    moteur, dites = _moteur(simple_workflow, _securite(numero="15", mots_en_plus=["chèvre"]))
    await _requete(moteur, _tour("La chèvre est coincée dans la clôture"))
    assert len(dites) == 1 and "15" in dites[0] and "112" not in dites[0]


@pytest.mark.asyncio
async def test_la_phrase_eteinte_au_catalogue_le_modele_donne_lui_meme_le_numero(simple_workflow):
    regle = {"motif": URGENCE_VITALE, "portee": "agent", "variantes": ["Appelez le {{numero}}."], "active": False}
    moteur, dites = _moteur(simple_workflow, {**_securite(), "phrases_regles": [regle]})
    trame = await _requete(moteur, _tour("Au secours !"))
    assert dites == []
    assert any("Dis d'abord" in m["content"] and "112" in m["content"] for m in trame.context.get_messages())
    assert len(moteur._gathered_context[marques.CLE]) == 1  # détecté et noté, même sans phrase


@pytest.mark.asyncio
async def test_une_requete_qui_ne_repond_pas_a_la_personne_n_est_pas_lue(simple_workflow):
    moteur, dites = _moteur(simple_workflow, _securite())
    contexte = LLMContext(messages=[{"role": "user", "content": "Au secours !"}, {"role": "assistant", "content": "Je regarde."}])
    await _requete(moteur, contexte)
    assert dites == []


def test_le_garde_fou_ne_lit_que_des_mots_aucun_appel_de_modele():
    source = open(urgence.__file__, encoding="utf8").read().lower()
    for interdit in ("interroger", "openai", "anthropic", "mistral", "llm.run", "chat_completion"):
        assert interdit not in source


# --- les scénarios de test : l'un EXIGE le déclenchement, l'autre EXIGE le silence ----------------------------------------------


@pytest.mark.asyncio
async def test_le_critere_exige_le_declenchement_sur_une_detresse_et_le_silence_sur_un_appel_banal(simple_workflow):
    from api.services.builder.tests_agent import verdict

    detresse, _ = _moteur(simple_workflow, _securite())
    await _requete(detresse, _tour("Au secours, mon mari ne respire plus !"))
    obs = verdict.observation_depuis_un_run([], detresse._gathered_context)
    assert verdict.evaluer_un({"type": "urgence_declenchee"}, obs).reussi is True
    assert verdict.evaluer_un({"type": "urgence_silencieuse"}, obs).reussi is False

    banal, _ = _moteur(simple_workflow, _securite())
    await _requete(banal, _tour("Bonjour, un rendez-vous mardi à quinze heures. C'est urgent pour vendredi, mais sans danger."))
    obs = verdict.observation_depuis_un_run([], banal._gathered_context)
    assert verdict.evaluer_un({"type": "urgence_declenchee"}, obs).reussi is False
    assert verdict.evaluer_un({"type": "urgence_silencieuse"}, obs).reussi is True


@pytest.mark.asyncio
async def test_garde_fou_eteint_le_scenario_qui_exige_le_declenchement_echoue(simple_workflow):
    from api.services.builder.tests_agent import verdict

    eteint, _ = _moteur(simple_workflow, None)
    await _requete(eteint, _tour("Au secours, mon mari ne respire plus !"))
    resultat = verdict.evaluer_un({"type": "urgence_declenchee"}, verdict.observation_depuis_un_run([], eteint._gathered_context))
    assert resultat.reussi is False and "Security theme" in (resultat.raison or "")


def test_les_deux_scenarios_de_la_bibliotheque_portent_le_bon_critere():
    import json
    from pathlib import Path

    dossier = Path(urgence.__file__).resolve().parents[1] / "builder" / "versement" / "contenu" / "scenarios-test"
    exige = json.loads((dossier / "urgence-doit-se-declencher.json").read_text(encoding="utf-8"))
    muet = json.loads((dossier / "urgence-appel-banal-muet.json").read_text(encoding="utf-8"))
    assert exige["contenu"]["criteres"] == [{"type": "urgence_declenchee"}]
    assert muet["contenu"]["criteres"] == [{"type": "urgence_silencieuse"}]


# --- le réglage dans Sécurité ----------------------------------------------------------------------------------------------------


def test_le_reglage_est_eteint_par_defaut_a_ses_bornes_et_compte_comme_une_couche_de_securite():
    from pydantic import ValidationError

    from api.schemas.securite_conversation import SecuriteConversation
    from api.services.publication.controles import _garde_fous

    defaut = SecuriteConversation()
    assert (defaut.garde_urgence.actif, defaut.garde_urgence.numero, defaut.garde_urgence.mots_en_plus) == (False, "112", [])
    assert SecuriteConversation.model_validate({"garde_urgence": {"actif": True, "numero": "15", "mots_en_plus": ["chèvre"]}}).garde_urgence.numero == "15"
    for faux in ({"numero": "samu"}, {"numero": ""}, {"mots_en_plus": ["a"]}, {"mots_en_plus": ["xx"] * 21}, {"inconnu": 1}):
        with pytest.raises(ValidationError):
            SecuriteConversation.model_validate({"garde_urgence": faux})
    assert _garde_fous({"securite_conversation": {"garde_urgence": {"actif": True}}}) == []
    assert _garde_fous({"securite_conversation": {"garde_urgence": {"actif": False}}}) != []
