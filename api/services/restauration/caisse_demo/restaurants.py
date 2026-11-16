"""[.mark] Module Restauration, lot 20 : les RESTAURANTS DE TEST de la caisse de démo (créés à l'écran, jamais dans le code).

Un restaurant de test porte : son nom et son état (ouvert, fermé, débordé), sa carte (format commun, importée d'un fichier ou d'une photo, ou écrite
à la main), ses ruptures, ses clients connus, ses réglages (horaires, temps de préparation, adresse du point de vente, et ce que la caisse a écrit dans son catalogue : remises, frais),
son comportement (``moteur.py``) et son scénario. Tout est borné à l'organisation du Labo qui l'a créé. **Une seule source par donnée (M53, Evan 16/11)** : la caisse de démo simule une caisse et ne porte que ce qu'une caisse porte (``DONNEES_DE_LA_CAISSE``).
Zones de livraison, minimums, délais par zone, types de commande et moyens de paiement du restaurant, réservations : le MODULE (classeur) les tient (``DONNEES_DU_MODULE``),
et c'est l'agent, par le module, qui vérifie la livraison ; la caisse reçoit la commande sans aucun contrôle de zone. Le jeton de sa caisse n'est montré qu'une fois (au
branchement) et n'est gardé qu'en empreinte.
"""

from __future__ import annotations

import copy
import secrets
from typing import Any

from api.db import db_client
from api.db.bases_clients.horloge import horloge
from api.services.restauration.caisse_demo import messages
from api.services.restauration.caisse_demo.catalogue import carte_vide
from api.services.restauration.caisse_demo.moteur import CONTROLES, empreinte_du_jeton
from api.services.restauration.prises import hubrise_traduction as ht

# M53 : ce qu'une caisse porte (carte, prix, ruptures, état, temps de préparation, horaires) ; le reste vit dans le module, jamais ici.
DONNEES_DE_LA_CAISSE = frozenset({"enseigne", "adresse", "code_postal", "ville", "delai", "horaires", "remises", "frais", "reprise"})
DONNEES_DU_MODULE = frozenset({"zones", "minimum", "delai_de_zone", "types_de_commande", "paiements", "reservations"})
ETATS = ("ouvert", "ferme", "deborde")
REPONSES = ("accepte", "controle", "silence", "panne")
ACCEPTATIONS = ("auto", "manuelle", "refus")
NOM_MAX = 120
DELAI_PAR_DEFAUT_S = 0.4  # le temps de réponse d'une caisse neuve (maquette F11)


class RestaurantDeTestRefuse(ValueError):
    """Une valeur refusée (liste fermée, taille) : le texte dit quoi, jamais un détail interne."""


def _reglages_par_defaut() -> dict[str, Any]:
    return {
        "enseigne": None, "adresse": "1 rue de Test", "code_postal": "60000", "ville": "Beauvais", "delai": 20, "horaires": None,
        "remises": [], "frais": [], "reprise": None,
    }


JOURS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
COUPURE = 6 * 60  # ``cutoff_time`` de la caisse de démo (« 06:00 ») : une fin avant elle est du même jour (« 18:00 » à « 01:00 »)


def _minutes(texte: Any) -> int:
    if not isinstance(texte, str) or len(texte) != 5 or texte[2] != ":" or not (texte[:2] + texte[3:]).isdigit():
        raise RestaurantDeTestRefuse("Horaires : une heure s'écrit HH:mm.")
    h, m = int(texte[:2]), int(texte[3:])
    if h > 23 or m > 59:
        raise RestaurantDeTestRefuse("Horaires : une heure s'écrit HH:mm.")
    return h * 60 + m


