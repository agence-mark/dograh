"""[.mark] Module Restauration, lot 2 : les commandes dans le classeur (contrat § 3, § 4).

``enregistrer_commande`` (recalcule TOUT depuis la carte ; un manque à la fois ; verrou anti-doublon),
``changer_statut`` (chemin fermé, ``DEJA_FAIT``), ``statut_commande``, ``commandes_planifiees``.

Montants en centimes, entiers. Le total du modèle n'est jamais pris : un prix donné qui diffère de la carte est refusé
(``prix_different``). L'heure vient de la source d'heure de l'organisation (D6). L'envoi à la caisse n'est PAS fait ici :
``declencher_envoi`` (un appelant, lot 9 et 10) est appelé APRÈS l'enregistrement validé, avec le numéro pour clé de
tâche (``_job_id`` = numéro : rejouable sans effet double).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients.annonce_heure import dite
from api.db.bases_clients.dates_futures import jour_dit
from api.db.bases_clients.restauration_carte import carte_du_restaurant, etat_combine, ruptures_du_restaurant
from api.db.bases_clients.restauration_commun import MODES, SOURCES, Resultat, fuseau_de, maintenant, poser_session
from api.db.bases_clients.restauration_remise import remises_applicables, retenir
from api.db.bases_clients.restauration_temps import annonce_pour, creneau_complet

E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")
STATUTS_FINAUX = frozenset({"terminee", "refusee", "annulee", "echec"})

# § 3 : nouvelle → envoyee → recue → acceptee → en_preparation → prete → terminee ; sorties refusee, annulee, echec.
# Une prise remplit ce qu'elle sait : on peut sauter des étapes vers l'avant, jamais revenir en arrière.
CHAINE = ("nouvelle", "envoyee", "recue", "acceptee", "en_preparation", "prete", "terminee")
TRANSITIONS: dict[str, frozenset[str]] = {
    **{etape: frozenset(CHAINE[i + 1 :]) for i, etape in enumerate(CHAINE)},
}
TRANSITIONS["nouvelle"] |= {"refusee", "annulee", "echec"}
TRANSITIONS["envoyee"] |= {"refusee", "annulee", "echec"}
TRANSITIONS["recue"] |= {"refusee", "annulee"}
TRANSITIONS["acceptee"] |= {"annulee"}
TRANSITIONS["en_preparation"] |= {"annulee"}
TRANSITIONS["prete"] |= {"annulee"}
TRANSITIONS["echec"] = frozenset({"envoyee"})  # le renvoi, par la tâche de rattrapage
for _final in ("refusee", "annulee"):
    TRANSITIONS[_final] = frozenset()


# T-06 : un groupe « moitiés » (deux choix exactement) ; la règle de prix est un réglage de l'agent (``commande_moities_prix``), la plus chère par défaut.
REGLES_MOITIES = ("plus_chere", "moyenne", "somme")


def _prix_des_moities(prix: list[int], regle: str) -> int:
    if not prix:
        return 0
    if regle == "somme":
        return sum(prix)
    if regle == "moyenne":
        return -(-sum(prix) // len(prix))  # arrondi vers le haut, au centime
    return max(prix)


def statut_de_fermeture(raison: str | None) -> str:
    """Le statut fermé (§ 5 du contrat) que rend une raison de fermeture de ``etat_combine``."""
    if raison == "livraison_terminee":
        return "LIVRAISON_TERMINEE"
    return "PAUSE_TYPE" if raison in ("pause_type", "pause_force", "caisse_pause", "fin_du_jour", "type_ferme") else "FERME"


def _refus(statut: str, suggestion: str, manque: str | None = None, **faits: Any) -> Resultat:
    return Resultat(statut, faits, suggestion, manque)


# --------------------------------------------------------------------------- #
# Le calcul d'un panier depuis la carte
# --------------------------------------------------------------------------- #


class _Panier:
    """Les index de la carte au moment de la commande (le même calcul pour toute commande)."""

    def __init__(self, carte: dict, mode: str, ruptures: set[str], regle_moities: str = "plus_chere"):
        self.mode = mode
        self.ruptures = ruptures
        self.regle_moities = regle_moities if regle_moities in REGLES_MOITIES else "plus_chere"
        self.groupes = {g["id"]: g for g in carte["groupes"]}
        self.produits = {p["id"]: p for p in carte["produits"]}
        self.decl: dict[str, tuple[dict, dict]] = {}
        for p in carte["produits"]:
            for d in p["declinaisons"]:
                if d["vendable"]:
                    self.decl[d["code_caisse"]] = (p, d)
        self.formules = {f["code_caisse"]: f for f in carte["formules"] if f["vendable"]}
        self.enfants: dict[str, list[dict]] = {}
        for g in carte["groupes"]:
            if g["parent_option_id"]:
                self.enfants.setdefault(g["parent_option_id"], []).append(g)

    def prix(self, d: dict) -> int:
        par_mode = d.get("prix_par_mode") or {}
        return par_mode.get(self.mode, d["prix"])


def _choix(panier: _Panier, groupes: list[dict], choisis: list[dict], quantite_ligne: int, rendu: list[dict]):
    """Vérifie et chiffre les choix d'un niveau. Rend ``(supplement_unitaire, None)`` ou ``(0, Resultat)``."""
    options: dict[str, tuple[dict, dict]] = {}
    for g in groupes:
        for o in g["options"]:
            if o["vendable"]:
                options.setdefault(o["code_caisse"], (g, o))
    par_groupe: dict[str, int] = {}
    par_option: dict[str, int] = {}
    supplement = 0
    moities: list[int] = []  # les prix des options d'un groupe « moitiés » : la règle choisit, ils ne s'additionnent pas
    for c in choisis:
        code = c.get("option_code")
        trouve = options.get(code)
        if trouve is None:
            return 0, _refus("HORS_CARTE", "Ce choix n'existe pas pour ce produit.", code=code)
        g, o = trouve
        n = c.get("quantite", 1)
        if not isinstance(n, int) or n < 1:
            return 0, _refus("ARGUMENT_INVALIDE", "Quantité de choix invalide.", "quantite", code=code)
        if code in panier.ruptures:
            return 0, _refus("RUPTURE", f"{o['nom']} n'est plus disponible.", code=code, nom=o["nom"])
        par_groupe[g["id"]] = par_groupe.get(g["id"], 0) + n
        par_option[code] = par_option.get(code, 0) + n
        if par_option[code] > g["max_par_option"]:
            return 0, _refus("MAXIMUM_ATTEINT", f"{o['nom']} ne se prend pas plus de {g['max_par_option']} fois.", groupe=g["id"], code=code)
        if g["role"] == "moities":
            moities.extend([o["prix"]] * n)
        else:
            supplement += o["prix"] * n
        sous = []
        enfants = panier.enfants.get(o["id"], [])
        gain, erreur = _choix(panier, enfants, c.get("choix") or [], quantite_ligne, sous)
        if erreur:
            return 0, erreur
        supplement += gain * n
        rendu.append({"option_code": code, "quantite": n, "choix": sous})
    supplement += _prix_des_moities(moities, panier.regle_moities)
    for g in groupes:
        n = par_groupe.get(g["id"], 0)
        if n < g["min"]:
            return 0, _refus("CHOIX_OBLIGATOIRE", f"Il faut choisir : {g['nom']}.", groupe=g["id"], nom=g["nom"], minimum=g["min"])
        if n > g["max"]:
            return 0, _refus("MAXIMUM_ATTEINT", f"Pas plus de {g['max']} pour : {g['nom']}.", groupe=g["id"], nom=g["nom"], maximum=g["max"])
    return supplement, None


