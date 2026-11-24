"""[.mark] Module Restauration, lot 13 (F7 et M7) : ce que les onglets Remises et Réglages restaurant (Envois) du fork lisent et écrivent.

Même règle que le reste du module : seuls les fichiers ``restauration*.py`` ouvrent une requête sur les tables ``resto_*``.

- les remises (``resto_remise``) : la règle telle que l'écran la compose, ses résultats d'après les commandes gardées (jamais une estimation), le passage d'un
  état à l'autre (brouillon, active, suspendue, terminée). Une remise de la caisse ou de .mark ne se modifie ni ne se supprime ici ;
- les envois après une action (``resto_envoi``, lot 7) : un SMS par déclencheur, éteint par défaut, un seul endroit de configuration (T-20).

L'auteur et la source vont au journal par ``poser_session`` (déclencheurs de la 028).
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from api.db.bases_clients.restauration_commun import maintenant, poser_session, json_lu
from api.db.bases_clients.restauration_remise import MECANISMES
from api.db.bases_clients.restauration_remise_offre import compter_les_offres

TRANSITIONS = {"brouillon": ("active",), "active": ("suspendue", "terminee"), "suspendue": ("active", "terminee"), "terminee": ()}
MAX_REMISES = 200

# Les envois : le déclencheur, les trous que le code remplit (jamais le modèle) et le texte par défaut proposé (éteint tant qu'on ne l'allume pas).
ENVOIS: dict[str, dict[str, Any]] = {
    "commande_enregistree": {"trous": ["prenom", "numero_court", "heure"], "defaut": "Bonjour {{prenom}}, votre commande {{numero_court}} est prête à {{heure}}."},
    "reservation_enregistree": {"trous": ["prenom", "quand", "personnes"], "defaut": "Bonjour {{prenom}}, votre réservation pour {{personnes}} est confirmée {{quand}}."},
    "reservation_modifiee": {"trous": ["prenom", "quand", "personnes"], "defaut": "Bonjour {{prenom}}, votre réservation est modifiée : {{personnes}} personnes, {{quand}}."},
    "reservation_annulee": {"trous": ["prenom", "quand", "personnes"], "defaut": "Bonjour {{prenom}}, votre réservation {{quand}} est annulée."},
    "carte": {"trous": [], "defaut": "Voici notre carte : (collez ici le lien de votre carte)."},
    "avis": {"trous": [], "defaut": "Merci de votre appel ! Votre avis nous aide : (collez ici le lien de votre avis)."},
    "heure_changee": {"trous": ["prenom", "numero_court", "heure"], "defaut": "Bonjour {{prenom}}, l'heure de votre commande {{numero_court}} change : {{heure}}."},
}


class RemiseRefusee(ValueError):
    """``code`` fermé : ``introuvable``, ``lecture_seule`` (remise de la caisse ou de .mark), ``transition``, ``trop_nombreuses``."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _rendue(r: asyncpg.Record, resultats: dict[tuple[str, str], tuple[int, int, int]], offres: dict[int, tuple[int, int]] | None = None) -> dict[str, Any]:
    cle_nom = (r["ref_caisse"] or "", (r["nom"] or "").strip().lower())
    n = ca = remise = 0
    if r["etat"] != "brouillon":
        for (ref, nom), (nb, chiffre, moins) in resultats.items():
            if (r["ref_caisse"] and ref == r["ref_caisse"]) or (nom == cle_nom[1] and (not r["ref_caisse"] or ref == "")):
                n, ca, remise = n + nb, ca + chiffre, remise + moins
    return {
        "id": r["id"], "nom": r["nom"], "mecanisme": r["mecanisme"], "declencheur": json_lu(r["declencheur"]) or {}, "effet": json_lu(r["effet"]) or {},
        "perimetre": json_lu(r["perimetre"]) or {}, "cumul": r["cumul"], "limite": json_lu(r["limite"]), "phrase": r["phrase"], "moment": json_lu(r["moment"]),
        "debut": r["debut"], "fin": r["fin"], "etat": r["etat"], "ref_caisse": r["ref_caisse"], "source": r["source"], "maj_le": r["maj_le"],
        "utilisations": n, "ca_centimes": ca, "remise_centimes": remise,
        # M38 : les offres dites par l'agent et celles qui se sont retrouvées sur une commande (migration 034).
        "dite": (offres or {}).get(r["id"], (0, 0))[0], "acceptee": (offres or {}).get(r["id"], (0, 0))[1],
    }


