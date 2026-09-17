"""[.mark] What the model reads once the names of the trade have been recognised.

Decision L5 of 2026-09-16, and the wording fixed by the plan, word for word:

- sure: no note, the heard words are REPLACED by the official name
  ("c'est un Edilcamin" -> "c'est un Edilkamin");
- doubtful, one to three names:
  ``[Lexique : « édile camembert » peut être Edilkamin (marque) ou Ecoforest
  (marque). Fais confirmer ce nom avant de le noter.]``

🔑 Like the towns, the instruction to the agent lives in the note and in no
agent's prompt (L9): every agent of the organization behaves the same without
anyone editing it.

⛔ The transcription kept in the run is what the caller was heard saying: only
what the model reads changes (same rule as the dictated numbers).
"""

from __future__ import annotations

from api.services.lexique.analyse import A_CONFIRMER, SURE, Detection

MARQUE = "[Lexique :"
# The notes of the other readers of the caller's message: the vocabulary never
# reads inside them (a brand named in a note must not be read again).
MARQUES_DES_AUTRES = ("[Vérification de la commune", "[Lecture des nombres")


def _libelle(terme: str, categorie: str | None) -> str:
    return f"{terme} ({categorie})" if categorie else terme


def _enumerer(libelles: list[str]) -> str:
    if len(libelles) == 1:
        return libelles[0]
    return ", ".join(libelles[:-1]) + " ou " + libelles[-1]


def phrase_de_mention(detection: Detection) -> str:
    propositions = [_libelle(p.terme, p.categorie) for p in detection.propositions[:3]]
    return (
        f"{MARQUE} « {detection.entendu} » peut être {_enumerer(propositions)}. "
        "Fais confirmer ce nom avant de le noter.]"
    )


def reecrire(texte: str, detections: list[Detection]) -> str:
    """``texte`` with the sure names written properly, WITHOUT any note."""
    corrige = texte
    # From the end: an earlier replacement would move the spans that follow.
    for detection in sorted(detections, key=lambda d: -d.debut):
        if detection.statut != SURE or detection.entendu == detection.terme:
            continue
        corrige = corrige[: detection.debut] + detection.terme + corrige[detection.fin :]
    return corrige


def mentions(detections: list[Detection]) -> list[str]:
    """One note per doubtful name, in the order the names were heard."""
    return [
        phrase_de_mention(d)
        for d in sorted(detections, key=lambda d: d.debut)
        if d.statut == A_CONFIRMER
    ]


def corriger(texte: str, detections: list[Detection]) -> str:
    """``texte`` with the sure names written properly, then one note per doubtful name.

    ⚠️ For a message that already carries the notes of the towns or of the
    numbers, the caller of this function composes the order itself
    (``reconnaissance_lexique.corriger_texte``): the notes of the vocabulary go
    AFTER theirs, never between the caller's words and their notes.
    """
    if not detections:
        return texte
    return " ".join([reecrire(texte, detections), *mentions(detections)])


def deja_mentionne(texte: str) -> bool:
    return MARQUE in texte


def partie_de_lappelant(texte: str) -> tuple[str, str]:
    """The caller's words, and the notes already added by any reader (kept as they are).

    A message read again after a tool call carries the notes of the towns and
    of the dictated numbers; the names cited there are never read as brands.
    """
    coupe = len(texte)
    for marque in (MARQUE, *MARQUES_DES_AUTRES):
        place = texte.find(marque)
        if place != -1:
            coupe = min(coupe, place)
    return texte[:coupe].rstrip(), texte[coupe:]
