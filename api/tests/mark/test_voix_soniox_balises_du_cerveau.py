"""[.mark] Chantier voix-soniox, lot 5 ter (D29) : le cerveau peut écrire une balise permise sous la voix Soniox.

| Test | Preuve |
|---|---|
| une balise de la liste, écrite par le cerveau, n'est plus retirée (même coupée en morceaux) | lot 5 ter |
| balise hors liste, didascalie, crochet ordinaire : retirés comme avant | zéro perte |
| balises empilées passent toutes ; balise collée à un mot ou en tête de réplique : gardée telle quelle | D-58 |
| liste ``[]``, ElevenLabs, mot à mot, pas de voix : le texte du cerveau est celui d'avant, tout crochet retiré | zéro perte |
| par le cerveau réel (mixin) : la liste vient de la MÊME fonction de résolution que le garde-fou | D-58 |
| de bout en bout : sortie du cerveau, puis file de la voix Soniox, puis transcription, verbatim, fiche sans crochet | D29 |
| le corpus des 3 889 phrases réelles : aucune n'a de balise permise, zéro changement | zéro perte |
| le branchement : les deux endroits où le modèle de conversation est créé posent la liste | R1 |

⛔ Aucun appel à Soniox : ces tests prouvent ce qui part et ce qui est retiré, pas que la voix joue bien une balise.
"""

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from api.services.pipecat.balises_expression import BALISES_PAR_DEFAUT, sans_balises
from api.services.pipecat.texte_du_cerveau import FluxNettoye, TexteDuCerveauMixin, sans_crochets
from api.tests.mark.test_texte_du_cerveau import _Flux, _dit, _m
from api.tests.mark.test_voix_soniox import _config
from api.tests.mark.test_voix_soniox_estampille_cle_balises import _dit as _dit_voix
from api.tests.mark.test_voix_soniox_estampille_cle_balises import _eleven, _voix_avec

CORPUS = Path(__file__).parent / "donnees" / "phrases-agent.jsonl"
LISTE = tuple(BALISES_PAR_DEFAUT)


async def _lire(morceaux, balises=LISTE):
    return [m async for m in FluxNettoye(_Flux(morceaux), [], False, balises)]


# --------------------------------------------------------------------------- #
# Le filtre
# --------------------------------------------------------------------------- #


async def test_une_balise_permise_passe_meme_coupee_en_morceaux():
    sorties = await _lire([_m(), _m("[wa"), _m("rm] Bon"), _m("jour."), _m(fin="stop")])
    assert _dit(sorties) == "[warm] Bonjour."


async def test_tout_autre_crochet_est_retire_comme_avant():
    assert _dit(await _lire([_m("[fou] Bonjour."), _m(fin="stop")])) == "Bonjour."
    assert _dit(await _lire([_m("*(sourit)* Bonjour."), _m(fin="stop")])) == "Bonjour."
    assert _dit(await _lire([_m("[warm] A [fou] B"), _m(fin="stop")])) == "[warm] A B"
    # Le passage de la fiche et les jetons d'appel ne sont jamais des balises.
    assert _dit(await _lire([_m("[Fiche de l'appel : pour toi seulement] Bonjour."), _m(fin="stop")])) == "Bonjour."


async def test_deux_balises_empilees_passent_toutes_les_deux():
    assert _dit(await _lire([_m("[warm][calm] Bonjour."), _m(fin="stop")])) == "[warm][calm] Bonjour."
    assert _dit(await _lire([_m("[warm] [calm] Bonjour."), _m(fin="stop")])) == "[warm] [calm] Bonjour."


async def test_une_balise_collee_a_un_mot_ou_en_tete_est_gardee_telle_qu_ecrite():
    """D-58 : le code ne reformate jamais ce que le cerveau a écrit (option la plus réversible)."""
    assert _dit(await _lire([_m("Bonjour[pause] merci."), _m(fin="stop")])) == "Bonjour[pause] merci."
    assert _dit(await _lire([_m("[slowly]Bonjour."), _m(fin="stop")])) == "[slowly]Bonjour."
    assert _dit(await _lire([_m("Merci. [pause]"), _m(fin="stop")])) == "Merci. [pause]"


