"""[.mark] RA-B (R5, audit 11 § 4) : retire le délai caché de la panne (``panne.delai_modele_s``) des configurations.

Le réglage visible est ``delai_garde_modele_s`` (Models, sous le cerveau). L'ancien ``panne.delai_modele_s`` n'avait pas
d'écran et n'était lu qu'à défaut du nouveau : on le reporte dans ``delai_garde_modele_s`` quand l'agent n'a pas encore
le sien (la valeur ne change donc pour personne), puis on le retire.

    python -m scripts.mark.retirer_delai_modele_panne                       # à blanc : dit ce qui serait fait
    python -m scripts.mark.retirer_delai_modele_panne --appliquer --sauvegarde copie.json

Idempotent (une seconde passe ne trouve plus rien). ⛔ Ne réécrit RIEN sans sauvegarde : ``--appliquer`` exige
``--sauvegarde`` et écrit d'abord, dans ce fichier, la configuration d'origine de chaque ligne touchée.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path

from sqlalchemy import text

TABLES = ("workflow_definitions", "workflows")
BORNE_BASSE, BORNE_HAUTE = 1.0, 30.0  # bornes de ``delai_garde_modele_s``


def migrer(configuration: dict | None) -> tuple[dict | None, bool]:
    """La configuration sans le délai caché, et si elle a changé. Ne modifie pas l'argument."""
    if not isinstance(configuration, dict):
        return configuration, False
    panne = configuration.get("panne")
    if not isinstance(panne, dict) or "delai_modele_s" not in panne:
        return configuration, False
    neuve = copy.deepcopy(configuration)
    ancien = neuve["panne"].pop("delai_modele_s")
    deja = neuve.get("delai_garde_modele_s")
    valeur_valide = isinstance(ancien, (int, float)) and not isinstance(ancien, bool)
    if deja is None and valeur_valide and ancien > 0:
        # Reporté dans les bornes du nouveau réglage (l'ancien admettait 0,1 s).
        neuve["delai_garde_modele_s"] = float(min(max(ancien, BORNE_BASSE), BORNE_HAUTE))
    return neuve, True


async def executer(session, appliquer: bool, sauvegarde: Path | None) -> list[dict]:
    """Passe sur les deux tables. Rend les lignes touchées (``table``, ``id``, ``avant``, ``apres``)."""
    touchees: list[dict] = []
    for table in TABLES:
        lignes = (
            await session.execute(
                text(
                    f"SELECT id, workflow_configurations FROM {table} "  # noqa: S608 -- nom de table fixe ci-dessus
                    "WHERE workflow_configurations::jsonb -> 'panne' ? 'delai_modele_s' ORDER BY id"
                )
            )
        ).mappings().all()
        for ligne in lignes:
            apres, change = migrer(ligne["workflow_configurations"])
            if change:
                touchees.append(
                    {"table": table, "id": ligne["id"], "avant": ligne["workflow_configurations"], "apres": apres}
                )
    if appliquer and touchees:
        if sauvegarde is None:
            raise ValueError("--appliquer exige --sauvegarde")
        # RV (point 10) : création exclusive, une sauvegarde qui existe déjà n'est jamais écrasée.
        with sauvegarde.open("x", encoding="utf-8") as sortie:
            sortie.write(json.dumps(touchees, ensure_ascii=False, indent=1))
        for t in touchees:
            await session.execute(
                text(f"UPDATE {table_sure(t['table'])} SET workflow_configurations = CAST(:c AS json) WHERE id = :i"),  # noqa: S608
                {"c": json.dumps(t["apres"]), "i": t["id"]},
            )
    return touchees


def table_sure(nom: str) -> str:
    if nom not in TABLES:
        raise ValueError(nom)
    return nom


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
    verbe = "retiré" if args.appliquer else "à retirer (à blanc)"
    print(f"{len(touchees)} configuration(s) : délai caché {verbe}")


if __name__ == "__main__":
    asyncio.run(main())
