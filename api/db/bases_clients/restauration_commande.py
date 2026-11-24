"""[.mark] Module Restauration, lot 2 : les commandes dans le classeur (contrat § 3, § 4).

``enregistrer_commande`` (recalcule TOUT depuis la carte ; un manque à la fois ; verrou anti-doublon),
``changer_statut`` (chemin fermé, ``DEJA_FAIT``), ``statut_commande``, ``commandes_planifiees``.

Montants en centimes, entiers. Le total du modèle n'est jamais pris : un prix donné qui diffère de la carte est refusé
(``prix_different``). L'heure vient de la source d'heure de l'organisation (D6). L'envoi à la caisse n'est PAS fait ici :
``declencher_envoi`` (un appelant, lot 9 et 10) est appelé APRÈS l'enregistrement validé, avec le numéro pour clé de
tâche (``_job_id`` = numéro : rejouable sans effet double).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
from loguru import logger

from api.db.bases_clients.annonce_heure import dite
from api.services.actions_communes.moyens_de_paiement import ABREGES
from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES
from api.services.mots_dits import heure_en_lettres, montant_en_lettres
from api.db.bases_clients.dates_futures import jour_dit
from api.services.commande.briques.article_simple import brique_art1_chiffrer
from api.services.commande.briques import conditions_de_vente, supplement_de_formule, menu_a_taille_liee, lot_a_prix_fixe, choix_entre_deux_contenus, inclus_par_rubrique, a_volonte, livraison_offerte, quota_inclus_puis_payant, option_conditionnelle, prix_par_mode, consigne_et_emballage, produit_au_poids, supplement_selon_la_taille, changer_d_accompagnement, retrait_d_ingredient
from api.services.commande.briques import formule as FO
from api.services.commande.briques.inconnue import regle_inconnue_en_note
from api.services.commande.briques.taille_fixant_le_nombre import appliquer_les_quotas
from api.db.bases_clients.restauration_carte import (
    accord_du_produit,
    carte_du_restaurant,
    etat_combine,
    ruptures_du_restaurant,
)
from api.db.bases_clients.restauration_commun import (
    MODES,
    SOURCES,
    Resultat,
    cle_du_client,
    fuseau_de,
    maintenant,
    poser_session,
)
from api.db.bases_clients.instantane import oublier
from api.db.bases_clients.restauration_reglage import reglages_de_l_enregistrement, reglages_du_module
from api.db.bases_clients.restauration_remise import au_mieux, remises_applicables, retenir
from api.db.bases_clients.restauration_remise_offre import noter_l_acceptation
from api.db.bases_clients.restauration_temps import annonce_pour, creneau_complet
from api.db.bases_clients.restauration_zone import zone_de_l_etablissement

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


# T-06 : un groupe « moitiés » (deux choix exactement) ; la règle de prix est un réglage de l'ÉTABLISSEMENT (``resto_reglage.moities_prix``, lot 10), la plus chère par défaut.
REGLES_MOITIES = ("plus_chere", "moyenne", "somme")


def repartir_les_moities(prix: list[int], regle: str) -> list[int]:
    """Le supplément des moitiés (la règle choisit, les prix ne s'additionnent pas) réparti entre elles, pour que la somme des parts soit exactement
    ce supplément : ``plus_chere`` le met sur la moitié la plus chère (0 sur les autres), ``somme`` laisse chaque prix, ``moyenne`` le répartit au centime
    près (le reste sur les premières). Ce que chaque choix porte : la caisse recalcule le même total que nous (D50)."""
    if not prix:
        return []
    if regle == "somme":
        return list(prix)
    if regle == "moyenne":
        total = -(-sum(prix) // len(prix))  # arrondi vers le haut, au centime
        base, reste = divmod(total, len(prix))
        return [base + (1 if i < reste else 0) for i in range(len(prix))]
    plus_chere = prix.index(max(prix))
    return [max(prix) if i == plus_chere else 0 for i in range(len(prix))]


def _prix_des_moities(prix: list[int], regle: str) -> int:
    return sum(repartir_les_moities(prix, regle))


def _taux_de_la_carte(produit: dict | None, mode: str) -> int | None:
    """Le taux de TVA (millièmes de %, 10 % = 10000) que la carte donne à ce produit pour ce mode ; ``None`` quand elle ne le dit pas
    (produit sans taux, formule : la carte ne porte pas de taux sur une formule)."""
    taux = ((produit or {}).get("tva_par_mode") or {}).get(mode)
    return taux if isinstance(taux, int) and not isinstance(taux, bool) and 0 <= taux <= 100000 else None


def taux_majoritaire(lignes: list[dict]) -> int | None:
    """Le taux porté par la plus grande part du panier (à égalité, le plus haut) : celui des frais et des remises, qui n'ont pas de taux propre.
    ``None`` quand aucune ligne n'a de taux."""
    parts: dict[int, int] = {}
    for l in lignes:
        if l.get("taux_tva") is not None:
            parts[l["taux_tva"]] = parts.get(l["taux_tva"], 0) + l["prix_unitaire"] * l["quantite"]
    return max(parts, key=lambda t: (parts[t], t)) if parts else None


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

    def __init__(self, carte: dict, mode: str, ruptures: set[str], regle_moities: str = "plus_chere", maintenant: datetime | None = None, servi_le: datetime | None = None):
        self.mode = mode
        self.maintenant, self.servi_le = maintenant, servi_le  # lot 12 (PRX9) : l'instant de l'appel et l'heure voulue, pour le délai minimal d'un article
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
        # Lot 11 (FOR6, FOR10) : une formule à tailles ou par personnes se vend sous le code de chaque déclinaison
        for f in list(self.formules.values()):
            for d in FO.declinaisons_de_la_formule(f):
                self.formules.setdefault(d["code"], f)
        self.categories = {c["id"]: c for c in carte.get("categories") or []}
        self.enfants: dict[str, list[dict]] = {}
        for g in carte["groupes"]:
            if g["parent_option_id"]:
                self.enfants.setdefault(g["parent_option_id"], []).append(g)

    def prix(self, d: dict) -> int:
        par_mode = d.get("prix_par_mode") or {}
        return par_mode.get(self.mode, d["prix"])


def _prix_de_l_option(g: dict, o: dict, declinaison: dict | None, mode: str | None = None) -> int:
    """Ce qu'une unité de cette option ajoute à la ligne : son prix au mode (PRX4), à la déclinaison de la ligne (RET2, qui passe d'abord), puis la différence avec
    l'option incluse du groupe (RET4)."""
    au_mode = {**o, "prix": prix_par_mode.brique_prx4_prix_au_mode(o, mode, o["prix"])}
    return changer_d_accompagnement.brique_ret4_difference_de_prix(g, au_mode, supplement_selon_la_taille.brique_ret2_prix_a_la_declinaison(au_mode, declinaison))


def _choix(panier: _Panier, groupes: list[dict], choisis: list[dict], quantite_ligne: int, rendu: list[dict], declinaison: dict | None = None):
    """Vérifie et chiffre les choix d'un niveau. Rend ``(supplement_unitaire, None)`` ou ``(0, Resultat)``."""
    groupes = option_conditionnelle.groupes_ouverts(groupes, choisis)  # OPT6 : un groupe conditionnel n'existe que si l'option qui l'ouvre est choisie
    options: dict[str, tuple[dict, dict]] = {}
    for g in groupes:
        for o in g["options"]:
            if o["vendable"]:
                options.setdefault(o["code_caisse"], (g, o))
    par_groupe: dict[str, int] = {}
    par_option: dict[str, int] = {}
    supplement = 0
    moities: list[tuple[dict, int]] = []  # les choix d'un groupe « moitiés » et leur prix : la règle choisit, ils ne s'additionnent pas
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
        refus = conditions_de_vente.refus_de_l_option(o, panier.mode)  # PRX1 et PRX3 : l'option hors de sa plage ou d'un autre mode
        if refus is not None:
            return 0, _refus("INTERDIT", "", **refus)
        prix_o = _prix_de_l_option(g, o, declinaison, panier.mode)
        entree = {"option_code": code, "quantite": n, "choix": [], "nom": o["nom"], "prix": 0 if g["role"] == "moities" else prix_o, "groupe": g["nom"]}
        entrees = [entree]
        if g["role"] == "moities":
            moities.append((entree, prix_o * n))
        else:
            # OPT3 : le quota compris dans le prix du groupe, puis chaque élément au prix du groupe ou de l'option ; les unités comprises et les payantes sont deux
            # entrées (la caisse porte un prix par entrée), les sous-choix sont reportés sur chacune (leur coût par unité ne change pas).
            gratuites, payantes, prix_paye = quota_inclus_puis_payant.brique_opt3_facturer_au_dela(g, {**o, "prix": prix_o}, par_groupe[g["id"]] - n, n)
            supplement += payantes * prix_paye
            if g.get("inclus") is not None:
                entrees = [{**entree, "quantite": q, "prix": p} for q, p in ((gratuites, 0), (payantes, prix_paye)) if q]
        enfants = panier.enfants.get(o["id"], [])
        sous: list[dict] = []
        gain, erreur = _choix(panier, enfants, c.get("choix") or [], quantite_ligne, sous, declinaison)
        if erreur:
            return 0, erreur
        supplement += gain * n
        for e in entrees:
            e["choix"] = copy.deepcopy(sous)
        rendu.extend(entrees)
    # Les parts des moitiés : leur somme est le supplément que la règle donne (``repartir_les_moities``), jamais la somme des deux prix.
    parts = repartir_les_moities([prix for _, prix in moities], panier.regle_moities)
    for (entree, _), part in zip(moities, parts):
        entree["prix"] = part // entree["quantite"]
    supplement += sum(parts)
    for g in groupes:
        n = par_groupe.get(g["id"], 0)
        if n < g["min"]:
            return 0, _refus("CHOIX_OBLIGATOIRE", f"Il faut choisir : {g['nom']}.", groupe=g["id"], nom=g["nom"], minimum=g["min"])
        if n > g["max"]:
            return 0, _refus("MAXIMUM_ATTEINT", f"Pas plus de {g['max']} pour : {g['nom']}.", groupe=g["id"], nom=g["nom"], maximum=g["max"])
    return supplement, None


def _nom_de_la_declinaison(panier: _Panier, code: str) -> str:
    """Le nom d'un produit de la carte tel que la commande le dit (« Pizza Normale » quand il a plusieurs déclinaisons) ; à défaut, son code."""
    trouve = panier.decl.get(code)
    if trouve is None:
        return code
    produit, d = trouve
    return produit["nom"] + (f" {d['nom']}" if len(produit["declinaisons"]) > 1 else "")


def _ligne_du_choix(panier: _Panier, lignes: list[dict], restantes: list[int], code: str, taille: dict | None, etape: str | None = None) -> tuple[int | None, str | None]:
    """La ligne de la formule où ce choix se range (la première qui l'accepte et a encore de la place), à la taille de la formule (FOR6) ; ``(None, raison)`` sinon."""
    trouve = panier.decl.get(code)
    if trouve is None:
        return None, None
    produit, d = trouve
    raison = None
    for i, ligne in enumerate(lignes):
        if etape is not None and ligne["nom"] != etape:
            continue  # un choix qui porte son étape se range sur elle seule
        voulue = menu_a_taille_liee.declinaison_voulue(taille, ligne["nom"])
        if voulue is not None:
            # la ligne change de déclinaison avec la taille : ce produit à cette déclinaison, s'il est accepté à l'une de ses déclinaisons
            oui = d["nom"] == voulue and any(FO.accepte(ligne, produit, x, panier.prix(x))[0] for x in produit["declinaisons"] if x["vendable"])
            r = None
        else:
            oui, r = FO.accepte(ligne, produit, d, panier.prix(d))
        if oui and restantes[i] > 0:
            return i, None
        raison = raison or r
    return None, raison


def _formule(panier: _Panier, f: dict, code: str, choisis: list[dict]) -> tuple[list[dict], int, bool, int | None, Resultat | None]:
    """Lot 11 (FOR1 à FOR15) : les choix d'une formule rangés sur ses lignes et chiffrés. Rend ``(rendu, supplement, alcool, taux, refus)`` : chaque choix est le
    produit choisi (son nom, sa déclinaison), son supplément de ligne (FOR4, le SEUL prix de ce choix dans la formule), les choix et retraits du plat (leurs suppléments
    à leur prix), son alcool et son taux ; le prix de la formule est celui de sa déclinaison (FOR1, FOR6, FOR10), jamais la somme des produits."""
    declinaison = FO.declinaison_de_la_formule(f, code) or {}
    taille = declinaison.get("taille")
    lignes = [FO.ligne_normale(l) for l in f["lignes"]]
    restantes = [l["quantite"] if not l["alternatives"] else max(int(a.get("quantite") or 1) for a in l["alternatives"]) for l in lignes]
    par_ligne: dict[int, list[dict]] = {}
    for c in choisis:
        code_c = c.get("option_code")
        n = c.get("quantite", 1)
        if not isinstance(n, int) or n < 1:
            return [], 0, False, None, _refus("ARGUMENT_INVALIDE", "Quantité de choix invalide.", "quantite", code=code_c)
        i, raison = _ligne_du_choix(panier, lignes, restantes, code_c, taille, c.get("etape"))
        if i is None:
            return [], 0, False, None, _refus("HORS_CARTE", "Ce choix n'existe pas dans cette formule.", code=code_c, raison=raison or "choix_hors_liste")
        if code_c in panier.ruptures:
            return [], 0, False, None, _refus("RUPTURE", "Un élément de la formule n'est plus disponible.", code=code_c)
        prises = 1 if lignes[i]["a_volonte"] else n
        if prises > restantes[i]:
            return [], 0, False, None, _refus("MAXIMUM_ATTEINT", f"Pas plus de {lignes[i]['quantite']} pour : {lignes[i]['nom']}.", groupe=lignes[i]["nom"],
                                              maximum=lignes[i]["quantite"])
        restantes[i] -= prises
        par_ligne.setdefault(i, []).append({**c, "quantite": prises})
    rendu: list[dict] = []
    supplement, alcool, parts_de_taux = 0, False, []
    for i, ligne in enumerate(lignes):
        pris = par_ligne.get(i, [])
        voulu = ligne["quantite"]
        if ligne["alternatives"]:
            options = [{"code": x, "nom": x, "alternative": k} for k, a in enumerate(ligne["alternatives"]) for x in a.get("codes") or []]
            pris, refus = choix_entre_deux_contenus.brique_for12_une_alternative({"nom": ligne["nom"], "alternatives": ligne["alternatives"], "options": options}, pris)
            if refus is not None:
                return [], 0, False, None, _refus("HORS_CARTE", "Une seule alternative.", groupe=ligne["nom"], **refus)
            voulu = next((int(a.get("quantite") or 1) for a in ligne["alternatives"] if pris and pris[0]["option_code"] in (a.get("codes") or [])), voulu)
        total = sum(c["quantite"] for c in pris)
        if ligne["obligatoire"] and total < (1 if ligne["a_volonte"] else voulu):
            return [], 0, False, None, _refus("CHOIX_OBLIGATOIRE", f"Il faut choisir : {ligne['nom']}.", groupe=ligne["nom"], nom=ligne["nom"], minimum=voulu)
        for c in pris:
            produit, d = panier.decl[c["option_code"]]
            groupes = appliquer_les_quotas([panier.groupes[g] for g in produit["groupes"] if g in panier.groupes and panier.groupes[g]["parent_option_id"] is None], d)
            sous: list[dict] = []
            gain, erreur = _choix(panier, groupes, c.get("choix") or [], 1, sous, d)
            if erreur:
                return [], 0, False, None, erreur
            retirables = {x["nom"] for x in produit["ingredients"] if x.get("retirable")} | set(retrait_d_ingredient.options_retirables(groupes))
            inconnus = [r for r in (c.get("retires") or []) if r not in retirables]
            if inconnus:
                return [], 0, False, None, _refus("HORS_CARTE", f"On ne peut pas retirer : {inconnus[0]}.", code=c["option_code"], retire=inconnus[0])
            prix_ligne = supplement_de_formule.brique_for4_ajouter_le_supplement_de_ligne(ligne, c["option_code"])
            supplement += (prix_ligne + gain) * c["quantite"]
            alcool = alcool or bool(produit.get("alcool"))
            taux = _taux_de_la_carte(produit, panier.mode)
            if taux is not None:
                parts_de_taux.append({"taux_tva": taux, "prix_unitaire": panier.prix(d), "quantite": c["quantite"]})
            rendu.append({"option_code": c["option_code"], "quantite": c["quantite"], "choix": sous, "nom": _nom_de_la_declinaison(panier, c["option_code"]),
                          "prix": prix_ligne, "groupe": ligne["nom"], "retires": list(c.get("retires") or []), "produit_nom": produit["nom"],
                          "alcool": bool(produit.get("alcool")), "taux_tva": taux, **({"a_volonte": True} if ligne["a_volonte"] else {})})
    return rendu, supplement, alcool, taux_majoritaire(parts_de_taux), None


def _regles_en_note(panier: _Panier, formule: dict | None, produit: dict | None, rendu: list[dict]) -> list[str]:
    """FOR13 (servi avec, sur la rubrique du produit) et FOR15 (à volonté) : les notes de ligne d'une ligne chiffrée."""
    textes = []
    categorie = (formule or produit or {}).get("categorie_id")
    servi = inclus_par_rubrique.faits_de_la_rubrique({"categories": list(panier.categories.values())}, categorie).get("servi_avec")
    if servi:
        textes.append(inclus_par_rubrique.brique_for13_inclus_de_la_rubrique(servi))
    textes += [a_volonte.note_a_volonte(c["groupe"]) for c in rendu if c.get("a_volonte")]
    return textes


def _accepte_en_lot(panier: _Panier, f: dict, code: str | None) -> bool:
    trouve = panier.decl.get(code or "")
    return trouve is not None and FO.accepte(FO.ligne_normale(f["lignes"][0]), trouve[0], trouve[1], panier.prix(trouve[1]))[0]


def _ligne_calculee(l: dict, code: str, n: int, nom: str, unitaire: int, note: str | None, alcool: bool, rendu: list[dict], formule: dict | None, produit: dict | None, taux: Any) -> dict:
    """Une ligne chiffrée de la commande (``produit`` : ``None`` pour une formule)."""
    return {
        "code_caisse": code, "nom": nom, "prix_unitaire": unitaire, "quantite": n, "note": note, "alcool": alcool, "poids_g": l.get("poids_g"),
        "choix": rendu, "retires": list(l.get("retires") or []), "formule_id": formule["id"] if formule else None, "taux_tva": taux,
        # Lot 7 : ce que le moteur de remises lit pour un périmètre (produit, catégorie). Le classeur ne les écrit pas sur la ligne.
        "produit_id": produit["id"] if produit else formule["id"], "categorie_id": produit["categorie_id"] if produit else formule.get("categorie_id"),
    }


def _lignes(panier: _Panier, brouillon_lignes: list[dict]) -> tuple[list[dict], int, Resultat | None]:
    calculees: list[dict] = []
    sous_total = 0
    pris_du_produit: dict[str, int] = {}
    # FOR11 : les unités qu'une formule par lot accepte forment des lots complets, dans l'ordre du panier ; le reste à l'unité
    brouillon_lignes, _ = lot_a_prix_fixe.brique_for11_compter_les_lots(
        brouillon_lignes, lot_a_prix_fixe.formules_par_lot(panier.formules), lambda f, code: _accepte_en_lot(panier, f, code))
    for rang, l in enumerate(brouillon_lignes, start=1):
        code, n = l.get("code_caisse"), l.get("quantite", 1)
        if not isinstance(n, int) or not 1 <= n <= 99:
            return [], 0, _refus("ARGUMENT_INVALIDE", "Quantité invalide.", "quantite", ligne=rang)
        formule = panier.formules.get(code)
        if code in panier.decl:
            produit, d = panier.decl[code]
            nom = produit["nom"] + (f" {d['nom']}" if len(produit["declinaisons"]) > 1 else "")
            base = panier.prix(d)
            if produit_au_poids.est_vendu_au_poids(produit):
                # QTE1 : le prix d'une portion est celui de son poids au prix au kilo ; sans poids, rien ne se chiffre (jamais un prix deviné)
                if not l.get("poids_g"):
                    return [], 0, _refus("INCOMPLETE", "", "poids", raison=produit_au_poids.RAISON_POIDS_A_DIRE, article=produit["nom"])
                base = produit_au_poids.prix_de_la_portion(produit, int(l["poids_g"]))
            # DEC2 : le minimum et le maximum d'un groupe sont ceux de la déclinaison choisie quand elle les fixe (une seule règle, ``briques/taille_fixant_le_nombre.py``)
            groupes = appliquer_les_quotas([panier.groupes[g] for g in produit["groupes"] if g in panier.groupes and panier.groupes[g]["parent_option_id"] is None], d)
            retirables = {i["nom"] for i in produit["ingredients"] if i.get("retirable")}
            options_retirables = retrait_d_ingredient.options_retirables(groupes)  # RET5 : « sans la sauce » sur une option retirable (``retirable`` de l'option)
            retirables |= set(options_retirables)
            alcool = bool(produit.get("alcool"))
            taux = _taux_de_la_carte(produit, panier.mode)
            erreur_f = None
        elif formule is not None:
            declinaison_f = FO.declinaison_de_la_formule(formule, code) or {"nom": formule["nom"], "prix": formule["prix"], "type": None}
            nom = formule["nom"] + (f" {declinaison_f['nom']}" if declinaison_f.get("type") else "")
            base, groupes, retirables, options_retirables = declinaison_f["prix"], [], set(), {}
            rendu_f, supplement_f, alcool, taux, erreur_f = _formule(panier, formule, code, l.get("choix") or [])
        else:
            return [], 0, _refus("HORS_CARTE", "Ce produit n'est pas à la carte.", code=code)
        if code in panier.ruptures:
            return [], 0, _refus("RUPTURE", f"{nom} n'est plus disponible.", code=code, nom=nom)
        # Lot 12 (PRX1, PRX3, PRX8, PRX9) : la plage, le mode, le maximum par commande et le délai minimal ; les quantités du même produit s'additionnent d'une ligne à l'autre
        objet = produit if code in panier.decl else formule
        refus = conditions_de_vente.refus_de_la_ligne(objet, d if code in panier.decl else None, panier.mode, n, pris_du_produit.get(objet["id"], 0), panier.maintenant, panier.servi_le)
        if refus is not None:
            return [], 0, _refus("INTERDIT", "", **refus)
        pris_du_produit[objet["id"]] = pris_du_produit.get(objet["id"], 0) + n
        if l.get("prix_unitaire") is not None and l["prix_unitaire"] != base:
            return [], 0, _refus("REFUSEE", "Le prix ne correspond pas à la carte.", raison="prix_different", code=code)
        if erreur_f:
            return [], 0, erreur_f
        inconnus = [r for r in (l.get("retires") or []) if r not in retirables]
        if inconnus:
            return [], 0, _refus("HORS_CARTE", f"On ne peut pas retirer : {inconnus[0]}.", code=code, retire=inconnus[0])
        rendu: list[dict] = []
        if formule is not None:
            rendu, supplement = rendu_f, supplement_f  # lot 11 : les choix rangés sur les lignes de la formule (``_formule``)
        else:
            supplement, erreur = _choix(panier, groupes, l.get("choix") or [], n, rendu, d if code in panier.decl else None)
            if erreur:
                return [], 0, erreur
            # RET5 : un retrait à prix (``prix_retrait`` d'une option retirable) est un choix signé, envoyé à la caisse comme une option retirée portant ce prix
            retraits = retrait_d_ingredient.brique_ret5_retirer(list(l.get("retires") or []), options_retirables)
            rendu.extend(retraits)
            supplement += sum(r["prix"] for r in retraits)
            # PRX7 : la consigne, l'emballage, les couverts de l'article s'ajoutent à sa ligne (par unité) et partent à la caisse en option « Frais »
            frais = consigne_et_emballage.brique_prx7_ligne_de_frais(produit)
            rendu.extend(frais)
            supplement += sum(f["prix"] for f in frais)
        unitaire = base + supplement
        sous_total += brique_art1_chiffrer(unitaire, n)
        porteur = {"note": l.get("note")}
        # FOR13, FOR15 : ce qu'aucune caisse n'exprime part en note de ligne (inventaire § 5, ``regle_inconnue_en_note``)
        for texte in _regles_en_note(panier, formule, produit if code in panier.decl else None, rendu):
            regle_inconnue_en_note(porteur, texte)
        calculees.append(_ligne_calculee(l, code, n, nom, unitaire, porteur["note"], alcool, rendu, formule, produit if code in panier.decl else None, taux))
    return calculees, sous_total, None


async def _zone_de_livraison(connexion: asyncpg.Connection, etablissement_id: int, zone_id: int | None, sous_total: int):
    """La zone de CET établissement (jamais celle d'un autre : relue avec l'établissement), son minimum et ses frais pour ce sous-total.
    Rend ``(zone, frais, None)`` ou ``(None, 0, Resultat)`` : ``HORS_ZONE`` ou ``MINIMUM_NON_ATTEINT``."""
    zone = await zone_de_l_etablissement(connexion, etablissement_id, zone_id)
    if zone is None:
        return None, 0, _refus("HORS_ZONE", "Nous ne livrons pas à cette adresse.")
    if sous_total < zone["minimum"]:
        return None, 0, _refus(
            "MINIMUM_NON_ATTEINT", f"Le minimum de commande est de {montant_en_lettres(zone['minimum'])}.",
            minimum=zone["minimum"], sous_total=sous_total,
        )
    return zone, livraison_offerte.brique_off4_frais_retires(zone, sous_total)["frais"], None  # lot 14 (OFF4) : la règle nommée


async def _remises_du_panier(
    connexion: asyncpg.Connection, etablissement_id: int, panier: _Panier, mode: str, calculees: list[dict], sous_total: int,
    moment: datetime, client: dict | None, demandees: list[dict] | None, codes: Iterable[str] = (),
) -> tuple[list[dict], list[dict], str | None]:
    """[.mark] Lot 7 : les remises de CE panier, calculées chez nous au centime par le moteur commun. ``demandees`` ``None`` : le code choisit
    l'ensemble le plus avantageux (chiffrage de l'appel) ; une liste de références : celles-là seulement, revérifiées (enregistrement).
    Rend ``(retenues, lignes_offertes, refus)`` : un article offert part à son prix de carte, avec une remise du même montant."""
    prix_par_code = {code: panier.prix(d) for code, (_, d) in panier.decl.items()}
    candidates = await remises_applicables(
        connexion, etablissement_id, {"mode": mode, "sous_total": sous_total, "lignes": calculees, "prix_par_code": prix_par_code}, moment, client, codes=codes
    )
    offertes: dict[str, list[dict]] = {}
    for c in candidates:
        if c["ajout"] and c["montant"]:
            lignes, _, erreur = _lignes(panier, [{"code_caisse": code, "quantite": q, "note": "offert"} for code, q in c["ajout"]])
            if erreur:
                c["montant"] = None  # l'article offert n'est pas vendable à cet instant (rupture, choix obligatoire) : la remise ne s'applique pas
            else:
                offertes[c["ref"]] = lignes
                c["montant"] = sum(l["prix_unitaire"] * l["quantite"] for l in lignes)
    plafond = sous_total + sum(c["montant"] for c in candidates if c["ajout"] and c["montant"])
    if demandees is None:
        retenues, motif = au_mieux(candidates, plafond), None
    else:
        retenues, motif = retenir(demandees, candidates, plafond)
    if motif:
        return [], [], motif
    lignes_offertes = [l for r in retenues for l in offertes.get(r["ref"], [])]
    return retenues, lignes_offertes, None


async def chiffrer_panier(
    connexion: asyncpg.Connection, etablissement_id: int, mode: str, lignes: list[dict], zone_id: int | None = None,
    moment: datetime | None = None, client: dict | None = None, servi_le: datetime | None = None, codes: Iterable[str] = (),
) -> Resultat:
    """[.mark] Lot 5 : le panier chiffré DEPUIS LA CARTE, comme le fera ``enregistrer_commande`` (mêmes fonctions), sans rien écrire.
    ``OK`` (``lignes`` avec leur prix de carte et leurs suppléments, ``sous_total``, ``frais``, ``total``, ``delai_zone``) ou le refus
    fermé du premier défaut : ``RUPTURE``, ``HORS_CARTE``, ``CHOIX_OBLIGATOIRE``, ``MAXIMUM_ATTEINT``, ``MINIMUM_NON_ATTEINT``…
    Hors des 17 fonctions du contrat : lecture seule, ce n'est pas un enregistrement."""
    if mode not in MODES:
        return _refus("ARGUMENT_INVALIDE", "Je n'ai pas compris le mode de la commande.", "mode")
    moment = moment or await maintenant(connexion)
    carte = await carte_du_restaurant(connexion, etablissement_id, servi_le or moment)  # lot 12 (PRX1) : la carte à l'heure voulue d'une précommande
    ruptures = {r["code_caisse"] for r in await ruptures_du_restaurant(connexion, etablissement_id, moment)}
    panier = _Panier(carte, mode, ruptures, (await reglages_du_module(connexion, etablissement_id))["moities_prix"], moment.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id))), servi_le)  # RET6 : la règle de l'établissement
    calculees, sous_total, erreur = _lignes(panier, lignes)
    if erreur:
        return erreur
    frais, delai_zone, offerte = 0, 0, False
    if mode == "livraison" and zone_id:
        zone, frais, erreur = await _zone_de_livraison(connexion, etablissement_id, zone_id, sous_total)
        if erreur:
            if erreur.statut == "MINIMUM_NON_ATTEINT":
                # sous le minimum, le panier se lit quand même (M27) : ses lignes chiffrées, pour la proposition en plus (lot 4)
                return Resultat(erreur.statut, {**erreur.faits, "lignes": calculees}, erreur.suggestion, erreur.manque)
            return erreur
        delai_zone = zone["delai"]
        offerte = livraison_offerte.brique_off4_frais_retires(zone, sous_total)["livraison_offerte"]
    # Lot 7 : les remises, choisies au mieux pour le client, calculées au centime ; ce que l'agent dit vient d'ici.
    retenues, offertes, _ = await _remises_du_panier(connexion, etablissement_id, panier, mode, calculees, sous_total, moment, client, None, codes)
    offerts_total = sum(l["prix_unitaire"] * l["quantite"] for l in offertes)
    remises_total = sum(r["montant"] for r in retenues)
    return Resultat(
        "OK",
        {
            "lignes": calculees, "sous_total": sous_total, "frais": frais, "delai_zone": delai_zone, "livraison_offerte": offerte,
            "offerts": [{"code_caisse": l["code_caisse"], "nom": l["nom"], "prix_unitaire": l["prix_unitaire"], "quantite": l["quantite"]} for l in offertes],
            "remises": [
                {"ref": r["ref"], "nom": r["nom"], "mecanisme": r["mecanisme"], "montant": r["montant"], "phrase": r["phrase"], "ref_caisse": r["ref_caisse"]}
                for r in retenues
            ],
            "total_remises": remises_total, "total": sous_total + offerts_total + frais - remises_total,
        },
        "",
    )