def _formule(panier: _Panier, f: dict, choisis: list[dict]) -> Resultat | None:
    """Chaque ligne de la formule reçoit exactement un choix (un code de caisse de la liste, ou d'une catégorie permise)."""
    restants = list(choisis)
    for ligne in f["lignes"]:
        correspond = None
        for c in restants:
            code = c.get("option_code")
            produit_decl = panier.decl.get(code)
            if code in (ligne.get("codes") or []):
                correspond = c
            elif produit_decl and produit_decl[0]["categorie_id"] in (ligne.get("categories") or []):
                if not ligne.get("declinaison") or produit_decl[1]["nom"] == ligne["declinaison"]:
                    correspond = c
            if correspond:
                break
        if correspond is None:
            return _refus("CHOIX_OBLIGATOIRE", f"Il faut choisir : {ligne['nom']}.", groupe=ligne["nom"], nom=ligne["nom"], minimum=1)
        restants.remove(correspond)
        if correspond["option_code"] in panier.ruptures:
            return _refus("RUPTURE", "Un élément de la formule n'est plus disponible.", code=correspond["option_code"])
    if restants:
        return _refus("HORS_CARTE", "Ce choix n'existe pas dans cette formule.", code=restants[0].get("option_code"))
    return None


def _lignes(panier: _Panier, brouillon_lignes: list[dict]) -> tuple[list[dict], int, Resultat | None]:
    calculees: list[dict] = []
    sous_total = 0
    for rang, l in enumerate(brouillon_lignes, start=1):
        code, n = l.get("code_caisse"), l.get("quantite", 1)
        if not isinstance(n, int) or not 1 <= n <= 99:
            return [], 0, _refus("ARGUMENT_INVALIDE", "Quantité invalide.", "quantite", ligne=rang)
        formule = panier.formules.get(code)
        if code in panier.decl:
            produit, d = panier.decl[code]
            nom = produit["nom"] + (f" {d['nom']}" if len(produit["declinaisons"]) > 1 else "")
            base = panier.prix(d)
            groupes = [panier.groupes[g] for g in produit["groupes"] if g in panier.groupes and panier.groupes[g]["parent_option_id"] is None]
            retirables = {i["nom"] for i in produit["ingredients"] if i.get("retirable")}
            erreur_f = None
        elif formule is not None:
            nom, base, groupes, retirables = formule["nom"], formule["prix"], [], set()
            erreur_f = _formule(panier, formule, l.get("choix") or [])
        else:
            return [], 0, _refus("HORS_CARTE", "Ce produit n'est pas à la carte.", code=code)
        if code in panier.ruptures:
            return [], 0, _refus("RUPTURE", f"{nom} n'est plus disponible.", code=code, nom=nom)
        if l.get("prix_unitaire") is not None and l["prix_unitaire"] != base:
            return [], 0, _refus("REFUSEE", "Le prix ne correspond pas à la carte.", raison="prix_different", code=code)
        if erreur_f:
            return [], 0, erreur_f
        inconnus = [r for r in (l.get("retires") or []) if r not in retirables]
        if inconnus:
            return [], 0, _refus("HORS_CARTE", f"On ne peut pas retirer : {inconnus[0]}.", code=code, retire=inconnus[0])
        rendu: list[dict] = []
        if formule is not None:
            rendu = [{"option_code": c["option_code"], "quantite": c.get("quantite", 1), "choix": []} for c in (l.get("choix") or [])]
            supplement = 0
        else:
            supplement, erreur = _choix(panier, groupes, l.get("choix") or [], n, rendu)
            if erreur:
                return [], 0, erreur
        unitaire = base + supplement
        sous_total += unitaire * n
        calculees.append(
            {"code_caisse": code, "nom": nom, "prix_unitaire": unitaire, "quantite": n, "note": l.get("note"),
             "choix": rendu, "retires": list(l.get("retires") or []), "formule_id": formule["id"] if formule else None}
        )
    return calculees, sous_total, None


