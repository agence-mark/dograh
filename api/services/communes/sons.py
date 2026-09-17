"""[.mark] How a town name SOUNDS, by the pronunciation library espeak-ng.

Why this module exists
----------------------
The transcription writes what it hears in other words: "Lyon Court" for
Liancourt, "monte-à-terre" for Montataire (benches of 2026-09-16 and 17).
The spelling keys (``cle_phonetique``, ``cle_sonore``) compare letters;
espeak-ng reads the words aloud as French and gives their sounds, so
"monte-à-terre" and "Montataire" come out identical.

Measured on 2026-09-17: helps the name said alone for Montataire,
Coye-la-Forêt, Liancourt, Clermont-Ferrand, Senlis, L'Isle-Adam; does not for
"Accueil", "il a foré", "conquérir" (the postal code decides those, V4).
About 0.04 ms per phrase; the 34 969 communes in about 1 second, once, by the
generation script (the sounds are stored in the list's file).

Decision of Evan, 2026-09-17 (V5). ⚠️ espeak-ng and phonemizer are GPL: no
consequence for a hosted service, and this module is not offered to Dograh.

⛔ Fail-open: without the library, ``sons`` returns None and the town check
works on the spelling keys alone, as before.
"""

from __future__ import annotations

import re
import threading

from loguru import logger

# Sounds that a French speaker and the transcription do not tell apart, merged:
# open and closed vowels, and each nasal vowel as one character.
_FUSIONS = (
    ("ɑ̃", "A"), ("ɔ̃", "O"), ("ɛ̃", "E"), ("œ̃", "E"),
    ("ɛ", "e"), ("ɔ", "o"), ("œ", "ø"), ("ə", "ø"), ("ɑ", "a"),
)
_RETIRES = str.maketrans("", "", " ˈˌːˑ-‿")

_backend = None
_indisponible = False
_verrou = threading.Lock()
# 🔒 One synthesis at a time: phonemizer writes each result to ONE temporary file
# per backend and espeak-ng's C state is shared, while ctypes releases the Python
# lock. Two calls at once returned wrong sounds 747 times out of 750 (review of
# 2026-09-17). About a millisecond per sentence: waiting costs nothing.
_verrou_synthese = threading.Lock()


def _obtenir_backend():
    global _backend, _indisponible
    if _backend is not None or _indisponible:
        return _backend
    with _verrou:
        if _backend is None and not _indisponible:
            try:
                # ⛔ Imported lazily: a dependency missing from the image must not
                # stop the API from starting.
                import espeakng_loader
                from phonemizer.backend import EspeakBackend
                from phonemizer.backend.espeak.wrapper import EspeakWrapper

                EspeakWrapper.set_library(espeakng_loader.get_library_path())
                EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
                _backend = EspeakBackend("fr-fr", preserve_punctuation=False, with_stress=False)
            except Exception as erreur:  # noqa: BLE001 -- the town check goes on without it
                _indisponible = True
                logger.warning(f"[.mark] Pronunciation library unavailable, spelling keys only: {erreur!r}")
    return _backend


def precharger() -> None:
    """Start the engine (about 650 ms the first time). Blocking: worker thread."""
    _obtenir_backend()


def simplifier(api: str) -> str:
    """The sounds, without spaces, stress or length, close sounds merged."""
    t = api.translate(_RETIRES)
    for avant, apres in _FUSIONS:
        t = t.replace(avant, apres)
    return t


# An elided letter is read as its name ("l" -> "èl"): glued back to its word,
# "l isle adam" is read "lisle adam".
_ELISION = re.compile(r"\b(qu|[cdjlmnst]) (?=[a-z])")


def sons(textes: list[str]) -> list[str] | None:
    """The simplified sounds of each normalised text, or None without the library.

    ⛔ Blocking (a C library, the Python lock held): call it off the event loop.
    """
    if not textes:
        return []
    backend = _obtenir_backend()
    if backend is None:
        return None
    try:
        prepares = [_ELISION.sub(r"\1", t) for t in textes]
        with _verrou_synthese:
            prononces = backend.phonemize(prepares, strip=True)
        return [simplifier(s) for s in prononces]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Pronunciation failed, spelling keys only: {erreur!r}")
        return None
