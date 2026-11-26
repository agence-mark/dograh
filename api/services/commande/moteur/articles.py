"""[.mark] Moteur de la commande : les articles : le catalogue, les choix, les retraits, l'ajout, la modification, le retrait et le vidage des lignes.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import copy
import re
from typing import Any
from loguru import logger

from api.db.bases_clients import recherche_liste
from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_moteur import norme_de_recherche
from api.services.commande import lecture, panier as P, tailles, textes_de_secours as TS
from api.services.commande.briques import conditions_de_vente, declinaison_nommee, taille_fixant_le_nombre, menu_a_composition_fixe, formule_a_etapes, menu_a_taille_liee, menu_pour_n_personnes, choix_entre_deux_contenus, a_volonte, inconnue, code_de_remise, choix_unique_obligatoire, option_conditionnelle, hors_jours_feries, produit_alcoolise, produit_au_poids, lot_de_vente, taille
from api.services.commande.briques import formule as FO
from api.services.mots_dits import liste_dite_et, nom_dit
from api.services.commande.resultat import Resultat
from api.services.actions_communes.petits_mots import LIAISON_D_UNE_COMPOSITION, RENVOI_A_UNE_LIGNE
from api.services.commande.source import Source
from api.services.commande.moteur.socle import LONGUEUR_NOTE, Reglages, _avec, phrase_d_une_remise_appliquee, _r, _sans_accent
from api.services.commande.moteur.prealables import _article_de_la_carte, chiffrer_le_panier, _prealables, _servi_le, _valider


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
            if not option_conditionnelle.brique_opt6_poser_b_si_a(g, choisis):
                continue  # OPT6 : un groupe conditionnel n'existe que si l'option qui l'ouvre est choisie
            sortie.append((chemin, g))
            for o in g["options"]:
                deja = next((c for c in choisis if c["option_code"] == o["code"] and FO.du_groupe(c, g)), None)
                if deja is not None and o["enfants"]:
                    descendre(o["enfants"], chemin + (o["code"],), deja["choix"])

    # DEC2 : les groupes de l'article tels que la déclinaison de la ligne les veut (minimum et maximum de sa taille)
    declinaison = next((d for d in article["declinaisons"] if d["code"] and d["code"] == ligne.get("code")), None)
    descendre(taille_fixant_le_nombre.appliquer_les_quotas(article["groupes"], declinaison), (), ligne["choix"])
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
        return declinaison_nommee.brique_dec1_demander_la_declinaison(article["declinaisons"])
    for chemin, g in _groupes_a_remplir(article, ligne):
        if FO.est_une_etape(g) and _compte(ligne, chemin, g) < choix_entre_deux_contenus.minimum_de_l_etape(g, [c for c in _niveau(ligne["choix"], chemin) if FO.du_groupe(c, g)]):
            return formule_a_etapes.brique_for2_une_etape_a_la_fois(g, list(chemin))  # FOR2 : une étape à la fois ; FOR12 : remplie à la quantité de l'alternative prise
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


def _phrase_de_la_question(q: dict, article_nom: str) -> str:
    """Le texte de secours de la question d'un choix (``TS.question_d_un_choix``) pour une question et le nom de l'article de la carte."""
    return TS.question_d_un_choix({"question": q, "article_de_la_carte": article_nom})


def choix_obligatoire(faits: dict) -> Resultat:
    """La question ouverte d'un choix (taille, groupe, étape) : ses faits portent ``question`` et ``article_de_la_carte`` (le nom de l'article, sans la taille de la ligne)."""
    return _r("CHOIX_OBLIGATOIRE", faits, _phrase_de_la_question(faits["question"], faits["article_de_la_carte"]), faits["question"]["nom"])


def _appliquer_les_defauts(article: dict, ligne: dict) -> None:
    """Les options pré-cochées d'un groupe obligatoire sont prises d'office (la sauce de base) ; l'appelant peut en changer."""
    for chemin, g in _groupes_a_remplir(article, ligne):
        if g["min"] >= 1 and _compte(ligne, chemin, g) == 0:
            for o in choix_unique_obligatoire.brique_opt1_choix_obligatoire(g):  # le défaut du groupe, ou celui de l'option : une seule règle (OPT1)
                if _compte(ligne, chemin, g) < g["max"]:
                    # FOR8, FOR14 : le seul choix d'une étape est posé d'office à la quantité de l'étape (huit pièces du plateau)
                    _niveau(ligne["choix"], chemin).append(FO.choix_d_etape(g, o, g["min"]) if FO.est_une_etape(g)
                                                           else {"option_code": o["code"], "nom": o["nom"], "quantite": 1, "choix": []})