async def _zone_de_livraison(connexion: asyncpg.Connection, etablissement_id: int, zone_id: int | None, sous_total: int):
    """La zone de CET établissement (jamais celle d'un autre : relue avec l'établissement), son minimum et ses frais pour ce sous-total.
    Rend ``(zone, frais, None)`` ou ``(None, 0, Resultat)`` : ``HORS_ZONE`` ou ``MINIMUM_NON_ATTEINT``."""
    zone = await connexion.fetchrow("SELECT * FROM mark.resto_zone WHERE id = $1 AND site_id = $2", zone_id, etablissement_id) if zone_id else None
    if zone is None:
        return None, 0, _refus("HORS_ZONE", "Nous ne livrons pas à cette adresse.")
    if sous_total < zone["minimum"]:
        return None, 0, _refus(
            "MINIMUM_NON_ATTEINT", f"Le minimum de commande est de {zone['minimum'] / 100:.2f} euros.".replace(".", ","),
            minimum=zone["minimum"], sous_total=sous_total,
        )
    frais = 0 if zone["gratuite_des"] is not None and sous_total >= zone["gratuite_des"] else zone["frais"]
    return zone, frais, None


async def chiffrer_panier(
    connexion: asyncpg.Connection, etablissement_id: int, mode: str, lignes: list[dict], zone_id: int | None = None,
    moment: datetime | None = None, regle_moities: str = "plus_chere",
) -> Resultat:
    """[.mark] Lot 5 : le panier chiffré DEPUIS LA CARTE, comme le fera ``enregistrer_commande`` (mêmes fonctions), sans rien écrire.
    ``OK`` (``lignes`` avec leur prix de carte et leurs suppléments, ``sous_total``, ``frais``, ``total``, ``delai_zone``) ou le refus
    fermé du premier défaut : ``RUPTURE``, ``HORS_CARTE``, ``CHOIX_OBLIGATOIRE``, ``MAXIMUM_ATTEINT``, ``MINIMUM_NON_ATTEINT``…
    Hors des 17 fonctions du contrat : lecture seule, ce n'est pas un enregistrement."""
    if mode not in MODES:
        return _refus("ARGUMENT_INVALIDE", "Je n'ai pas compris le mode de la commande.", "mode")
    moment = moment or await maintenant(connexion)
    carte = await carte_du_restaurant(connexion, etablissement_id, moment)
    ruptures = {r["code_caisse"] for r in await ruptures_du_restaurant(connexion, etablissement_id, moment)}
    calculees, sous_total, erreur = _lignes(_Panier(carte, mode, ruptures, regle_moities), lignes)
    if erreur:
        return erreur
    frais, delai_zone = 0, 0
    if mode == "livraison" and zone_id:
        zone, frais, erreur = await _zone_de_livraison(connexion, etablissement_id, zone_id, sous_total)
        if erreur:
            return erreur
        delai_zone = zone["delai"]
    return Resultat(
        "OK", {"lignes": calculees, "sous_total": sous_total, "frais": frais, "total": sous_total + frais, "delai_zone": delai_zone}, ""
    )


