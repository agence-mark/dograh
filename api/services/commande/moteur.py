"""[.mark] Mécanisme commun : les gestes de la commande sur catalogue (lot 5, E-01, E-35, T-06, T-18).

Chaque geste prend la SOURCE (le catalogue vrai), le panier de l'appel et les réglages de l'agent, et rend un ``Resultat`` fermé
(statut, faits, suggestion, manque). Le modèle choisit comment le dire ; le code tient les faits :

- un manque à la fois, dans l'ordre où on le demande (mode, zone avant les articles, taille, choix obligatoire…) ;
- AUCUN article perdu à cause de l'ordre (W16) : « un filtre et un joint » met le joint même si le filtre attend sa taille ;
- le prix, le total et les choix obligatoires ne sont jamais ceux du modèle : la source chiffre, le moteur ne fait que le relayer ;
- un article, un choix, un retrait ou un supplément qui n'existe pas est refusé avec les plus proches, jamais un prix inventé (E-35) ;
- le moteur n'envoie jamais rien nulle part : l'enregistrement de la source déclenche l'envoi.

La recherche d'un article ou d'un choix passe par le moteur de recherche dans une liste fermée (lot 4), à zéro faux sûr.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from loguru import logger

from api.db.bases_clients import dates_futures, recherche_liste
from api.schemas.apres_appel import numero_e164
from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_moteur import norme_de_recherche
from api.services.commande import lecture, panier as P, tailles
from api.services.commande.briques import art3, conditions_de_vente, dec1, dec2, for1, for2, for6, for10, for12, for15, inconnue, inf1, inf2, inf3, inf4, inf5, inf6, inf7, off3, opt1, opt6, prx2, prx5, prx6, qte1, qte2, taille
from api.services.commande.briques import formule as FO
from api.services.mots_dits import chiffres_en_lettres, liste_dite, liste_dite_et, montant_en_lettres, nom_dit, nombre_en_lettres, phrase_nette
from api.services.commande.resultat import Resultat, avec_numero_affiche, avec_numeros_retenus
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS as MOTIFS_DES_PHRASES, NUMERO_AFFICHE_GARDE
from api.services.commande.source import Source
from api.services.actions_communes.types import Adresse, MomentVoulu

LONGUEUR_NOTE = 200
_PETITS_MOTS = frozenset({"la", "le", "les", "l", "de", "du", "des", "un", "une", "ligne", "celle", "celui", "ci"})


@dataclass(frozen=True)
class Reglages:
    """Les réglages de construction du module (registre des modules), lus dans la configuration de l'agent."""

    ordre_impose: bool = True  # la zone avant les articles quand le mode en exige une (W6)
    relecture_en_deux_temps: bool = True
    vente_en_plus: bool = True
    notes_libres: bool = True  # E-35 : « bien cuite », « sauce à part » : une note de ligne, sans prix
    mentions_de_remise: int = 1  # T-08 : combien de fois par appel l'agent parle d'une remise de lui-même (0 : seulement sur demande)
    # M98 : la question qui finit la relecture quand le numéro qui s'affiche est gardé (phrase du code réglable, lue par l'action à l'endroit de
    # l'appel) ; ``None`` ou vide : la relecture finit par « C'est bon ? ».
    question_numero_affiche: str | None = MOTIFS_DES_PHRASES[NUMERO_AFFICHE_GARDE].variantes_defaut[0]
    # M108 : la question qui finit la confirmation d'une commande enregistrée (phrase du code réglable, lue par l'action à l'endroit de l'appel) ;
    # ``None`` ou vide : la confirmation est dite seule.
    question_apres_enregistrement: str | None = MOTIFS_DES_PHRASES[APRES_ENREGISTREMENT].variantes_defaut[0]
    # M118 : la surcouche de l'agent sur la table standard des mots de taille (``tailles.py``) : ``{mot: rang}``, ``None`` retire un mot.
    mots_de_taille: dict[str, Any] | None = None


def _r(statut: str, faits: dict | None = None, suggestion: str = "", manque: str | None = None) -> Resultat:
    return Resultat(statut, faits or {}, suggestion, manque)


def _avec(resultat: Resultat, p: dict[str, Any], **plus: Any) -> Resultat:
    """Le résultat, avec le résumé du panier : le modèle sait toujours où en est la commande."""
    return Resultat(resultat.statut, {**resultat.faits, "panier": {**P.resume(p), **plus}}, resultat.suggestion, resultat.manque)


# --------------------------------------------------------------------------- #
# Lire le catalogue : les morceaux, les choix, les retraits
# --------------------------------------------------------------------------- #


def _chercher_dans(elements: list[Element], texte: str) -> dict:
    return recherche_liste.chercher(elements, texte)


def _est_le_nom(trouve: dict, texte: str) -> bool:
    """Le texte ENTIER est le nom d'un seul élément (« 4 saisons », « vis et boulons ») : retenu, et le nom dit en entier. Une
    correspondance partielle (« filtre et joint » contient « filtre ») n'est jamais prise pour un nom : zéro faux sûr."""
    if trouve.get("statut") != "RETENU" or not trouve.get("candidats"):
        return False
    return norme_de_recherche(trouve["candidats"][0]["libelle"]) == norme_de_recherche(texte)  # SA-52 : « deux » = « 2 »


def _groupes_a_remplir(article: dict, ligne: dict) -> list[tuple[tuple[str, ...], dict]]:
    """Les groupes de choix où ``ligne`` peut ou doit choisir : ceux de l'article, puis ceux des options déjà choisies (une fois imbriqués)."""
    sortie: list[tuple[tuple[str, ...], dict]] = []

    def descendre(groupes: list[dict], chemin: tuple[str, ...], choisis: list[dict]) -> None:
        for g in groupes:
            if not opt6.brique_opt6_poser_b_si_a(g, choisis):
                continue  # OPT6 : un groupe conditionnel n'existe que si l'option qui l'ouvre est choisie
            sortie.append((chemin, g))
            for o in g["options"]:
                deja = next((c for c in choisis if c["option_code"] == o["code"] and FO.du_groupe(c, g)), None)
                if deja is not None and o["enfants"]:
                    descendre(o["enfants"], chemin + (o["code"],), deja["choix"])

    # DEC2 : les groupes de l'article tels que la déclinaison de la ligne les veut (minimum et maximum de sa taille)
    declinaison = next((d for d in article["declinaisons"] if d["code"] and d["code"] == ligne.get("code")), None)
    descendre(dec2.appliquer_les_quotas(article["groupes"], declinaison), (), ligne["choix"])
    return sortie


def _niveau(choix: list[dict], chemin: tuple[str, ...]) -> list[dict]:
    courant = choix
    for code in chemin:
        courant = next(c for c in courant if c["option_code"] == code)["choix"]
    return courant


def _compte(ligne: dict, chemin: tuple[str, ...], groupe: dict) -> int:
    return sum(c["quantite"] for c in _niveau(ligne["choix"], chemin) if FO.du_groupe(c, groupe))


def _question(article: dict, ligne: dict) -> dict | None:
    """La première question encore ouverte pour cette ligne : la déclinaison, puis chaque choix obligatoire. ``None`` : la ligne est complète."""
    if not ligne.get("code"):
        return dec1.brique_dec1_demander_la_declinaison(article["declinaisons"])
    for chemin, g in _groupes_a_remplir(article, ligne):
        if FO.est_une_etape(g) and _compte(ligne, chemin, g) < for12.minimum_de_l_etape(g, [c for c in _niveau(ligne["choix"], chemin) if FO.du_groupe(c, g)]):
            return for2.brique_for2_une_etape_a_la_fois(g, list(chemin))  # FOR2 : une étape à la fois ; FOR12 : remplie à la quantité de l'alternative prise
        if FO.est_une_etape(g):
            continue
        if _compte(ligne, chemin, g) < g["min"]:
            return {
                "type": "groupe", "groupe": g["id"], "nom": g["nom"], "min": g["min"], "max": g["max"], "chemin": list(chemin),
                "options": [o["nom"] for o in g["options"] if o["vendable"] and not o["rupture"]],
                # OPT3 : le nombre compris dans le prix et le prix de chacun au-delà (quand la carte les dit), à faire dire par le modèle
                **({"inclus": g["inclus"], **({"prix_au_dela": g["prix_au_dela"]} if g.get("prix_au_dela") is not None else {})} if g.get("inclus") is not None else {}),
            }
    return None


_UNITE_DITE = re.compile(r"(?<![\w,.])(\d+(?:[,.]\d+)?)\s*(cl|ml|l|g|kg)(?![\w])", re.IGNORECASE)
_UNITES_EN_MOTS = {"cl": "centilitre", "ml": "millilitre", "l": "litre", "g": "gramme", "kg": "kilo"}


def _unites_dites(texte: str) -> str:
    """« 33 cl » -> « 33 centilitres », « 1,5 l » -> « 1,5 litre » : une unité abrégée n'est pas une parole (SA-52, appel 2604)."""
    def dite(m: re.Match) -> str:
        valeur = float(m.group(1).replace(",", "."))
        mot = _UNITES_EN_MOTS[m.group(2).casefold()]
        return f"{m.group(1)} {mot}{'s' if valeur >= 2 else ''}"

    return _UNITE_DITE.sub(dite, texte or "")


def _phrase_de_la_question(q: dict, article_nom: str) -> str:
    """SA-52 (appel 2604) : la question d'un choix est une PHRASE à dire, jamais une étiquette (« taille pour X : 33 cl… ») que le modèle
    lit telle quelle : « Quelle taille pour votre X : 33 centilitres, 1,5 litre ou 2 litres ? » ; « Pour votre X, qu'est-ce que vous prenez
    comme couleurs, deux au choix : … ? ». Sans accord deviné (« comme » ne dépend pas du genre du nom du groupe)."""
    if not q["options"]:
        return f"Il faut préciser : {q['nom']}."
    options = liste_dite([_unites_dites(o) for o in q["options"]])
    if q["type"] == "declinaison":
        return f"{q.get('libelle') or 'Quel choix'} pour votre {article_nom} : {options} ?"
    nom = re.sub(r"\s*\([^)]*\)", "", q["nom"]).strip() or q["nom"]
    nom = _unites_dites(nom[:1].lower() + nom[1:])
    combien = ""
    if q.get("max", 1) > 1:
        combien = f", {nombre_en_lettres(q['max'])} au choix" if q.get("min") == q["max"] else f", jusqu'à {nombre_en_lettres(q['max'])}"
    return f"Pour votre {article_nom}, qu'est-ce que vous prenez comme {nom}{combien} : {options} ?"


def _appliquer_les_defauts(article: dict, ligne: dict) -> None:
    """Les options pré-cochées d'un groupe obligatoire sont prises d'office (la sauce de base) ; l'appelant peut en changer."""
    for chemin, g in _groupes_a_remplir(article, ligne):
        if g["min"] >= 1 and _compte(ligne, chemin, g) == 0:
            for o in opt1.brique_opt1_choix_obligatoire(g):  # le défaut du groupe, ou celui de l'option : une seule règle (OPT1)
                if _compte(ligne, chemin, g) < g["max"]:
                    # FOR8, FOR14 : le seul choix d'une étape est posé d'office à la quantité de l'étape (huit pièces du plateau)
                    _niveau(ligne["choix"], chemin).append(FO.choix_d_etape(g, o, g["min"]) if FO.est_une_etape(g)
                                                           else {"option_code": o["code"], "nom": o["nom"], "quantite": 1, "choix": []})


def _choisir(ligne: dict, chemin: tuple[str, ...], groupe: dict, option: dict, quantite: int) -> Resultat | None:
    """Pose ``quantite`` de cette option. Un choix unique (obligatoire, un seul) est REMPLACÉ (changement d'avis) ; sinon les maximums du
    groupe et de l'option sont respectés. ``None`` : posé."""
    if option["rupture"]:
        return _r("RUPTURE", {"nom": option["nom"], "code": option["code"]}, f"{option['nom']} n'est plus disponible.")
    niveau = _niveau(ligne["choix"], chemin)
    if groupe["max"] == 1 and (groupe["min"] >= 1 or FO.est_une_etape(groupe)):
        return remplacer_un_choix(niveau, groupe, option)
    existant = next((c for c in niveau if c["option_code"] == option["code"] and FO.du_groupe(c, groupe)), None)
    total_groupe = _compte(ligne, chemin, groupe)
    nouvelle = (existant["quantite"] if existant else 0) + quantite
    if total_groupe + quantite > groupe["max"] or nouvelle > groupe["max_par_option"]:
        return _r(
            "MAXIMUM_ATTEINT", {"groupe": groupe["nom"], "option": option["nom"], "maximum": groupe["max"], "maximum_par_option": groupe["max_par_option"]},
            f"{groupe['nom']} : pas plus de {nombre_en_lettres(groupe['max'] if total_groupe + quantite > groupe['max'] else groupe['max_par_option'])} ; {option['nom']} n'est pas pris.",
        )
    if existant:
        existant["quantite"] = nouvelle
    else:
        niveau.append(FO.choix_d_etape(groupe, option, quantite) if FO.est_une_etape(groupe)
                      else {"option_code": option["code"], "nom": option["nom"], "quantite": quantite, "choix": []})
    return None


def remplacer_un_choix(niveau: list[dict], groupe: dict, option: dict) -> None:
    """B10, B11 (7c) : un choix unique (un groupe obligatoire d'un seul choix, une étape de formule d'un seul choix) est REMPLACÉ : seul le choix de CE groupe
    change ; les autres groupes et étapes sont gardés. Le nouveau choix repart sans les choix de l'ancien (la sauce de l'ancien plat n'est pas reportée)."""
    niveau[:] = [c for c in niveau if not FO.du_groupe(c, groupe)]
    niveau.append(FO.choix_d_etape(groupe, option) if FO.est_une_etape(groupe) else {"option_code": option["code"], "nom": option["nom"], "quantite": 1, "choix": []})


def _options_disponibles(article: dict, ligne: dict, roles: tuple[str, ...] | None = None) -> dict[str, tuple[tuple[str, ...], dict, dict]]:
    """Index identifiant → (chemin, groupe, option) de tout ce que ``ligne`` peut encore choisir."""
    index: dict[str, tuple[tuple[str, ...], dict, dict]] = {}
    for chemin, g in _groupes_a_remplir(article, ligne):
        if roles and g["role"] not in roles:
            continue
        for o in g["options"]:
            if o["vendable"]:
                index[f"{'/'.join(chemin)}|{g['id']}|{o['code']}"] = (chemin, g, o)
    return index


def _sans_le_nom_du_groupe(elements: list[Element], index: dict, morceau: str) -> dict | None:
    """SA-52 (appel 2604) : « finition mate » quand l'option s'appelle « Mate » dans le groupe « Finitions » : le nom du groupe dit avec
    l'option n'est pas un mot de son nom. Le morceau sans les mots des noms de groupes est cherché ; retenu seulement si l'option retenue est
    dans un groupe qui porte TOUS les mots retirés (zéro faux sûr). ``None`` : rien de plus sûr."""
    mots_des_groupes = {m for (_, g, _) in index.values() for m in norme_de_recherche(g["nom"]).split()}
    dits = norme_de_recherche(morceau).split()
    retires = {m for m in dits if m in mots_des_groupes}
    reste = " ".join(m for m in dits if m not in mots_des_groupes)
    if not retires or not reste:
        return None
    trouve = _chercher_dans(elements, reste)
    if trouve["statut"] != "RETENU" or not retires <= set(norme_de_recherche(index[trouve["retenu"]][1]["nom"]).split()):
        return None
    return trouve


def choix_sans_objet(ligne: dict, morceau: str, notes_libres: bool) -> None:
    """Lot 4 (M01, E19, appel 2642) : un choix dit pour un article qui n'en a aucun n'est jamais un refus : il devient une note de ligne quand les
    notes libres sont permises, sinon il est ignoré ; dans les deux cas il est signalé (``choix_sans_objet`` de la ligne, rendu dans les faits)."""
    ligne.setdefault("choix_sans_objet", []).append(morceau)
    if notes_libres:
        inconnue.ajouter_a_la_note(ligne, morceau)  # la même note que celle d'une règle inconnue (E29) : une seule fonction


def _appliquer_les_choix(article: dict, ligne: dict, texte: str, *, roles: tuple[str, ...] | None = None, dans: str | None = None,
                         notes_libres: bool = True) -> Resultat | None:
    """Les choix dits (« sauce barbecue et double fromage ») cherchés DANS les groupes de l'article : jamais ailleurs. ``dans`` : un
    groupe d'abord (la question ouverte). Rend un refus fermé ou ``None`` quand tout est posé."""
    for quantite, morceau, brut in lecture.morceaux_d_options(texte):
        if roles == ("moities",):
            quantite, morceau = 1, brut  # lot 4 (C13, 2663) : une moitié est UN nom (« 4 fromages ») ; son nombre n'est jamais une quantité
        cible = dans
        if article.get("formule") and roles is None:
            refus, cible = placer_les_choix(article, ligne, morceau, dans)
            if refus is not None:
                return refus
        index = _options_disponibles(article, ligne, roles)
        if not index and not _options_disponibles(article, ligne, None):
            choix_sans_objet(ligne, brut.strip(" ,;."), notes_libres)
            continue
        if not index:
            return _r("HORS_CARTE", {"article": ligne["nom"], "raison": "aucun_choix"}, f"{ligne['nom']} ne se prend pas avec des choix.")
        elements = [Element(cle, o["nom"], tuple(o.get("synonymes") or ()), g["nom"]) for cle, (_, g, o) in index.items()]
        trouve = None
        if brut != morceau:
            # « 4 saisons » : le nombre est peut-être le début d'un NOM. Le texte tel que dit est pris s'il est certain.
            entier = _chercher_dans(elements, brut)
            if _est_le_nom(entier, brut):
                trouve, quantite, morceau = entier, 1, brut
        if trouve is None and cible:
            restreint = [e for e in elements if index[e.id][1]["id"] == cible]
            trouve = _chercher_dans(restreint, morceau) if restreint else None
            if trouve and trouve["statut"] == "INTROUVABLE":
                trouve = None
        if trouve is None:
            trouve = _chercher_dans(elements, morceau)
        if trouve["statut"] != "RETENU":
            trouve = _sans_le_nom_du_groupe(elements, index, morceau) or trouve
        if trouve["statut"] != "RETENU" and _dans_la_composition(article, brut):
            continue  # SA-52 : ce que l'article contient déjà (sa description, ses ingrédients) : rien à choisir ni à refuser
        if trouve["statut"] == "AMBIGU":
            noms = [c["libelle"] for c in trouve["candidats"]]
            return _r("AMBIGU", {"candidats": noms, "dit": morceau, CLE_OPTION_DITE: morceau}, "Vous voulez dire : " + liste_dite(noms) + " ?")
        if trouve["statut"] != "RETENU":
            proches = [index[c["id"]][2] for c in trouve["candidats"] if c["id"] in index]
            suppl = [o for c in trouve["candidats"] if c["id"] in index for o in [index[c["id"]][2]] if index[c["id"]][1]["role"] == "supplement"]
            propose = suppl or proches
            return _r(
                "HORS_CARTE",
                {"article": ligne["nom"], "dit": morceau, "plus_proches": [{"nom": o["nom"], "prix": o["prix"]} for o in propose[:3]]},
                f"Je n'ai pas « {morceau} » pour {ligne['nom']}."
                + (f" Le plus proche : {liste_dite([o['nom'] for o in propose[:3]])}." if propose else _ce_qui_se_choisit(index)),
            )
        chemin, g, o = index[trouve["retenu"]]
        refus = _choisir(ligne, chemin, g, o, quantite)
        if refus is not None:
            return refus
    return None


def _ce_qui_se_choisit(index: dict) -> str:
    """Aucune option proche du mot dit : le refus dit ce que l'article propose (DEC4, conversation du 19/11), au plus quatre noms."""
    noms = list(dict.fromkeys(o["nom"] for _, (_, _, o) in index.items()))[:4]
    return f" Ce qui se choisit : {liste_dite(noms)}." if noms else ""


def placer_les_choix(article: dict, ligne: dict, morceau: str, dans: str | None) -> tuple[Resultat | None, str | None]:
    """B10 (FOR1, FOR2) : un mot de ``composition`` d'une formule se range sur l'étape dont il est le choix ; ``dans`` : la question d'étape ouverte, et elle seule.
    Un mot choix de deux étapes est refusé (jamais deviné) ; un mot hors de la ligne (FOR3) est refusé avec la raison et les choix de l'étape. ``None`` : le mot
    se pose (sur son étape, ou sur un choix du plat déjà choisi). Rend ``(refus, étape où chercher)``."""
    ouvertes = [g for g in article["groupes"] if g["id"] == dans] if dans else None
    refus = FO.etapes_du_mot(article, morceau, ouvertes, ligne.get("choix") or [])
    if refus is None:
        return None, dans
    if "cible" in refus:
        return None, refus["cible"]
    if refus["raison"] == "choix_de_plusieurs_etapes":
        return _r("INCOMPLETE", {"article": ligne["nom"], **refus}, f"Pour quelle étape : {liste_dite(refus['etapes'])} ?", "etape"), None
    return _r("HORS_CARTE", {"article": ligne["nom"], **{k: v for k, v in refus.items() if k != "prix_max"}, **({"regle_prix_max": refus["prix_max"]} if refus.get("prix_max") else {})},
              f"Je n'ai pas « {morceau} » dans {ligne['nom']}."), None


def retirer_sur_le_plat(article: dict, ligne: dict, texte: str) -> Resultat | None:
    """Lot 11 (L11-03) : « sans olives » dit sur une formule se retire du plat choisi qui a cet ingrédient retirable ; deux plats qui l'ont : la question
    (jamais deviné, E12) ; aucun : une note de ligne (``retrait_en_note``, lot 4)."""
    choisis = [(c, o) for g in article["groupes"] if FO.est_une_etape(g) for o in g["options"] for c in ligne["choix"]
                if FO.du_groupe(c, g) and c["option_code"] == o["code"]]
    for _, morceau, _brut in lecture.morceaux_d_options(texte):
        porteurs = []
        for c, o in choisis:
            trouve = _chercher_dans([Element(nom, nom) for nom in o.get("retirables") or []], morceau)
            if trouve["statut"] == "RETENU":
                porteurs.append((c, trouve["retenu"]))
        if len(porteurs) > 1:
            noms = [c["nom"] for c, _ in porteurs]
            return _r("AMBIGU", {"candidats": noms, "dit": morceau}, "Sur lequel : " + liste_dite(noms) + " ?")
        if porteurs:
            c, nom = porteurs[0]
            if nom not in c.setdefault("retires", []):
                c["retires"].append(nom)
            continue
        retrait_en_note({"retirables": [], "ingredients": []}, ligne, morceau)
    return None


def a_la_taille_de_la_formule(article: dict, ligne: dict) -> Resultat | None:
    """FOR6 (D34, conflit 3) : les choix des étapes que la taille de la formule change passent à sa déclinaison (le coca reste coca, en grand) ; un choix qui n'a
    pas cette déclinaison est refusé avec les choix qui l'ont. FOR12, FOR15 : une alternative à la fois, rien de facturé à la quantité sur une ligne à volonté."""
    if not article.get("formule"):
        return None
    taille = next((d.get("taille") for d in article["declinaisons"] if d["code"] == ligne.get("code")), None)
    for g in article["groupes"]:
        if not FO.est_une_etape(g):
            continue
        dans = [c for c in ligne["choix"] if FO.du_groupe(c, g)]
        apres, refus = for6.brique_for6_passer_en_maxi(g, dans, taille)
        if refus is None:
            apres, refus = for12.brique_for12_une_alternative(g, apres)
        if refus is not None and refus["raison"] == for12.RAISON:
            return _r("HORS_CARTE", {"article": ligne["nom"], **refus}, for12.phrase_du_refus(ligne["nom"], refus["choix"]))
        if refus is not None:
            return _r("HORS_CARTE", {"article": ligne["nom"], **refus}, f"{refus.get('valeur') or ligne['nom']} : {liste_dite(refus.get('choix') or [])} ?")
        apres = for15.brique_for15_a_volonte(g, apres)
        ligne["choix"] = [c for c in ligne["choix"] if c not in dans] + apres
    return None


def _sans_accent(texte: str) -> str:
    """Le texte en minuscules sans accents, de même longueur (une position dans l'un est la même dans l'autre)."""
    return "".join(unicodedata.normalize("NFD", c)[0] for c in texte).lower()


def _moities_choisies(article: dict, ligne: dict) -> list[str]:
    """Les noms des moitiés déjà choisies sur la ligne (les options des groupes de rôle ``moities``)."""
    noms: list[str] = []
    for chemin, g in _groupes_a_remplir(article, ligne):
        if g.get("role") != "moities":
            continue
        codes = {o["code"] for o in g["options"]}
        noms += [c["nom"] for c in _niveau(ligne["choix"], chemin) if c["option_code"] in codes and c.get("nom")]
    return noms


# Ce qui relie « X » à la moitié dans « sans X sur la moitié A » : retiré pour ne garder que l'ingrédient.
_LIAISON_AVANT_MOITIE = re.compile(
    r"(?:^|\s)(?:sur|de|pour|dans|cote|a)\s+(?:(?:la|le|l)\s*'?\s*)?(?:moitie\s+)?(?:(?:de|du|la|le|l)\s*'?\s*)?$"
)