def _choisir(ligne: dict, chemin: tuple[str, ...], groupe: dict, option: dict, quantite: int) -> Resultat | None:
    """Pose ``quantite`` de cette option. Un choix unique (obligatoire, un seul) est REMPLACÉ (changement d'avis) ; sinon les maximums du
    groupe et de l'option sont respectés. ``None`` : posé."""
    if option["rupture"]:
        faits = {"nom": option["nom"], "code": option["code"]}
        return _r("RUPTURE", faits, "")
    niveau = _niveau(ligne["choix"], chemin)
    if groupe["max"] == 1 and (groupe["min"] >= 1 or FO.est_une_etape(groupe)):
        return remplacer_un_choix(niveau, groupe, option)
    existant = next((c for c in niveau if c["option_code"] == option["code"] and FO.du_groupe(c, groupe)), None)
    total_groupe = _compte(ligne, chemin, groupe)
    nouvelle = (existant["quantite"] if existant else 0) + quantite
    if total_groupe + quantite > groupe["max"] or nouvelle > groupe["max_par_option"]:
        faits = {
            "groupe": groupe["nom"], "option": option["nom"], "maximum": groupe["max"], "maximum_par_option": groupe["max_par_option"],
            "maximum_atteint": groupe["max"] if total_groupe + quantite > groupe["max"] else groupe["max_par_option"],  # le nombre que le refus dit
        }
        return _r("MAXIMUM_ATTEINT", faits, "")
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
            faits = {"article": ligne["nom"], "raison": "aucun_choix"}
            return _r("HORS_CARTE", faits, "")
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
            faits = {"candidats": noms, "dit": morceau, CLE_OPTION_DITE: morceau}
            return _r("AMBIGU", faits, TS.vous_voulez_dire(faits))
        if trouve["statut"] != "RETENU":
            proches = [index[c["id"]][2] for c in trouve["candidats"] if c["id"] in index]
            suppl = [o for c in trouve["candidats"] if c["id"] in index for o in [index[c["id"]][2]] if index[c["id"]][1]["role"] == "supplement"]
            propose = suppl or proches
            faits = {"article": ligne["nom"], "dit": morceau, "plus_proches": [{"nom": o["nom"], "prix": o["prix"]} for o in propose[:3]]}
            if not propose:
                faits["choix_possibles"] = _ce_qui_se_choisit(index)  # aucune option proche du mot dit : ce que l'article propose
            return _r("HORS_CARTE", faits, "")
        chemin, g, o = index[trouve["retenu"]]
        refus = _choisir(ligne, chemin, g, o, quantite)
        if refus is not None:
            return refus
    return None


def _ce_qui_se_choisit(index: dict) -> list[str]:
    """Aucune option proche du mot dit : ce que l'article propose (DEC4, conversation du 19/11), au plus quatre noms."""
    return list(dict.fromkeys(o["nom"] for _, (_, _, o) in index.items()))[:4]


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
        faits = {"article": ligne["nom"], **refus}
        return _r("INCOMPLETE", faits, "", "etape"), None
    faits = {"article": ligne["nom"], **{k: v for k, v in refus.items() if k != "prix_max"}, **({"regle_prix_max": refus["prix_max"]} if refus.get("prix_max") else {})}
    return _r("HORS_CARTE", faits, ""), None


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
            faits = {"candidats": noms, "dit": morceau}
            return _r("AMBIGU", faits, TS.sur_lequel(faits))
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
        apres, refus = menu_a_taille_liee.brique_for6_passer_en_maxi(g, dans, taille)
        if refus is None:
            apres, refus = choix_entre_deux_contenus.brique_for12_une_alternative(g, apres)
        if refus is not None and refus["raison"] == choix_entre_deux_contenus.RAISON:
            faits = {"article": ligne["nom"], **refus}
            return _r("HORS_CARTE", faits, "")
        if refus is not None:
            faits = {"article": ligne["nom"], **refus}
            return _r("HORS_CARTE", faits, "")
        apres = a_volonte.brique_for15_a_volonte(g, apres)
        ligne["choix"] = [c for c in ligne["choix"] if c not in dans] + apres
    return None


