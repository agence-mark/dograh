"""[.mark] The voice says the numbers of the answer in words (plan voix-et-communes, lot 1).

The questions this file answers:

1. Does every postal code of France come out as the short group Evan chose
   (V2), and do the words say back the same five digits?
2. Do the 78 sentences the agent wrote at the bench of 2026-09-17 come out as
   written down, one by one (V3, and Evan's condition: break nothing)?
3. Is the rewriting given to every French voice, and to it alone, and does the
   model's history keep the digits (V1)?

⛔ It does NOT prove the voice pronounces the words well: the ear decides, at
the bench (column « la voix a récité juste ? »).
"""

import json
import re
import statistics
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSAudioRawFrame,
    TTSTextFrame,
)
from pipecat.services.tts_service import TTSService
from pipecat.tests import run_test

from api.services.communes.base import charger_base
from api.services.configuration.registry import (
    CartesiaTTSConfiguration,
    DeepgramTTSConfiguration,
    ElevenlabsTTSConfiguration,
    MistralTTSConfiguration,
)
from api.services.nombres.lecture import _TABLE
from api.services.nombres.voix import code_postal_en_mots, ecrire_pour_la_voix
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.nombres_pour_la_voix import nombres_en_mots
from api.services.pipecat.service_factory import (
    construire_remplacements_de_voix,
    create_tts_service,
)

DONNEES = Path(__file__).parent / "donnees" / "nombres_ecrits_par_agent_2026-09-17.json"
STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)
STT_ANGLAIS = SimpleNamespace(language="en", language_hints=None)


@pytest.fixture(scope="module")
def base():
    return charger_base()


# --------------------------------------------------------------------------- #
# Reading the words back into digits, WITHOUT num2words: a check that used the
# writer to read its own output would prove nothing.
# --------------------------------------------------------------------------- #


def _sans_accents(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _chiffres_de(mots: str) -> str:
    """"zéro zéro quarante-deux" -> "0042"; "soixante mille" -> "60000"."""
    jetons = _sans_accents(mots).replace("-", " ").split()
    zeros = 0
    while jetons and jetons[0] == "zero":
        zeros += 1
        jetons = jetons[1:]
    if not jetons:
        return "0" * zeros
    jetons = ["cent" if j == "cents" else "vingt" if j == "vingts" else j for j in jetons]
    if "mille" in jetons:
        k = jetons.index("mille")
        avant = _TABLE[" ".join(jetons[:k])] if k else 1
        apres = _TABLE[" ".join(jetons[k + 1:])] if k + 1 < len(jetons) else 0
        valeur = avant * 1000 + apres
    else:
        valeur = _TABLE[" ".join(jetons)]
    return "0" * zeros + str(valeur)


# --------------------------------------------------------------------------- #
# 1. Postal codes: V2, case by case, then every code of France
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "code, dit",
    [
        ("60550", "soixante, cinq cent cinquante"),
        ("60100", "soixante, cent"),
        ("60000", "soixante mille"),
        ("75001", "soixante-quinze, zéro zéro un"),
        ("02200", "zéro deux, deux cents"),
        ("20000", "vingt mille"),
        ("20090", "vingt, zéro quatre-vingt-dix"),
        # Not in V2, same rule: the whole number when the end is 000.
        ("80000", "quatre-vingt mille"),
        ("06000", "zéro six mille"),
    ],
)
def test_code_postal_en_groupe_court(code, dit):
    assert code_postal_en_mots(code) == dit


def test_tous_les_codes_postaux_de_france_se_disent_en_groupe_court(base):
    """Every code: after "code postal", the voice gets the short group, no
    digit left, and the words say the same five digits back."""
    erreurs = []
    for code in sorted(base.par_cp):
        dit = ecrire_pour_la_voix(f"Code postal {code}.", base.par_cp)
        mots = dit[len("Code postal "):-1]
        if any(c.isdigit() for c in dit):
            erreurs.append((code, dit))
            continue
        if code.endswith("000"):
            relu = _chiffres_de(mots)
        else:
            departement, _, fin = mots.partition(", ")
            relu = _chiffres_de(departement).zfill(2) + _chiffres_de(fin).zfill(3)
            if len(_chiffres_de(departement)) != 2 or len(_chiffres_de(fin)) != 3:
                erreurs.append((code, dit))
                continue
        if relu.zfill(5) != code:
            erreurs.append((code, dit))
    assert len(base.par_cp) > 6000
    assert erreurs == []


def test_cinq_chiffres_sans_contexte_ni_existence_ne_sont_pas_un_code(base):
    assert "99999" not in base.par_cp
    assert ecrire_pour_la_voix("Il y en a 99999.", base.par_cp) == (
        "Il y en a quatre-vingt-dix-neuf mille neuf cent quatre-vingt-dix-neuf."
    )
    # Without the list: only the context says it is a postal code.
    assert ecrire_pour_la_voix("code postal 60550", None) == "code postal soixante, cinq cent cinquante"
    assert ecrire_pour_la_voix('Pour "60340", pouvez-vous confirmer ?', None) == (
        'Pour "soixante, trois cent quarante", pouvez-vous confirmer ?'
    )
    assert ecrire_pour_la_voix("Vers 60340 ?", None) == "Vers soixante mille trois cent quarante ?"


