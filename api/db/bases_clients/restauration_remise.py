"""[.mark] Module Restauration, lots 2 et 7 : les remises applicables, chiffrées (contrat § 4, plan § 3.8, E-52).

Règle unique (§ 3.8) : le comptoir calcule l'effet exact de la remise ; la commande part avec les articles à leur prix
de carte et UNE ligne de remise chiffrée par remise appliquée (nom, montant, référence de caisse si elle existe). Un article
offert part à son prix avec une remise du même montant.

**Les douze mécanismes** (E-52, liste d'Evan du 15/11, fermée en code) : ``pourcentage``, ``montant``, ``x_achetes_y_offert``,
``deuxieme_moitie_prix``, ``prix_du_jour``, ``seuil_panier``, ``passage_en_menu``, ``taille_superieure``, ``offre_famille``,
``creneau``, ``nouveaute``, ``fidelite``. Chacun est traduit vers une famille du moteur commun (``remises_moteur.py``, sans mot de
restaurant) ; le calcul est celui du moteur, au centime. Une ligne de la table dont le mécanisme n'est pas dans la liste n'est
jamais appliquée ni annoncée (la base du portail est écrite directement : la liste se garde ici).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients import remises_moteur as moteur
from api.db.bases_clients.instantane import instantane_de, stable
from api.db.bases_clients.restauration_carte import _json, disponible_a
from api.db.bases_clients.restauration_commun import couvre, fuseau_de

# mécanisme du module -> famille du moteur commun
FAMILLE_DU_MECANISME: dict[str, str] = {
    "pourcentage": "pourcentage",
    "montant": "montant",
    "x_achetes_y_offert": "lot_offert",
    "deuxieme_moitie_prix": "rang_reduit",
    "prix_du_jour": "prix_fixe",
    "seuil_panier": "pourcentage",
    "passage_en_menu": "composition",
    "taille_superieure": "ecart_de_rang",
    "offre_famille": "composition",
    "creneau": "pourcentage",
    "nouveaute": "prix_fixe",
    "fidelite": "tous_les",
}
MECANISMES = tuple(FAMILLE_DU_MECANISME)
MECANISMES_CHIFFRES = frozenset(MECANISMES)  # les douze : plus aucun n'est « lu sans être appliqué »
assert len(MECANISMES) == 12 and {f for f in FAMILLE_DU_MECANISME.values()} <= moteur.FAMILLES


def _regle(r: asyncpg.Record) -> dict[str, Any]:
    return {
        "famille": FAMILLE_DU_MECANISME[r["mecanisme"]],
        "exige_un_minimum": r["mecanisme"] == "seuil_panier",
        "declencheur": _json(r["declencheur"]) or {}, "effet": _json(r["effet"]) or {}, "perimetre": _json(r["perimetre"]) or {},
        "limite": _json(r["limite"]) or {},
    }


def _effet_sur_le_sous_total(effet: dict, sous_total: int) -> int | None:
    """Rétrocompatibilité : une remise évaluée sans le détail du panier (``lignes`` absent) ne sait que pourcentage et montant."""
    if "pourcentage" in effet:
        pct = effet["pourcentage"]
        return moteur.part_en_centimes(sous_total, float(pct)) if isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 < pct <= 100 else None
    m = effet.get("montant")
    return min(sous_total, m) if isinstance(m, int) and not isinstance(m, bool) and m > 0 else None


async def remises_actives_a(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime) -> list[asyncpg.Record]:
    """Les lignes des remises ACTIVES de l'établissement dont la période couvre ``moment`` (début compris, fin exclue), par identifiant. Pendant un
    appel (lot 5) : les remises actives lues au chargement, la période choisie ici ; hors d'un appel, à la base."""

    async def lire() -> list[asyncpg.Record]:
        return list(await connexion.fetch("SELECT * FROM mark.resto_remise WHERE site_id = $1 AND etat = 'active' ORDER BY id", etablissement_id))

    actives = await lire() if instantane_de(connexion) is None else await stable(connexion, ("remises_actives", etablissement_id), lire)
    return [r for r in actives if couvre(r["debut"], r["fin"], moment)]