def _moities_choisies(article: dict, ligne: dict) -> list[str]:
    """Les noms des moitiés déjà choisies sur la ligne (les options des groupes de rôle ``moities``)."""
    noms: list[str] = []
    for chemin, g in _groupes_a_remplir(article, ligne):
        if g.get("role") != "moities":
            continue
        codes = {o["code"] for o in g["options"]}
        noms += [c["nom"] for c in _niveau(ligne["choix"], chemin) if c["option_code"] in codes and c.get("nom")]
    return noms


# C6 n° 4 : la note d'un retrait sur une moitié, écrite sur la ligne pour la cuisine (caisse, ticket) ; jamais dite par le code : la relecture la donne au modèle en fait (``note`` de la ligne).
NOTE_DE_MOITIE = "sans {ingredient} sur la moitié {moitie}"
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
            faits = {"raison": "retrait_sans_ingredient"}
            return _r("INCOMPLETE", faits, "")
        if moitie is None:
            faits = {"candidats": list(moities), "dit": ingredient}
            return _r("AMBIGU", faits, TS.sur_quelle_moitie(faits))
        notes.append(NOTE_DE_MOITIE.format(ingredient=ingredient, moitie=moitie))
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
            faits = {"candidats": noms, "dit": morceau}
            return _r("AMBIGU", faits, TS.vous_voulez_retirer(faits))
        if trouve["statut"] != "RETENU":
            faits = {"article": ligne["nom"], "dit": morceau, "retirables": list(retirables)}
            return _r("HORS_CARTE", faits, "")
        if trouve["retenu"] not in ligne["retires"]:
            ligne["retires"].append(trouve["retenu"])
    return None


def _noter(ligne: dict, note: str, regles: Reglages) -> Resultat | None:
    note = " ".join((note or "").split())
    if not note:
        return None
    if not regles.notes_libres:
        faits = {"raison": "notes_non_acceptees"}
        return _r("HORS_CARTE", faits, "")
    ligne["note"] = (f"{ligne['note']} ; {note}" if ligne.get("note") else note)[:LONGUEUR_NOTE]
    return None


def noter_la_commande(p: dict[str, Any], regles: Reglages, texte: str | None) -> Resultat | None:
    """Lot 4 (E-35) : la note de toute la commande (la case ``note_generale``), sous la même règle que la note d'une ligne : refusée quand le
    réglage des notes libres est éteint (rien n'est noté), sinon posée. ``None`` : posée, ou rien à noter."""
    note = " ".join(str(texte or "").split())
    if not note:
        return None
    if not regles.notes_libres:
        faits = {"raison": "notes_non_acceptees"}
        return _avec(_r("HORS_CARTE", faits, ""), p)
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
    verdict = code_de_remise.brique_off3_verifier_le_code(dit, await lecture())
    if "raison" in verdict:
        faits = {"raison": code_de_remise.RAISON, "dit": verdict["dit"]}
        return _avec(_r("HORS_CARTE", faits, ""), p)
    if verdict["code"] not in p.setdefault("codes_dits", []):
        p["codes_dits"].append(verdict["code"])
    if verdict["ref"] not in p.setdefault("remises_du_code", []):
        p["remises_du_code"].append(verdict["ref"])  # ce que le code a donné droit : sa remise se dit au moment où elle s'applique (``porte.poser_la_remise_du_code``)
    chiffre = await chiffrer_le_panier(source, p, regles) if p["lignes"] and p["mode"] and not P.a_completer(p) else None
    appliquee = next((r for r in (chiffre.faits.get("remises") or []) if r["ref"] == verdict["ref"]), None) if chiffre is not None and chiffre.statut == "OK" else None
    faits = {"code": verdict["code"], "remise": verdict["nom"], "appliquee": appliquee is not None}
    if appliquee is None:
        return _avec(_r("OK", faits, ""), p)
    return _avec(_r("OK", {**faits, "reduction": appliquee["montant"]}, phrase_d_une_remise_appliquee(appliquee)), p)


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


