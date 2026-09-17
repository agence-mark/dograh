"""[.mark] What the transcription listens for, and how the voice says the names.

Two uses of the same vocabulary (L4, L7, L8 of 2026-09-16):

- ① the terms ticked « listen for » are sent to the transcription after the
  agent's own Dictionary, within one budget (T11, raised by Evan on 2026-09-17:
  120 terms or 1 600 characters, because the Dictionary of the agents already
  holds 81 terms and 1 142 characters and Deepgram takes it);
- ③ the pronunciations are applied to the text sent to the voice, in ONE table
  with the agent's « Pronunciation fixes », the agent winning on the same word.

⚠️ Only the text sent to the voice changes; the conversation the model reads
keeps the official spelling.
"""

from __future__ import annotations

import re

from loguru import logger

from api.schemas.lexique_metier import LexiqueMetier, normaliser_terme

MAX_TERMES_ECOUTES = 120
MAX_CARACTERES_ECOUTES = 1600


def termes_du_dictionnaire(dictionary: str | None) -> list[str]:
    """The agent's Dictionary, as the call already reads it: comma separated."""
    if not dictionary or not isinstance(dictionary, str):
        return []
    return [terme.strip() for terme in dictionary.split(",") if terme.strip()]


def construire_liste_flux(
    dictionary: str | None, lexique: LexiqueMetier | None
) -> tuple[list[str], bool]:
    """The terms the transcription listens for, and whether the budget cut the list.

    The agent's Dictionary comes first (it is what the agent's own screen
    promises), then the ticked terms in the order of the vocabulary. Duplicates
    are dropped without regard to case; the official spelling is sent, never the
    other spellings.
    """
    voulus = termes_du_dictionnaire(dictionary)
    if lexique is not None:
        voulus += [terme.terme for terme in lexique.termes if terme.a_ecouter]
    retenus: list[str] = []
    vus: set[str] = set()
    caracteres = 0
    depassement = False
    for terme in voulus:
        empreinte = terme.casefold()
        if empreinte in vus:
            continue
        if len(retenus) >= MAX_TERMES_ECOUTES or caracteres + len(terme) > MAX_CARACTERES_ECOUTES:
            depassement = True
            continue
        vus.add(empreinte)
        retenus.append(terme)
        caracteres += len(terme)
    if depassement:
        logger.warning(
            f"[.mark] Terms listened for capped at {len(retenus)} terms / {caracteres} characters: "
            f"{len(voulus)} were asked for. The ones left out keep correction and pronunciation."
        )
    return retenus, depassement


def prononciations_du_lexique(lexique: LexiqueMetier | None) -> list[tuple[str, str]]:
    """(spelling, how to say it) for every spelling of every name that has one."""
    if lexique is None:
        return []
    paires = []
    for terme in lexique.termes:
        if not terme.prononciation:
            continue
        for ecrit in dict.fromkeys(terme.formes()):
            paires.append((ecrit, terme.prononciation))
    return paires


def entrees_de_lagent(run_configs: dict | None) -> list[tuple[str, str]]:
    """The agent's « Pronunciation fixes », written ``heard:spoken``.

    ⛔ An entry with no colon, or with an empty left side, is skipped rather
    than guessed at: a replacement of the empty string would rewrite every
    single character of the answer.
    """
    entrees = (run_configs or {}).get("tts_replacements") or []
    paires = []
    for entree in entrees:
        if not isinstance(entree, str) or ":" not in entree:
            continue
        entendu, prononce = entree.split(":", 1)
        entendu = entendu.strip()
        if not entendu:
            continue
        paires.append((entendu, prononce.strip()))
    return paires


def regles_de_prononciation(
    run_configs: dict | None, lexique: LexiqueMetier | None
) -> list[tuple[str, str]]:
    """One table: the vocabulary, then the agent, which wins on the same word (L8).

    Same rules for every entry: case is ignored, and only whole words are
    replaced -- "Scan" never eats the "Scan" of "Scandinave". The longest
    spellings are applied first, so "Cheminées Godin" is said before "Godin".

    ⛔ Patterns are escaped: this screen is filled in by people running a
    business, and a dot typed in "M." would otherwise match any character.
    """
    table: dict[str, tuple[str, str]] = {}
    for ecrit, prononce in prononciations_du_lexique(lexique):
        table[normaliser_terme(ecrit)] = (ecrit, prononce)
    for ecrit, prononce in entrees_de_lagent(run_configs):
        table[normaliser_terme(ecrit)] = (ecrit, prononce)
    regles = []
    for ecrit, prononce in sorted(table.values(), key=lambda paire: -len(paire[0])):
        # (?i): what is typed on screen is matched whatever its case.
        motif = r"(?i)(?<!\w)" + re.escape(ecrit) + r"(?!\w)"
        # A backslash in the replacement is a group reference for ``re.sub``.
        regles.append((motif, prononce.replace("\\", "\\\\")))
    return regles