async def nombre_de_commandes_du_client(connexion: asyncpg.Connection, etablissement_id: int, telephone: str) -> int:
    """Combien de commandes ce client a déjà passées ici (fidélité) ; lu une fois par appel (lot 5)."""

    async def lire() -> int:
        return await connexion.fetchval("SELECT nb_commandes FROM mark.resto_client WHERE site_id = $1 AND telephone = $2", etablissement_id, telephone) or 0

    return int(await stable(connexion, ("nb_commandes_du_client", etablissement_id, telephone), lire))


async def remises_applicables(
    connexion: asyncpg.Connection, etablissement_id: int, panier: dict, moment: datetime, client: dict | None = None, *, codes: Iterable[str] = ()
) -> list[dict]:
    """Les remises ACTIVES de l'établissement, valables à ce moment pour ce panier, avec leur effet chiffré.

    ``panier`` : ``{"mode", "sous_total": centimes, "lignes"?: [{code_caisse, prix_unitaire, quantite, produit_id?, categorie_id?}],
    "prix_par_code"?: {code: centimes}}``. Sans ``lignes``, seules les remises sur le sous-total (pourcentage, montant, seuil, créneau, fidélité
    sur le total) sont évaluées. ``client`` : ``{"telephone"}`` du client (fidélité : sa Nième commande). Chaque ligne :
    ``{ref, id, nom, mecanisme, montant, chiffree, cumul, phrase, ref_caisse, ajout, unites}``. ``montant`` vaut ``None`` quand la remise
    ne s'applique pas à ce panier (hors seuil, hors créneau, hors mode, rien à réduire). ``codes`` (lot 14, OFF3) : les codes que l'appelant a dits ; une remise
    À CODE ne s'évalue que pour un code dit (sinon elle n'existe pas pour ce panier)."""
    if moment.tzinfo is None:
        raise ValueError("Le moment doit être aware.")
    local = moment.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id)))
    sous_total = int(panier.get("sous_total", 0))
    lignes_du_panier = panier.get("lignes")
    unites = [
        moteur.Unite(rang, l["code_caisse"], int(l["prix_unitaire"]), l.get("produit_id"), l.get("categorie_id"))
        for rang, l in enumerate(lignes_du_panier or [], start=1) for _ in range(int(l.get("quantite", 1)))
    ]
    rang_du_client = None
    telephone = (client or {}).get("telephone")
    if telephone:
        rang_du_client = 1 + await nombre_de_commandes_du_client(connexion, etablissement_id, telephone)
    dits = {str(c).upper() for c in codes or ()}
    contexte = moteur.Contexte(panier.get("mode"), sous_total, rang_du_client, dict(panier.get("prix_par_code") or {}), moment)
    lignes = await remises_actives_a(connexion, etablissement_id, moment)
    sortie = []
    for r in lignes:
        if r["mecanisme"] not in FAMILLE_DU_MECANISME:
            continue  # la liste est fermée : un mécanisme inconnu n'est ni appliqué ni annoncé
        if r["code"] and r["code"] not in dits:
            continue  # OFF3 : une remise à code ne s'applique qu'avec son code dit
        montant: int | None = None
        ajout: tuple = ()
        concernees: tuple = ()
        if disponible_a(_json(r["moment"]), local):
            if lignes_du_panier is None:
                regle = _regle(r)
                if regle["famille"] in ("pourcentage", "montant") and not (regle["perimetre"].get("modes") and panier.get("mode") not in regle["perimetre"]["modes"]):
                    minimum = regle["declencheur"].get("minimum", 0)
                    if not (regle["exige_un_minimum"] and "minimum" not in regle["declencheur"]) and sous_total >= minimum:
                        montant = _effet_sur_le_sous_total(regle["effet"], sous_total)
            else:
                effet = moteur.evaluer(_regle(r), unites, contexte)
                if effet is not None:
                    montant, ajout, concernees = effet.montant, effet.ajout, effet.unites
        sortie.append(
            {
                "ref": r["ref"] or str(r["id"]), "id": r["id"], "nom": r["nom"], "mecanisme": r["mecanisme"],
                "montant": montant, "chiffree": True, "cumul": r["cumul"], "phrase": r["phrase"],
                "ref_caisse": r["ref_caisse"], "ajout": ajout, "unites": concernees,
            }
        )
    return sortie