async def article_de_la_carte(
    connexion: asyncpg.Connection, etablissement_id: int, ref: str, moment: datetime | None = None, mode: str | None = None
) -> dict | None:
    """[.mark] Lot 5 : ce que l'agent peut proposer pour UN article de la carte (produit ou formule) à ce moment : ses déclinaisons
    (prix, vendable, en rupture), ses groupes de choix avec leurs options (prix, retirable, en rupture), ses ingrédients retirables.
    ``None`` : pas à la carte à ce moment (ou autre établissement). Une formule rend un groupe par ligne de la formule."""
    moment = moment or await maintenant(connexion)
    carte = await carte_du_restaurant(connexion, etablissement_id, moment)
    ruptures = {r["code_caisse"] for r in await ruptures_du_restaurant(connexion, etablissement_id, moment)}
    panier = _Panier(carte, mode or "emporter", ruptures)
    produit = next((p for p in carte["produits"] if p["id"] == ref), None)

    enfants_de: dict[str, list[dict]] = {}
    for g in carte["groupes"]:
        if g["parent_option_id"]:
            enfants_de.setdefault(g["parent_option_id"], []).append(g)

    def option(o: dict, profondeur: int = 0) -> dict:
        return {
            "id": o["id"], "code": o["code_caisse"], "nom": o["nom"], "prix": o["prix"], "retirable": o["retirable"],
            "par_defaut": o["par_defaut"], "vendable": o["vendable"], "rupture": o["code_caisse"] in ruptures,
            "enfants": [groupe(e, profondeur + 1) for e in enfants_de.get(o["id"], [])] if profondeur < 3 else [],
        }

    def groupe(g: dict, profondeur: int = 0) -> dict:
        return {
            "id": g["id"], "nom": g["nom"], "min": g["min"], "max": g["max"], "max_par_option": g["max_par_option"],
            "role": g["role"], "defaut": g["defaut"], "options": [option(o, profondeur) for o in g["options"]],
        }

    if produit is not None:
        return {
            "id": produit["id"], "nom": produit["nom"], "formule": False,
            "declinaisons": [
                {"code": d["code_caisse"], "nom": d["nom"], "prix": panier.prix(d), "vendable": d["vendable"], "rupture": d["code_caisse"] in ruptures}
                for d in produit["declinaisons"]
            ],
            "groupes": [groupe(g) for g in carte["groupes"] if g["id"] in produit["groupes"] and g["parent_option_id"] is None],
            "retirables": [i["nom"] for i in produit["ingredients"] if i.get("retirable")],
            "ingredients": [i["nom"] for i in produit["ingredients"]],
        }
    formule = next((f for f in carte["formules"] if f["id"] == ref), None)
    if formule is None:
        return None
    groupes = []
    for ligne in formule["lignes"]:
        options = []
        for p in carte["produits"]:
            for d in p["declinaisons"]:
                dedans = d["code_caisse"] in (ligne.get("codes") or []) or (
                    p["categorie_id"] in (ligne.get("categories") or []) and (not ligne.get("declinaison") or d["nom"] == ligne["declinaison"])
                )
                if dedans and d["vendable"]:
                    nom = p["nom"] + (f" {d['nom']}" if len(p["declinaisons"]) > 1 else "")
                    options.append(
                        {"id": d["id"], "code": d["code_caisse"], "nom": nom, "prix": 0, "retirable": False, "par_defaut": False, "vendable": True,
                         "rupture": d["code_caisse"] in ruptures, "enfants": []}
                    )
        groupes.append(
            {"id": ligne["nom"], "nom": ligne["nom"], "min": 1, "max": 1, "max_par_option": 1, "role": "choix", "defaut": [], "options": options, "enfants": []}
        )
    return {
        "id": formule["id"], "nom": formule["nom"], "formule": True,
        "declinaisons": [{"code": formule["code_caisse"], "nom": formule["nom"], "prix": formule["prix"], "vendable": formule["vendable"], "rupture": formule["code_caisse"] in ruptures}],
        "groupes": groupes, "retirables": [], "ingredients": [],
    }


# --------------------------------------------------------------------------- #
# enregistrer_commande
# --------------------------------------------------------------------------- #


def _cle_doublon(brouillon: dict, calculees: list[dict]) -> str:
    """Même appel + même panier = même clé. Sans appel : le client, le mode, l'heure voulue et le panier."""
    panier = json.dumps(
        [(l["code_caisse"], l["quantite"], l["choix"], sorted(l["retires"]), l["note"]) for l in calculees], sort_keys=True, ensure_ascii=False
    )
    heure = brouillon.get("heure_voulue")
    qui = brouillon.get("appel_id") or f"{brouillon['client']['telephone']}|{brouillon['mode']}|{heure.isoformat() if heure else ''}"
    return hashlib.sha256(f"{qui}|{panier}".encode()).hexdigest()


def _heure_dite(heure: datetime, fuseau: ZoneInfo) -> str:
    local = heure.astimezone(fuseau)
    return f"{local.hour} h {local.minute:02d}" if local.minute else f"{local.hour} h"


def _quand_dit(heure: datetime, maintenant_: datetime, fuseau: ZoneInfo) -> str:
    """« 19 h 30 » le jour même, « samedi 14 novembre à 19 h 30 » un autre jour : une commande pour plus tard dit toujours son jour."""
    local = heure.astimezone(fuseau)
    if local.date() == maintenant_.astimezone(fuseau).date():
        return _heure_dite(heure, fuseau)
    return f"{jour_dit(local.date())} à {_heure_dite(heure, fuseau)}"