async def chercher_l_article(source: Source, texte: str, regles: Reglages) -> Resultat:
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
    faits = {"dit": dit, quoi: noms}
    return _r("INCOMPLETE", faits, "", "articles")


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


def _ambigu_de_la_carte(texte: str, trouve: Any) -> Resultat:
    """Plusieurs articles de la carte portent ce que la personne a dit : la question « Vous voulez dire… ? ». Les candidats sont gardés avec la question par libellé ET par
    identifiant (deux articles peuvent porter le même libellé) ; le modèle ne voit que les libellés."""
    noms = [c["libelle"] for c in trouve.faits.get("candidats", [])]
    retenus = [{"libelle": c["libelle"], "id": c["id"]} for c in trouve.faits.get("candidats", []) if c.get("id")]
    faits = {"candidats": noms, "dit": texte, CLE_CANDIDATS: retenus}
    return _r("AMBIGU", faits, trouve.suggestion or TS.vous_voulez_dire(faits))


async def _un_article(
    source: Source, p: dict[str, Any], regles: Reglages, quantite: int, texte: str, *, variante: str | None = None, choix: str | None = None,
    sans: str | None = None, note: str | None = None, moities: str | None = None, personnes: Any = None, poids: Any = None, ref: str | None = None,
) -> Resultat:
    """Un article de la fiche, structuré (son nom, sa quantité, sa variante, ses choix, ses retraits, sa note, ses moitiés) : le cherche, compose sa
    ligne, la complète ou en garde la question, la chiffre. Rien n'est posé sur un refus ; la variante n'est jamais lue dans les choix (M24)."""
    if not variante:
        # La taille collée au nom (« reine normale », B12 décision 2) : le produit plus sa variante, jamais une variante déjà dans la fiche remplacée
        collee = await taille.lire_la_taille_collee_au_nom(source, texte, p.get("mode") or source.modes[0])
        if collee is not None:
            texte, variante = collee
    # B5 (N1) : le candidat choisi à la question est pris par son identifiant ; la recherche n'est jamais rejouée sur son nom (la boucle « Kebab »)
    trouve = Resultat("RETENU", {"retenu": ref}, "") if ref else await chercher_l_article(source, texte, regles)
    trouve, dit_en_plus = await _un_seul_candidat(source, trouve, texte)
    if personnes is not None and trouve.statut == "AMBIGU" and len(trouve.faits.get("candidats") or []) == 1:
        # FOR10 (conversation FOR10-A du lot 11) : « seau pour quatre personnes » écrit dans ``article`` AVEC ``personnes`` : le seul candidat, vendu par
        # personnes, est retenu ; le reste des mots est le nombre, déjà dans sa sous-case
        seul = trouve.faits["candidats"][0]["id"]
        if menu_pour_n_personnes.vendu_par_personnes(await _article_de_la_carte(source, p, seul, p["mode"])):
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
        retenu = menu_a_composition_fixe.brique_for1_departager_par_la_composition(candidats, [m for _, m, _ in lecture.morceaux_d_options(choix)])
        if retenu is not None:
            trouve = Resultat("RETENU", {**{k: v for k, v in trouve.faits.items() if k != "rangements"}, "retenu": retenu}, "")
    elif trouve.statut == "AMBIGU" and not choix:
        # FOR1 : la formule et des choix certains de ses étapes parmi les candidats (toute la phrase écrite dans ``article``) : la formule, les autres y sont rangés
        libelles = {c["id"]: c["libelle"] for c in trouve.faits.get("candidats", [])}
        candidats = [(i, await _article_de_la_carte(source, p, i, p["mode"])) for i in libelles]
        formule_et_choix = menu_a_composition_fixe.brique_for1_formule_des_candidats(candidats, libelles)
        if formule_et_choix is not None:
            choix = ", ".join(formule_et_choix[1])
            trouve = Resultat("RETENU", {**trouve.faits, "retenu": formule_et_choix[0]}, "")
    # B5 (N1) : la rustine du lot 20 (le nom exact retenu ici, après la recherche) est retirée : elle rendait sûr à tort ce que la recherche, mesurée
    # à zéro faux sûr, demande (« pesto » : la pizza Pesto et les pâtes au pesto, deux rangements). La boucle « Kebab » se règle là où elle naissait :
    # la réponse « Kebab » à « Vous voulez dire… ? » choisit le candidat de même nom (``porte._repondre_a_l_hesitation``).
    if trouve.statut == "AMBIGU":
        return _ambigu_de_la_carte(texte, trouve)
    if trouve.statut != "RETENU" and trouve.faits.get("rangements"):
        return _question_de_rangement(texte, trouve.faits["rangements"])
    if trouve.statut != "RETENU":
        proches = list(dict.fromkeys(c["libelle"] for c in trouve.faits.get("candidats", [])))[:3]  # deux entrées de la carte au même libellé : un seul nom proposé
        faits = {"dit": texte, "plus_proches": proches}
        return _r("INTROUVABLE", faits, "")
    article = await _article_de_la_carte(source, p, trouve.faits["retenu"], p["mode"])
    if article is None:
        faits = {"dit": texte, "pas_servi_maintenant": True}
        return _r("INTROUVABLE", faits, "")
    # Lot 12 (PRX1, PRX3, PRX8) : hors de sa plage à ce moment, d'un autre mode, au-delà du maximum par commande : refusé dès l'ajout, avec les faits (jamais une phrase)
    deja_pris = sum(int(l["quantite"]) for l in p["lignes"] if l.get("ref") == article["id"])
    refus_de_la_carte = conditions_de_vente.refus_de_la_ligne(article, None, p.get("mode"), quantite, deja_pris, None, None)
    if refus_de_la_carte is not None:
        return _r("INTERDIT", refus_de_la_carte, "")
    # Lot 13 (QTE2) : un lot de vente se dit en pièces ; la ligne compte des lots. (QTE1) : un article au poids se pose avec son poids, que le code lit et chiffre.
    lot = lot_de_vente.brique_qte2_multiple_du_lot(article, quantite)
    if lot.get("raison"):
        return _r("INTERDIT", lot, "")
    quantite = lot.get("lots", quantite)
    if quantite > lecture.QUANTITE_MAX:  # C4 : le plafond s'applique aux lignes comptées (des lots), jamais aux pièces dites
        faits = {"quantite": lot.get("pieces", quantite), "quantite_max": lecture.QUANTITE_MAX}
        return _r("ARGUMENT_INVALIDE", faits, "", "quantite")
    au_poids = produit_au_poids.brique_qte1_chiffrer_au_poids(article, poids, quantite)
    if au_poids.get("raison"):
        return _r("INTERDIT", au_poids, "")
    if personnes is not None and not variante:
        variante = menu_pour_n_personnes.brique_for10_pour_combien(article, personnes)  # FOR10 : la sous-case ``personnes`` dit la déclinaison de la formule
        if variante is None and any(d.get("type") == "personnes" for d in article["declinaisons"]):
            question = declinaison_nommee.brique_dec1_demander_la_declinaison(article["declinaisons"])
            return choix_obligatoire({"article": article["nom"], "article_de_la_carte": article["nom"], "question": question, "dit": personnes, "raison": menu_pour_n_personnes.RAISON_HORS_LISTE})
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
            faits = {"nom": f"{article['nom']} {declinaison['nom']}", "autres_tailles": autres}
            return _r("RUPTURE", faits, "")
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
        return _avec(choix_obligatoire({"article": ligne["nom"], "article_de_la_carte": article["nom"], "question": question}), p)
    essai = copy.deepcopy(p)
    if not _fusionner(essai, ligne):
        essai["lignes"].append(ligne)
    P.toucher(essai)
    chiffre = await chiffrer_le_panier(source, essai, regles)
    if _bloque_l_ajout(chiffre):
        return _avec(chiffre, p)
    _valider(p, essai)
    return _r("OK", {"ajoute": ligne["nom"], "quantite": quantite, **({"choix_sans_objet": ligne["choix_sans_objet"]} if ligne.get("choix_sans_objet") else {}),
                     **(produit_alcoolise.brique_prx6_regle_d_age_dite(article) or {}),  # PRX6 : un article alcoolisé rend le fait ``alcool``
                     **FO.regle_a_dire_a_l_ajout(article),  # FOR7, FOR9, FOR13 : la condition, le justificatif, ce qui est servi avec (dits par le code)
                     **({"composition": FO.composition_de_la_ligne(article, ligne)} if article.get("formule") else {}),  # lot 11 : le modèle repasse avec elle
                     **_faits_du_poids_et_du_lot(article, au_poids, lot, quantite)})


