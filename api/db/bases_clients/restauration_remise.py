"""[.mark] Module Restauration, lot 2 : les remises applicables, chiffrées (contrat § 4, plan § 3.8, E-52).

Règle unique (§ 3.8) : le comptoir calcule l'effet exact de la remise ; la commande part avec les articles à leur prix
de carte et UNE ligne de remise chiffrée par remise appliquée (nom, montant, référence de caisse si elle existe).

Chiffrés ici : ``pourcentage``, ``montant``, ``seuil_panier`` (minimum de panier), ``creneau`` (jours et heures).
Les autres mécanismes (X achetés = Y offert, 2e à moitié prix, prix du jour, passage en menu, taille supérieure,
offre famille, nouveauté, fidélité) se lisent mais restent ``chiffree = False`` : le lot 7 les chiffre. Une remise non
chiffrée n'est JAMAIS appliquée ni annoncée.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients.restauration_carte import _json, disponible_a
from api.db.bases_clients.restauration_commun import fuseau_de

MECANISMES_CHIFFRES = frozenset({"pourcentage", "montant", "seuil_panier", "creneau"})


def _effet(effet: dict, sous_total: int) -> int | None:
    """Le montant en centimes (entier, arrondi à l'unité la plus proche, jamais au-delà du sous-total), ou ``None``."""
    if "pourcentage" in effet:
        pct = effet["pourcentage"]
        if not isinstance(pct, (int, float)) or not 0 < pct <= 100:
            return None
        return min(sous_total, (int(sous_total * pct * 100) + 5000) // 10000)
    if "montant" in effet:
        montant = effet["montant"]
        if not isinstance(montant, int) or montant <= 0:
            return None
        return min(sous_total, montant)
    return None


async def remises_applicables(
    connexion: asyncpg.Connection, etablissement_id: int, panier: dict, moment: datetime, client: dict | None = None
) -> list[dict]:
    """Les remises ACTIVES de l'établissement, valables à ce moment pour ce panier, avec leur effet chiffré.

    ``panier`` : ``{"mode": ..., "sous_total": centimes}``. ``client`` : réservé à la fidélité (lot 7). Chaque ligne :
    ``{ref, nom, mecanisme, montant, chiffree, cumul, phrase, ref_caisse}``. ``montant`` vaut ``None`` quand la remise
    ne s'applique pas à ce panier (hors seuil, hors créneau, hors mode) ou n'est pas encore chiffrée."""
    if moment.tzinfo is None:
        raise ValueError("Le moment doit être aware.")
    local = moment.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id)))
    sous_total = int(panier.get("sous_total", 0))
    mode = panier.get("mode")
    lignes = await connexion.fetch(
        "SELECT * FROM mark.resto_remise WHERE site_id = $1 AND etat = 'active' "
        "AND (debut IS NULL OR debut <= $2) AND (fin IS NULL OR fin > $2) ORDER BY id",
        etablissement_id,
        moment,
    )
    sortie = []
    for r in lignes:
        declencheur, effet, perimetre = _json(r["declencheur"]) or {}, _json(r["effet"]) or {}, _json(r["perimetre"]) or {}
        chiffree = r["mecanisme"] in MECANISMES_CHIFFRES
        montant: int | None = None
        if chiffree:
            dans_le_moment = disponible_a(_json(r["moment"]), local)
            dans_le_mode = not perimetre.get("modes") or mode in perimetre["modes"]
            au_dessus_du_seuil = sous_total >= int(declencheur.get("minimum", 0))
            if r["mecanisme"] == "seuil_panier" and "minimum" not in declencheur:
                au_dessus_du_seuil = False  # un seuil sans minimum ne s'applique à rien
            if dans_le_moment and dans_le_mode and au_dessus_du_seuil:
                montant = _effet(effet, sous_total)
        sortie.append(
            {
                "ref": r["ref"] or str(r["id"]), "id": r["id"], "nom": r["nom"], "mecanisme": r["mecanisme"],
                "montant": montant, "chiffree": chiffree, "cumul": r["cumul"], "phrase": r["phrase"],
                "ref_caisse": r["ref_caisse"],
            }
        )
    return sortie


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