def horaires_valides(horaires: Any) -> dict[str, list[dict[str, str]]] | None:
    """Les horaires au format ``OpeningHours`` de HubRise (documentation publique, Locations) : ``null`` (non posés), ou des jours (``monday``...) portant des créneaux
    ``{from, to}`` en ``HH:mm``. Un jour absent est fermé ; au moins un créneau dans la semaine ; ``to`` suit ``from`` (ou tombe avant la coupure de 06:00 : même jour) ;
    aucun chevauchement dans un même jour. Refusé avec la raison, jamais corrigé en silence."""
    if horaires is None:
        return None
    if not isinstance(horaires, dict) or set(horaires) - set(JOURS):
        raise RestaurantDeTestRefuse("Horaires : les jours sont monday à sunday.")
    propres: dict[str, list[dict[str, str]]] = {}
    for jour in JOURS:
        creneaux = horaires.get(jour) or []
        if not isinstance(creneaux, list) or len(creneaux) > 6:
            raise RestaurantDeTestRefuse("Horaires : une liste de 6 créneaux au plus par jour.")
        plages = []
        for c in creneaux:
            if not isinstance(c, dict) or set(c) != {"from", "to"}:
                raise RestaurantDeTestRefuse("Horaires : un créneau a un from et un to.")
            debut, fin = _minutes(c["from"]), _minutes(c["to"])
            if fin <= debut:
                if fin > COUPURE:
                    raise RestaurantDeTestRefuse("Horaires : la fin doit suivre le début.")
                fin += 24 * 60
            plages.append((debut, fin, {"from": c["from"], "to": c["to"]}))
        plages.sort(key=lambda x: x[0])
        if any(a[1] > b[0] for a, b in zip(plages, plages[1:])):
            raise RestaurantDeTestRefuse("Horaires : deux créneaux d'un même jour se chevauchent.")
        if plages:
            propres[jour] = [p[2] for p in plages]
    if not propres:
        raise RestaurantDeTestRefuse("Horaires : au moins un créneau dans la semaine.")
    return propres


def comportement_valide(c: dict[str, Any]) -> dict[str, Any]:
    """Un comportement aux valeurs de listes fermées ; ce qui n'y est pas est refusé (jamais ignoré en silence)."""
    if not isinstance(c, dict):
        raise RestaurantDeTestRefuse("Comportement : un objet.")
    permis = {"reponse", "controles", "delai_s", "acceptation", "doublon", "limite_commandes", "rupture_plein_appel", "carte_changee", "commande_deux_fois"}
    if set(c) - permis:
        raise RestaurantDeTestRefuse(f"Comportement : champs inconnus {sorted(set(c) - permis)}")
    propre: dict[str, Any] = {}
    if "reponse" in c:
        if c["reponse"] not in REPONSES:
            raise RestaurantDeTestRefuse("Comportement : réponse hors de la liste.")
        propre["reponse"] = c["reponse"]
    if "controles" in c:
        if not isinstance(c["controles"], list) or any(x not in CONTROLES for x in c["controles"]):
            raise RestaurantDeTestRefuse("Comportement : contrôles hors de la liste.")
        propre["controles"] = list(dict.fromkeys(c["controles"]))
    if "acceptation" in c:
        if c["acceptation"] not in ACCEPTATIONS:
            raise RestaurantDeTestRefuse("Comportement : acceptation hors de la liste.")
        propre["acceptation"] = c["acceptation"]
    if "delai_s" in c:
        if isinstance(c["delai_s"], bool) or not isinstance(c["delai_s"], (int, float)) or not 0 <= c["delai_s"] <= 60:
            raise RestaurantDeTestRefuse("Comportement : délai de 0 à 60 secondes.")
        propre["delai_s"] = c["delai_s"]
    if "doublon" in c:
        propre["doublon"] = bool(c["doublon"])
    if "rupture_plein_appel" in c:
        v = c["rupture_plein_appel"]
        if v not in (None, False) and (not isinstance(v, str) or not v or len(v) > 80):
            raise RestaurantDeTestRefuse("Comportement : la rupture en plein appel vise un produit (son identifiant) ou « auto ».")
        if v:
            propre["rupture_plein_appel"] = v
    for cle in ("carte_changee", "commande_deux_fois"):
        if cle in c:
            propre[cle] = bool(c[cle])
    if "limite_commandes" in c:
        if isinstance(c["limite_commandes"], bool) or not isinstance(c["limite_commandes"], int) or not 1 <= c["limite_commandes"] <= 600:
            raise RestaurantDeTestRefuse("Comportement : limite de 1 à 600 par minute.")
        propre["limite_commandes"] = c["limite_commandes"]
    return propre


def _nom(nom: Any) -> str:
    propre = " ".join(str(nom or "").split())[:NOM_MAX]
    if not propre:
        raise RestaurantDeTestRefuse("Un nom est nécessaire.")
    return propre


