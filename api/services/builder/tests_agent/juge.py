"""[.mark] Builder, lot 6 : le juge à part (Q1, B43). TOUJOURS non bloquant.

Le code décide (``verdict.py``). Le juge ne sert qu'à ce que le code ne sait pas vérifier (« une seule question », naturel,
ton) et son avis s'affiche À PART : il n'entre jamais dans ``ok`` et ne bloque jamais une publication.

* **plusieurs passes quand c'est serré** : une passe ; si une réponse manque de confiance (< ``SEUIL_DE_CONFIANCE``), jusqu'à
  ``PASSES_MAX`` passes et vote à la majorité ; la question est alors marquée ``serre``.
* **calibré sur nos notes** : ``calibrer`` compare les avis du juge aux notes humaines gardées (``MARK_BUILDER:<agent>:notes_juge``) ;
  tant que l'accord est sous ``ACCORD_MIN`` (ou les notes sous ``NOTES_MIN``), l'avis est marqué ``non_calibre``.

Le cerveau est injecté (le même que celui du builder) : les tests passent un cerveau factice. ⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

import json
import re
from typing import Any

from api.schemas.appel_simule import CONSIGNE_JUGE
from api.services.builder import stock
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau
from api.services.builder.constantes import cle_builder
from api.services.builder.tests_agent.jeu import completer

SEUIL_DE_CONFIANCE = 0.7
PASSES_MAX = 3
NOTES_MIN = 5
ACCORD_MIN = 0.8

FORMAT = (
    "Réponds UNIQUEMENT par un objet JSON par ligne, une ligne par question, dans l'ordre : "
    '{"ok": true|false, "confiance": nombre entre 0 et 1, "raison": "une phrase"}.'
)


def _conversation(lignes: list[tuple[str, str]]) -> str:
    return "\n".join(f"{'AGENT' if r == 'agent' else 'APPELANT'} : {t}" for r, t in lignes)


def lire_les_reponses(texte: str, n: int) -> list[dict[str, Any]]:
    """Les n réponses du juge. Une réponse illisible vaut « pas d'avis » (``ok`` None), jamais un oui inventé."""
    sorties: list[dict[str, Any]] = []
    for ligne in texte.splitlines():
        m = re.search(r"\{.*\}", ligne)
        if not m:
            continue
        try:
            brut = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(brut, dict) and isinstance(brut.get("ok"), bool):
            try:
                confiance = max(0.0, min(1.0, float(brut.get("confiance", 0.5))))
            except (TypeError, ValueError):
                confiance = 0.5
            sorties.append({"ok": brut["ok"], "confiance": confiance, "raison": str(brut.get("raison") or "")[:300]})
    while len(sorties) < n:
        sorties.append({"ok": None, "confiance": 0.0, "raison": "no usable answer"})
    return sorties[:n]


async def _une_passe(cerveau: Cerveau, lignes: list[tuple[str, str]], questions: list[str]) -> list[dict[str, Any]]:
    demande = (
        f"Conversation :\n{_conversation(lignes)}\n\nQuestions :\n"
        + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
        + f"\n\n{FORMAT}"
    )
    texte = await completer(cerveau, CONSIGNE_JUGE, [{"role": "user", "content": demande}])
    return lire_les_reponses(texte, len(questions))


async def juger(cerveau: Cerveau, lignes: list[tuple[str, str]], questions: list[str]) -> dict[str, Any]:
    """L'avis du juge sur ``questions``. Jamais bloquant ; une erreur du cerveau donne « pas d'avis », pas un échec du test."""
    if not questions:
        return {"bloquant": False, "avis": []}
    passes: list[list[dict[str, Any]]] = []
    try:
        passes.append(await _une_passe(cerveau, lignes, questions))
        while len(passes) < PASSES_MAX and any(r["ok"] is None or r["confiance"] < SEUIL_DE_CONFIANCE for r in passes[0]):
            passes.append(await _une_passe(cerveau, lignes, questions))
    except ErreurCerveau as erreur:
        return {"bloquant": False, "avis": [], "erreur": erreur.message}
    avis = []
    for i, question in enumerate(questions):
        reponses = [p[i] for p in passes if p[i]["ok"] is not None]
        oui = sum(1 for r in reponses if r["ok"])
        non = len(reponses) - oui
        ok = None if not reponses else oui > non if oui != non else None
        serre = len(passes) > 1
        raison = next((r["raison"] for r in reponses if r["ok"] == ok), "") if ok is not None else "no majority"
        avis.append({"question": question, "ok": ok, "serre": serre, "passes": len(passes), "raison": raison})
    return {"bloquant": False, "avis": avis}


# --- la calibration sur nos notes ------------------------------------------------------------------------------------------------


def calibrer(avis_du_juge: list[dict[str, Any]], notes: list[dict[str, Any]]) -> dict[str, Any]:
    """Accord entre le juge et nos notes. Chaque entrée : ``{"id": ..., "ok": bool}``. Pur."""
    juge = {a["id"]: a["ok"] for a in avis_du_juge if a.get("ok") is not None}
    communs = [n for n in notes if n.get("id") in juge]
    accords = [n for n in communs if bool(n["ok"]) == bool(juge[n["id"]])]
    taux = len(accords) / len(communs) if communs else None
    return {
        "comparees": len(communs),
        "accord": taux,
        "desaccords": [n["id"] for n in communs if n not in accords],
        "calibre": taux is not None and len(communs) >= NOTES_MIN and taux >= ACCORD_MIN,
    }


def cle_des_notes(workflow_id: int) -> str:
    return cle_builder(workflow_id, "notes_juge")


async def noter(organization_id: int, workflow_id: int, identifiant: str, ok: bool) -> None:
    def transformer(ligne):
        notes = [n for n in (ligne or {}).get("notes") or [] if n.get("id") != identifiant] + [{"id": identifiant, "ok": bool(ok)}]
        return {"notes": notes[-200:]}

    await stock.modifier(organization_id, cle_des_notes(workflow_id), transformer)


async def notes(organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
    return list((await stock.lire(organization_id, cle_des_notes(workflow_id)) or {}).get("notes") or [])