def _retrait_et_moitie(morceau: str, moities: list[str]) -> tuple[str, str | None]:
    """« X sur la A » : le retrait (« X ») et la moitié dite (« A »). ``None`` : aucune moitié nommée."""
    normalise = _sans_accent(morceau)
    trouvees = []
    for nom in dict.fromkeys(moities):
        m = re.search(rf"(?<!\w){re.escape(_sans_accent(nom))}(?!\w)", normalise)
        if m:
            trouvees.append((m, nom))
    if len(trouvees) != 1:
        return morceau.strip(" ,;."), None
    m, nom = trouvees[0]
    avant = normalise[: m.start()]
    liaison = _LIAISON_AVANT_MOITIE.search(avant)
    coupe = liaison.start() if liaison else m.start()
    return f"{morceau[:coupe]} {morceau[m.end():]}".strip(" ,;."), nom


def _noter_un_retrait_par_moitie(ligne: dict, texte: str, moities: list[str]) -> Resultat | None:
    """Une ligne en deux moitiés : le code n'essaie pas de retirer un ingrédient d'une moitié (le catalogue ne le sait pas). Il l'ACCEPTE et
    l'écrit en note sur la ligne (« sans X sur la moitié A »), que la source reçoit avec la ligne. Quelle moitié :
    celle que l'appelant a nommée ; sinon une question fermée. Ce n'est pas une note libre : le réglage des notes libres n'a pas à l'autoriser."""
    notes = []
    for _, morceau, _brut in lecture.morceaux_d_options(texte):
        ingredient, moitie = _retrait_et_moitie(morceau, moities)
        if not ingredient:
            return _r("INCOMPLETE", {"raison": "retrait_sans_ingredient"}, "Qu'est-ce qu'il faut retirer ?")
        if moitie is None:
            return _r(
                "AMBIGU", {"candidats": list(moities), "dit": ingredient},
                f"Sans {ingredient} sur quelle moitié : " + liste_dite(list(dict.fromkeys(moities))) + " ?",
            )
        notes.append(f"sans {ingredient} sur la moitié {moitie}")
    for note in notes:
        if note not in (ligne.get("note") or ""):
            ligne["note"] = (f"{ligne['note']} ; {note}" if ligne.get("note") else note)[:LONGUEUR_NOTE]
    return None


def retrait_en_note(article: dict, ligne: dict, morceau: str) -> bool:
    """Lot 4 (M05, E19) : un retrait que le catalogue ne décrit pas (l'article n'a pas la liste de ce qu'il contient, ou la chose n'y est pas) ne
    bloque jamais : il devient une note de ligne (« sans coriandre »), envoyée avec la ligne. Vrai : noté. Un ingrédient décrit mais non retirable
    reste refusé (règle du catalogue)."""
    retirables = article.get("retirables") or []
    decrits = [*retirables, *(article.get("ingredients") or [])]
    if decrits and _chercher_dans([Element(str(n), str(n)) for n in decrits], morceau)["statut"] != "INTROUVABLE":
        return False
    note = f"sans {morceau.strip(' ,;.')}"
    if note not in (ligne.get("note") or ""):
        ligne["note"] = (f"{ligne['note']} ; {note}" if ligne.get("note") else note)[:LONGUEUR_NOTE]
    return True


def _appliquer_les_retraits(article: dict, ligne: dict, texte: str) -> Resultat | None:
    retirables = article["retirables"]
    # SA-22 : une ligne en deux moitiés : le retrait devient une note de ligne (voir ``_noter_un_retrait_par_moitie``).
    moities = _moities_choisies(article, ligne)
    if len(moities) >= 2:
        return _noter_un_retrait_par_moitie(ligne, texte, moities)
    for _, morceau, _brut in lecture.morceaux_d_options(texte):
        if retrait_en_note(article, ligne, morceau):
            continue
        trouve = _chercher_dans([Element(nom, nom) for nom in retirables], morceau)
        if trouve["statut"] == "AMBIGU":
            noms = [c["libelle"] for c in trouve["candidats"]]
            return _r("AMBIGU", {"candidats": noms, "dit": morceau}, "Vous voulez retirer : " + liste_dite(noms) + " ?")
        if trouve["statut"] != "RETENU":
            return _r(
                "HORS_CARTE", {"article": ligne["nom"], "dit": morceau, "retirables": list(retirables)},
                f"On ne peut pas retirer « {morceau} » de {ligne['nom']}. On peut retirer : {liste_dite_et(list(retirables))}.",
            )
        if trouve["retenu"] not in ligne["retires"]:
            ligne["retires"].append(trouve["retenu"])
    return None


def _noter(ligne: dict, note: str, regles: Reglages) -> Resultat | None:
    note = " ".join((note or "").split())
    if not note:
        return None
    if not regles.notes_libres:
        return _r("HORS_CARTE", {"raison": "notes_non_acceptees"}, "Je ne peux pas noter cette demande.")
    ligne["note"] = (f"{ligne['note']} ; {note}" if ligne.get("note") else note)[:LONGUEUR_NOTE]
    return None


def noter_la_commande(p: dict[str, Any], regles: Reglages, texte: str | None) -> Resultat | None:
    """Lot 4 (E-35) : la note de toute la commande (la case ``note_generale``), sous la même règle que la note d'une ligne : refusée quand le
    réglage des notes libres est éteint (rien n'est noté), sinon posée. ``None`` : posée, ou rien à noter."""
    note = " ".join(str(texte or "").split())
    if not note:
        return None
    if not regles.notes_libres:
        return _avec(_r("HORS_CARTE", {"raison": "notes_non_acceptees"}, "Je ne peux pas noter cette demande."), p)
    p["note"] = note[:LONGUEUR_NOTE]
    return None


async def poser_le_code_de_remise(source: Source, p: dict[str, Any], regles: Reglages, dit: str | None, reduction_annoncee: bool) -> Resultat | None:
    """Lot 14 (OFF3) : le code de remise que l'appelant dit est VÉRIFIÉ par le code contre les remises à code de l'établissement (jamais deviné).

    - un code connu est gardé dans l'appel (une fois) et la remise se chiffre avec le panier ; le retour dit ce que la remise donne (faits ``code``, ``reduction``) ;
    - un code inconnu (faux, expiré, d'une remise brouillon ou d'un autre établissement : le même refus) rend la raison ``code_inconnu`` et ne pose rien ;
    - ``reduction_annoncee`` sans code (« j'ai un code » sans le dire) : le retour rend le fait et ``manque`` ``code_de_remise`` ; la question vient du modèle.
    ``None`` : rien à faire."""
    lecture = getattr(source, "codes_de_remise", None)
    if lecture is None:
        return None
    if not str(dit or "").strip():
        return _avec(_r("OK", {"reduction_annoncee": True}, "", "code_de_remise"), p) if reduction_annoncee else None
    verdict = off3.brique_off3_verifier_le_code(dit, await lecture())
    if "raison" in verdict:
        return _avec(_r("HORS_CARTE", {"raison": off3.RAISON, "dit": verdict["dit"]}, "Je ne connais pas ce code."), p)
    if verdict["code"] not in p.setdefault("codes_dits", []):
        p["codes_dits"].append(verdict["code"])
    if verdict["ref"] not in p.setdefault("remises_du_code", []):
        p["remises_du_code"].append(verdict["ref"])  # ce que le code a donné droit : sa remise se dit au moment où elle s'applique (``porte.poser_la_remise_du_code``)
    chiffre = await _chiffrer(source, p, regles) if p["lignes"] and p["mode"] and not P.a_completer(p) else None
    appliquee = next((r for r in (chiffre.faits.get("remises") or []) if r["ref"] == verdict["ref"]), None) if chiffre is not None and chiffre.statut == "OK" else None
    faits = {"code": verdict["code"], "remise": verdict["nom"], "appliquee": appliquee is not None}
    if appliquee is None:
        return _avec(_r("OK", faits, f"Le code {verdict['code']} est bon, {_dit(verdict['nom'])} s'appliquera dès que votre commande y donne droit."), p)
    return _avec(_r("OK", {**faits, "reduction": appliquee["montant"]}, _phrase_d_une_remise_appliquee(appliquee)), p)


# --------------------------------------------------------------------------- #
# Préalables : le mode, la zone
# --------------------------------------------------------------------------- #


def _phrase_des_modes(source: Source) -> str:
    return liste_dite([source.libelles_des_modes.get(m, m) for m in source.modes])


