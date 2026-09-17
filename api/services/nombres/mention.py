"""[.mark] The note on numbers added to the caller's message, which the model reads.

The wording is fixed by the plan (nombres-dictes, 2026-09-16), word for word:

- ambiguous amount (N3):
  ``[Lecture des nombres : « trois mille cinq » peut être 3 500 € ou 3 005 €.
  Si tu notes ce montant, note les deux.]``
  No reading back is asked: an agent may be forbidden to read an amount.
- reference (N4), only at steps that collect a ``reference…`` variable:
  ``[Lecture des nombres : référence entendue « deux mille vingt-six tiret huit
  cent quarante-sept », écrite « 2026-847 ». Relis-la en recopiant « 2026-847 »
  tel quel, en chiffres, et fais-la confirmer avant de la noter.]``
  Changed by Evan, 2026-09-17 (bench run 267): "relis-la groupe par groupe" made
  the model write the words itself ("quatre-vingt-quatre sept" for 847), which
  the voice rewrite cannot correct; in digits, the voice says them right.
- nothing for a phone, a department, an unambiguous amount, anything else.

⛔ ``MARQUE`` makes the note idempotent, like the town note's.
"""

from __future__ import annotations

from api.services.nombres.lecture import MONTANT, REFERENCE, NombreLu

MARQUE = "[Lecture des nombres"


def _euros(valeur: int) -> str:
    return f"{valeur:,}".replace(",", " ")


def phrase_de_mention(nombre: NombreLu) -> str | None:
    if nombre.type == MONTANT and nombre.montant_ambigu:
        courant, arithmetique = nombre.montants
        return (
            f"{MARQUE} : « {nombre.entendu} » peut être {_euros(courant)} € ou "
            f"{_euros(arithmetique)} €. Si tu notes ce montant, note les deux.]"
        )
    if nombre.type == REFERENCE:
        return (
            f"{MARQUE} : référence entendue « {nombre.entendu} », écrite « {nombre.ecrit} ». "
            f"Relis-la en recopiant « {nombre.ecrit} » tel quel, en chiffres, "
            "et fais-la confirmer avant de la noter.]"
        )
    return None


def mentionner_nombres(texte: str, nombres: list[NombreLu], avec_references: bool = True) -> str:
    """``texte`` followed by one note per number that needs one, or ``texte`` unchanged.

    ``avec_references``: False at a step that collects no reference (N4).
    """
    phrases = [
        phrase
        for n in nombres
        if (avec_references or n.type != REFERENCE)
        and (phrase := phrase_de_mention(n)) is not None
    ]
    return " ".join([texte, *phrases]) if phrases else texte


def deja_mentionne(texte: str) -> bool:
    return MARQUE in texte
