"""[.mark] Builder, U6 (U12 point 2) : le juge dans Claude Code, trois actions du registre partagé (écran et MCP, un seul résultat).

* ``juge_a_faire``  : la file « À juger » (vrais appels et tests) de l'organisation ;
* ``juge_lire``     : le dossier d'un élément (transcription numérotée, outils, fiche, grille, consigne du juge) ;
* ``juge_ecrire``   : les verdicts, contrôlés par le schéma (``services/juge/verdicts``) : verdict fermé, réplique citée qui existe,
  preuve exacte obligatoire. Sinon REFUSÉ avec la raison. `/juger` traite la file par lots avec ces trois actions, `/analyser` lit les
  appels avec ``juge_lire``.

L'élément n'est lu et écrit que dans l'organisation de la personne. Un verdict écrit par Claude Code porte la mention d'exemption (D9).
Les deux portes passent par la même fonction (test des deux portes) ; le juge reste un geste de Claude Code, rien dans le chat de l'écran ne le déclenche.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.db import db_client
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.builder.cerveau import independance
from api.services.builder.consignes import consigne_juge
from api.services.juge import a_ameliorer, appels, file
from api.services.juge import verdicts as v


class _AFaire(BaseModel):
    workflow_id: int | None = Field(default=None, description="Only this agent's items.")


class _Lire(BaseModel):
    id: str = Field(min_length=1, max_length=200, description="An id from juge_a_faire.")


class _Ecrire(BaseModel):
    id: str = Field(min_length=1, max_length=200, description="An id from juge_a_faire.")
    verdicts: list[dict[str, Any]] = Field(
        min_length=1,
        max_length=40,
        description=(
            "One per criterion: {critere, verdict: reussi|rate|non_verifiable, replique: line number, "
            "preuve: exact quote of that line (the reason if non_verifiable), confiance: 0 to 1}."
        ),
    )


async def _a_faire(contexte: Contexte, p: _AFaire) -> dict[str, Any]:
    items = await file.lister(contexte.organisation_id, p.workflow_id)
    return {
        "ok": True,
        "total": len(items),
        "a_juger": [{k: i.get(k) for k in ("id", "type", "workflow_id", "run_id", "test", "le")} for i in items],
    }


async def _dossier(contexte: Contexte, item: dict[str, Any]) -> tuple[list[tuple[str, str]], list[dict], dict, list[str]]:
    """(lignes, outils, fiche, critères) d'un élément. Un run d'une autre organisation est introuvable."""
    if item["type"] == "test":
        return [(r, t) for r, t in item.get("lignes") or []], [], {}, list(item.get("criteres") or [])
    run, organisation = await db_client.get_workflow_run_with_context(
        int(item["run_id"]), organization_id=contexte.organisation_id
    )
    if run is None or organisation != contexte.organisation_id:
        raise ErreurAction("This call is not found in your organization.", "introuvable")
    dossier = appels.dossier_d_un_run(run)
    return dossier["lignes"], dossier["outils"], dossier["fiche"], await appels.grille()


async def _item(contexte: Contexte, identifiant: str) -> dict[str, Any]:
    item = await file.trouver(contexte.organisation_id, identifiant)
    if item is None:
        raise ErreurAction("Nothing to judge under this id: it was judged, or it is not in your organization.", "introuvable")
    return item


async def _lire(contexte: Contexte, p: _Lire) -> dict[str, Any]:
    item = await _item(contexte, p.id)
    lignes, outils, fiche, criteres = await _dossier(contexte, item)
    return {
        "ok": True,
        "id": item["id"],
        "type": item["type"],
        "consigne": await consigne_juge(),
        "criteres": criteres,
        "transcription": v.numerotee(lignes),
        "outils": outils,
        "fiche": fiche,
        "ecrire": "Send juge_ecrire with one verdict per criterion; the proof is an exact quote of the line you cite.",
    }


async def _ecrire(contexte: Contexte, p: _Ecrire) -> dict[str, Any]:
    item = await _item(contexte, p.id)
    lignes, _, _, criteres = await _dossier(contexte, item)
    try:
        verifies = v.verifier(p.verdicts, lignes, criteres)
    except v.VerdictRefuse as refus:
        raise ErreurAction(str(refus), "verdict_refuse") from None
    resultat = {
        "etat": "juge",
        "source": "claude_code",
        "juge_le": file.maintenant(),
        "verdicts": verifies,
        "reussi": v.reussi(verifies),
        "mention": independance.MENTION_CLAUDE_CODE,
    }
    if item["type"] == "appel":
        await appels.ecrire_dans_le_run(int(item["run_id"]), resultat)
    else:
        from api.services.builder import stock

        await stock.ecrire(
            contexte.organisation_id, f"{file.PREFIXE_VERDICT_TEST}{item['workflow_id']}:{item.get('test')}", resultat
        )
    # U12 + G1b : « À améliorer » se remplit comme sur clé d'API, par la même entrée unique (le module de la boucle).
    points = await a_ameliorer.signaler(contexte.organisation_id, item, verifies, lignes, "claude_code")
    await file.retirer(contexte.organisation_id, item["id"])
    return {"ok": True, "id": item["id"], "reussi": resultat["reussi"], "mention": resultat["mention"], "a_ameliorer": points}


for _nom, _desc, _param, _fonction, _ecriture in (
    ("juge_a_faire", "List what waits to be judged (real calls and tests) when the judge is set on Claude Code.", _AFaire, _a_faire, False),
    (
        "juge_lire",
        "Read one item to judge: numbered transcript, tools, final sheet, criteria and the judge's instruction.",
        _Lire,
        _lire,
        False,
    ),
    (
        "juge_ecrire",
        "Write the verdicts of one item (one per criterion, a closed verdict, a quoted line that exists, an exact proof); refused with the reason otherwise.",
        _Ecrire,
        _ecrire,
        True,
    ),
):
    enregistrer(
        Action(nom=_nom, description=_desc, parametres=_param, fonction=_fonction, ecriture=_ecriture, moteur=True, mcp=True, groupe="juge")
    )
