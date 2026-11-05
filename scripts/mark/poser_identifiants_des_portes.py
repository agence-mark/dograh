"""[.mark] L6+ (audit 01 A8) : migration DOUCE du graphe, l'identifiant stable de chaque porte.

Pour chaque liaison sans ``data.identifiant``, pose l'identifiant égal au nom que son libellé donne AUJOURD'HUI à la fonction
(``services/workflow/portes.py``) : rien ne change pour le modèle, les traces, les conditions ni les tests ; un renommage futur du
libellé ne changera plus le nom de la porte. Les anciens graphes non migrés se lisent comme avant (le nom vient du libellé).

    python -m scripts.mark.poser_identifiants_des_portes                       # à blanc : dit ce qui serait fait
    python -m scripts.mark.poser_identifiants_des_portes --appliquer --sauvegarde portes.json

Idempotent (une seconde passe ne trouve plus rien). ⛔ Ne réécrit RIEN sans sauvegarde : ``--appliquer`` exige ``--sauvegarde``
et y écrit d'abord le graphe d'origine de chaque ligne touchée (versions publiées, archivées et brouillons, et la copie héritée de
la table ``workflows``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from api.services.workflow.portes import poser_les_identifiants

# (table, colonne du graphe) : la version d'agent et la copie héritée de la table des agents.
CIBLES = (("workflow_definitions", "workflow_json"), ("workflows", "workflow_definition"))


def cible_sure(table: str) -> str:
    for t, colonne in CIBLES:
        if t == table:
            return colonne
    raise ValueError(table)


async def executer(session, appliquer: bool, sauvegarde: Path | None) -> list[dict]:
    """Rend les lignes touchées (``table``, ``id``, ``avant``, ``apres``, ``poses``)."""
    touchees: list[dict] = []
    for table, colonne in CIBLES:
        lignes = (
            await session.execute(text(f"SELECT id, {colonne} AS graphe FROM {table} WHERE {colonne} IS NOT NULL ORDER BY id"))  # noqa: S608
        ).mappings().all()
        for ligne in lignes:
            apres, poses = poser_les_identifiants(ligne["graphe"])
            if poses:
                touchees.append({"table": table, "id": ligne["id"], "avant": ligne["graphe"], "apres": apres, "poses": poses})
    if appliquer and touchees:
        if sauvegarde is None:
            raise ValueError("--appliquer exige --sauvegarde")
        # RV (point 10) : création exclusive, une sauvegarde qui existe déjà n'est jamais écrasée.
        with sauvegarde.open("x", encoding="utf-8") as sortie:
            sortie.write(json.dumps([{k: t[k] for k in ("table", "id", "avant")} for t in touchees], ensure_ascii=False))
        for t in touchees:
            colonne = cible_sure(t["table"])  # nom de table et de colonne pris dans CIBLES, jamais d'une donnée
            await session.execute(
                text(f"UPDATE {t['table']} SET {colonne} = CAST(:g AS json) WHERE id = :i"),  # noqa: S608
                {"g": json.dumps(t["apres"]), "i": t["id"]},
            )
    return touchees


async def main() -> None:
    lecteur = argparse.ArgumentParser()
    lecteur.add_argument("--appliquer", action="store_true")
    lecteur.add_argument("--sauvegarde", default=None)
    args = lecteur.parse_args()
    if args.appliquer and not args.sauvegarde:
        raise SystemExit("--appliquer exige --sauvegarde <fichier.json>")
    if args.appliquer and Path(args.sauvegarde).exists():
        raise SystemExit("--sauvegarde: ce fichier existe déjà, choisir un nouveau nom (il garde l'état d'avant d'une autre passe)")
    from api.db import db_client

    async with db_client.async_session() as session:
        touchees = await executer(session, args.appliquer, Path(args.sauvegarde) if args.sauvegarde else None)
        if args.appliquer:
            await session.commit()
    verbe = "posés" if args.appliquer else "à poser (à blanc)"
    print(f"{sum(t['poses'] for t in touchees)} identifiant(s) de porte {verbe} dans {len(touchees)} graphe(s)")


if __name__ == "__main__":
    asyncio.run(main())