async def test_la_casse_et_les_espaces_de_la_balise_ne_comptent_pas():
    assert _dit(await _lire([_m("[Warm] Bonjour."), _m(fin="stop")])) == "[Warm] Bonjour."
    assert _dit(await _lire([_m("[ warm ] Bonjour."), _m(fin="stop")])) == "[ warm ] Bonjour."


async def test_une_balise_ne_retient_pas_la_voix_jusqu_au_bout():
    """Une balise fermée est rendue tout de suite : le texte qui suit n'attend pas 160 caractères."""
    sorties = await _lire([_m("[warm] Bonjour"), _m(", je vous écoute.")])
    assert [(_dit([s])) for s in sorties] == ["[warm] Bonjour", ", je vous écoute."]


async def test_sans_liste_le_filtre_est_celui_d_avant():
    for balises in ((), None, []):
        assert _dit(await _lire([_m("[warm] Bonjour."), _m(fin="stop")], balises or ())) == "Bonjour."
    assert sans_crochets("[warm] Bonjour") == "Bonjour"
    assert sans_crochets("[warm] Bonjour", ()) == "Bonjour"
    assert sans_crochets("[warm] Bonjour", ["warm"]) == "[warm] Bonjour"


async def test_un_crochet_jamais_ferme_est_rendu_tel_quel_meme_avec_une_liste():
    sorties = await _lire([_m("Le total [environ"), _m(" douze."), _m(fin="stop")])
    assert _dit(sorties) == "Le total [environ douze."


# --------------------------------------------------------------------------- #
# La liste vient de la même fonction que le garde-fou de la voix
# --------------------------------------------------------------------------- #


def test_la_liste_du_cerveau_est_celle_de_l_estampille_et_du_garde_fou():
    from api.services.pipecat.service_factory import balises_du_cerveau

    assert balises_du_cerveau(_config(), None) == tuple(sorted(LISTE))
    assert balises_du_cerveau(_config(), {"tts_balises_permises": ["Calm", "[pause]"]}) == ("calm", "pause")
    # Éteint, mot à mot (voix ou agent), autre voix, pas de voix : aucune.
    assert balises_du_cerveau(_config(), {"tts_balises_permises": []}) == ()
    assert balises_du_cerveau(_config(text_aggregation_mode="token"), None) == ()
    assert balises_du_cerveau(_config(), {"tts_text_aggregation_mode": "token"}) == ()
    assert balises_du_cerveau(_eleven(), None) == ()
    assert balises_du_cerveau(_eleven(), {"tts_balises_permises": ["warm"]}) == ()
    assert balises_du_cerveau(None, None) == ()


async def _cerveau(voix, run_configs, texte):
    """Le cerveau réel (le mixin), le modèle de conversation posé comme le fait l'appel."""
    from api.services.pipecat.service_factory import poser_les_balises_du_cerveau

    class _Base:
        _settings = SimpleNamespace(system_instruction="")

        async def get_chat_completions(self, context):
            return _Flux([_m(texte), _m(fin="stop")])

    class _Service(TexteDuCerveauMixin, _Base):
        pass

    service = poser_les_balises_du_cerveau(_Service(), voix, run_configs)
    sorties = [m async for m in await service.get_chat_completions(SimpleNamespace(tools=None, messages=[]))]
    return _dit(sorties)


