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
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from api.db.bases_clients import recherche_liste
from api.schemas.apres_appel import numero_e164
from api.db.bases_clients.recherche_liste import Element
from api.services.commande import lecture, panier as P
from api.services.commande.parole import liste_dite, liste_dite_et, montant_en_lettres
from api.services.commande.resultat import Resultat
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
    return recherche_liste.normaliser(trouve["candidats"][0]["libelle"]) == recherche_liste.normaliser(texte)


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


def _phrase_de_la_question(q: dict, article_nom: str) -> str:
    return f"{q['nom']} pour {article_nom} : {liste_dite(q['options'])} ?" if q["options"] else f"Il faut préciser : {q['nom']}."


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


def _appliquer_les_choix(article: dict, ligne: dict, texte: str, *, roles: tuple[str, ...] | None = None, dans: str | None = None) -> Resultat | None:
    """Les choix dits (« sauce barbecue et double fromage ») cherchés DANS les groupes de l'article : jamais ailleurs. ``dans`` : un
    groupe d'abord (la question ouverte). Rend un refus fermé ou ``None`` quand tout est posé."""
    for quantite, morceau, brut in lecture.morceaux_d_options(texte):
        index = _options_disponibles(article, ligne, roles)
        if not index:
            return _r("HORS_CARTE", {"article": ligne["nom"], "raison": "aucun_choix"}, f"{ligne['nom']} ne se prend pas avec des choix.")
        elements = [Element(cle, o["nom"], (), g["nom"]) for cle, (_, g, o) in index.items()]
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


def _appliquer_les_retraits(article: dict, ligne: dict, texte: str) -> Resultat | None:
    retirables = article["retirables"]
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
    return None


