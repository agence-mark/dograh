"""[.mark] Builder partie 3, SA-17c : les trois gestes des contacts du portail, dans la base du client (migration 023).

Comportement repris de celui que le portail code déjà (``portes/contacts/contrat.ts`` et ``fictif.ts``) :

- ``fusionner`` : un doublon passe dans la fiche qu'il double. Appels, demandes, objets, vérifications, commentaires, numéros
  passent sur la fiche gardée, qui ne perd aucun champ et ne prend du doublon que ce qui lui manque (nom, prénom, société,
  mail et son « déclaré », adresse) ; « ne pas mémoriser » se cumule ; le doublon disparaît ; une autre fiche qui doutait du
  doublon doute désormais de la fiche gardée. Rejouable : un renvoi (``contact_fusion``) garde la trace, un second passage
  rend la même fiche sans rien changer. Une fiche sans doute n'est pas fusionnée.
- ``separer`` : « Ce n'est pas la même personne ». Le doute est levé, les deux fiches restent (rien n'est défait).
- ``memoriser`` : se coche et se décoche ; une fiche marquée « ne pas mémoriser » n'a plus aucun historique lu par l'agent
  (``dossier.lire_dossier``).

Une transaction courte, les deux fiches verrouillées dans l'ordre de leur identifiant. Chaque geste qui change quelque chose
écrit une ligne dans ``journal_modif`` (qui, quoi, quand), sans coordonnées de la personne.
"""

from __future__ import annotations

import json

import asyncpg

PROFONDEUR_MAX_DES_RENVOIS = 10


class ContactInconnu(LookupError):
    """No such contact in this client's database. Safe to show."""


class PasDeDoute(ValueError):
    """The contact has no doubt: nothing to merge. Safe to show."""


async def _journaliser(connexion, contact_id: int, champ: str, avant: dict, apres: dict, auteur: str) -> None:
    await connexion.execute(
        "INSERT INTO mark.journal_modif (table_nom, ligne_id, champ, avant, apres, auteur) "
        "VALUES ('contact', $1, $2, $3::jsonb, $4::jsonb, $5)",
        str(contact_id),
        champ,
        json.dumps(avant),
        json.dumps(apres),
        auteur[:200],
    )


async def lire_fiche(connexion: asyncpg.Connection, contact_id: int) -> dict | None:
    """La fiche telle que le portail la lit après un geste, ou ``None``."""
    c = await connexion.fetchrow(
        "SELECT id, nom, prenom, mail, mail_declare, nature, doublon_de, doublon_raison, ne_pas_memoriser "
        "FROM mark.contact WHERE id = $1",
        contact_id,
    )
    if c is None:
        return None
    telephones = [r["numero"] for r in await connexion.fetch(
        "SELECT numero FROM mark.telephone WHERE contact_id = $1 ORDER BY numero", contact_id)]
    nb_appels = await connexion.fetchval("SELECT count(*) FROM mark.appel WHERE contact_id = $1", contact_id)
    nb_commentaires = await connexion.fetchval(
        "SELECT count(*) FROM mark.commentaire WHERE contact_id = $1 AND supprime_le IS NULL", contact_id)
    return {
        "id": c["id"],
        "nom": c["nom"],
        "prenom": c["prenom"],
        "mail": c["mail"],
        "mail_declare": c["mail_declare"],
        "nature": c["nature"],
        "telephones": telephones,
        "doublon": {"avec": c["doublon_de"], "raison": c["doublon_raison"]} if c["doublon_de"] else None,
        "ne_pas_memoriser": c["ne_pas_memoriser"],
        "nb_appels": nb_appels,
        "nb_commentaires": nb_commentaires,
    }


async def _fiche_ou_inconnue(connexion, contact_id: int) -> dict:
    fiche = await lire_fiche(connexion, contact_id)
    if fiche is None:
        raise ContactInconnu(f"Contact {contact_id} not found.")
    return fiche


async def _garde_apres_renvois(connexion, ancien_id: int) -> int | None:
    """La fiche où est allée une fiche fusionnée (les renvois se suivent si la fiche gardée a été fusionnée à son tour)."""
    courant = ancien_id
    for _ in range(PROFONDEUR_MAX_DES_RENVOIS):
        suivant = await connexion.fetchval("SELECT garde_id FROM mark.contact_fusion WHERE ancien_id = $1", courant)
        if suivant is None:
            return None if courant == ancien_id else courant
        courant = suivant
    return courant


