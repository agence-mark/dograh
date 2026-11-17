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
import hashlib
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
from api.services.mots_dits import chiffres_en_lettres, liste_dite, liste_dite_et, montant_en_lettres, nom_dit, nombre_en_lettres, phrase_nette
from api.services.commande.resultat import Resultat, avec_numero_affiche, avec_numeros_retenus
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS as MOTIFS_DES_PHRASES, NUMERO_AFFICHE_GARDE
from api.services.commande.source import Source

LONGUEUR_NOTE = 200
_PETITS_MOTS = frozenset({"la", "le", "les", "l", "de", "du", "des", "un", "une", "ligne", "celle", "celui", "ci"})


@dataclass(frozen=True)
class Reglages:
    """Les réglages de construction du module (registre des modules), lus dans la configuration de l'agent."""

    ordre_impose: bool = True  # la zone avant les articles quand le mode en exige une (W6)
    relecture_en_deux_temps: bool = True
    vente_en_plus: bool = True
    notes_libres: bool = True  # E-35 : « bien cuite », « sauce à part » : une note de ligne, sans prix
    regle_moities: str = "plus_chere"
    mentions_de_remise: int = 1  # T-08 : combien de fois par appel l'agent parle d'une remise de lui-même (0 : seulement sur demande)
    # M98 : la question qui finit la relecture quand le numéro qui s'affiche est gardé (phrase du code réglable, lue par l'action à l'endroit de
    # l'appel) ; ``None`` ou vide : la relecture finit par « C'est bon ? ».
    question_numero_affiche: str | None = MOTIFS_DES_PHRASES[NUMERO_AFFICHE_GARDE].variantes_defaut[0]
    # M108 : la question qui finit la confirmation d'une commande enregistrée (phrase du code réglable, lue par l'action à l'endroit de l'appel) ;
    # ``None`` ou vide : la confirmation est dite seule.
    question_apres_enregistrement: str | None = MOTIFS_DES_PHRASES[APRES_ENREGISTREMENT].variantes_defaut[0]
    # M118 : la surcouche de l'agent sur la table standard des mots de taille (``tailles.py``) : ``{mot: rang}``, ``None`` retire un mot.
    mots_de_taille: dict[str, Any] | None = None

    def pour_la_source(self) -> dict[str, Any]:
        return {"regle_moities": self.regle_moities}


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
            sortie.append((chemin, g))
            for o in g["options"]:
                deja = next((c for c in choisis if c["option_code"] == o["code"]), None)
                if deja is not None and o["enfants"]:
                    descendre(o["enfants"], chemin + (o["code"],), deja["choix"])

    descendre(article["groupes"], (), ligne["choix"])
    return sortie


def _niveau(choix: list[dict], chemin: tuple[str, ...]) -> list[dict]:
    courant = choix
    for code in chemin:
        courant = next(c for c in courant if c["option_code"] == code)["choix"]
    return courant


def _compte(ligne: dict, chemin: tuple[str, ...], groupe: dict) -> int:
    codes = {o["code"] for o in groupe["options"]}
    return sum(c["quantite"] for c in _niveau(ligne["choix"], chemin) if c["option_code"] in codes)


