"""[.mark] Module Restauration, lots 9 et 10 : la couche d'accès de la LIAISON à la caisse (hors des 17 fonctions du contrat du classeur).

Le seul endroit, avec les autres ``restauration*.py``, où l'on écrit dans ``resto_liaison``, ``resto_liaison_acces``, ``resto_etat_caisse`` (côté
caisse), ``resto_message_recu``, ``resto_imprimante`` et ``resto_ticket``. Toute requête porte l'établissement dans le ``WHERE`` ; rien n'est
jamais lu ni écrit pour un autre. Jamais un secret ici : ``resto_liaison_acces`` ne garde que la RÉFÉRENCE du jeton (rangé dans le coffre
d'identifiants de Dograh) et ``resto_imprimante`` que l'empreinte du jeton de l'imprimante. L'heure vient de ``horloge`` (D6).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import asyncpg

from api.db.bases_clients.restauration_commun import Resultat, maintenant, poser_session

ETATS_DE_LIAISON = ("aucune", "ok", "erreur", "rompue")
# Les codes d'erreur de la liaison : une liste fermée, jamais le texte d'un fournisseur (la colonne est bornée à 80).
CODES_D_ERREUR = frozenset(
    {"caisse_injoignable", "jeton_refuse", "limite_atteinte", "reponse_inattendue", "abonnement_echoue", "import_echoue", "papier", "capot", "imprimante_erreur"}
)
CODES_D_AVERTISSEMENT = frozenset({"horaires_differents", "carte_sans_code", "etat_inconnu"})


async def cle_du_site(connexion: asyncpg.Connection, etablissement_id: int) -> str | None:
    """La ``cle`` de l'établissement (celle que le lien point de vente de la base de Dograh désigne)."""
    return await connexion.fetchval("SELECT cle FROM mark.site WHERE id = $1", etablissement_id)


async def site_par_cle(connexion: asyncpg.Connection, cle: str) -> int | None:
    return await connexion.fetchval("SELECT id FROM mark.site WHERE cle = $1", cle)


# --------------------------------------------------------------------------- la liaison


def _liaison(r: asyncpg.Record | None) -> dict | None:
    if r is None:
        return None
    return {
        "prise": r["prise"], "point_de_vente": r["point_de_vente"], "etat": r["etat"], "derniere_erreur": r["derniere_erreur"],
        "derniere_synchro": r["derniere_synchro"], "mode_passif": r["mode_passif"], "derniere_releve": r["derniere_releve"],
        "avertissements": list(r["avertissements"] or []), "alerte_sans_reponse_min": r["alerte_sans_reponse_min"], "releve_messages_min": r["releve_messages_min"],
    }


async def liaison(connexion: asyncpg.Connection, etablissement_id: int) -> dict | None:
    return _liaison(await connexion.fetchrow("SELECT * FROM mark.resto_liaison WHERE site_id = $1", etablissement_id))


async def liaisons_de(connexion: asyncpg.Connection, prise: str) -> list[dict]:
    """Toutes les liaisons de cette prise de la base (la veille et le rattrapage parcourent les établissements)."""
    lignes = await connexion.fetch("SELECT site_id, * FROM mark.resto_liaison WHERE prise = $1 ORDER BY site_id", prise)
    return [{"etablissement_id": r["site_id"], **_liaison(r)} for r in lignes]


async def poser_liaison(
    connexion: asyncpg.Connection, etablissement_id: int, prise: str, point_de_vente: str | None, etat: str, *, erreur: str | None = None,
    source: str = "mark", auteur: str = "liaison"
) -> None:
    if etat not in ETATS_DE_LIAISON or (erreur is not None and erreur not in CODES_D_ERREUR):
        raise ValueError(f"Liaison hors liste : {etat!r} {erreur!r}")
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, source, auteur)
        await connexion.execute(
            "INSERT INTO mark.resto_liaison (site_id, prise, point_de_vente, etat, derniere_erreur, derniere_synchro, maj_le) VALUES ($1, $2, $3, $4, $5, $6, $7) "
            "ON CONFLICT (site_id) DO UPDATE SET prise = EXCLUDED.prise, point_de_vente = EXCLUDED.point_de_vente, etat = EXCLUDED.etat, "
            "derniere_erreur = EXCLUDED.derniere_erreur, derniere_synchro = COALESCE(EXCLUDED.derniere_synchro, resto_liaison.derniere_synchro), maj_le = EXCLUDED.maj_le",
            etablissement_id, prise, point_de_vente, etat, erreur, maintenant_ if etat == "ok" else None, maintenant_,
        )


