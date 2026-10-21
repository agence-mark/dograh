"""[.mark] Chantier correctifs-apres-banc-v4 (lot 4, 4.10) : le compte rendu standard après une phrase du code.

Quand une phrase du code est suivie de « le modèle reprend », le modèle reçoit, **dans le résultat de son
outil** (jamais un message à part, refusé par certains fournisseurs), un compte rendu en français :

    [Ce qui vient de se passer : <le fait>.
    L'appelant a entendu : « <la phrase dite> ». Ne la répète pas.
    Noté dans la fiche : <les notes faites par la sortie ou le code>.
    Plus possible dans cet appel : <l'outil retiré>.]

Chaque ligne n'apparaît que si elle a un contenu. Aucun mot de métier : le fait vient du motif, la note
de la fiche et l'interdit de l'outil retiré viennent de ce que le code a réellement fait. Il remplace la
consigne anglaise « do not repeat it… » d'avant.

Mesuré au lot 0 : le levier qui évite la répétition est la phrase inscrite dans l'historique APRÈS le
résultat (0/30) ; le compte rendu dit en plus ce qui est noté et ce qui n'est plus possible.
"""

from __future__ import annotations

from collections.abc import Iterable


def _liste(elements: Iterable[str] | None) -> str:
    return " ; ".join(e.strip() for e in (elements or []) if e and e.strip())


def compte_rendu(
    fait: str,
    *,
    dit: str | None = None,
    notes: Iterable[str] | None = None,
    interdits: Iterable[str] | None = None,
    detail: str | None = None,
    crochets: bool = True,
) -> str:
    """Le compte rendu standard. ``fait`` : le fait du motif ; ``detail`` : sa raison courte, s'il y en a
    une (déjà écrite par le code, jamais par le modèle)."""
    lignes: list[str] = []
    fait = (fait or "").strip().rstrip(".")
    if fait:
        suite = f", {detail.strip().rstrip('.')}" if detail and detail.strip() else ""
        lignes.append(f"Ce qui vient de se passer : {fait}{suite}.")
    if dit and dit.strip():
        lignes.append(f"L'appelant a entendu : « {dit.strip()} ». Ne la répète pas.")
    notees = _liste(notes)
    if notees:
        lignes.append(f"Noté dans la fiche : {notees}.")
    interdit = _liste(interdits)
    if interdit:
        lignes.append(f"Plus possible dans cet appel : {interdit}.")
    if not lignes:
        return ""
    corps = "\n".join(lignes)
    return f"[{corps}]" if crochets else corps
