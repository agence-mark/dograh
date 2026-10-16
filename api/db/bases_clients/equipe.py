"""[.mark] The team and the routing in the client's database (theme « Team and routing », L3).

People (``personne``) and subjects (``sujet``, ``personne_sujet``): who receives what.
Read by the after-call (L4) to know who gets the mail of a request.

⛔ A person or a subject removed on screen is DEACTIVATED, never deleted: requests and
call-backs refer to them.
"""

from __future__ import annotations

import asyncpg

from api.schemas.base_client import Equipe, Personne, Sujet


async def _auteur(connexion: asyncpg.Connection, auteur: str) -> None:
    await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])


async def _table_des_lieux_existe(connexion: asyncpg.Connection) -> bool:
    """[.mark] Lot 5: a client database still at version 14 has no ``personne_site`` (015): the
    places are then the legacy column only, and a call never fails in the gap between the
    deployment and « Upgrade »."""
    return bool(await connexion.fetchval("SELECT to_regclass('mark.personne_site') IS NOT NULL"))


async def lire_equipe(connexion: asyncpg.Connection) -> Equipe:
    sites = {
        r["id"]: r["cle"]
        for r in await connexion.fetch("SELECT id, cle FROM mark.site")
    }
    # [.mark] Lot 5 (M5): the places of each person -- the union of the legacy column (first) and of
    # ``personne_site`` (015, when the database has it).
    autres_lieux: dict[int, list[str]] = {}
    if await _table_des_lieux_existe(connexion):
        for lien in await connexion.fetch(
            "SELECT personne_id, site_id FROM mark.personne_site ORDER BY personne_id, site_id"
        ):
            if sites.get(lien["site_id"]):
                autres_lieux.setdefault(lien["personne_id"], []).append(sites[lien["site_id"]])
    personnes = await connexion.fetch(
        "SELECT * FROM mark.personne WHERE cle IS NOT NULL ORDER BY id"
    )
    cles = {p["id"]: p["cle"] for p in personnes}
    # A subject removed on screen is deactivated: it is no longer shown (re-adding its code revives it).
    sujets = await connexion.fetch("SELECT * FROM mark.sujet WHERE actif ORDER BY id")
    liens = await connexion.fetch(
        "SELECT * FROM mark.personne_sujet ORDER BY sujet_id, priorite, personne_id"
    )
    # l-agent-collegue, L4 (H7): each person's agendas, one line of lien_externe per software.
    from api.db.bases_clients.hub import agendas_par_personne

    agendas = await agendas_par_personne(connexion)
    return Equipe(
        personnes=[
            Personne(
                cle=p["cle"],
                prenom=p["prenom"],
                nom=p["nom"],
                role=p["role"],
                mail=p["mail"],
                telephone=p["telephone"],
                etablissements=_lieux_de(sites.get(p["site_id"]), autres_lieux.get(p["id"], [])),
                destinataire_defaut=p["destinataire_defaut"],
                actif=p["actif"],
                description=p.get("description"),
                divulguer_telephone=bool(p.get("divulguer_telephone")),
                divulguer_mail=bool(p.get("divulguer_mail")),
                joignable_par_transfert=bool(p.get("joignable_par_transfert")),
                agendas=agendas.get(p["id"]) or None,
            )
            for p in personnes
        ],
        sujets=[
            Sujet(
                code=s["code"],
                libelle=s["libelle"],
                mots_declencheurs=list(s["mots_declencheurs"] or []),
                urgent=s["urgent"],
                actif=s["actif"],
                destinataires=[
                    cles[lien["personne_id"]]
                    for lien in liens
                    if lien["sujet_id"] == s["id"] and lien["personne_id"] in cles
                ],
            )
            for s in sujets
        ],
    )


def _lieux_de(premier: str | None, autres: list[str]) -> list[str]:
    """The legacy place first, then the others of ``personne_site``, without a duplicate."""
    lieux = [premier] if premier else []
    return lieux + [lieu for lieu in autres if lieu not in lieux]


class EtablissementInconnu(ValueError):
    pass


