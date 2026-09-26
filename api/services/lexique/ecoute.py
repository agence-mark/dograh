"""[.mark] What the transcription listens for, and how the voice says the names.

Two uses of the same vocabulary (L4, L7, L8 of 2026-09-16):

- ① the terms ticked « listen for » are sent to the transcription after the
  agent's own Dictionary, within the ceiling DECLARED WITH THE PROVIDER, in
  tokens (``api/services/configuration/plafond_lexique.py``, Q1 of 2026-09-26:
  the 120 terms / 1 600 characters of 2026-09-17 were refused by Deepgram and
  made every agent fall silent on 2026-09-18);
- ③ the pronunciations are applied to the text sent to the voice, in ONE table
  with the agent's « Pronunciation fixes », the agent winning on the same word.

⚠️ Only the text sent to the voice changes; the conversation the model reads
keeps the official spelling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from api.schemas.lexique_metier import LexiqueMetier, normaliser_terme
from api.services.configuration.plafond_lexique import PlafondLexique, jetons_du_terme


def termes_du_dictionnaire(dictionary: str | None) -> list[str]:
    """The agent's Dictionary, as the call already reads it: comma separated."""
    if not dictionary or not isinstance(dictionary, str):
        return []
    return [terme.strip() for terme in dictionary.split(",") if terme.strip()]


@dataclass(frozen=True)
class ListeEcoutee:
    """The list sent to the transcription, and what the ceiling left out."""

    termes: list[str]
    # Asked for but not sent: past the ceiling, or no ceiling declared at all.
    non_envoyes: list[str]
    # The prudent estimate of what ``termes`` costs.
    jetons: int
    # None: the provider declares no ceiling, and nothing is sent.
    plafond: PlafondLexique | None

    @property
    def tronquee(self) -> bool:
        return bool(self.non_envoyes)


def termes_voulus(dictionary: str | None, lexique: LexiqueMetier | None) -> list[str]:
    """The Dictionary first, then the ticked terms, duplicates dropped whatever their case."""
    voulus = termes_du_dictionnaire(dictionary)
    if lexique is not None:
        voulus += [terme.terme for terme in lexique.termes if terme.a_ecouter]
    uniques: list[str] = []
    vus: set[str] = set()
    for terme in voulus:
        empreinte = terme.casefold()
        if empreinte not in vus:
            vus.add(empreinte)
            uniques.append(terme)
    return uniques


def construire_liste_ecoutee(
    dictionary: str | None,
    lexique: LexiqueMetier | None,
    plafond: PlafondLexique | None,
) -> ListeEcoutee:
    """The terms the transcription listens for, within the provider's ceiling.

    The agent's Dictionary comes first (it is what the agent's own screen
    promises), then the ticked terms in the order of the vocabulary; the
    official spelling is sent, never the other spellings. The END is cut: a
    term that does not fit is left out and the next ones are tried, so a long
    name never costs the short ones behind it.

    ⛔ No ceiling declared for the provider: NOTHING is sent (Q1, 2026-09-26),
    and it is logged. An unknown limit is a risk of refusal.
    """
    voulus = termes_voulus(dictionary, lexique)
    if plafond is None:
        if voulus:
            logger.warning(
                f"[.mark] No term sent to the transcription: its provider declares no ceiling "
                f"({len(voulus)} asked for). The vocabulary keeps correction and pronunciation."
            )
        return ListeEcoutee(termes=[], non_envoyes=voulus, jetons=0, plafond=None)
    retenus: list[str] = []
    non_envoyes: list[str] = []
    jetons = 0
    for terme in voulus:
        cout = jetons_du_terme(terme, plafond)
        if (plafond.termes is not None and len(retenus) >= plafond.termes) or (
            plafond.jetons is not None and jetons + cout > plafond.jetons
        ):
            non_envoyes.append(terme)
            continue
        retenus.append(terme)
        jetons += cout
    if non_envoyes:
        logger.warning(
            f"[.mark] Terms listened for capped at {len(retenus)} terms / {jetons} tokens "
            f"(ceiling {plafond.termes} terms / {plafond.jetons} tokens, {plafond.fournisseur}): "
            f"{len(non_envoyes)} of {len(voulus)} left out "
            f"({', '.join(non_envoyes[:10])}). They keep correction and pronunciation."
        )
    return ListeEcoutee(termes=retenus, non_envoyes=non_envoyes, jetons=jetons, plafond=plafond)