def _question(article: dict, ligne: dict) -> dict | None:
    """La première question encore ouverte pour cette ligne : la déclinaison, puis chaque choix obligatoire. ``None`` : la ligne est complète."""
    if not ligne.get("code"):
        noms = [d["nom"] for d in article["declinaisons"] if d["vendable"] and not d["rupture"]]
        return {"type": "declinaison", "nom": "taille", "min": 1, "max": 1, "chemin": [], "options": noms}
    for chemin, g in _groupes_a_remplir(article, ligne):
        if _compte(ligne, chemin, g) < g["min"]:
            return {
                "type": "groupe", "groupe": g["id"], "nom": g["nom"], "min": g["min"], "max": g["max"], "chemin": list(chemin),
                "options": [o["nom"] for o in g["options"] if o["vendable"] and not o["rupture"]],
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
        return f"Quelle taille pour votre {article_nom} : {options} ?"
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
            for o in g["options"]:
                if o["par_defaut"] and o["vendable"] and not o["rupture"] and _compte(ligne, chemin, g) < g["max"]:
                    _niveau(ligne["choix"], chemin).append({"option_code": o["code"], "nom": o["nom"], "quantite": 1, "choix": []})


def _choisir(ligne: dict, chemin: tuple[str, ...], groupe: dict, option: dict, quantite: int) -> Resultat | None:
    """Pose ``quantite`` de cette option. Un choix unique (obligatoire, un seul) est REMPLACÉ (changement d'avis) ; sinon les maximums du
    groupe et de l'option sont respectés. ``None`` : posé."""
    if option["rupture"]:
        return _r("RUPTURE", {"nom": option["nom"], "code": option["code"]}, f"{option['nom']} n'est plus disponible.")
    niveau = _niveau(ligne["choix"], chemin)
    codes = {o["code"] for o in groupe["options"]}
    if groupe["max"] == 1 and groupe["min"] >= 1:
        niveau[:] = [c for c in niveau if c["option_code"] not in codes]
        niveau.append({"option_code": option["code"], "nom": option["nom"], "quantite": 1, "choix": []})
        return None
    existant = next((c for c in niveau if c["option_code"] == option["code"]), None)
    total_groupe = _compte(ligne, chemin, groupe)
    nouvelle = (existant["quantite"] if existant else 0) + quantite
    if total_groupe + quantite > groupe["max"] or nouvelle > groupe["max_par_option"]:
        return _r(
            "MAXIMUM_ATTEINT", {"groupe": groupe["nom"], "option": option["nom"], "maximum": groupe["max"], "maximum_par_option": groupe["max_par_option"]},
            f"On ne peut pas en prendre davantage : {groupe['nom']}.",
        )
    if existant:
        existant["quantite"] = nouvelle
    else:
        niveau.append({"option_code": option["code"], "nom": option["nom"], "quantite": quantite, "choix": []})
    return None


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


def _appliquer_les_choix(article: dict, ligne: dict, texte: str, *, roles: tuple[str, ...] | None = None, dans: str | None = None) -> Resultat | None:
    """Les choix dits (« sauce barbecue et double fromage ») cherchés DANS les groupes de l'article : jamais ailleurs. ``dans`` : un
    groupe d'abord (la question ouverte). Rend un refus fermé ou ``None`` quand tout est posé."""
    for quantite, morceau, brut in lecture.morceaux_d_options(texte):
        index = _options_disponibles(article, ligne, roles)
        if not index:
            return _r("HORS_CARTE", {"article": ligne["nom"], "raison": "aucun_choix"}, f"{ligne['nom']} ne se prend pas avec des choix.")
        elements = [Element(cle, o["nom"], tuple(o.get("synonymes") or ()), g["nom"]) for cle, (_, g, o) in index.items()]
        trouve = None
        if brut != morceau:
            # « 4 saisons » : le nombre est peut-être le début d'un NOM. Le texte tel que dit est pris s'il est certain.
            entier = _chercher_dans(elements, brut)
            if _est_le_nom(entier, brut):
                trouve, quantite, morceau = entier, 1, brut
        if trouve is None and dans:
            restreint = [e for e in elements if index[e.id][1]["id"] == dans]
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
            return _r("AMBIGU", {"candidats": noms, "dit": morceau}, "Vous voulez dire : " + liste_dite(noms) + " ?")
        if trouve["statut"] != "RETENU":
            proches = [index[c["id"]][2] for c in trouve["candidats"] if c["id"] in index]
            suppl = [o for c in trouve["candidats"] if c["id"] in index for o in [index[c["id"]][2]] if index[c["id"]][1]["role"] == "supplement"]
            propose = suppl or proches
            return _r(
                "HORS_CARTE",
                {"article": ligne["nom"], "dit": morceau, "plus_proches": [{"nom": o["nom"], "prix": o["prix"]} for o in propose[:3]]},
                f"Je n'ai pas « {morceau} » pour {ligne['nom']}."
                + (f" Le plus proche : {liste_dite([o['nom'] for o in propose[:3]])}." if propose else ""),
            )
        chemin, g, o = index[trouve["retenu"]]
        refus = _choisir(ligne, chemin, g, o, quantite)
        if refus is not None:
            return refus
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


def _appliquer_les_retraits(article: dict, ligne: dict, texte: str) -> Resultat | None:
    retirables = article["retirables"]
    # SA-22 : une ligne en deux moitiés : le retrait devient une note de ligne (voir ``_noter_un_retrait_par_moitie``).
    moities = _moities_choisies(article, ligne)
    if len(moities) >= 2:
        return _noter_un_retrait_par_moitie(ligne, texte, moities)
    for _, morceau, _brut in lecture.morceaux_d_options(texte):
        if not retirables:
            return _r("HORS_CARTE", {"article": ligne["nom"], "raison": "rien_a_retirer"}, f"On ne peut rien retirer dans {ligne['nom']}.")
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


# --------------------------------------------------------------------------- #
# Préalables : le mode, la zone
# --------------------------------------------------------------------------- #


def _phrase_des_modes(source: Source) -> str:
    return liste_dite([source.libelles_des_modes.get(m, m) for m in source.modes])


async def _prealables(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat | None:
    if not p["mode"]:
        return _avec(_r("INCOMPLETE", {"modes": list(source.modes)}, f"{_phrase_des_modes(source).capitalize()} ?", "mode"), p)
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
    return await source.chiffrer(p["mode"], lignes, _zone_id(p), {**regles.pour_la_source(), "client": {"telephone": telephone} if telephone else None})


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


async def heure_du_lieu(source: Source, texte: str | None, etat: dict[str, Any] | None = None) -> Resultat | None:
    """M74 (appels 2562, 2563) : l'heure qu'un modèle passe à un outil n'est pas toujours celle rendue par la résolution de la date. Mécanisme
    commun à toute heure voulue, sans mot de métier : un instant précis (ISO avec fuseau) est gardé tel quel ; une date-heure ISO sans fuseau
    (« 2026-11-17T12:00:00 ») ou des mots (« demain midi ») sont résolus par le CODE au fuseau du lieu (``source.resoudre_une_date``), jamais
    devinés. Rend ``RETENU`` avec ``faits.heure_voulue`` (aware), ou le résultat de la résolution (doute, heure manquante) à dire ; ``None`` sans texte."""
    t = (texte or "").strip()
    if not t:
        return None
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


async def garder_l_heure(source: Source, p: dict[str, Any], texte: str | None) -> None:
    """D15 : une heure voulue dite dès le premier tour (« pour ce soir 19 h ») est GARDÉE jusqu'à ``finaliser``, résolue par le code (M74).
    Une heure qui ne se résout pas sûrement est ignorée : la question de l'heure se posera à ``finaliser``."""
    r = await heure_du_lieu(source, texte, p)
    if r is not None and r.statut == "RETENU" and r.faits.get("heure_voulue"):
        p["heure_voulue"] = r.faits["heure_voulue"]


async def choisir_mode(source: Source, p: dict[str, Any], regles: Reglages, mode: str | None, heure_voulue: str | None = None) -> Resultat:
    """Pose le mode de la commande (les modes sont ceux de la source). Les articles déjà pris sont GARDÉS : on les rechiffre pour
    le nouveau mode, et on dit ceux qui n'y tiennent plus. Un mode fermé n'est jamais posé : la raison fermée est rendue, SAUF quand le réglage
    du type permet de commander pour plus tard (D15) : le mode est posé, la commande est « à planifier » (``FERME_PLANIFIABLE``)."""
    choisi = _mode_dit(source, mode)
    if choisi is None:
        return _r("ARGUMENT_INVALIDE", {"modes": list(source.modes)}, f"{_phrase_des_modes(source).capitalize()} ?", "mode")
    etat = await source.etat(choisi)
    a_planifier = not etat["ouvert"] and bool(etat.get("planifiee_permise"))
    if not etat["ouvert"] and not a_planifier:
        return _avec(
            _r(etat["statut"], {"mode": choisi, **{k: etat.get(k) for k in ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")}}, etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."),
            p,
        )
    await garder_l_heure(source, p, heure_voulue)
    r = await _poser_le_mode(source, p, regles, choisi, a_planifier)
    if not a_planifier or r.statut != "OK":
        return r
    # Fermé mais planifiable : le résultat dit la fermeture et propose le créneau ; la question en cours (zone, articles) suit, sinon l'heure.
    fermeture = etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."
    dire = getattr(source, "quand_dit", None)
    if p.get("heure_voulue") and dire:
        # Appel 2566 : l'heure est déjà dite et gardée, c'est déjà l'accord pour plus tard ; la proposition de « plus tard » n'est pas refaite (le modèle la
        # tournait en « est-ce que cela vous convient ? »). Le résultat dit pour quand la commande est prise ; le créneau se vérifie à ``finaliser``.
        fermeture = f"Commande pour {await dire(datetime.fromisoformat(p['heure_voulue']))}."
    faits = {**r.faits, **{k: etat.get(k) for k in ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")}, "a_planifier": True, "fermeture": fermeture}
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
        return _avec(_r("OK", faits, "Qu'est-ce que je vous mets ?", "articles"), p)
    return _avec(_r("OK", faits, ""), p)


# --------------------------------------------------------------------------- #
# Lot 6 : l'ouverture, l'heure annoncée, l'adresse, la date
# --------------------------------------------------------------------------- #

CLES_DE_L_ETAT = ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")


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


async def verifier_adresse(source: Source, p: dict[str, Any], regles: Reglages, adresse: str | None) -> Resultat:
    """Situe l'adresse dite dans les zones de la source. ``RETENU`` : la zone et l'adresse sont posées sur la commande (et le panier rechiffré avec les
    frais et le minimum de la zone). Un doute (``AMBIGU``, ``INTROUVABLE``) ne pose rien et rend les candidats à confirmer ; ``HORS_ZONE`` vide la zone
    et l'adresse déjà posées (jamais l'ancienne zone pour une nouvelle adresse)."""
    texte = (adresse or "").strip()
    if not texte:
        return _avec(_r("ARGUMENT_INVALIDE", {}, source.question_de_la_zone, "adresse"), p)
    r = await source.verifier_adresse(texte)
    essai = copy.deepcopy(p)
    if r.statut == "RETENU":
        zone = r.faits["zone"]
        essai["zone"], essai["adresse"] = {"id": zone["id"], "nom": zone["nom"]}, texte
    elif r.statut in ("HORS_ZONE", "AMBIGU", "INTROUVABLE") and (essai.get("zone") or essai.get("adresse")):
        essai["zone"] = essai["adresse"] = None  # une adresse en doute ou hors zone ne laisse jamais l'ancienne zone en place
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
    if r.statut == "RETENU" and not p.get("mode"):
        # SA-52 (appel 2602) : une adresse vérifiée sans mode posé dit le mode : celui (le seul) qui exige une adresse, s'il est offert.
        # Posé comme ``choisir_mode`` le pose (ouverture vérifiée, ce qui était gardé est pris) ; un mode fermé ne pose rien.
        avec_adresse = [m for m in source.modes if source.exige_une_zone(m)]
        if len(avec_adresse) == 1:
            pose = await choisir_mode(source, p, regles, avec_adresse[0])
            if pose.statut in ("OK", "FERME_PLANIFIABLE") or p.get("mode"):
                return _avec(Resultat(pose.statut if pose.statut != "OK" else r.statut, {**faits, **pose.faits}, " ".join(t for t in (r.suggestion, pose.suggestion) if t), pose.manque), p)
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
            return _avec(Resultat(r.statut, faits, (r.suggestion + " Qu'est-ce que je vous mets ?").strip(), "articles"), p)
    return _avec(Resultat(r.statut, faits, r.suggestion, r.manque), p)


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
        if (autre["code"], autre["choix"], sorted(autre["retires"]), autre.get("note")) == (ligne["code"], ligne["choix"], sorted(ligne["retires"]), ligne.get("note")):
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


def _remplacer_l_attente(p: dict[str, Any], ligne: dict[str, Any], en_attente_avant: set[str] | None) -> None:
    """C3 : un article redit alors que sa ligne attendait encore une réponse (taille, choix) REMPLACE cette ligne : jamais deux lignes en
    attente pour le même article. Seules les lignes en attente d'avant l'appel d'``ajouter`` comptent (« deux fois le même » dans une même
    phrase restent deux lignes) ; chacune n'est remplacée qu'une fois."""
    if not en_attente_avant or ligne["ref"] not in en_attente_avant:
        return
    p["lignes"] = [l for l in p["lignes"] if not (l.get("attente") and l["ref"] == ligne["ref"])]
    en_attente_avant.discard(ligne["ref"])


async def _moities_separees(source: Source, dit: str) -> str:
    """« A B » (deux moitiés dites sans séparateur) : le seul découpage dont les deux parts sont chacune un article certain.
    Aucun découpage sûr (ou une séparation déjà dite) : le texte tel quel, la résolution des moitiés tranche."""
    mots = dit.split()
    if len(mots) < 2 or re.search(r"[,;]", dit):
        return dit
    sures = []
    for i in range(1, len(mots)):
        a, b = " ".join(mots[:i]), " ".join(mots[i:])
        if (await source.chercher(a)).statut == "RETENU" and (await source.chercher(b)).statut == "RETENU":
            sures.append(f"{a}, {b}")
    return sures[0] if len(sures) == 1 else dit


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
    """L'option de l'article que ``texte`` nomme sans doute (« pistache » dans le groupe des parfums), cherchée comme ``ajouter`` la cherche ;
    ``None`` : aucune option certaine."""
    index = _options_disponibles(article, {"choix": []})
    if not index:
        return None
    trouve = _chercher_dans([Element(cle, o["nom"], tuple(o.get("synonymes") or ()), g["nom"]) for cle, (_, g, o) in index.items()], texte)
    return index[trouve["retenu"]][2] if trouve["statut"] == "RETENU" else None


def _rang(r: Resultat) -> int:
    return {"RETENU": 2, "AMBIGU": 1}.get(r.statut, 0)


async def _chercher_l_article(source: Source, texte: str, regles: Reglages) -> Resultat:
    """M117 (appel 2598) : l'article d'un morceau. Le texte entier d'abord ; s'il n'est pas certain et qu'il porte des mots de taille usuels
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
    dit = f" {recherche_liste.normaliser(texte)} "
    du_nom = frozenset(recherche_liste.normaliser(article["nom"]).split())
    par_nom = []
    for d in declinaisons:
        nom = recherche_liste.normaliser(d["nom"])
        if nom and f" {nom} " in dit and not set(nom.split()) <= du_nom:
            par_nom.append(d)
    if par_nom:
        return par_nom[0] if len(par_nom) == 1 else None
    return tailles.declinaison_par_mot(declinaisons, texte, regles.mots_de_taille, hors=du_nom)


def _declinaison_choisie(article: dict, choix: str, regles: Reglages) -> dict | None:
    """La réponse à « quelle taille ? » : le nom d'une déclinaison (cherché comme toujours), sinon un mot de taille usuel (M118)."""
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


def _sans_la_taille(article: dict, choix: str, dite: dict, regles: Reglages) -> str | None:
    """SA-55 : les morceaux du choix qui ne disent QUE la taille ``dite`` sont retirés ; le reste (un supplément, une sauce) est rendu tel que
    dit, ``None`` s'il ne reste rien. Un morceau qui nomme une option (une option dont le nom porte le mot de la taille) est gardé."""
    gardes = [
        m.brut
        for m in lecture.morceaux_d_options(choix)
        if (_declinaison_choisie(article, m.texte, regles) or {}).get("code") != dite["code"] or _option_dite(article, m.texte) is not None
    ]
    return ", ".join(gardes) or None


async def _departager_par_la_taille(source: Source, p: dict[str, Any], trouve: Resultat, textes: list[str | None], regles: Reglages) -> Resultat | None:
    """M120 (appel 2598) : deux articles du même nom et une taille dite (« quatre fromages normale ») : seul celui qui a cette taille reste.
    Plus d'un, ou aucun : ``None``, le doute reste une question."""
    candidats = trouve.faits.get("candidats") or []
    if trouve.statut != "AMBIGU" or len(candidats) < 2 or not any(t for t in textes):
        return None
    gardes = []
    for c in candidats:
        article = await source.article(c["id"], p["mode"])
        if article is not None and any(_taille_dans(article, t, regles) for t in textes if t):
            gardes.append(c)
    if len(gardes) != 1:
        return None
    return Resultat("RETENU", {**trouve.faits, "retenu": gardes[0]["id"], "candidats": gardes}, "")


# SA-52 (appel 2604) : le choix dit avec un article encore en doute (« un X, option A » : lequel ?) est GARDÉ, comme les articles
# gardés jusqu'au mode (M116) ; il est posé sur la prochaine ligne créée si son article est un des candidats proposés, jamais ailleurs.
CLE_CHOIX_EN_SUSPENS = "choix_en_suspens"


def _poser_le_suspens(p: dict[str, Any], article: dict, ligne: dict) -> None:
    """Le choix gardé, posé sur ``ligne`` quand son article est un des candidats ; tout ou rien (un choix qui ne va pas à cet article n'empêche
    jamais l'ajout). Consommé par la première ligne créée, qu'il s'y pose ou non."""
    suspens = p.pop(CLE_CHOIX_EN_SUSPENS, None)
    if not suspens or article["nom"] not in (suspens.get("candidats") or []):
        return
    essai = copy.deepcopy(ligne)
    if suspens.get("choix"):
        if essai["code"]:
            if _appliquer_les_choix(article, essai, suspens["choix"]) is not None:
                return
        else:
            essai["choix_a_poser"] = (essai.get("choix_a_poser") or []) + [suspens["choix"]]
    if suspens.get("sans") and _appliquer_les_retraits(article, essai, suspens["sans"]) is not None:
        return
    ligne.clear()
    ligne.update(essai)


async def _un_article(
    source: Source, p: dict[str, Any], regles: Reglages, quantite: int, texte: str, *, choix: str | None, sans: str | None, note: str | None,
    moities: str | None, tout_seul: bool, brut: str | None = None, en_attente_avant: set[str] | None = None,
    retraits_dits: str | None = None, choix_dits: str | None = None,
) -> Resultat:
    """Un morceau de la phrase : le cherche, compose sa ligne, la complète ou en garde la question, la chiffre. Rien n'est posé sur un refus."""
    trouve = None
    if brut and brut != texte:
        # « 4 saisons » : le nombre de tête est peut-être le début d'un NOM. Le texte tel que dit est pris s'il est certain (zéro faux sûr).
        entier = await source.chercher(brut)
        if _est_le_nom({"statut": entier.statut, "candidats": entier.faits.get("candidats")}, brut):
            trouve, quantite, texte = entier, 1, brut
    if quantite > lecture.QUANTITE_MAX:
        return _r("ARGUMENT_INVALIDE", {"quantite": quantite}, f"{quantite}, c'est beaucoup : je vous mets combien exactement ?", "quantite")
    dit_entier = brut or texte  # M118 : la taille dite se lit dans tout le morceau (« deux reines grandes taille »)
    if trouve is None:
        trouve = await _chercher_l_article(source, texte, regles)
    trouve, dit_en_plus = await _un_seul_candidat(source, trouve, texte)
    departage = await _departager_par_la_taille(source, p, trouve, [dit_entier, choix if tout_seul else None], regles)
    if departage is not None:
        trouve = departage
    if dit_en_plus and not moities:
        choix = f"{choix}, {dit_en_plus}" if choix else dit_en_plus
        tout_seul = True  # un choix né du nom dit n'est pas un choix de la phrase entière
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
    article = await source.article(trouve.faits["retenu"], p["mode"])
    if article is None:
        return _r("INTROUVABLE", {"dit": texte}, f"« {texte} » n'est pas disponible en ce moment.")
    declinaison = _declinaison_dite(article, trouve.faits) or _taille_dans(article, dit_entier, regles)
    ligne: dict[str, Any] = {
        "n": 0, "ref": article["id"], "nom": article["nom"], "code": None, "quantite": quantite, "choix": [], "retires": [], "note": None,
        "attente": None, "declinaison_dite": ((trouve.faits.get("options") or {}).get("variante")),
        "genre": article.get("genre"), "commun": bool(article.get("commun")),  # M26 : de quoi accorder ce qu'on dit de la ligne
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
    if choix and tout_seul and len(article["declinaisons"]) > 1:
        # C3 : l'article renvoyé AVEC la réponse à « quelle taille ? » : le choix dit est la taille, jamais un choix à poser plus tard.
        # M120 : aussi quand la phrase disait déjà la taille (« quatre fromages normale », choix « Normale ») : jamais refusé comme option.
        dite = _declinaison_choisie(article, choix, regles)
        if dite is not None and dite["vendable"] and not dite["rupture"]:
            ligne["code"] = dite["code"]
            if len(article["declinaisons"]) > 1:
                ligne["nom"] = f"{article['nom']} {dite['nom']}"
                ligne["taille"] = dite["nom"]
            # SA-55 (appels 2606, 2609) : ce qui, dans le choix, n'est pas la taille (la taille suivie d'un supplément) reste un choix à poser,
            # jamais jeté en silence ; ce qui ne se trouve pas est refusé comme tout choix.
            choix = _sans_la_taille(article, choix, dite, regles)
    if ligne["code"]:
        _appliquer_les_defauts(article, ligne)
    if not tout_seul and (choix or sans or note or moities):
        return _r("ARGUMENT_INVALIDE", {}, "Prenons les articles un par un pour les choix.", "articles")
    # M119 : ce que la phrase dit pour CET article seulement (« dont une sans champignons »).
    if choix_dits:
        choix = f"{choix}, {choix_dits}" if choix else choix_dits
    if retraits_dits:
        sans = f"{sans}, {retraits_dits}" if sans else retraits_dits
    for texte_choix, roles in ((moities, ("moities",)), (choix, None)):
        if texte_choix and ligne["code"]:
            erreur = _appliquer_les_choix(article, ligne, texte_choix, roles=roles)
            if erreur:
                return erreur
        elif texte_choix:
            ligne["choix_a_poser"] = (ligne.get("choix_a_poser") or []) + [texte_choix]
    if sans and moities and not ligne["code"] and ligne.get("choix_a_poser"):
        # SA-22 : les moitiés attendent la taille : le retrait attend avec elles (il se note sur la moitié dite).
        ligne["retraits_a_poser"] = (ligne.get("retraits_a_poser") or []) + [sans]
    elif sans:
        erreur = _appliquer_les_retraits(article, ligne, sans)
        if erreur:
            return erreur
    erreur = _noter(ligne, note or "", regles)
    if erreur:
        return erreur
    _poser_le_suspens(p, article, ligne)
    question = _question(article, ligne)
    if question is not None:
        ligne["attente"] = question
        ligne["article_nom"] = article["nom"]
        _remplacer_l_attente(p, ligne, en_attente_avant)
        p["lignes"].append(ligne)
        P.toucher(p)
        return _avec(
            _r("CHOIX_OBLIGATOIRE", {"article": ligne["nom"], "question": question}, _phrase_de_la_question(question, article["nom"]), question["nom"]), p
        )
    essai = copy.deepcopy(p)
    avant = set(en_attente_avant) if en_attente_avant is not None else None
    _remplacer_l_attente(essai, ligne, avant)
    if not _fusionner(essai, ligne):
        essai["lignes"].append(ligne)
    P.toucher(essai)
    chiffre = await _chiffrer(source, essai, regles)
    if _bloque_l_ajout(chiffre):
        return _avec(chiffre, p)
    _valider(p, essai)
    if avant is not None and en_attente_avant is not None:
        en_attente_avant.intersection_update(avant)
    return _r("OK", {"ajoute": ligne["nom"], "quantite": quantite})


async def ajouter(
    source: Source, p: dict[str, Any], regles: Reglages, *, articles: str | None = None, choix: str | None = None, sans: str | None = None,
    note: str | None = None, moities: str | None = None,
) -> Resultat:
    """Ajoute au panier ce que l'appelant vient de dire : plusieurs articles et quantités dans une phrase, chaque morceau par la recherche
    dans le catalogue. Sans ``articles`` : répond à la question ouverte (taille, choix) ou complète la dernière ligne. Un manque à la fois ;
    ce qui est posé reste posé même quand un autre morceau pose une question."""
    manque = await _prealables(source, p, regles)
    if manque is not None:
        if (articles or "").strip():
            # SA-33 (appel 2559) : dit avant le mode ou la zone, l'article est gardé (pris dès le préalable posé) ; la question reste la même.
            _garder_le_dit(p, {"articles": articles, "choix": choix, "sans": sans, "note": note, "moities": moities})
            return _avec(manque, p)
        return manque
    await _reprendre_les_dits(source, p, regles)
    pieces = lecture.decouper(articles or "")
    if not pieces:
        return await _repondre(source, p, regles, choix=choix, sans=sans, note=note, moities=moities)
    deux = None if moities else lecture.deux_moities(articles or "")
    if deux is not None:
        # C4 : « <article> moitié A moitié B » dit dans les articles : l'article des moitiés (son nom, ou celui que la source en connaît) avec ses deux moitiés.
        texte_de_l_article = f"{deux.debut} moitié moitié".strip()
        trouve = await source.chercher(texte_de_l_article)
        if trouve.statut == "RETENU":
            pieces, moities = [lecture.Morceau(deux.quantite, texte_de_l_article, texte_de_l_article)], f"{deux.a}, {deux.b}"
    lecture_naturelle = deux is None or len(pieces) > 1
    if len(pieces) > 1:
        # Un nom qui contient « et » : le texte entier est essayé d'abord, et pris seulement s'il est certain (zéro faux sûr).
        entier = lecture.sans_quantite(articles or "")
        trouve = await source.chercher(entier)
        if _est_le_nom({"statut": trouve.statut, "candidats": trouve.faits.get("candidats")}, entier):
            q, reste = lecture.une_quantite(lecture.en_chiffres((articles or "").strip()))
            pieces = [lecture.Morceau(q, reste, reste)]
            lecture_naturelle = False
    # M117, M119 (appel 2598) : chaque article de la phrase, avec ce qui ne vaut que pour lui (« deux X dont une sans Y » : deux lignes).
    lus = (lecture.lire_les_articles(articles) if lecture_naturelle else []) or [lecture.ArticleDit(q, t, b) for q, t, b in pieces]
    if lecture_naturelle and not lecture.parle_de_moities(articles):
        lus = await _rattacher_les_choix(source, p, regles, lus)
    plusieurs = len(lus) > 1
    if plusieurs and moities and not lecture.parle_de_moities(articles):
        moities = None  # M119 : des moitiés que la phrase ne dit pas ne sont jamais inventées
    if sans and any(lu.sans for lu in lus) and _deja_dit(sans, articles):
        sans = None  # le retrait de l'appel est celui que la phrase place déjà sur le bon article
    if plusieurs and note and _deja_dit(note, articles):
        note = None
    repondu: list[str] = []
    if plusieurs and choix and P.a_completer(p):
        # M120 : la phrase renvoyée AVEC la réponse à la question ouverte : la réponse va à la question, ce qui est déjà au panier n'est pas repris.
        deja = {l["ref"] for l in p["lignes"]}
        repondu = await _repondre_aux_attentes(source, p, regles, choix)
        if repondu:
            choix, sans = None, None if sans and _deja_dit(sans, articles) else sans
            restants = []
            for lu in lus:
                trouve = await _chercher_l_article(source, lu.texte, regles)
                if not (trouve.statut == "RETENU" and trouve.faits.get("retenu") in deja):
                    restants.append(lu)
            lus = restants
            if not lus:
                return _avec(await _etat_apres_ajout(source, p, regles, {"ajoutes": [], "repondu": repondu}), p)
    if plusieurs and choix and _deja_dit(choix, articles):
        choix = None  # le choix de l'appel est dit dans la phrase : il y est lu, article par article
    meme_article = len({lecture.recherche_normale(lu.texte) for lu in lus}) == 1
    ajoutes: list[str] = []
    probleme: Resultat | None = None
    en_attente_avant = {l["ref"] for l in P.a_completer(p)}
    en_suspens: dict[str, Any] | None = None
    for lu in lus:
        quantite, texte, brut = lu.quantite, lu.texte, lu.brut
        moities_du_morceau, sans_du_morceau = moities, sans
        if not moities:
            # C4 : « moitié-moitié A B » (un seul marqueur) dit dans les articles : ce qui suit le marqueur est les deux moitiés, le reste est l'article.
            seul = lecture.moities_apres_le_marqueur(texte)
            if seul is not None:
                texte_de_l_article = f"{seul[0]} moitié moitié".strip()
                if (await source.chercher(texte_de_l_article)).statut == "RETENU":
                    dites, _, retire = re.split(r"\b(sans)\b", seul[1], maxsplit=1, flags=re.IGNORECASE) if re.search(r"\bsans\b", seul[1], re.IGNORECASE) else (seul[1], "", "")
                    texte, brut, moities_du_morceau = texte_de_l_article, texte_de_l_article, await _moities_separees(source, dites.strip(" ,"))
                    sans_du_morceau = sans or retire.strip(" ,") or None
        tout_seul = len(lus) == 1 or meme_article or moities_du_morceau != moities
        r = await _un_article(
            source, p, regles, quantite, texte, choix=choix, sans=sans_du_morceau, note=note, moities=moities_du_morceau,
            tout_seul=tout_seul, brut=brut, en_attente_avant=en_attente_avant, retraits_dits=lu.sans, choix_dits=lu.avec,
        )
        if r.statut == "OK":
            ajoutes.append(r.faits["ajoute"])
        elif probleme is None:
            probleme = r
        if r.statut in ("AMBIGU", "INTROUVABLE"):
            dits = [c for c in ((choix if tout_seul else None), lu.avec) if c]
            retraits = [c for c in ((sans_du_morceau if tout_seul else None), lu.sans) if c]
            noms = r.faits.get("candidats") or r.faits.get("plus_proches") or []
            if (dits or retraits) and noms:
                en_suspens = {"candidats": list(noms), "choix": ", ".join(dits) or None, "sans": ", ".join(retraits) or None}
    if en_suspens is not None:
        p[CLE_CHOIX_EN_SUSPENS] = en_suspens  # D4 : posé à la prochaine ligne créée, si son article est un des candidats
    faits: dict[str, Any] = {"ajoutes": ajoutes, **({"repondu": repondu} if repondu else {})}
    if probleme is not None:
        return _avec(Resultat(probleme.statut, {**probleme.faits, **faits}, probleme.suggestion, probleme.manque), p)
    return _avec(await _etat_apres_ajout(source, p, regles, faits), p)


# --------------------------------------------------------------------------- #
# SA-52 (appels 2602, 2604) : les choix d'un article dits dans la même phrase que lui
# --------------------------------------------------------------------------- #


def _dans_la_composition(article: dict, morceau: str) -> bool:
    """« A et B » pour un article décrit « avec A et B » : ce que l'article CONTIENT déjà (son nom, sa description, ses
    ingrédients) n'est pas un choix à refuser. Tous les mots dits doivent y être ; un mot court ou de liaison ne compte pas."""
    mots = [m for m in norme_de_recherche(morceau).split() if len(m) >= 3 and m not in _MOTS_DE_LIAISON]
    if not mots:
        return False
    contenu = " ".join([article.get("nom") or "", article.get("description") or "", *(article.get("ingredients") or [])])
    return set(mots) <= set(norme_de_recherche(contenu).split())


def _option_certaine(article: dict, texte: str) -> bool:
    """Le texte nomme sans doute une option de l'article (par son nom, un synonyme, ou avec le nom de son groupe : « finition mate »)."""
    index = _options_disponibles(article, {"choix": []})
    if not index:
        return False
    elements = [Element(cle, o["nom"], tuple(o.get("synonymes") or ()), g["nom"]) for cle, (_, g, o) in index.items()]
    trouve = _chercher_dans(elements, texte)
    if trouve["statut"] != "RETENU":
        trouve = _sans_le_nom_du_groupe(elements, index, texte) or trouve
    return trouve["statut"] == "RETENU"


def _un_choix(article: dict, morceau: lecture.Morceau) -> bool:
    return _option_certaine(article, morceau.brut) or _option_certaine(article, morceau.texte) or _dans_la_composition(article, morceau.brut)


def _en_choix(article: dict, texte: str) -> str | None:
    """``texte`` (« rouge et bleu finition mate vernis ») lu comme une suite d'options de l'article (ou de ce qu'il contient déjà) :
    rendu séparé par des virgules (« rouge, bleu, finition mate, vernis »). Un morceau sans séparateur est coupé en suites de mots
    qui sont chacune un choix certain, la plus longue d'abord. ``None`` : un morceau au moins n'est pas un choix de cet article."""
    morceaux = lecture.morceaux_d_options(texte)
    if not morceaux:
        return None
    sortie: list[str] = []
    for m in morceaux:
        if _un_choix(article, m):
            sortie.append(m.brut)
            continue
        mots, i = m.brut.split(), 0
        while i < len(mots):
            j = next((j for j in range(len(mots), i, -1) if _un_choix(article, lecture.Morceau(*lecture.une_quantite(" ".join(mots[i:j])), " ".join(mots[i:j])))), None)
            if j is None:
                return None
            sortie.append(" ".join(mots[i:j]))
            i = j
    return ", ".join(sortie)


async def _article_certain(source: Source, p: dict[str, Any], regles: Reglages, texte: str) -> dict | None:
    trouve = await _chercher_l_article(source, texte, regles)
    if trouve.statut != "RETENU":
        return None
    article = await source.article(trouve.faits["retenu"], p["mode"])
    return article if article is not None and (article.get("groupes") or article.get("description") or article.get("ingredients")) else None


async def _rattacher_les_choix(source: Source, p: dict[str, Any], regles: Reglages, lus: list[lecture.ArticleDit]) -> list[lecture.ArticleDit]:
    """Un produit à choix multiples (C5 : n options d'un groupe) prend ses choix dans la même phrase : « X 2 couleurs, rouge et bleu,
    finition mate, vernis » est UN article. Mécanisme commun, aucun mot du catalogue :

    - un morceau dit SANS quantité, juste après un article certain, et qui est une de SES options (ou ce qu'il contient déjà), est un choix
      de cet article, jamais un article à part (« un rouge » dit avec sa quantité reste un article) ;
    - un morceau qui n'est pas un article certain mais COMMENCE par un (« X 2 couleurs rouge ») est coupé là, si tout ce qui suit est
      fait de ses options.
    Rien de sûr : la phrase reste lue comme avant."""
    sortie: list[lecture.ArticleDit] = []
    porteur: tuple[int, dict] | None = None  # (rang dans ``sortie``, l'article) : l'article certain qui reçoit les choix qui suivent
    for lu in lus:
        quantite_dite = lecture._QUANTITE.match(lu.brut or "") is not None
        choix = _en_choix(porteur[1], lu.texte) if porteur is not None and not quantite_dite and lu.sans is None and lu.avec is None else None
        if porteur is not None and choix:
            i, _ = porteur
            avant = sortie[i]
            sortie[i] = avant._replace(avec=f"{avant.avec}, {choix}" if avant.avec else choix)
            continue
        article = await _article_certain(source, p, regles, lu.texte)
        if article is None:
            mots = lu.texte.split()
            for k in range(len(mots) - 1, 0, -1):
                debut, reste = " ".join(mots[:k]), " ".join(mots[k:])
                article = await _article_certain(source, p, regles, debut)
                choix = _en_choix(article, reste) if article is not None else None
                if choix:
                    lu = lu._replace(texte=debut, brut=debut, avec=f"{choix}, {lu.avec}" if lu.avec else choix)
                    break
                article = None
        sortie.append(lu)
        porteur = (len(sortie) - 1, article) if article is not None and article.get("groupes") else None
    return sortie


_MOTS_DE_LIAISON = frozenset({"de", "du", "des", "la", "le", "les", "l", "un", "une", "sans", "avec", "en", "et"})


def _deja_dit(valeur: str | None, articles: str | None) -> bool:
    """Tous les mots de ``valeur`` sont dans la phrase des articles : la lecture de la phrase l'a déjà placé (M119)."""
    mots = [m for m in recherche_liste.normaliser(lecture.en_chiffres(valeur or "")).split() if m not in _MOTS_DE_LIAISON]
    dits = set(recherche_liste.normaliser(lecture.en_chiffres(articles or "")).split())
    return bool(mots) and all(m in dits for m in mots)


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


def _garder_le_dit(p: dict[str, Any], dit: dict[str, Any]) -> None:
    """SA-33 : ce qui est dit avant un préalable, gardé tel quel dans le panier de l'appel (une seule fois : le même dit redit n'est pas doublé)."""
    dit = {cle: valeur for cle, valeur in dit.items() if valeur is not None and str(valeur).strip()}
    gardes = p.setdefault("dits_en_attente", [])
    if dit and dit not in gardes:
        gardes.append(dit)


async def _reprendre_les_dits(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat | None:
    """SA-33 : les préalables sont posés, ce qui était gardé est pris, dans l'ordre où il a été dit. Rend le résultat de ces ajouts (la première
    question qu'ils posent, sinon l'état du panier, avec ``ajoutes``), ou ``None`` s'il n'y avait rien de gardé ou qu'un préalable manque encore."""
    gardes = list(p.get("dits_en_attente") or [])
    if not gardes or await _prealables(source, p, regles) is not None:
        return None
    p["dits_en_attente"] = []
    ajoutes: list[str] = []
    question: Resultat | None = None
    for dit in gardes:
        r = await ajouter(source, p, regles, **dit)
        ajoutes += [a for a in (r.faits.get("ajoutes") or []) if a not in ajoutes]
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
        return _avec(_r("INCOMPLETE", {}, "Qu'est-ce que je vous mets ?", "articles"), p)
    cible = (P.a_completer(p) or p["lignes"][-1:] or [None])[0]
    if cible is None:
        return _avec(_r("INCOMPLETE", {}, "Qu'est-ce que je vous mets ?", "articles"), p)
    attentes = P.a_completer(p)
    if choix and not (sans or note or moities) and sum(1 for l in attentes if l["ref"] == cible["ref"] and l["attente"] == cible.get("attente")) > 1:
        # SA-52 : « deux X dont un sans Y » fait deux lignes qui attendent la même question : la réponse vaut pour les deux.
        if await _repondre_aux_attentes(source, p, regles, choix):
            return _avec(await _etat_apres_ajout(source, p, regles, {}), p)
    return await _travailler_une_ligne(source, p, regles, cible, choix=choix, sans=sans, note=note, moities=moities)


async def _travailler_une_ligne(
    source: Source, p: dict[str, Any], regles: Reglages, cible: dict[str, Any], *, choix: str | None = None, sans: str | None = None,
    note: str | None = None, moities: str | None = None, quantite: int | None = None,
) -> Resultat:
    """Applique choix, retraits, note, moitiés, quantité à UNE ligne, sur une copie : adopté seulement si tout tient et se chiffre."""
    essai = copy.deepcopy(p)
    ligne = next(l for l in essai["lignes"] if l["n"] == cible["n"])
    article = await source.article(ligne["ref"], essai["mode"])
    if article is None:
        return _avec(_r("INTROUVABLE", {"article": ligne["nom"]}, f"{ligne['nom']} n'est plus au catalogue."), p)
    attente = ligne.get("attente")
    if attente and attente["type"] == "declinaison" and choix:
        # La réponse à « quelle taille ? » : la déclinaison dite (le nom d'une taille).
        trouve = _declinaison_choisie(article, choix, regles)
        if trouve is None:
            return _avec(_r("CHOIX_OBLIGATOIRE", {"article": ligne["nom"], "question": attente}, _phrase_de_la_question(attente, article["nom"]), attente["nom"]), p)
        if not trouve["vendable"] or trouve["rupture"]:
            return _avec(_r("RUPTURE", {"nom": f"{article['nom']} {trouve['nom']}"}, f"{article['nom']} {trouve['nom']} n'est plus disponible."), p)
        ligne["code"] = trouve["code"]
        if len(article["declinaisons"]) > 1:
            ligne["nom"] = f"{article['nom']} {trouve['nom']}"
            ligne["taille"] = trouve["nom"]
        choix = None
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
            dans = attente["groupe"] if attente and attente.get("type") == "groupe" and roles is None else None
            erreur = _appliquer_les_choix(article, ligne, texte, roles=roles, dans=dans)
            if erreur:
                return _avec(erreur, p)
    if sans:
        erreur = _appliquer_les_retraits(article, ligne, sans)
        if erreur:
            return _avec(erreur, p)
    erreur = _noter(ligne, note or "", regles)
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


async def modifier(
    source: Source, p: dict[str, Any], regles: Reglages, *, ligne: str | None = None, quantite: int | None = None, choix: str | None = None,
    sans: str | None = None, note: str | None = None, moities: str | None = None,
) -> Resultat:
    """Change UNE ligne : sa quantité (zéro la retire), ses choix, ses retraits, sa note. Tout ou rien : un changement qui ne tient pas n'est pas posé."""
    cible, refus = await _trouver_la_ligne(p, ligne)
    if refus is not None:
        return _avec(refus, p)
    if quantite is not None and (not isinstance(quantite, int) or isinstance(quantite, bool) or not 0 <= quantite <= lecture.QUANTITE_MAX):
        return _avec(_r("ARGUMENT_INVALIDE", {}, "Combien exactement ?", "quantite"), p)
    if quantite == 0:
        return await retirer(source, p, regles, ligne=str(cible["n"]))
    if quantite is None and not (choix or sans or note or moities):
        return _avec(_r("INCOMPLETE", {}, "Qu'est-ce que je change ?", "modification"), p)
    return await _travailler_une_ligne(source, p, regles, cible, choix=choix, sans=sans, note=note, moities=moities, quantite=quantite)


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
    return nom_dit(l["nom"], l["quantite"], genre=l.get("genre"), commun=bool(l.get("commun")))


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
                "n": l["n"], "nom": l["nom"], "quantite": l["quantite"], "prix_unitaire": calculee["prix_unitaire"] if calculee else None,
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
    return _avec(
        _r(
            "OK",
            {
                "lignes": lignes, "sous_total": chiffre.faits["sous_total"], "frais": chiffre.faits["frais"], "total": total,
                "remises": [{"nom": r["nom"], "montant": r["montant"]} for r in remises], "total_remises": chiffre.faits.get("total_remises", 0),
                "offerts": chiffre.faits.get("offerts") or [],
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
        {"cle": list(_cle_de_ligne(l)), "nom": l["nom"], "quantite": l["quantite"], "genre": l.get("genre"), "commun": bool(l.get("commun"))}
        for l in P.lignes_pretes(p)
    ]


def _majuscule(texte: str) -> str:
    """La première lettre en majuscule, le reste tel quel (``capitalize`` mettrait le reste en minuscules)."""
    return texte[:1].upper() + texte[1:]


def _cle_lue(a: dict[str, Any]) -> str:
    """La clé d'une ligne, lue pareil avant et après un aller-retour JSON (la fiche s'écrit entre deux tours : un tuple y devient une liste)."""
    return json.dumps(a["cle"], ensure_ascii=False)


def _ce_qui_a_change(avant: list[dict[str, Any]], apres: list[dict[str, Any]]) -> list[str]:
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


async def _le_reglement(source: Source, p: dict[str, Any], total: int, brut: dict[str, Any]) -> tuple[dict | None, Resultat | None]:
    """Le règlement tel que dit : un moyen, ou une part en un moyen et le reste en un autre (titres, puis espèces sur un billet). Le code
    calcule le reste et la monnaie ; il refuse un moyen non accepté. ``(paiement, None)`` ou ``(None, refus)``."""
    reglages = await source.reglages()
    # M90 (appel 2574) : un moyen que la source réserve à certains modes n'est ni proposé ni accepté hors de ces modes. Mécanisme commun : la
    # source déclare ``moyens_reserves_au_mode`` ({moyen: modes}) ; sans déclaration, tous les moyens réglés valent pour tous les modes.
    reserves = getattr(source, "moyens_reserves_au_mode", None) or {}
    acceptes = [m for m in reglages["moyens_paiement"] if m not in reserves or p.get("mode") in reserves[m]]
    moyen, moyen_reste = brut.get("moyen"), brut.get("moyen_reste")
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


def _phrase_du_reglement(source: Source, paiement: dict[str, Any]) -> str:
    morceaux = [f"{montant_en_lettres(m['montant'])} {source.libelles_des_moyens.get(m['moyen'], m['moyen'])}" for m in paiement["moyens"]]
    phrase = "Vous réglez " + liste_dite_et(morceaux)
    if paiement.get("rendu_sur"):
        phrase += f", sur un billet de {montant_en_lettres(paiement['rendu_sur'])}"
    return phrase + "."


def _contenu_relu(p: dict[str, Any], total: int, paiement: dict[str, Any]) -> str:
    """M106/M107 : tout ce que dit la relecture (le panier et son moment, le total, le règlement, le nom, les numéros, la note) : la même empreinte
    = rien de nouveau depuis la relecture dite."""
    client = p["client"]
    contenu = {
        "panier": P.empreinte(p), "total": total, "moyens": paiement.get("moyens"), "rendu_sur": paiement.get("rendu_sur"),
        "prenom": client.get("prenom"), "telephone": client.get("telephone"), "second": client.get("second_numero"),
        "note": p.get("note"), "consigne": p.get("consigne"),
    }
    return hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _relecture_deja_dite(p: dict[str, Any], total: int) -> Resultat:
    """M106/M107 (appels 2592, 2593) : ``finaliser`` rappelé sans rien de nouveau (souvent sur une question de la personne pendant la relecture) :
    rien n'est redit, ni relecture ni question du code ; la parole revient au modèle avec les faits, pour qu'il réponde à la personne. La relecture
    reste valable (même jeton) : un « oui » ensuite enregistre."""
    return _avec(
        _r("INCOMPLETE", {"total": total, "a_confirmer": True, "relecture_deja_dite": True, "rien_de_nouveau": True}, "", "reponse_a_la_relecture"),
        p, total=total,
    )


def _ecrire_la_relecture(
    source: Source, p: dict[str, Any], chiffre: Resultat, paiement: dict[str, Any], garde_le_numero: bool, regles: Reglages | None = None
) -> Resultat:
    """La relecture : tout la première fois, seulement ce qui a changé après une correction. Un jeton en prouve la lecture.

    M98 : quand le numéro qui s'affiche est gardé, la relecture complète finit par UNE question qui le dit (phrase réglable,
    ``question_numero_affiche``), à la place du « C'est bon ? », jamais en plus. Une relecture refaite parce que seul le numéro a changé
    (le panier n'a pas bougé) ne redit ni le panier ni le total : le numéro dicté est relu par le code, puis « C'est bon ? »."""
    avant, maintenant = p.get("derniere_lecture"), _instantane(p)
    total = chiffre.faits["total"]
    question = ((regles or Reglages()).question_numero_affiche or "").strip()
    relue = p.get("relecture") or {}
    seul_le_numero = bool(relue and relue.get("empreinte") == P.empreinte(p) and relue.get("telephone", p["client"].get("telephone")) != p["client"].get("telephone"))
    if avant and p.get("derniere_lecture_mode") == p["mode"]:
        changes = _ce_qui_a_change(avant, maintenant)
        if not changes and seul_le_numero:
            phrase = "C'est bon ?"
        else:
            phrase = (_majuscule(liste_dite_et(changes)) + ". " if changes else "") + f"Cela fait maintenant {montant_en_lettres(total)}. C'est bon ?"
    else:
        phrase = f"Je vous relis : {_phrase_des_lignes(P.lignes_pretes(p))}"
        if p["mode"]:
            phrase += f", {source.libelles_des_modes.get(p['mode'], p['mode'])}"
        if p.get("heure_voulue_dite"):
            phrase += f", pour {p['heure_voulue_dite']}"
        # C6 : à un appelant pressé, la relecture ne cite ni l'offert ni la remise (le total dit reste celui de la source).
        remises = [] if p.get("presse") else chiffre.faits.get("remises") or []
        offerts = [] if p.get("presse") else chiffre.faits.get("offerts") or []
        if offerts:
            phrase += ", plus " + _phrase_des_lignes([{"quantite": o["quantite"], "nom": o["nom"], "choix": [], "retires": []} for o in offerts]) + " offert"
        if remises:
            phrase += ", avec " + liste_dite_et([_dit(r["nom"]) for r in remises])
        phrase += f". Cela fait {montant_en_lettres(total)}. {_phrase_du_reglement(source, paiement)}"
        phrase += f" {question}" if garde_le_numero and question else " C'est bon ?"
    # M98 : la relecture vaut pour CE numéro : un autre numéro dit ensuite la refait (relu par le code), jamais un « oui » qui l'enregistre sans relecture.
    p["relecture"] = {
        "empreinte": P.empreinte(p), "jeton": uuid.uuid4().hex, "version": p["version"], "telephone": p["client"].get("telephone"),
        "contenu": _contenu_relu(p, total, paiement),  # M106/M107 : ce que la relecture a dit, pour reconnaître un rappel sans rien de nouveau
    }
    p["derniere_lecture"], p["derniere_lecture_mode"] = maintenant, p["mode"]
    return _avec(
        _r("INCOMPLETE", {"total": total, "lignes": [{"nom": l["nom"], "quantite": l["quantite"]} for l in P.lignes_pretes(p)], "a_confirmer": True}, phrase, "relecture"),
        p, total=total,
    )


def _peut_parler_d_offre(p: dict[str, Any], regles: Reglages, ref: str | None = None) -> bool:
    """T-08 : une offre se dit au plus ``mentions_de_remise`` fois par appel, jamais après un refus ; une offre déjà dite peut être suivie (« laquelle voulez-vous ? »)."""
    if p.get("remise_refusee"):
        return False
    return (ref is not None and ref in p.get("remises_dites", [])) or p.get("mentions_de_remise", 0) < regles.mentions_de_remise


async def _vente_en_plus(source: Source, p: dict[str, Any], regles: Reglages, chiffre: Resultat) -> Resultat | None:
    """M25 : UN article précis proposé en plus (une offre atteinte, sinon ce qui manque au panier, la meilleure vente d'abord), jamais une phrase générique.
    Rien de pertinent à proposer : ``None`` et la commande continue. Une source sans cette capacité garde la question ouverte."""
    chercher = getattr(source, "proposer_en_plus", None)
    if chercher is None:
        return _r("INCOMPLETE", {}, "Souhaitez-vous ajouter quelque chose avec cela ?", "vente_en_plus")
    lignes = chiffre.faits.get("lignes") or []
    proposition = await chercher(p["mode"], lignes, _peut_parler_d_offre(p, regles))
    if proposition is not None and proposition.get("raison") == "offre" and not _peut_parler_d_offre(p, regles, proposition["offre"]["ref"]):
        proposition = await chercher(p["mode"], lignes, False)
    if proposition is None:
        return None
    nom = nom_dit(proposition["nom"], 1, genre=proposition.get("genre"), commun=bool(proposition.get("commun")))
    faits = {"proposition": {k: proposition.get(k) for k in ("ref", "nom", "prix", "declinaison", "raison", "etoile", "choix", "plusieurs_tailles")}}
    # le oui qui suit : `en_plus` à ``finaliser`` ; ``choix`` = les autres options que la proposition permet (M73)
    p["proposition_en_plus"] = {"ref": proposition.get("ref"), "nom": proposition["nom"], "choix": [c for c in (proposition.get("choix") or []) if isinstance(c, str)]}
    if proposition["raison"] == "offre":
        offre = proposition["offre"]
        if offre["ref"] not in p.setdefault("remises_dites", []):
            p["remises_dites"].append(offre["ref"])
            p["mentions_de_remise"] = p.get("mentions_de_remise", 0) + 1
        offert = "offerte" if proposition.get("genre") == "f" else "offert"
        faits["proposition"]["offre"] = offre["nom"]
        phrase = f"{_dit(offre['nom'])} : vous avez droit à {nom} {offert}. Je vous l'ajoute ?"
    else:
        phrase = f"Avec cela, je vous propose {nom} à {montant_en_lettres(proposition['prix'])}. Je vous l'ajoute ?"
    return _r("INCOMPLETE", faits, phrase, "vente_en_plus")


async def _deja_au_panier(source: Source, p: dict[str, Any], texte: str) -> bool:
    """Chaque article dit est-il déjà une ligne du panier (même article) ? Alors le redire ne l'ajoute pas une seconde fois."""
    refs = {l["ref"] for l in p["lignes"]}
    pieces = lecture.decouper(texte)
    if not pieces:
        return False
    for _quantite, morceau, _brut in pieces:
        trouve = await source.chercher(morceau)
        if trouve.statut != "RETENU":
            return False
        article = await source.article(trouve.faits["retenu"], p["mode"])
        if article is None or article["id"] not in refs:
            return False
    return True


async def finaliser(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, **gestes: Any) -> Resultat:
    """Le geste, puis le numéro dicté et RETENU dans cet appel dit par le code (``avec_numeros_retenus``) : un numéro corrigé se relit tel que retenu,
    jamais de mémoire. Le numéro qui s'affiche n'est jamais relu ; un numéro déjà dit n'est pas redit tant qu'il ne change pas.

    M98 : quand le numéro gardé est celui qui s'affiche, il est porté dans les faits (``numero_affiche_dit``) pour que l'agent puisse le dire si on
    le lui demande, sans être ajouté à la phrase."""
    r = await _finaliser(source, p, regles, appelant, **gestes)
    client = p["client"]
    if appelant.telephone_affiche and client.get("telephone") == appelant.telephone_affiche:
        r = avec_numero_affiche(r, appelant.telephone_affiche)
    numero = _numero_dit(gestes.get("telephone")) if gestes.get("telephone") else None
    dit = numero if numero and client.get("telephone") == numero and numero != appelant.telephone_affiche and client.get("numero_dit") != numero else None
    second = client.get("second_numero") or {}
    deuxieme = _numero_dit(gestes.get("second_numero")) if gestes.get("second_numero") else None
    second_dit = deuxieme if deuxieme and second.get("numero") == deuxieme and client.get("second_numero_dit") != deuxieme else None
    if r.statut in ("ENREGISTREE", "DEJA_FAIT", "TRANSMISE") or not (dit or second_dit):
        return r
    if dit:
        client["numero_dit"] = dit
    if second_dit:
        client["second_numero_dit"] = second_dit
    return avec_numeros_retenus(r, dit, second_dit)


async def _finaliser(
    source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, *, prenom: str | None = None, telephone: str | None = None,
    second_numero: str | None = None, second_qui: str | None = None, second_pourquoi: str | None = None, moyen: str | None = None,
    part: Any = None, moyen_reste: str | None = None, rendu_sur: Any = None, note: str | None = None, consigne: str | None = None,
    confirmer: bool = False, heure_voulue: str | None = None, articles: str | None = None, en_plus: bool | None = None,
) -> Resultat:
    """Conduit la commande jusqu'à son enregistrement, UN manque à la fois dans l'ordre : articles et choix, ouverture, une offre en plus (une
    fois), prénom, numéro (jamais redemandé quand il s'affiche), règlement, puis la RELECTURE. L'enregistrement n'a lieu que sur ``confirmer`` après
    une relecture valide ; une correction invalide la relecture et seul ce qui a changé est relu. Le total est celui de la source."""
    deja = p.get("enregistree")
    if deja and p["lignes"]:
        return _avec(Resultat("DEJA_FAIT", dict(deja), "Votre commande est déjà enregistrée."), p)
    if note and note.strip() and not (await source.reglages()).get("notes_libres", True):
        # Réglage « notes libres » éteint : l'agent n'en prend plus, refusé avant tout le reste (rien n'est gardé).
        return _avec(_r("ARGUMENT_INVALIDE", {"raison": "notes_refusees"}, "Je ne peux pas noter de remarque sur cette commande.", "note"), p)
    manque = await _prealables(source, p, regles)
    if manque is not None:
        return manque
    await _reprendre_les_dits(source, p, regles)  # SA-33 : ce qui était gardé avant les préalables n'est jamais oublié à la fin
    # C5 : ce que l'appelant dit EN MÊME TEMPS (des articles, le oui ou le non à l'offre en plus) n'est jamais perdu.
    proposee = p.pop("proposition_en_plus", None)
    if articles and p["lignes"] and await _deja_au_panier(source, p, articles):
        articles = None  # le modèle renvoie les articles déjà pris à chaque appel : jamais le double de ce qui est déjà dans le panier
    if articles and proposee and en_plus is True and lecture.sans_quantite(articles).casefold() in (proposee["nom"].casefold(), f"un {proposee['nom']}".casefold()):
        articles = None  # le oui à la proposition redit le nom proposé : il n'est ajouté qu'une fois
    if articles and proposee and en_plus is True:
        # M73 (appels 2560, 2568) : « oui, mais plutôt X » où X est une des options que la proposition permet : X REMPLACE l'article proposé,
        # une seule fois. Mécanisme commun de l'offre en plus, sans mot de métier.
        dit = recherche_liste.normaliser(lecture.sans_quantite(articles))
        autre = next((c for c in proposee.get("choix") or [] if recherche_liste.normaliser(c) == dit), None)
        if autre:
            proposee = {**proposee, "nom": autre}
            articles = None
    a_ajouter = [t for t in (articles, proposee["nom"] if proposee and en_plus is True else None) if t and t.strip()]
    for texte in a_ajouter:
        ajout = await ajouter(source, p, regles, articles=texte)
        # Un texte que le catalogue ne connaît pas (un « non », un « oui » mis là par le modèle) n'est pas un article : ignoré, la commande continue.
        if ajout.statut not in ("OK", "INTROUVABLE"):
            return ajout
    if not p["lignes"]:
        return _avec(_r("INCOMPLETE", {}, "Qu'est-ce que je vous mets ?", "articles"), p)
    en_attente = P.a_completer(p)
    if en_attente:
        q = en_attente[0]["attente"]
        return _avec(_r("CHOIX_OBLIGATOIRE", {"article": en_attente[0]["nom"], "question": q}, _phrase_de_la_question(q, en_attente[0]["article_nom"]), q["nom"]), p)
    chiffre = await _chiffrer(source, p, regles)
    if chiffre.statut != "OK":
        return _avec(chiffre, p)
    total = chiffre.faits["total"]
    if heure_voulue:
        resolue = await heure_du_lieu(source, heure_voulue, p)
        if resolue is not None and resolue.statut != "RETENU":
            return _avec(resolue, p)  # un doute ou une heure manquante se dit, jamais une heure devinée
        if resolue is not None and resolue.faits.get("heure_voulue"):
            p["heure_voulue"] = resolue.faits["heure_voulue"]
    etat = await source.etat(p["mode"])
    if not etat["ouvert"] and not p.get("heure_voulue"):
        faits_fermes = {k: etat.get(k) for k in CLES_DE_L_ETAT}
        if etat.get("planifiee_permise"):
            # D15 : fermé, mais le réglage du type permet de commander pour plus tard : l'heure voulue est LA question (une seule).
            p["a_planifier"] = True
            return _avec(
                _r("FERME_PLANIFIABLE", {**faits_fermes, "a_planifier": True}, f"{etat.get('phrase') or 'Nous ne prenons pas de commande en ce moment.'} Pour quel jour et à quelle heure ?", "heure_voulue"),
                p,
            )
        return _avec(_r(etat["statut"], faits_fermes, etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."), p)
    if p.get("heure_voulue"):
        # D15 : l'heure voulue (dite plus tôt ou maintenant) est vérifiée AVANT la relecture : créneau ouvert, délai minimal, jours à l'avance, place.
        verifier = getattr(source, "verifier_un_creneau", None)
        refus = await verifier(p["mode"], datetime.fromisoformat(p["heure_voulue"])) if verifier else None
        if refus is not None:
            p["heure_voulue"] = p["heure_voulue_dite"] = None  # une heure refusée n'est pas gardée : on en demande une autre
            return _avec(refus, p)
        dire = getattr(source, "quand_dit", None)
        p["heure_voulue_dite"] = await dire(datetime.fromisoformat(p["heure_voulue"])) if dire else None
    # C5 : ce qui est dit dans cet appel du geste est GARDÉ même quand la question d'avant (l'offre en plus) prend la réponse : le prénom, le numéro
    # valide et le règlement ne se redemandent pas.
    if prenom and prenom.strip():
        p["client"]["prenom"] = " ".join(prenom.split())[:60]
    if telephone and _numero_dit(telephone):
        p["client"]["telephone"] = _numero_dit(telephone)
    if moyen or part is not None or moyen_reste or rendu_sur is not None:
        retenu = {"moyen": moyen, "part": _centimes(part) if part is not None else None, "moyen_reste": moyen_reste,
                  "rendu_sur": _centimes(rendu_sur) if rendu_sur is not None else None}
        p["paiement"] = {k: v for k, v in retenu.items() if v is not None}
    if regles.vente_en_plus and not p["vente_en_plus_faite"]:
        p["vente_en_plus_faite"] = True  # une seule fois par commande, jamais redemandée
        proposition = await _vente_en_plus(source, p, regles, chiffre)
        if proposition is not None:
            return _avec(proposition, p)
    client = p["client"]
    if prenom and prenom.strip():
        client["prenom"] = " ".join(prenom.split())[:60]
    numero = _numero_dit(telephone) if telephone else None
    if telephone and numero is None:
        return _avec(_r("ARGUMENT_INVALIDE", {}, "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", "telephone"), p)
    numero = numero or client.get("telephone") or appelant.telephone_affiche
    # M98 : le numéro gardé est celui qui s'affiche (redonné ou non) : la relecture le dit en une question ; un autre numéro dicté ne l'est jamais.
    garde_le_numero = bool(numero and numero == appelant.telephone_affiche)
    if numero:
        client["telephone"] = numero
        connu = await source.client(numero)
        if connu and connu.get("prenom") and not client.get("prenom"):
            client["prenom"] = connu["prenom"]
    if numero:
        # Le numéro est connu : une remise qui reconnaît le client (fidélité) se calcule maintenant, avant tout total dit.
        chiffre = await _chiffrer(source, p, regles)
        if chiffre.statut != "OK":
            return _avec(chiffre, p)
        total = chiffre.faits["total"]
    if not client.get("prenom"):
        return _avec(_r("INCOMPLETE", {}, "À quel nom je mets la commande ?", "prenom"), p)
    if not numero:
        return _avec(_r("INCOMPLETE", {}, "Quel est votre numéro de téléphone ?", "telephone"), p)
    if second_numero:
        second = _numero_dit(second_numero)
        if second is None:
            return _avec(_r("ARGUMENT_INVALIDE", {}, "Je n'ai pas bien compris le second numéro : vous pouvez le redire ?", "second_numero"), p)
        client["second_numero"] = {"numero": second, "qui": (second_qui or "").strip()[:60] or None, "pourquoi": (second_pourquoi or "").strip()[:100] or None}
    if note and note.strip():
        p["note"] = (f"{p['note']} ; {note.strip()}" if p.get("note") else note.strip())[:300]
    if consigne and consigne.strip():
        p["consigne"] = consigne.strip()
    if moyen or part is not None or moyen_reste or rendu_sur is not None or p.get("paiement") is None:
        brut = {"moyen": moyen, "part": _centimes(part) if part is not None else None, "moyen_reste": moyen_reste,
                "rendu_sur": _centimes(rendu_sur) if rendu_sur is not None else None}
        if (part is not None and brut["part"] is None) or (rendu_sur is not None and brut["rendu_sur"] is None):
            return _avec(_r("ARGUMENT_INVALIDE", {}, "Quel montant exactement ?", "paiement"), p)
        p["paiement"] = {k: v for k, v in brut.items() if v is not None}
    paiement, refus = await _le_reglement(source, p, total, p["paiement"] or {})
    if refus is not None:
        if refus.manque in ("paiement", "paiement_reste"):
            p["paiement"] = None if refus.manque == "paiement" else p["paiement"]
        return _avec(refus, p)

    # --- la relecture en deux temps : on ne confirme jamais ce qu'on n'a pas relu
    relue = p.get("relecture")
    valide = bool(relue and relue["empreinte"] == P.empreinte(p) and relue.get("telephone", client["telephone"]) == client["telephone"])
    if regles.relecture_en_deux_temps and not (confirmer and valide):
        if valide and relue.get("contenu") == _contenu_relu(p, total, paiement):
            # M106/M107 : la relecture valable est déjà dite et rien n'a changé : jamais une relecture « maintenant » sans changement.
            return _relecture_deja_dite(p, total)
        return _ecrire_la_relecture(source, p, chiffre, paiement, garde_le_numero, regles)
    jeton = relue["jeton"] if valide else uuid.uuid4().hex
    if p.get("consigne"):
        ecrite = await source.consigne(client["telephone"], p["consigne"])
        if ecrite.statut == "ARGUMENT_INVALIDE" and ecrite.faits.get("raison") == "pour_la_commande":
            # La source refuse d'en faire une habitude de la fiche (une donnée sensible) : elle se note sur la commande seulement.
            p["note"] = (f"{p['note']} ; {p['consigne']}" if p.get("note") else p["consigne"])[:300]
        p["consigne"] = None

    brouillon = {
        "mode": p["mode"], "lignes": P.pour_le_chiffrage(p), "zone_id": _zone_id(p), "adresse": p.get("adresse"),
        "client": {"telephone": client["telephone"], "prenom": client.get("prenom"), "second_numero": client.get("second_numero")},
        "paiement": {"moyens": paiement["moyens"], "rendu_sur": paiement["rendu_sur"]}, "note": p.get("note"),
        "heure_voulue": datetime.fromisoformat(p["heure_voulue"]) if p.get("heure_voulue") else None,
        "appel_id": appelant.appel_id, "cree_par": "agent", **regles.pour_la_source(),
        # Les remises que le chiffrage vient de calculer : l'enregistrement les recalcule et refuse tout écart (jamais un montant du modèle).
        "remises": [{"ref": r["ref"]} for r in chiffre.faits.get("remises") or []],
    }
    r = await source.enregistrer(brouillon, jeton)
    if r.statut in ("ENREGISTREE", "DEJA_FAIT"):
        faits = {**r.faits, "monnaie": paiement["monnaie"]}
        p["enregistree"] = P.serialisable(faits)  # le panier s'écrit en JSON : jamais un datetime
        statut = source.statut_de_l_enregistrement() if r.statut == "ENREGISTREE" else "DEJA_FAIT"
        suggestion = r.suggestion
        question = (regles.question_apres_enregistrement or "").strip()
        if statut != "DEJA_FAIT" and question and suggestion.strip():
            # M108 (appels 2592, 2593) : la confirmation dite par le code finit par une question : la parole revient à la personne (M92), l'appel
            # ne se termine pas dans la même réponse.
            suggestion = f"{suggestion.rstrip()} {question}"
        return _avec(Resultat(statut, faits, suggestion), p)
    if r.statut == "INCOMPLETE" and r.manque == "relecture":
        return _ecrire_la_relecture(source, p, chiffre, paiement, garde_le_numero, regles)
    return _avec(r, p)


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
    """``sur`` : la donnée prouve qu'au moins une façon de le commander ne contient pas ``code`` ; ``contient`` : toutes en contiennent ;
    ``inconnu`` sinon. Une donnée absente n'est JAMAIS « sans » (jamais un faux non)."""
    signalements = article.get("signalements")
    if signalements is None:
        return "inconnu"
    if any(s["code"] == code for s in signalements):
        return "contient"
    etat = "sur"
    for options in article.get("obligatoires") or []:
        if any(_option_signale(o, code) is False for o in options):
            continue
        if options and all(_option_signale(o, code) for o in options):
            return "contient"
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
        return _r("OK", {"recherche": "sans", "regime": regime, "renseigne": False}, f"Je ne peux pas vous garantir ce qui est {regime} : {_PAS_SUR}")
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
    contiennent = sum(1 for _, e in etats if e == "contient")
    inconnus = sum(1 for _, e in etats if e == "inconnu")
    faits = {"recherche": "sans", "code": code, "categories": categories, "sans": surs, "contiennent": contiennent, "inconnus": inconnus}
    if surs:
        dits = surs[:_PLUS_DE_NOMS]
        entre_autres = ", entre autres," if len(surs) > len(dits) else ""
        verbe = "ne contient pas" if len(surs) == 1 else "ne contiennent pas"
        phrase = f"D'après la fiche, {liste_dite_et(dits)}{entre_autres} {verbe} {_de(mot)}."
        if inconnus:
            phrase += " Pour les autres, je ne peux pas le garantir."
        return _r("OK", faits, phrase)
    nommes = " ".join(_mots_significatifs(reste)) if categories else ""
    debut = f"Je ne peux pas vous garantir de {nommes} sans {mot}" if nommes else f"Je ne peux rien vous garantir sans {mot}"
    if contiennent and not inconnus:
        return _r("OK", faits, f"{debut} : d'après la fiche, il y en a {'dedans' if contiennent == 1 else 'partout'}.")
    return _r("OK", faits, f"{debut} : {_PAS_SUR}")


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
    sans = await _chercher_ce_qui_est_sans(source, p, regles, produit, signale)
    if sans is not None:
        return _avec(sans, p)
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
    if not signale:
        composition = list(fiche.get("ingredients") or [])
        avec = {"option": option["nom"]} if option else {}
        if not composition:
            return _avec(_r("OK", {"article": nom, "renseigne": False, **avec}, NON_CONFIRMABLE), p)
        return _avec(_r("OK", {"article": nom, "renseigne": True, "ingredients": composition, **avec}, f"Dans {nom}, il y a {liste_dite_et(composition)}."), p)
    return _avec(_signalement_dit(source, fiche, option, signale), p)


_NON_GARANTI = "je ne peux pas le garantir : l'équipe peut vous le confirmer."


def _option_signale(o: dict, code: str) -> bool | None:
    """``True`` : l'option porte ``code`` (sa donnée ou son nom le dit) ; ``False`` : sa donnée dit que non ; ``None`` : on ne sait pas."""
    if code in (o.get("signalements_du_nom") or []) or any(s["code"] == code for s in (o.get("signalements") or [])):
        return True
    return False if o.get("signalements") is not None else None


def _options_obligatoires(fiche: dict) -> list[dict]:
    """Les options des choix sans lesquels l'article ne se commande pas (au moins un à prendre)."""
    return [o for _, g in _groupes_a_remplir(fiche, {"choix": []}) if g["min"] >= 1 for o in g["options"] if o["vendable"]]


def _signalement_dit(source: Source, fiche: dict, option: dict | None, signale: str) -> Resultat:
    """La réponse sur UN signalement (ou la liste), l'option dite ou les choix obligatoires compris (M88)."""
    nom = fiche["nom"]
    signalements = fiche.get("signalements")
    libelles = fiche.get("signalements_libelles") or {}
    faits: dict[str, Any] = {"article": nom, **({"option": option["nom"]} if option else {})}
    nom_dit = f"{nom} {option['nom']}" if option else nom
    options = [option] if option else _options_obligatoires(fiche)
    code = source.signalement_dit(signale)
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
        dit = _option_signale(option, code)
        if dit:
            return _r("OK", {**faits, "signalement": "present"}, f"Oui, {nom_dit} contient {libelle}.")
        if signalements is not None and dit is False:
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
# reconnaitre_le_client : le numéro qui s'affiche, ses habitudes (lot 7)
# --------------------------------------------------------------------------- #


async def reconnaitre_le_client(source: Source, p: dict[str, Any], regles: Reglages, confirmer_consignes: bool = False) -> Resultat:
    """Reconnaît l'appelant par le numéro qui s'affiche (jamais un numéro dicté pour une autre personne) dans la fiche du lieu :
    son prénom et ses habitudes (« sonner au 2e »), relues pour qu'il les confirme (« toujours au 2e ? »). Les habitudes confirmées
    (``confirmer_consignes``) sont jointes à la note de la commande. Une habitude est une consigne, jamais une donnée sensible (la fiche la refuse).
    Numéro masqué ou inconnu : rien n'est dit, l'agent continue comme avec n'importe qui."""
    client = p.setdefault("client", {})
    numero = client.get("telephone") or client.get("telephone_affiche")
    if not numero:
        return _avec(_r("OK", {"connu": False, "raison": "numero_masque"}), p)
    connu = await source.client(numero)
    if not connu:
        return _avec(_r("OK", {"connu": False, "raison": "inconnu"}), p)
    prenom = connu.get("prenom")
    consignes = list(connu.get("consignes") or [])
    if prenom and not client.get("prenom"):
        client["prenom"] = prenom
    faits: dict[str, Any] = {"connu": True, "prenom": prenom, "consignes": consignes, "nb_commandes": connu.get("nb_commandes", 0)}
    if confirmer_consignes and consignes:
        joint = " ; ".join(consignes)
        deja = p.get("note") or ""
        if joint not in deja:
            p["note"] = (f"{deja} ; {joint}" if deja else joint)[:300]
        faits["jointes_a_la_commande"] = True
        return _avec(_r("OK", faits, "C'est noté."), p)
    if consignes:
        phrase = ("Bonjour " + prenom + ". " if prenom else "") + "La dernière fois, vous aviez demandé : " + liste_dite_et(consignes) + ". C'est toujours d'actualité ?"
    else:
        phrase = f"Bonjour {prenom}." if prenom else ""
    return _avec(_r("OK", faits, phrase), p)


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