async def creer(organization_id: int, nom: str, *, carte: dict[str, Any] | None = None, reglages: dict[str, Any] | None = None, comportement: dict[str, Any] | None = None,
                etat: str = "ouvert", clients: list[dict[str, Any]] | None = None, scenario: str | None = None) -> dict[str, Any]:
    if etat not in ETATS:
        raise RestaurantDeTestRefuse("État hors de la liste.")
    if carte is not None and carte.get("format") != ht.FORMAT_CARTE:
        raise RestaurantDeTestRefuse(f"Carte : le format commun ({ht.FORMAT_CARTE}) est attendu.")
    compte = "t" + secrets.token_hex(3)
    return await db_client.creer_restaurant_de_demo(
        organization_id, _nom(nom), f"{compte}-0", horloge(organization_id).maintenant(), etat=etat, carte=copy.deepcopy(carte) if carte else carte_vide(),
        reglages={**_reglages_par_defaut(), **(reglages or {})}, comportement=comportement_valide(comportement if comportement is not None else {"delai_s": DELAI_PAR_DEFAUT_S}), clients=clients or [], scenario=scenario,
    )


async def donner_un_jeton(organization_id: int, restaurant_id: int) -> str:
    """Un jeton NEUF pour la caisse de ce restaurant (l'ancien cesse de valoir). Rendu une seule fois ; seule son empreinte est gardée."""
    jeton = "demo_" + secrets.token_urlsafe(32)
    ok = await db_client.modifier_restaurant_de_demo(organization_id, restaurant_id, {"jeton_empreinte": empreinte_du_jeton(jeton)}, horloge(organization_id).maintenant())
    if ok is None:
        raise RestaurantDeTestRefuse("Restaurant de test introuvable.")
    return jeton


async def regler(organization_id: int, restaurant_id: int, champs: dict[str, Any]) -> dict[str, Any] | None:
    """Change ce qui se règle à l'écran : nom, état, minutes en plus, réglages (fusionnés), comportement (validé), clients, carte (format commun)."""
    actuel = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if actuel is None:
        return None
    voulu: dict[str, Any] = {}
    if "nom" in champs:
        voulu["nom"] = _nom(champs["nom"])
    if "etat" in champs:
        if champs["etat"] not in ETATS:
            raise RestaurantDeTestRefuse("État hors de la liste.")
        voulu["etat"] = champs["etat"]
    if "minutes_en_plus" in champs:
        if isinstance(champs["minutes_en_plus"], bool) or not isinstance(champs["minutes_en_plus"], int) or not 0 <= champs["minutes_en_plus"] <= 240:
            raise RestaurantDeTestRefuse("Minutes en plus : de 0 à 240.")
        voulu["minutes_en_plus"] = champs["minutes_en_plus"]
    if "reglages" in champs:
        if not isinstance(champs["reglages"], dict):
            raise RestaurantDeTestRefuse("Réglages : un objet.")
        if set(champs["reglages"]) & DONNEES_DU_MODULE:
            raise RestaurantDeTestRefuse("Réglages : zones, minimums, types de commande et moyens de paiement se règlent dans le module (Restauration), pas dans la caisse.")
        if set(champs["reglages"]) - set(_reglages_par_defaut()):
            raise RestaurantDeTestRefuse("Réglages : champs inconnus.")
        if "horaires" in champs["reglages"]:
            champs["reglages"] = {**champs["reglages"], "horaires": horaires_valides(champs["reglages"]["horaires"])}
        voulu["reglages"] = {**actuel["reglages"], **champs["reglages"]}
    if "comportement" in champs:
        voulu["comportement"] = comportement_valide(champs["comportement"])
        voulu["reglages"] = {**voulu.get("reglages", actuel["reglages"]), "prix_change_fait": False}  # un imprévu « carte changée » se redéclenche à chaque mise en place
    if "clients" in champs:
        if not isinstance(champs["clients"], list) or len(champs["clients"]) > 200:
            raise RestaurantDeTestRefuse("Clients connus : une liste de 200 au plus.")
        voulu["clients"] = champs["clients"]
    if "carte" in champs:
        if champs["carte"].get("format") != ht.FORMAT_CARTE:
            raise RestaurantDeTestRefuse(f"Carte : le format commun ({ht.FORMAT_CARTE}) est attendu.")
        voulu["carte"] = champs["carte"]
    return await db_client.modifier_restaurant_de_demo(organization_id, restaurant_id, voulu, horloge(organization_id).maintenant()) if voulu else actuel