async def formules_de_la_carte(connexion: asyncpg.Connection, etablissement_id: int, moment: datetime | None = None) -> list[str]:
    """[.mark] Lot 11 (conversation FOR2-B) : les noms des formules à la carte à ce moment ; la lecture des offres les rend avec les remises (« la formule
    midi » cherchée dans les offres n'y était pas, l'agent disait qu'elle n'existait pas)."""
    carte = await carte_du_restaurant(connexion, etablissement_id, moment or await maintenant(connexion))
    return [f["nom"] for f in carte["formules"] if f.get("vendable", True) and not f.get("indisponible")]


def _enfants_par_option(carte: dict) -> dict[str, list[dict]]:
    """Les groupes enfants de chaque option (un groupe qui dépend du choix d'une option)."""
    enfants_de: dict[str, list[dict]] = {}
    for g in carte["groupes"]:
        if g["parent_option_id"]:
            enfants_de.setdefault(g["parent_option_id"], []).append(g)
    return enfants_de


def _synonymes_des_produits(carte: dict) -> dict[str, list[str]]:
    """Chantier Partie 1, lot 4 (C13, appel 2663) : une moitié EST un produit de la carte : elle se trouve aussi par les synonymes de ce produit
    (« reine » pour la moitié « Regina ») ; un synonyme n'est jamais inventé, seulement repris du produit du même nom."""
    synonymes: dict[str, list[str]] = {}
    for p in carte["produits"]:
        synonymes.setdefault(p["nom"].casefold().strip(), []).extend(s for s in p.get("synonymes") or () if s)
    return synonymes


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

    enfants_de, synonymes_des_produits = _enfants_par_option(carte), _synonymes_des_produits(carte)

    def option(o: dict, profondeur: int = 0, role: str | None = None) -> dict:
        synonymes = list(o.get("synonymes") or ())
        if role == "moities":
            synonymes += [s for s in synonymes_des_produits.get(str(o["nom"]).casefold().strip(), []) if s not in synonymes]
        return {
            "id": o["id"], "code": o["code_caisse"], "nom": o["nom"], "prix": o["prix"], "retirable": o["retirable"],
            # Lot 12 (PRX1, PRX3, PRX4) : hors de sa plage à ce moment, les modes où elle se vend, son prix par mode ; ``None`` = non dit
            "indisponible": o.get("indisponible"), "modes": o.get("modes"), "prix_par_mode": o.get("prix_par_mode"),
            "par_defaut": o["par_defaut"], "vendable": o["vendable"], "rupture": o["code_caisse"] in ruptures, "prix_retrait": o.get("prix_retrait"),
            "synonymes": synonymes,  # SA-52 : une option se trouve aussi par ses synonymes
            "allergenes": o.get("allergenes"),  # M88 : None tant que la carte ne porte pas les allergènes d'une option (inconnu, jamais « sans »)
            "enfants": [groupe(e, profondeur + 1) for e in enfants_de.get(o["id"], [])] if profondeur < 3 else [],
        }

    def groupe(g: dict, profondeur: int = 0) -> dict:
        return {
            "id": g["id"], "nom": g["nom"], "min": g["min"], "max": g["max"], "max_par_option": g["max_par_option"],
            "role": g["role"], "defaut": g["defaut"], "options": [option(o, profondeur, g["role"]) for o in g["options"]],
            "inclus": g.get("inclus"), "prix_au_dela": g.get("prix_au_dela"), "si_option": g.get("si_option"),  # lot 9 : OPT3, OPT6
        }

    def vue_du_produit(produit: dict) -> dict:
        return {
            "id": produit["id"], "nom": produit["nom"], "formule": False,
            "categorie": next((c["nom"] for c in carte["categories"] if c["id"] == produit["categorie_id"]), None),
            "declinaisons": [
                {"code": d["code_caisse"], "nom": d["nom"], "prix": panier.prix(d), "vendable": d["vendable"], "rupture": d["code_caisse"] in ruptures,
                 "indisponible": d.get("indisponible"),  # lot 12 (PRX1)
                 # Lot 8 : ce que la déclinaison distingue, le mot de sa question et les quotas qu'elle fixe ; ``None`` = non dit (jamais deviné)
                 "type": d.get("type"), "libelle_question": d.get("libelle_question"), "quotas": d.get("quotas")}
                for d in produit["declinaisons"]
            ],
            "groupes": [groupe(g) for g in carte["groupes"] if g["id"] in produit["groupes"] and g["parent_option_id"] is None],
            "description": produit.get("description") or "",  # SA-52 : ce que l'article contient déjà n'est pas un choix à refuser
            "retirables": [i["nom"] for i in produit["ingredients"] if i.get("retirable")]
            + [o["nom"] for g in carte["groupes"] if g["id"] in produit["groupes"] and g["parent_option_id"] is None for o in g["options"] if o.get("retirable") and o["vendable"]],
            "ingredients": [i["nom"] for i in produit["ingredients"]],
            "allergenes": produit["allergenes"],  # None : la fiche ne dit rien (jamais « sans »), [] : aucun
            # Lot 15 (INF3, INF5, INF7) : étiquettes de régime, épice (texte), nutrition ; ``None`` = non dit
            "regimes": produit.get("regimes"), "epice": produit.get("epice"), "nutrition": produit.get("nutrition"),
            # Lot 8 : de quoi accorder ce que l'agent dit (surcouche du produit) et le produit « du moment » (ART3)
            "genre": accord_du_produit(produit)[0], "commun": accord_du_produit(produit)[1],
            "du_moment": bool(produit.get("du_moment")), "texte_du_jour": produit.get("texte_du_jour"),
            # Lot 12 (PRX1 à PRX9) : les conditions de vente du produit ; ``None`` = non dit
            "indisponible": produit.get("indisponible"), "disponibilite": produit.get("disponibilite"), "modes": produit.get("modes"), "alcool": bool(produit.get("alcool")), "degre": produit.get("degre"),
            "frais": produit.get("frais"), "max_par_commande": produit.get("max_par_commande"), "delai_minimal_heures": produit.get("delai_minimal_heures"),
            "personnes_min": produit.get("personnes_min"),
            "unite": produit.get("unite") or "piece", "prix_par_unite": produit.get("prix_par_unite"), "arrondi": produit.get("arrondi"),  # lot 13 (QTE1, QTE2)
            "lot_de_vente": produit.get("lot_de_vente"),
            **inclus_par_rubrique.faits_de_la_rubrique(carte, produit["categorie_id"]),  # lot 11 (FOR13) : ce qui est servi avec chaque produit de la rubrique
        }

    if produit is not None:
        return vue_du_produit(produit)
    formule = next((f for f in carte["formules"] if f["id"] == ref), None)
    if formule is None:
        return None
    # Lot 11 (FOR1 à FOR15) : une étape par ligne ; chaque choix d'étape porte l'article du produit choisi (ses groupes, ses retraits, son alcool, sa TVA)
    return FO.article_de_la_formule(carte, formule, ruptures, panier.prix, vue_du_produit)


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


