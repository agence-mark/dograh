"""[.mark] Partie 3, SA-L3b (05 § 12) : reprend les agents existants dans le modèle des branches.

La migration d'`alembic` (``c7a2e9d4b1f6``) pose déjà la branche « Principale » de chaque agent (la version en ligne devient la
principale, aucune version n'est réécrite). Ce script reprend ce que la migration ne peut pas faire :

- une « Principale » manquante (un agent créé entre la montée et ce script) est posée ;
- un déploiement progressif en cours (ligne ``MARK_DEPLOIEMENT:<agent>`` de ``organization_configurations``, SA-4) devient une
  branche « Déploiement vN » qui sert la nouvelle version avec sa part ; la principale reste sur l'ancienne version avec le reste.
  Un « retour à la vN » (part 0) devient la même chose avec 0 % : la principale reste épinglée sur la vN.

    python -m scripts.mark.migrer_branches                              # à blanc : dit ce qui serait fait
    python -m scripts.mark.migrer_branches --appliquer --sauvegarde copie.json

Idempotent : une seconde passe ne trouve plus de ligne à reprendre, et ne recrée pas une branche déjà posée.
⛔ Ne réécrit RIEN sans sauvegarde : ``--appliquer`` exige ``--sauvegarde`` et écrit d'abord, dans ce fichier, chaque ligne de
déploiement et l'état de la principale avant le changement. La ligne d'origine n'est retirée qu'une fois la branche posée, dans la
même transaction.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import text

PREFIXE = "MARK_DEPLOIEMENT:"


def nom_de_la_branche(numero: int | None, identifiant: int) -> str:
    return f"Déploiement v{numero}" if numero is not None else f"Déploiement #{identifiant}"


def lire_la_ligne(cle: str, valeur) -> tuple[int, int, int, int] | None:
    """(agent, nouvelle, precedente, pourcentage) d'une ligne lisible, sinon ``None`` (une ligne illisible n'est jamais touchée)."""
    if not cle.startswith(PREFIXE) or not isinstance(valeur, dict):
        return None
    agent = cle[len(PREFIXE):]
    nouvelle, precedente = valeur.get("nouvelle"), valeur.get("precedente")
    part = valeur.get("pourcentage", 0)
    if not agent.isdigit() or not isinstance(nouvelle, int) or not isinstance(precedente, int):
        return None
    if isinstance(part, bool) or not isinstance(part, int) or not 0 <= part <= 99:
        return None
    return int(agent), nouvelle, precedente, part


async def executer(session, appliquer: bool, sauvegarde: Path | None) -> list[dict]:
    """Une passe. Rend ce qui est (ou serait) fait : une entrée par principale posée, une par déploiement repris."""
    faits: list[dict] = []
    manquantes = (
        await session.execute(
            text(
                "SELECT w.id, w.organization_id FROM workflows w WHERE w.organization_id IS NOT NULL AND NOT EXISTS "
                "(SELECT 1 FROM workflow_branches b WHERE b.workflow_id = w.id AND b.est_principale) ORDER BY w.id"
            )
        )
    ).all()
    for agent, organisation in manquantes:
        faits.append({"genre": "principale", "agent": agent, "organisation": organisation})

    lignes = (
        await session.execute(
            text("SELECT id, organization_id, key, value FROM organization_configurations WHERE key LIKE :p ORDER BY id"),
            {"p": PREFIXE + "%"},
        )
    ).mappings().all()
    reprises: list[dict] = []
    for ligne in lignes:
        lue = lire_la_ligne(ligne["key"], ligne["value"])
        if lue is None:
            continue
        agent, nouvelle, precedente, part = lue
        appartient = (
            await session.execute(
                text("SELECT 1 FROM workflows WHERE id = :a AND organization_id = :o"),
                {"a": agent, "o": ligne["organization_id"]},
            )
        ).first()
        versions = {
            r[0]: r[1]
            for r in (
                await session.execute(
                    text("SELECT id, version_number FROM workflow_definitions WHERE workflow_id = :a AND id IN (:n, :p)"),
                    {"a": agent, "n": nouvelle, "p": precedente},
                )
            ).all()
        }
        if not appartient or nouvelle not in versions or precedente not in versions:
            continue  # une ligne qui ne correspond à aucun agent ou version de son organisation n'est jamais reprise
        reprises.append(
            {
                "genre": "deploiement",
                "ligne_id": ligne["id"],
                "organisation": ligne["organization_id"],
                "cle": ligne["key"],
                "valeur": ligne["value"],
                "agent": agent,
                "nouvelle": nouvelle,
                "precedente": precedente,
                "part": part,
                "nom": nom_de_la_branche(versions[nouvelle], nouvelle),
            }
        )
    faits.extend(reprises)
    if not appliquer or not faits:
        return faits
    if sauvegarde is None:
        raise ValueError("--appliquer exige --sauvegarde")
    avant = []
    for fait in reprises:
        principale = (
            await session.execute(
                text("SELECT id, part_trafic, head_definition_id FROM workflow_branches WHERE workflow_id = :a AND est_principale"),
                {"a": fait["agent"]},
            )
        ).mappings().first()
        avant.append({**fait, "principale_avant": dict(principale) if principale else None})
    # RV (point 10) : « x » = création exclusive, un fichier de sauvegarde qui existe déjà n'est jamais écrasé (l'état d'avant d'une autre passe).
    with sauvegarde.open("x", encoding="utf-8") as sortie:
        sortie.write(json.dumps({"faits": faits, "avant": avant}, ensure_ascii=False, indent=1, default=str))

    for fait in faits:
        if fait["genre"] == "principale":
            await _poser_la_principale(session, fait["organisation"], fait["agent"])
    for fait in reprises:
        await _poser_la_principale(session, fait["organisation"], fait["agent"])
        existe = (
            await session.execute(
                text("SELECT 1 FROM workflow_branches WHERE workflow_id = :a AND nom = :n"), {"a": fait["agent"], "n": fait["nom"]}
            )
        ).first()
        if not existe:
            await session.execute(
                text(
                    "INSERT INTO workflow_branches (organization_id, workflow_id, nom, est_principale, statut, part_trafic, "
                    "head_definition_id, base_definition_id, protegee) VALUES (:o, :a, :n, false, 'active', :p, :h, :b, false)"
                ),
                {"o": fait["organisation"], "a": fait["agent"], "n": fait["nom"], "p": fait["part"], "h": fait["nouvelle"], "b": fait["precedente"]},
            )
        await session.execute(
            text(
                "UPDATE workflow_branches SET part_trafic = :p, head_definition_id = :h "
                "WHERE workflow_id = :a AND organization_id = :o AND est_principale"
            ),
            {"p": 100 - fait["part"], "h": fait["precedente"], "a": fait["agent"], "o": fait["organisation"]},
        )
        await session.execute(
            text("DELETE FROM organization_configurations WHERE id = :i AND organization_id = :o"),
            {"i": fait["ligne_id"], "o": fait["organisation"]},
        )
    return faits


async def _poser_la_principale(session, organisation: int, agent: int) -> None:
    await session.execute(
        text(
            "INSERT INTO workflow_branches (organization_id, workflow_id, nom, est_principale, statut, part_trafic, protegee) "
            "SELECT :o, :a, 'Principale', true, 'active', 100, false WHERE NOT EXISTS "
            "(SELECT 1 FROM workflow_branches WHERE workflow_id = :a AND est_principale)"
        ),
        {"o": organisation, "a": agent},
    )


async def _principal(appliquer: bool, sauvegarde: Path | None) -> int:
    from api.db import db_client

    async with db_client.async_session() as session:
        faits = await executer(session, appliquer, sauvegarde)
        if appliquer:
            await session.commit()
    verbe = "repris" if appliquer else "à reprendre (à blanc)"
    for fait in faits:
        print(f"{verbe} : {fait['genre']} agent {fait['agent']}" + (f" -> {fait['nom']} à {fait['part']} %" if "nom" in fait else ""))
    if not faits:
        print("Rien à reprendre.")
    return 0


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("--appliquer", action="store_true", help="écrire (sinon à blanc)")
    analyseur.add_argument("--sauvegarde", type=Path, help="fichier où écrire l'état d'avant (obligatoire avec --appliquer)")
    arguments = analyseur.parse_args()
    if arguments.appliquer and arguments.sauvegarde is None:
        analyseur.error("--appliquer exige --sauvegarde")
    if arguments.appliquer and arguments.sauvegarde.exists():
        analyseur.error("--sauvegarde: ce fichier existe déjà, choisir un nouveau nom (il garde l'état d'avant d'une autre passe)")
    return asyncio.run(_principal(arguments.appliquer, arguments.sauvegarde))


if __name__ == "__main__":
    raise SystemExit(main())