async def remises_pour_l_ecran(connexion: asyncpg.Connection, etablissement_id: int) -> list[dict[str, Any]]:
    """Les remises de l'établissement, celles qui servent d'abord, avec ce qu'elles ont fait sur les commandes gardées (ni annulées, ni refusées, ni en échec)."""
    groupes = await connexion.fetch(
        "SELECT coalesce(r.value ->> 'ref_caisse', '') AS ref, coalesce(r.value ->> 'nom', '') AS nom, count(*)::int AS n, coalesce(sum(c.total), 0)::bigint AS ca, "
        "coalesce(sum(CASE WHEN r.value ->> 'montant' ~ '^-?[0-9]+$' THEN abs((r.value ->> 'montant')::bigint) ELSE 0 END), 0)::bigint AS remise "
        "FROM mark.resto_commande c, LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(c.remises) = 'array' THEN c.remises ELSE '[]'::jsonb END) AS r(value) "
        "WHERE c.site_id = $1 AND c.statut NOT IN ('annulee', 'refusee', 'echec') GROUP BY 1, 2",
        etablissement_id,
    )
    resultats = {(g["ref"], g["nom"].strip().lower()): (g["n"], g["ca"], g["remise"]) for g in groupes}
    lignes = await connexion.fetch(
        "SELECT * FROM mark.resto_remise WHERE site_id = $1 ORDER BY CASE etat WHEN 'active' THEN 0 WHEN 'suspendue' THEN 1 WHEN 'brouillon' THEN 2 ELSE 3 END, id LIMIT $2",
        etablissement_id, MAX_REMISES,
    )
    offres = await compter_les_offres(connexion, etablissement_id)
    return [_rendue(r, resultats, offres) for r in lignes]


async def _ligne(connexion: asyncpg.Connection, etablissement_id: int, remise_id: int) -> asyncpg.Record:
    r = await connexion.fetchrow("SELECT * FROM mark.resto_remise WHERE id = $1 AND site_id = $2 FOR UPDATE", remise_id, etablissement_id)
    if r is None:
        raise RemiseRefusee("introuvable")
    if r["source"] not in ("portail", "agent"):
        raise RemiseRefusee("lecture_seule")  # la caisse ou .mark la tient
    return r


def _valeurs(champs: dict[str, Any]) -> list[Any]:
    j = lambda v: None if v is None else json.dumps(v)  # noqa: E731
    return [
        champs["nom"], champs["mecanisme"], j(champs["declencheur"]), j(champs["effet"]), j(champs["perimetre"]), champs["cumul"], j(champs.get("limite")),
        champs.get("phrase"), j(champs.get("moment")), champs.get("debut"), champs.get("fin"), champs["etat"],
    ]


async def ecrire_une_remise(connexion: asyncpg.Connection, etablissement_id: int, champs: dict[str, Any], auteur: str, remise_id: int | None = None) -> int:
    """Crée (``remise_id`` absent) ou modifie une remise de l'écran. Rend son identifiant. ``RemiseRefusee`` sinon."""
    if champs["mecanisme"] not in MECANISMES:
        raise ValueError("mecanisme")
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        if remise_id is None:
            if await connexion.fetchval("SELECT count(*) FROM mark.resto_remise WHERE site_id = $1", etablissement_id) >= MAX_REMISES:
                raise RemiseRefusee("trop_nombreuses")
            return await connexion.fetchval(
                "INSERT INTO mark.resto_remise (site_id, nom, mecanisme, declencheur, effet, perimetre, cumul, limite, phrase, moment, debut, fin, etat, source) "
                "VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7, $8::jsonb, $9, $10::jsonb, $11, $12, $13, 'portail') RETURNING id",
                etablissement_id, *_valeurs(champs),
            )
        ancienne = await _ligne(connexion, etablissement_id, remise_id)
        if ancienne["etat"] == "terminee":
            raise RemiseRefusee("transition")  # une remise terminée ne change plus
        await connexion.execute(
            "UPDATE mark.resto_remise SET nom = $3, mecanisme = $4, declencheur = $5::jsonb, effet = $6::jsonb, perimetre = $7::jsonb, cumul = $8, limite = $9::jsonb, "
            "phrase = $10, moment = $11::jsonb, debut = $12, fin = $13, etat = $14, maj_le = $15 WHERE id = $1 AND site_id = $2",
            remise_id, etablissement_id, *_valeurs({**champs, "etat": champs["etat"] if ancienne["etat"] == "brouillon" else ancienne["etat"]}), await maintenant(connexion),
        )
        return remise_id


