"""[.mark] SQL of a caller's record in the hub, and of his verification (chantier l-agent-collegue, L6).

The hub IS the client's database (H1, V4): a record is a contact, his numbers, his last address,
his requests and his appointments, in the common format of the hub (``OBJETS["dossier"]``):

    {id_externe, telephones, nom, prenom, mail, code_postal, commune, references,
     demandes: [{reference, type, statut, creee_le, resume}],
     rendez_vous: [{debut, fin, libelle, statut}]}

Read only after the code decided (``services/verification``); what the agent receives is cut
down there to the fields declared readable. ``ecrire_verifications`` writes each attempt, never
an answer (V6).
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

LIMITE = 5


async def contact_par_telephone(connexion: asyncpg.Connection, numero: str | None) -> int | None:
    if not numero:
        return None
    return await connexion.fetchval("SELECT contact_id FROM mark.telephone WHERE numero = $1", numero)


async def contact_par_reference(connexion: asyncpg.Connection, reference: str | None) -> int | None:
    """A request's number, as the client reads it (``demande.id``)."""
    chiffres = "".join(c for c in str(reference or "") if c.isdigit())
    if not chiffres or len(chiffres) > 18:
        return None
    return await connexion.fetchval(
        "SELECT contact_id FROM mark.demande WHERE id = $1", int(chiffres)
    )


async def lire_dossier(connexion: asyncpg.Connection, contact_id: int) -> dict | None:
    contact = await connexion.fetchrow(
        "SELECT id, nom, prenom, mail FROM mark.contact WHERE id = $1", contact_id
    )
    if contact is None:
        return None
    telephones = [
        r["numero"]
        for r in await connexion.fetch(
            "SELECT numero FROM mark.telephone WHERE contact_id = $1 ORDER BY numero", contact_id
        )
    ]
    adresse = await connexion.fetchrow(
        "SELECT code_postal, commune FROM mark.adresse WHERE contact_id = $1 ORDER BY id DESC LIMIT 1",
        contact_id,
    )
    demandes = await connexion.fetch(
        """
        SELECT d.id, coalesce(t.libelle, d.type) AS type, coalesce(s.libelle, d.statut) AS statut,
               d.creee_le, d.resume
        FROM mark.demande d
        LEFT JOIN mark.liste_valeur t ON t.liste = 'type_demande' AND t.code = d.type
        LEFT JOIN mark.liste_valeur s ON s.liste = 'statut_demande' AND s.code = d.statut
        WHERE d.contact_id = $1
        ORDER BY d.creee_le DESC
        """,
        contact_id,
    )
    rendez_vous = await connexion.fetch(
        """
        SELECT r.debut, r.fin, coalesce(tr.libelle, td.libelle, d.type) AS libelle,
               coalesce(s.libelle, r.statut) AS statut
        FROM mark.rendez_vous r
        JOIN mark.demande d ON d.id = r.demande_id
        LEFT JOIN mark.type_rendez_vous tr ON tr.code = r.type_code AND tr.site_id IS NULL
        LEFT JOIN mark.liste_valeur td ON td.liste = 'type_demande' AND td.code = d.type
        LEFT JOIN mark.liste_valeur s ON s.liste = 'statut_rdv' AND s.code = r.statut
        WHERE d.contact_id = $1 AND r.fin >= now() - interval '1 day'
        ORDER BY r.debut
        LIMIT $2
        """,
        contact_id,
        LIMITE,
    )
    return {
        "id_externe": str(contact["id"]),
        "telephones": telephones,
        "nom": contact["nom"],
        "prenom": contact["prenom"],
        "mail": contact["mail"],
        "code_postal": (adresse["code_postal"] if adresse else None),
        "commune": (adresse["commune"] if adresse else None),
        "references": [str(d["id"]) for d in demandes],
        "demandes": [
            {"reference": str(d["id"]), "type": d["type"], "statut": d["statut"],
             "creee_le": d["creee_le"].isoformat(), "resume": d["resume"]}
            for d in demandes[:LIMITE]
        ],
        "rendez_vous": [
            {"debut": r["debut"].isoformat(), "fin": r["fin"].isoformat(),
             "libelle": r["libelle"], "statut": r["statut"]}
            for r in rendez_vous
        ],
    }


def _moment(iso) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if isinstance(iso, str) else None
    except ValueError:
        return None


async def ecrire_verifications(
    connexion: asyncpg.Connection, appel_id: int | None, tentatives: list[dict]
) -> int:
    """V6: one row per attempt, written once per call (a replay writes nothing twice)."""
    if not appel_id or not tentatives:
        return 0
    if await connexion.fetchval("SELECT count(*) FROM mark.verification WHERE appel_id = $1", appel_id):
        return 0
    ecrites = 0
    async with connexion.transaction():
        for t in tentatives:
            if not isinstance(t, dict) or t.get("resultat") not in ("verifie", "insuffisant", "echec", "bloque"):
                continue
            source = str(t.get("source") or "hub")
            contact_id = None
            if source == "hub" and str(t.get("dossier") or "").isdigit():
                contact_id = await connexion.fetchval(
                    "SELECT id FROM mark.contact WHERE id = $1", int(t["dossier"])
                )
            await connexion.execute(
                "INSERT INTO mark.verification (appel_id, contact_id, source, dossier_externe, "
                "facteurs_essayes, facteurs_reussis, resultat, le) VALUES ($1, $2, $3, $4, $5, $6, $7, coalesce($8, now()))",
                appel_id,
                contact_id,
                source,
                None if source == "hub" else (str(t.get("dossier"))[:200] if t.get("dossier") else None),
                [f for f in t.get("facteurs_essayes") or [] if f in ("numero", "question", "code_sms")],
                [f for f in t.get("facteurs_reussis") or [] if f in ("numero", "question", "code_sms")],
                t["resultat"],
                _moment(t.get("le")),
            )
            ecrites += 1
    return ecrites