def _faits_du_poids_et_du_lot(article: dict[str, Any], au_poids: dict[str, Any], lot: dict[str, Any], quantite: int = 1) -> dict[str, Any]:
    """Lot 13 : ce que l'ajout rend d'un article au poids (QTE1 : ``grammes``, ``arrondi_a`` et ``prix_de_la_ligne``, en centimes, que la porte donne au modèle : C6 n° 11) ou d'un lot de
    vente (QTE2 : ``lots``, ``pieces``)."""
    faits: dict[str, Any] = {}
    if au_poids:
        faits["grammes"] = au_poids["grammes"]
        if "arrondi_a" in au_poids:
            faits["arrondi_a"] = au_poids["arrondi_a"]
        faits["prix_de_la_ligne"] = au_poids["prix"] * quantite  # Pierre 12 : plusieurs portions : le total de la ligne, jamais le prix d'une portion
    if lot:
        faits.update(lots=lot["lots"], pieces=lot["pieces"])
    return faits


async def _noter_une_regle_inconnue_de_la_carte(source: Source, p: dict[str, Any], regles: Reglages, article: dict[str, Any], ligne: dict[str, Any]) -> None:
    """Lot 12 (PRX2) : l'article se vend « hors jours fériés » et le jour voulu est férié : la ligne reste vendable, la règle part en note et le portail est signalé."""
    if not (article.get("disponibilite") or {}).get("hors_feries"):
        return
    quand = _servi_le(p) or await source.maintenant_du_lieu()
    texte = hors_jours_feries.brique_prx2_en_regle_inconnue(article, quand.date())
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
        "ref": str(article[CLE_REF_CHOISIE]) if article.get(CLE_REF_CHOISIE) else None,  # B5 (N1) : posée par le code seul, jamais par le modèle
    }