async def changer_l_etat(connexion: asyncpg.Connection, etablissement_id: int, remise_id: int, etat: str, auteur: str) -> None:
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        r = await _ligne(connexion, etablissement_id, remise_id)
        if etat not in TRANSITIONS.get(r["etat"], ()):
            raise RemiseRefusee("transition")
        await connexion.execute("UPDATE mark.resto_remise SET etat = $3, maj_le = $4 WHERE id = $1 AND site_id = $2", remise_id, etablissement_id, etat, await maintenant(connexion))


async def supprimer_une_remise(connexion: asyncpg.Connection, etablissement_id: int, remise_id: int, auteur: str) -> None:
    """Supprime une remise de l'écran ; l'historique des changements la garde (déclencheurs de la 028). Les commandes déjà prises gardent leur remise écrite."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        await _ligne(connexion, etablissement_id, remise_id)
        await connexion.execute("DELETE FROM mark.resto_remise WHERE id = $1 AND site_id = $2", remise_id, etablissement_id)


# --------------------------------------------------------------------------- les envois


async def envois_pour_l_ecran(connexion: asyncpg.Connection, etablissement_id: int) -> list[dict[str, Any]]:
    """Un SMS par déclencheur de la liste fermée : le texte posé (ou celui qu'on propose) et s'il est allumé. Éteint par défaut (E-18)."""
    posees = {r["declencheur"]: r for r in await connexion.fetch("SELECT declencheur, texte, actif FROM mark.resto_envoi WHERE site_id = $1 AND type = 'sms' ORDER BY id DESC", etablissement_id)}
    return [
        {
            "declencheur": d, "type": "sms", "texte": (posees[d]["texte"] if d in posees else m["defaut"]), "actif": bool(d in posees and posees[d]["actif"]),
            "texte_par_defaut": m["defaut"], "trous": list(m["trous"]),
        }
        for d, m in ENVOIS.items()
    ]


async def ecrire_les_envois(connexion: asyncpg.Connection, etablissement_id: int, changements: list[dict[str, Any]], auteur: str) -> None:
    """Pose ce que l'écran a changé (texte, allumé) pour chaque déclencheur donné ; une ligne n'est créée qu'avec un texte (celui du défaut sinon)."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", auteur)
        for c in changements:
            if c["declencheur"] not in ENVOIS:
                raise ValueError("declencheur")
            existe = await connexion.fetchval("SELECT id FROM mark.resto_envoi WHERE site_id = $1 AND type = 'sms' AND declencheur = $2 ORDER BY id LIMIT 1", etablissement_id, c["declencheur"])
            if existe is None:
                await connexion.execute(
                    "INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', $2, $3, $4)",
                    etablissement_id, c["declencheur"], c.get("texte") or ENVOIS[c["declencheur"]]["defaut"], bool(c.get("actif")),
                )
                continue
            champs = {k: c[k] for k in ("texte", "actif") if c.get(k) is not None}
            if champs:
                sets = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(champs))
                await connexion.execute(
                    f"UPDATE mark.resto_envoi SET {sets}, maj_le = $2 WHERE id = $1", existe, await maintenant(connexion), *champs.values()
                )
