"""[.mark] Chantier Partie 1, lot 6 : le repli A (B12 § 2, décision 1 ; D62 : repli A seul, aucun ``tool_choice``, B13 point 1 réfuté).

- ``refus_de_la_fiche(retour)`` : le retour refuse-t-il la FICHE (sa forme, ou une valeur qui ne vient pas d'elle) ? Lecture de la liste fermée du
  lot 2 (``enveloppe.REFUS_DE_LA_FICHE``), jamais du sens. Après un refus de la fiche, une phrase du modèle sans outil n'est jamais dite. Après un
  refus du métier (hors zone, rupture, minimum…), la phrase du modèle qui dit la raison reste dite.
- ``repli_dit_par_le_code(p)`` : au bout des passes, sans phrase dicible, le code redit, dans cet ordre, la question en attente par sa phrase du code
  (une proposition par sa phrase de B8 ; une étape de menu par ses choix), sinon la phrase de ce qui manque (``phrases_du_manque``), sinon rien (le
  tour est compté faux). Le code ne choisit rien : il redemande.
"""

from __future__ import annotations

import re
from typing import Any

from api.services.actions_communes.enveloppe import REFUS_DE_LA_FICHE

RAPPEL_APRES_REFUS = (
    "- Ta réponse précédente n'avait pas d'appel d'outil après le refus de ta fiche : elle n'a pas été dite, et rien n'est changé."
)


def _raisons(x: Any, sortie: list[str]) -> list[str]:
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "raison" and isinstance(v, str):
                sortie.append(v)
            else:
                _raisons(v, sortie)
    elif isinstance(x, list):
        for v in x:
            _raisons(v, sortie)
    return sortie


def refus_de_la_fiche(retour: Any) -> bool:
    """Vrai si le retour porte une raison rangée « fiche » (``REFUS_DE_LA_FICHE``)."""
    return any(r in REFUS_DE_LA_FICHE for r in _raisons(retour, []))


# Les statuts du module qui refusent (le ``REFUSE`` et l'``INTROUVABLE`` du banc) ; un manque (``INCOMPLETE`` : le numéro, le prénom), le minimum
# de la zone ou une précision à demander ne refusent rien : le modèle demande la suite (banc : ``i["refus"]``).
STATUTS_QUI_REFUSENT = frozenset({"HORS_ZONE", "INTROUVABLE", "RUPTURE", "HORS_CARTE", "INTERDIT"})


def refuse(retour: Any) -> bool:
    """Le retour refuse-t-il quelque chose : la fiche (``REJETEE``, une liste de refus), ou le métier (un statut du module qui refuse, hors zone,
    rupture, introuvable) ? ``a_faire`` seul n'en est pas un (une proposition née dans ce tour en porte un, la fiche restant FAIT), ni un fait
    bloquant qui ne refuse pas (un manque, le minimum de la zone dit par le code). Égalité à la vraie boucle (L06-41)."""
    if not isinstance(retour, dict):
        return False
    if retour.get("statut") in ("REJETEE", "INTROUVABLE") or retour.get("refus"):
        return True
    bloquant = (retour.get("faits") or {}).get("fait_bloquant") or {}
    return bloquant.get("statut_du_module") in STATUTS_QUI_REFUSENT or any(
        r.get("statut_du_module") in STATUTS_QUI_REFUSENT for r in retour.get("resultats") or [] if isinstance(r, dict))


def repli_dit_par_le_code(p: dict[str, Any] | None) -> str | None:
    """La phrase que le code dit quand le modèle n'a rien de dicible au bout des passes (``appel_b12.repli_dit_par_le_code``)."""
    if not isinstance(p, dict):
        return None
    q = p.get("question")
    if isinstance(q, dict):
        if q.get("type") == "proposition":
            return q.get("repli") or None
        texte = str(q.get("texte") or "").strip()
        if q.get("type") == "etape" and texte:
            return re.sub(r", ligne \d+ :", " :", texte).rstrip(" .") + " ?"
        return texte or None
    from api.services.commande.phrases_du_manque import texte_a_dire

    return texte_a_dire(p)