async def marquer_la_liaison(
    connexion: asyncpg.Connection, etablissement_id: int, etat: str, erreur: str | None = None, *, synchro: bool = False
) -> bool:
    """Change l'état de la liaison (``ok``, ``erreur``, ``rompue``) ; ``True`` si l'état a CHANGÉ (le flux n'est émis qu'alors)."""
    if etat not in ETATS_DE_LIAISON or (erreur is not None and erreur not in CODES_D_ERREUR):
        raise ValueError(f"Liaison hors liste : {etat!r} {erreur!r}")
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, "mark", "liaison")
        avant = await connexion.fetchval("SELECT etat FROM mark.resto_liaison WHERE site_id = $1 FOR UPDATE", etablissement_id)
        if avant is None:
            return False
        await connexion.execute(
            "UPDATE mark.resto_liaison SET etat = $2, derniere_erreur = $3, derniere_synchro = CASE WHEN $4 THEN $5 ELSE derniere_synchro END, maj_le = $5 "
            "WHERE site_id = $1",
            etablissement_id, etat, erreur, synchro, maintenant_,
        )
    return avant != etat


async def poser_la_veille(connexion: asyncpg.Connection, etablissement_id: int, *, passif: bool | None = None, releve: bool = False, avertissements: list[str] | None = None) -> None:
    if avertissements is not None and not set(avertissements) <= CODES_D_AVERTISSEMENT:
        raise ValueError(f"Avertissement hors liste : {avertissements!r}")
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, "mark", "liaison")
        await connexion.execute(
            "UPDATE mark.resto_liaison SET mode_passif = COALESCE($2, mode_passif), derniere_releve = CASE WHEN $3 THEN $5 ELSE derniere_releve END, "
            "avertissements = COALESCE($4, avertissements), maj_le = $5 WHERE site_id = $1",
            etablissement_id, passif, releve, avertissements, maintenant_,
        )


async def supprimer_la_liaison(connexion: asyncpg.Connection, etablissement_id: int) -> None:
    async with connexion.transaction():
        await poser_session(connexion, "mark", "liaison")
        await connexion.execute("DELETE FROM mark.resto_liaison_acces WHERE site_id = $1", etablissement_id)
        await connexion.execute("DELETE FROM mark.resto_liaison WHERE site_id = $1", etablissement_id)


# --------------------------------------------------------------------------- l'accès (la référence du jeton, jamais sa valeur)


async def poser_acces(connexion: asyncpg.Connection, etablissement_id: int, credential_uuid: str) -> None:
    maintenant_ = await maintenant(connexion)
    await connexion.execute(
        "INSERT INTO mark.resto_liaison_acces (site_id, credential_uuid, maj_le) VALUES ($1, $2, $3) "
        "ON CONFLICT (site_id) DO UPDATE SET credential_uuid = EXCLUDED.credential_uuid, maj_le = EXCLUDED.maj_le",
        etablissement_id, credential_uuid, maintenant_,
    )


async def acces(connexion: asyncpg.Connection, etablissement_id: int) -> str | None:
    """La référence du jeton (``credential_uuid`` du coffre de Dograh) de CET établissement."""
    return await connexion.fetchval("SELECT credential_uuid FROM mark.resto_liaison_acces WHERE site_id = $1", etablissement_id)


# --------------------------------------------------------------------------- l'état que la caisse porte