async def remises_en_cours(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime) -> list[dict]:
    """[.mark] Lot 7 : les remises ACTIVES de CET établissement valables à ce moment (créneau compris), sans regarder le panier : de quoi répondre
    « qu'est-ce que vous avez ». ``{ref, nom, mecanisme, phrase, minimum}`` ; ``minimum`` : le seuil de panier en centimes, s'il y en a un."""
    if moment.tzinfo is None:
        raise ValueError("Le moment doit être aware.")
    local = moment.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id)))
    lignes = await remises_actives_a(connexion, etablissement_id, moment)
    sortie = []
    for r in lignes:
        if r["code"] or r["mecanisme"] not in FAMILLE_DU_MECANISME or not disponible_a(_json(r["moment"]), local):
            continue  # OFF3 : une remise à code n'est jamais annoncée
        minimum = (_json(r["declencheur"]) or {}).get("minimum")
        sortie.append(
            {"ref": r["ref"] or str(r["id"]), "nom": r["nom"], "mecanisme": r["mecanisme"], "phrase": r["phrase"],
             "minimum": minimum if isinstance(minimum, int) and not isinstance(minimum, bool) and minimum > 0 else None}
        )
    return sortie


async def remises_a_code(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime) -> list[dict]:
    """[.mark] Lot 14 (OFF3) : les remises à code ACTIVES de CET établissement valables à ce moment, ``{code, ref, nom, phrase}``. Une remise brouillon, suspendue,
    expirée ou d'un autre établissement n'y figure pas : son code est un code inconnu."""
    return [{"code": r["code"], "ref": r["ref"] or str(r["id"]), "nom": r["nom"], "phrase": r["phrase"]}
            for r in await remises_actives_a(connexion, etablissement_id, moment) if r["code"] and r["mecanisme"] in FAMILLE_DU_MECANISME]


def au_mieux(candidates: list[dict], sous_total: int) -> list[dict]:
    """L'ensemble de remises le plus avantageux pour le client parmi celles qui s'appliquent (exclusive seule ou cumulables ensemble)."""
    return moteur.choisir_au_mieux(candidates, sous_total)


def retenir(demandees: list[dict[str, Any]], candidates: list[dict], sous_total: int):
    """Parmi les remises demandées (par ``ref`` ou ``nom``), celles qui s'appliquent : ``(retenues, refus)``.
    ``refus`` : ``None`` ou la raison fermée (``remise_inconnue`` : absente, non chiffrée ou sans effet sur ce panier ;
    ``autre`` : deux remises exclusives). Le total des remises ne dépasse jamais le sous-total."""
    retenues = []
    for d in demandees:
        cle = d.get("ref") or d.get("nom")
        trouvee = next((c for c in candidates if cle in (c["ref"], c["nom"])), None)
        if trouvee is None or not trouvee["chiffree"] or not trouvee["montant"]:
            return [], "remise_inconnue"
        if any(trouvee["ref"] == r["ref"] for r in retenues):
            continue
        retenues.append(trouvee)
    if sum(1 for r in retenues if r["cumul"] == "exclusive") > 1:
        return [], "autre"
    if len(retenues) > 1 and any(r["cumul"] == "exclusive" for r in retenues):
        return [], "autre"  # une remise exclusive ne se cumule avec aucune autre
    reste = sous_total
    finales = []
    for r in retenues:
        montant = min(r["montant"], reste)
        reste -= montant
        finales.append({**r, "montant": montant})
    return finales, None