def prononciations_du_lexique(lexique: LexiqueMetier | None) -> list[tuple[str, str]]:
    """(spelling, how to say it) for every spelling of every name that has one."""
    return [(ecrit, prononce) for ecrit, prononce, _ in _prononciations_par_terme(lexique)]


def _prononciations_par_terme(lexique: LexiqueMetier | None) -> list[tuple[str, str, str]]:
    """(spelling, how to say it, the term it belongs to), every spelling kept."""
    if lexique is None:
        return []
    paires = []
    for terme in lexique.termes:
        if not terme.prononciation:
            continue
        for ecrit in dict.fromkeys(terme.formes()):
            paires.append((ecrit, terme.prononciation, terme.terme))
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
    # ⛔ Indexée sur l'orthographe ÉCRITE, pas sur sa forme normalisée : « Jotul »
    # et « Jøtul » ont la même forme normalisée, et l'une écrasait l'autre. C'est
    # l'orthographe officielle qui disparaissait -- celle que la correction écrit,
    # donc la seule que la voix reçoit (relecture indépendante du 17/09).
    du_lexique = _prononciations_par_terme(lexique)
    de_lagent = entrees_de_lagent(run_configs)
    # L'agent l'emporte sur le mot qu'il nomme, et sa façon de le dire vaut pour
    # TOUTES les orthographes de ce nom : sinon la variante resterait dite
    # autrement que le nom officiel, ou plus dite du tout.
    surcharges = {
        terme: prononce
        for ecrit, prononce in de_lagent
        for orthographe, _, terme in du_lexique
        if normaliser_terme(orthographe) == normaliser_terme(ecrit)
    }
    table: dict[str, tuple[str, str]] = {}
    couvertes: set[str] = set()
    for ecrit, prononce, terme in du_lexique:
        if terme in surcharges:
            prononce = surcharges[terme]
        table[ecrit] = (ecrit, prononce)
        couvertes.add(normaliser_terme(ecrit))
    for ecrit, prononce in de_lagent:
        # ⛔ Une orthographe déjà portée par le lexique surchargé ne se réécrit pas
        # ici : les motifs ignorent la casse, et deux motifs équivalents
        # appliquaient le remplacement DEUX fois (contre-relecture du 17/09).
        if normaliser_terme(ecrit) in couvertes:
            continue
        table[ecrit] = (ecrit, prononce)
    regles = []
    for ecrit, prononce in sorted(table.values(), key=lambda paire: -len(paire[0])):
        # (?i): what is typed on screen is matched whatever its case.
        motif = r"(?i)(?<!\w)" + re.escape(ecrit) + r"(?!\w)"
        # A backslash in the replacement is a group reference for ``re.sub``.
        regles.append((motif, prononce.replace("\\", "\\\\")))
    return regles


CLE_PROPOSE = "lexique_propose"
# ⛔ The former name, injected with THE SAME content for as long as an agent
# reads it (agents 20, 25, 26 and their copies): removing it is a step of its
# own, on Evan's go (plan « le lexique », rule of safety n° 1).
CLE_A_ECOUTER = "lexique_a_ecouter"


def termes_proposes(lexique: LexiqueMetier | None) -> list[str]:
    """The names the business offers, in the order of the vocabulary."""
    if lexique is None:
        return []
    return [terme.terme for terme in lexique.termes if terme.propose]


def injecter_lexique_propose(contexte: dict, termes: list[str]) -> dict:
    """Return the call context with ``lexique_propose`` (and its former name
    ``lexique_a_ecouter``): the names the business offers, comma separated.

    The agent answers "do you offer X?" from this variable, so a name ticked on
    screen is said without republishing the agent (Q1 = B of 2026-09-16). It
    reads ONLY the box « the business offers it » (Q4, 2026-09-26): what the
    transcription listens for is another question.

    - No name offered: the context is returned unchanged, keys absent.
    - A value already present and non-empty is kept, key by key (the pre-call
      fetch wins).
    - ⛔ Never raises.
    """
    try:
        if not termes:
            return contexte
        valeur = ", ".join(termes)
        resultat = dict(contexte)
        for cle in (CLE_PROPOSE, CLE_A_ECOUTER):
            actuelle = contexte.get(cle)
            if actuelle is not None and not (isinstance(actuelle, str) and not actuelle.strip()):
                continue
            resultat[cle] = valeur
        return resultat
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.error(f"[.mark] Offered names not injected, the call goes on: {erreur!r}")
        return contexte