async def fusionner(connexion: asyncpg.Connection, contact_id: int, auteur: str) -> tuple[dict, bool, int]:
    """``(fiche gardée, déjà fait, id de la fiche fusionnée)``. ``ContactInconnu`` ; ``PasDeDoute``."""
    async with connexion.transaction():
        doublon = await connexion.fetchrow(
            "SELECT * FROM mark.contact WHERE id = $1 FOR UPDATE", contact_id)
        if doublon is None:
            garde_id = await _garde_apres_renvois(connexion, contact_id)
            if garde_id is None:
                raise ContactInconnu(f"Contact {contact_id} not found.")
            return await _fiche_ou_inconnue(connexion, garde_id), True, contact_id
        if doublon["doublon_de"] is None:
            raise PasDeDoute("This contact has no doubt: there is nothing to merge.")
        garde = await connexion.fetchrow(
            "SELECT * FROM mark.contact WHERE id = $1 FOR UPDATE", doublon["doublon_de"])
        if garde is None:  # le doute tombe avec la fiche (ON DELETE SET NULL), mais une course reste possible
            raise PasDeDoute("This contact has no doubt: there is nothing to merge.")
        garde_id = garde["id"]

        avant = {"doublon": contact_id, "garde_nom": garde["nom"], "garde_mail": garde["mail"]}
        # Jamais de champ écrasé : la fiche gardée ne prend du doublon que ce qui lui manque.
        mail_repris = garde["mail"] is None and doublon["mail"] is not None
        await connexion.execute(
            """
            UPDATE mark.contact SET
                nom = coalesce(nom, $2), prenom = coalesce(prenom, $3), societe_id = coalesce(societe_id, $4),
                mail = coalesce(mail, $5),
                mail_declare = CASE WHEN $6 THEN $7 ELSE mail_declare END,
                ne_pas_memoriser = ne_pas_memoriser OR $8,
                doublon_de = NULL, doublon_raison = NULL
            WHERE id = $1
            """,
            garde_id, doublon["nom"], doublon["prenom"], doublon["societe_id"], doublon["mail"],
            mail_repris, doublon["mail_declare"], doublon["ne_pas_memoriser"],
        )
        # Ce qui était rattaché au doublon passe sur la fiche gardée.
        for table in ("appel", "demande", "objet", "verification", "commentaire", "telephone"):
            await connexion.execute(
                f"UPDATE mark.{table} SET contact_id = $2 WHERE contact_id = $1", contact_id, garde_id)
        # L'adresse : reprise seulement si la fiche gardée n'en a aucune.
        if not await connexion.fetchval("SELECT 1 FROM mark.adresse WHERE contact_id = $1 LIMIT 1", garde_id):
            await connexion.execute("UPDATE mark.adresse SET contact_id = $2 WHERE contact_id = $1", contact_id, garde_id)
        # Une autre fiche qui doutait du doublon doute désormais de la fiche gardée.
        await connexion.execute(
            "UPDATE mark.contact SET doublon_de = $2 WHERE doublon_de = $1 AND id <> $2", contact_id, garde_id)
        await connexion.execute(
            "INSERT INTO mark.contact_fusion (ancien_id, garde_id, auteur) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            contact_id, garde_id, auteur[:200])
        await connexion.execute("DELETE FROM mark.contact WHERE id = $1", contact_id)
        await _journaliser(connexion, garde_id, "fusion", avant, {"garde": garde_id}, auteur)
        return await _fiche_ou_inconnue(connexion, garde_id), False, contact_id


async def separer(connexion: asyncpg.Connection, contact_id: int, auteur: str) -> dict:
    """Le doute est levé, les deux fiches restent. Sans doute : rien ne change."""
    async with connexion.transaction():
        c = await connexion.fetchrow("SELECT doublon_de, doublon_raison FROM mark.contact WHERE id = $1 FOR UPDATE", contact_id)
        if c is None:
            raise ContactInconnu(f"Contact {contact_id} not found.")
        if c["doublon_de"] is not None:
            await connexion.execute(
                "UPDATE mark.contact SET doublon_de = NULL, doublon_raison = NULL WHERE id = $1", contact_id)
            await _journaliser(connexion, contact_id, "doublon", {"avec": c["doublon_de"]}, {"avec": None}, auteur)
        return await _fiche_ou_inconnue(connexion, contact_id)


async def memoriser(connexion: asyncpg.Connection, contact_id: int, memoriser_: bool, auteur: str) -> dict:
    """``memoriser_`` faux : l'agent ne lit plus aucun historique de cette personne. Se coche et se décoche (idempotent)."""
    async with connexion.transaction():
        c = await connexion.fetchrow("SELECT ne_pas_memoriser FROM mark.contact WHERE id = $1 FOR UPDATE", contact_id)
        if c is None:
            raise ContactInconnu(f"Contact {contact_id} not found.")
        if c["ne_pas_memoriser"] == memoriser_:  # l'état voulu n'est pas l'état présent
            await connexion.execute(
                "UPDATE mark.contact SET ne_pas_memoriser = $2 WHERE id = $1", contact_id, not memoriser_)
            await _journaliser(
                connexion, contact_id, "ne_pas_memoriser",
                {"ne_pas_memoriser": c["ne_pas_memoriser"]}, {"ne_pas_memoriser": not memoriser_}, auteur)
        return await _fiche_ou_inconnue(connexion, contact_id)