async def dupliquer(organization_id: int, restaurant_id: int, nom: str | None = None) -> dict[str, Any] | None:
    source = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if source is None:
        return None
    return await creer(
        organization_id, nom or f"{source['nom']} (copie)", carte=source["carte"], reglages=source["reglages"], comportement=source["comportement"], etat=source["etat"],
        clients=source["clients"], scenario=source["scenario"],
    )


# --------------------------------------------------------------------------- les gestes « en plein appel » : la caisse le dit par un message signé


def _trouver(carte: dict[str, Any], code: str) -> list[dict[str, Any]]:
    trouves = [d for p in carte.get("produits", []) for d in p.get("declinaisons", []) if d.get("code_caisse") == code]
    return trouves + [o for g in carte.get("groupes", []) for o in g.get("options", []) if o.get("code_caisse") == code]


async def poser_une_rupture(organization_id: int, restaurant_id: int, code: str, disponible: bool) -> bool:
    """Un produit (ou une option) passe en rupture, ou revient, PAR LA CAISSE : message ``inventory.patch`` signé, comme une vraie caisse."""
    r = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if r is None or not _trouver(r["carte"], code):
        return False
    stocks = [s for s in r["stocks"] if (s.get("sku_ref") or s.get("option_ref")) != code]
    if not disponible:
        genre = "sku_ref" if any(d.get("code_caisse") == code for p in r["carte"].get("produits", []) for d in p.get("declinaisons", [])) else "option_ref"
        stocks.append({genre: code, "stock": "0.0", "expires_at": None})
    r = await db_client.modifier_restaurant_de_demo(organization_id, restaurant_id, {"stocks": stocks}, horloge(organization_id).maintenant())
    await messages.poster(r, "inventory", "patch", catalog_id=r["point_de_vente"].rsplit("-", 1)[0] + "-cat")
    return True


async def changer_un_prix(organization_id: int, restaurant_id: int, code: str, prix: int) -> bool:
    """Le prix change PAR LA CAISSE pendant l'appel : message ``catalog.update`` signé (la carte est relue par la prise)."""
    r = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if r is None or isinstance(prix, bool) or not isinstance(prix, int) or prix < 0:
        return False
    carte = copy.deepcopy(r["carte"])
    cibles = _trouver(carte, code)
    if not cibles:
        return False
    for c in cibles:
        c["prix"] = prix
    r = await db_client.modifier_restaurant_de_demo(organization_id, restaurant_id, {"carte": carte}, horloge(organization_id).maintenant())
    await messages.poster(r, "catalog", "update", catalog_id=r["point_de_vente"].rsplit("-", 1)[0] + "-cat")
    return True


async def changer_l_etat_par_la_caisse(organization_id: int, restaurant_id: int, etat: str, minutes_en_plus: int = 0) -> bool:
    """L'état du restaurant change PAR LA CAISSE (ouvert, débordé, fermé) : message ``location.update`` signé."""
    if etat not in ETATS:
        return False
    r = await db_client.modifier_restaurant_de_demo(organization_id, restaurant_id, {"etat": etat, "minutes_en_plus": minutes_en_plus if etat == "deborde" else 0}, horloge(organization_id).maintenant())
    if r is None:
        return False
    await messages.poster(r, "location", "update")
    return True


async def changer_une_commande(organization_id: int, restaurant_id: int, ref: str, statut: str | None = None, heure_confirmee: str | None = None) -> bool:
    """La caisse fait avancer une commande (``accepted``, ``in_preparation``, ``rejected``…) ou change son heure : message ``order.update`` signé."""
    r = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    ligne = await db_client.lire_commande_de_demo(r["id"], ref) if r else None
    if r is None or ligne is None:
        return False
    corps = dict(ligne["corps"])
    if statut:
        corps["status"] = statut
    if heure_confirmee:
        corps["confirmed_time"] = heure_confirmee
    await db_client.modifier_commande_de_demo(r["id"], ref, corps["status"], corps, horloge(organization_id).maintenant())
    await messages.poster(r, "order", "update", order_id=ref, new_state={"status": corps["status"]})
    return True