async def enregistrer_commande(
    connexion: asyncpg.Connection,
    etablissement_id: int,
    brouillon: dict,
    jeton_relecture: str | None,
    *,
    declencher_envoi: Callable[[uuid.UUID], Awaitable[None]] | None = None,
) -> Resultat:
    """Enregistre une commande. Recalcule les prix, le total, les frais et les remises depuis la carte ; revérifie
    ouverture, ruptures, zone, minimum et paiement ; rend ``ENREGISTREE`` (numéro, numéro court, heure annoncée, total),
    ``INCOMPLETE`` (UN manque à la fois), un refus fermé ou ``DEJA_FAIT`` (même appel + même panier = même numéro).

    ``brouillon`` : ``mode``, ``client {telephone, prenom?, second_numero?}``, ``lignes [{code_caisse, quantite?, note?,
    choix?, retires?}]``, ``heure_voulue?`` (aware ; vide = dès que possible), ``adresse?``, ``zone_id?`` (livraison),
    ``remises? [{ref|nom}]``, ``paiement {moyens, reste_par_moyen, rendu_sur?}``, ``note?``, ``appel_id?``, ``cree_par?``.
    ``jeton_relecture`` : exigé (la relecture en deux temps, lot 24, en définit la preuve ; ici : non vide)."""
    maintenant_ = await maintenant(connexion)
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    mode = brouillon.get("mode")
    client = brouillon.get("client") or {}
    heure_voulue = brouillon.get("heure_voulue")
    cree_par = brouillon.get("cree_par", "agent")

    # --- Les manques, un à la fois, dans l'ordre où on les demande ---
    if mode not in MODES:
        return _refus("ARGUMENT_INVALIDE", "Je n'ai pas compris le mode de la commande.", "mode")
    if not brouillon.get("lignes"):
        return _refus("INCOMPLETE", "Qu'est-ce que je vous mets ?", "lignes")
    if not isinstance(client.get("telephone"), str) or not E164.match(client["telephone"]):
        return _refus("INCOMPLETE", "Quel est votre numéro de téléphone ?", "telephone")
    if mode == "livraison" and not brouillon.get("adresse"):
        return _refus("INCOMPLETE", "Quelle est l'adresse de livraison ?", "adresse")
    if mode == "livraison" and not brouillon.get("zone_id"):
        return _refus("INCOMPLETE", "Je dois situer l'adresse de livraison.", "zone")
    if not jeton_relecture or not str(jeton_relecture).strip():
        return _refus("INCOMPLETE", "Je vous relis la commande avant de l'enregistrer.", "relecture")
    if cree_par not in ("agent", "portail", "caisse"):
        return _refus("ARGUMENT_INVALIDE", "Origine de la commande invalide.", "cree_par")
    if heure_voulue is not None and (heure_voulue.tzinfo is None or heure_voulue < maintenant_):
        return _refus("ARGUMENT_INVALIDE", "L'heure demandée n'est pas valable.", "heure_voulue")
    if sum(len(str(client.get(k) or "")) for k in ("prenom",)) > 60:
        return _refus("ARGUMENT_INVALIDE", "Prénom trop long.", "prenom")

    # --- Ouverture, au moment de la commande (l'heure voulue si elle est planifiée) ---
    moment = heure_voulue or maintenant_
    reglage = await connexion.fetchrow("SELECT * FROM mark.resto_reglage_type WHERE site_id = $1 AND type = $2", etablissement_id, mode)
    if heure_voulue is not None and heure_voulue > maintenant_ + timedelta(minutes=1):
        if reglage is None or not reglage["planifiee_permise"]:
            return _refus("ARGUMENT_INVALIDE", "Je ne prends pas de commande pour plus tard.", "heure_voulue")
        if reglage["jours_a_l_avance"] and heure_voulue > maintenant_ + timedelta(days=reglage["jours_a_l_avance"]):
            return _refus("ARGUMENT_INVALIDE", "C'est trop loin pour moi.", "heure_voulue")
        if heure_voulue < maintenant_ + timedelta(minutes=reglage["delai_minimal"]):
            return _refus("ARGUMENT_INVALIDE", "C'est trop tôt pour moi.", "heure_voulue")
    etat = await etat_combine(connexion, etablissement_id, mode, moment)
    if not etat["ouvert"]:
        raison = etat["raison"]
        return _refus(statut_de_fermeture(raison), "Nous ne prenons pas de commande en ce moment.", raison=raison, reprise=etat["reprise"], prochaine_ouverture=etat["prochaine_ouverture"])

    # --- Commande pour plus tard : le quart d'heure voulu a-t-il encore de la place ? Sinon le premier libre est proposé (lot 6, capacité par quart) ---
    if heure_voulue is not None and heure_voulue > maintenant_ + timedelta(minutes=1):
        libre = await creneau_complet(connexion, etablissement_id, mode, heure_voulue)
        if libre is not None:
            return _refus(
                "ARGUMENT_INVALIDE", f"Ce créneau est complet, je peux vous proposer {_quand_dit(libre, maintenant_, fuseau)}.", "heure_voulue",
                raison="creneau_plein", proposition=libre,
            )

    # --- La carte, les ruptures, le panier ---
    carte = await carte_du_restaurant(connexion, etablissement_id, moment)
    ruptures = {r["code_caisse"] for r in await ruptures_du_restaurant(connexion, etablissement_id, moment)}
    panier = _Panier(carte, mode, ruptures, brouillon.get("regle_moities") or "plus_chere")
    calculees, sous_total, erreur = _lignes(panier, brouillon["lignes"])
    if erreur:
        return erreur

    # --- Livraison : la zone de CET établissement, minimum, frais ---
    frais, zone = 0, None
    if mode == "livraison":
        zone, frais, erreur = await _zone_de_livraison(connexion, etablissement_id, brouillon["zone_id"], sous_total)
        if erreur:
            return erreur

    # --- Remises : recalculées chez nous, jamais le montant du modèle ---
    retenues: list[dict] = []
    if brouillon.get("remises"):
        candidates = await remises_applicables(connexion, etablissement_id, {"mode": mode, "sous_total": sous_total}, moment, client)
        retenues, motif = retenir(brouillon["remises"], candidates, sous_total)
        if motif:
            return _refus("REFUSEE", "Cette remise ne s'applique pas à votre commande.", raison=motif)
    total_remises = sum(r["montant"] for r in retenues)
    total = sous_total + frais - total_remises

    # --- Paiement : moyens acceptés, plafond du titre-restaurant, le compte est bon ---
    parametres = await connexion.fetchrow("SELECT moyens_paiement, plafond_titre_restaurant FROM mark.resto_reglage WHERE site_id = $1", etablissement_id)
    acceptes = set(parametres["moyens_paiement"]) if parametres else {"carte", "especes"}
    paiement = brouillon.get("paiement") or {}
    moyens = list(paiement.get("moyens") or [])
    reste = dict(paiement.get("reste_par_moyen") or {})
    if not moyens and not reste:
        return _refus("INCOMPLETE", "Vous réglez comment ?", "paiement")
    if not all(isinstance(m, dict) and isinstance(m.get("moyen"), str) and "montant" in m for m in moyens):
        return _refus("ARGUMENT_INVALIDE", "Règlement invalide.", "paiement")
    for moyen in [m["moyen"] for m in moyens] + list(reste):
        if moyen not in acceptes:
            return _refus("MOYEN_NON_ACCEPTE", "Ce moyen de paiement n'est pas accepté.", moyen=moyen, acceptes=sorted(acceptes))
    plafond = parametres["plafond_titre_restaurant"] if parametres else None
    titres = sum(m["montant"] for m in moyens if m["moyen"] == "titre_restaurant") + reste.get("titre_restaurant", 0)
    if plafond is not None and titres > plafond:
        return _refus("PLAFOND_TITRE_RESTAURANT", "Le montant en titres-restaurant dépasse le plafond.", plafond=plafond, montant=titres)
    if any(not isinstance(m["montant"], int) or m["montant"] < 0 for m in moyens) or any(not isinstance(v, int) or v < 0 for v in reste.values()):
        return _refus("ARGUMENT_INVALIDE", "Montant de paiement invalide.", "paiement")
    if sum(m["montant"] for m in moyens) + sum(reste.values()) != total:
        return _refus("INCOMPLETE", "Le règlement ne couvre pas exactement le total.", "paiement", total=total)

    # --- L'heure annoncée (lot 6) : l'heure voulue, sinon le délai du type OU de la zone en entier, plus la durée ajoutée par la puce, plus l'attente de
    # capacité, dans le format réglé (heure fixe, tranche, durée), arrondie vers le haut. Écrite ici, sur la demande : un changement de la puce ne la touche plus ---
    annonce = None
    if heure_voulue is not None:
        heure_annoncee = heure_voulue
    else:
        annonce = await annonce_pour(connexion, etablissement_id, mode, maintenant_, zone["id"] if zone else None, etat=etat)
        heure_annoncee = annonce["annonce"].prete

    cle = _cle_doublon(brouillon, calculees)
    jour_local = maintenant_.astimezone(fuseau).date()
    numero = uuid.uuid4()
    async with connexion.transaction():
        await poser_session(connexion, cree_par if cree_par in SOURCES else "agent", f"commande:{cree_par}")
        # Le verrou anti-doublon : deux appels simultanés du même panier s'attendent ; le second rend le numéro du premier.
        await connexion.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"resto_commande:{etablissement_id}:{cle}")
        existante = await connexion.fetchrow("SELECT numero, numero_court, heure_annoncee, total FROM mark.resto_commande WHERE site_id = $1 AND cle_doublon = $2", etablissement_id, cle)
        if existante is not None:
            return Resultat(
                "DEJA_FAIT",
                {"numero": str(existante["numero"]), "numero_court": existante["numero_court"], "heure_annoncee": existante["heure_annoncee"], "total": existante["total"]},
                f"Votre commande est déjà enregistrée pour {_heure_dite(existante['heure_annoncee'], fuseau)}." if existante["heure_annoncee"] else "Votre commande est déjà enregistrée.",
            )
        prefixe = await connexion.fetchval("SELECT prefixe_numero_court FROM mark.resto_reglage WHERE site_id = $1", etablissement_id) or ""
        compteur = await connexion.fetchval(
            "INSERT INTO mark.resto_compteur_jour (site_id, jour, dernier) VALUES ($1, $2, 1) "
            "ON CONFLICT (site_id, jour) DO UPDATE SET dernier = mark.resto_compteur_jour.dernier + 1 RETURNING dernier",
            etablissement_id, jour_local,
        )
        numero_court = f"{prefixe}{compteur}"
        await connexion.execute(
            "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, heure_voulue, heure_annoncee, telephone, prenom, "
            "second_numero, adresse, zone_id, remises, sous_total, frais, total, paiement, note, statut, cree_par, appel_id, "
            "cle_doublon, cree_le, maj_le) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, $12::jsonb, $13, $14, $15, "
            "$16::jsonb, $17, 'nouvelle', $18, $19, $20, $21, $21)",
            numero, numero_court, etablissement_id, mode, heure_voulue, heure_annoncee, client["telephone"], client.get("prenom"),
            json.dumps(client["second_numero"]) if client.get("second_numero") else None,
            json.dumps(brouillon["adresse"]) if brouillon.get("adresse") else None,
            zone["id"] if zone else None,
            json.dumps([{"nom": r["nom"], "montant": r["montant"], "ref_caisse": r["ref_caisse"]} for r in retenues]),
            sous_total, frais, total,
            json.dumps({"moyens": moyens, "rendu_sur": paiement.get("rendu_sur"), "reste_par_moyen": reste}),
            brouillon.get("note"), cree_par, brouillon.get("appel_id"), cle, maintenant_,
        )
        for rang, l in enumerate(calculees, start=1):
            await connexion.execute(
                "INSERT INTO mark.resto_commande_ligne (numero, site_id, rang, code_caisse, nom, prix_unitaire, quantite, note, choix, retires, formule_ref) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)",
                numero, etablissement_id, rang, l["code_caisse"], l["nom"], l["prix_unitaire"], l["quantite"], l["note"],
                json.dumps(l["choix"]), l["retires"], l["formule_id"],
            )
        # La fiche du client : créée ou mise à jour (consignes et adresses gardées).
        await connexion.execute(
            "INSERT INTO mark.resto_client (site_id, telephone, prenom, derniere_commande_id, derniere_commande_le, nb_commandes, cree_le, maj_le) "
            "VALUES ($1, $2, $3, $4, $5, 1, $5, $5) ON CONFLICT (site_id, telephone) DO UPDATE SET "
            "prenom = coalesce(EXCLUDED.prenom, mark.resto_client.prenom), derniere_commande_id = EXCLUDED.derniere_commande_id, "
            "derniere_commande_le = EXCLUDED.derniere_commande_le, nb_commandes = mark.resto_client.nb_commandes + 1, maj_le = EXCLUDED.maj_le",
            etablissement_id, client["telephone"], client.get("prenom"), numero, maintenant_,
        )
    if declencher_envoi is not None:
        await declencher_envoi(numero)  # l'envoi : après l'enregistrement validé, clé de tâche = le numéro
    faits = {"numero": str(numero), "numero_court": numero_court, "heure_annoncee": heure_annoncee, "total": total}
    if annonce is None:
        return Resultat("ENREGISTREE", faits, f"Votre commande est enregistrée pour {_quand_dit(heure_annoncee, maintenant_, fuseau)}.")
    a = annonce["annonce"]
    faits["annonce"] = {"format": a.format, "minutes": a.minutes, "debut": a.debut, "fin": a.fin, "dite": dite(a, fuseau)}
    return Resultat("ENREGISTREE", faits, f"Votre commande est enregistrée, elle sera prête {dite(a, fuseau)}.")