async def choisir_mode(source: Source, p: dict[str, Any], regles: Reglages, mode: str | None) -> Resultat:
    """Pose le mode de la commande (les modes sont ceux de la source). Les articles déjà pris sont GARDÉS : on les rechiffre pour
    le nouveau mode, et on dit ceux qui n'y tiennent plus. Un mode fermé n'est jamais posé : la raison fermée est rendue."""
    choisi = _mode_dit(source, mode)
    if choisi is None:
        return _r("ARGUMENT_INVALIDE", {"modes": list(source.modes)}, f"{_phrase_des_modes(source).capitalize()} ?", "mode")
    etat = await source.etat(choisi)
    if not etat["ouvert"]:
        return _avec(
            _r(etat["statut"], {"mode": choisi, **{k: etat.get(k) for k in ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")}}, etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."),
            p,
        )
    essai = copy.deepcopy(p)
    essai["mode"] = choisi
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
        return _avec(_r("OK", faits, source.question_de_la_zone, "zone"), p)
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
    return _avec(Resultat(r.statut, faits, r.suggestion, r.manque), p)


async def resoudre_une_date(source: Source, p: dict[str, Any], regles: Reglages, texte: str | None, heure: str | None = None) -> Resultat:
    """La date (et l'heure) dites, résolues par le code vers l'avenir, au jour et au fuseau du lieu. Sûres : ``RETENU`` avec ``faits.heure_voulue`` (ISO,
    à donner à ``finaliser``). Un doute est rendu en candidats à confirmer ; rien n'est jamais choisi en silence. Ne change pas la commande."""
    return _avec(await source.resoudre_une_date((texte or "").strip(), (heure or "").strip() or None), p)


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


async def _un_article(
    source: Source, p: dict[str, Any], regles: Reglages, quantite: int, texte: str, *, choix: str | None, sans: str | None, note: str | None,
    moities: str | None, tout_seul: bool, brut: str | None = None,
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
    if trouve is None:
        trouve = await source.chercher(texte)
    if trouve.statut == "AMBIGU":
        noms = [c["libelle"] for c in trouve.faits.get("candidats", [])]
        return _r("AMBIGU", {"candidats": noms, "dit": texte}, trouve.suggestion or "Vous voulez dire : " + liste_dite(noms) + " ?")
    if trouve.statut != "RETENU":
        proches = [c["libelle"] for c in trouve.faits.get("candidats", [])][:3]
        return _r(
            "INTROUVABLE", {"dit": texte, "plus_proches": proches},
            f"Je ne trouve pas « {texte} »." + (f" Le plus proche : {liste_dite(proches)}." if proches else ""),
        )
    article = await source.article(trouve.faits["retenu"], p["mode"])
    if article is None:
        return _r("INTROUVABLE", {"dit": texte}, f"« {texte} » n'est pas disponible en ce moment.")
    declinaison = _declinaison_dite(article, trouve.faits)
    ligne: dict[str, Any] = {
        "n": 0, "ref": article["id"], "nom": article["nom"], "code": None, "quantite": quantite, "choix": [], "retires": [], "note": None,
        "attente": None, "declinaison_dite": ((trouve.faits.get("options") or {}).get("variante")),
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
    if ligne["code"]:
        _appliquer_les_defauts(article, ligne)
    if not tout_seul and (choix or sans or note or moities):
        return _r("ARGUMENT_INVALIDE", {}, "Prenons les articles un par un pour les choix.", "articles")
    for texte_choix, roles in ((moities, ("moities",)), (choix, None)):
        if texte_choix and ligne["code"]:
            erreur = _appliquer_les_choix(article, ligne, texte_choix, roles=roles)
            if erreur:
                return erreur
        elif texte_choix:
            ligne["choix_a_poser"] = (ligne.get("choix_a_poser") or []) + [texte_choix]
    if sans:
        erreur = _appliquer_les_retraits(article, ligne, sans)
        if erreur:
            return erreur
    erreur = _noter(ligne, note or "", regles)
    if erreur:
        return erreur
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
    if chiffre.statut != "OK":
        return _avec(chiffre, p)
    _valider(p, essai)
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
        return manque
    pieces = lecture.decouper(articles or "")
    if not pieces:
        return await _repondre(source, p, regles, choix=choix, sans=sans, note=note, moities=moities)
    if len(pieces) > 1:
        # Un nom qui contient « et » : le texte entier est essayé d'abord, et pris seulement s'il est certain (zéro faux sûr).
        entier = lecture.sans_quantite(articles or "")
        trouve = await source.chercher(entier)
        if _est_le_nom({"statut": trouve.statut, "candidats": trouve.faits.get("candidats")}, entier):
            q, reste = lecture.une_quantite(lecture.en_chiffres((articles or "").strip()))
            pieces = [lecture.Morceau(q, reste, reste)]
    ajoutes: list[str] = []
    probleme: Resultat | None = None
    for quantite, texte, brut in pieces:
        r = await _un_article(source, p, regles, quantite, texte, choix=choix, sans=sans, note=note, moities=moities, tout_seul=len(pieces) == 1, brut=brut)
        if r.statut == "OK":
            ajoutes.append(r.faits["ajoute"])
        elif probleme is None:
            probleme = r
    faits = {"ajoutes": ajoutes}
    if probleme is not None:
        return _avec(Resultat(probleme.statut, {**probleme.faits, **faits}, probleme.suggestion, probleme.manque), p)
    return _avec(await _etat_apres_ajout(source, p, regles, faits), p)


async def _etat_apres_ajout(source: Source, p: dict[str, Any], regles: Reglages, faits: dict[str, Any]) -> Resultat:
    en_attente = P.a_completer(p)
    if en_attente:
        q = en_attente[0]["attente"]
        return _r("CHOIX_OBLIGATOIRE", {**faits, "article": en_attente[0]["nom"], "question": q}, _phrase_de_la_question(q, en_attente[0]["article_nom"]), q["nom"])
    chiffre = await _chiffrer(source, p, regles)
    return _r("OK", {**faits, "total": chiffre.faits.get("total"), "sous_total": chiffre.faits.get("sous_total"), "frais": chiffre.faits.get("frais")}, "")


async def _repondre(source: Source, p: dict[str, Any], regles: Reglages, *, choix: str | None, sans: str | None, note: str | None, moities: str | None) -> Resultat:
    """Pas d'article dit : la réponse à la question ouverte, ou un choix, un retrait, une note sur la dernière ligne."""
    if not (choix or sans or note or moities):
        return _avec(_r("INCOMPLETE", {}, "Qu'est-ce que je vous mets ?", "articles"), p)
    cible = (P.a_completer(p) or p["lignes"][-1:] or [None])[0]
    if cible is None:
        return _avec(_r("INCOMPLETE", {}, "Qu'est-ce que je vous mets ?", "articles"), p)
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
        cherchee = _chercher_dans([Element(d["nom"], d["nom"]) for d in article["declinaisons"]], choix)
        trouve = next((d for d in article["declinaisons"] if d["nom"] == cherchee["retenu"]), None) if cherchee["statut"] == "RETENU" else None
        if trouve is None:
            return _avec(_r("CHOIX_OBLIGATOIRE", {"article": ligne["nom"], "question": attente}, _phrase_de_la_question(attente, article["nom"]), attente["nom"]), p)
        if not trouve["vendable"] or trouve["rupture"]:
            return _avec(_r("RUPTURE", {"nom": f"{article['nom']} {trouve['nom']}"}, f"{article['nom']} {trouve['nom']} n'est plus disponible."), p)
        ligne["code"] = trouve["code"]
        if len(article["declinaisons"]) > 1:
            ligne["nom"] = f"{article['nom']} {trouve['nom']}"
        choix = None
        _appliquer_les_defauts(article, ligne)
        for texte_en_attente in ligne.pop("choix_a_poser", []):
            erreur = _appliquer_les_choix(article, ligne, texte_en_attente)
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
    if chiffre.statut != "OK":
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
    voulus = {m for m in recherche_liste.normaliser(texte).split() if m not in _PETITS_MOTS}
    correspond = [
        l for l in p["lignes"]
        if voulus and voulus <= set(recherche_liste.normaliser(l["nom"] + " " + " ".join(c.get("nom", "") for c in l["choix"])).split())
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
    P.toucher(essai)
    _valider(p, essai)
    return _avec(_r("OK", {"vide": True}, ""), p)


def _phrase_des_lignes(lignes: list[dict[str, Any]]) -> str:
    from api.services.commande.parole import _lettres

    morceaux = []
    for l in lignes:
        morceau = f"{_lettres(l['quantite'])} {l['nom']}"
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
    total = None if en_attente else chiffre.faits["total"]
    phrase = f"Vous avez {_phrase_des_lignes(P.lignes_pretes(p))}."
    if total is not None:
        phrase += f" Cela fait {montant_en_lettres(total)}."
    remises = chiffre.faits.get("remises") or []
    if remises and total is not None:
        phrase += f" Avec {liste_dite_et([r['nom'] for r in remises])}, vous économisez {montant_en_lettres(chiffre.faits['total_remises'])}."
    return _avec(
        _r(
            "OK",
            {
                "lignes": lignes, "sous_total": chiffre.faits["sous_total"], "frais": chiffre.faits["frais"], "total": total,
                "remises": [{"nom": r["nom"], "montant": r["montant"]} for r in remises], "total_remises": chiffre.faits.get("total_remises", 0),
                "offerts": chiffre.faits.get("offerts") or [],
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
    return [{"cle": list(_cle_de_ligne(l)), "nom": l["nom"], "quantite": l["quantite"]} for l in P.lignes_pretes(p)]


def _ce_qui_a_change(avant: list[dict[str, Any]], apres: list[dict[str, Any]]) -> list[str]:
    from api.services.commande.parole import _lettres

    anciens = {tuple(map(str, a["cle"])): a for a in avant}
    nouveaux = {tuple(map(str, a["cle"])): a for a in apres}
    dits: list[str] = []
    for cle, n in nouveaux.items():
        a = anciens.get(cle)
        if a is None:
            dits.append(f"on ajoute {_lettres(n['quantite'])} {n['nom']}")
        elif a["quantite"] != n["quantite"]:
            dits.append(f"{n['nom']} passe à {_lettres(n['quantite'])}")
    for cle, a in anciens.items():
        if cle not in nouveaux:
            dits.append(f"on retire {a['nom']}")
    return dits


async def _le_reglement(source: Source, p: dict[str, Any], total: int, brut: dict[str, Any]) -> tuple[dict | None, Resultat | None]:
    """Le règlement tel que dit : un moyen, ou une part en un moyen et le reste en un autre (titres, puis espèces sur un billet). Le code
    calcule le reste et la monnaie ; il refuse un moyen non accepté. ``(paiement, None)`` ou ``(None, refus)``."""
    reglages = await source.reglages()
    acceptes = reglages["moyens_paiement"]
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


def _ecrire_la_relecture(source: Source, p: dict[str, Any], chiffre: Resultat, paiement: dict[str, Any], garde_le_numero: bool) -> Resultat:
    """La relecture : tout la première fois, seulement ce qui a changé après une correction. Un jeton en prouve la lecture."""
    avant, maintenant = p.get("derniere_lecture"), _instantane(p)
    total = chiffre.faits["total"]
    if avant and p.get("derniere_lecture_mode") == p["mode"]:
        changes = _ce_qui_a_change(avant, maintenant)
        phrase = (liste_dite_et(changes).capitalize() + ". " if changes else "") + f"Cela fait maintenant {montant_en_lettres(total)}. C'est bon ?"
    else:
        phrase = f"Je vous relis : {_phrase_des_lignes(P.lignes_pretes(p))}"
        if p["mode"]:
            phrase += f", {source.libelles_des_modes.get(p['mode'], p['mode'])}"
        remises = chiffre.faits.get("remises") or []
        offerts = chiffre.faits.get("offerts") or []
        if offerts:
            phrase += ", plus " + _phrase_des_lignes([{"quantite": o["quantite"], "nom": o["nom"], "choix": [], "retires": []} for o in offerts]) + " offert"
        if remises:
            phrase += ", avec " + liste_dite_et([r["nom"] for r in remises])
        phrase += f". Cela fait {montant_en_lettres(total)}. {_phrase_du_reglement(source, paiement)}"
        if garde_le_numero:
            phrase += " Je garde le numéro qui s'affiche pour la commande, en cas de souci."
        phrase += " C'est bon ?"
    p["relecture"] = {"empreinte": P.empreinte(p), "jeton": uuid.uuid4().hex, "version": p["version"]}
    p["derniere_lecture"], p["derniere_lecture_mode"] = maintenant, p["mode"]
    return _avec(
        _r("INCOMPLETE", {"total": total, "lignes": [{"nom": l["nom"], "quantite": l["quantite"]} for l in P.lignes_pretes(p)], "a_confirmer": True}, phrase, "relecture"),
        p, total=total,
    )


async def finaliser(
    source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, *, prenom: str | None = None, telephone: str | None = None,
    second_numero: str | None = None, second_qui: str | None = None, second_pourquoi: str | None = None, moyen: str | None = None,
    part: Any = None, moyen_reste: str | None = None, rendu_sur: Any = None, note: str | None = None, consigne: str | None = None,
    confirmer: bool = False, heure_voulue: str | None = None,
) -> Resultat:
    """Conduit la commande jusqu'à son enregistrement, UN manque à la fois dans l'ordre : articles et choix, ouverture, une offre en plus (une
    fois), prénom, numéro (jamais redemandé quand il s'affiche), règlement, puis la RELECTURE. L'enregistrement n'a lieu que sur ``confirmer`` après
    une relecture valide ; une correction invalide la relecture et seul ce qui a changé est relu. Le total est celui de la source."""
    deja = p.get("enregistree")
    if deja and p["lignes"]:
        return _avec(Resultat("DEJA_FAIT", dict(deja), "Votre commande est déjà enregistrée."), p)
    manque = await _prealables(source, p, regles)
    if manque is not None:
        return manque
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
        try:
            voulue = datetime.fromisoformat(heure_voulue)
        except ValueError:
            return _avec(_r("ARGUMENT_INVALIDE", {}, "À quelle heure exactement ?", "heure_voulue"), p)
        if voulue.tzinfo is None:
            return _avec(_r("ARGUMENT_INVALIDE", {}, "À quelle heure exactement ?", "heure_voulue"), p)
        p["heure_voulue"] = voulue.isoformat()
    etat = await source.etat(p["mode"])
    if not etat["ouvert"] and not p.get("heure_voulue"):
        return _avec(
            _r(etat["statut"], {k: etat.get(k) for k in ("raison", "reprise", "prochaine_ouverture", "planifiee_permise")}, etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."),
            p,
        )
    if regles.vente_en_plus and not p["vente_en_plus_faite"]:
        p["vente_en_plus_faite"] = True  # une seule fois par commande, jamais redemandée
        return _avec(_r("INCOMPLETE", {}, "Souhaitez-vous ajouter quelque chose avec cela ?", "vente_en_plus"), p)
    client = p["client"]
    if prenom and prenom.strip():
        client["prenom"] = " ".join(prenom.split())[:60]
    numero = numero_e164(telephone) if telephone else None
    if telephone and numero is None:
        return _avec(_r("ARGUMENT_INVALIDE", {}, "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", "telephone"), p)
    numero = numero or client.get("telephone") or appelant.telephone_affiche
    garde_le_numero = bool(numero and numero == appelant.telephone_affiche and not telephone)
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
        second = numero_e164(second_numero)
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
    valide = bool(relue and relue["empreinte"] == P.empreinte(p))
    if regles.relecture_en_deux_temps and not (confirmer and valide):
        return _ecrire_la_relecture(source, p, chiffre, paiement, garde_le_numero)
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
        p["enregistree"] = faits
        statut = source.statut_de_l_enregistrement() if r.statut == "ENREGISTREE" else "DEJA_FAIT"
        return _avec(Resultat(statut, faits, r.suggestion), p)
    if r.statut == "INCOMPLETE" and r.manque == "relecture":
        return _ecrire_la_relecture(source, p, chiffre, paiement, garde_le_numero)
    return _avec(r, p)


# --------------------------------------------------------------------------- #
# remises_disponibles : la parole des remises (lot 7, T-08)
# --------------------------------------------------------------------------- #


def _phrase_d_une_remise_appliquee(r: dict[str, Any]) -> str:
    return r.get("phrase") or f"Bonne nouvelle : {r['nom']}, cela vous fait {montant_en_lettres(r['montant'])} de moins."


async def remises_disponibles(
    source: Source, p: dict[str, Any], regles: Reglages, *, demande: bool = False, presse: bool = False, refus: bool = False
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
        phrase = "En ce moment : " + liste_dite_et([r["phrase"] or r["nom"] for r in en_cours]) + "."
        return _avec(_r("OK", {"a_dire": True, "remises": dites, "appliquees": [r["nom"] for r in appliquees]}, phrase), p)
    if p.get("remise_refusee"):
        return _avec(_r("OK", {"a_dire": False, "raison": "refusee"}), p)
    if presse:
        return _avec(_r("OK", {"a_dire": False, "raison": "presse"}), p)
    if p["mentions_de_remise"] >= regles.mentions_de_remise:
        return _avec(_r("OK", {"a_dire": False, "raison": "deja_dite"}), p)
    for r in appliquees:
        if r["ref"] not in p["remises_dites"]:
            p["mentions_de_remise"] += 1
            p["remises_dites"].append(r["ref"])
            return _avec(_r("OK", {"a_dire": True, "moment": "appliquee", "remise": {"nom": r["nom"], "montant": r["montant"]}}, _phrase_d_une_remise_appliquee(r)), p)
    sous_total = chiffre.faits["sous_total"] if chiffre is not None and chiffre.statut == "OK" else 0
    for r in en_cours:
        minimum = r.get("minimum")
        if minimum and r["ref"] not in p["remises_dites"] and sous_total and minimum * 7 // 10 <= sous_total < minimum:
            p["mentions_de_remise"] += 1
            p["remises_dites"].append(r["ref"])
            reste = minimum - sous_total
            return _avec(
                _r("OK", {"a_dire": True, "moment": "seuil_presque_atteint", "remise": {"nom": r["nom"], "manque": reste}},
                   f"Il vous manque {montant_en_lettres(reste)} pour avoir {r['nom']}."),
                p,
            )
    return _avec(_r("OK", {"a_dire": False, "raison": "rien_a_dire"}), p)


# --------------------------------------------------------------------------- #
# voir_produit : la composition et les signalements d'un article (lot 7, E-14, E-15)
# --------------------------------------------------------------------------- #

NON_CONFIRMABLE = "Je ne peux pas vous le confirmer."


async def voir_produit(source: Source, p: dict[str, Any], regles: Reglages, produit: str | None, signale: str | None = None) -> Resultat:
    """Ce que le catalogue dit d'UN article.

    - sans ``signale`` : sa composition (« il y a quoi dans la Reine »), rien d'autre : un signalement n'est jamais donné de soi-même ;
    - avec ``signale`` (l'appelant parle d'une sensibilité) : seulement ce signalement-là, d'après la fiche.

    Une donnée absente est INCONNUE, jamais « sans » : « je ne peux pas vous le confirmer », sans passer la main (E-15). Une fiche qui dit
    la liste (même vide) permet de dire qu'elle ne contient pas la chose demandée, en précisant que c'est la fiche qui le dit."""
    if not produit or not produit.strip():
        return _r("ARGUMENT_INVALIDE", {}, "De quel article parlez-vous ?", "produit")
    trouve = await source.chercher(produit.strip())
    if trouve.statut != "RETENU":
        return _avec(trouve, p)
    fiche = await source.article(trouve.faits["retenu"], p.get("mode") or source.modes[0])
    if fiche is None:
        return _avec(_r("INTROUVABLE", {}, "Je ne trouve pas cet article."), p)
    nom = fiche["nom"]
    if not signale:
        composition = list(fiche.get("ingredients") or [])
        if not composition:
            return _avec(_r("OK", {"article": nom, "renseigne": False}, NON_CONFIRMABLE), p)
        return _avec(_r("OK", {"article": nom, "renseigne": True, "ingredients": composition}, f"Dans {nom}, il y a {liste_dite_et(composition)}."), p)
    signalements = fiche.get("signalements")
    if signalements is None:
        return _avec(_r("OK", {"article": nom, "signalement": "inconnu"}, NON_CONFIRMABLE), p)
    code = source.signalement_dit(signale)
    libelles = fiche.get("signalements_libelles") or {}
    if code is None:
        presents = [s["libelle"] for s in signalements]
        return _avec(
            _r("OK", {"article": nom, "signalement": "liste", "presents": presents},
               (f"D'après la fiche, {nom} contient {liste_dite_et(presents)}." if presents else f"D'après la fiche, {nom} n'en déclare aucun.")),
            p,
        )
    libelle = libelles.get(code, code)
    if any(s["code"] == code for s in signalements):
        return _avec(_r("OK", {"article": nom, "signalement": "present", "code": code}, f"Oui, {nom} contient {libelle}."), p)
    return _avec(_r("OK", {"article": nom, "signalement": "absent_de_la_fiche", "code": code}, f"D'après la fiche, {nom} ne contient pas {libelle}."), p)


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