ABREGE_DU_TYPE = {"livraison": "L", "emporter": "E", "sur_place": "S"}


def _prefixe_du_numero(numero_mode: str, prefixe_mixte: str, mode: str, moyens: list[dict], reste: dict, fixe: str) -> str:
    """Le préfixe du numéro court (Réglages › Commandes) : ``type`` = L, E ou S ; ``moyen`` = CB, ESP, TR… ou le préfixe mixte quand la commande se règle
    avec deux moyens ou plus ; ``aucun`` = le préfixe fixe de l'établissement (vide par défaut)."""
    if numero_mode == "type":
        return ABREGE_DU_TYPE.get(mode, "")
    if numero_mode == "moyen":
        utilises = {m["moyen"] for m in moyens if m.get("montant")} | {m for m, v in reste.items() if v}
        if len(utilises) > 1:
            return prefixe_mixte
        return ABREGES.get(next(iter(utilises), ""), "")
    return fixe


def _heure_dite(heure: datetime, fuseau: ZoneInfo) -> str:
    local = heure.astimezone(fuseau)
    return heure_en_lettres(local.hour, local.minute)


def _quand_dit(heure: datetime, maintenant_: datetime, fuseau: ZoneInfo) -> str:
    """« 19 h 30 » le jour même, « samedi 14 novembre à 19 h 30 » un autre jour : une commande pour plus tard dit toujours son jour."""
    local = heure.astimezone(fuseau)
    if local.date() == maintenant_.astimezone(fuseau).date():
        return _heure_dite(heure, fuseau)
    return f"{jour_dit(local.date())} à {_heure_dite(heure, fuseau)}"