CLE_REF_CHOISIE = "ref_choisie"  # B5 (N1) : le candidat choisi en réponse à « Vous voulez dire… ? », par son identifiant : jamais recherché à nouveau
CLE_CANDIDATS = "candidats_par_identifiant"  # n° 55 : les candidats d'une ambiguïté, ``{libelle, id}`` (deux peuvent porter le même libellé), gardés avec la question, jamais montrés au modèle
CLE_OPTION_DITE = "option_dite"  # T1 (lot 19 bis) : l'hésitation porte sur une OPTION (les mots dits), jamais sur l'article ; gardée avec la question, jamais montrée au modèle
RAISON_QUANTITE_INFERIEURE_A_UN = "quantite_inferieure_a_un"  # C8 (lot 19 bis) : une quantité nulle ou négative n'est jamais un article de plus


async def ajouter_un_article(source: Source, p: dict[str, Any], regles: Reglages, article: dict[str, Any]) -> Resultat:
    """Un article de la case ``ajouter`` (la seule case qui additionne, E3). Sans mode ou sans zone, il est mis en attente du préalable
    (``mettre_en_attente_du_prealable``) et pris dès qu'ils sont posés ; sinon il est pris tout de suite."""
    dit = _article_de_la_fiche(article)
    if dit["quantite"] < 1:
        faits = {"raison": RAISON_QUANTITE_INFERIEURE_A_UN, "quantite": dit["quantite"]}
        return _r("ARGUMENT_INVALIDE", faits, "", "quantite")
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
    mots = [m for m in norme_de_recherche(morceau).split() if len(m) >= 3 and m not in LIAISON_D_UNE_COMPOSITION]
    if not mots:
        return False
    contenu = " ".join([article.get("nom") or "", article.get("description") or "", *(article.get("ingredients") or [])])
    return set(mots) <= set(norme_de_recherche(contenu).split())


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
    return await etat_apres_ajout(source, p, regles, {"ajoutes": ajoutes})



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


