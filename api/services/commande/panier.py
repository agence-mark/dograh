"""[.mark] Mécanisme commun : l'état du panier pendant l'appel, dans la fiche de l'appel (``commande_panier``).

Un simple dictionnaire sérialisable : il survit à un compactage du contexte, il s'écrit avec la fiche, et une panne en emporte le contenu
(il se joint au message laissé à l'équipe, W24). Le modèle ne le voit jamais directement : il le lit par ``voir_commande``.

Une ligne : ``{n, ref, nom, code, quantite, choix, retires, note, attente}``. ``code`` vide : la déclinaison n'est pas choisie.
``attente`` : la question encore ouverte pour cette ligne (un choix obligatoire), jamais une ligne perdue (W16).
Toute modification du panier invalide la relecture déjà faite (``relecture`` redevient vide) : on ne confirme jamais ce qu'on n'a pas relu.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CLE = "commande_panier"


def nouveau() -> dict[str, Any]:
    return {
        "version": 0,
        "mode": None,
        "zone": None,  # {id, nom}
        "adresse": None,
        "heure_voulue": None,  # ISO, commande planifiée (lot 6)
        "lignes": [],
        "client": {},
        "paiement": None,
        "note": None,
        "relecture": None,  # {version, jeton, lignes, total}
        "vente_en_plus_faite": False,
        "enregistree": None,  # {numero, numero_court, heure_annoncee, total}
        "derniere_lecture": None,  # ce qui a été relu la dernière fois : après une correction, seul ce qui a changé est relu
        "derniere_lecture_mode": None,
        "consigne": None,  # une habitude à retenir pour le prochain appel, écrite à l'enregistrement
    }


def du_dossier(fiche: dict | None) -> dict[str, Any]:
    """Le panier de l'appel, créé au premier besoin. Sans fiche (un essai isolé) : un panier jetable."""
    if not isinstance(fiche, dict):
        return nouveau()
    existant = fiche.get(CLE)
    if not isinstance(existant, dict) or "lignes" not in existant:
        existant = fiche[CLE] = nouveau()
    return existant


def repartir_de_zero(fiche: dict | None) -> dict[str, Any]:
    """Un panier neuf (après une commande enregistrée : la suivante est une autre commande). Le client reste connu."""
    ancien = du_dossier(fiche)
    neuf = nouveau()
    neuf["client"] = dict(ancien.get("client") or {})
    neuf["mode"] = ancien.get("mode")
    neuf["zone"] = ancien.get("zone")
    neuf["adresse"] = ancien.get("adresse")
    if isinstance(fiche, dict):
        fiche[CLE] = neuf
    return neuf


def toucher(p: dict[str, Any]) -> None:
    """Le panier a changé : la version avance, la relecture et un éventuel enregistrement ne valent plus."""
    p["version"] += 1
    p["relecture"] = None
    for i, ligne in enumerate(p["lignes"], start=1):
        ligne["n"] = i


def a_completer(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [l for l in p["lignes"] if l.get("attente")]


def lignes_pretes(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [l for l in p["lignes"] if not l.get("attente") and l.get("code")]


def pour_le_chiffrage(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Les lignes complètes au format que la source chiffre : ``code``, ``quantite``, ``choix``, ``retires``, ``note``."""
    return [
        {"code": l["code"], "quantite": l["quantite"], "choix": l["choix"], "retires": list(l["retires"]), "note": l.get("note")}
        for l in lignes_pretes(p)
    ]


def empreinte(p: dict[str, Any]) -> str:
    """Ce qui fait qu'une relecture vaut encore : le mode, la zone, le moment voulu et chaque ligne, dans l'ordre."""
    contenu = {
        "mode": p["mode"], "zone": (p.get("zone") or {}).get("id"), "heure": p.get("heure_voulue"),
        "lignes": [(l["code"], l["quantite"], l["choix"], sorted(l["retires"]), l.get("note")) for l in lignes_pretes(p)],
    }
    return hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def resume(p: dict[str, Any]) -> dict[str, Any]:
    """Ce que chaque retour d'outil dit du panier (court : le détail est dans ``voir_commande``)."""
    return {
        "mode": p["mode"], "zone": (p.get("zone") or {}).get("nom"), "articles": sum(l["quantite"] for l in p["lignes"]),
        "a_completer": len(a_completer(p)),
    }