async def question_du_mode(source: Source, p: dict[str, Any], statut: str) -> Resultat:
    """La question du mode. Appel 2610 : quand AUCUN mode ne prend de commande maintenant, la personne le sait dès cette première question
    (la fermeture et la reprise, dites une fois par commande), jamais à la fin. Aucun mode planifiable : la fermeture seule, sans question
    de mode. Une heure déjà gardée vaut accord pour plus tard : rien n'est ajouté."""
    question = f"{_phrase_des_modes(source).capitalize()} ?"
    faits: dict[str, Any] = {"modes": list(source.modes)}
    if not p.get("fermeture_dite") and not p.get("heure_voulue"):
        etats = [await source.etat(m) for m in source.modes]
        if etats and not any(e["ouvert"] for e in etats):
            ferme = etats[0]
            faits.update({k: ferme.get(k) for k in ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")})
            phrase = annoncer_la_fermeture(p, ferme)
            if not any(e.get("planifiee_permise") for e in etats):
                return _r(ferme.get("statut") or "FERME", faits, phrase)
            return _r(statut, {**faits, "ferme_maintenant": True}, f"{phrase} {question}", "mode")
    return _r(statut, faits, question, "mode")


async def _prealables(source: Source, p: dict[str, Any], regles: Reglages, pour_prendre: bool = False) -> Resultat | None:
    """Ce qui manque avant les articles (le mode, puis la zone). ``pour_prendre`` : la prise d'un article ; une commune dite hors zone y suffit
    (B12, conversation 2 : l'article est pris, c'est la zone qui est refusée, et elle reste exigée à la fin)."""
    if not p["mode"]:
        return _avec(await question_du_mode(source, p, "INCOMPLETE"), p)
    if pour_prendre and p.get("commune_hors_zone"):
        return None
    if regles.ordre_impose and source.exige_une_zone(p["mode"]) and not p.get("zone"):
        return _avec(_r("INCOMPLETE", {}, source.question_de_la_zone, "zone"), p)
    return None


def _rien_n_est_pris(p: dict[str, Any]) -> bool:
    """Aucune ligne au panier et rien de gardé en attente d'un préalable (M116)."""
    return not p["lignes"] and not p.get("dits_en_attente")


def _zone_id(p: dict[str, Any]) -> int | None:
    return (p.get("zone") or {}).get("id")


async def _chiffrer(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
    """Le panier (ses lignes complètes) chiffré par la source. Sans ligne complète : ``OK`` à zéro."""
    lignes = P.pour_le_chiffrage(p)
    if not lignes or not p["mode"]:
        return _r("OK", {"lignes": [], "sous_total": 0, "frais": 0, "total": 0})
    # Le client (son numéro, jamais son nom) : la source peut en avoir besoin pour une remise qui le reconnaît (fidélité, lot 7).
    telephone = (p.get("client") or {}).get("telephone") or (p.get("client") or {}).get("telephone_affiche")
    return await source.chiffrer(p["mode"], lignes, _zone_id(p), {"client": {"telephone": telephone} if telephone else None, "servi_le": _servi_le(p), "codes": list(p.get("codes_dits") or [])})


def _servi_le(p: dict[str, Any]) -> datetime | None:
    """Lot 12 (PRX1) : l'heure voulue d'une précommande, ou ``None`` (l'instant de l'appel) : la carte se lit à ce moment-là."""
    voulue = p.get("heure_voulue")
    return datetime.fromisoformat(voulue) if isinstance(voulue, str) else voulue


async def _article_de_la_carte(source: Source, p: dict[str, Any], ref: str, mode: str) -> dict[str, Any] | None:
    """L'article de la carte au moment que la commande regarde (l'heure voulue d'une précommande, sinon maintenant)."""
    servi_le = _servi_le(p)
    return await (source.article(ref, mode, servi_le=servi_le) if servi_le else source.article(ref, mode))


def _valider(p: dict[str, Any], essai: dict[str, Any]) -> None:
    """Adopte l'état ``essai`` : le dictionnaire de l'appel garde son identité (la fiche le tient)."""
    p.clear()
    p.update(essai)


# --------------------------------------------------------------------------- #
# choisir_mode
# --------------------------------------------------------------------------- #


def _mode_dit(source: Source, texte: str | None) -> str | None:
    voulu = lecture.en_chiffres(str(texte or "")).strip().casefold().replace(" ", "_")
    for m in source.modes:
        if voulu in (m.casefold(), source.libelles_des_modes.get(m, "").casefold().replace(" ", "_")):
            return m
    # Un verbe pour un nom (le mode dit à l'infinitif) : un mot dit et un mot du mode partagent leurs quatre premières lettres, un seul mode en est là.
    dits = {w[:4] for w in re.findall(r"[a-zà-ÿ]{4,}", str(texte or "").casefold())}
    proches = [m for m in source.modes if dits & {w[:4] for w in re.findall(r"[a-zà-ÿ]{4,}", f"{m} {source.libelles_des_modes.get(m, '')}".replace("_", " ").casefold())}]
    return proches[0] if len(proches) == 1 else None


def _avec_le_moment(r: Resultat | None, texte_dit: str) -> Resultat | None:
    """Lot 1 (complément de Pierre, point 3) : une heure retenue porte son ``MomentVoulu`` (instant avec fuseau et mots dits) dans ``faits.moment_voulu``."""
    if r is None or r.statut != "RETENU" or not r.faits.get("heure_voulue"):
        return r
    moment = MomentVoulu(debut=r.faits["heure_voulue"], texte_dit=texte_dit)
    return Resultat(r.statut, {**r.faits, "moment_voulu": moment.vers_json()}, r.suggestion, r.manque)


async def heure_du_lieu(source: Source, texte: str | None, etat: dict[str, Any] | None = None) -> Resultat | None:
    """M74 (appels 2562, 2563) : l'heure qu'un modèle passe à un outil n'est pas toujours celle rendue par la résolution de la date. Mécanisme
    commun à toute heure voulue, sans mot de métier : un instant précis (ISO avec fuseau) est gardé tel quel ; une date-heure ISO sans fuseau
    (« 2026-11-17T12:00:00 ») ou des mots (« demain midi ») sont résolus par le CODE au fuseau du lieu (``source.resoudre_une_date``), jamais
    devinés. Rend ``RETENU`` avec ``faits.heure_voulue`` (aware) et ``faits.moment_voulu`` (``MomentVoulu``, lot 1), ou le résultat de la résolution
    (doute, heure manquante) à dire ; ``None`` sans texte."""
    t = (texte or "").strip()
    if not t:
        return None
    return _avec_le_moment(await _resoudre_l_heure_du_lieu(source, t, etat), t)


async def _resoudre_l_heure_du_lieu(source: Source, t: str, etat: dict[str, Any] | None) -> Resultat:
    try:
        voulue = datetime.fromisoformat(t)
    except ValueError:
        if etat is None:
            return await source.resoudre_une_date(t, t)
        if dates_futures.moment_du_jour(t):
            dates_futures.retenir_le_moment(etat, t)  # M85 : « demain soir » garde le soir pour l'heure dite ensuite
        r = await source.resoudre_une_date(t, dates_futures.heure_avec_le_moment(etat, t))
        garde = etat.get(dates_futures.CLE_DU_MOMENT) or {}
        if r.statut == "INTROUVABLE" and r.manque == "jour" and garde.get("texte"):
            # une heure seule (« huit heures et demie ») : le jour dit plus tôt, avec son moment, est repris
            return await source.resoudre_une_date(garde["texte"], dates_futures.heure_avec_le_moment(etat, t))
        return r
    if voulue.tzinfo is not None:
        return Resultat("RETENU", {"heure_voulue": voulue.isoformat()}, "")
    return await source.resoudre_une_date(f"{voulue.day}/{voulue.month}", f"{voulue.hour}:{voulue.minute:02d}")


def poser_le_moment(p: dict[str, Any], moment: MomentVoulu) -> None:
    """Le seul endroit qui pose l'heure voulue sur la commande : ``moment_voulu`` (le type) et ``heure_voulue`` (son instant, lu par
    l'enregistrement et les prises), écrits ensemble depuis le même objet : ils ne divergent jamais."""
    p["moment_voulu"] = moment.vers_json()
    p["heure_voulue"] = moment.debut


def _sans_jour_dit(texte: str, vu_de: datetime) -> bool:
    """Le texte dit une heure seule (« midi », « vers dix-neuf heures ») : aucun jour n'y est lu."""
    try:
        return dates_futures.resoudre_une_date(texte, vu_de).statut == dates_futures.INTROUVABLE
    except ValueError:
        return False


async def resoudre_l_heure_selon_l_ouverture(source: Source, p: dict[str, Any], texte: str) -> Resultat | None:
    """Lot 4 (S01, C9, appel 2667) : l'heure dite, résolue par le code (``heure_du_lieu``). Une heure dite SEULE (« alors midi ») qui tombe quand le
    lieu est fermé aujourd'hui vaut pour la prochaine ouverture (« nous rouvrons jeudi » puis « midi » : jeudi midi), si ce créneau-là tient ;
    sinon elle reste telle quelle et la vérification du créneau dira pourquoi. ``None`` sans texte."""
    jour_dit = (p.get(dates_futures.CLE_DU_MOMENT) or {}).get("jour")  # lu avant la résolution, qui le remplace
    r = await heure_du_lieu(source, texte, p)
    if r is None or r.statut != "RETENU" or not r.faits.get("heure_voulue"):
        return r
    voulue = datetime.fromisoformat(r.faits["heure_voulue"])
    if jour_dit and _sans_jour_dit(texte, voulue):
        # M85 (appel 2667) : « demain à trois heures », puis « alors midi » : le jour dit plus tôt reste celui de la commande
        meme_jour = _avec_le_moment(await source.resoudre_une_date(jour_dit, texte), texte)
        if meme_jour is not None and meme_jour.statut == "RETENU" and meme_jour.faits.get("heure_voulue"):
            r, voulue = meme_jour, datetime.fromisoformat(meme_jour.faits["heure_voulue"])
    if not p.get("mode"):
        return r
    verifier = getattr(source, "verifier_un_creneau", None)
    if verifier is None or not _sans_jour_dit(texte, voulue) or await verifier(p["mode"], voulue) is None:
        return r
    prochaine = (await source.etat(p["mode"])).get("prochaine_ouverture")
    if not isinstance(prochaine, datetime) or prochaine.date() == voulue.date():
        return r
    jour = prochaine.astimezone(voulue.tzinfo)
    autre = _avec_le_moment(await source.resoudre_une_date(f"{jour.day}/{jour.month}", f"{voulue.hour}:{voulue.minute:02d}"), texte)
    if autre is not None and autre.statut == "RETENU" and await verifier(p["mode"], datetime.fromisoformat(autre.faits["heure_voulue"])) is None:
        return autre
    return r


async def poser_l_heure(source: Source, p: dict[str, Any], texte: str | None) -> Resultat | None:
    """Lot 4 (E28) : l'opération qui pose l'heure voulue. Elle la résout (``resoudre_l_heure_selon_l_ouverture``), la pose (``poser_le_moment``) et
    vérifie son créneau tout de suite (``verifier_le_creneau``), à chaque correction aussi. ``None`` : posée et valable ; sinon le doute (une question)
    ou le refus du créneau, à dire."""
    if not (texte or "").strip():
        return None
    r = await resoudre_l_heure_selon_l_ouverture(source, p, str(texte))
    if r is None:
        return None
    if r.statut != "RETENU" or not r.faits.get("moment_voulu"):
        return _avec(r, p)
    poser_le_moment(p, MomentVoulu.depuis_json(r.faits["moment_voulu"]))
    return await verifier_le_creneau(source, p)


async def garder_l_heure(source: Source, p: dict[str, Any], texte: str | None) -> None:
    """D15 : une heure voulue dite dès le premier tour (« pour ce soir 19 h ») est GARDÉE jusqu'à ``finaliser``, résolue par le code (M74).
    Une heure qui ne se résout pas sûrement est ignorée : la question de l'heure se posera à ``finaliser``."""
    r = await heure_du_lieu(source, texte, p)
    if r is not None and r.statut == "RETENU" and r.faits.get("moment_voulu"):
        poser_le_moment(p, MomentVoulu.depuis_json(r.faits["moment_voulu"]))


async def choisir_mode(source: Source, p: dict[str, Any], regles: Reglages, mode: str | None, heure_voulue: str | None = None) -> Resultat:
    """Pose le mode de la commande (les modes sont ceux de la source). Les articles déjà pris sont GARDÉS : on les rechiffre pour
    le nouveau mode, et on dit ceux qui n'y tiennent plus. Un mode fermé n'est jamais posé : la raison fermée est rendue, SAUF quand le réglage
    du type permet de commander pour plus tard (D15) : le mode est posé, la commande est « à planifier » (``FERME_PLANIFIABLE``)."""
    choisi = _mode_dit(source, mode)
    if choisi is None:
        return await question_du_mode(source, p, "ARGUMENT_INVALIDE")
    etat = await source.etat(choisi)
    a_planifier = not etat["ouvert"] and bool(etat.get("planifiee_permise"))
    if not etat["ouvert"] and not a_planifier:
        return _avec(
            _r(etat["statut"], {"mode": choisi, **{k: etat.get(k) for k in ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")}}, annoncer_la_fermeture(p, etat)),
            p,
        )
    await garder_l_heure(source, p, heure_voulue)
    r = await _poser_le_mode(source, p, regles, choisi, a_planifier)
    if not a_planifier or r.statut != "OK":
        return r
    # Fermé mais planifiable : le résultat dit la fermeture et propose le créneau ; la question en cours (zone, articles) suit, sinon l'heure.
    # Appel 2610 : la fermeture déjà dite avec la question du mode ne se redit pas.
    fermeture = annoncer_la_fermeture(p, etat)
    dire = getattr(source, "quand_dit", None)
    if p.get("heure_voulue") and dire:
        # Appel 2566 : l'heure est déjà dite et gardée, c'est déjà l'accord pour plus tard ; la proposition de « plus tard » n'est pas refaite (le modèle la
        # tournait en « est-ce que cela vous convient ? »). Le résultat dit pour quand la commande est prise ; le créneau se vérifie à ``finaliser``.
        fermeture = f"Commande pour {await dire(datetime.fromisoformat(p['heure_voulue']))}."
    faits = {**r.faits, **{k: etat.get(k) for k in ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")}, "a_planifier": True, "fermeture": fermeture}
    prochaine = etat.get("prochaine_ouverture")
    if not p.get("heure_voulue") and not p.get("heure_proposee_faite") and isinstance(prochaine, datetime) and dire is not None:
        # Evan, 21/11 : « il faut lui indiquer dès le début de l'appel que le magasin est fermé et lui demander si elle veut planifier une commande pour
        # l'ouverture à 18 h ». La proposition est LA question du début (``heure_proposee``) ; ce qui manque ensuite (les articles, l'adresse) suit sa réponse.
        p["heure_proposee_faite"] = True
        phrase = f"{fermeture} Voulez-vous que je prépare votre commande pour {await dire(prochaine)} ?".strip()
        return _avec(_r("FERME_PLANIFIABLE", {**faits, "heure_proposee": prochaine.isoformat()}, phrase, "heure_proposee"), p)
    suite = r.suggestion if r.manque else ("" if p.get("heure_voulue") else "Pour quel jour et à quelle heure ?")
    phrase = fermeture + (f" {suite}" if suite else "")
    return _avec(_r("FERME_PLANIFIABLE", faits, phrase.strip(), r.manque), p)


async def _poser_le_mode(source: Source, p: dict[str, Any], regles: Reglages, choisi: str, a_planifier: bool) -> Resultat:
    essai = copy.deepcopy(p)
    essai["mode"] = choisi
    essai["a_planifier"] = a_planifier
    essai["mode_dit"] = source.libelles_des_modes.get(choisi, choisi)  # pour l'équipe, si une panne coupe l'appel (``contenu_dit``)
    if not source.exige_une_zone(choisi):
        essai["zone"] = essai["adresse"] = None
    P.toucher(essai)
    chiffre = await _chiffrer(source, essai, regles)
    _valider(p, essai)
    faits: dict[str, Any] = {"mode": choisi, "zone_requise": source.exige_une_zone(choisi)}
    if chiffre.statut != "OK":
        # Le nouveau mode ne tient pas pour un des articles (prix, minimum de la zone, rupture) : dit, rien n'est retiré en silence.
        faits["a_revoir"] = {"statut": chiffre.statut, **chiffre.faits}
        return _avec(_r("OK", faits, chiffre.suggestion), p)
    if source.exige_une_zone(choisi) and not p.get("zone"):
        if _rien_n_est_pris(p):
            faits["panier_vide"] = True  # M116 : le modèle ne parle pas de la commande comme si elle avait des articles
        return _avec(_r("OK", faits, source.question_de_la_zone, "zone"), p)
    repris = await _reprendre_les_dits(source, p, regles)
    if repris is not None:
        # SA-33 : ce qui était dit avant le mode est pris maintenant ; la suite est sa question, ou rien.
        return _avec(Resultat(repris.statut, {**faits, **repris.faits}, repris.suggestion, repris.manque), p)
    if not p["lignes"]:
        # Rien n'est encore pris : le résultat le dit (un manque à la fois), pour que le modèle enchaîne sur les articles que la personne a déjà dits,
        # ou les lui demande, au lieu de parler de la commande comme si elle avait des articles.
        return _avec(_r("OK", faits, "", "articles"), p)
    return _avec(_r("OK", faits, ""), p)


# --------------------------------------------------------------------------- #
# Lot 6 : l'ouverture, l'heure annoncée, l'adresse, la date
# --------------------------------------------------------------------------- #

CLES_DE_L_ETAT = ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")


async def lire_l_ouverture(source: Source, mode: str | None = None) -> dict[str, Any]:
    """Lot 4 (Q10, audit § 3.3, appel 2648) : LA lecture de l'ouverture, une seule, pour le décroché, l'état et les outils : les horaires, l'état
    du lieu (pause, débordé) et le forçage de l'organisation, lus par la source (``etat`` ; ``en_pause`` : une pause, dont la reprise seule compte).
    Rend ``{ouvert, etat (OUVERT, PAUSE, FERME), reprise, phrase, modes}``. Une pause sans fin connue n'a AUCUNE reprise (jamais inventée)."""
    modes = [mode] if mode else list(source.modes)
    etats = {m: await source.etat(m) for m in modes}
    ouverts = [m for m, e in etats.items() if e["ouvert"]]
    if ouverts or not etats:
        return {"ouvert": True, "etat": "OUVERT", "reprise": None, "phrase": "", "modes": {m: e["ouvert"] for m, e in etats.items()}}
    premier = next(iter(etats.values()))
    pause = bool(premier.get("en_pause"))
    reprise = premier.get("reprise") if pause else (premier.get("reprise") or premier.get("prochaine_ouverture"))
    return {"ouvert": False, "etat": "PAUSE" if pause else "FERME", "reprise": reprise, "phrase": premier.get("phrase") or "",
            "modes": {m: e["ouvert"] for m, e in etats.items()}}


async def etat_ouverture(source: Source, p: dict[str, Any], regles: Reglages, mode: str | None = None) -> Resultat:
    """Ce qui est ouvert maintenant. Sans ``mode`` : chacun des modes de la source (``faits.modes``). Avec un mode : son état, et le statut fermé
    (la raison et la reprise) quand il ne prend rien. Lecture seule : ni le mode, ni le panier ne changent."""
    if mode:
        choisi = _mode_dit(source, mode)
        if choisi is None:
            return _r("ARGUMENT_INVALIDE", {"modes": list(source.modes)}, f"{_phrase_des_modes(source).capitalize()} ?", "mode")
        modes = [choisi]
    else:
        modes = list(source.modes)
    lignes = []
    for m in modes:
        etat = await source.etat(m)
        lignes.append({"mode": m, "libelle": source.libelles_des_modes.get(m, m), "ouvert": etat["ouvert"], **{k: etat.get(k) for k in CLES_DE_L_ETAT}, "phrase": etat.get("phrase") or ""})
    if mode and not lignes[0]["ouvert"]:
        etat = await source.etat(modes[0])
        return _r(etat["statut"], {"modes": lignes}, etat.get("phrase") or "Nous ne prenons pas de commande en ce moment.")
    ouverts = [l["libelle"] for l in lignes if l["ouvert"]]
    return _r("OK", {"modes": lignes, "ouverts": ouverts}, "")


async def heure_annoncee(source: Source, p: dict[str, Any], regles: Reglages, mode: str | None = None) -> Resultat:
    """L'heure que le code annoncerait maintenant pour ce mode (le mode de la commande par défaut) ; quand le mode exige une zone, selon la zone. Rien n'est
    promis : seul l'enregistrement fixe l'heure. Le texte vient du code, jamais d'un calcul du modèle."""
    choisi = _mode_dit(source, mode) if mode else p.get("mode")
    if choisi is None:
        return _avec(_r("INCOMPLETE", {"modes": list(source.modes)}, f"{_phrase_des_modes(source).capitalize()} ?", "mode"), p)
    if source.exige_une_zone(choisi) and not p.get("zone"):
        return _avec(_r("INCOMPLETE", {"mode": choisi}, source.question_de_la_zone, "zone"), p)
    etat = await source.etat(choisi)
    if not etat["ouvert"]:
        return _avec(_r(etat["statut"], {"mode": choisi, **{k: etat.get(k) for k in CLES_DE_L_ETAT}}, etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."), p)
    annonce = await source.annonce(choisi, _zone_id(p))
    if annonce is None:
        return _r("INDISPONIBLE", {"mode": choisi}, "")
    return _r("OK", {"mode": choisi, "heure_annoncee": annonce["prete"], "texte": annonce["texte"], "minutes": annonce.get("minutes")}, f"Ce sera prêt {annonce['texte']}.")


def _sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte.casefold()) if not unicodedata.combining(c))


def voie_de_l_adresse(texte: str, commune: str, code_postal: str | None) -> str:
    """La voie dite (« 12 rue de la République ») : les mots dits, sans la commune ni le code postal reconnus par la vérification (lot 1, C6). Ne devine
    rien : on retire seulement ce que la source a reconnu, en fin d'adresse ; ce qui reste est la voie, éventuellement vide (une voie exigée : lot 4)."""
    reste = texte.strip()
    nom = re.escape(_sans_accent(commune)).replace(r"\-", "[- ]").replace(r"\ ", "[- ]")
    cp = re.escape(code_postal) if code_postal else None
    motifs = [rf"[\s,;]*(?:{cp}\s*)?(?:(?:a|au)\s+)?{nom}(?:\s*{cp})?\s*$" if cp else rf"[\s,;]*(?:(?:a|au)\s+)?{nom}\s*$"]
    if cp:
        motifs.append(rf"[\s,;]*{cp}\s*$")
    for motif in motifs:
        m = re.search(motif, _sans_accent(reste))
        if m:
            reste = reste[: m.start()]  # la forme sans accent garde la même longueur que le texte (NFKD sur des lettres latines simples)
    return reste.strip(" ,;")


def adresse_verifiee(texte: str, commune: dict[str, Any], voie: str | None = None) -> Adresse:
    """L'``Adresse`` posée sur la commande quand la source a retenu la commune (``faits.commune`` : nom, code postal, INSEE) : jamais le texte brut.
    ``voie`` : la voie dite à part de la commune (la case ``adresse`` de la fiche), prise telle quelle ; sinon elle est lue dans ``texte``."""
    nom = str(commune.get("nom") or "").strip()
    voie = voie.strip(" ,;") if voie is not None else voie_de_l_adresse(texte, nom, commune.get("code_postal"))
    return Adresse(voie=voie, code_postal=commune.get("code_postal"), commune=nom, insee=commune.get("insee"), texte_dit=texte)


async def retenir_la_seule_commune_livree(source: Source, r: Resultat) -> Resultat:
    """Lot 4 (A21, appel 2619) : une commune a des homonymes et UNE seule est dans une zone : c'est elle, sans question. Un doute entre deux communes
    livrées (ou aucune) reste une question."""
    livrables = [c for c in (r.faits.get("candidats") or []) if isinstance(c, dict) and c.get("dans_une_zone")] if r.statut == "AMBIGU" else []
    if len(livrables) != 1:
        return r
    c = livrables[0]
    return await source.verifier_adresse(f"{c.get('code_postal') or ''} {c.get('nom') or ''}".strip())


def exiger_une_voie(p: dict[str, Any], commune: dict[str, Any]) -> Resultat:
    """Lot 4 (M15, C6, appel 2647) : une adresse ne se retient pas sur la commune seule (« à Gouvieux ») : la commune est gardée, la zone n'est pas
    posée, et la voie est demandée (``manque`` : ``voie``)."""
    p["commune_dite"] = commune.get("nom")
    return _avec(_r("INCOMPLETE", {"commune": commune, "voie": None}, "", "voie"), p)


def mode_implique_par_l_adresse(source: Source) -> str | None:
    """Lot 4 (M14, SA-52, appel 2602) : une adresse vérifiée sans mode posé dit le mode, quand la source n'a qu'UN mode à adresse (posé comme
    ``choisir_mode`` le pose : ouverture vérifiée, ce qui était gardé est pris ; un mode fermé ne pose rien). Plusieurs modes à adresse : ``None``,
    la fiche porte le mode."""
    avec_adresse = [m for m in source.modes if source.exige_une_zone(m)]
    return avec_adresse[0] if len(avec_adresse) == 1 else None


def proposer_un_autre_mode_hors_zone(source: Source, r: Resultat) -> Resultat:
    """Lot 4 (C12, appels 2644, 2645) : hors zone, le retour porte en choix les modes ouverts qui n'exigent pas d'adresse."""
    autres = [m for m in source.modes if not source.exige_une_zone(m)]
    if r.statut != "HORS_ZONE" or not autres:
        return r
    choix = [{"mode": m, "libelle": source.libelles_des_modes.get(m, m)} for m in autres]
    return Resultat(r.statut, {**r.faits, "autres_modes": choix}, r.suggestion, r.manque)


async def verifier_adresse(source: Source, p: dict[str, Any], regles: Reglages, adresse: str | None, commune: str | None = None) -> Resultat:
    """Situe l'adresse dite dans les zones de la source. ``RETENU`` : la zone et l'adresse sont posées sur la commande (et le panier rechiffré avec les
    frais et le minimum de la zone). Un doute (``AMBIGU``, ``INTROUVABLE``) ne pose rien et rend les candidats à confirmer ; ``HORS_ZONE`` vide la zone
    et l'adresse déjà posées (jamais l'ancienne zone pour une nouvelle adresse) et propose un autre mode. ``commune`` : la commune dite à part (la case
    ``commune`` de la fiche) : elle seule situe l'adresse ; une rue « de Beauvais » n'est jamais lue comme la commune Beauvais (C6)."""
    voie_dite, commune_dite = (adresse or "").strip(), (commune or "").strip()
    texte = ", ".join(x for x in (voie_dite, commune_dite) if x)
    if not texte:
        return _avec(_r("ARGUMENT_INVALIDE", {}, source.question_de_la_zone, "adresse"), p)
    r = proposer_un_autre_mode_hors_zone(source, await retenir_la_seule_commune_livree(source, await source.verifier_adresse(commune_dite or voie_dite)))
    essai = copy.deepcopy(p)
    if r.statut == "RETENU":
        posee = adresse_verifiee(texte, r.faits.get("commune") or {}, voie_dite if commune_dite else None)
        if not posee.voie:
            essai["zone"] = essai["adresse"] = None
            _valider(p, essai)
            return exiger_une_voie(p, r.faits.get("commune") or {})
        zone = r.faits["zone"]
        essai["zone"], essai["adresse"], essai["commune_dite"], essai["commune_hors_zone"] = {"id": zone["id"], "nom": zone["nom"]}, posee.vers_json(), None, None
    elif r.statut == "HORS_ZONE":
        # la commune est dite et refusée : l'ancienne zone ne reste jamais en place, et ce qui était gardé est pris (B12, conversation 2)
        essai["zone"] = essai["adresse"] = None
        essai["commune_hors_zone"] = (r.faits.get("commune") or {}).get("nom") or commune_dite or voie_dite
    elif r.statut in ("AMBIGU", "INTROUVABLE") and (essai.get("zone") or essai.get("adresse")):
        essai["zone"] = essai["adresse"] = None  # une adresse en doute ne laisse jamais l'ancienne zone en place
    else:
        return _avec(r, p)
    P.toucher(essai)
    faits = dict(r.faits)
    if r.statut == "RETENU":
        chiffre = await _chiffrer(source, essai, regles)
        if chiffre.statut != "OK":
            faits["a_revoir"] = {"statut": chiffre.statut, **chiffre.faits}  # le minimum de cette zone n'est pas atteint : dit, rien n'est retiré
            _valider(p, essai)
            return _avec(Resultat(r.statut, faits, chiffre.suggestion, r.manque), p)
    _valider(p, essai)
    implique = mode_implique_par_l_adresse(source) if r.statut == "RETENU" and not p.get("mode") else None
    if implique is not None:
        pose = await choisir_mode(source, p, regles, implique)
        if pose.statut in ("OK", "FERME_PLANIFIABLE") or p.get("mode"):
            return _avec(Resultat(pose.statut if pose.statut != "OK" else r.statut, {**faits, **pose.faits}, " ".join(t for t in (r.suggestion, pose.suggestion) if t), pose.manque), p)
    if r.statut == "HORS_ZONE":
        repris = await _reprendre_les_dits(source, p, regles)
        if repris is not None and repris.faits.get("ajoutes"):
            faits["ajoutes"] = repris.faits["ajoutes"]
    if r.statut == "RETENU":
        repris = await _reprendre_les_dits(source, p, regles)
        if repris is not None and repris.statut != "OK":
            # SA-33 : ce qui était dit avant la zone est pris ; sa question passe avant tout.
            return _avec(Resultat(repris.statut, {**faits, **repris.faits}, repris.suggestion, repris.manque), p)
        if repris is not None:
            faits["ajoutes"] = repris.faits.get("ajoutes") or []
        elif p.get("mode") and _rien_n_est_pris(p) and not r.manque:
            # M116 (appel 2598) : l'adresse est posée et rien n'est encore pris : le résultat le dit et demande les plats (un manque à la fois),
            # jamais un article cité comme pris sur un panier vide.
            faits["panier_vide"] = True
            return _avec(Resultat(r.statut, faits, " ".join(t for t in (r.suggestion, _minimum_de_l_adresse(faits, p)) if t), "articles"), p)
    if r.statut == "RETENU":
        return _avec(Resultat(r.statut, faits, " ".join(t for t in (r.suggestion, _minimum_de_l_adresse(faits, p)) if t), r.manque), p)
    return _avec(Resultat(r.statut, faits, r.suggestion, r.manque), p)


def _minimum_de_l_adresse(faits: dict[str, Any], p: dict[str, Any]) -> str:
    """Agent fiable (Evan, 17/11) : le minimum de la zone est dit dès que l'adresse est retenue et que rien n'est encore pris, pour que la
    personne le sache tout de suite. Un panier déjà commencé sous le minimum le dit par le chiffrage (``a_revoir``) ; un panier vide, ici."""
    minimum = ((faits.get("zone") or {}).get("minimum")) or 0
    if minimum <= 0 or not _rien_n_est_pris(p):
        return ""
    return f"Le minimum de commande pour cette adresse est de {montant_en_lettres(minimum)}."


async def resoudre_une_date(source: Source, p: dict[str, Any], regles: Reglages, texte: str | None, heure: str | None = None) -> Resultat:
    """La date (et l'heure) dites, résolues par le code vers l'avenir, au jour et au fuseau du lieu. Sûres : ``RETENU`` avec ``faits.heure_voulue`` (ISO,
    à donner à ``finaliser``). Un doute est rendu en candidats à confirmer ; rien n'est jamais choisi en silence. Ne change pas la commande."""
    # M85 : le moment dit avec le jour (« demain soir ») est gardé dans le panier ; « huit heures et demie » dit ensuite se lit « du soir ».
    dates_futures.retenir_le_moment(p, texte)
    heure_lue = dates_futures.heure_avec_le_moment(p, (heure or "").strip() or None)
    return _avec(await source.resoudre_une_date((texte or "").strip(), heure_lue), p)


# --------------------------------------------------------------------------- #
# ajouter
# --------------------------------------------------------------------------- #


def _fusionner(p: dict[str, Any], ligne: dict[str, Any]) -> bool:
    """Une ligne identique à une ligne complète du panier s'y ajoute (deux « joints » ne font pas deux lignes)."""
    if ligne.get("attente"):
        return False
    for autre in P.lignes_pretes(p):
        if (autre["code"], autre["choix"], sorted(autre["retires"]), autre.get("note"), autre.get("poids_g")) == (ligne["code"], ligne["choix"], sorted(ligne["retires"]), ligne.get("note"), ligne.get("poids_g")):
            autre["quantite"] += ligne["quantite"]
            return True
    return False


def _declinaison_dite(article: dict, trouve: dict) -> dict | None:
    voulue = ((trouve.get("options") or {}).get("variante") or "").casefold()
    if voulue:
        return next((d for d in article["declinaisons"] if d["nom"].casefold() == voulue), None)
    if len(article["declinaisons"]) == 1:
        return article["declinaisons"][0]
    return None


async def _un_seul_candidat(source: Source, trouve: Resultat, texte: str) -> tuple[Resultat, str | None]:
    """Un seul article possible et des mots en plus (« tiramisu Classic ») : ce qui reste est le choix dit avec l'article, pas un doute sur
    l'article. Rend l'article retenu et ce qui reste dit ; sinon la recherche telle quelle et ``None``."""
    if trouve.statut != "AMBIGU" or len(trouve.faits.get("candidats", [])) != 1:
        return trouve, None
    nom_unique = trouve.faits["candidats"][0]["libelle"]
    connus = set(nom_unique.casefold().split())
    reste = [m for m in texte.split() if m.casefold() not in connus]
    if reste and len(reste) <= 2 and len(reste) < len(texte.split()) and not {m.casefold() for m in reste} & {"ou", "et", "avec", "sans", "plus", "puis"}:
        sur = await source.chercher(nom_unique)
        if sur.statut == "RETENU":
            return sur, " ".join(reste)
    return trouve, None


def _option_dite(article: dict, texte: str) -> dict | None:
    """L'option de l'article que ``texte`` nomme sans doute (« pistache » dans le groupe des parfums) ; ``None`` : aucune option certaine."""
    index = _options_disponibles(article, {"choix": []})
    if not index:
        return None
    trouve = _chercher_dans([Element(cle, o["nom"], tuple(o.get("synonymes") or ()), g["nom"]) for cle, (_, g, o) in index.items()], texte)
    return index[trouve["retenu"]][2] if trouve["statut"] == "RETENU" else None


def _rang(r: Resultat) -> int:
    return {"RETENU": 2, "AMBIGU": 1}.get(r.statut, 0)


async def _chercher_l_article(source: Source, texte: str, regles: Reglages) -> Resultat:
    """M117 (appel 2598) : l'article d'un nom dit. Le texte entier d'abord ; s'il n'est pas certain et qu'il porte des mots de taille usuels
    (« reines grandes taille »), le texte sans eux est essayé, et gardé s'il dit mieux (zéro faux sûr : c'est toujours la recherche qui tranche)."""
    trouve = await source.chercher(texte)
    if trouve.statut == "RETENU":
        return trouve
    nu = tailles.sans_les_mots_de_taille(texte, regles.mots_de_taille)
    if nu and nu != texte.strip():
        autre = await source.chercher(nu)
        if _rang(autre) >= _rang(trouve):
            return autre  # les mots de taille ne disent rien du nom : à égalité, la recherche sans eux est la plus juste
    return trouve


def _taille_dans(article: dict, texte: str | None, regles: Reglages) -> dict | None:
    """M118, M120 : la déclinaison que ``texte`` dit : un nom de déclinaison dit tel quel, sinon un mot de taille de la table (``tailles.py``).
    Les mots du nom de l'article ne sont jamais lus comme une taille. ``None`` : rien de sûr (jamais un rapprochement deviné)."""
    declinaisons = article["declinaisons"]
    if len(declinaisons) < 2 or not (texte or "").strip():
        return None
    # lot 19 (D21) : la même norme que la recherche, pour qu'« 1,5 litre » (la taille telle que l'agent la dit) soit « 1,5 l » de la carte
    dit = f" {norme_de_recherche(texte)} "
    du_nom = frozenset(norme_de_recherche(article["nom"]).split())
    par_nom = []
    for d in declinaisons:
        nom = norme_de_recherche(d["nom"])
        if nom and f" {nom} " in dit and not set(nom.split()) <= du_nom:
            par_nom.append(d)
    if par_nom:
        return par_nom[0] if len(par_nom) == 1 else None
    return tailles.declinaison_par_mot(declinaisons, texte, regles.mots_de_taille, hors=du_nom)


def _declinaison_choisie(article: dict, choix: str, regles: Reglages) -> dict | None:
    """La variante dite (la case ``variante``, ou la réponse à « quelle taille ? ») : le nom d'une déclinaison (cherché comme toujours), sinon un mot
    de taille usuel (M118). ``None`` : rien de sûr, la taille reste une question."""
    cherchee = _chercher_dans([Element(d["nom"], d["nom"]) for d in article["declinaisons"]], choix)
    if cherchee["statut"] == "RETENU":
        return next((d for d in article["declinaisons"] if d["nom"] == cherchee["retenu"]), None)
    return _taille_dans(article, choix, regles)


def _question_de_rangement(dit: str, rangements: list[dict]) -> Resultat:
    """SA-55 (appel 2606) : un rangement dit (un mot de rangement seul) n'est pas un article introuvable : on demande lequel. Plusieurs rangements : leurs
    noms ; un seul : ses premiers éléments (jamais toute la liste). Rien n'est posé ; ce n'est pas un échec (la garde ne le compte pas)."""
    if len(rangements) > 1:
        noms, quoi = [r["nom"] for r in rangements], "rangements"
    else:
        noms, quoi = list(rangements[0]["exemples"]), "exemples"
    phrase = f"Nous avons {liste_dite_et(noms)}" + (", entre autres" if quoi == "exemples" else "") + " : qu'est-ce que je vous mets ?"
    return _r("INCOMPLETE", {"dit": dit, quoi: noms}, phrase, "articles")


async def _departager_par_la_taille(source: Source, p: dict[str, Any], trouve: Resultat, textes: list[str | None], regles: Reglages) -> Resultat | None:
    """M120 (appel 2598) : deux articles du même nom et une taille dite (« quatre fromages normale ») : seul celui qui a cette taille reste.
    Plus d'un, ou aucun : ``None``, le doute reste une question."""
    candidats = trouve.faits.get("candidats") or []
    if trouve.statut != "AMBIGU" or len(candidats) < 2 or not any(t for t in textes):
        return None
    gardes = []
    for c in candidats:
        article = await _article_de_la_carte(source, p, c["id"], p["mode"])
        if article is not None and any(_taille_dans(article, t, regles) for t in textes if t):
            gardes.append(c)
    if len(gardes) != 1:
        return None
    return Resultat("RETENU", {**trouve.faits, "retenu": gardes[0]["id"], "candidats": gardes}, "")


async def _un_article(
    source: Source, p: dict[str, Any], regles: Reglages, quantite: int, texte: str, *, variante: str | None = None, choix: str | None = None,
    sans: str | None = None, note: str | None = None, moities: str | None = None, personnes: Any = None, poids: Any = None,
) -> Resultat:
    """Un article de la fiche, structuré (son nom, sa quantité, sa variante, ses choix, ses retraits, sa note, ses moitiés) : le cherche, compose sa
    ligne, la complète ou en garde la question, la chiffre. Rien n'est posé sur un refus ; la variante n'est jamais lue dans les choix (M24)."""
    if not variante:
        # La taille collée au nom (« reine normale », B12 décision 2) : le produit plus sa variante, jamais une variante déjà dans la fiche remplacée
        collee = await taille.lire_la_taille_collee_au_nom(source, texte, p.get("mode") or source.modes[0])
        if collee is not None:
            texte, variante = collee
    trouve = await _chercher_l_article(source, texte, regles)
    trouve, dit_en_plus = await _un_seul_candidat(source, trouve, texte)
    if personnes is not None and trouve.statut == "AMBIGU" and len(trouve.faits.get("candidats") or []) == 1:
        # FOR10 (conversation FOR10-A du lot 11) : « seau pour quatre personnes » écrit dans ``article`` AVEC ``personnes`` : le seul candidat, vendu par
        # personnes, est retenu ; le reste des mots est le nombre, déjà dans sa sous-case
        seul = trouve.faits["candidats"][0]["id"]
        if for10.vendu_par_personnes(await _article_de_la_carte(source, p, seul, p["mode"])):
            trouve, dit_en_plus = Resultat("RETENU", {**trouve.faits, "retenu": seul}, ""), None
    departage = await _departager_par_la_taille(source, p, trouve, [texte, variante], regles)
    if departage is not None:
        trouve = departage
    if dit_en_plus and not moities:
        choix = f"{choix}, {dit_en_plus}" if choix else dit_en_plus
    if trouve.statut != "RETENU" and choix and (trouve.statut == "AMBIGU" or trouve.faits.get("rangements")):
        # FOR1 : « le menu » quand la carte en a plusieurs (des candidats, ou un rangement dit seul) : la seule formule dont les étapes acceptent tous les mots de
        # la composition ; sinon le doute reste (la question des candidats ou du rangement)
        ids = [c["id"] for c in trouve.faits.get("candidats", []) if trouve.statut == "AMBIGU"]
        for r in trouve.faits.get("rangements") or []:
            for libelle in r.get("exemples") or []:
                exact = await source.chercher(libelle)
                if exact.statut == "RETENU" and exact.faits["retenu"] not in ids:
                    ids.append(exact.faits["retenu"])
        candidats = [(i, await _article_de_la_carte(source, p, i, p["mode"])) for i in ids]
        retenu = for1.brique_for1_departager_par_la_composition(candidats, [m for _, m, _ in lecture.morceaux_d_options(choix)])
        if retenu is not None:
            trouve = Resultat("RETENU", {**{k: v for k, v in trouve.faits.items() if k != "rangements"}, "retenu": retenu}, "")
    elif trouve.statut == "AMBIGU" and not choix:
        # FOR1 : la formule et des choix certains de ses étapes parmi les candidats (toute la phrase écrite dans ``article``) : la formule, les autres y sont rangés
        libelles = {c["id"]: c["libelle"] for c in trouve.faits.get("candidats", [])}
        candidats = [(i, await _article_de_la_carte(source, p, i, p["mode"])) for i in libelles]
        formule_et_choix = for1.brique_for1_formule_des_candidats(candidats, libelles)
        if formule_et_choix is not None:
            choix = ", ".join(formule_et_choix[1])
            trouve = Resultat("RETENU", {**trouve.faits, "retenu": formule_et_choix[0]}, "")
    if trouve.statut == "AMBIGU":
        # Lot 20 (appels 456 à 458, a307) : « Kebab » quand la carte a Kebab, Assiette kebab et Barquette de kebab : le candidat dont le nom est EXACTEMENT
        # celui qui est dit est retenu (égalité de forme, jamais une devinette) ; sans cela la réponse « Kebab » reposait la même question sans fin.
        from api.services.actions_communes.forme import norm

        exacts = [c["id"] for c in trouve.faits.get("candidats", []) if norm(str(c.get("libelle") or "")) == norm(str(texte or ""))]
        if len(exacts) == 1:
            trouve = Resultat("RETENU", {**trouve.faits, "retenu": exacts[0]}, "")
    if trouve.statut == "AMBIGU":
        noms = [c["libelle"] for c in trouve.faits.get("candidats", [])]
        return _r("AMBIGU", {"candidats": noms, "dit": texte}, trouve.suggestion or "Vous voulez dire : " + liste_dite(noms) + " ?")
    if trouve.statut != "RETENU" and trouve.faits.get("rangements"):
        return _question_de_rangement(texte, trouve.faits["rangements"])
    if trouve.statut != "RETENU":
        proches = [c["libelle"] for c in trouve.faits.get("candidats", [])][:3]
        return _r(
            "INTROUVABLE", {"dit": texte, "plus_proches": proches},
            f"Je ne trouve pas « {texte} »." + (f" Le plus proche : {liste_dite(proches)}." if proches else ""),
        )
    article = await _article_de_la_carte(source, p, trouve.faits["retenu"], p["mode"])
    if article is None:
        return _r("INTROUVABLE", {"dit": texte}, f"« {texte} » n'est pas disponible en ce moment.")
    # Lot 12 (PRX1, PRX3, PRX8) : hors de sa plage à ce moment, d'un autre mode, au-delà du maximum par commande : refusé dès l'ajout, avec les faits (jamais une phrase)
    deja_pris = sum(int(l["quantite"]) for l in p["lignes"] if l.get("ref") == article["id"])
    refus_de_la_carte = conditions_de_vente.refus_de_la_ligne(article, None, p.get("mode"), quantite, deja_pris, None, None)
    if refus_de_la_carte is not None:
        return _r("INTERDIT", refus_de_la_carte, "")
    # Lot 13 (QTE2) : un lot de vente se dit en pièces ; la ligne compte des lots. (QTE1) : un article au poids se pose avec son poids, que le code lit et chiffre.
    lot = qte2.brique_qte2_multiple_du_lot(article, quantite)
    if lot.get("raison"):
        return _r("INTERDIT", lot, "")
    quantite = lot.get("lots", quantite)
    if quantite > lecture.QUANTITE_MAX:  # C4 : le plafond s'applique aux lignes comptées (des lots), jamais aux pièces dites
        return _r("ARGUMENT_INVALIDE", {"quantite": lot.get("pieces", quantite)}, f"{lot.get('pieces', quantite)}, c'est beaucoup : je vous mets combien exactement ?", "quantite")
    au_poids = qte1.brique_qte1_chiffrer_au_poids(article, poids)
    if au_poids.get("raison"):
        return _r("INTERDIT", au_poids, "")
    if personnes is not None and not variante:
        variante = for10.brique_for10_pour_combien(article, personnes)  # FOR10 : la sous-case ``personnes`` dit la déclinaison de la formule
        if variante is None and any(d.get("type") == "personnes" for d in article["declinaisons"]):
            question = dec1.brique_dec1_demander_la_declinaison(article["declinaisons"])
            ligne_refus = {"article": article["nom"], "question": question, "dit": personnes, "raison": for10.RAISON_HORS_LISTE}
            return _r("CHOIX_OBLIGATOIRE", ligne_refus, _phrase_de_la_question(question, article["nom"]), question["nom"])
    if variante:
        # la variante dite et elle seule : une variante que l'article n'a pas reste une question, jamais la seule déclinaison posée sans le dire (C8, 2664)
        declinaison = _declinaison_choisie(article, variante, regles)
    else:
        declinaison = _declinaison_dite(article, trouve.faits) or _taille_dans(article, texte, regles)
    ligne: dict[str, Any] = {
        "n": 0, "ref": article["id"], "nom": article["nom"], "code": None, "quantite": quantite, "choix": [], "retires": [], "note": None,
        "attente": None, "declinaison_dite": ((trouve.faits.get("options") or {}).get("variante")),
        "genre": article.get("genre"), "commun": bool(article.get("commun")),  # M26 : de quoi accorder ce qu'on dit de la ligne
        **({"formule_id": article["id"]} if article.get("formule") else {}),  # lot 11 : la vue de l'état sait qu'une ligne est une formule (contrat)
        **({"poids_g": au_poids["grammes"]} if au_poids else {}),  # lot 13 (QTE1) : le poids d'UNE portion, en grammes
        **({"lot_de_vente": int(article["lot_de_vente"])} if article.get("lot_de_vente") else {}),  # C4 : la ligne compte des lots, elle se dit en pièces
    }
    if declinaison is not None:
        if not declinaison["vendable"] or declinaison["rupture"]:
            autres = [d["nom"] for d in article["declinaisons"] if d["vendable"] and not d["rupture"] and d is not declinaison]
            return _r(
                "RUPTURE", {"nom": f"{article['nom']} {declinaison['nom']}", "autres_tailles": autres},
                f"{article['nom']} {declinaison['nom']} n'est plus disponible." + (f" Il reste : {liste_dite(autres)}." if autres else ""),
            )
        ligne["code"] = declinaison["code"]
        if len(article["declinaisons"]) > 1:
            ligne["nom"] = f"{article['nom']} {declinaison['nom']}"
            ligne["taille"] = declinaison["nom"]  # M18 : la sous-ligne du panier en direct
    if ligne["code"]:
        _appliquer_les_defauts(article, ligne)
    for texte_choix, roles in ((moities, ("moities",)), (choix, None)):
        if texte_choix and ligne["code"]:
            erreur = _appliquer_les_choix(article, ligne, texte_choix, roles=roles, notes_libres=regles.notes_libres)
            if erreur:
                return erreur
        elif texte_choix:
            ligne["choix_a_poser"] = (ligne.get("choix_a_poser") or []) + [texte_choix]
    if sans and moities and not ligne["code"] and ligne.get("choix_a_poser"):
        # SA-22 : les moitiés attendent la taille : le retrait attend avec elles (il se note sur la moitié dite).
        ligne["retraits_a_poser"] = (ligne.get("retraits_a_poser") or []) + [sans]
    elif sans:
        erreur = (retirer_sur_le_plat if article.get("formule") else _appliquer_les_retraits)(article, ligne, sans)
        if erreur:
            return erreur
    erreur = _noter(ligne, note or "", regles)
    if erreur:
        return erreur
    if ligne["code"]:
        erreur = a_la_taille_de_la_formule(article, ligne)
        if erreur:
            return erreur
    await _noter_une_regle_inconnue_de_la_carte(source, p, regles, article, ligne)  # PRX2 : « hors jours fériés » est une note de ligne signalée, jamais un refus
    question = _question(article, ligne)
    if question is not None:
        ligne["attente"] = question
        ligne["article_nom"] = article["nom"]
        p["lignes"].append(ligne)
        P.toucher(p)
        return _avec(
            _r("CHOIX_OBLIGATOIRE", {"article": ligne["nom"], "question": question}, _phrase_de_la_question(question, article["nom"]), question["nom"]), p
        )
    essai = copy.deepcopy(p)
    if not _fusionner(essai, ligne):
        essai["lignes"].append(ligne)
    P.toucher(essai)
    chiffre = await _chiffrer(source, essai, regles)
    if _bloque_l_ajout(chiffre):
        return _avec(chiffre, p)
    _valider(p, essai)
    return _r("OK", {"ajoute": ligne["nom"], "quantite": quantite, **({"choix_sans_objet": ligne["choix_sans_objet"]} if ligne.get("choix_sans_objet") else {}),
                     **(prx6.brique_prx6_regle_d_age_dite(article) or {}),  # PRX6 : un article alcoolisé rend le fait ``alcool``
                     **FO.regle_a_dire_a_l_ajout(article),  # FOR7, FOR9, FOR13 : la condition, le justificatif, ce qui est servi avec (dits par le code)
                     **({"composition": FO.composition_de_la_ligne(article, ligne)} if article.get("formule") else {}),  # lot 11 : le modèle repasse avec elle
                     **_faits_du_poids_et_du_lot(article, au_poids, lot)})


def _faits_du_poids_et_du_lot(article: dict[str, Any], au_poids: dict[str, Any], lot: dict[str, Any]) -> dict[str, Any]:
    """Lot 13 : ce que l'ajout rend d'un article au poids (QTE1 : ``grammes`` et ``arrondi_a``, et le prix dit par le code, jamais montré au modèle) ou d'un lot de vente (QTE2 : ``lots``, ``pieces``)."""
    faits: dict[str, Any] = {}
    if au_poids:
        faits["grammes"] = au_poids["grammes"]
        if "arrondi_a" in au_poids:
            faits["arrondi_a"] = au_poids["arrondi_a"]
        debut = "Arrondi à " if "arrondi_a" in au_poids else ""
        faits["prix_a_dire"] = f"{debut}{chiffres_en_lettres(str(au_poids['grammes']))} grammes de {article['nom'].lower()} : {montant_en_lettres(au_poids['prix'])}."
    if lot:
        faits.update(lots=lot["lots"], pieces=lot["pieces"])
    return faits


async def _noter_une_regle_inconnue_de_la_carte(source: Source, p: dict[str, Any], regles: Reglages, article: dict[str, Any], ligne: dict[str, Any]) -> None:
    """Lot 12 (PRX2) : l'article se vend « hors jours fériés » et le jour voulu est férié : la ligne reste vendable, la règle part en note et le portail est signalé."""
    if not (article.get("disponibilite") or {}).get("hors_feries"):
        return
    quand = _servi_le(p) or await source.maintenant_du_lieu()
    texte = prx2.brique_prx2_en_regle_inconnue(article, quand.date())
    if texte is None:
        return
    inconnue.regle_inconnue_en_note(ligne, texte, regles.notes_libres)
    signaler = getattr(source, "signaler_une_regle_inconnue", None)
    if signaler is not None:
        await signaler(article["id"], texte)


def _article_de_la_fiche(article: dict[str, Any]) -> dict[str, Any]:
    """Un objet de la case ``ajouter`` (nom, quantité, variante, retraits, suppléments, composition, moitiés, précision) au format du moteur ; la
    variante « autre » n'est jamais une variante (E27 : la valeur hors liste est redemandée)."""
    quantite = article.get("quantite")
    if isinstance(quantite, float) and quantite.is_integer():
        quantite = int(quantite)  # C8 : « 2.0 » est deux
    variante = str(article.get("variante") or "").strip()
    return {
        "quantite": quantite if isinstance(quantite, int) and not isinstance(quantite, bool) else 1,  # C8 : 0 ou -2 sont gardés tels, ``quantite_inferieure_a_un`` les refuse (jamais un « 1 » silencieux)
        "texte": str(article.get("article") or "").strip(),
        "variante": None if variante in ("", "autre") else variante,
        "choix": ", ".join(str(c) for c in [*(article.get("supplements") or []), *(article.get("composition") or [])]) or None,
        "sans": ", ".join(str(s) for s in article.get("sans") or []) or None,
        "moities": ", ".join(str(m) for m in article.get("moities") or []) or None,
        "note": str(article.get("precision_article") or "").strip() or None,
        "personnes": article.get("personnes"),  # FOR10 (lot 11) : la sous-case ``ajouter[].personnes``
        "poids": article.get("poids"),  # QTE1 (lot 13) : la sous-case ``ajouter[].poids``
    }


CLE_OPTION_DITE = "option_dite"  # T1 (lot 19 bis) : l'hésitation porte sur une OPTION (les mots dits), jamais sur l'article ; gardée avec la question, jamais montrée au modèle
RAISON_QUANTITE_INFERIEURE_A_UN = "quantite_inferieure_a_un"  # C8 (lot 19 bis) : une quantité nulle ou négative n'est jamais un article de plus


async def ajouter_un_article(source: Source, p: dict[str, Any], regles: Reglages, article: dict[str, Any]) -> Resultat:
    """Un article de la case ``ajouter`` (la seule case qui additionne, E3). Sans mode ou sans zone, il est mis en attente du préalable
    (``mettre_en_attente_du_prealable``) et pris dès qu'ils sont posés ; sinon il est pris tout de suite."""
    dit = _article_de_la_fiche(article)
    if dit["quantite"] < 1:
        return _r("ARGUMENT_INVALIDE", {"raison": RAISON_QUANTITE_INFERIEURE_A_UN, "quantite": dit["quantite"]}, "Combien exactement ?", "quantite")
    if await _prealables(source, p, regles, pour_prendre=True) is not None:
        mettre_en_attente_du_prealable(p, dit)
        return _r("OK", {"garde": " ".join(x for x in (dit["texte"], dit["variante"]) if x), "quantite": dit["quantite"]}, "")
    await _reprendre_les_dits(source, p, regles)  # ce qui était gardé passe avant, dans l'ordre où il a été dit (jamais oublié)
    return await _un_article(source, p, regles, dit.pop("quantite"), dit.pop("texte"), **dit)


# --------------------------------------------------------------------------- #
# SA-52 (appels 2602, 2604) : ce que l'article contient déjà n'est pas un choix à refuser
# --------------------------------------------------------------------------- #


def _dans_la_composition(article: dict, morceau: str) -> bool:
    """« A et B » pour un article décrit « avec A et B » : ce que l'article CONTIENT déjà (son nom, sa description, ses
    ingrédients) n'est pas un choix à refuser. Tous les mots dits doivent y être ; un mot court ou de liaison ne compte pas."""
    mots = [m for m in norme_de_recherche(morceau).split() if len(m) >= 3 and m not in _MOTS_DE_LIAISON]
    if not mots:
        return False
    contenu = " ".join([article.get("nom") or "", article.get("description") or "", *(article.get("ingredients") or [])])
    return set(mots) <= set(norme_de_recherche(contenu).split())


_MOTS_DE_LIAISON = frozenset({"de", "du", "des", "la", "le", "les", "l", "un", "une", "sans", "avec", "en", "et"})


async def _repondre_aux_attentes(source: Source, p: dict[str, Any], regles: Reglages, choix: str) -> list[str]:
    """M120 : ``choix`` répond à la question ouverte : posé sur chaque ligne de cet article qui attend la même question. Rend les lignes
    complétées ; vide quand ``choix`` ne répond pas (rien n'est changé)."""
    attentes = P.a_completer(p)
    premiere = attentes[0]
    faites: list[str] = []
    for ligne in [l for l in attentes if l["ref"] == premiere["ref"] and l["attente"] == premiere["attente"]]:
        n, avant = ligne["n"], ligne["attente"]
        r = await _travailler_une_ligne(source, p, regles, ligne, choix=choix)
        apres = next((l for l in p["lignes"] if l["n"] == n), None)
        if apres is None or apres.get("attente") == avant or r.statut not in ("OK", "CHOIX_OBLIGATOIRE"):
            break
        faites.append(apres["nom"])
    return faites


def mettre_en_attente_du_prealable(p: dict[str, Any], dit: dict[str, Any]) -> None:
    """Lot 4 (M28, SA-33, appels 2559, 2602) : un article dit avant le mode ou la zone est GARDÉ tel que dit (structuré) dans le panier de l'appel,
    puis pris dès qu'ils sont posés ; une fiche rejouée ne le double pas (la clé d'idempotence de la fiche, lot 3)."""
    gardes = p.setdefault("dits_en_attente", [])
    dit = {cle: valeur for cle, valeur in dit.items() if valeur is not None}
    gardes.append(dit)


async def _reprendre_les_dits(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat | None:
    """SA-33 : les préalables sont posés, ce qui était gardé est pris, dans l'ordre où il a été dit. Rend le résultat de ces ajouts (la première
    question qu'ils posent, sinon l'état du panier, avec ``ajoutes``), ou ``None`` s'il n'y avait rien de gardé ou qu'un préalable manque encore."""
    gardes = [d for d in p.get("dits_en_attente") or [] if isinstance(d, dict) and d.get("texte")]
    if not gardes or await _prealables(source, p, regles, pour_prendre=True) is not None:
        return None
    p["dits_en_attente"] = []
    ajoutes: list[str] = []
    question: Resultat | None = None
    for dit in gardes:
        dit = dict(dit)
        r = await _un_article(source, p, regles, int(dit.pop("quantite", 1) or 1), dit.pop("texte"), **dit)
        if r.statut == "OK" and r.faits.get("ajoute") and r.faits["ajoute"] not in ajoutes:
            ajoutes.append(r.faits["ajoute"])
        if r.statut != "OK" and question is None:
            question = r
    if question is not None:
        return Resultat(question.statut, {**question.faits, "ajoutes": ajoutes}, question.suggestion, question.manque)
    return await _etat_apres_ajout(source, p, regles, {"ajoutes": ajoutes})


def _bloque_l_ajout(chiffre: Resultat) -> bool:
    """[.mark] Lot 17 : un panier sous le minimum de sa zone n'empêche pas d'ajouter (le minimum se juge à la fin, par ``finaliser`` et
    l'enregistrement) ; tout autre refus du chiffrage (rupture, article absent du catalogue, hors zone…) bloque le geste."""
    return chiffre.statut not in ("OK", "MINIMUM_NON_ATTEINT")


def _minimum_non_atteint(chiffre: Resultat) -> dict[str, int] | None:
    """Ce qui manque pour le minimum de la zone, quand le chiffrage le dit : ``{minimum, manque}`` en centimes."""
    if chiffre.statut != "MINIMUM_NON_ATTEINT":
        return None
    minimum, sous_total = chiffre.faits.get("minimum"), chiffre.faits.get("sous_total")
    if not isinstance(minimum, int) or not isinstance(sous_total, int):
        return None
    return {"minimum": minimum, "manque": max(0, minimum - sous_total)}


async def _etat_apres_ajout(source: Source, p: dict[str, Any], regles: Reglages, faits: dict[str, Any]) -> Resultat:
    en_attente = P.a_completer(p)
    if en_attente:
        q = en_attente[0]["attente"]
        return _r("CHOIX_OBLIGATOIRE", {**faits, "article": en_attente[0]["nom"], "question": q}, _phrase_de_la_question(q, en_attente[0]["article_nom"]), q["nom"])
    chiffre = await _chiffrer(source, p, regles)
    minimum = _minimum_non_atteint(chiffre)
    if minimum is not None:
        return _r("OK", {**faits, "minimum_non_atteint": minimum}, "")
    return _r("OK", {**faits, "total": chiffre.faits.get("total"), "sous_total": chiffre.faits.get("sous_total"), "frais": chiffre.faits.get("frais")}, "")


async def _repondre(source: Source, p: dict[str, Any], regles: Reglages, *, choix: str | None, sans: str | None, note: str | None, moities: str | None) -> Resultat:
    """Pas d'article dit : la réponse à la question ouverte, ou un choix, un retrait, une note sur la dernière ligne."""
    if not (choix or sans or note or moities):
        return _avec(_r("INCOMPLETE", {}, "", "articles"), p)
    cible = (P.a_completer(p) or p["lignes"][-1:] or [None])[0]
    if cible is None:
        return _avec(_r("INCOMPLETE", {}, "", "articles"), p)
    attentes = P.a_completer(p)
    if choix and not (sans or note or moities) and sum(1 for l in attentes if l["ref"] == cible["ref"] and l["attente"] == cible.get("attente")) > 1:
        # SA-52 : « deux X dont un sans Y » fait deux lignes qui attendent la même question : la réponse vaut pour les deux.
        if await _repondre_aux_attentes(source, p, regles, choix):
            return _avec(await _etat_apres_ajout(source, p, regles, {}), p)
    return await _travailler_une_ligne(source, p, regles, cible, choix=choix, sans=sans, note=note, moities=moities)


def changer_la_taille(article: dict, ligne: dict, variante: str, regles: Reglages) -> Resultat | None:
    """Lot 4 (M32, C8, appel 2653) : la variante dite remplace celle de la ligne (« finalement en grande »), même quand aucune taille n'est
    attendue. ``None`` : la ligne a sa nouvelle déclinaison ; ``RIEN_A_CHANGER`` : c'est déjà la sienne ; une variante que l'article n'a pas
    est redemandée avec ses choix (jamais une taille choisie à sa place, E12) ; une variante en rupture est refusée avec celles qui restent."""
    dite = _declinaison_choisie(article, variante, regles)
    vendables = [d["nom"] for d in article["declinaisons"] if d["vendable"] and not d["rupture"]]
    if dite is None:
        question = dec1.brique_dec1_demander_la_declinaison(article["declinaisons"])
        return _r("CHOIX_OBLIGATOIRE", {"article": ligne["nom"], "question": question, "dit": variante}, _phrase_de_la_question(question, article["nom"]), question["nom"])
    if dite["code"] == ligne.get("code"):
        return _r("RIEN_A_CHANGER", {"ligne": ligne["n"], "article": ligne["nom"], "variante": dite["nom"]}, "")
    if not dite["vendable"] or dite["rupture"]:
        autres = [n for n in vendables if n != dite["nom"]]
        return _r("RUPTURE", {"nom": f"{article['nom']} {dite['nom']}", "autres_tailles": autres}, f"{article['nom']} {dite['nom']} n'est plus disponible.")
    ligne["code"] = dite["code"]
    if len(article["declinaisons"]) > 1:
        ligne["nom"] = f"{article['nom']} {dite['nom']}"
        ligne["taille"] = dite["nom"]
    return None


async def _travailler_une_ligne(
    source: Source, p: dict[str, Any], regles: Reglages, cible: dict[str, Any], *, choix: str | None = None, sans: str | None = None,
    note: str | None = None, moities: str | None = None, quantite: int | None = None, variante: str | None = None,
) -> Resultat:
    """Applique variante, choix, retraits, note, moitiés, quantité à UNE ligne, sur une copie : adopté seulement si tout tient et se chiffre."""
    essai = copy.deepcopy(p)
    ligne = next(l for l in essai["lignes"] if l["n"] == cible["n"])
    article = await _article_de_la_carte(source, essai, ligne["ref"], essai["mode"])
    if article is None:
        return _avec(_r("INTROUVABLE", {"article": ligne["nom"]}, f"{ligne['nom']} n'est plus au catalogue."), p)
    attente = ligne.get("attente")
    if variante and not (attente and attente["type"] == "declinaison"):
        refus = changer_la_taille(article, ligne, variante, regles)
        if refus is not None and refus.statut == "RIEN_A_CHANGER" and not (quantite is not None or choix or sans or note or moities):
            return _avec(refus, p)
        if refus is not None and refus.statut != "RIEN_A_CHANGER":
            return _avec(refus, p)
    taille_dite = variante if variante and attente and attente["type"] == "declinaison" else None  # la ligne attend sa taille : la variante y répond
    if attente and attente["type"] == "declinaison" and (taille_dite or choix):
        # La réponse à « quelle taille ? » : la déclinaison dite (le nom d'une taille).
        trouve = _declinaison_choisie(article, taille_dite or choix, regles)
        if trouve is None:
            return _avec(_r("CHOIX_OBLIGATOIRE", {"article": ligne["nom"], "question": attente}, _phrase_de_la_question(attente, article["nom"]), attente["nom"]), p)
        if not trouve["vendable"] or trouve["rupture"]:
            return _avec(_r("RUPTURE", {"nom": f"{article['nom']} {trouve['nom']}"}, f"{article['nom']} {trouve['nom']} n'est plus disponible."), p)
        ligne["code"] = trouve["code"]
        if len(article["declinaisons"]) > 1:
            ligne["nom"] = f"{article['nom']} {trouve['nom']}"
            ligne["taille"] = trouve["nom"]
        choix = choix if taille_dite else None
        _appliquer_les_defauts(article, ligne)
        for texte_en_attente in ligne.pop("choix_a_poser", []):
            erreur = _appliquer_les_choix(article, ligne, texte_en_attente)
            if erreur:
                return _avec(erreur, p)
        for retrait_en_attente in ligne.pop("retraits_a_poser", []):
            erreur = _appliquer_les_retraits(article, ligne, retrait_en_attente)
            if erreur:
                return _avec(erreur, p)
    for texte, roles in ((moities, ("moities",)), (choix, None)):
        if texte:
            dans = attente["groupe"] if attente and attente.get("type") in ("groupe", for2.TYPE_DE_LA_QUESTION) and roles is None else None
            erreur = _appliquer_les_choix(article, ligne, texte, roles=roles, dans=dans, notes_libres=regles.notes_libres)
            if erreur:
                return _avec(erreur, p)
    if sans:
        erreur = (retirer_sur_le_plat if article.get("formule") else _appliquer_les_retraits)(article, ligne, sans)
        if erreur:
            return _avec(erreur, p)
    erreur = _noter(ligne, note or "", regles)
    if erreur:
        return _avec(erreur, p)
    if ligne.get("code"):
        erreur = a_la_taille_de_la_formule(article, ligne)  # FOR6 : passer en grand garde les choix (D34, conflit 3)
        if erreur:
            return _avec(erreur, p)
    if quantite is not None:
        ligne["quantite"] = quantite
    ligne["attente"] = None
    question = _question(article, ligne)
    if question is not None:
        ligne["attente"], ligne["article_nom"] = question, article["nom"]
    P.toucher(essai)
    chiffre = await _chiffrer(source, essai, regles)
    if _bloque_l_ajout(chiffre):
        return _avec(chiffre, p)
    _valider(p, essai)
    return _avec(await _etat_apres_ajout(source, p, regles, {"ligne": ligne["n"], "article": ligne["nom"]}), p)


# --------------------------------------------------------------------------- #
# modifier, retirer, vider, voir
# --------------------------------------------------------------------------- #


async def _trouver_la_ligne(p: dict[str, Any], dit: str | None) -> tuple[dict | None, Resultat | None]:
    """La ligne que l'appelant désigne : son numéro (« la deuxième »), sinon son nom parmi les lignes du panier. ``(ligne, None)`` ou ``(None, refus)``."""
    if not p["lignes"]:
        return None, _r("INTROUVABLE", {}, "Il n'y a encore rien dans la commande.")
    texte = lecture.en_chiffres(str(dit or "")).strip()
    if not texte and len(p["lignes"]) == 1:
        return p["lignes"][0], None
    if texte.isdigit():
        n = int(texte)
        ligne = next((l for l in p["lignes"] if l["n"] == n), None)
        return (ligne, None) if ligne else (None, _r("INTROUVABLE", {"lignes": len(p["lignes"])}, f"Il n'y a pas de ligne {n}."))
    if not texte:
        return None, _r("INCOMPLETE", {}, "Laquelle voulez-vous changer ?", "ligne")
    # SA-52 (appel 2604) : « X deux couleurs » désigne la ligne « X 2 couleurs » (les nombres lus des deux côtés).
    voulus = {m for m in norme_de_recherche(texte).split() if m not in _PETITS_MOTS}
    correspond = [
        l for l in p["lignes"]
        if voulus and voulus <= set(norme_de_recherche(l["nom"] + " " + " ".join(c.get("nom", "") for c in l["choix"])).split())
    ]
    if len(correspond) == 1:
        return correspond[0], None
    noms = [l["nom"] for l in (correspond or p["lignes"])]
    if len(correspond) > 1:
        return None, _r("AMBIGU", {"candidats": noms, "lignes": [l["n"] for l in correspond]}, "Laquelle : " + liste_dite(noms) + " ?")
    trouve = _chercher_dans([Element(str(l["n"]), l["nom"]) for l in p["lignes"]], texte)  # une faute de transcription : le moteur, à zéro faux sûr
    if trouve["statut"] == "RETENU":
        return next(l for l in p["lignes"] if str(l["n"]) == trouve["retenu"]), None
    return None, _r("INTROUVABLE", {"lignes": noms}, f"Je ne trouve pas « {texte} » dans la commande.")


async def lots_des_quantites_hautes(source: Source, p: dict[str, Any], regles: Reglages, fiche: dict[str, Any]) -> dict[int, int]:
    """C4 : pour chaque opération de la fiche dont la quantité dépasse le plafond d'une ligne, le lot de vente de son article (``{id(opération): pièces du lot}``), pour que le plafond se juge
    sur les lignes comptées (des lots). Ne cherche rien tant qu'aucune quantité n'est haute : le cas courant ne coûte aucune recherche."""
    lots: dict[int, int] = {}
    try:
        for x in [*(fiche.get("ajouter") or []), *(fiche.get("changer_quantite") or [])]:
            if not isinstance(x, dict) or not isinstance(x.get("quantite"), int) or isinstance(x["quantite"], bool) or x["quantite"] <= lecture.QUANTITE_MAX:
                continue
            if x.get("ligne") is not None:
                cible, _ = await _trouver_la_ligne(p, str(x["ligne"]))
                lot = (cible or {}).get("lot_de_vente")
            else:
                trouve = await _chercher_l_article(source, str(x.get("article") or ""), regles)
                article = await _article_de_la_carte(source, p, trouve.faits["retenu"], p.get("mode") or source.modes[0]) if trouve.statut == "RETENU" else None
                lot = (article or {}).get("lot_de_vente")
            if lot:
                lots[id(x)] = int(lot)
    except Exception:  # noqa: BLE001  # ne lève jamais : sans lot trouvé, le plafond reste celui des quantités dites
        logger.exception("[.mark] lots_des_quantites_hautes")
    return lots


async def modifier(
    source: Source, p: dict[str, Any], regles: Reglages, *, ligne: str | None = None, quantite: int | None = None, choix: str | None = None,
    sans: str | None = None, note: str | None = None, moities: str | None = None, variante: str | None = None,
) -> Resultat:
    """Change UNE ligne : sa quantité (zéro la retire), sa variante (``changer_la_taille``), ses choix, ses retraits, sa note. Tout ou rien : un
    changement qui ne tient pas n'est pas posé."""
    cible, refus = await _trouver_la_ligne(p, ligne)
    if refus is not None:
        return _avec(refus, p)
    if quantite is not None and (not isinstance(quantite, int) or isinstance(quantite, bool) or quantite < 0):
        return _avec(_r("ARGUMENT_INVALIDE", {}, "Combien exactement ?", "quantite"), p)
    if quantite and cible.get("lot_de_vente"):  # C4 : une ligne vendue par lot se corrige en PIÈCES, comme à l'ajout (QTE2) ; la ligne compte des lots
        lot = qte2.brique_qte2_multiple_du_lot({"nom": cible["nom"], "lot_de_vente": cible["lot_de_vente"]}, quantite)
        if lot.get("raison"):
            return _avec(_r("INTERDIT", lot, ""), p)
        quantite = lot["lots"]
    if quantite is not None and quantite > lecture.QUANTITE_MAX:
        return _avec(_r("ARGUMENT_INVALIDE", {}, "Combien exactement ?", "quantite"), p)
    if quantite == 0:
        return await retirer(source, p, regles, ligne=str(cible["n"]))
    if quantite is None and not (choix or sans or note or moities or variante):
        return _avec(_r("INCOMPLETE", {}, "Qu'est-ce que je change ?", "modification"), p)
    return await _travailler_une_ligne(source, p, regles, cible, choix=choix, sans=sans, note=note, moities=moities, quantite=quantite, variante=variante)


async def retirer(source: Source, p: dict[str, Any], regles: Reglages, *, ligne: str | None = None) -> Resultat:
    cible, refus = await _trouver_la_ligne(p, ligne)
    if refus is not None:
        return _avec(refus, p)
    essai = copy.deepcopy(p)
    essai["lignes"] = [l for l in essai["lignes"] if l["n"] != cible["n"]]
    P.toucher(essai)
    chiffre = await _chiffrer(source, essai, regles)
    _valider(p, essai)
    faits = {"retire": cible["nom"], "total": chiffre.faits.get("total") if chiffre.statut == "OK" else None}
    return _avec(_r("OK", faits, ""), p)


async def vider_commande(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
    """Vide les articles. Le mode, la zone et le client sont gardés : l'appelant repart de zéro sur les articles, pas sur l'adresse."""
    essai = copy.deepcopy(p)
    essai["lignes"] = []
    essai["dits_en_attente"] = []  # SA-33 : ce qui était gardé avant les préalables part aussi
    P.toucher(essai)
    _valider(p, essai)
    return _avec(_r("OK", {"vide": True}, ""), p)


def _ligne_dite(l: dict[str, Any]) -> str:
    """« une chaise haute », « deux joints » : la quantité et le nom, accordés (M26)."""
    return nom_dit(l["nom"], P.pieces(l), genre=l.get("genre"), commun=bool(l.get("commun")))  # C4 : des pièces pour un article vendu par lot


def _phrase_des_lignes(lignes: list[dict[str, Any]]) -> str:
    morceaux = []
    for l in lignes:
        morceau = _ligne_dite(l)
        details = [c["nom"] for c in l["choix"] if c.get("nom")]
        if details:
            morceau += " avec " + liste_dite_et(details)
        if l["retires"]:
            morceau += " sans " + liste_dite_et(l["retires"])
        if l.get("note"):
            morceau += f", {l['note']}"
        if l.get("offerte_dite"):
            morceau += " offerte" if l.get("genre") == "f" else " offert"
        morceaux.append(morceau)
    return liste_dite_et(morceaux)


def contenu_dit(p: dict[str, Any], source: Source | None = None) -> str:
    """Le contenu de la commande en cours, en une phrase pour l'équipe (articles, choix, retraits, mode). Les lignes en attente de leur question y sont aussi :
    rien de ce que l'appelant a dit n'est perdu."""
    lignes = _phrase_des_lignes(p["lignes"]) if p["lignes"] else "aucun article"
    mode = p.get("mode")
    if mode:
        lignes += f" ({(source.libelles_des_modes.get(mode, mode) if source else p.get('mode_dit') or mode)})"
    if (p.get("zone") or {}).get("nom"):
        lignes += f", zone {p['zone']['nom']}"
    if p.get("note"):
        lignes += f", note : {p['note']}"
    return lignes


async def voir_la_carte(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
    """``lire`` avec ``sujet: carte`` sans article (E16, ART3) : les rubriques de la carte et le texte du jour de chaque produit du moment, tel que saisi ; un texte absent est dit
    non renseigné (jamais inventé), la phrase est alors « Je ne peux pas vous le confirmer. »."""
    carte = await source.carte_a_lire(p.get("mode") or "emporter")
    du_moment = carte.get("du_moment") or []
    textes = [d["texte_du_jour"] for d in du_moment if d["renseigne"]]
    suggestion = textes[0] if len(textes) == 1 and len(du_moment) == 1 else (NON_CONFIRMABLE if du_moment and not textes else "")
    return _avec(_r("OK", carte, suggestion), p)


async def voir_commande(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
    """Le panier tel que le code le tient : lignes numérotées, prix, frais, total. Rien d'autre n'est jamais « le total »."""
    if not p["lignes"]:
        return _avec(_r("OK", {"lignes": [], "total": 0, "vide": True}, "La commande est vide pour le moment."), p)
    chiffre = await _chiffrer(source, p, regles)
    minimum = _minimum_non_atteint(chiffre)  # M27 : sous le minimum de la zone, le panier se lit quand même ; on dit ce qui manque
    if minimum is not None:
        sans_zone = copy.deepcopy(p)
        sans_zone["zone"] = None
        chiffre = await _chiffrer(source, sans_zone, regles)
    if chiffre.statut != "OK":
        return _avec(chiffre, p)
    calculees = {l["n"]: c for l, c in zip(P.lignes_pretes(p), chiffre.faits.get("lignes", []))}
    lignes = []
    for l in p["lignes"]:
        calculee = calculees.get(l["n"])
        lignes.append(
            {
                "n": l["n"], "nom": l["nom"], "quantite": P.pieces(l), "prix_unitaire": calculee["prix_unitaire"] if calculee else None,
                "choix": [c["nom"] for c in l["choix"] if c.get("nom")], "retires": list(l["retires"]), "note": l.get("note"),
                "a_completer": l["attente"]["nom"] if l.get("attente") else None,
            }
        )
    en_attente = P.a_completer(p)
    total = None if en_attente or minimum is not None else chiffre.faits["total"]
    phrase = f"Vous avez {_phrase_des_lignes(P.lignes_pretes(p))}."
    if minimum is not None:
        phrase += (
            f" Cela fait {montant_en_lettres(chiffre.faits['sous_total'])}, il manque {montant_en_lettres(minimum['manque'])}"
            f" pour atteindre le minimum de {montant_en_lettres(minimum['minimum'])}."
        )
    elif total is not None:
        phrase += f" Cela fait {montant_en_lettres(total)}."
    remises = chiffre.faits.get("remises") or []
    if remises and total is not None:
        phrase += f" Avec {liste_dite_et([_dit(r['nom']) for r in remises])}, vous économisez {montant_en_lettres(chiffre.faits['total_remises'])}."
    offerte = bool(chiffre.faits.get("livraison_offerte")) and total is not None  # lot 14 (OFF4) : le code dit que la livraison est offerte
    if offerte:
        phrase += " La livraison est offerte."
    return _avec(
        _r(
            "OK",
            {
                "lignes": lignes, "sous_total": chiffre.faits["sous_total"], "frais": chiffre.faits["frais"], "total": total,
                "remises": [{"nom": r["nom"], "montant": r["montant"]} for r in remises], "total_remises": chiffre.faits.get("total_remises", 0),
                "offerts": chiffre.faits.get("offerts") or [], **({"livraison_offerte": True} if offerte else {}),
                **({"minimum_non_atteint": minimum} if minimum is not None else {}),
            },
            phrase,
        ),
        p, total=total,
    )


# --------------------------------------------------------------------------- #
# finaliser : relire, puis enregistrer
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Appelant:
    """Ce que le code sait de l'appelant, jamais le modèle : le numéro qui s'affiche (E.164, ``None`` s'il est masqué) et l'identifiant de l'appel."""

    telephone_affiche: str | None = None
    appel_id: str | None = None


def _numero_dit(texte: str | None) -> str | None:
    """Le numéro dit, en E.164, ou ``None``. Les chiffres écrits en lettres (« zéro six douze trente-quatre… ») sont lus : le modèle les rend parfois ainsi."""
    # M98 : dit par paires en lettres, le numéro garde ses virgules (« 06, 98, 76… ») : elles ne sont que des pauses.
    return numero_e164(texte) or numero_e164(lecture.en_chiffres(texte or "").replace(",", " "))


def _centimes(euros: Any) -> int | None:
    """Des euros dits (``20``, ``4.5``) en centimes entiers ; ``None`` si ce n'est pas un montant."""
    try:
        valeur = float(euros)
    except (TypeError, ValueError):
        return None
    return round(valeur * 100) if valeur >= 0 else None


def _cle_de_ligne(l: dict[str, Any]) -> tuple:
    return (l["code"], tuple(sorted(c["option_code"] for c in l["choix"])), tuple(sorted(l["retires"])), l.get("note") or "")


def _instantane(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Ce qui a été relu : chaque ligne, sa quantité. Gardé pour ne redire, après une correction, que ce qui a changé."""
    return [
        {"n": l.get("n"), "cle": list(_cle_de_ligne(l)), "nom": l["nom"], "quantite": P.pieces(l), "genre": l.get("genre"), "commun": bool(l.get("commun"))}
        for l in P.lignes_pretes(p)
    ]


def _majuscule(texte: str) -> str:
    """La première lettre en majuscule, le reste tel quel (``capitalize`` mettrait le reste en minuscules)."""
    return texte[:1].upper() + texte[1:]


def _cle_lue(a: dict[str, Any]) -> str:
    """La clé d'une ligne, lue pareil avant et après un aller-retour JSON (la fiche s'écrit entre deux tours : un tuple y devient une liste)."""
    return json.dumps(a["cle"], ensure_ascii=False)


def _ce_qui_a_change(avant: list[dict[str, Any]], apres: list[dict[str, Any]]) -> list[str]:
    """Chantier Partie 1, lot 6 (L06-41, ``banc-b2/guichet_candidat.py``) : une ligne se suit par son NUMÉRO quand elle en a un ; la même ligne qui
    change de variante ou de composition est « changée » (« C'est changé : Margherita Mega »), jamais retirée puis ajoutée. Une relecture d'avant
    sans numéro garde la comparaison par contenu."""
    if all(a.get("n") is not None for a in [*avant, *apres]):
        anciens_n = {a["n"]: a for a in avant}
        dits = []
        for n in apres:
            a = anciens_n.get(n["n"])
            if a is None:
                dits.append(f"on ajoute {_ligne_dite(n)}")
            elif _cle_lue(a) != _cle_lue(n):
                dits.append(f"c'est changé : {n['nom']}")
            elif a["quantite"] != n["quantite"]:
                dits.append(f"{n['nom']} passe à {nombre_en_lettres(n['quantite'])}")
        nouveaux_n = {n["n"] for n in apres}
        dits += [f"on retire {a['nom']}" for a in avant if a["n"] not in nouveaux_n]
        return dits
    anciens = {_cle_lue(a): a for a in avant}
    nouveaux = {_cle_lue(a): a for a in apres}
    dits: list[str] = []
    for cle, n in nouveaux.items():
        a = anciens.get(cle)
        if a is None:
            dits.append(f"on ajoute {_ligne_dite(n)}")
        elif a["quantite"] != n["quantite"]:
            dits.append(f"{n['nom']} passe à {nombre_en_lettres(n['quantite'])}")
    for cle, a in anciens.items():
        if cle not in nouveaux:
            dits.append(f"on retire {a['nom']}")
    return dits


def le_seul_moyen_de_sa_famille(moyen: str | None, acceptes: list[str]) -> str | None:
    """Lot 4 (C11, appel 2639) : le moyen dit n'est pas accepté tel quel, mais l'établissement n'accepte qu'UNE façon de payer de la même famille
    (même premier mot du code, ``x`` et ``x_y``) à ce mode : c'est celle-là, jamais redemandée. Deux façons acceptées, ou aucune : le moyen tel que
    dit (la liste fermée de la fiche le porte, ou le refus le dit)."""
    if not moyen or moyen in acceptes:
        return moyen
    famille = moyen.split("_")[0]
    proches = [m for m in acceptes if m.split("_")[0] == famille]
    return proches[0] if len(proches) == 1 else moyen


async def _le_reglement(source: Source, p: dict[str, Any], total: int, brut: dict[str, Any]) -> tuple[dict | None, Resultat | None]:
    """Le règlement tel que dit : un moyen, ou une part en un moyen et le reste en un autre (titres, puis espèces sur un billet). Le code
    calcule le reste et la monnaie ; il refuse un moyen non accepté. ``(paiement, None)`` ou ``(None, refus)``."""
    reglages = await source.reglages()
    # M90 (appel 2574) : un moyen que la source réserve à certains modes n'est ni proposé ni accepté hors de ces modes. Mécanisme commun : la
    # source déclare ``moyens_reserves_au_mode`` ({moyen: modes}) ; sans déclaration, tous les moyens réglés valent pour tous les modes.
    reserves = getattr(source, "moyens_reserves_au_mode", None) or {}
    acceptes = [m for m in reglages["moyens_paiement"] if m not in reserves or p.get("mode") in reserves[m]]
    moyen, moyen_reste = le_seul_moyen_de_sa_famille(brut.get("moyen"), acceptes), le_seul_moyen_de_sa_famille(brut.get("moyen_reste"), acceptes)
    if not moyen:
        return None, _r(
            "INCOMPLETE", {"moyens": [source.libelles_des_moyens.get(m, m) for m in acceptes], "acceptes": list(acceptes)}, "Vous réglez comment ?", "paiement"
        )
    for m in (moyen, moyen_reste):
        if m and m not in acceptes:
            return None, _r(
                "MOYEN_NON_ACCEPTE", {"moyen": m, "acceptes": list(acceptes)},
                "Ce moyen de paiement n'est pas accepté. On prend : " + liste_dite_et([source.libelles_des_moyens.get(a, a) for a in acceptes]) + ".",
            )
    part = brut.get("part")
    if part is None or part >= total:
        moyens = [{"moyen": moyen, "montant": total}]
    elif part <= 0:
        return None, _r("ARGUMENT_INVALIDE", {}, "Quel montant exactement ?", "paiement")
    elif not moyen_reste:
        return None, _r("INCOMPLETE", {"reste": total - part}, "Et le reste, vous le réglez comment ?", "paiement_reste")
    else:
        moyens = [{"moyen": moyen, "montant": part}, {"moyen": moyen_reste, "montant": total - part}]
    paiement: dict[str, Any] = {"moyens": moyens, "rendu_sur": None, "monnaie": 0}
    rendu_sur = brut.get("rendu_sur")
    if rendu_sur:
        # Un billet n'a de sens que pour le règlement qui se paie en main ; la monnaie est calculée sur ce qui est payé avec lui.
        cible = next((m for m in moyens if m["moyen"] == brut.get("moyen_du_billet", "especes")), None)
        if cible is None:
            return None, _r("ARGUMENT_INVALIDE", {}, "Sur quel règlement le billet ?", "paiement")
        if rendu_sur < cible["montant"]:
            return None, _r("ARGUMENT_INVALIDE", {"montant": cible["montant"], "billet": rendu_sur}, "Le billet ne couvre pas ce règlement.", "paiement")
        paiement["rendu_sur"], paiement["monnaie"] = rendu_sur, rendu_sur - cible["montant"]
    return paiement, None


def dire_le_rendu_de_monnaie(paiement: dict[str, Any]) -> str:
    """Lot 4 (C11) : le rendu calculé par le code, dit mot pour mot dans la confirmation ; rien quand il n'y a pas de monnaie à rendre."""
    monnaie = int(paiement.get("monnaie") or 0)
    if monnaie <= 0 or not paiement.get("rendu_sur"):
        return ""
    return f"Sur votre billet de {montant_en_lettres(paiement['rendu_sur'])}, on vous rendra {montant_en_lettres(monnaie)}."


def _relecture_deja_dite(p: dict[str, Any], total: int) -> Resultat:
    """M106/M107 (appels 2592, 2593) : la fin rappelée sans rien de nouveau (souvent sur une question de la personne pendant le récapitulatif) :
    rien n'est redit ; la parole revient au modèle avec les faits. Le récapitulatif reste valable : un « oui » ensuite le valide."""
    return _avec(
        _r("INCOMPLETE", {"total": total, "a_confirmer": True, "relecture_deja_dite": True, "rien_de_nouveau": True}, "", "reponse_a_la_relecture"),
        p, total=total,
    )


def recapituler(source: Source, p: dict[str, Any], chiffre: Resultat) -> Resultat:
    """Lot 4 (M38) : LA relecture, la seule (le récapitulatif et le total, avant le règlement, le numéro et le prénom ; appel 2631, Evan, 18/11).
    Tout la première fois, seulement ce qui a changé après une correction. Un jeton en prouve la lecture."""
    avant, maintenant = p.get("derniere_lecture"), _instantane(p)
    total = chiffre.faits["total"]
    if avant and p.get("derniere_lecture_mode") == p["mode"]:
        changes = _ce_qui_a_change(avant, maintenant)
        phrase = (_majuscule(liste_dite_et(changes)) + ". " if changes else "") + f"Cela fait maintenant {montant_en_lettres(total)}. C'est bon ?"
    else:
        lignes = P.lignes_pretes(p)
        if not any(r.get("mecanisme") == "x_achetes_y_offert" for r in chiffre.faits.get("remises") or []):
            # la ligne née de l'offre n'est « offerte » que tant que l'offre vaut (une pizza retirée : elle redevient payante, et se relit ainsi)
            lignes = [{**l, "offerte_dite": False} for l in lignes]
        phrase = f"Je vous relis : {_phrase_des_lignes(lignes)}"
        if p["mode"]:
            phrase += f", {source.libelles_des_modes.get(p['mode'], p['mode'])}"
        if p.get("heure_voulue_dite"):
            phrase += f", pour {p['heure_voulue_dite']}"
        offerts = [] if p.get("presse") else chiffre.faits.get("offerts") or []
        if offerts:
            phrase += ", plus " + _phrase_des_lignes([{"quantite": o["quantite"], "nom": o["nom"], "choix": [], "retires": []} for o in offerts]) + " offert"
        # L06-41 (``banc-b2/guichet_candidat.py`` ``recap``) : la relecture ne nomme pas la remise ; le total la compte, la ligne offerte le dit.
        phrase += f". Cela fait {montant_en_lettres(total)}. C'est bon ?"
    p["relecture"] = {
        "empreinte": P.empreinte(p), "jeton": uuid.uuid4().hex, "version": p["version"], "telephone": p["client"].get("telephone"),
        "recapitulatif": True, "total": total,
    }
    p["derniere_lecture"], p["derniere_lecture_mode"] = maintenant, p["mode"]
    return _avec(
        _r("INCOMPLETE", {"total": total, "lignes": [{"nom": l["nom"], "quantite": P.pieces(l)} for l in P.lignes_pretes(p)], "a_confirmer": True}, phrase, "relecture"),
        p, total=total,
    )


async def regler(
    source: Source, p: dict[str, Any], total: int, *, moyen: str | None = None, rendu_sur: Any = None, part: Any = None, moyen_reste: str | None = None,
) -> tuple[dict | None, Resultat | None]:
    """Lot 4 (M39) : le règlement. Ce qui est dit maintenant remplace ce qui l'était (E3) ; un règlement déjà dit n'est jamais redemandé (C11).
    Rend ``(paiement, None)`` ou ``(None, refus)`` (moyen manquant, non accepté, montant invalide)."""
    if moyen or part is not None or moyen_reste or rendu_sur is not None:
        brut = {"moyen": moyen, "part": _centimes(part) if part is not None else None, "moyen_reste": moyen_reste,
                "rendu_sur": _centimes(rendu_sur) if rendu_sur is not None else None}
        if (part is not None and brut["part"] is None) or (rendu_sur is not None and brut["rendu_sur"] is None):
            return None, _avec(_r("ARGUMENT_INVALIDE", {}, "Quel montant exactement ?", "paiement"), p)
        p["paiement"] = {**(p.get("paiement") or {}), **{k: v for k, v in brut.items() if v is not None}}
    paiement, refus = await _le_reglement(source, p, total, p.get("paiement") or {})
    if refus is not None:
        if refus.manque in ("paiement", "paiement_reste"):
            p["paiement"] = None if refus.manque == "paiement" else p["paiement"]
        return None, _avec(refus, p)
    return paiement, None


TYPE_DE_LA_QUESTION_DU_NUMERO = "numero_affiche"  # C7 : la question « je note le numéro qui s'affiche ? », numérotée comme les autres (règle 4 des cases)


def repondre_au_numero_affiche(p: dict[str, Any], sens: str | None) -> Resultat:
    """C7 : la réponse à la question du numéro qui s'affiche (``reponse`` citant sa question) : « accepte » le garde, « refuse » demande le numéro à noter, « autre » laisse la question posée.
    Le numéro affiché n'est jamais gardé sans cette réponse (avant : une seconde ``finaliser`` de la même fiche valait pour un « oui »)."""
    if sens == "accepte":
        p["numero_affiche_accepte"] = True
        return Resultat("OK", {"numero_affiche": "accepte"}, "")
    if sens == "refuse":
        p["numero_affiche_refuse"] = True
        return Resultat("OK", {"numero_affiche": "refuse"}, "")
    return Resultat("OK", {"rien_ajoute": True, "question_gardee": True}, "")


async def identifier(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, *, telephone: str | None, prenom: str | None) -> Resultat | None:
    """Lot 4 (M39) : le numéro (celui qui s'affiche est proposé une fois ; un numéro dicté est relu par le code), puis le prénom (celui de la fiche
    du client quand le numéro est connu). ``None`` : la personne est identifiée."""
    client = p["client"]
    if prenom and prenom.strip():
        client["prenom"] = " ".join(prenom.split())[:60]
    attendait_le_numero_affiche = p.pop("attente_du_code", None) == "numero_affiche"
    accepte, refuse = bool(p.pop("numero_affiche_accepte", None)), bool(p.pop("numero_affiche_refuse", None))  # C7 : posés par la réponse à sa question, jamais par un « confirmer »
    numero = _numero_dit(telephone) if telephone else None
    if telephone and numero is None:
        return _avec(_r("ARGUMENT_INVALIDE", {}, "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", "telephone"), p)
    if numero:
        client["telephone"] = numero
    elif not client.get("telephone") and appelant.telephone_affiche:
        if attendait_le_numero_affiche and accepte:
            client["telephone"] = appelant.telephone_affiche
        elif attendait_le_numero_affiche and refuse:
            return _avec(_r("INCOMPLETE", {}, "Quel numéro je note ?", "telephone"), p)
        else:
            p["attente_du_code"] = "numero_affiche"
            question = (regles.question_numero_affiche or "").strip() or "Je note le numéro qui s'affiche, c'est bon ?"
            return _avec(_r("INCOMPLETE", {}, question, "confirmer_numero"), p)
    if not client.get("telephone"):
        return _avec(_r("INCOMPLETE", {}, "Quel est votre numéro de téléphone ?", "telephone"), p)
    if not client.get("prenom"):
        connu = await source.client(client["telephone"])
        if connu and connu.get("prenom"):
            client["prenom"] = connu["prenom"]
    if not client.get("prenom"):
        return _avec(_r("INCOMPLETE", {}, "À quel nom je mets la commande ?", "prenom"), p)
    return None


CONSIGNE_AUCUNE = "aucune"


def demander_la_consigne_livreur(source: Source, p: dict[str, Any], r: Resultat) -> Resultat:
    """Lot 4 (C7) : un mode qui exige une adresse demande UNE fois une consigne pour le livreur, avec le récapitulatif (le fait
    ``consigne_livreur: a_demander`` dans son retour) ; elle ne bloque jamais l'enregistrement (B12, conversation 1 : la commande s'enregistre sans
    elle) ; « aucune » est une réponse (rien n'est noté). Une consigne déjà dite (avec l'adresse, ou par le greffier) n'est jamais redemandée."""
    if not p.get("mode") or not source.exige_une_zone(p["mode"]) or p.get("consigne_livreur") or p.get("consigne_livreur_demandee"):
        return r
    p["consigne_livreur_demandee"] = True
    return Resultat(r.statut, {**r.faits, "consigne_livreur": "a_demander"}, r.suggestion, r.manque)


async def retenir_une_habitude(source: Source, telephone: str, texte: str) -> bool:
    """Lot 4 (M41) : une HABITUDE du client (« sonnez au 2e »), écrite sur sa fiche pour ses prochains appels ; jamais la consigne de cette commande.
    Rend vrai si elle est retenue ; une donnée que la fiche du client refuse (une donnée de santé) ne vit que dans la commande (faux)."""
    ecrite = await source.consigne(telephone, texte)
    return not (ecrite.statut == "ARGUMENT_INVALIDE" and ecrite.faits.get("raison") == "pour_la_commande")


CLE_NOTES_DU_GREFFIER = "notes_du_greffier"  # dans le panier : ce que le greffier a noté (allergie, consigne), posé par la porte à chaque fiche


def _consigne_du_livreur(p: dict[str, Any]) -> str | None:
    """Lot 16 : la consigne pour le livreur de CETTE commande (celle de la fiche, sinon celle que le greffier a notée), sans « aucune » : elle part à la caisse dans ``delivery_notes``."""
    consigne = str(p.get("consigne_livreur") or "").strip() or str((p.get(CLE_NOTES_DU_GREFFIER) or {}).get("consigne_livreur") or "").strip()
    return None if not consigne or consigne.casefold() == CONSIGNE_AUCUNE else consigne


def _note_de_la_commande(p: dict[str, Any]) -> str | None:
    """La note envoyée avec la commande (E22, rien n'écrase rien) : la note de la commande, la consigne pour le livreur de CETTE commande, puis
    ce que le greffier a noté et que la fiche ne dit pas déjà (``note.composer_la_note_de_commande``, lot 6)."""
    from api.services.commande.note import composer_la_note_de_commande

    morceaux = [{"texte": str(p["note"])}] if p.get("note") else []
    consigne = str(p.get("consigne_livreur") or "").strip()
    if consigne and consigne.casefold() != CONSIGNE_AUCUNE and all(consigne != m["texte"] for m in morceaux):
        morceaux.append({"texte": f"livreur : {consigne}"})
    note = composer_la_note_de_commande(morceaux, p.get(CLE_NOTES_DU_GREFFIER))
    return note  # la taille est tenue par la composition : l'allergie n'est jamais coupée (D23)


def _brouillon_de_la_commande(p: dict[str, Any], chiffre: Resultat, paiement: dict[str, Any], appelant: Appelant, regles: Reglages) -> dict[str, Any]:
    client = p["client"]
    return {
        "mode": p["mode"], "lignes": P.pour_le_chiffrage(p), "zone_id": _zone_id(p), "adresse": p.get("adresse"),
        "client": {"telephone": client["telephone"], "prenom": client.get("prenom"), "second_numero": client.get("second_numero")},
        "paiement": {"moyens": paiement["moyens"], "rendu_sur": paiement["rendu_sur"]}, "note": _note_de_la_commande(p), "consigne_livreur": _consigne_du_livreur(p),
        "heure_voulue": datetime.fromisoformat(p["heure_voulue"]) if p.get("heure_voulue") else None,
        "appel_id": appelant.appel_id, "cree_par": "agent",
        # Les remises que le chiffrage vient de calculer : l'enregistrement les recalcule et refuse tout écart (jamais un montant du modèle).
        "remises": [{"ref": r["ref"]} for r in chiffre.faits.get("remises") or []], "codes": list(p.get("codes_dits") or []),
    }


async def enregistrer(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, chiffre: Resultat, paiement: dict[str, Any]) -> Resultat:
    """Lot 4 (M39, M40) : l'enregistrement, une fois par appel (E30) ; le récapitulatif approuvé en est la preuve (son jeton). La confirmation est dite
    par le code mot pour mot, avec le rendu de monnaie (C11) et la question qui rend la parole (M108)."""
    client = p["client"]
    if p.get("habitude"):
        if not await retenir_une_habitude(source, client["telephone"], p["habitude"]):
            p["note"] = (f"{p['note']} ; {p['habitude']}" if p.get("note") else p["habitude"])[:300]
        p["habitude"] = None
    jeton = (p.get("relecture") or {}).get("jeton") or uuid.uuid4().hex
    r = await source.enregistrer(_brouillon_de_la_commande(p, chiffre, paiement, appelant, regles), jeton)
    if r.statut in ("ENREGISTREE", "DEJA_FAIT"):
        faits = {**r.faits, "monnaie": paiement["monnaie"]}
        p["enregistree"] = P.serialisable(faits)
        p["empreinte_enregistree"] = P.empreinte(p)
        statut = source.statut_de_l_enregistrement() if r.statut == "ENREGISTREE" else "DEJA_FAIT"
        suggestion = " ".join(t for t in (r.suggestion.strip(), dire_le_rendu_de_monnaie(paiement)) if t)
        question = (regles.question_apres_enregistrement or "").strip()
        if statut != "DEJA_FAIT" and question and suggestion:
            # M108 (appels 2592, 2593) : la confirmation finit par une question : la parole revient à la personne.
            suggestion = f"{suggestion} {question}"
        return _avec(Resultat(statut, faits, suggestion), p)
    if r.statut == "INCOMPLETE" and r.manque == "relecture":
        p["recapitulatif_approuve"] = None
        return recapituler(source, p, chiffre)
    return _avec(r, p)


def _peut_parler_d_offre(p: dict[str, Any], regles: Reglages, ref: str | None = None) -> bool:
    """T-08 : une offre se dit au plus ``mentions_de_remise`` fois par appel, jamais après un refus ; une offre déjà dite peut être suivie (« laquelle voulez-vous ? »)."""
    if p.get("remise_refusee"):
        return False
    return (ref is not None and ref in p.get("remises_dites", [])) or p.get("mentions_de_remise", 0) < regles.mentions_de_remise


def _le(nom: str, genre: str | None) -> str:
    """« Le filtre », « La vis », « L'écrou » : l'article défini du nom proposé, d'après son genre (sans mot de métier)."""
    if _sans_accent(nom[:1]) in "aeiouyh":
        return f"L'{nom}"
    return f"{'La' if genre == 'f' else 'Le'} {nom}"


async def proposer_un_article_en_plus(source: Source, p: dict[str, Any], regles: Reglages, chiffre: Resultat | None = None) -> Resultat | None:
    """Lot 4 (A18, M47, D23, D33) : UN article précis proposé en plus (une offre atteinte, sinon ce qui manque au panier, la meilleure vente d'abord),
    UNE fois par commande, jamais après un refus. Le code décide quoi et quand ; le modèle pose la question avec ses mots (``texte`` : « proposer X ») ;
    le chiffre est dit par le code juste après la phrase du modèle (``chiffre``, gardé dans la question, jamais montré au modèle) ; une proposition
    offerte n'a pas de chiffre. ``repli`` : la proposition de B8, dite par le code seulement quand le modèle n'a aucune phrase (lot 6, E-b).
    ``None`` : rien à proposer, la commande continue."""
    if not regles.vente_en_plus or p.get("vente_en_plus_faite") or p.get("proposition_refusee") or not P.lignes_pretes(p) or P.a_completer(p):
        return None
    chercher = getattr(source, "proposer_en_plus", None)
    if chercher is None:
        return None
    if chiffre is None:
        chiffre = await _chiffrer(source, p, regles)
    if _bloque_l_ajout(chiffre):
        return None  # sous le minimum de la zone, on propose quand même (le minimum se juge à la fin, lot 17)
    p["vente_en_plus_faite"] = True  # une seule fois par commande, même quand rien n'est trouvé
    lignes = chiffre.faits.get("lignes") or []
    proposition = await chercher(p["mode"], lignes, _peut_parler_d_offre(p, regles))
    if proposition is not None and proposition.get("raison") == "offre" and not _peut_parler_d_offre(p, regles, proposition["offre"]["ref"]):
        proposition = await chercher(p["mode"], lignes, False)
    if proposition is None:
        return None
    nom = nom_dit(proposition["nom"], 1, genre=proposition.get("genre"), commun=bool(proposition.get("commun")))
    offerte = proposition["raison"] == "offre"
    faits = {"proposition": {k: proposition.get(k) for k in ("ref", "nom", "declinaison", "raison", "etoile", "plusieurs_tailles")}}
    if offerte:
        offre = proposition["offre"]
        if offre["ref"] not in p.setdefault("remises_dites", []):
            p["remises_dites"].append(offre["ref"])
            p["mentions_de_remise"] = p.get("mentions_de_remise", 0) + 1
        faits["proposition"]["offre"] = offre["nom"]
        offert = "offerte" if proposition.get("genre") == "f" else "offert"
        repli = f"{_dit(offre['nom'])} : vous avez droit à {nom} {offert}. Je vous l'ajoute ?"
        chiffre_dit = None
    else:
        repli = f"Avec cela, je vous propose {nom} à {montant_en_lettres(proposition['prix'])}. Je vous l'ajoute ?"
        chiffre_dit = f"{_le(proposition['nom'], proposition.get('genre'))} est à {montant_en_lettres(proposition['prix'])}."
    p["proposition_en_plus"] = {
        "ref": proposition.get("ref"), "nom": proposition["nom"], "choix": [c for c in (proposition.get("choix") or []) if isinstance(c, str)],
        "offerte": offerte, "chiffre": chiffre_dit, "repli": repli,
    }
    return _r("INCOMPLETE", faits, f"proposer {proposition['nom']}" + (" offert" if offerte else ""), "vente_en_plus")


async def repondre_a_la_proposition(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, sens: str | None,
                                    variante: str | None = None) -> Resultat:
    """Lot 4 (M44, appels 2560, 2568) : la réponse à la proposition en plus. ``accepte`` ajoute l'article proposé ; « oui, mais plutôt X »
    (``variante`` : X, un article du catalogue) ajoute X à sa place ; un mot qui n'est pas un article du catalogue (« oui ») n'est jamais lu comme
    un article. ``refuse`` : rien n'est ajouté et plus rien n'est proposé. La proposition faite juste après le premier article laisse la commande
    continuer ; celle de la fin mène à la suite de la fin."""
    proposee = p.pop("proposition_en_plus", None) or {}
    tot = bool(p.pop("vente_en_plus_tot", False))
    r = _r("OK", {"rien_ajoute": True})
    if sens == "accepte" and proposee:
        nom = proposee["nom"]
        if variante and recherche_liste.normaliser(variante) != recherche_liste.normaliser(nom):
            autre = await _chercher_l_article(source, variante, regles)
            if autre.statut == "RETENU":
                nom = variante
        deja = {l.get("n") for l in p["lignes"]}
        r = await _un_article(source, p, regles, 1, nom)
        if r.statut == "OK":
            if proposee.get("offerte"):
                # L06-41 (``banc-b2/guichet_candidat.py`` ``libelle``) : la ligne née de l'offre acceptée se relit « offerte » (le chiffrage, lui,
                # reste celui de la remise) ; une ligne qui existait déjà et qui gagne un de plus n'est pas marquée.
                for l in p["lignes"]:
                    if l.get("n") not in deja:
                        l["offerte_dite"] = True
            r = await _etat_apres_ajout(source, p, regles, dict(r.faits))
    elif sens == "refuse":
        p["proposition_refusee"] = True
    if tot or r.statut not in ("OK",) or r.manque:
        return _avec(r, p)
    return await finaliser(source, p, regles, appelant)


async def verifier_le_creneau(source: Source, p: dict[str, Any]) -> Resultat | None:
    """Lot 4 (E28, M48, appel 2667) : l'heure voulue posée tient-elle (ouvert à cette heure, délai minimal, jours à l'avance, place) ? Appelée par
    l'opération qui pose l'heure, à chaque correction et avant le récapitulatif. ``None`` : elle tient (et son texte dit est posé) ; sinon le refus
    de la source, et l'heure n'est pas gardée (on en demande une autre)."""
    if not p.get("heure_voulue") or not p.get("mode"):
        return None
    verifier = getattr(source, "verifier_un_creneau", None)
    refus = await verifier(p["mode"], datetime.fromisoformat(p["heure_voulue"])) if verifier else None
    if refus is not None:
        p["heure_voulue"] = p["heure_voulue_dite"] = p["moment_voulu"] = None
        return _avec(refus, p)
    dire = getattr(source, "quand_dit", None)
    p["heure_voulue_dite"] = await dire(datetime.fromisoformat(p["heure_voulue"])) if dire else None
    return None


def question_de_la_ligne_en_attente(p: dict[str, Any]) -> Resultat | None:
    """File d'attente des questions (lot 20, appel 450) : la question d'une ligne qui attend son choix (une taille), lue dans l'ÉTAT du panier, jamais
    gardée à part : tant qu'une ligne attend, sa question existe, quel que soit le résultat qui a suivi dans la fiche. ``None`` : aucune ligne n'attend."""
    en_attente = P.a_completer(p)
    if not en_attente:
        return None
    q = en_attente[0]["attente"]
    return _avec(_r("CHOIX_OBLIGATOIRE", {"article": en_attente[0]["nom"], "question": q}, _phrase_de_la_question(q, en_attente[0]["article_nom"]), q["nom"]), p)


def annoncer_la_fermeture(p: dict[str, Any], etat: dict[str, Any]) -> str:
    """Lot 4 (M07, appel 2649) : la phrase de la fermeture, dite UNE fois par appel (un drapeau du panier, lu partout) ; ensuite, rien."""
    if p.get("fermeture_dite"):
        return ""
    p["fermeture_dite"] = True
    return etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."


async def finaliser(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, **gestes: Any) -> Resultat:
    """La fin, puis le numéro dicté et RETENU dans cet appel dit par le code (``avec_numeros_retenus``) : un numéro corrigé se relit tel que retenu,
    jamais de mémoire. Le numéro qui s'affiche n'est jamais relu ; un numéro déjà dit n'est pas redit tant qu'il ne change pas.

    M98 : quand le numéro gardé est celui qui s'affiche, il est porté dans les faits (``numero_affiche_dit``) pour que l'agent puisse le dire si on
    le lui demande, sans être ajouté à la phrase."""
    if gestes.get("telephone"):
        # Un numéro dicté est jugé et RETENU dès qu'il est dit, à n'importe quelle étape de la fin (M78, M98) : refusé s'il est invalide, sinon gardé pour
        # être dit par le code, tel que retenu, avec la suite ; jamais attendu de l'étape où l'on demande le numéro.
        dicte = _numero_dit(gestes["telephone"])
        if dicte is None:
            return _avec(_r("ARGUMENT_INVALIDE", {}, "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", "telephone"), p)
        if not p.get("enregistree"):
            p.setdefault("client", {})["telephone"] = dicte
    r = await _finaliser(source, p, regles, appelant, **gestes)
    client = p["client"]
    if appelant.telephone_affiche and client.get("telephone") == appelant.telephone_affiche:
        r = avec_numero_affiche(r, appelant.telephone_affiche)
    numero = _numero_dit(gestes.get("telephone")) if gestes.get("telephone") else None
    dit = numero if numero and client.get("telephone") == numero and numero != appelant.telephone_affiche and client.get("numero_dit") != numero else None
    if r.statut in ("ENREGISTREE", "DEJA_FAIT", "TRANSMISE") or not dit:
        return r
    client["numero_dit"] = dit
    return avec_numeros_retenus(r, dit, None)


async def _finaliser(
    source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, *, confirmer: bool = False, prenom: str | None = None,
    telephone: str | None = None, moyen: str | None = None, rendu_sur: Any = None, part: Any = None, moyen_reste: str | None = None,
) -> Resultat:
    """Lot 4 (M38 à M40) : la fin nommée, une seule, dans l'ordre d'un commerçant (appel 2631, Evan, 18/11) : les articles complets, l'ouverture et
    le créneau, la proposition en plus (une fois), ``recapituler`` (avec ``demander_la_consigne_livreur``) et son accord, ``regler``, ``identifier``,
    ``enregistrer``. Un manque à la fois ; une commande incomplète n'est jamais enregistrée ; un panier changé après l'accord se relit (seulement ce
    qui a changé). Le total est celui de la source."""
    deja = p.get("enregistree")
    if deja and p["lignes"]:
        return _avec(Resultat("DEJA_FAIT", dict(deja), "Votre commande est déjà enregistrée."), p)
    manque = await _prealables(source, p, regles)
    if manque is not None:
        return manque
    await _reprendre_les_dits(source, p, regles)  # SA-33 : ce qui était gardé avant les préalables n'est jamais oublié à la fin
    if not p["lignes"]:
        return _avec(_r("INCOMPLETE", {}, "", "articles"), p)
    attente = question_de_la_ligne_en_attente(p)
    if attente is not None:
        return attente
    chiffre = await _chiffrer(source, p, regles)
    if chiffre.statut != "OK":
        return _avec(chiffre, p)
    total = chiffre.faits["total"]
    etat = await source.etat(p["mode"])
    if not etat["ouvert"] and not p.get("heure_voulue"):
        faits_fermes = {k: etat.get(k) for k in CLES_DE_L_ETAT}
        if etat.get("planifiee_permise"):
            # D15 : fermé, mais le réglage du type permet de commander pour plus tard : l'heure voulue est LA question (une seule).
            p["a_planifier"] = True
            prochaine = etat.get("prochaine_ouverture")
            dire = getattr(source, "quand_dit", None)
            if isinstance(prochaine, datetime) and dire is not None:
                # Lot 19, aparté d'Evan (20/11) : « le plus naturel, c'est de proposer une commande pour le prochain service qui commence à telle heure,
                # et de faire confirmer par le client » : l'heure de la réouverture est proposée, la personne la confirme (question ``heure_proposee``).
                phrase = f"{annoncer_la_fermeture(p, etat)} Je vous la prépare pour {await dire(prochaine)} ?".strip()
                return _avec(_r("FERME_PLANIFIABLE", {**faits_fermes, "a_planifier": True, "heure_proposee": prochaine.isoformat()}, phrase, "heure_proposee"), p)
            phrase = f"{annoncer_la_fermeture(p, etat)} Pour quel jour et à quelle heure ?".strip()
            return _avec(_r("FERME_PLANIFIABLE", {**faits_fermes, "a_planifier": True}, phrase, "heure_voulue"), p)
        return _avec(_r(etat["statut"], faits_fermes, annoncer_la_fermeture(p, etat)), p)
    refus = await verifier_le_creneau(source, p)
    if refus is not None:
        return refus
    proposition = await proposer_un_article_en_plus(source, p, regles, chiffre)
    if proposition is not None:
        return _avec(proposition, p)
    attente_allergie = await allergie_sans_reponse(source, p, regles)  # lot 15 : les faits d'une allergie connue sont donnés au modèle AVANT la relecture et l'enregistrement
    if attente_allergie is not None:
        return attente_allergie
    # 1. Le récapitulatif et son accord (``recapituler``, la seule relecture)
    cle = f"{P.empreinte(p)}:{total}"
    if p.get("recapitulatif_approuve") != cle:
        relue = p.get("relecture") or {}
        dit = bool(relue.get("recapitulatif") and relue.get("empreinte") == P.empreinte(p) and relue.get("total") == total)
        if dit and confirmer:
            p["recapitulatif_approuve"] = cle
            confirmer = False  # le oui valait pour le récapitulatif, pas pour la suite
        elif dit:
            return _relecture_deja_dite(p, total)
        else:
            return demander_la_consigne_livreur(source, p, recapituler(source, p, chiffre))
    # 2. Le règlement, 3. le numéro et le prénom, 4. l'enregistrement (la consigne pour le livreur est demandée avec le récapitulatif)
    paiement, refus = await regler(source, p, total, moyen=moyen, rendu_sur=rendu_sur, part=part, moyen_reste=moyen_reste)
    if refus is not None:
        return refus
    manque = await identifier(source, p, regles, appelant, telephone=telephone, prenom=prenom)
    if manque is not None:
        return manque
    return await enregistrer(source, p, regles, appelant, chiffre, paiement)


# --------------------------------------------------------------------------- #
# La commande enregistrée reste adressable (lot 4, E10, S8 ; A31, M34) : une commande par appel (E30), changée ou annulée selon la prise
# --------------------------------------------------------------------------- #


def commande_de_l_appel(p: dict[str, Any]) -> dict[str, Any] | None:
    """La commande enregistrée dans CET appel (numéro, numéro court, heure annoncée, total), tant qu'elle n'est pas annulée ; ``None`` sinon."""
    commande = p.get("enregistree")
    return commande if isinstance(commande, dict) and commande.get("numero") and not p.get("annulee") else None


def _permet_l_annulation(source: Source) -> bool:
    permet = getattr(source, "permet_l_annulation", None)
    return bool(permet and permet() and getattr(source, "annuler_une_commande", None))


async def annuler_commande_enregistree(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
    """Elle annule la commande de CET appel, déjà enregistrée : elle passe à « annulée » dans le classeur et la prise est informée. Refusée avec la
    raison quand la prise ne sait pas annuler (fiche de capacités de sa prise) ou que la commande ne peut plus l'être (déjà remise)."""
    commande = commande_de_l_appel(p)
    if commande is None:
        return _avec(_r("INTROUVABLE", {"raison": "commande_introuvable"}, ""), p)
    if not _permet_l_annulation(source):
        return _avec(_r("INTERDIT", {"raison": "annulation_impossible", "numero_court": commande.get("numero_court")}, ""), p)
    r = await source.annuler_une_commande(str(commande["numero"]))
    if r.statut not in ("OK", "DEJA_FAIT"):
        return _avec(_r("INTERDIT", {"raison": "commande_deja_preparee", "numero_court": commande.get("numero_court")}, ""), p)
    p["enregistree"], p["annulee"], p["question"] = None, True, None
    p["commande_annulee"] = commande.get("numero_court")
    return _avec(_r("OK", {"commande_annulee": commande.get("numero_court")}, ""), p)


async def changer_commande_enregistree(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, avant: dict[str, Any]) -> Resultat:
    """La commande de CET appel, déjà enregistrée, vient d'être changée dans le panier (« finalement deux tiramisus », « mettez-la en mega ») :
    le changement est porté à la prise en remplaçant la commande (l'ancienne annulée, la nouvelle enregistrée à sa place : toujours une seule
    commande active pour l'appel, E30). ``avant`` : le panier d'avant la fiche. Quand la prise ne sait pas annuler, que le nouveau panier ne se
    chiffre pas ou que le règlement ne tient plus, rien n'est changé (le panier redevient celui d'avant) et la raison est rendue."""
    commande = commande_de_l_appel(avant) or {}

    def remettre(r: Resultat) -> Resultat:
        p.clear()
        p.update(avant)
        return _avec(r, p)

    if not _permet_l_annulation(source):
        return remettre(_r("INTERDIT", {"raison": "changement_impossible", "numero_court": commande.get("numero_court")}, ""))
    if P.a_completer(p):
        return _avec(await _etat_apres_ajout(source, p, regles, {}), p)  # la ligne changée attend encore sa réponse : rien ne part à la prise
    chiffre = await _chiffrer(source, p, regles)
    if chiffre.statut != "OK":
        return remettre(chiffre)
    paiement, refus = await _le_reglement(source, p, chiffre.faits["total"], p.get("paiement") or {})
    if refus is not None:
        return remettre(refus)
    annulee = await source.annuler_une_commande(str(commande.get("numero")))
    if annulee.statut not in ("OK", "DEJA_FAIT"):
        return remettre(_r("INTERDIT", {"raison": "commande_deja_preparee", "numero_court": commande.get("numero_court")}, ""))
    p["enregistree"] = None
    r = await enregistrer(source, p, regles, appelant, chiffre, paiement)
    if r.statut not in ("ENREGISTREE", "TRANSMISE"):
        logger.error(f"[.mark] commande {commande.get('numero_court')} annulée pour être changée, la nouvelle n'est pas enregistrée : {r.statut}")
        return r
    return Resultat(r.statut, {**r.faits, "remplace": commande.get("numero_court")}, r.suggestion, r.manque)


# --------------------------------------------------------------------------- #
# remises_disponibles : la parole des remises (lot 7, T-08)
# --------------------------------------------------------------------------- #


def _dit(texte: str) -> str:
    """Une phrase écrite par une personne (une offre, un nom d'offre), prête à être dite : chiffres en lettres, un seul point final."""
    return phrase_nette(chiffres_en_lettres(texte))


def _phrase_d_une_remise_appliquee(r: dict[str, Any]) -> str:
    return _dit(r["phrase"]) if r.get("phrase") else f"Bonne nouvelle : {_dit(r['nom'])}, cela vous fait {montant_en_lettres(r['montant'])} de moins."


async def _noter_dite(source: Source, ref: str, appel_id: str | None) -> None:
    """M38 : une offre rendue à dire est comptée « dite » (une fois par appel). Ne casse jamais l'appel."""
    noter = getattr(source, "noter_une_offre_dite", None)
    if noter is None:
        return
    try:
        await noter(ref, appel_id)
    except Exception as erreur:  # noqa: BLE001 -- un compteur d'écran ne défait jamais la réponse à l'appelant
        logger.warning(f"[.mark] Offer said not counted: {erreur!r}")


async def remises_disponibles(
    source: Source, p: dict[str, Any], regles: Reglages, *, demande: bool = False, presse: bool = False, refus: bool = False, appel_id: str | None = None
) -> Resultat:
    """Ce que l'agent peut dire des remises, et QUAND. Le code compte, le modèle dit.

    - ``demande`` (l'appelant demande « qu'est-ce que vous avez ») : on répond toujours, par les remises valables maintenant ;
    - sinon c'est l'initiative de l'agent, au plus ``regles.mentions_de_remise`` fois par appel, jamais à un appelant ``presse`` ni à celui
      qui a dit non (``refus``, retenu pour tout l'appel) ; une remise déjà dite n'est pas redite ;
    - ce qui vaut la peine d'être dit : une remise qui s'APPLIQUE au panier, ou un seuil de panier presque atteint (à moins de 30 %).
    ``faits.a_dire`` est faux quand il n'y a rien à dire (avec ``raison``) : l'agent se tait, il n'invente rien."""
    p.setdefault("mentions_de_remise", 0)
    p.setdefault("remises_dites", [])
    if refus:
        p["remise_refusee"] = True
    en_cours = await source.remises_en_cours()
    chiffre = await _chiffrer(source, p, regles) if p["lignes"] and p["mode"] and not P.a_completer(p) else None
    appliquees = (chiffre.faits.get("remises") or []) if chiffre is not None and chiffre.statut == "OK" else []
    if demande:
        if not en_cours:
            return _avec(_r("OK", {"a_dire": False, "raison": "aucune", "remises": []}, "Pas d'offre en ce moment."), p)
        dites = [{"nom": r["nom"], "phrase": r["phrase"]} for r in en_cours]
        for r in en_cours:
            await _noter_dite(source, r["ref"], appel_id)
        phrase = phrase_nette("En ce moment : " + liste_dite_et([_dit(r["phrase"] or r["nom"]).rstrip(".") for r in en_cours]) + ".")
        return _avec(_r("OK", {"a_dire": True, "remises": dites, "appliquees": [r["nom"] for r in appliquees]}, phrase), p)
    if p.get("remise_refusee"):
        return _avec(_r("OK", {"a_dire": False, "raison": "refusee"}), p)
    if presse:
        p["presse"] = True  # retenu pour tout l'appel : la relecture non plus ne cite aucune offre
        return _avec(_r("OK", {"a_dire": False, "raison": "presse"}), p)
    if p["mentions_de_remise"] >= regles.mentions_de_remise:
        return _avec(_r("OK", {"a_dire": False, "raison": "deja_dite"}), p)
    for r in appliquees:
        if r["ref"] not in p["remises_dites"]:
            p["mentions_de_remise"] += 1
            p["remises_dites"].append(r["ref"])
            await _noter_dite(source, r["ref"], appel_id)
            return _avec(_r("OK", {"a_dire": True, "moment": "appliquee", "remise": {"nom": r["nom"], "montant": r["montant"]}}, _phrase_d_une_remise_appliquee(r)), p)
    # M25 : une offre « X achetés, Y offerts d'une autre sorte » ATTEINTE ou presque, même sans l'article offert au panier.
    offres = []
    if chiffre is not None and chiffre.statut == "OK" and getattr(source, "offres_a_portee", None) is not None:
        offres = await source.offres_a_portee(p["mode"], chiffre.faits.get("lignes") or [])
    for o in offres:
        if o["ref"] in p["remises_dites"]:
            continue
        if o["etat"] == "atteinte" and o.get("proposition"):
            p["mentions_de_remise"] += 1
            p["remises_dites"].append(o["ref"])
            await _noter_dite(source, o["ref"], appel_id)
            debut = _dit(o["phrase"]) if o.get("phrase") else f"{_dit(o['nom'])} : vous y avez droit."
            phrase = f"{debut} Qu'est-ce qui vous ferait plaisir : {liste_dite(o['choix'])} ?"
            faits = {"a_dire": True, "moment": "offre_atteinte", "remise": {"nom": o["nom"], "choix": o["choix"], "prix": o["proposition"]["prix"]}}
            return _avec(_r("OK", faits, phrase), p)
        if o["etat"] == "presque":
            p["mentions_de_remise"] += 1
            p["remises_dites"].append(o["ref"])
            await _noter_dite(source, o["ref"], appel_id)
            faits = {"a_dire": True, "moment": "offre_presque_atteinte", "remise": {"nom": o["nom"], "manque_articles": o["manque"]}}
            return _avec(_r("OK", faits, f"Il vous manque encore un article pour avoir {_dit(o['nom'])}."), p)
    sous_total = chiffre.faits["sous_total"] if chiffre is not None and chiffre.statut == "OK" else 0
    for r in en_cours:
        minimum = r.get("minimum")
        if minimum and r["ref"] not in p["remises_dites"] and sous_total and minimum * 7 // 10 <= sous_total < minimum:
            p["mentions_de_remise"] += 1
            p["remises_dites"].append(r["ref"])
            await _noter_dite(source, r["ref"], appel_id)
            reste = minimum - sous_total
            return _avec(
                _r("OK", {"a_dire": True, "moment": "seuil_presque_atteint", "remise": {"nom": r["nom"], "manque": reste}},
                   f"Il vous manque {montant_en_lettres(reste)} pour avoir {_dit(r['nom'])}."),
                p,
            )
    return _avec(_r("OK", {"a_dire": False, "raison": "rien_a_dire"}), p)


# --------------------------------------------------------------------------- #
# voir_produit : la composition et les signalements d'un article (lot 7, E-14, E-15)
# --------------------------------------------------------------------------- #

NON_CONFIRMABLE = "Je ne peux pas vous le confirmer."

# M104 (appel 2591) : « vous avez des X sans Y ? », « quelque chose sans Y ? », un régime : chercher dans le catalogue ce qui est SANS une chose.
_SANS = re.compile(r"(?<!\w)sans\s+(?P<chose>.+)$", re.IGNORECASE)
# Des mots de la langue qui ne nomment rien du catalogue (aucun mot de métier) : ce qui reste nomme une catégorie, un article ou rien.
_MOTS_DE_LA_QUESTION = frozenset({
    "un", "une", "des", "de", "du", "d", "la", "le", "les", "l", "vous", "avez", "auriez", "est", "ce", "que", "qu", "quoi", "qui", "il", "y", "a",
    "en", "pour", "moi", "nous", "quelque", "chose", "choses", "truc", "trucs", "rien", "autre", "aussi", "chez", "votre", "vos",
})
_PLUS_DE_NOMS = 5
_PAS_SUR = "la fiche ne le précise pas, l'équipe peut vous répondre."


def _mots_significatifs(texte: str) -> list[str]:
    """Les mots qui nomment quelque chose, tels qu'ils sont dits (« des tartes » → ``["tartes"]``)."""
    return [m for m in re.findall(r"[\w-]+", texte) if _sans_accent(m) not in _MOTS_DE_LA_QUESTION]


def _sans_accent(mot: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", mot.casefold()) if unicodedata.category(c) != "Mn")


def _racines(texte: str) -> set[str]:
    """Les mots significatifs, sans accent ni marque du pluriel : « Tartes salées » → ``{tarte, salee}``."""
    racines = set()
    for mot in re.findall(r"[\w-]+", texte):
        m = _sans_accent(mot)
        if m in _MOTS_DE_LA_QUESTION:
            continue
        racines.add(m[:-1] if len(m) > 3 and m[-1] in "sx" else m)
    return racines


def _sans_article(libelle: str) -> str:
    """« le gluten » → « gluten », « les œufs » → « œufs »."""
    return re.sub(r"^(?:le|la|les|l['’])\s*", "", libelle.strip(), flags=re.IGNORECASE)


def _de(mot: str) -> str:
    return ("d'" if _sans_accent(mot[:1]) in "aeiouyh" or mot[:1].casefold() == "œ" else "de ") + mot


def _etat_sans(article: dict, code: str) -> str:
    """``sur`` : la donnée prouve que l'article ET toutes les options de ses choix obligatoires ne contiennent pas ``code`` ; ``contient`` : toutes les façons de le commander en contiennent ;
    ``selon_le_choix`` : une option obligatoire en contient (A3, lot 19 bis : « sans » ne tient pas si le client peut devoir la prendre) ; ``inconnu`` sinon.
    Une donnée absente n'est JAMAIS « sans » (jamais un faux non)."""
    signalements = article.get("signalements")
    dit = inf1.brique_inf1_repondre_depuis_la_donnee(None if signalements is None else [s["code"] for s in signalements], code)  # lot 15 (INF1)
    if dit == "inconnu":
        return "inconnu"
    if dit == "present":
        return "contient"
    etat = "sur"
    for options in article.get("obligatoires") or []:
        signales = [_option_signale(o, code) for o in options]
        if options and all(signales):
            return "contient"
        if any(signales):
            etat = "selon_le_choix"
        elif etat == "sur" and options and not all(x is False for x in signales):
            etat = "inconnu"
    return etat


async def _chercher_ce_qui_est_sans(source: Source, p: dict[str, Any], regles: Reglages, produit: str | None, signale: str | None) -> Resultat | None:
    """M104 : ce que le catalogue a SANS une chose (dans une catégorie si elle est dite), d'après la donnée seulement. ``None`` : ce n'est pas
    cette question (un article précis, ou rien d'« évité » reconnu) : ``voir_produit`` répond comme avant.

    Une chose que la donnée ne porte pas (un régime) n'est jamais déduite : « je ne peux pas le garantir ». Un article dont la donnée manque
    n'est jamais rendu « sans ». Les formules n'y sont pas (leur contenu dépend du choix)."""
    texte, evite = (produit or "").strip(), (signale or "").strip()
    trouve = _SANS.search(texte)
    reste, chose = (texte[: trouve.start()].strip(), trouve.group("chose").strip()) if trouve else (texte, evite)
    regime = getattr(source, "regime_dit", None)
    regime = regime(f"{texte} {evite}") if regime else None
    code = source.signalement_dit(chose) if chose else None
    if code is None:
        if regime is None:
            return None
        if texte and getattr(source, "regime_dit", lambda _t: None)(texte) is None:
            return None  # un article nommé, le régime en « à éviter » : la question porte sur CET article (``_regime_dit``), pas sur le catalogue
        return await _regime_du_catalogue(source, p, regime)
    lire = getattr(source, "catalogue", None)
    if lire is None:
        return None
    catalogue = await lire(p.get("mode") or source.modes[0])
    articles = catalogue.get("articles") or []
    voulu = _racines(reste)
    categories = sorted({a["categorie"] for a in articles if a.get("categorie") and voulu and voulu <= _racines(a["categorie"])})
    if reste and voulu and not categories:
        if not trouve:
            return None  # « il y a du Y dans l'article X ? » : la question sur UN article, comme avant
        sur_un_article = await voir_produit(source, p, regles, reste, chose)
        if sur_un_article.statut == "OK":
            return sur_un_article  # « l'article X sans Y, c'est possible ? »
    if categories:
        articles = [a for a in articles if a.get("categorie") in categories]
    mot = _sans_article((catalogue.get("libelles") or {}).get(code, code))
    etats = [(a, _etat_sans(a, code)) for a in articles]
    surs = [a["nom"] for a, e in etats if e == "sur"]
    selon = [a["nom"] for a, e in etats if e == "selon_le_choix"]
    contiennent = sum(1 for _, e in etats if e == "contient")
    inconnus = sum(1 for _, e in etats if e == "inconnu")
    faits = {"recherche": "sans", "code": code, "categories": categories, "sans": surs, "contiennent": contiennent, "inconnus": inconnus, **({"selon_le_choix": selon} if selon else {})}
    if surs:
        dits = surs[:_PLUS_DE_NOMS]
        entre_autres = ", entre autres," if len(surs) > len(dits) else ""
        verbe = "ne contient pas" if len(surs) == 1 else "ne contiennent pas"
        phrase = f"D'après la fiche, {liste_dite_et(dits)}{entre_autres} {verbe} {_de(mot)}."
        if selon:
            phrase += f" Pour {liste_dite_et(selon[:_PLUS_DE_NOMS])}, ça dépend du choix : je ne peux pas le garantir."
        if inconnus:
            phrase += " Pour les autres, je ne peux pas le garantir."
        return _r("OK", faits, phrase)
    nommes = " ".join(_mots_significatifs(reste)) if categories else ""
    debut = f"Je ne peux pas vous garantir de {nommes} sans {mot}" if nommes else f"Je ne peux rien vous garantir sans {mot}"
    if contiennent and not inconnus and not selon:
        return _r("OK", faits, f"{debut} : d'après la fiche, il y en a {'dedans' if contiennent == 1 else 'partout'}.")
    if selon:
        return _r("OK", faits, f"{debut} : pour {liste_dite_et(selon[:_PLUS_DE_NOMS])}, ça dépend du choix, et {_PAS_SUR}")
    return _r("OK", faits, f"{debut} : {_PAS_SUR}")


# Lot 4 (M49, C13, appels 2640, 2641) : « qu'avez-vous sans oignons ? », « lesquels contiennent du chorizo ? », « un article avec du thon ».
_CONTIENT = re.compile(r"(?<!\w)(?:avec|qui\s+contien(?:t|nent)|contenant)\s+(?:(?:du|de\s+la|de\s+l['’]|des|de|d['’]|un|une)\s*)?(?P<chose>.+)$", re.IGNORECASE)
_SANS_INGREDIENT = re.compile(r"(?<!\w)sans\s+(?:(?:du|de\s+la|de\s+l['’]|des|de|d['’])\s*)?(?P<chose>.+)$", re.IGNORECASE)


def _contient_l_ingredient(source: Source, ingredients: list[str] | None, chose: str) -> bool | None:
    """``True`` : un ingrédient du catalogue est la chose dite (au mot près, pluriel compris) ou un de ses noms la porte (« thon » pour
    « du poisson ») ; ``False`` : le catalogue dit ce que l'article contient, et la chose n'y est pas ; ``None`` : il ne le dit pas (inconnu)."""
    if not ingredients:
        return None
    voulus = _racines(chose)
    code = source.signalement_dit(chose) if getattr(source, "signalement_dit", None) else None
    nommes = getattr(source, "codes_d_un_nom", None)
    for ingredient in ingredients:
        if voulus and voulus <= _racines(ingredient):
            return True
        if code and nommes and code in nommes(ingredient):
            return True
    return False


async def chercher_par_ingredient(source: Source, p: dict[str, Any], regles: Reglages, chose: str, *, contient: bool, categorie: str | None = None) -> Resultat:
    """Lot 4 (M49, C13) : une LECTURE du catalogue par ingrédient. ``contient`` : les articles qui contiennent la chose (« du thon », « du poisson ») ;
    sinon ceux qui ne la contiennent pas (« sans oignons »). Seule la donnée parle : un article dont le catalogue ne dit pas ce qu'il contient est
    INCONNU, jamais « il n'y en a pas » (E21) ; un article sans la chose n'est dit « sans » que d'après la fiche."""
    lire = getattr(source, "catalogue", None)
    if lire is None:
        return _r("OK", {"recherche": "ingredient", "articles": [], "inconnus": 0, "renseigne": False}, NON_CONFIRMABLE)
    catalogue = await lire(p.get("mode") or source.modes[0])
    articles = catalogue.get("articles") or []
    voulu = _racines(categorie or "")
    if voulu:
        dans = [a for a in articles if a.get("categorie") and voulu <= _racines(a["categorie"])]
        articles = dans or articles
    etats = [(a, _contient_l_ingredient(source, a.get("ingredients"), chose)) for a in articles]
    trouves = list(dict.fromkeys(a["nom"] for a, e in etats if e is (True if contient else False)))
    inconnus = sum(1 for _, e in etats if e is None)
    faits = {"recherche": "ingredient", "chose": chose, "contient": contient, "articles": trouves, "inconnus": inconnus}
    chose_dite = _sans_article(chose)
    if trouves:
        dits = trouves[:_PLUS_DE_NOMS]
        entre_autres = ", entre autres," if len(trouves) > len(dits) else ""
        verbe = ("contient" if len(trouves) == 1 else "contiennent") if contient else ("ne contient pas" if len(trouves) == 1 else "ne contiennent pas")
        phrase = f"D'après nos articles, {liste_dite_et(dits)}{entre_autres} {verbe} {_de(chose_dite)}."
        if inconnus:
            phrase += " Pour les autres, je ne peux pas vous le confirmer."
        return _r("OK", faits, phrase)
    if inconnus:
        return _r("OK", faits, NON_CONFIRMABLE)
    phrase = f"D'après nos articles, aucun ne contient {_de(chose_dite)}." if contient else "D'après nos articles, tous en contiennent."
    return _r("OK", faits, phrase)


def ingredient_demande(texte: str | None) -> tuple[str, bool, str] | None:
    """La recherche par ingrédient que dit la lecture (« avec du thon », « qui contiennent du chorizo », « sans oignons ») : la chose, ``contient``
    et ce qui la précède (une catégorie dite) ; ``None`` : ce n'est pas une recherche par ingrédient."""
    t = (texte or "").strip()
    for motif, contient in ((_CONTIENT, True), (_SANS_INGREDIENT, False)):
        m = motif.search(t)
        if m and m.group("chose").strip(" ?.!"):
            return m.group("chose").strip(" ?.!"), contient, t[: m.start()].strip()
    return None


async def voir_produit(source: Source, p: dict[str, Any], regles: Reglages, produit: str | None, signale: str | None = None) -> Resultat:
    """Ce que le catalogue dit d'UN article.

    - sans ``signale`` : sa composition (« il y a quoi dans la Reine »), rien d'autre : un signalement n'est jamais donné de soi-même ;
    - avec ``signale`` (l'appelant parle d'une sensibilité) : seulement ce signalement-là, d'après la fiche.

    Une donnée absente est INCONNUE, jamais « sans » : « je ne peux pas vous le confirmer », sans passer la main (E-15). Une fiche qui dit
    la liste (même vide) permet de dire qu'elle ne contient pas la chose demandée, en précisant que c'est la fiche qui le dit.

    M88 (appel 2574) : un seul article possible et le reste dit qui nomme une de ses options (« tiramisu pistache ») retient l'article AVEC
    l'option (le chemin d'``ajouter``) ; un reste qui n'est pas une option certaine laisse le doute. Les signalements d'une option comptent :
    l'option dite, ou sans option dite, chaque choix OBLIGATOIRE (« ça dépend », l'option qui en contient est nommée). Une option sans donnée
    n'est jamais dite « sans » : « je ne peux pas le garantir »."""
    demande = ingredient_demande(produit) if not signale else None
    if demande is not None and demande[1]:
        r = await chercher_par_ingredient(source, p, regles, demande[0], contient=True, categorie=demande[2])
        if r.faits.get("articles") or not (await source.chercher(produit.strip())).statut == "RETENU":
            return _avec(r, p)  # « un article avec du thon » : les articles qui en contiennent (jamais un article proposé par ressemblance de lettres)
    sans = await _chercher_ce_qui_est_sans(source, p, regles, produit, signale)
    if sans is not None:
        return _avec(sans, p)
    if demande is not None and not demande[1]:
        r = await chercher_par_ingredient(source, p, regles, demande[0], contient=False, categorie=demande[2])
        if r.faits.get("articles") or r.faits.get("inconnus"):
            return _avec(r, p)  # « lesquels sans oignons ? » : d'après les ingrédients du catalogue
    if not produit or not produit.strip():
        return _r("ARGUMENT_INVALIDE", {}, "De quel article parlez-vous ?", "produit")
    cherche = await source.chercher(produit.strip())
    trouve, dit_en_plus = await _un_seul_candidat(source, cherche, produit.strip())
    if trouve.statut != "RETENU":
        return _avec(trouve, p)
    fiche = await source.article(trouve.faits["retenu"], p.get("mode") or source.modes[0])
    if fiche is None:
        return _avec(_r("INTROUVABLE", {}, "Je ne trouve pas cet article."), p)
    option = _option_dite(fiche, dit_en_plus) if dit_en_plus else None
    if dit_en_plus and option is None:
        return _avec(cherche, p)  # le reste dit n'est pas une option certaine : le doute reste un doute
    nom = fiche["nom"]
    info = await _regles_d_information(source)
    if not signale:
        du_moment = art3.brique_art3_texte_du_jour(fiche)
        if du_moment is not None:  # ART3 : un produit du moment se lit par son texte du jour, tel que saisi, jamais par ses ingrédients
            return _avec(_r("OK", {"article": nom, **du_moment}, du_moment["texte_du_jour"] if du_moment["renseigne"] else NON_CONFIRMABLE), p)
        if fiche.get("formule"):  # lot 11 : une formule se lit par ses étapes et ses règles, son prix dit par le code
            return _avec(_lecture_de_la_formule(fiche), p)
        composition = list(fiche.get("ingredients") or [])
        avec = {"option": option["nom"]} if option else {}
        avec.update({"servi_avec": fiche["servi_avec"]} if fiche.get("servi_avec") else {})  # FOR13 : ce qui est servi avec, d'après la rubrique
        avec.update(_informations_de_la_fiche(fiche, info))  # lot 15 (INF3, INF4, INF5, INF7) : régimes, épice, nutrition, ce qui est écrit pour le halal
        prix = _faits_du_prix(fiche)  # PRX5 : le prix « à partir de », dit par le code
        if not composition:
            return _avec(_r("OK", {"article": nom, "renseigne": False, **avec, **prix}, NON_CONFIRMABLE), p)
        return _avec(_r("OK", {"article": nom, "renseigne": True, "ingredients": composition, **avec, **prix}, f"Dans {nom}, il y a {liste_dite_et(composition)}."), p)
    regime = getattr(source, "regime_dit", lambda _t: None)(signale)
    if regime is not None:
        return _avec(_regime_dit(source, fiche, regime, info), p)
    if info.get("allergies_renvoyees_au_restaurant"):  # D22 : le restaurant a choisi de renvoyer toute question d'allergène vers lui
        return _avec(_r("OK", {"article": nom, "signalement": "renvoye_au_restaurant", "equipe_confirme": True, **_consigne_d_allergie(info)}, "L'équipe vous le confirme."), p)
    dit = _signalement_dit(source, fiche, option, signale)
    return _avec(Resultat(dit.statut, {**dit.faits, **_consigne_d_allergie(info)}, dit.suggestion, dit.manque), p)


# --------------------------------------------------------------------------- #
# L'allergie : les faits donnés au modèle par le code (lot 15, D22 ; proposition de Pierre du 19/11, tranchée par Evan le 20/11)
# --------------------------------------------------------------------------- #

RAISON_ALLERGIE = "allergie_sans_reponse"  # un préalable manquant (statut INCOMPLETE, comme les autres) : pas d'enregistrement tant que les faits de l'allergie n'ont pas été donnés au modèle dans un tour dont la phrase a été dite


def allergie_connue(p: dict[str, Any]) -> str | None:
    """L'allergie que le greffier a notée dans l'appel (la donnée structurée, ``CLE_NOTES_DU_GREFFIER``) : jamais lue dans les mots de la personne (D1)."""
    texte = str((p.get(CLE_NOTES_DU_GREFFIER) or {}).get("allergie") or "").strip()
    return texte or None


def _options_de_la_fiche(groupes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [o for g in groupes or [] for o in [*(g.get("options") or []), *_options_de_la_fiche([e for o in g.get("options") or [] for e in o.get("enfants") or []])]]


async def _etat_de_l_allergene_par_ligne(source: Source, p: dict[str, Any], code: str, seulement: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], str]:
    """Pour ``code`` : ``[{"article", "etat"}]`` (``present`` | ``absent_de_la_fiche`` | ``inconnu``) d'après les allergènes VALIDÉS du produit et des options choisies (INF1, INF2), comme ``lire``.
    ``seulement`` (A2) : les lignes à regarder, par défaut toutes celles du panier."""
    lignes: list[dict[str, Any]] = []
    libelle = code
    for ligne in (p.get("lignes") or []) if seulement is None else seulement:
        fiche = await source.article(ligne["ref"], p.get("mode") or source.modes[0]) if ligne.get("ref") else None
        if fiche is None:
            lignes.append({"article": ligne["nom"], "etat": "inconnu"})
            continue
        libelle = (fiche.get("signalements_libelles") or {}).get(code, libelle)
        choisi = str(ligne.get("choix") or "").casefold()
        options = [
            {"allergenes": None if o.get("signalements") is None else [s["code"] for s in o["signalements"]], "signalements_du_nom": o.get("signalements_du_nom")}
            for o in _options_de_la_fiche(fiche.get("groupes") or []) if o.get("nom") and str(o["nom"]).casefold() in choisi
        ]
        signalements = fiche.get("signalements")
        lignes.append({"article": ligne["nom"], "etat": inf2.brique_inf2_produit_et_options(None if signalements is None else [s["code"] for s in signalements], options, code)})
    return lignes, libelle


BORNE_DES_ARTICLES_D_ALLERGIE = 12  # au-delà, le fait dit le NOMBRE d'articles et que l'équipe confirme, jamais une liste de la carte entière


def _bornee(noms: list[str]) -> dict[str, Any]:
    """Une liste de noms d'articles, bornée : les noms si elle tient, sinon seulement leur nombre."""
    noms = list(dict.fromkeys(noms))
    return {"noms": noms} if len(noms) <= BORNE_DES_ARTICLES_D_ALLERGIE else {"nombre": len(noms)}


async def _articles_de_la_carte_concernes(source: Source, p: dict[str, Any], code: str) -> dict[str, Any]:
    """Les articles de la CARTE que l'allergène ``code`` concerne, sans que la personne les nomme : ceux qui le contiennent (allergènes validés) et ceux dont la donnée est inconnue ou seulement
    proposée (à confirmer par l'équipe). Un article dont la liste validée ne le nomme pas n'y figure pas. Les formules n'y sont pas (leur contenu dépend du choix)."""
    lire = getattr(source, "catalogue", None)
    if lire is None:
        return {}
    articles = (await lire(p.get("mode") or source.modes[0])).get("articles") or []
    contiennent = [a["nom"] for a in articles if inf1.brique_inf1_repondre_depuis_la_donnee(None if a.get("signalements") is None else [s["code"] for s in a["signalements"]], code) == "present"]
    inconnus = [a["nom"] for a in articles if a.get("signalements") is None]
    return {"carte": {"contiennent": _bornee(contiennent), "a_confirmer_par_l_equipe": _bornee(inconnus)}}


async def faits_de_l_allergie(source: Source, p: dict[str, Any], seulement: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Les faits que le CODE donne au modèle dès qu'une allergie est connue dans l'appel, comme un ``lire`` qu'il n'aurait pas eu à appeler : pour chaque article du panier, l'allergène est
    ``present``, ``absent_de_la_fiche`` ou ``inconnu`` (allergènes validés seulement). ``a_confirmer_par_l_equipe`` quand une donnée manque, quand le restaurant a choisi de renvoyer vers lui (D22) ou
    quand l'allergie n'est pas un des quatorze (E21) : jamais « il n'y en a pas » sans donnée validée. Aucune phrase : le modèle répond avec ses mots. ``None`` : aucune allergie connue.
    ``seulement`` (A2) : ne regarder que ces lignes du panier (ajoutées ou changées depuis les faits donnés), sans redonner la carte."""
    allergie = allergie_connue(p)
    if allergie is None:
        return None
    info = await _regles_d_information(source)
    faits: dict[str, Any] = {"allergie": allergie, **_consigne_d_allergie(info)}
    codes, mot_inconnu = _signalements_dits(source, allergie)
    if info.get("allergies_renvoyees_au_restaurant"):
        return {**faits, "renvoye_au_restaurant": True, "a_confirmer_par_l_equipe": True}
    if not codes:
        return {**faits, "allergene": None, "a_confirmer_par_l_equipe": True}
    par_allergene = [await _faits_d_un_allergene(source, p, code, seulement) for code in codes]
    if len(par_allergene) == 1 and not mot_inconnu:
        return {**faits, **par_allergene[0]}
    # A1 : plusieurs allergènes dits (ou un mot d'allergie que la source ne reconnaît pas) : chacun est vérifié ; le reste est « à confirmer par l'équipe »
    return {**faits, "allergenes": par_allergene, "a_confirmer_par_l_equipe": mot_inconnu or any(a["a_confirmer_par_l_equipe"] for a in par_allergene)}


def _signalements_dits(source: Source, texte: str) -> tuple[list[str], bool]:
    """A1 : les codes que le texte nomme (tous), et si une partie du texte n'est pas reconnue. Une source qui ne sait nommer qu'un code : ce code, rien d'inconnu."""
    tous = getattr(source, "signalements_dits", None)
    if tous is not None:
        codes, inconnu = tous(texte)
        return list(codes), bool(inconnu)
    code = getattr(source, "signalement_dit", lambda _t: None)(texte)
    return ([code] if code else []), False


async def _faits_d_un_allergene(source: Source, p: dict[str, Any], code: str, seulement: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Les faits d'UN allergène : ``allergene``, ``articles`` du panier, ``carte`` (articles de la carte concernés, donnés une fois : pas redonnés pour des lignes ajoutées après),
    ``a_confirmer_par_l_equipe``."""
    lignes, libelle = await _etat_de_l_allergene_par_ligne(source, p, code, seulement)
    carte = {} if seulement is not None else await _articles_de_la_carte_concernes(source, p, code)  # conv4 : « il y en a dans la reine ? » sans que la reine soit au panier ni dans la fiche
    if not lignes:
        libelle = await _libelle_de_l_allergene(source, p, code)
    inconnus_de_la_carte = (carte.get("carte") or {}).get("a_confirmer_par_l_equipe") or {}
    return {"allergene": libelle, "articles": lignes, **carte, "a_confirmer_par_l_equipe": any(l["etat"] == "inconnu" for l in lignes) or bool(inconnus_de_la_carte.get("noms") or inconnus_de_la_carte.get("nombre"))}


async def _libelle_de_l_allergene(source: Source, p: dict[str, Any], code: str) -> str:
    """Le mot de l'allergène dit par la source (``libelles`` du catalogue) ; le code lui-même si la source n'en dit pas."""
    lire = getattr(source, "catalogue", None)
    return ((await lire(p.get("mode") or source.modes[0])).get("libelles") or {}).get(code, code) if lire is not None else code


def _signature_de_la_ligne(ligne: dict[str, Any]) -> list[Any]:
    """Ce qui fait qu'une ligne n'est plus celle dont les faits d'allergie ont été donnés : l'article, ses choix et ses retraits."""
    return [ligne.get("ref"), ligne.get("nom"), ligne.get("choix"), sorted(ligne.get("retires") or [])]


def lignes_sans_faits_d_allergie(p: dict[str, Any]) -> list[dict[str, Any]]:
    """A2 : les lignes du panier ajoutées ou changées depuis que les faits de l'allergie ont été donnés (empreinte par ligne, ``allergie_donnee_lignes``). Rien tant que l'allergie n'a pas été donnée :
    ``allergie_a_donner`` donne alors tout le panier."""
    donnees = p.get("allergie_donnee_lignes")
    if not isinstance(donnees, dict) or p.get("allergie_donnee") != allergie_connue(p):
        return []
    return [l for l in p.get("lignes") or [] if donnees.get(str(l.get("n"))) != _signature_de_la_ligne(l)]


def allergie_a_donner(p: dict[str, Any]) -> str | None:
    """L'allergie dont les faits n'ont pas encore été donnés au modèle (``None`` : aucune, ou déjà donnés pour tout le panier). Des lignes ajoutées ou changées depuis (A2) la rouvrent."""
    allergie = allergie_connue(p)
    if not allergie:
        return None
    return allergie if p.get("allergie_donnee") != allergie or lignes_sans_faits_d_allergie(p) else None


def noter_l_allergie_donnee(p: dict[str, Any], tour: int) -> None:
    """Les faits de l'allergie viennent d'être donnés au modèle, dans ce tour, pour toutes les lignes du panier (A2 : leur empreinte est gardée) : sa phrase est dite à la fin du tour,
    l'enregistrement reste permis aux tours suivants."""
    p["allergie_donnee"], p["allergie_donnee_au_tour"] = allergie_connue(p), tour
    p["allergie_donnee_lignes"] = {str(l.get("n")): _signature_de_la_ligne(l) for l in p.get("lignes") or []}


async def faits_a_redonner_pour_les_lignes_nouvelles(source: Source, p: dict[str, Any]) -> dict[str, Any] | None:
    """A2 : pour les lignes ajoutées ou changées depuis les faits donnés, SES faits (``present`` ou ``inconnu`` pour un des allergènes dits) ; ``None`` si aucune ligne nouvelle ne demande de les redonner
    (aucune, ou toutes ``absent_de_la_fiche``, ou une allergie renvoyée au restaurant ou hors des quatorze : déjà dite « à confirmer par l'équipe »). Le code fournit et bloque, il ne parle pas."""
    nouvelles = lignes_sans_faits_d_allergie(p)
    if not nouvelles:
        return None
    faits = await faits_de_l_allergie(source, p, nouvelles)
    if not faits or faits.get("renvoye_au_restaurant"):
        return None
    par_allergene = faits.get("allergenes") or ([faits] if faits.get("allergene") is not None else [])
    if any(l.get("etat") in ("present", "inconnu") for a in par_allergene for l in a.get("articles") or []):
        return faits
    return None


async def allergie_sans_reponse(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat | None:
    """Le fait bloquant : ni relecture ni enregistrement tant que les faits de l'allergie n'ont pas été donnés au modèle dans un tour DÉJÀ FINI (critère sur l'état, jamais sur les mots).
    Si la fiche de ce tour est la première à connaître l'allergie, le retour porte ses faits et la relecture repart de zéro. A2 : une ligne ajoutée ou changée depuis, dont un allergène dit est
    ``present`` ou ``inconnu``, redonne SES faits et rebloque de la même façon. ``None`` : rien n'attend."""
    allergie = allergie_connue(p)
    if allergie is None or not p.get("lignes"):
        return None
    tour = int(p.get("tour_de_l_appel") or 0)
    faits: dict[str, Any] | None = None
    if p.get("allergie_donnee") == allergie:
        faits = await faits_a_redonner_pour_les_lignes_nouvelles(source, p)
        if faits is None:
            if lignes_sans_faits_d_allergie(p):
                noter_l_allergie_donnee(p, int(p.get("allergie_donnee_au_tour") or 0))  # lignes sans enjeu : empreinte mise à jour, rien ne bloque
            if int(p.get("allergie_donnee_au_tour") or 0) < tour:
                return None
    if faits is None:
        faits = await faits_de_l_allergie(source, p) or {}
    noter_l_allergie_donnee(p, tour)
    p["relecture"] = p["recapitulatif_approuve"] = p["derniere_lecture"] = None
    p["relecture_acceptee"] = False
    return _avec(_r("INCOMPLETE", {**faits, "raison": RAISON_ALLERGIE}, ""), p)


async def _regles_d_information(source: Source) -> dict[str, Any]:
    """Lot 15 : ce que l'établissement a écrit (consigne d'allergie, halal, renvoi vers le restaurant) ; vide pour une source qui n'en a pas."""
    lire = getattr(source, "regles_d_information", None)
    return dict(await lire()) if lire is not None else {}


def _consigne_d_allergie(info: dict[str, Any]) -> dict[str, Any]:
    """INF6 : la consigne d'allergie du restaurant, un fait que l'agent répète (jamais inventée)."""
    consigne = inf6.brique_inf6_repeter_et_noter(info.get("consigne_allergie"), None)["consigne"]
    return {"consigne_du_restaurant": consigne} if consigne else {}


def _informations_de_la_fiche(fiche: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    """Ce que la donnée de l'article dit en plus, pour la lecture : régimes étiquetés (INF3), halal du restaurant (INF4), épice (INF5), nutrition et degré (INF7). Seul ce qui est écrit."""
    faits: dict[str, Any] = {}
    if fiche.get("regimes"):
        faits["regimes"] = [inf3.LIBELLES.get(r, r) for r in fiche["regimes"]]
    if inf4.brique_inf4_dire_ce_qui_est_ecrit(fiche.get("regimes"), bool(info.get("halal_restaurant")))["restaurant"]:
        faits["restaurant_halal"] = True
    epice = inf5.brique_inf5_depuis_le_texte(fiche.get("epice"))
    if epice:
        faits["epice"] = epice
    nutrition = inf7.brique_inf7_depuis_la_donnee(fiche.get("nutrition"), fiche.get("degre"))
    if nutrition:
        faits["nutrition"] = nutrition
    return faits


def _regime_dit(source: Source, fiche: dict[str, Any], regime: str, info: dict[str, Any]) -> Resultat:
    """La réponse sur UN régime pour UN article : seulement ce qui est écrit (étiquette de l'article, case du restaurant pour le halal), sinon « je ne peux pas vous garantir »."""
    nom = fiche["nom"]
    code = getattr(source, "regime_code", lambda _t: None)(regime)
    if code == inf4.CODE:
        ecrit = inf4.brique_inf4_dire_ce_qui_est_ecrit(fiche.get("regimes"), bool(info.get("halal_restaurant")))
        if ecrit["article"]:
            return _r("OK", {"article": nom, "regime": regime, "etiquete": True}, f"D'après la fiche, {nom} est {regime}.")
        if ecrit["restaurant"]:
            return _r("OK", {"article": nom, "regime": regime, "etiquete": False, "restaurant": True}, f"D'après la fiche du restaurant, la carte est {regime}.")
    elif code and inf3.brique_inf3_jamais_sans_etiquette(fiche.get("regimes"), code) == "etiquete":
        return _r("OK", {"article": nom, "regime": regime, "etiquete": True}, f"D'après la fiche, {nom} est {regime}.")
    return _r("OK", {"article": nom, "regime": regime, "renseigne": False}, f"Je ne peux pas vous garantir ce qui est {regime} : {_PAS_SUR}")


async def _regime_du_catalogue(source: Source, p: dict[str, Any], regime: str) -> Resultat:
    """INF3, INF4 : « du végétarien ? », « c'est halal ? » sans article : seulement les articles ÉTIQUETÉS (et la case halal du restaurant) ; sans étiquette, rien n'est garanti."""
    faits: dict[str, Any] = {"recherche": "sans", "regime": regime, "renseigne": False}
    code = getattr(source, "regime_code", lambda _t: None)(regime)
    info = await _regles_d_information(source)
    etiquetes: list[str] = []
    lire = getattr(source, "catalogue", None)
    if code and lire is not None:
        etiquetes = inf3.articles_etiquetes((await lire(p.get("mode") or source.modes[0])).get("articles") or [], code)
    restaurant = code == inf4.CODE and bool(info.get("halal_restaurant"))
    if etiquetes:
        dits = etiquetes[:_PLUS_DE_NOMS]
        entre_autres = ", entre autres," if len(etiquetes) > len(dits) else ""
        verbe = "est" if len(etiquetes) == 1 else "sont"
        return _r("OK", {**faits, "renseigne": True, "articles": etiquetes, **({"restaurant": True} if restaurant else {})},
                  f"D'après la fiche, {liste_dite_et(dits)}{entre_autres} {verbe} {regime}. Pour les autres, je ne peux pas le garantir.")
    if restaurant:
        return _r("OK", {**faits, "renseigne": True, "restaurant": True}, f"D'après la fiche du restaurant, la carte est {regime}.")
    return _r("OK", faits, f"Je ne peux pas vous garantir ce qui est {regime} : {_PAS_SUR}")


def _lecture_de_la_formule(fiche: dict[str, Any]) -> Resultat:
    """Lot 11 (conversations FOR7, FOR9, FOR10) : la lecture d'une formule rend ses étapes et ses choix, ses règles, et son prix, que le code dit lui-même
    (``prix_a_dire``, comme PRX5) ; jamais « je ne peux pas le confirmer » pour une formule de la carte."""
    lu = FO.lecture_de_la_formule(fiche)
    faits: dict[str, Any] = {"article": fiche["nom"], "renseigne": True, **lu}
    if lu.get("prix"):
        debut = "à partir de " if lu["prix"]["a_partir_de"] else "à "
        faits["prix_a_dire"] = f"{_le(fiche['nom'], fiche.get('genre'))} est {debut}{montant_en_lettres(lu['prix']['montant'])}."
    au_choix = "; ".join(f"{e['etape']} : {liste_dite(e['choix'])}" for e in lu["etapes"] if e["choix"])
    return _r("OK", faits, f"{fiche['nom']}. {au_choix}." if au_choix else fiche["nom"] + ".")


def _faits_du_prix(fiche: dict[str, Any]) -> dict[str, Any]:
    """Lot 12 (PRX5, D33) : le prix de l'article à la lecture (``prix`` : ``montant`` et ``a_partir_de``) et la phrase que le code dit lui-même (``prix_a_dire``, jamais montrée au
    modèle : ``lire`` la range dans les textes du code). Un article sans prix lisible n'en rend aucun."""
    prix = prx5.brique_prx5_jamais_le_prix_de_depart_comme_final(fiche)
    if prix is None:
        return {}
    debut = "à partir de " if prix["a_partir_de"] else "à "
    # Le nombre du nom (« les frites ») n'est connu nulle part, le genre par défaut est masculin : jamais d'article deviné (conversation PRX5-A : « Le Frites est »), le nom seul
    sujet = f"Pour {fiche['nom']}, c'est"
    return {"prix": prix, "prix_a_dire": f"{sujet} {debut}{montant_en_lettres(prix['montant'])}."}


_NON_GARANTI = "je ne peux pas le garantir : l'équipe peut vous le confirmer."


def _option_signale(o: dict, code: str) -> bool | None:
    """``True`` : l'option porte ``code`` (sa donnée ou son nom le dit) ; ``False`` : sa donnée dit que non ; ``None`` : on ne sait pas."""
    if code in (o.get("signalements_du_nom") or []) or any(s["code"] == code for s in (o.get("signalements") or [])):
        return True
    return False if o.get("signalements") is not None else None


def _options_obligatoires(fiche: dict) -> list[dict]:
    """Les options des choix sans lesquels l'article ne se commande pas (au moins un à prendre)."""
    return [o for _, g in _groupes_a_remplir(fiche, {"choix": []}) if g["min"] >= 1 for o in g["options"] if o["vendable"]]


_LA_LISTE = re.compile(r"(?<!\w)(?:allerg[eè]nes?|allergies?|signalements?|ingr[ée]dients?)(?!\w)", re.IGNORECASE)


def _est_la_liste_demandee(signale: str) -> bool:
    """A4 : le modèle demande LA liste (« allergènes ») et non une chose précise ; seule la liste se lit sans code."""
    return bool(_LA_LISTE.search(signale or ""))


def _signalement_dit(source: Source, fiche: dict, option: dict | None, signale: str) -> Resultat:
    """La réponse sur UN signalement (ou la liste), l'option dite ou les choix obligatoires compris (M88)."""
    nom = fiche["nom"]
    signalements = fiche.get("signalements")
    libelles = fiche.get("signalements_libelles") or {}
    faits: dict[str, Any] = {"article": nom, **({"option": option["nom"]} if option else {})}
    nom_dit = f"{nom} {option['nom']}" if option else nom
    options = [option] if option else _options_obligatoires(fiche)
    code = source.signalement_dit(signale)
    if code is None and not _est_la_liste_demandee(signale):
        # A4 : une chose hors des quatorze (ail, kiwi, fraise) n'est jamais déclarée : « n'en déclare aucun » sonnerait comme un non
        return _r("OK", {**faits, "signalement": "inconnu"}, "Pour cette chose, " + _NON_GARANTI)
    if code is None:
        if signalements is None:
            return _r("OK", {**faits, "signalement": "inconnu"}, NON_CONFIRMABLE)
        codes = [s["code"] for s in signalements]
        for o in options if option else []:
            codes += [c for c in (o.get("signalements_du_nom") or []) + [s["code"] for s in (o.get("signalements") or [])] if c not in codes]
        presents = [libelles.get(c, c) for c in codes]
        phrase = f"D'après la fiche, {nom_dit} contient {liste_dite_et(presents)}." if presents else f"D'après la fiche, {nom_dit} n'en déclare aucun."
        if any(o.get("signalements") is None for o in options):
            phrase += " Selon le choix, " + _NON_GARANTI if not option else f" Pour {option['nom']}, " + _NON_GARANTI
        return _r("OK", {**faits, "signalement": "liste", "presents": presents}, phrase)
    libelle = libelles.get(code, code)
    faits["code"] = code
    if signalements is not None and any(s["code"] == code for s in signalements):
        return _r("OK", {**faits, "signalement": "present"}, f"Oui, {nom_dit} contient {libelle}.")
    if option is not None:
        # Lot 15 (INF2) : le produit et l'option choisie ensemble
        option_vue = {"allergenes": None if option.get("signalements") is None else [s["code"] for s in option["signalements"]], "signalements_du_nom": option.get("signalements_du_nom")}
        etat = inf2.brique_inf2_produit_et_options(None if signalements is None else [s["code"] for s in signalements], [option_vue], code)
        if etat == "present":
            return _r("OK", {**faits, "signalement": "present"}, f"Oui, {nom_dit} contient {libelle}.")
        if etat == "absent_de_la_fiche":
            return _r("OK", {**faits, "signalement": "absent_de_la_fiche"}, f"D'après la fiche, {nom_dit} ne contient pas {libelle}.")
        return _r("OK", {**faits, "signalement": "inconnu"}, f"Pour {nom_dit}, " + _NON_GARANTI)
    contiennent = [o["nom"] for o in options if _option_signale(o, code)]
    inconnues = [o for o in options if _option_signale(o, code) is None]
    if contiennent:
        suite = " Pour les autres, " + _NON_GARANTI if inconnues or signalements is None else " Pour les autres, d'après la fiche, non."
        return _r("OK", {**faits, "signalement": "selon_option", "options_qui_contiennent": contiennent}, f"Ça dépend : avec {liste_dite(contiennent)}, oui." + suite)
    if signalements is None:
        return _r("OK", {**faits, "signalement": "inconnu"}, NON_CONFIRMABLE)
    if inconnues:
        return _r("OK", {**faits, "signalement": "inconnu"}, "Ça dépend du choix, et " + _NON_GARANTI)
    return _r("OK", {**faits, "signalement": "absent_de_la_fiche"}, f"D'après la fiche, {nom} ne contient pas {libelle}.")


# --------------------------------------------------------------------------- #
# retrouver_commande : où en est une commande déjà passée (lot 7, E-15, E-36)
# --------------------------------------------------------------------------- #

_PERDUES = frozenset({"refusee", "echec"})


async def retrouver_commande(source: Source, p: dict[str, Any], regles: Reglages, appelant: "Appelant", numero: str | None = None) -> Resultat:
    """Retrouve une commande du jour : par son numéro (``numero``, court ou long), sinon par le numéro qui s'affiche. Le statut est LU dans le classeur,
    jamais deviné. À l'appelant on ne dit que « enregistrée » et l'heure (E-36) : les étapes de la préparation servent le suivi, pas l'appel. Une commande
    annulée ou qui n'est pas passée est dite telle quelle ; plusieurs commandes : on demande laquelle. Aucune plainte ici : le passage de main est celui de l'équipe."""
    if numero and numero.strip():
        trouve = await source.retrouver(numero=numero.strip())
    elif appelant.telephone_affiche:
        trouve = await source.retrouver(telephone=appelant.telephone_affiche)
    else:
        return _avec(_r("INCOMPLETE", {}, "Quel est le numéro de la commande ?", "reference"), p)
    if trouve.statut != "OK":
        return _avec(_r("INTROUVABLE", {}, "Je ne trouve pas de commande, ni aujourd'hui ni sous ce numéro."), p)
    commandes = trouve.faits.get("commandes") or []
    if len(commandes) > 1:
        dites = [f"la {c['numero_court']}" + (f" pour {c['quand_dit']}" if c.get("quand_dit") else "") for c in commandes]
        return _avec(
            _r("AMBIGU", {"candidats": [{"numero_court": c["numero_court"], "quand_dit": c.get("quand_dit")} for c in commandes]}, "Vous en avez plusieurs : " + liste_dite(dites) + ". Laquelle ?", "reference"),
            p,
        )
    c = commandes[0]
    faits = {"numero_court": c["numero_court"], "statut": c["statut"], "mode": c["mode"], "quand_dit": c.get("quand_dit")}
    if c["statut"] == "annulee":
        phrase = "Cette commande est annulée."
    elif c["statut"] in _PERDUES:
        phrase = "Cette commande n'est pas passée à la préparation : je laisse un message à l'équipe qui vous rappelle."
    else:
        phrase = "Votre commande est enregistrée" + (f" pour {c['quand_dit']}." if c.get("quand_dit") else ".")
    return _avec(_r("OK", faits, phrase), p)


# --------------------------------------------------------------------------- #
# envoyer_un_message : un message demandé par l'appelant (lot 7, E-18)
# --------------------------------------------------------------------------- #


async def envoyer_un_message(source: Source, p: dict[str, Any], regles: Reglages, appelant: "Appelant", quoi: str | None, organisation: int | None) -> Resultat:
    """Envoie à l'appelant le message qu'il demande (par le numéro qui s'affiche, jamais un numéro dicté) : le TEXTE est celui que l'établissement a écrit, le
    modèle n'écrit rien. Éteint par défaut : ``INDISPONIBLE`` avec la phrase, rien ne part. Une seule fois par appel et par sorte de message."""
    if not quoi:
        return _r("ARGUMENT_INVALIDE", {}, "Quel message voulez-vous recevoir ?", "quoi")
    quoi = quoi.strip().casefold()
    cle = f"{appelant.appel_id or 'sans-appel'}:{quoi}:{appelant.telephone_affiche or ''}"
    return _avec(await source.envoyer(quoi, appelant.telephone_affiche, cle, organisation), p)
