"""[.mark] Lot F7 : les objets de l'agent dans la base du client (migration 019).

Lecture de tous les objets (ce que lit un appel, ce que montre l'écran), écriture d'UN objet à la fois
(jamais le catalogue entier), suppression, et l'utilisation calculée par Dograh (``objet_agent_utilisation``,
lue par ``v_portail_objets``). L'auteur est posé dans ``mark.auteur`` : l'historique (D111) dit qui a écrit.

La validation du type est dans la base (D114) : une valeur refusée remonte en ``ObjetRefuse`` avec le message
de la base, qui ne contient que des libellés et la valeur saisie (jamais une donnée d'un appelant).
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import asyncpg

from api.schemas.objets_agent import ColonneObjet, LigneObjet, ObjetAgent, ObjetEnvoye


class ObjetRefuse(ValueError):
    """The database refused the object (type, empty line, unknown establishment). Safe to show."""


class ObjetInconnu(LookupError):
    """No object with this identifier in this database."""


class NomPris(ValueError):
    """Another object already has this technical name. Safe to show."""


async def objets_presents(connexion: asyncpg.Connection) -> bool:
    """A database before the 019 has no objects (and is not an error)."""
    return bool(await connexion.fetchval("SELECT to_regclass('mark.objet_agent') IS NOT NULL"))


def _cellules(brut) -> dict:
    valeurs = json.loads(brut) if isinstance(brut, str) else (brut or {})
    return valeurs if isinstance(valeurs, dict) else {}


async def lire_objets(connexion: asyncpg.Connection) -> list[ObjetAgent]:
    """Every object, its columns and its lines, in display order. None before the 019."""
    if not await objets_presents(connexion):
        return []
    objets = await connexion.fetch(
        "SELECT o.id, o.nom, o.libelle, o.description, o.forme, o.type, o.valeur, s.cle AS etablissement, "
        "o.modifie_le FROM mark.objet_agent o LEFT JOIN mark.site s ON s.id = o.site_id ORDER BY o.libelle, o.id"
    )
    colonnes = await connexion.fetch(
        "SELECT id, objet_id, libelle, type, ordre, pose_par FROM mark.objet_agent_colonne ORDER BY objet_id, ordre, id"
    )
    lignes = await connexion.fetch(
        "SELECT id, objet_id, ordre, valeurs FROM mark.objet_agent_ligne ORDER BY objet_id, ordre, id"
    )
    par_objet: dict[int, list] = {}
    libelles: dict[int, str] = {}
    for c in colonnes:
        par_objet.setdefault(c["objet_id"], []).append(c)
        libelles[c["id"]] = c["libelle"]
    lignes_par_objet: dict[int, list] = {}
    for ligne in lignes:
        lignes_par_objet.setdefault(ligne["objet_id"], []).append(ligne)
    sortie: list[ObjetAgent] = []
    for o in objets:
        sortie.append(
            ObjetAgent(
                id=o["id"],
                nom=o["nom"],
                libelle=o["libelle"],
                description=o["description"],
                forme=o["forme"],
                type=o["type"],
                valeur=o["valeur"],
                etablissement=o["etablissement"],
                modifie_le=o["modifie_le"],
                colonnes=[
                    ColonneObjet(
                        id=c["id"], libelle=c["libelle"], type=c["type"], ordre=c["ordre"], pose_par=c["pose_par"]
                    )
                    for c in par_objet.get(o["id"], [])
                ],
                lignes=[
                    LigneObjet(
                        id=ligne["id"],
                        ordre=ligne["ordre"],
                        valeurs={
                            libelles[int(k)]: v
                            for k, v in _cellules(ligne["valeurs"]).items()
                            if k.isdigit() and int(k) in libelles and isinstance(v, str)
                        },
                    )
                    for ligne in lignes_par_objet.get(o["id"], [])
                ],
            )
        )
    return sortie


async def _site_de(connexion: asyncpg.Connection, etablissement: str | None) -> int | None:
    if not etablissement:
        return None
    site = await connexion.fetchval("SELECT id FROM mark.site WHERE cle = $1", etablissement)
    if site is None:
        raise ObjetRefuse(f"« {etablissement} » is not an establishment of this database.")
    return site


def _message(erreur: Exception) -> str:
    """The database's own message (« objet_agent_ligne : … »), without the table's name."""
    texte = str(getattr(erreur, "message", None) or erreur)
    return texte.split(" : ", 1)[1] if " : " in texte else texte


async def ecrire_objet(
    connexion: asyncpg.Connection, objet: ObjetEnvoye, auteur: str, objet_id: int | None = None
) -> int:
    """Create (``objet_id`` absent) or rewrite ONE object, in one transaction: its columns and lines are
    what is sent (with an id: changed; without: added; not sent: removed). Returns its identifier."""
    try:
        async with connexion.transaction():
            await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])
            site = await _site_de(connexion, objet.etablissement)
            valeur = objet.valeur if objet.forme == "valeur" else None
            if objet_id is None:
                objet_id = await connexion.fetchval(
                    "INSERT INTO mark.objet_agent (nom, libelle, description, forme, type, valeur, site_id) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
                    objet.nom, objet.libelle, objet.description, objet.forme,
                    objet.type if objet.forme == "valeur" else None, valeur, site,
                )
            else:
                change = await connexion.fetchval(
                    "UPDATE mark.objet_agent SET nom = $2, libelle = $3, description = $4, forme = $5, type = $6, "
                    "valeur = $7, site_id = $8 WHERE id = $1 RETURNING id",
                    objet_id, objet.nom, objet.libelle, objet.description, objet.forme,
                    objet.type if objet.forme == "valeur" else None, valeur, site,
                )
                if change is None:
                    raise ObjetInconnu(objet_id)
            if objet.forme == "liste":
                await _ecrire_colonnes_et_lignes(connexion, objet_id, objet)
            return objet_id
    except asyncpg.UniqueViolationError:
        raise NomPris(
            f"Another object is already called « {objet.nom} », or two columns have the same label."
        ) from None
    except (asyncpg.CheckViolationError, asyncpg.RaiseError, asyncpg.InsufficientPrivilegeError) as erreur:
        raise ObjetRefuse(_message(erreur)) from None


async def _ecrire_colonnes_et_lignes(connexion: asyncpg.Connection, objet_id: int, objet: ObjetEnvoye) -> None:
    gardees = [c.id for c in objet.colonnes if c.id is not None]
    # Les cellules d'une colonne retirée partent avec elle (déclencheur de la 019).
    await connexion.execute(
        "DELETE FROM mark.objet_agent_colonne WHERE objet_id = $1 AND NOT (id = ANY($2::bigint[]))",
        objet_id, gardees,
    )
    ids: dict[str, int] = {}
    for colonne in objet.colonnes:
        if colonne.id is None:
            ids[colonne.libelle] = await connexion.fetchval(
                "INSERT INTO mark.objet_agent_colonne (objet_id, libelle, type, ordre, pose_par) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                objet_id, colonne.libelle, colonne.type, colonne.ordre, colonne.pose_par,
            )
        else:
            change = await connexion.fetchval(
                "UPDATE mark.objet_agent_colonne SET libelle = $3, type = $4, ordre = $5, pose_par = $6 "
                "WHERE id = $1 AND objet_id = $2 RETURNING id",
                colonne.id, objet_id, colonne.libelle, colonne.type, colonne.ordre, colonne.pose_par,
            )
            if change is None:
                raise ObjetRefuse(f"Column {colonne.id} is not a column of this object.")
            ids[colonne.libelle] = colonne.id
    gardees_l = [ligne.id for ligne in objet.lignes if ligne.id is not None]
    await connexion.execute(
        "DELETE FROM mark.objet_agent_ligne WHERE objet_id = $1 AND NOT (id = ANY($2::bigint[]))",
        objet_id, gardees_l,
    )
    for ligne in objet.lignes:
        inconnues = [libelle for libelle in ligne.valeurs if libelle not in ids]
        if inconnues:
            raise ObjetRefuse(f"« {inconnues[0]} » is not a column of this object.")
        cellules = json.dumps({str(ids[libelle]): v for libelle, v in ligne.valeurs.items()})
        if ligne.id is None:
            await connexion.execute(
                "INSERT INTO mark.objet_agent_ligne (objet_id, ordre, valeurs) VALUES ($1, $2, $3::jsonb)",
                objet_id, ligne.ordre, cellules,
            )
        else:
            change = await connexion.fetchval(
                "UPDATE mark.objet_agent_ligne SET ordre = $3, valeurs = $4::jsonb WHERE id = $1 AND objet_id = $2 "
                "RETURNING id",
                ligne.id, objet_id, ligne.ordre, cellules,
            )
            if change is None:
                raise ObjetRefuse(f"Line {ligne.id} is not a line of this object.")


async def supprimer_objet(connexion: asyncpg.Connection, objet_id: int, auteur: str) -> None:
    """The object, its columns and lines go; its history stays (D111)."""
    async with connexion.transaction():
        await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])
        parti = await connexion.fetchval("DELETE FROM mark.objet_agent WHERE id = $1 RETURNING id", objet_id)
    if parti is None:
        raise ObjetInconnu(objet_id)


async def ecrire_utilisation(
    connexion: asyncpg.Connection, utilisation: dict[str, Iterable[int]]
) -> None:
    """Which agents read which object (by name; agents by their Dograh identifier). Computed by Dograh
    (D118), never typed. An agent the database does not know yet is left out (the portal only shows
    agents attached to it, which the database knows). Before the 019: nothing."""
    if not await objets_presents(connexion):
        return
    async with connexion.transaction():
        await connexion.execute("DELETE FROM mark.objet_agent_utilisation")
        for nom, agents in utilisation.items():
            liste = sorted({int(a) for a in agents})
            if not liste:
                continue
            await connexion.execute(
                "INSERT INTO mark.objet_agent_utilisation (objet_id, agent_id) "
                "SELECT o.id, a.id FROM mark.objet_agent o JOIN mark.agent a ON a.dograh_workflow_id = ANY($2::integer[]) "
                "WHERE o.nom = $1 ON CONFLICT DO NOTHING",
                nom, liste,
            )


async def lire_plafond(connexion: asyncpg.Connection) -> int | None:
    """The ceiling the database applies (D112). ``None`` before the 019."""
    if not await objets_presents(connexion):
        return None
    return await connexion.fetchval("SELECT plafond_caracteres FROM mark.objet_agent_reglage WHERE id = 1")


async def ecrire_plafond(connexion: asyncpg.Connection, plafond: int, auteur: str) -> None:
    """Set the ceiling. An object already over it stays as it is until it is next written (then refused)."""
    async with connexion.transaction():
        await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])
        # The row is written by the 019 itself: always there.
        await connexion.execute("UPDATE mark.objet_agent_reglage SET plafond_caracteres = $1 WHERE id = 1", plafond)