# --------------------------------------------------------------------------- #
# 2. The 78 sentences of runs 264 and 265, one by one
# --------------------------------------------------------------------------- #


def _phrases():
    return json.loads(DONNEES.read_text(encoding="utf-8"))["phrases"]


def test_le_jeu_du_banc_est_complet():
    phrases = _phrases()
    assert len(phrases) == 78
    assert {p["run"] for p in phrases} == {264, 265}


@pytest.mark.parametrize("phrase", _phrases(), ids=lambda p: p["ecrit"][:50])
def test_phrases_du_banc(phrase, base):
    assert ecrire_pour_la_voix(phrase["ecrit"], base.par_cp) == phrase["dit"]
    assert not re.search(r"\d", phrase["dit"])


def test_les_cas_nommes_par_le_plan(base):
    """Named in the plan (lot 1), so held here as sentences, not only in the data."""
    v = lambda t: ecrire_pour_la_voix(t, base.par_cp)  # noqa: E731
    # ③ before ④: a reference is never a postal code, even an existing one.
    assert "60300" in base.par_cp
    assert v("J'ai retenu : la référence 60300.") == "J'ai retenu : la référence soixante mille trois cents."
    assert v("12 rue de la Gare") == "douze rue de la Gare"
    assert v("Élément 8") == "Élément huit"
    assert v("le numéro de téléphone 06 12 34 56 78") == (
        "le numéro de téléphone zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit"
    )
    assert v("un montant de 15 000 euros") == "un montant de quinze mille euros"
    assert v("la référence 2026-847") == "la référence deux mille vingt-six, tiret, huit cent quarante-sept"


@pytest.mark.parametrize(
    "ecrit, dit",
    [
        # ① phones in every usual shape
        ("0612345678", "zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit"),
        ("06.12.34.56.78", "zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit"),
        ("+33 (0)6 12 34 56 78", "plus trente-trois, six, douze, trente-quatre, cinquante-six, soixante-dix-huit"),
        ("+33612345678", "plus trente-trois, six, douze, trente-quatre, cinquante-six, soixante-dix-huit"),
        # ② amounts
        ("15 000 €", "quinze mille euros"),
        ("1 €", "un euro"),
        ("0,50 €", "cinquante centimes"),
        ("120,50 €", "cent vingt euros cinquante"),
        ("un montant de 15000", "un montant de quinze mille"),
        ("un acompte de 60300", "un acompte de soixante mille trois cents"),
        # ③ references
        ("facture n° 1234 du 12 mars", "facture numéro mille deux cent trente-quatre du douze mars"),
        ("devis FA-2026-001 et la suite", "devis FA, tiret, deux mille vingt-six, tiret, zéro zéro un et la suite"),
        ("le bon de commande 4521", "le bon de commande quatre mille cinq cent vingt et un"),
        # hours, dates, ordinals, percentages, decimals
        ("à 14h30", "à quatorze heures trente"),
        ("à 9h", "à neuf heures"),
        ("à 21h", "à vingt et une heures"),
        ("le 17/09/2026", "le dix-sept septembre deux mille vingt-six"),
        ("le 1/10", "le premier octobre"),
        ("au 1er étage", "au premier étage"),
        ("la 2e porte", "la deuxième porte"),
        ("20 % de remise", "vingt pour cent de remise"),
        ("2,5 mètres", "deux virgule cinq mètres"),
        # letters glued to digits are read apart
        ("en 4G", "en quatre G"),
        # voice tags keep their digits (review of 2026-09-17)
        ('<break time="1s"/> code postal 60550', '<break time="1s"/> code postal soixante, cinq cent cinquante'),
        # no digit: untouched, the very same object
        ("Rien à retenir.", "Rien à retenir."),
    ],
)
def test_les_autres_nombres(ecrit, dit, base):
    assert ecrire_pour_la_voix(ecrit, base.par_cp) == dit


def test_vitesse(base):
    """Plan: median ≤ 0.5 ms, max ≤ 2 ms per sentence (measured locally at
    0.03 ms and 0.14 ms). Asserted with a margin: a CI runner is slower, and
    what this must catch is a pattern that backtracks, not a slow machine."""
    phrases = [p["ecrit"] for p in _phrases()]
    for p in phrases:
        ecrire_pour_la_voix(p, base.par_cp)
    durees = []
    for p in phrases * 5:
        debut = time.perf_counter()
        ecrire_pour_la_voix(p, base.par_cp)
        durees.append((time.perf_counter() - debut) * 1000)
    assert statistics.median(durees) <= 0.5
    assert max(durees) <= 8


def test_une_longue_suite_de_chiffres_ne_bloque_pas(base):
    texte = " ".join(["12"] * 400) + " " + "1" * 300
    debut = time.perf_counter()
    ecrire_pour_la_voix(texte, base.par_cp)
    assert time.perf_counter() - debut < 0.5