async def etat_apres_ajout(source: Source, p: dict[str, Any], regles: Reglages, faits: dict[str, Any]) -> Resultat:
    en_attente = P.a_completer(p)
    if en_attente:
        q = en_attente[0]["attente"]
        return choix_obligatoire({**faits, "article": en_attente[0]["nom"], "article_de_la_carte": en_attente[0]["article_nom"], "question": q})
    chiffre = await chiffrer_le_panier(source, p, regles)
    minimum = _minimum_non_atteint(chiffre)
    if minimum is not None:
        return _r("OK", {**faits, "minimum_non_atteint": minimum}, "")
    return _r("OK", {**faits, "total": chiffre.faits.get("total"), "sous_total": chiffre.faits.get("sous_total"), "frais": chiffre.faits.get("frais")}, "")


async def repondre_a_un_choix(source: Source, p: dict[str, Any], regles: Reglages, *, choix: str | None, sans: str | None, note: str | None, moities: str | None) -> Resultat:
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
            return _avec(await etat_apres_ajout(source, p, regles, {}), p)
    return await _travailler_une_ligne(source, p, regles, cible, choix=choix, sans=sans, note=note, moities=moities)


def changer_la_taille(article: dict, ligne: dict, variante: str, regles: Reglages) -> Resultat | None:
    """Lot 4 (M32, C8, appel 2653) : la variante dite remplace celle de la ligne (« finalement en grande »), même quand aucune taille n'est
    attendue. ``None`` : la ligne a sa nouvelle déclinaison ; ``RIEN_A_CHANGER`` : c'est déjà la sienne ; une variante que l'article n'a pas
    est redemandée avec ses choix (jamais une taille choisie à sa place, E12) ; une variante en rupture est refusée avec celles qui restent."""
    dite = _declinaison_choisie(article, variante, regles)
    vendables = [d["nom"] for d in article["declinaisons"] if d["vendable"] and not d["rupture"]]
    if dite is None:
        question = declinaison_nommee.brique_dec1_demander_la_declinaison(article["declinaisons"])
        return choix_obligatoire({"article": ligne["nom"], "article_de_la_carte": article["nom"], "question": question, "dit": variante})
    if dite["code"] == ligne.get("code"):
        return _r("RIEN_A_CHANGER", {"ligne": ligne["n"], "article": ligne["nom"], "variante": dite["nom"]}, "")
    if not dite["vendable"] or dite["rupture"]:
        autres = [n for n in vendables if n != dite["nom"]]
        faits = {"nom": f"{article['nom']} {dite['nom']}", "autres_tailles": autres}
        return _r("RUPTURE", faits, "")
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
        faits = {"article": ligne["nom"]}
        return _avec(_r("INTROUVABLE", faits, ""), p)
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
            return _avec(choix_obligatoire({"article": ligne["nom"], "article_de_la_carte": article["nom"], "question": attente}), p)
        if not trouve["vendable"] or trouve["rupture"]:
            faits = {"nom": f"{article['nom']} {trouve['nom']}"}
            return _avec(_r("RUPTURE", faits, ""), p)
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
            dans = attente["groupe"] if attente and attente.get("type") in ("groupe", formule_a_etapes.TYPE_DE_LA_QUESTION) and roles is None else None
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
    P.toucher_si_change(essai, p)  # n° 8 : une ligne redite à l'identique ne fait pas repartir la relecture
    chiffre = await chiffrer_le_panier(source, essai, regles)
    if _bloque_l_ajout(chiffre):
        return _avec(chiffre, p)
    _valider(p, essai)
    return _avec(await etat_apres_ajout(source, p, regles, {"ligne": ligne["n"], "article": ligne["nom"]}), p)


# --------------------------------------------------------------------------- #
# modifier, retirer, vider, voir
# --------------------------------------------------------------------------- #