async def ecrire_equipe(
    connexion: asyncpg.Connection, equipe: Equipe, auteur: str
) -> None:
    async with connexion.transaction():
        await _auteur(connexion, auteur)
        sites = {
            r["cle"]: r["id"]
            for r in await connexion.fetch(
                "SELECT id, cle FROM mark.site WHERE cle IS NOT NULL AND actif"
            )
        }
        ids: dict[str, int] = {}
        table_des_lieux = await _table_des_lieux_existe(connexion)
        for p in equipe.personnes:
            for lieu in p.etablissements:
                if lieu not in sites:
                    raise EtablissementInconnu(f"{p.prenom}: unknown establishment « {lieu} ».")
            ids[p.cle] = await connexion.fetchval(
                """
                INSERT INTO mark.personne (cle, site_id, prenom, nom, role, mail, telephone, destinataire_defaut, actif,
                    description, divulguer_telephone, divulguer_mail, joignable_par_transfert)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (cle) DO UPDATE SET site_id = EXCLUDED.site_id, prenom = EXCLUDED.prenom,
                    nom = EXCLUDED.nom, role = EXCLUDED.role, mail = EXCLUDED.mail,
                    telephone = EXCLUDED.telephone, destinataire_defaut = EXCLUDED.destinataire_defaut,
                    actif = EXCLUDED.actif, description = EXCLUDED.description,
                    divulguer_telephone = EXCLUDED.divulguer_telephone, divulguer_mail = EXCLUDED.divulguer_mail,
                    joignable_par_transfert = EXCLUDED.joignable_par_transfert
                RETURNING id
                """,
                p.cle,
                sites.get(p.etablissements[0]) if p.etablissements else None,  # the first place (legacy column)
                p.prenom,
                p.nom,
                p.role,
                p.mail,
                p.telephone,
                p.destinataire_defaut,
                p.actif,
                p.description,
                p.divulguer_telephone,
                p.divulguer_mail,
                p.joignable_par_transfert,
            )
            # [.mark] Lot 5 (M5): every place of the person, in ``personne_site``. Several places on a
            # database that does not have the table yet fail here (the route answers « Upgrade »);
            # one place or none loses nothing, the legacy column above holds it.
            if table_des_lieux or len(p.etablissements) > 1:
                voulus = [sites[lieu] for lieu in p.etablissements]
                await connexion.execute(
                    "DELETE FROM mark.personne_site WHERE personne_id = $1 AND NOT (site_id = ANY($2::bigint[]))",
                    ids[p.cle],
                    voulus,
                )
                for site_id in voulus:
                    await connexion.execute(
                        "INSERT INTO mark.personne_site (personne_id, site_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        ids[p.cle],
                        site_id,
                    )
        await connexion.execute(
            "UPDATE mark.personne SET actif = false WHERE actif AND cle IS NOT NULL AND NOT (cle = ANY($1::text[]))",
            list(ids),
        )
        # l-agent-collegue, L4 (H7): the agendas sent (None: left as they are).
        from api.db.bases_clients.hub import ecrire_agendas

        await ecrire_agendas(
            connexion,
            {ids[p.cle]: p.agendas for p in equipe.personnes if p.agendas is not None},
        )
        codes: list[str] = []
        for s in equipe.sujets:
            sujet_id = await connexion.fetchval(
                """
                INSERT INTO mark.sujet (code, libelle, mots_declencheurs, urgent, actif)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (code) DO UPDATE SET libelle = EXCLUDED.libelle,
                    mots_declencheurs = EXCLUDED.mots_declencheurs, urgent = EXCLUDED.urgent,
                    actif = EXCLUDED.actif
                RETURNING id
                """,
                s.code,
                s.libelle,
                s.mots_declencheurs,
                s.urgent,
                s.actif,
            )
            codes.append(s.code)
            await connexion.execute(
                "DELETE FROM mark.personne_sujet WHERE sujet_id = $1 AND NOT (personne_id = ANY($2::bigint[]))",
                sujet_id,
                [ids[cle] for cle in s.destinataires],
            )
            for priorite, cle in enumerate(s.destinataires, start=1):
                await connexion.execute(
                    "INSERT INTO mark.personne_sujet (personne_id, sujet_id, priorite) VALUES ($1, $2, $3) "
                    "ON CONFLICT (personne_id, sujet_id) DO UPDATE SET priorite = EXCLUDED.priorite",
                    ids[cle],
                    sujet_id,
                    priorite,
                )
        await connexion.execute(
            "UPDATE mark.sujet SET actif = false WHERE actif AND NOT (code = ANY($1::text[]))",
            codes,
        )
