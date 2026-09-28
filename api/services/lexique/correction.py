"""[.mark] What the model reads once the names of the trade have been recognised.

Chantier correctifs-modules, D2 and D3 (decisions of Evan, 28/09), replacing L5
of 2026-09-16:

- ⛔ The caller's words are NEVER rewritten. The model, and every reader after
  this one (towns, numbers, streets), reads the sentence as it was heard. A
  reading gone wrong is a suggestion the model may ignore, never a word it
  cannot see (pause note of 27/09: the module « sabotait les autres modules »).
- The vocabulary adds a RECOMMENDATION, for the model only, never read aloud and
  with no question asked because of it:
  ``[Lexique, pour toi seulement, jamais dit à voix haute : la personne a peut-être dit Edilkamin.]``
  (« a dit » when the reading is sure). Two names possible:
  ``… a peut-être dit Rika ou Scan.]`` -- the record's tool then asks once
  (``fiche_au_fil_de_leau.lire_lexique``).
- A name heard exactly as it is written adds nothing.

🔑 Like the towns, the instruction to the agent lives in the note and in no
agent's prompt (L9): every agent of the organization behaves the same.
"""

from __future__ import annotations

from api.schemas.lexique_metier import normaliser_terme
from api.services.lexique.analyse import A_CONFIRMER, SEUIL_A_CONFIRMER, SURE, Detection

MARQUE = "[Lexique"
# The notes of the other readers of the caller's message: the vocabulary never
# reads inside them (a brand named in a note must not be read again).
MARQUES_DES_AUTRES = ("[Vérification de la commune", "[Lecture des nombres")
ENTETE = f"{MARQUE}, pour toi seulement, jamais dit à voix haute :"


def termes_possibles(detection: Detection) -> list[str]:
    """The names this reading may be: the retained one, and for a doubtful
    reading a second one close enough to be as likely."""
    if detection.statut == SURE:
        return [detection.terme]
    termes = [detection.terme]
    for proposition in detection.propositions[1:2]:
        if proposition.score >= SEUIL_A_CONFIRMER and proposition.terme not in termes:
            termes.append(proposition.terme)
    return termes


def phrase_de_mention(detection: Detection) -> str:
    termes = termes_possibles(detection)
    if detection.statut == SURE:
        return f"{ENTETE} la personne a dit {termes[0]}.]"
    return f"{ENTETE} la personne a peut-être dit {' ou '.join(termes)}.]"


def _deja_ecrit(detection: Detection) -> bool:
    return normaliser_terme(detection.entendu) == normaliser_terme(detection.terme)


def mentions(detections: list[Detection]) -> list[str]:
    """One recommendation per name heard otherwise than written, in the order
    the names were heard. Towns (homonyms) add nothing."""
    return [
        phrase_de_mention(d)
        for d in sorted(detections, key=lambda d: d.debut)
        if d.statut in (SURE, A_CONFIRMER) and not (d.statut == SURE and _deja_ecrit(d))
    ]


def corriger(texte: str, detections: list[Detection]) -> str:
    """``texte`` UNCHANGED, then one recommendation per name (D2).

    ⚠️ For a message that already carries the notes of the towns or of the
    numbers, the caller of this function composes the order itself
    (``reconnaissance_lexique.corriger_texte``): the notes of the vocabulary go
    AFTER theirs, never between the caller's words and their notes.
    """
    return " ".join([texte, *mentions(detections)]) if detections else texte


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
