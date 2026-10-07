"""[.mark] The mentions of the team after a call (chantier l-agent-collegue, L3, C11 to C13).

- A gesture made by the code (transfer, passing on) is a CERTAIN mention, written with the
  gestures (``db/bases_clients/gestes.py``), whatever the switch: it only exists when the
  agent used the tool.
- When the agent's « Team known to the agent » is on (X2: off, nothing new is written):
  the recipients of the after-call mail are certain mentions (``destinataire``), and the
  names found in the summary and in the record are ``detectee`` or ``a_confirmer``
  (``nom_cite``, ``services/noms_personnes``).
- ⛔ The caller's own identity fields of the record (name, first name, mail, call-back
  number: the roles of the after-call) are never searched: a caller who bears the name of an
  employee is not a mention of that employee.
"""

from __future__ import annotations

from api.schemas.apres_appel import ApresAppelAgent

ROLES_DE_LAPPELANT = ("nom", "prenom", "mail", "numero_rappel")


def textes_de_la_fiche(champs: list[dict], agent: ApresAppelAgent | None) -> list[str]:
    """The record's values to search, the caller's identity fields left out."""
    exclus = {agent.champ(r) if agent else r for r in ROLES_DE_LAPPELANT}
    return [
        str(c.get("valeur"))
        for c in champs or []
        if c.get("nom") not in exclus and c.get("valeur")
    ]


def mentions_des_noms(personnes, textes: list[str]) -> list[dict]:
    """``nom_cite`` mentions found in these texts, the surest per person."""
    from api.services.noms_personnes import reperer

    meilleures: dict[str, dict] = {}
    for texte in textes:
        for r in reperer(texte, personnes):
            avant = meilleures.get(r.cle)
            if avant is None or (avant["certitude"] == "a_confirmer" and r.certitude == "detectee"):
                meilleures[r.cle] = {
                    "cle": r.cle,
                    "source": "nom_cite",
                    "certitude": r.certitude,
                    "extrait": r.extrait,
                }
    return list(meilleures.values())


def mentions_des_destinataires(destinataires: list[dict]) -> list[dict]:
    return [
        {"cle": d["cle"], "source": "destinataire", "certitude": "certaine", "extrait": None}
        for d in destinataires or []
        if d.get("cle")
    ]