async def poser_etat_de_la_caisse(connexion: asyncpg.Connection, etablissement_id: int, etat: dict[str, Any], *, horaires: dict | None = None) -> bool:
    """Écrit ``resto_etat_caisse`` d'après ``etat_de_hubrise`` (mode, minutes en plus, reprise, temps de préparation). ``True`` si quelque chose a changé
    (alors ``caisse.etat`` est émis). La source est toujours la caisse : le portail l'affiche en lecture seule (E-49)."""
    if etat.get("mode") not in ("normal", "deborde", "pause"):
        raise ValueError(f"Mode de caisse hors liste : {etat.get('mode')!r}")
    maintenant_ = await maintenant(connexion)
    avant = await connexion.fetchrow("SELECT mode, minutes_en_plus, reprise, temps_preparation, horaires FROM mark.resto_etat_caisse WHERE site_id = $1", etablissement_id)
    horaires_json = None if horaires is None else json.dumps(horaires)
    async with connexion.transaction():
        await poser_session(connexion, "caisse", "caisse")
        await connexion.execute(
            "INSERT INTO mark.resto_etat_caisse (site_id, mode, minutes_en_plus, reprise, temps_preparation, horaires, source, maj_le) "
            "VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'caisse', $7) "
            "ON CONFLICT (site_id) DO UPDATE SET mode = EXCLUDED.mode, minutes_en_plus = EXCLUDED.minutes_en_plus, reprise = EXCLUDED.reprise, "
            "temps_preparation = EXCLUDED.temps_preparation, horaires = COALESCE(EXCLUDED.horaires, resto_etat_caisse.horaires), source = 'caisse', maj_le = EXCLUDED.maj_le",
            etablissement_id, etat["mode"], int(etat.get("minutes_en_plus") or 0), etat.get("reprise"), etat.get("temps_preparation"), horaires_json, maintenant_,
        )
    if avant is None:
        return True
    return (avant["mode"], avant["minutes_en_plus"], avant["reprise"], avant["temps_preparation"]) != (
        etat["mode"], int(etat.get("minutes_en_plus") or 0), etat.get("reprise"), etat.get("temps_preparation")
    )


async def retirer_l_etat_de_la_caisse(connexion: asyncpg.Connection, etablissement_id: int) -> None:
    """Plus de caisse : le portail et la fiche de l'établissement font de nouveau foi."""
    async with connexion.transaction():
        await poser_session(connexion, "mark", "liaison")
        await connexion.execute("DELETE FROM mark.resto_etat_caisse WHERE site_id = $1", etablissement_id)


JOURS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


async def horaires_de_l_etablissement(connexion: asyncpg.Connection, etablissement_id: int) -> dict[str, list[dict[str, str]]]:
    """Les horaires de la fiche de l'établissement (jour 1 = lundi), au format de ceux de la caisse, pour les comparer : avertir, jamais écraser."""
    sortie: dict[str, list[dict[str, str]]] = {}
    for r in await connexion.fetch("SELECT jour, ouverture, fermeture FROM mark.horaire WHERE site_id = $1 ORDER BY jour, ouverture", etablissement_id):
        sortie.setdefault(JOURS[(r["jour"] - 1) % 7], []).append({"from": r["ouverture"].strftime("%H:%M"), "to": r["fermeture"].strftime("%H:%M")})
    return sortie


# --------------------------------------------------------------------------- messages reçus (anti-doublon)


async def noter_le_message(connexion: asyncpg.Connection, fournisseur: str, identifiant: str, etablissement_id: int | None, type_: str | None) -> bool:
    """``True`` si le message est NOUVEAU (à traiter) ; ``False`` s'il a déjà été vu (ignoré : rejeu sans effet double)."""
    maintenant_ = await maintenant(connexion)
    ligne = await connexion.fetchval(
        "INSERT INTO mark.resto_message_recu (fournisseur, identifiant, site_id, type, recu_le) VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (fournisseur, identifiant) DO NOTHING RETURNING 1",
        fournisseur, identifiant[:200], etablissement_id, (type_ or "")[:60] or None, maintenant_,
    )
    return bool(ligne)