# --------------------------------------------------------------------------- #
# Statuts, retrouver, planifiées
# --------------------------------------------------------------------------- #


async def changer_statut(
    connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, de: str, vers: str, source: str
) -> Resultat:
    """Un pas du chemin fermé. ``OK`` ; ``DEJA_FAIT`` quand la commande est déjà à ``vers`` (le second geste identique,
    jamais d'écrasement) ; ``INTERDIT`` quand ``de`` n'est pas le statut actuel ou que le pas n'est pas permis ;
    ``INTROUVABLE`` : pas une commande de CET établissement."""
    if source not in SOURCES or de not in TRANSITIONS or vers not in TRANSITIONS:
        return Resultat("ARGUMENT_INVALIDE", manque="statut")
    try:
        numero = uuid.UUID(str(numero))
    except ValueError:
        return Resultat("ARGUMENT_INVALIDE", manque="numero")
    if vers not in TRANSITIONS[de]:
        # Même geste rejoué ? On le dit avant d'interdire.
        actuel = await connexion.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1 AND site_id = $2", numero, etablissement_id)
        if actuel is None:
            return Resultat("INTROUVABLE", {"numero": str(numero)})
        return Resultat("DEJA_FAIT" if actuel == vers else "INTERDIT", {"statut_actuel": actuel, "de": de, "vers": vers})
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, source, f"statut:{source}")
        # Le statut de départ est vérifié PAR LA REQUÊTE : deux gestes simultanés, un seul passe.
        passe = await connexion.fetchval(
            "UPDATE mark.resto_commande SET statut = $4, maj_le = $5, tentatives = tentatives + CASE WHEN $4 = 'envoyee' THEN 1 ELSE 0 END "
            "WHERE numero = $1 AND site_id = $2 AND statut = $3 RETURNING 1",
            numero, etablissement_id, de, vers, maintenant_,
        )
    if passe:
        return Resultat("OK", {"numero": str(numero), "de": de, "vers": vers})
    actuel = await connexion.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1 AND site_id = $2", numero, etablissement_id)
    if actuel is None:
        return Resultat("INTROUVABLE", {"numero": str(numero)})
    return Resultat("DEJA_FAIT" if actuel == vers else "INTERDIT", {"statut_actuel": actuel, "de": de, "vers": vers})