async def creneau_refuse(
    connexion: asyncpg.Connection, etablissement_id: int, mode: str, heure_voulue: datetime | None, maintenant_: datetime, fuseau: ZoneInfo,
) -> Resultat | None:
    """D15 : ce que l'heure voulue (ou le moment même, sans heure) a de refusable, sinon ``None``. Dans l'ordre : l'attente plus tard permise par le
    réglage du type, les jours à l'avance, le délai minimal, l'ouverture AU MOMENT VOULU (le refus dit alors quand on rouvre), la place du quart
    d'heure (le premier libre est proposé). Lecture seule : sert à l'enregistrement et à l'agent, avant la relecture."""
    plus_tard = heure_voulue is not None and heure_voulue > maintenant_ + timedelta(minutes=1)
    reglage = await connexion.fetchrow("SELECT * FROM mark.resto_reglage_type WHERE site_id = $1 AND type = $2", etablissement_id, mode)
    if plus_tard:
        if reglage is None or not reglage["planifiee_permise"]:
            return _refus("ARGUMENT_INVALIDE", "Je ne prends pas de commande pour plus tard.", "heure_voulue")
        # M91 (appel 2577, 00 h 50) : « J+1 » compte en JOURS du lieu (jusqu'à la fin de demain), comme la réservation (``capacite``), jamais en
        # 24 heures glissantes ; le refus dit jusqu'à quand.
        limite = (maintenant_.astimezone(fuseau) + timedelta(days=reglage["jours_a_l_avance"])).date() if reglage["jours_a_l_avance"] else None
        if limite is not None and heure_voulue.astimezone(fuseau).date() > limite:
            jusqu_a = "aujourd'hui" if limite == maintenant_.astimezone(fuseau).date() else jour_dit(limite)
            return _refus("ARGUMENT_INVALIDE", f"Je prends les commandes jusqu'à {jusqu_a} : pour quand la voulez-vous ?", "heure_voulue")
        if heure_voulue < maintenant_ + timedelta(minutes=reglage["delai_minimal"]):
            return _refus("ARGUMENT_INVALIDE", "C'est trop tôt pour moi.", "heure_voulue")
    etat = await etat_combine(connexion, etablissement_id, mode, heure_voulue or maintenant_)
    if not etat["ouvert"]:
        raison = etat["raison"]
        quand = etat["reprise"] or etat["prochaine_ouverture"]
        if plus_tard and isinstance(quand, datetime):
            phrase = f"À cette heure nous sommes fermés. Nous rouvrons {_quand_dit(quand, maintenant_, fuseau)} : pour quelle heure à partir de là ?"
        else:
            phrase = "Nous ne prenons pas de commande en ce moment."
        return _refus(statut_de_fermeture(raison), phrase, "heure_voulue" if plus_tard else None, raison=raison, reprise=etat["reprise"], prochaine_ouverture=etat["prochaine_ouverture"])
    if plus_tard:
        libre = await creneau_complet(connexion, etablissement_id, mode, heure_voulue)
        if libre is not None:
            return _refus(
                "ARGUMENT_INVALIDE", f"Ce créneau est complet, je peux vous proposer {_quand_dit(libre, maintenant_, fuseau)}.", "heure_voulue",
                raison="creneau_plein", proposition=libre,
            )
    return None