async def marquer_le_message_traite(connexion: asyncpg.Connection, fournisseur: str, identifiant: str) -> None:
    maintenant_ = await maintenant(connexion)
    await connexion.execute(
        "UPDATE mark.resto_message_recu SET traite_le = $3 WHERE fournisseur = $1 AND identifiant = $2", fournisseur, identifiant[:200], maintenant_
    )


async def oublier_le_message(connexion: asyncpg.Connection, fournisseur: str, identifiant: str) -> None:
    """Un traitement qui a ÉCHOUÉ ne doit pas empêcher la nouvelle tentative de la caisse : le message est de nouveau « nouveau »."""
    await connexion.execute(
        "DELETE FROM mark.resto_message_recu WHERE fournisseur = $1 AND identifiant = $2 AND traite_le IS NULL", fournisseur, identifiant[:200]
    )


# --------------------------------------------------------------------------- commandes : ce que la prise dit après l'envoi


async def poser_ref_fournisseur(connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, ref: str | None) -> bool:
    """Écrit l'identifiant que la caisse a donné à NOTRE commande (jamais d'écrasement par du vide)."""
    if not ref:
        return False
    return bool(
        await connexion.fetchval(
            "UPDATE mark.resto_commande SET ref_fournisseur = $3 WHERE numero = $1 AND site_id = $2 AND (ref_fournisseur IS DISTINCT FROM $3) RETURNING 1",
            uuid.UUID(str(numero)), etablissement_id, ref[:120],
        )
    )


async def commande_par_ref_fournisseur(connexion: asyncpg.Connection, etablissement_id: int, ref: str) -> str | None:
    """Le numéro de NOTRE commande que la caisse connaît sous cet identifiant ; ``None`` si ce n'est pas une commande de cet établissement."""
    numero = await connexion.fetchval("SELECT numero FROM mark.resto_commande WHERE site_id = $1 AND ref_fournisseur = $2", etablissement_id, ref)
    return None if numero is None else str(numero)


async def poser_l_heure_annoncee(connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, heure: datetime, source: str = "caisse") -> bool:
    """L'heure changée par la caisse (temps de préparation allongé). ``True`` si l'heure a changé."""
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, source, f"heure:{source}")
        return bool(
            await connexion.fetchval(
                "UPDATE mark.resto_commande SET heure_annoncee = $3, maj_le = $4 WHERE numero = $1 AND site_id = $2 AND heure_annoncee IS DISTINCT FROM $3 RETURNING 1",
                uuid.UUID(str(numero)), etablissement_id, heure, maintenant_,
            )
        )


async def commandes_a_reprendre(connexion: asyncpg.Connection, etablissement_id: int, *, limite: int = 50) -> list[str]:
    """Les commandes de CET établissement restées ``nouvelle`` ou ``envoyee`` dont l'envoi est à reprendre : la reprise est ESPACÉE (2, 4, 8 puis 15 minutes
    après le dernier essai, selon le nombre d'essais déjà faits) pour ne pas harceler une caisse qui se remet. Rejouable sans effet double : la prise
    cherche par notre numéro avant de renvoyer."""
    maintenant_ = await maintenant(connexion)
    lignes = await connexion.fetch(
        "SELECT numero FROM mark.resto_commande WHERE site_id = $1 AND statut IN ('nouvelle', 'envoyee') "
        "AND maj_le <= $2::timestamptz - (LEAST(power(2, tentatives), 15) * interval '1 minute') "
        "AND NOT EXISTS (SELECT 1 FROM mark.resto_ticket t WHERE t.numero = resto_commande.numero) ORDER BY maj_le LIMIT $3",
        etablissement_id, maintenant_, limite,
    )
    return [str(r["numero"]) for r in lignes]


