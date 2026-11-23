"""[.mark] Module Restauration, lot 3 : ce que le système fait quand une capacité manque (``fiches-capacites.md``, tableau).

UNE règle par capacité, lue sur la fiche : jamais un ``if prise == "hubrise"`` ailleurs (test de vocabulaire des fournisseurs
dans ``test_restauration_prises.py``). Les fonctions sont pures.

| Capacité absente | Ce que le système fait |
|---|---|
| ``etat_restaurant`` non lu | le portail et la fiche établissement font foi (le plus prudent gagne) : ``source_de_l_etat`` |
| ``etapes`` sans ``acceptee`` | l'outil rend ``TRANSMISE``, jamais « acceptée » : ``statut_pour_l_outil`` |
| ``notifications = interrogation`` | une tâche planifiée interroge : ``mode_de_veille`` |
| ``represente`` sans ``imbrication`` | choix imbriqués aplatis à l'envoi : ``adapter_commande`` |
| ``represente`` sans ``second_telephone`` | second numéro dans la note de commande : ``adapter_commande`` |
| ``represente`` sans ``plusieurs_paiements`` | paiement mixte écrit dans la note : ``adapter_commande`` |
| ``represente`` sans ``retrait`` | ingrédients retirés écrits dans la note de la ligne : ``adapter_commande`` |
| ``anti_doublon = chercher_avant_renvoi`` | avant tout renvoi, recherche par notre numéro : ``doit_chercher_avant_renvoi`` |
| ``clients_lus`` faux | client reconnu par notre base seulement : ``client_lu_par_la_prise`` |
| ``remises_lues`` faux | le portail est maître des remises : ``maitre_des_remises`` |
"""

from __future__ import annotations

import copy
from typing import Any

from api.services.actions_communes.euros import en_euros
from api.services.restauration.caisse.prises.capacites import Capacites


def source_de_l_etat(capacites: Capacites) -> str:
    """Qui porte l'état du restaurant : ``caisse`` si la prise le lit, sinon ``portail`` (la fiche établissement aussi)."""
    return "caisse" if capacites.lit_l_etat else "portail"


def statut_pour_l_outil(capacites: Capacites, etape: str | None) -> str:
    """Le statut que l'outil rend après l'envoi. ``TRANSMISE`` tant que la prise ne sait pas dire « acceptée » (ou n'en
    est pas là) : jamais « acceptée » inventé. ``OK`` seulement quand la prise dit que la commande est prise en charge."""
    if "acceptee" in capacites.etapes and etape in ("acceptee", "en_preparation", "prete", "terminee"):
        return "OK"
    return "TRANSMISE"


def mode_de_veille(capacites: Capacites) -> str:
    """Comment on apprend un changement : ``notification`` (signée, reçue), ``interrogation`` (tâche planifiée) ou ``aucun``."""
    return {"signees": "notification", "interrogation": "interrogation", "aucune": "aucun"}[capacites.notifications]


def doit_chercher_avant_renvoi(capacites: Capacites) -> bool:
    return capacites.anti_doublon == "chercher_avant_renvoi"


def client_lu_par_la_prise(capacites: Capacites) -> bool:
    return capacites.clients_lus


def maitre_des_remises(capacites: Capacites) -> str:
    return "caisse" if capacites.remises_lues else "portail"


def _aplatir(choix: list[dict]) -> list[dict]:
    plats: list[dict] = []
    for c in choix or []:
        plats.append({k: v for k, v in c.items() if k != "choix"})
        plats.extend(_aplatir(c.get("choix") or []))
    return plats


def _aplatir_une_formule(choix: list[dict]) -> list[dict]:
    """Une ligne de formule : ses choix SONT ses articles (un produit par étape), pas une imbrication à défaire. Seuls les choix posés sous chaque article (suppléments,
    sauces) sont mis à plat, sous cet article : les aplatir avec les articles en ferait des produits de plus au lieu des options de l'article (lot 19 bis, K3)."""
    return [{**c, "choix": _aplatir(c.get("choix") or [])} if c.get("choix") else c for c in choix]


def adapter_commande(capacites: Capacites, commande: dict[str, Any]) -> dict[str, Any]:
    """La commande du format commun, ramenée à ce que la prise représente. N'écrit jamais dans l'argument."""
    c = copy.deepcopy(commande)
    ajouts: list[str] = []
    represente = capacites.represente
    for ligne in c.get("lignes") or []:
        if "imbrication" not in represente and ligne.get("choix"):
            ligne["choix"] = _aplatir_une_formule(ligne["choix"]) if ligne.get("formule_id") else _aplatir(ligne["choix"])
        if "retrait" not in represente and ligne.get("retires"):
            reste = f"Sans : {', '.join(ligne['retires'])}"
            ligne["note"] = f"{ligne['note']} ; {reste}" if ligne.get("note") else reste
            ligne["retires"] = []
    client = c.get("client") or {}
    second = client.get("second_numero")
    if second and "second_telephone" not in represente:
        detail = " ".join(x for x in (second.get("qui"), second.get("pourquoi")) if x)
        ajouts.append(f"Second numéro : {second['numero']}" + (f" ({detail})" if detail else ""))
        client["second_numero"] = None
    paiement = c.get("paiement") or {}
    moyens = paiement.get("moyens") or []
    if len(moyens) > 1 and "plusieurs_paiements" not in represente:
        ajouts.append("Paiement mixte : " + " + ".join(f"{m['moyen']} {en_euros(m['montant'])}" for m in moyens))
        paiement["moyens"] = []
    if ajouts:
        note = c.get("note")
        c["note"] = " | ".join(([note] if note else []) + ajouts)
    return c