def _commande(r: asyncpg.Record) -> dict:
    return {
        "numero": str(r["numero"]), "numero_court": r["numero_court"], "mode": r["mode"], "statut": r["statut"],
        "heure_voulue": r["heure_voulue"], "heure_annoncee": r["heure_annoncee"], "telephone": r["telephone"],
        "prenom": r["prenom"], "total": r["total"], "cree_par": r["cree_par"], "cree_le": r["cree_le"],
    }


async def commande_complete(connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID) -> dict | None:
    """[.mark] Lot 3 : la commande ENTIÈRE de CET établissement au format commun (lignes, choix, remises, paiement), pour qu'une prise
    l'envoie. ``None`` si ce n'est pas une commande de cet établissement. Lecture seule ; hors des 17 fonctions du contrat."""
    try:
        numero = uuid.UUID(str(numero))
    except ValueError:
        return None
    r = await connexion.fetchrow("SELECT * FROM mark.resto_commande WHERE site_id = $1 AND numero = $2", etablissement_id, numero)
    if r is None:
        return None
    lignes = await connexion.fetch("SELECT * FROM mark.resto_commande_ligne WHERE site_id = $1 AND numero = $2 ORDER BY rang", etablissement_id, numero)

    def json_(v):
        return json.loads(v) if isinstance(v, str) else v

    return {
        "numero": str(r["numero"]), "numero_court": r["numero_court"], "etablissement_id": etablissement_id, "mode": r["mode"],
        "heure_voulue": r["heure_voulue"], "heure_annoncee": r["heure_annoncee"],
        "client": {"telephone": r["telephone"], "prenom": r["prenom"], "second_numero": json_(r["second_numero"])},
        "adresse": json_(r["adresse"]), "zone_id": r["zone_id"], "remises": json_(r["remises"]) or [], "frais": r["frais"], "total": r["total"],
        "paiement": json_(r["paiement"]) or {}, "note": r["note"], "statut": r["statut"], "ref_fournisseur": r["ref_fournisseur"],
        "tentatives": r["tentatives"], "cree_par": r["cree_par"], "appel_id": r["appel_id"],
        "lignes": [
            {"code_caisse": l["code_caisse"], "nom": l["nom"], "prix_unitaire": l["prix_unitaire"], "quantite": l["quantite"], "note": l["note"],
             "choix": json_(l["choix"]) or [], "retires": list(l["retires"] or []), "formule_id": l["formule_ref"]}
            for l in lignes
        ],
    }