async def compter_un_essai_rate(connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, *, ajouter: bool = True) -> int:
    """Un essai d'envoi qui n'a pas abouti : ``tentatives`` + 1 (et ``maj_le``, qui espace la reprise). Le PREMIER envoi (``nouvelle`` -> ``envoyee``) compte
    déjà son essai par ``changer_statut`` : ``ajouter=False`` ne fait que relire. Rend le nombre d'essais."""
    maintenant_ = await maintenant(connexion)
    return int(
        await connexion.fetchval(
            "UPDATE mark.resto_commande SET tentatives = tentatives + CASE WHEN $4 THEN 1 ELSE 0 END, maj_le = $3 WHERE numero = $1 AND site_id = $2 RETURNING tentatives",
            uuid.UUID(str(numero)), etablissement_id, maintenant_, ajouter,
        )
        or 0
    )


async def commandes_sans_reponse(connexion: asyncpg.Connection, etablissement_id: int, *, depuis_minutes: int) -> list[dict]:
    """Les commandes que la caisse a REÇUES (elle leur a donné un identifiant) mais qu'elle n'a pas encore prises en charge, depuis plus de ``depuis_minutes`` :
    une alerte, jamais un renvoi aveugle. (Un envoi qui n'a pas abouti n'a pas d'identifiant : il est à reprendre, pas « sans réponse ».)"""
    maintenant_ = await maintenant(connexion)
    lignes = await connexion.fetch(
        "SELECT numero, numero_court, maj_le FROM mark.resto_commande WHERE site_id = $1 AND statut = 'envoyee' AND ref_fournisseur IS NOT NULL AND maj_le <= $2 ORDER BY maj_le",
        etablissement_id, maintenant_ - timedelta(minutes=depuis_minutes),
    )
    return [{"numero": str(r["numero"]), "numero_court": r["numero_court"], "depuis": r["maj_le"]} for r in lignes]


async def ruptures_de_la_caisse(connexion: asyncpg.Connection, etablissement_id: int) -> dict[str, bool]:
    """``{code_caisse: disponible}`` : ce que le classeur sait des ruptures (pour ne pousser que ce qui change)."""
    return {r["code_caisse"]: r["disponible"] for r in await connexion.fetch("SELECT code_caisse, disponible FROM mark.resto_rupture WHERE site_id = $1", etablissement_id)}


async def genre_du_code(connexion: asyncpg.Connection, etablissement_id: int, code_caisse: str) -> str | None:
    """``declinaison`` ou ``option`` : ce qu'un code de caisse désigne dans la carte de CET établissement (la prise écrit ``sku_ref`` ou ``option_ref``)."""
    if await connexion.fetchval(
        "SELECT EXISTS (SELECT 1 FROM mark.resto_declinaison WHERE (site_id IS NULL OR site_id = $1) AND code_caisse = $2)", etablissement_id, code_caisse
    ):
        return "declinaison"
    if await connexion.fetchval("SELECT EXISTS (SELECT 1 FROM mark.resto_option WHERE (site_id IS NULL OR site_id = $1) AND code_caisse = $2)", etablissement_id, code_caisse):
        return "option"
    return None


# --------------------------------------------------------------------------- l'imprimante et les tickets (lot 10)


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


async def poser_imprimante(
    connexion: asyncpg.Connection, etablissement_id: int, jeton: str, *, nom: str | None = None, mode_planifiee: str = "differe", minutes_avant: int = 20
) -> None:
    """Branche l'imprimante de l'établissement ; le jeton n'est gardé qu'en empreinte (SHA-256). Rejouable : un nouveau jeton remplace l'ancien."""
    maintenant_ = await maintenant(connexion)
    await connexion.execute(
        "INSERT INTO mark.resto_imprimante (site_id, jeton_empreinte, nom, mode_planifiee, minutes_avant, maj_le) VALUES ($1, $2, $3, $4, $5, $6) "
        "ON CONFLICT (site_id) DO UPDATE SET jeton_empreinte = EXCLUDED.jeton_empreinte, nom = EXCLUDED.nom, "
        "mode_planifiee = EXCLUDED.mode_planifiee, minutes_avant = EXCLUDED.minutes_avant, maj_le = EXCLUDED.maj_le",
        etablissement_id, empreinte(jeton), nom, mode_planifiee, minutes_avant, maintenant_,
    )