# --------------------------------------------------------------------------- #
# 3. Wired to every French voice, and for the voice only
# --------------------------------------------------------------------------- #


def _audio_config():
    return AudioConfig(transport_in_sample_rate=16000, transport_out_sample_rate=24000)


FOURNISSEURS = {
    "cartesia": lambda: CartesiaTTSConfiguration(api_key="cartesia-key"),
    "deepgram": lambda: DeepgramTTSConfiguration(api_key="deepgram-key"),
    "elevenlabs": lambda: ElevenlabsTTSConfiguration(api_key="elevenlabs-key"),
    "mistral": lambda: MistralTTSConfiguration(api_key="mistral-key"),
}


@pytest.mark.parametrize("nom", sorted(FOURNISSEURS))
def test_chaque_voix_francaise_recoit_la_reecriture(nom):
    user_config = SimpleNamespace(tts=FOURNISSEURS[nom](), stt=STT_FRANCAIS)
    service = create_tts_service(user_config, _audio_config(), run_configs={})
    assert [t for _, t in service._text_transforms] == [nombres_en_mots]
    assert nombres_en_mots not in service._text_filters


def test_voxtral_garde_le_texte_du_modele_pour_lhistorique():
    """⚠️ V1 holds only for voices WITHOUT word timestamps (review of 2026-09-17):
    those build the context from the text they were given, not from what they
    said. Our agents speak with Voxtral: this turns red if that ever changes."""
    user_config = SimpleNamespace(tts=FOURNISSEURS["mistral"](), stt=STT_FRANCAIS)
    service = create_tts_service(user_config, _audio_config(), run_configs={})
    assert service._push_text_frames is True


@pytest.mark.parametrize("nom", sorted(FOURNISSEURS))
def test_une_voix_non_francaise_ne_la_recoit_pas(nom):
    user_config = SimpleNamespace(tts=FOURNISSEURS[nom](), stt=STT_ANGLAIS)
    service = create_tts_service(user_config, _audio_config(), run_configs={})
    assert service._text_transforms == []


def test_mot_a_mot_ne_la_recoit_pas():
    """Word by word, "15" and " 000" arrive apart and cannot be read."""
    assert construire_remplacements_de_voix({"tts_text_aggregation_mode": "token"}, True) == []
    assert construire_remplacements_de_voix({"tts_text_aggregation_mode": None}, True) != []


@pytest.mark.asyncio
async def test_apres_les_remplacements_de_lecran():
    transformations = construire_remplacements_de_voix({"tts_replacements": ["SAV:S. A. V."]}, True)
    assert [t for _, t in transformations][1] is nombres_en_mots
    texte = "Le SAV au 03 44 22 10 60"
    for _, transformation in transformations:
        texte = await transformation(texte, "sentence")
    assert texte == "Le S. A. V. au zéro trois, quarante-quatre, vingt-deux, dix, soixante"


@pytest.mark.asyncio
async def test_une_erreur_rend_le_texte_tel_quel(monkeypatch):
    """⛔ Pipecat drops the sentence's audio when a transform raises."""
    from api.services.pipecat import nombres_pour_la_voix

    def casse(*_):
        raise RuntimeError("boom")

    monkeypatch.setattr(nombres_pour_la_voix, "ecrire_pour_la_voix", casse)
    assert await nombres_en_mots("code postal 60550") == "code postal 60550"


class _VoixQuiEcoute(TTSService):
    """A voice that keeps the text it was asked to say (push_text_frames on, like Mistral)."""

    def __init__(self, **kwargs):
        super().__init__(push_start_frame=True, push_stop_frames=True, sample_rate=24000, **kwargs)
        self.dits: list[str] = []

    def can_generate_metrics(self) -> bool:
        return False

    async def run_tts(self, text: str, context_id: str):
        self.dits.append(text)
        yield TTSAudioRawFrame(audio=b"\x00\x00" * 240, sample_rate=24000, num_channels=1, context_id=context_id)


@pytest.mark.asyncio
async def test_la_voix_dit_les_mots_et_lhistorique_garde_les_chiffres():
    """V1, through Pipecat itself: what is spoken is in words; the text frame
    that goes back into the model's context carries the digits."""
    voix = _VoixQuiEcoute(text_transforms=construire_remplacements_de_voix({}, True))
    descendus, _ = await run_test(
        voix,
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("Beauvais, code postal 60000, c'est bien ça ?"),
            LLMFullResponseEndFrame(),
        ],
        # Same margin as the other pipeline tests of this folder: the start of a
        # pipeline is slower after heavy modules in the same run (a 1 s default timed out).
        start_timeout=15,
    )
    assert voix.dits and "soixante mille" in " ".join(voix.dits)
    assert not any(c.isdigit() for c in " ".join(voix.dits))
    historique = " ".join(f.text for f in descendus if isinstance(f, TTSTextFrame))
    assert "60000" in historique
    assert "soixante" not in historique