async def statut_commande(
    connexion: asyncpg.Connection,
    etablissement_id: int,
    numero: str | None = None,
    telephone: str | None = None,
    jour: date | None = None,
) -> Resultat:
    """Retrouver une commande : par numéro (l'identifiant ou le numéro court du jour), sinon par téléphone et jour
    (le jour de l'établissement ; aujourd'hui par défaut). ``OK`` avec ``commandes`` (les plus récentes d'abord) ou
    ``INTROUVABLE``. Seulement les commandes de CET établissement."""
    if numero:
        try:
            lignes = await connexion.fetch("SELECT * FROM mark.resto_commande WHERE site_id = $1 AND numero = $2", etablissement_id, uuid.UUID(str(numero)))
        except ValueError:
            jour_cherche = jour or (await maintenant(connexion)).astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id))).date()
            debut, fin = await _fenetre(connexion, etablissement_id, jour_cherche)
            lignes = await connexion.fetch(
                "SELECT * FROM mark.resto_commande WHERE site_id = $1 AND numero_court = $2 AND cree_le >= $3 AND cree_le < $4 ORDER BY cree_le DESC",
                etablissement_id, str(numero), debut, fin,
            )
    elif telephone:
        jour_cherche = jour or (await maintenant(connexion)).astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id))).date()
        debut, fin = await _fenetre(connexion, etablissement_id, jour_cherche)
        lignes = await connexion.fetch(
            "SELECT * FROM mark.resto_commande WHERE site_id = $1 AND telephone = $2 AND cree_le >= $3 AND cree_le < $4 ORDER BY cree_le DESC LIMIT 20",
            etablissement_id, telephone, debut, fin,
        )
    else:
        return Resultat("ARGUMENT_INVALIDE", manque="numero")
    if not lignes:
        return Resultat("INTROUVABLE", {}, "Je ne trouve pas cette commande.")
    return Resultat("OK", {"commandes": [_commande(r) for r in lignes]})


async def _fenetre(connexion: asyncpg.Connection, etablissement_id: int, jour: date) -> tuple[datetime, datetime]:
    """Le début et la fin (aware) d'un jour dans le fuseau de l'établissement."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    debut = datetime(jour.year, jour.month, jour.day, tzinfo=fuseau)
    return debut, datetime.combine(jour + timedelta(days=1), datetime.min.time(), tzinfo=fuseau)


async def commandes_planifiees(connexion: asyncpg.Connection, etablissement_id: int, du: datetime, au: datetime) -> dict:
    """Les commandes dont l'heure voulue tombe dans ``[du, au[`` (hors annulées, refusées, en échec) et le chiffre
    d'affaires à venir (E-17)."""
    if du.tzinfo is None or au.tzinfo is None:
        raise ValueError("Les bornes doivent être aware.")
    lignes = await connexion.fetch(
        "SELECT * FROM mark.resto_commande WHERE site_id = $1 AND heure_voulue >= $2 AND heure_voulue < $3 "
        "AND statut NOT IN ('annulee', 'refusee', 'echec') ORDER BY heure_voulue, numero_court",
        etablissement_id, du, au,
    )
    return {"commandes": [_commande(r) for r in lignes], "nombre": len(lignes), "chiffre_affaires": sum(r["total"] for r in lignes)}