async def imprimante_par_jeton(connexion: asyncpg.Connection, jeton: str) -> dict | None:
    """L'imprimante dont l'empreinte est celle du jeton (comparaison par la base, sur une empreinte à longueur fixe)."""
    r = await connexion.fetchrow("SELECT * FROM mark.resto_imprimante WHERE jeton_empreinte = $1", empreinte(jeton))
    return None if r is None else dict(r)


async def noter_l_interrogation(connexion: asyncpg.Connection, etablissement_id: int, etat: str) -> None:
    maintenant_ = await maintenant(connexion)
    await connexion.execute(
        "UPDATE mark.resto_imprimante SET derniere_interrogation = $2, etat = $3, maj_le = $2 WHERE site_id = $1", etablissement_id, maintenant_, etat
    )


async def creer_le_ticket(
    connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, *, liberer_le: datetime | None = None, programmee: bool = False
) -> bool:
    """Un ticket par commande (``numero`` est la clé) : un second appel n'en crée pas un second (jamais deux tickets). ``True`` si créé."""
    maintenant_ = await maintenant(connexion)
    return bool(
        await connexion.fetchval(
            "INSERT INTO mark.resto_ticket (numero, site_id, liberer_le, programmee, cree_le, maj_le) "
            "SELECT $1, $2, $3, $4, $5, $5 WHERE EXISTS (SELECT 1 FROM mark.resto_commande WHERE numero = $1 AND site_id = $2) "
            "ON CONFLICT (numero) DO NOTHING RETURNING 1",
            uuid.UUID(str(numero)), etablissement_id, liberer_le, programmee, maintenant_,
        )
    )


async def ticket_a_imprimer(connexion: asyncpg.Connection, etablissement_id: int) -> str | None:
    """Le plus ancien ticket LIBÉRÉ de CET établissement qui attend (``en_file``) ou dont la remise est restée sans nouvelle (``recupere``)."""
    maintenant_ = await maintenant(connexion)
    numero = await connexion.fetchval(
        "SELECT numero FROM mark.resto_ticket WHERE site_id = $1 AND statut = 'en_file' AND (liberer_le IS NULL OR liberer_le <= $2) ORDER BY cree_le LIMIT 1",
        etablissement_id, maintenant_,
    )
    return None if numero is None else str(numero)


async def marquer_le_ticket(
    connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, statut: str, code: str | None = None
) -> Resultat:
    """Fait avancer un ticket : ``recupere`` (l'imprimante l'a pris), ``imprime`` (elle confirme), ``erreur`` (papier, capot…). ``DEJA_FAIT`` si déjà là."""
    if statut not in ("en_file", "recupere", "imprime", "erreur"):
        return Resultat("ARGUMENT_INVALIDE", manque="statut")
    maintenant_ = await maintenant(connexion)
    n = uuid.UUID(str(numero))
    actuel = await connexion.fetchval("SELECT statut FROM mark.resto_ticket WHERE numero = $1 AND site_id = $2", n, etablissement_id)
    if actuel is None:
        return Resultat("INTROUVABLE", {"numero": str(n)})
    if actuel == statut or actuel == "imprime":
        return Resultat("DEJA_FAIT", {"statut_actuel": actuel})  # un ticket imprimé ne change plus : la confirmation rejouée ne fait rien
    await connexion.execute(
        "UPDATE mark.resto_ticket SET statut = $3, code = $4, "
        "tentatives = tentatives + CASE WHEN $3 = 'recupere' THEN 1 ELSE 0 END, "
        "recupere_le = CASE WHEN $3 = 'recupere' THEN $5 ELSE recupere_le END, "
        "imprime_le = CASE WHEN $3 = 'imprime' THEN $5 ELSE imprime_le END, maj_le = $5 WHERE numero = $1 AND site_id = $2",
        n, etablissement_id, statut, code, maintenant_,
    )
    return Resultat("OK", {"numero": str(n), "statut": statut})