def _manques_de_la_demande(brouillon: dict, jeton_relecture: str | None, maintenant_: datetime) -> Resultat | None:
    """Les manques, un à la fois, dans l'ordre où on les demande : le premier refus, ou ``None`` quand la demande est complète."""
    mode = brouillon.get("mode")
    client = brouillon.get("client") or {}
    heure_voulue = brouillon.get("heure_voulue")
    cree_par = brouillon.get("cree_par", "agent")
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
    if len(str(client.get("prenom") or "")) > 60:
        return _refus("ARGUMENT_INVALIDE", "Prénom trop long.", "prenom")
    return None


def _reglement_du_brouillon(brouillon: dict) -> tuple[dict, list, dict]:
    """``(paiement, moyens, reste_par_moyen)`` tels que le brouillon les porte."""
    paiement = brouillon.get("paiement") or {}
    return paiement, list(paiement.get("moyens") or []), dict(paiement.get("reste_par_moyen") or {})


def _controler_le_reglement(brouillon: dict, reglages: dict, total: int, calculees: list[dict]) -> Resultat | None:
    """Le règlement : moyens acceptés, plafond du titre-restaurant, alcool et rendu, le compte est bon. Le premier refus, ou ``None`` quand tout passe."""
    module, acceptes, plafond = reglages["module"], set(reglages["moyens_paiement"]), reglages["plafond_titre"]
    paiement, moyens, reste = _reglement_du_brouillon(brouillon)
    if not moyens and not reste:
        return _refus("INCOMPLETE", "Vous réglez comment ?", "paiement")
    if not all(isinstance(m, dict) and isinstance(m.get("moyen"), str) and "montant" in m for m in moyens):
        return _refus("ARGUMENT_INVALIDE", "Règlement invalide.", "paiement")
    for moyen in [m["moyen"] for m in moyens] + list(reste):
        if moyen not in acceptes:
            return _refus("MOYEN_NON_ACCEPTE", "Ce moyen de paiement n'est pas accepté.", moyen=moyen, acceptes=sorted(acceptes))
    titres = sum(m["montant"] for m in moyens if m["moyen"] == "titre_restaurant") + reste.get("titre_restaurant", 0)
    if plafond is not None and titres > plafond:
        return _refus("PLAFOND_TITRE_RESTAURANT", "Le montant en titres-restaurant dépasse le plafond.", plafond=plafond, montant=titres)
    if titres and module["titre_alcool_exclu"]:
        # Un titre-restaurant ne paie pas l'alcool : ce qui dépasse la part sans alcool de la commande est refusé.
        eligible = max(0, total - sum(l["prix_unitaire"] * l["quantite"] for l in calculees if l["alcool"]))
        if any(l["alcool"] for l in calculees) and titres > eligible:
            return _refus("PLAFOND_TITRE_RESTAURANT", "Les titres-restaurant ne paient pas l'alcool.", plafond=eligible, montant=titres, raison="alcool")
    if titres and module["titre_sans_rendu"] and paiement.get("rendu_sur") and not any(m["moyen"] == "especes" for m in moyens):
        # Pas de rendu sur un titre-restaurant : le billet ne se rend que sur des espèces.
        return _refus("MOYEN_NON_ACCEPTE", "On ne rend pas la monnaie sur un titre-restaurant.", moyen="titre_restaurant", acceptes=sorted(acceptes), raison="sans_rendu")
    if any(not isinstance(m["montant"], int) or m["montant"] < 0 for m in moyens) or any(not isinstance(v, int) or v < 0 for v in reste.values()):
        return _refus("ARGUMENT_INVALIDE", "Montant de paiement invalide.", "paiement")
    if sum(m["montant"] for m in moyens) + sum(reste.values()) != total:
        return _refus("INCOMPLETE", "Le règlement ne couvre pas exactement le total.", "paiement", total=total)
    return None


