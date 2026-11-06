"""[.mark] RA-B (R4d, audit 02 B2 et § 5.2) : l'ordre dans lequel les données entrent dans l'appel, écrit une fois.

Ce que l'appel sait au décroché vient de six couches, de la plus basse à la plus haute. Une couche plus haute passe
par-dessus une plus basse ; une seule exception, écrite ici : **la lecture avant l'appel** (l'adresse de l'étape de
départ, un logiciel du client) ne remplace **jamais** un objet de l'organisation, sauf si l'étape de départ le demande
par son nom (``pre_call_fetch_remplace``). Chaque remplacement est tracé dans le run (``runtime_configuration``,
clé ``lecture_avant_l_appel``) : le nom de la donnée et ce qui s'est passé, jamais sa valeur.

Cet ordre est affiché tel quel dans la fiche de l'étape de départ (``ui``, ``OrdreDInjection``) : même liste, même ordre.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.workflow.initial_context import merge_external_initial_context

CLE_TRACE = "lecture_avant_l_appel"

# (identifiant, libellé en français, libellé en anglais) : du plus bas au plus haut.
ORDRE_D_INJECTION: tuple[tuple[str, str, str], ...] = (
    ("defaut", "Valeurs par défaut du code", "Code defaults"),
    ("organisation", "Organisation (annonce, équipe, phrases)", "Organization (announcement, team, phrases)"),
    ("etablissement", "Établissement servi", "Establishment served"),
    ("objets", "Objets de l'agent", "Agent objects"),
    ("lecture", "Lecture avant l'appel", "Pre-call lookup"),
    ("appel", "Contexte de l'appel (numéro, date, direction)", "Call context (number, date, direction)"),
)

REGLE_FR = (
    "La lecture avant l'appel ne remplace un objet que si l'étape de départ le demande, par son nom."
)


def noms_demandes(texte: Any) -> set[str]:
    """Les noms listés (séparés par des virgules) dans le réglage de l'étape de départ."""
    if not isinstance(texte, str):
        return set()
    return {n.strip() for n in texte.split(",") if n.strip()}


def noms_des_objets(contexte: dict) -> set[str]:
    """Les objets posés au décroché, lus dans l'estampille du run (poses + gardes)."""
    estampille = (contexte.get("runtime_configuration") or {}).get("objets")
    if not isinstance(estampille, dict):
        return set()
    return {
        n
        for cle in ("poses", "gardes")
        for n in (estampille.get(cle) or [])
        if isinstance(n, str)
    }


def fusionner_la_lecture(
    contexte: dict, lecture: dict | None, demandes: set[str] | None = None
) -> tuple[dict, list[dict]]:
    """Le contexte après la lecture avant l'appel, et la trace de ce qu'elle a fait (une ligne par donnée qui
    existait déjà : ``refusee`` pour un objet non demandé, ``remplacee`` sinon). ⛔ Ne lève jamais (dans le doute,
    la lecture est fusionnée comme avant)."""
    try:
        demandes = demandes or set()
        objets = noms_des_objets(contexte)
        retenue = {
            k: v
            for k, v in (lecture or {}).items()
            if not (k in objets and k not in demandes)
        }
        trace: list[dict] = []
        for cle in (lecture or {}):
            if cle in objets and cle not in demandes:
                trace.append({"cle": cle, "couche": "objets", "decision": "refusee"})
            elif (
                contexte.get(cle) not in (None, "")
                and contexte.get(cle) != lecture[cle]
                and cle != "runtime_configuration"
            ):
                trace.append(
                    {
                        "cle": cle,
                        "couche": "objets" if cle in objets else "contexte",
                        "decision": "remplacee",
                    }
                )
        fusionne = merge_external_initial_context(contexte, retenue)
        if trace:
            runtime = dict(fusionne.get("runtime_configuration") or {})
            runtime[CLE_TRACE] = trace
            fusionne["runtime_configuration"] = runtime
        return fusionne, trace
    except Exception as erreur:  # noqa: BLE001 -- la lecture ne coûte jamais l'appel
        logger.error(f"[injection] trace de la lecture avant l'appel impossible : {erreur!r}")
        return merge_external_initial_context(contexte, lecture), []