async def remettre_en_file(connexion: asyncpg.Connection, etablissement_id: int, depuis_minutes: int, tentatives_max: int) -> list[str]:
    """Un ticket ``recupere`` ou en ``erreur`` depuis plus de ``depuis_minutes`` sans confirmation d'impression retourne en file (la confirmation peut
    se perdre : repli prévu), tant qu'il n'a pas épuisé ses tentatives."""
    maintenant_ = await maintenant(connexion)
    lignes = await connexion.fetch(
        "UPDATE mark.resto_ticket SET statut = 'en_file', maj_le = $2 WHERE site_id = $1 AND statut IN ('recupere', 'erreur') AND maj_le <= $3 AND tentatives < $4 RETURNING numero",
        etablissement_id, maintenant_, maintenant_ - timedelta(minutes=depuis_minutes), tentatives_max,
    )
    return [str(r["numero"]) for r in lignes]


async def tickets_non_imprimes(connexion: asyncpg.Connection, etablissement_id: int, depuis_minutes: int) -> list[dict]:
    """Les tickets libérés depuis plus de ``depuis_minutes`` qui ne sont pas imprimés et dont l'alerte n'a pas encore été dite. Marque l'alerte (une seule fois)."""
    maintenant_ = await maintenant(connexion)
    lignes = await connexion.fetch(
        "UPDATE mark.resto_ticket SET alerte_le = $2 WHERE site_id = $1 AND statut <> 'imprime' AND alerte_le IS NULL "
        "AND COALESCE(liberer_le, cree_le) <= $3 RETURNING numero, code",
        etablissement_id, maintenant_, maintenant_ - timedelta(minutes=depuis_minutes),
    )
    return [{"numero": str(r["numero"]), "code": r["code"] or "non_imprime"} for r in lignes]


async def etat_de_la_commande(connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID) -> dict | None:
    """``{numero, statut, heure_annoncee, ref_fournisseur}`` de la commande de CET établissement ; ``None`` si ce n'en est pas une (ou numéro mal formé)."""
    try:
        n = uuid.UUID(str(numero))
    except ValueError:
        return None
    r = await connexion.fetchrow("SELECT numero, statut, heure_annoncee, ref_fournisseur FROM mark.resto_commande WHERE numero = $1 AND site_id = $2", n, etablissement_id)
    return None if r is None else {"numero": str(r["numero"]), "statut": r["statut"], "heure_annoncee": r["heure_annoncee"], "ref_fournisseur": r["ref_fournisseur"]}


async def ids_des_sites(connexion: asyncpg.Connection) -> list[int]:
    """Les établissements de cette base (une base = une organisation) : le rattrapage les parcourt un à un."""
    return [r["id"] for r in await connexion.fetch("SELECT id FROM mark.site ORDER BY id")]


async def envoi_actif(connexion: asyncpg.Connection, etablissement_id: int, type_: str, declencheur: str) -> dict | None:
    """L'envoi (SMS, mail) ALLUMÉ de CET établissement pour ce déclencheur ; ``None`` : éteint (il l'est par défaut, E-18)."""
    r = await connexion.fetchrow(
        "SELECT id, type, declencheur, texte FROM mark.resto_envoi WHERE site_id = $1 AND type = $2 AND declencheur = $3 AND actif ORDER BY id LIMIT 1",
        etablissement_id, type_, declencheur,
    )
    return None if r is None else dict(r)


async def le_ticket(connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID) -> dict | None:
    """Le ticket de CETTE commande de CET établissement ; ``None`` sinon."""
    try:
        n = uuid.UUID(str(numero))
    except ValueError:
        return None
    r = await connexion.fetchrow("SELECT numero, statut, liberer_le, programmee, tentatives FROM mark.resto_ticket WHERE numero = $1 AND site_id = $2", n, etablissement_id)
    return None if r is None else {**dict(r), "numero": str(r["numero"])}


async def imprimante(connexion: asyncpg.Connection, etablissement_id: int) -> dict | None:
    r = await connexion.fetchrow(
        "SELECT site_id, nom, mode_planifiee, minutes_avant, derniere_interrogation, etat FROM mark.resto_imprimante WHERE site_id = $1", etablissement_id
    )
    return None if r is None else dict(r)