async def _remises_et_total(
    connexion: asyncpg.Connection, etablissement_id: int, brouillon: dict, panier: _Panier, calculees: list[dict], sous_total: int, frais: int, moment: datetime
) -> tuple[Resultat | None, list[dict], list[dict], int, int]:
    """Les remises retenues (recalculées chez nous), les lignes avec les articles offerts, le sous-total et le total. ``(refus, retenues, lignes, sous_total, total)``."""
    retenues: list[dict] = []
    offertes: list[dict] = []
    if brouillon.get("remises"):
        retenues, offertes, motif = await _remises_du_panier(
            connexion, etablissement_id, panier, brouillon["mode"], calculees, sous_total, moment, brouillon.get("client") or {}, brouillon["remises"], brouillon.get("codes") or ()
        )
        if motif:
            return _refus("REFUSEE", "Cette remise ne s'applique pas à votre commande.", raison=motif), [], calculees, sous_total, 0
    sous_total += sum(l["prix_unitaire"] * l["quantite"] for l in offertes)  # un article offert part à son prix de carte, la remise du même montant l'annule
    return None, retenues, calculees + offertes, sous_total, sous_total + frais - sum(r["montant"] for r in retenues)


def _enregistree(faits: dict, annonce: dict | None, mode: str, maintenant_: datetime, fuseau: ZoneInfo) -> Resultat:
    """La réponse d'une commande enregistrée : la phrase de l'annonce du délai (format réglé), ou l'heure voulue."""
    # M121 : l'heure annoncée d'une livraison compte le délai de la zone en entier (E-42) : c'est son ARRIVÉE, pas l'heure où elle est prête.
    etat = "livrée" if mode == "livraison" else "prête"
    if annonce is None:
        # Chantier Partie 1, lot 6 (L06-41, ``banc-b2/guichet_candidat.py`` ``_enregistrer``) : la même phrase que l'annonce d'un délai.
        return Resultat("ENREGISTREE", faits, PHRASES_DITES.enregistree_avec_delai(etat, f"pour {_quand_dit(faits['heure_annoncee'], maintenant_, fuseau)}"))
    a = annonce["annonce"]
    faits["annonce"] = {"format": a.format, "minutes": a.minutes, "debut": a.debut, "fin": a.fin, "dite": dite(a, fuseau)}
    return Resultat("ENREGISTREE", faits, PHRASES_DITES.enregistree_avec_delai(etat, dite(a, fuseau)))