async def _trouver_la_ligne(p: dict[str, Any], dit: str | None) -> tuple[dict | None, Resultat | None]:
    """La ligne que l'appelant désigne : son numéro (« la deuxième »), sinon son nom parmi les lignes du panier. ``(ligne, None)`` ou ``(None, refus)``."""
    if not p["lignes"]:
        faits = {"panier_vide": True}
        return None, _r("INTROUVABLE", faits, "")
    texte = lecture.en_chiffres(str(dit or "")).strip()
    if not texte and len(p["lignes"]) == 1:
        return p["lignes"][0], None
    if texte.isdigit():
        n = int(texte)
        ligne = next((l for l in p["lignes"] if l["n"] == n), None)
        if ligne:
            return ligne, None
        faits = {"lignes": len(p["lignes"]), "ligne": n}
        return None, _r("INTROUVABLE", faits, "")
    if not texte:
        return None, _r("INCOMPLETE", {}, "", "ligne")
    # SA-52 (appel 2604) : « X deux couleurs » désigne la ligne « X 2 couleurs » (les nombres lus des deux côtés).
    voulus = {m for m in norme_de_recherche(texte).split() if m not in RENVOI_A_UNE_LIGNE}
    correspond = [
        l for l in p["lignes"]
        if voulus and voulus <= set(norme_de_recherche(l["nom"] + " " + " ".join(c.get("nom", "") for c in l["choix"])).split())
    ]
    if len(correspond) == 1:
        return correspond[0], None
    noms = [l["nom"] for l in (correspond or p["lignes"])]
    if len(correspond) > 1:
        faits = {"candidats": noms, "lignes": [l["n"] for l in correspond]}
        return None, _r("AMBIGU", faits, TS.laquelle(faits))
    trouve = _chercher_dans([Element(str(l["n"]), l["nom"]) for l in p["lignes"]], texte)  # une faute de transcription : le moteur, à zéro faux sûr
    if trouve["statut"] == "RETENU":
        return next(l for l in p["lignes"] if str(l["n"]) == trouve["retenu"]), None
    faits = {"lignes": noms, "dit": texte}
    return None, _r("INTROUVABLE", faits, "")


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
                trouve = await chercher_l_article(source, str(x.get("article") or ""), regles)
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
        return _avec(_r("ARGUMENT_INVALIDE", {}, "", "quantite"), p)
    if quantite and cible.get("lot_de_vente"):  # C4 : une ligne vendue par lot se corrige en PIÈCES, comme à l'ajout (QTE2) ; la ligne compte des lots
        lot = lot_de_vente.brique_qte2_multiple_du_lot({"nom": cible["nom"], "lot_de_vente": cible["lot_de_vente"]}, quantite)
        if lot.get("raison"):
            return _avec(_r("INTERDIT", lot, ""), p)
        quantite = lot["lots"]
    if quantite is not None and quantite > lecture.QUANTITE_MAX:
        faits = {"quantite_max": lecture.QUANTITE_MAX}  # pas la quantité dite : elle change d'un tour à l'autre et remettrait le compteur du journal à zéro
        return _avec(_r("ARGUMENT_INVALIDE", faits, "", "quantite"), p)
    if quantite == 0:
        return await retirer(source, p, regles, ligne=str(cible["n"]))
    if quantite is None and not (choix or sans or note or moities or variante):
        return _avec(_r("INCOMPLETE", {}, "", "modification"), p)
    return await _travailler_une_ligne(source, p, regles, cible, choix=choix, sans=sans, note=note, moities=moities, quantite=quantite, variante=variante)


async def retirer(source: Source, p: dict[str, Any], regles: Reglages, *, ligne: str | None = None) -> Resultat:
    cible, refus = await _trouver_la_ligne(p, ligne)
    if refus is not None:
        return _avec(refus, p)
    essai = copy.deepcopy(p)
    essai["lignes"] = [l for l in essai["lignes"] if l["n"] != cible["n"]]
    P.toucher(essai)
    chiffre = await chiffrer_le_panier(source, essai, regles)
    _valider(p, essai)
    # M9 (contrôle long, lot 3) : jamais « total: null » : le total quand le panier se chiffre ; sous le minimum de la zone, ce qui manque (comme après un ajout) ; panier vidé, rien
    faits: dict[str, Any] = {"retire": cible["nom"]}
    if chiffre.statut == "OK":
        faits["total"] = chiffre.faits.get("total")
    elif (minimum := _minimum_non_atteint(chiffre)) is not None:
        faits["minimum_non_atteint"] = minimum
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
