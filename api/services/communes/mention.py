"""[.mark] The note added to the caller's message, which the model reads.

🔑 The instruction to the agent lives HERE, in the note, and in no agent's
prompt (decision of 2026-09-16): every agent that collects a town gets the
same behaviour without anyone editing its prompt.

The wording is fixed by the plan, word for word:

- sure:
  ``[Vérification de la commune : « Beauvet » correspond à Beauvais (60000, Oise).
  Utilise ce nom sans le faire répéter.]``
- uncertain (one to three proposals); when the words heard are a postal code,
  the last sentence ends « fais préciser la commune avant de la noter. »:
  ``[Vérification de la commune : « Sanlis » peut être Senlis (60300, Oise),
  Senlis (62310, Pas-de-Calais) ou Saint-Lys (31470, Haute-Garonne). Demande
  d'abord si c'est Senlis (Oise) ; si ce n'est pas elle, propose Senlis
  (Pas-de-Calais), puis Saint-Lys (Haute-Garonne). Nomme chaque commune avec
  son département. Si aucune ne convient, fais préciser la commune ou son code
  postal avant de la noter.]``
  Decision of Evan, 2026-09-17 (bench run 268): « Fais préciser la commune »
  alone made the model ask an open question four times without ever saying
  Bresles, which it had been given first. The agent now names the first
  proposal; a refusal rules it out and brings the next one.
- nothing found: no note, the text is returned as is.

⛔ ``MARQUE`` is what makes the annotation idempotent: a message that already
starts a note with it is never annotated twice.
"""

from __future__ import annotations

from api.services.communes.analyse import SURE, Detection, Lecture
from api.services.communes.base import BaseCommunes

MARQUE = "[Vérification de la commune"


def _libelle(lecture: Lecture, base: BaseCommunes, codes_postaux_dits: frozenset[str]) -> str:
    c = lecture.commune
    # The postal code shown is the commune's first one, unless the caller
    # said one that belongs to it.
    dits = sorted(set(c.cps) & codes_postaux_dits)
    cp = dits[0] if dits else (c.cps[0] if c.cps else "?")
    return f"{c.nom} ({cp}, {base.nom_departement(c.dep)})"


def _enumerer(libelles: list[str]) -> str:
    if len(libelles) == 1:
        return libelles[0]
    return ", ".join(libelles[:-1]) + " ou " + libelles[-1]


def phrase_de_mention(detection: Detection, base: BaseCommunes) -> str:
    dits = detection.codes_postaux_dits
    if detection.statut == SURE:
        return (
            f"{MARQUE} : « {detection.entendu} » correspond à "
            f"{_libelle(detection.lectures[0], base, dits)}. "
            "Utilise ce nom sans le faire répéter.]"
        )
    propositions = [_libelle(l, base, dits) for l in detection.lectures[:3]]
    # A postal code was heard: asking for "the town or its postal code" would
    # get the same code again (plan nombres-dictes).
    preciser = (
        "fais préciser la commune avant de la noter.]"
        if detection.code_postal_entendu
        else "fais préciser la commune ou son code postal avant de la noter.]"
    )
    # Each town with its department: a bare name would read « si ce n'est pas
    # Saint-Just, propose Saint-Just » for homonyms (review of 2026-09-17:
    # 11 % of communes share their name).
    noms = [f"{l.commune.nom} ({base.nom_departement(l.commune.dep)})" for l in detection.lectures[:3]]
    if len(noms) == 1:
        demande = f"Demande si c'est {noms[0]}, en nommant son département. Si ce n'est pas elle, {preciser}"
    else:
        demande = (
            f"Demande d'abord si c'est {noms[0]} ; si ce n'est pas elle, propose {', puis '.join(noms[1:])}. "
            f"Nomme chaque commune avec son département. Si aucune ne convient, {preciser}"
        )
    return f"{MARQUE} : « {detection.entendu} » peut être {_enumerer(propositions)}. {demande}"


def mentionner(texte: str, detections: list[Detection], base: BaseCommunes) -> str:
    """``texte`` followed by one note per town found, or ``texte`` unchanged."""
    if not detections:
        return texte
    return " ".join([texte, *(phrase_de_mention(d, base) for d in detections)])


def deja_mentionne(texte: str) -> bool:
    return MARQUE in texte