@dataclass
class _ACommande:
    """Tout ce que l'écriture d'une commande reçoit, déjà contrôlé et chiffré par ``enregistrer_commande`` : elle n'ajoute aucune règle."""

    etablissement_id: int
    brouillon: dict
    mode: str
    client: dict
    cree_par: str
    heure_voulue: datetime | None
    heure_annoncee: datetime
    zone: dict | None
    retenues: list[dict]
    calculees: list[dict]
    sous_total: int
    frais: int
    total: int
    paiement: dict
    moyens: list
    reste: dict
    cle: str
    maintenant: datetime
    fuseau: ZoneInfo
    reglages: dict


async def _ecrire_la_commande(connexion: asyncpg.Connection, a: _ACommande) -> tuple[Resultat | None, uuid.UUID, str]:
    """Écrit la commande, ses lignes et la fiche du client en UNE transaction. ``(deja_fait, numero, numero_court)`` : ``deja_fait`` non vide quand le même appel
    a déjà enregistré le même panier (rien n'est écrit, le numéro rendu est celui du premier)."""
    etablissement_id, brouillon, client, cree_par, module = a.etablissement_id, a.brouillon, a.client, a.cree_par, a.reglages["module"]
    mode, heure_voulue, heure_annoncee, zone, retenues, calculees = a.mode, a.heure_voulue, a.heure_annoncee, a.zone, a.retenues, a.calculees
    sous_total, frais, total, paiement, moyens, reste = a.sous_total, a.frais, a.total, a.paiement, a.moyens, a.reste
    cle, maintenant_, fuseau, reglages = a.cle, a.maintenant, a.fuseau, a.reglages
    # M14 : les taux sont FIGÉS ici, avec la commande (un changement de la carte ne touche pas une commande déjà prise). Les frais et les remises
    # n'ont pas de taux propre : ils suivent celui de la plus grande part du panier.
    taux_du_panier = taux_majoritaire(calculees)
    jour_local = a.maintenant.astimezone(fuseau).date()
    numero = uuid.uuid4()
    async with connexion.transaction():
        await poser_session(connexion, cree_par if cree_par in SOURCES else "agent", f"commande:{cree_par}")
        # Le verrou anti-doublon : deux appels simultanés du même panier s'attendent ; le second rend le numéro du premier.
        await connexion.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"resto_commande:{etablissement_id}:{cle}")
        # Clôture, lot B4 (M2) : une commande ANNULÉE n'est jamais « déjà faite » : changée après l'enregistrement (l'heure, même panier), l'ancienne est
        # annulée puis la nouvelle enregistrée ; avant, l'anti-doublon rendait l'ancienne annulée comme enregistrée et la commande était perdue
        existante = await connexion.fetchrow(
            "SELECT numero, numero_court, heure_annoncee, total FROM mark.resto_commande WHERE site_id = $1 AND cle_doublon = $2 AND statut <> 'annulee'",
            etablissement_id, cle)
        if existante is not None:
            return Resultat(
                "DEJA_FAIT",
                {"numero": str(existante["numero"]), "numero_court": existante["numero_court"], "heure_annoncee": existante["heure_annoncee"], "total": existante["total"]},
                f"Votre commande est déjà enregistrée pour {_heure_dite(existante['heure_annoncee'], fuseau)}." if existante["heure_annoncee"] else "Votre commande est déjà enregistrée.",
            ), numero, ""
        prefixe = _prefixe_du_numero(
            module["numero_mode"], module["prefixe_mixte"], mode, moyens, reste,
            reglages["prefixe_numero_court"],
        )
        compteur = await connexion.fetchval(
            "INSERT INTO mark.resto_compteur_jour (site_id, jour, dernier) VALUES ($1, $2, 1) "
            "ON CONFLICT (site_id, jour) DO UPDATE SET dernier = mark.resto_compteur_jour.dernier + 1 RETURNING dernier",
            etablissement_id, jour_local,
        )
        numero_court = f"{prefixe}{compteur}"
        await connexion.execute(
            "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, heure_voulue, heure_annoncee, telephone, prenom, "
            "second_numero, adresse, zone_id, remises, sous_total, frais, total, paiement, note, statut, cree_par, appel_id, "
            "cle_doublon, cree_le, maj_le, taux_tva_frais, consigne_livreur) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, $12::jsonb, $13, $14, $15, "
            "$16::jsonb, $17, 'nouvelle', $18, $19, $20, $21, $21, $22, $23)",
            numero, numero_court, etablissement_id, mode, heure_voulue, heure_annoncee, client["telephone"], client.get("prenom"),
            json.dumps(client["second_numero"]) if client.get("second_numero") else None,
            json.dumps(brouillon["adresse"]) if brouillon.get("adresse") else None,
            zone["id"] if zone else None,
            json.dumps([{"nom": r["nom"], "montant": r["montant"], "ref_caisse": r["ref_caisse"], "taux_tva": taux_du_panier} for r in retenues]),
            sous_total, frais, total,
            json.dumps({"moyens": moyens, "rendu_sur": paiement.get("rendu_sur"), "reste_par_moyen": reste}),
            brouillon.get("note"), cree_par, brouillon.get("appel_id"), cle, maintenant_, taux_du_panier if frais else None,
            (brouillon.get("consigne_livreur") or None),  # lot 16 : la consigne pour le livreur, envoyée à la caisse dans ``customer.delivery_notes``
        )
        for rang, l in enumerate(calculees, start=1):
            await connexion.execute(
                "INSERT INTO mark.resto_commande_ligne (numero, site_id, rang, code_caisse, nom, prix_unitaire, quantite, note, choix, retires, formule_ref, taux_tva, poids_g) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13)",
                numero, etablissement_id, rang, l["code_caisse"], l["nom"], l["prix_unitaire"], l["quantite"], l["note"],
                json.dumps(l["choix"]), l["retires"], l["formule_id"], l["taux_tva"], l.get("poids_g"),
            )
        # La fiche du client : créée ou mise à jour (consignes et adresses gardées).
        await connexion.execute(
            "INSERT INTO mark.resto_client (site_id, telephone, prenom, derniere_commande_id, derniere_commande_le, nb_commandes, cree_le, maj_le) "
            "VALUES ($1, $2, $3, $4, $5, 1, $5, $5) ON CONFLICT (site_id, telephone) DO UPDATE SET "
            "prenom = coalesce(EXCLUDED.prenom, mark.resto_client.prenom), derniere_commande_id = EXCLUDED.derniere_commande_id, "
            "derniere_commande_le = EXCLUDED.derniere_commande_le, nb_commandes = mark.resto_client.nb_commandes + 1, maj_le = EXCLUDED.maj_le",
            etablissement_id, client["telephone"], client.get("prenom"), numero, maintenant_,
        )
        # Lot 5 : la fiche du client et son nombre de commandes viennent de changer : relues à leur prochaine lecture dans cet appel
        oublier(connexion, cle_du_client(etablissement_id, client["telephone"]))
        oublier(connexion, ("nb_commandes_du_client", etablissement_id, client["telephone"]))
        # M38 : les offres dites dans cet appel et portées par la commande passent à « acceptée » (sans appel connu, rien n'est noté).
        # Dans son propre point de reprise : un compteur d'écran (table absente d'une base pas encore mise à niveau, par exemple) ne défait jamais une commande.
        try:
            async with connexion.transaction():
                await noter_l_acceptation(connexion, etablissement_id, brouillon.get("appel_id"), [r["id"] for r in retenues if r.get("id") is not None], numero)
        except Exception:  # un compteur d'écran ne défait jamais une commande, mais il se voit
            logger.exception("[.mark] Offer acceptance not counted")
    return None, numero, numero_court