async def test_par_le_cerveau_reel_la_balise_permise_passe_sous_soniox_seulement():
    texte = "[warm] Bonjour [fou] monsieur."
    assert await _cerveau(_config(), None, texte) == "[warm] Bonjour monsieur."
    assert await _cerveau(_config(), {"tts_balises_permises": ["calm"]}, texte) == "Bonjour monsieur."
    assert await _cerveau(_config(), {"tts_balises_permises": []}, texte) == "Bonjour monsieur."
    # D-23 : mot à mot, rien ne passe.
    assert await _cerveau(_config(text_aggregation_mode="token"), None, texte) == "Bonjour monsieur."
    # ElevenLabs et pas de voix : comme avant, tout crochet retiré.
    assert await _cerveau(_eleven(), None, texte) == "Bonjour monsieur."
    assert await _cerveau(_eleven(), {"tts_balises_permises": ["warm"]}, texte) == "Bonjour monsieur."
    assert await _cerveau(None, None, texte) == "Bonjour monsieur."


async def test_le_mixin_sans_liste_posee_se_comporte_comme_avant():
    class _Base:
        _settings = SimpleNamespace(system_instruction="")

        async def get_chat_completions(self, context):
            return _Flux([_m("[warm] Bonjour."), _m(fin="stop")])

    class _Service(TexteDuCerveauMixin, _Base):
        pass

    sorties = [m async for m in await _Service().get_chat_completions(SimpleNamespace(tools=None, messages=[]))]
    assert _dit(sorties) == "Bonjour."


def test_le_pendant_responses_recoit_la_liste():
    from api.services.pipecat.responses_llm import FluxNettoyeResponses

    assert FluxNettoyeResponses(_Flux([]), [], False, ("warm",))._nettoye._balises == frozenset({"warm"})
    assert FluxNettoyeResponses(_Flux([]), [], False)._nettoye._balises == frozenset()


# --------------------------------------------------------------------------- #
# De bout en bout : cerveau -> voix Soniox -> ce que les gens lisent
# --------------------------------------------------------------------------- #


async def test_de_bout_en_bout_la_balise_arrive_a_la_voix_et_jamais_a_l_ecran():
    from api.services.pipecat.greffier import message_du_greffier
    from api.services.pipecat.realtime_feedback_events import build_bot_text_event
    from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche

    voix = _config()
    ecrit = await _cerveau(voix, None, "[warm] Bonjour [fou] monsieur Dupont.")
    assert ecrit == "[warm] Bonjour monsieur Dupont."

    # La file de la voix : la balise permise part à Soniox.
    assert await _dit_voix(_voix_avec(voix), ecrit) == "[warm] Bonjour monsieur Dupont."
    # La transcription affichée, le verbatim conservé (même constructeur) et la fiche : aucun crochet.
    assert build_bot_text_event(text=ecrit)["payload"]["text"] == "Bonjour monsieur Dupont."
    assert sans_balises(ecrit) == "Bonjour monsieur Dupont."
    message = message_du_greffier(
        ReglagesFiche(champs=()), {}, [{"role": "assistant", "content": ecrit}, {"role": "user", "content": "Oui."}]
    )
    assert "[warm]" not in message and "Agent : Bonjour monsieur Dupont." in message


# --------------------------------------------------------------------------- #
# Zéro perte et branchement
# --------------------------------------------------------------------------- #


def test_corpus_aucune_phrase_reelle_ne_porte_de_balise_permise_zero_changement():
    with CORPUS.open(encoding="utf-8") as fichier:
        phrases = [json.loads(ligne)["texte"] for ligne in fichier if ligne.strip()]
    assert len(phrases) > 3000
    avec_balise = [p for p in phrases if any(f"[{nom}]" in p.lower() for nom in LISTE)]
    assert avec_balise == [], "le corpus contient une balise permise : le constat « aucune » est faux"
    for phrase in phrases:
        assert sans_crochets(phrase, LISTE) == sans_crochets(phrase), phrase


def test_les_deux_endroits_ou_le_modele_de_conversation_est_cree_posent_la_liste():
    from api.services.pipecat import agent_runtime_factory, run_pipeline

    assert "poser_les_balises_du_cerveau(llm, user_config.tts, run_configs)" in inspect.getsource(run_pipeline)
    source = inspect.getsource(agent_runtime_factory)
    assert "poser_les_balises_du_cerveau(" in source and "self._voix_de_l_appel" in source
