"""[.mark] Module Restauration, lot 20 : les IMPRÉVUS PENDANT L'APPEL, déclenchés tout seuls par la caisse de démo (E-53, maquette F11 « Imprévus pendant l'appel »).

Trois comportements, éteints par défaut, qui se posent dans ``comportement`` du restaurant de test (comme une vraie caisse, par des messages signés) :

- ``rupture_plein_appel`` : un produit (son identifiant dans la carte ; ``"auto"`` : le premier de la carte) PASSE EN RUPTURE après avoir été ajouté au panier. Quand une commande qui le
  contient arrive, la caisse la reçoit puis la REFUSE et le dit : message ``order.update`` (refusée) et message ``inventory.patch`` (le produit n'est plus disponible). Une commande
  qui ne le contient pas n'est pas touchée ;
- ``carte_changee`` : un prix change ENTRE la lecture de la carte et l'envoi de la commande : à la première lecture de la carte pendant un essai, la caisse rend la carte telle qu'elle
  est, puis augmente de 0,50 EUR le prix du premier produit et le dit (message ``catalog.update``). Une seule fois par mise en place (``reglages.prix_change_fait``) ;
- ``commande_deux_fois`` : la caisse reçoit la commande DEUX fois (même ``private_ref``, deux identifiants) : de quoi voir si la plateforme sait reconnaître la sienne.

Aucune heure lue ici : la source d'heure de l'organisation (D6). Rien ne part vers un tiers : les messages sont écrits pour la prise, rendus par la tâche planifiée.
"""

from __future__ import annotations

import copy
from typing import Any

from api.db import db_client
from api.db.bases_clients.horloge import horloge
from api.services.restauration.caisse.caisse_demo import messages

SUPPLEMENT_DE_PRIX = 50  # centimes : « un prix change » de 0,50 EUR
AUTO = "auto"


def _catalogue(r: dict[str, Any]) -> str:
    return r["point_de_vente"].rsplit("-", 1)[0] + "-cat"


def _produit_vise(r: dict[str, Any]) -> dict[str, Any] | None:
    voulu = (r["comportement"] or {}).get("rupture_plein_appel")
    produits = (r["carte"] or {}).get("produits") or []
    if not voulu:
        return None
    if voulu == AUTO:
        return produits[0] if produits else None
    return next((p for p in produits if p.get("id") == voulu), None)


def _codes(produit: dict[str, Any]) -> set[str]:
    return {c for d in produit.get("declinaisons") or [] for c in (d.get("code_caisse"), d.get("id")) if c}


def rupture_visee(r: dict[str, Any], commande: dict[str, Any]) -> list[str]:
    """Les codes de caisse du produit visé que CETTE commande contient (vide : le comportement est éteint, ou la commande ne le contient pas)."""
    produit = _produit_vise(r)
    if produit is None:
        return []
    codes = _codes(produit)
    return [d["code_caisse"] for d in produit.get("declinaisons") or [] if d.get("code_caisse") and any(i.get("sku_ref") in codes for i in commande.get("items") or [])]


async def mettre_en_rupture(r: dict[str, Any], codes: list[str]) -> None:
    """Les codes passent en rupture (stock 0), dit par la caisse : message ``inventory.patch`` signé."""
    refaits = {c for c in codes}
    stocks = [s for s in r["stocks"] if (s.get("sku_ref") or s.get("option_ref")) not in refaits] + [{"sku_ref": c, "stock": "0.0", "expires_at": None} for c in sorted(refaits)]
    r2 = await db_client.modifier_restaurant_de_demo(r["organization_id"], r["id"], {"stocks": stocks}, horloge(r["organization_id"]).maintenant())
    await messages.poster(r2 or r, "inventory", "patch", catalog_id=_catalogue(r))


async def changer_un_prix_apres_la_lecture(r: dict[str, Any]) -> None:
    """À appeler APRÈS avoir rendu la carte lue : le prix du premier produit monte de 0,50 EUR (une seule fois), la caisse le dit (``catalog.update``)."""
    if not (r["comportement"] or {}).get("carte_changee") or (r["reglages"] or {}).get("prix_change_fait"):
        return
    carte = copy.deepcopy(r["carte"])
    cible = next((d for p in carte.get("produits") or [] for d in p.get("declinaisons") or []), None)
    if cible is None:
        return
    cible["prix"] = int(cible["prix"]) + SUPPLEMENT_DE_PRIX
    r2 = await db_client.modifier_restaurant_de_demo(
        r["organization_id"], r["id"], {"carte": carte, "reglages": {**r["reglages"], "prix_change_fait": True}}, horloge(r["organization_id"]).maintenant()
    )
    await messages.poster(r2 or r, "catalog", "update", catalog_id=_catalogue(r))


async def recevoir_une_seconde_fois(r: dict[str, Any], ordre: dict[str, Any], identifiant: str) -> None:
    """La même commande arrive une seconde fois : même ``private_ref``, un autre identifiant (la caisse n'a pas reconnu la première)."""
    maintenant = horloge(r["organization_id"]).maintenant()
    second = {**ordre, "id": identifiant}
    await db_client.ajouter_commande_de_demo(r["id"], identifiant, second.get("private_ref"), second["status"], second, maintenant)