async def enregistrer_commande(
    connexion: asyncpg.Connection,
    etablissement_id: int,
    brouillon: dict,
    jeton_relecture: str | None,
    *,
    declencher_envoi: Callable[[uuid.UUID], Awaitable[None]] | None = None,
    a_blanc: bool = False,
) -> Resultat:
    """Enregistre une commande. Recalcule les prix, le total, les frais et les remises depuis la carte ; revérifie
    ouverture, ruptures, zone, minimum et paiement ; rend ``ENREGISTREE`` (numéro, numéro court, heure annoncée, total),
    ``INCOMPLETE`` (UN manque à la fois), un refus fermé ou ``DEJA_FAIT`` (même appel + même panier = même numéro).

    ``brouillon`` : ``mode``, ``client {telephone, prenom?, second_numero?}``, ``lignes [{code_caisse, quantite?, note?,
    choix?, retires?}]``, ``heure_voulue?`` (aware ; vide = dès que possible), ``adresse?``, ``zone_id?`` (livraison),
    ``remises? [{ref|nom}]``, ``paiement {moyens, reste_par_moyen, rendu_sur?}``, ``note?``, ``appel_id?``, ``cree_par?``.
    ``jeton_relecture`` : exigé (la relecture en deux temps, lot 24, en définit la preuve ; ici : non vide).
    ``a_blanc`` (clôture, Pierre A2) : fait tous les contrôles qui peuvent refuser (ouverture, ruptures relues, zone, remises, règlement, heure) et
    s'arrête avant l'anti-doublon et toute écriture : ``OK`` ou le refus que l'enregistrement rendrait. Sert à changer une commande enregistrée en
    tout ou rien : l'ancienne n'est annulée qu'une fois la nouvelle sûre d'entrer."""
    maintenant_ = await maintenant(connexion)
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    mode = brouillon.get("mode")
    client = brouillon.get("client") or {}
    heure_voulue = brouillon.get("heure_voulue")
    cree_par = brouillon.get("cree_par", "agent")

    refus_de_la_demande = _manques_de_la_demande(brouillon, jeton_relecture, maintenant_)
    if refus_de_la_demande is not None:
        return refus_de_la_demande
    # --- Ouverture, au moment de la commande (l'heure voulue si elle est planifiée), puis capacité du quart d'heure voulu ---
    moment = heure_voulue or maintenant_
    refus = await creneau_refuse(connexion, etablissement_id, mode, heure_voulue, maintenant_, fuseau)
    if refus is not None:
        return refus
    etat = await etat_combine(connexion, etablissement_id, mode, moment)  # ouvert à ce moment : sert l'annonce de l'heure plus bas
    # --- La carte, les ruptures, le panier ---
    carte = await carte_du_restaurant(connexion, etablissement_id, moment)  # D61 point 3 : la carte de l'appel, ses prix du début à la fin
    # Lot 5 : une rupture posée pendant l'appel refuse l'enregistrement : les ruptures sont relues à la base ici
    ruptures = {r["code_caisse"] for r in await ruptures_du_restaurant(connexion, etablissement_id, moment, relire=True)}
    reglages = await reglages_de_l_enregistrement(connexion, etablissement_id)  # UNE lecture : moyens, plafond, module, préfixe du numéro
    module = reglages["module"]
    panier = _Panier(carte, mode, ruptures, module["moities_prix"], maintenant_.astimezone(fuseau), heure_voulue)  # RET6 : la règle de l'établissement
    calculees, sous_total, erreur = _lignes(panier, brouillon["lignes"])
    if erreur:
        return erreur
    # --- Livraison : la zone de CET établissement, minimum, frais ---
    frais, zone = 0, None
    if mode == "livraison":
        zone, frais, erreur = await _zone_de_livraison(connexion, etablissement_id, brouillon["zone_id"], sous_total)
        if erreur:
            return erreur
    # --- Remises : recalculées chez nous au centime, jamais le montant du modèle ; seules celles que le chiffrage de l'appel a nommées ---
    erreur, retenues, calculees, sous_total, total = await _remises_et_total(connexion, etablissement_id, brouillon, panier, calculees, sous_total, frais, moment)
    if erreur:
        return erreur
    # --- Paiement : moyens acceptés, plafond du titre-restaurant, le compte est bon ---
    refus_du_reglement = _controler_le_reglement(brouillon, reglages, total, calculees)
    if refus_du_reglement is not None:
        return refus_du_reglement
    paiement, moyens, reste = _reglement_du_brouillon(brouillon)
    annonce, heure_annoncee = None, heure_voulue
    if heure_voulue is None:  # l'heure annoncée est écrite ici, sur la demande : un changement de la puce ne la touche plus
        annonce = await annonce_pour(connexion, etablissement_id, mode, maintenant_, zone["id"] if zone else None, etat=etat)
        heure_annoncee = annonce["annonce"].prete
    if a_blanc:
        return Resultat("OK", {"total": total})
    a = _ACommande(
        etablissement_id, brouillon, mode, client, cree_par, heure_voulue, heure_annoncee, zone, retenues, calculees, sous_total, frais, total, paiement, moyens, reste,
        _cle_doublon(brouillon, calculees), maintenant_, fuseau, reglages,
    )
    deja_fait, numero, numero_court = await _ecrire_la_commande(connexion, a)
    if deja_fait is not None:
        return deja_fait
    if declencher_envoi is not None:
        await declencher_envoi(numero)  # l'envoi : après l'enregistrement validé, clé de tâche = le numéro
    faits = {"numero": str(numero), "numero_court": numero_court, "heure_annoncee": heure_annoncee, "total": total}
    return _enregistree(faits, annonce, mode, maintenant_, fuseau)


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
            "UPDATE mark.resto_commande SET statut = $4, maj_le = $5, tentatives = tentatives + CASE WHEN $4 = 'envoyee' THEN 1 ELSE 0 END, "
            # Lot 16 : l'heure de l'envoi (la montre du suivi « restée nouvelle ») et celle de l'acceptation, posées par la couche d'accès, de l'heure de la source d'heure (D6)
            "envoyee_le = CASE WHEN $4 = 'envoyee' THEN $5 ELSE envoyee_le END, acceptee_le = CASE WHEN $4 = 'acceptee' AND acceptee_le IS NULL THEN $5 ELSE acceptee_le END "
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
        "consigne_livreur": r["consigne_livreur"], "cause_echec": r["cause_echec"], "envoyee_le": r["envoyee_le"], "acceptee_le": r["acceptee_le"],
        "lignes": [
            {"code_caisse": l["code_caisse"], "nom": l["nom"], "prix_unitaire": l["prix_unitaire"], "quantite": l["quantite"], "note": l["note"],
             "choix": json_(l["choix"]) or [], "retires": list(l["retires"] or []), "formule_id": l["formule_ref"], "poids_g": l["poids_g"]}
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
