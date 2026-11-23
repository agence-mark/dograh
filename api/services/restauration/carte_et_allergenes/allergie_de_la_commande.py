"""[.mark] Restauration : l'allergie de la commande (lot 15, D22 ; proposition de Pierre du 19/11, tranchée par Evan le 20/11).

Sorti du moteur commun de la commande (``services/commande/moteur/``) : le vocabulaire du métier (allergie, régime, allergène) vit dans le module
du métier ; le moteur commun ne garde que le mécanisme générique (« un fait bloquant connu de l'appel », ``moteur.socle.METIER``), que ce module
branche en fin de fichier.
"""

from __future__ import annotations

import re
from typing import Any

from api.services.actions_communes.parole import CLE_FAITS_A_DIRE
from api.services.commande.briques import allergenes_du_produit, allergenes_d_une_option, regime_d_un_article, halal, epice_en_descripteur, consigne_d_allergie, nutrition_et_degre, prix_a_partir_de
from api.services.commande.briques import formule as FO
from api.services.mots_dits import liste_dite, liste_dite_et, montant_en_lettres
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.commande.moteur.socle import CLE_NOTES_DU_GREFFIER, METIER, NON_CONFIRMABLE, Reglages, _PAS_SUR, _PLUS_DE_NOMS, _avec, _le, _r, _racines
from api.services.commande.moteur.articles import _groupes_a_remplir

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
        lignes.append({"article": ligne["nom"], "etat": allergenes_d_une_option.brique_inf2_produit_et_options(None if signalements is None else [s["code"] for s in signalements], options, code)})
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
    contiennent = [a["nom"] for a in articles if allergenes_du_produit.brique_inf1_repondre_depuis_la_donnee(None if a.get("signalements") is None else [s["code"] for s in a["signalements"]], code) == "present"]
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


CLES_DE_L_ALLERGIE_DONNEE = ("allergie_donnee", "allergie_donnee_au_tour", "allergie_donnee_lignes")


def rouvrir_l_allergie_non_dite(p: dict[str, Any]) -> None:
    """Pierre A3 : les faits de l'allergie ont été notés « donnés » en sortant de la fiche, mais le modèle ne les a pas reçus (le code a dit sa propre phrase à la
    place du second passage) : l'allergie redevient « à donner », elle revient à la fiche suivante. Sans effet quand rien n'a été noté dans la fiche."""
    avant = p.pop("allergie_donnee_avant", None)
    if isinstance(avant, dict):
        p.update(avant)


def noter_l_allergie_donnee(p: dict[str, Any], tour: int) -> None:
    """Les faits de l'allergie viennent d'être donnés au modèle, dans ce tour, pour toutes les lignes du panier (A2 : leur empreinte est gardée) : sa phrase est dite à la fin du tour,
    l'enregistrement reste permis aux tours suivants."""
    p["allergie_donnee_avant"] = {k: p.get(k) for k in CLES_DE_L_ALLERGIE_DONNEE}  # Pierre A3 : de quoi la rouvrir si ses faits ne sont pas dits
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
    p["relecture"] = p["derniere_lecture"] = None
    p["relecture_acceptee"] = False
    return _avec(_r("INCOMPLETE", {**faits, "raison": RAISON_ALLERGIE}, ""), p)


async def _regles_d_information(source: Source) -> dict[str, Any]:
    """Lot 15 : ce que l'établissement a écrit (consigne d'allergie, halal, renvoi vers le restaurant) ; vide pour une source qui n'en a pas."""
    lire = getattr(source, "regles_d_information", None)
    return dict(await lire()) if lire is not None else {}


def _consigne_d_allergie(info: dict[str, Any]) -> dict[str, Any]:
    """INF6 : la consigne d'allergie du restaurant, un fait que l'agent répète (jamais inventée)."""
    consigne = consigne_d_allergie.brique_inf6_repeter_et_noter(info.get("consigne_allergie"), None)["consigne"]
    return {"consigne_du_restaurant": consigne} if consigne else {}


def _informations_de_la_fiche(fiche: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    """Ce que la donnée de l'article dit en plus, pour la lecture : régimes étiquetés (INF3), halal du restaurant (INF4), épice (INF5), nutrition et degré (INF7). Seul ce qui est écrit."""
    faits: dict[str, Any] = {}
    if fiche.get("regimes"):
        faits["regimes"] = [regime_d_un_article.LIBELLES.get(r, r) for r in fiche["regimes"]]
    if halal.brique_inf4_dire_ce_qui_est_ecrit(fiche.get("regimes"), bool(info.get("halal_restaurant")))["restaurant"]:
        faits["restaurant_halal"] = True
    epice = epice_en_descripteur.brique_inf5_depuis_le_texte(fiche.get("epice"))
    if epice:
        faits["epice"] = epice
    nutrition = nutrition_et_degre.brique_inf7_depuis_la_donnee(fiche.get("nutrition"), fiche.get("degre"))
    if nutrition:
        faits["nutrition"] = nutrition
    return faits


def _regime_dit(source: Source, fiche: dict[str, Any], regime: str, info: dict[str, Any]) -> Resultat:
    """La réponse sur UN régime pour UN article : seulement ce qui est écrit (étiquette de l'article, case du restaurant pour le halal), sinon « je ne peux pas vous garantir »."""
    nom = fiche["nom"]
    code = getattr(source, "regime_code", lambda _t: None)(regime)
    if code == halal.CODE:
        ecrit = halal.brique_inf4_dire_ce_qui_est_ecrit(fiche.get("regimes"), bool(info.get("halal_restaurant")))
        if ecrit["article"]:
            return _r("OK", {"article": nom, "regime": regime, "etiquete": True}, f"D'après la fiche, {nom} est {regime}.")
        if ecrit["restaurant"]:
            return _r("OK", {"article": nom, "regime": regime, "etiquete": False, "restaurant": True}, f"D'après la fiche du restaurant, la carte est {regime}.")
    elif code and regime_d_un_article.brique_inf3_jamais_sans_etiquette(fiche.get("regimes"), code) == "etiquete":
        return _r("OK", {"article": nom, "regime": regime, "etiquete": True}, f"D'après la fiche, {nom} est {regime}.")
    return _r("OK", {"article": nom, "regime": regime, "renseigne": False}, f"Je ne peux pas vous garantir ce qui est {regime} : {_PAS_SUR}")


async def _nomme_une_categorie(source: Source, p: dict[str, Any], texte: str) -> bool:
    """« des pizzas », « végétarien » : le texte nomme une CATÉGORIE de la carte, pas un article : la question porte sur le catalogue (sinon « pizzas » cherchait un article et
    la réponse était « introuvable » au lieu de « je ne peux pas le garantir »)."""
    lire = getattr(source, "catalogue", None)
    voulu = _racines(texte)
    if lire is None or not voulu:
        return False
    articles = (await lire(p.get("mode") or source.modes[0])).get("articles") or []
    return any(a.get("categorie") and voulu <= _racines(a["categorie"]) for a in articles)


async def _regime_du_catalogue(source: Source, p: dict[str, Any], regime: str) -> Resultat:
    """INF3, INF4 : « du végétarien ? », « c'est halal ? » sans article : seulement les articles ÉTIQUETÉS (et la case halal du restaurant) ; sans étiquette, rien n'est garanti."""
    faits: dict[str, Any] = {"recherche": "sans", "regime": regime, "renseigne": False}
    code = getattr(source, "regime_code", lambda _t: None)(regime)
    info = await _regles_d_information(source)
    etiquetes: list[str] = []
    lire = getattr(source, "catalogue", None)
    if code and lire is not None:
        etiquetes = regime_d_un_article.articles_etiquetes((await lire(p.get("mode") or source.modes[0])).get("articles") or [], code)
    restaurant = code == halal.CODE and bool(info.get("halal_restaurant"))
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
    prix = prix_a_partir_de.brique_prx5_jamais_le_prix_de_depart_comme_final(fiche)
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
    """La réponse sur le ou les signalements dits (Pierre 9 : « lait et poisson » : chacun est vérifié, jamais le dernier seul) : un seul, la réponse d'avant ;
    plusieurs, une réponse par allergène, et un mot que la source ne reconnaît pas (« kiwi ») reste « à confirmer par l'équipe », jamais passé sous silence."""
    codes, mot_inconnu = _signalements_dits(source, signale) if signale else ([], False)
    if len(codes) < 2 and not (codes and mot_inconnu):
        return _signalement_d_un_mot(source, fiche, option, signale)
    libelles = fiche.get("signalements_libelles") or {}
    reponses = [_signalement_d_un_mot(source, fiche, option, libelles.get(c, c)) for c in codes]
    phrase = " ".join(r.suggestion for r in reponses if r.suggestion)
    if mot_inconnu:
        phrase = f"{phrase} Pour le reste de ce que vous citez, {_NON_GARANTI}".strip()
    faits = {"article": fiche["nom"], **({"option": option["nom"]} if option else {}), "signalement": "plusieurs",
             "par_signalement": [{"code": c, "signalement": r.faits.get("signalement")} for c, r in zip(codes, reponses)], "a_confirmer_par_l_equipe": mot_inconnu or any(
                 r.faits.get("signalement") in ("inconnu", "selon_option") for r in reponses)}
    return _r("OK", faits, phrase)


def _signalement_d_un_mot(source: Source, fiche: dict, option: dict | None, signale: str) -> Resultat:
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
        etat = allergenes_d_une_option.brique_inf2_produit_et_options(None if signalements is None else [s["code"] for s in signalements], [option_vue], code)
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


A_FAIRE_DE_L_ALLERGIE = "l'allergie de la personne est connue : réponds-lui avec tes mots d'après faits.allergie ; ce qui est à confirmer par l'équipe, dis-le"


async def poser_les_faits_de_l_allergie(ctx: Any, source: Source, p: dict[str, Any], regles: Reglages, retour: dict[str, Any]) -> None:
    """Lot 15 (D22) : dès qu'une allergie est connue dans l'appel (la case du greffier), le code lit lui-même les allergènes validés du panier et les DONNE au modèle dans le retour (``faits.allergie``),
    comme un ``lire`` qu'il n'aurait pas eu à appeler. Aucune phrase du code : le modèle répond avec ses mots. ⛔ Ne lève jamais."""
    try:
        if allergie_a_donner(p) is None:
            return  # connue et pas encore donnée : même panier vide (la carte concernée est donnée avec)
        if p.get("allergie_donnee") == allergie_connue(p):
            faits = await faits_a_redonner_pour_les_lignes_nouvelles(source, p)  # A2 : seulement les lignes ajoutées ou changées depuis
            if faits is None:
                noter_l_allergie_donnee(p, int(p.get("allergie_donnee_au_tour") or 0))  # sans enjeu : empreinte mise à jour, rien n'est redit
                return
        else:
            faits = await faits_de_l_allergie(source, p)
        if not faits:
            return
        noter_l_allergie_donnee(p, int(p.get("tour_de_l_appel") or 0))
        retour["faits"] = {**(retour.get("faits") or {}), "allergie": faits}
        retour[CLE_FAITS_A_DIRE] = True  # lot 20 (conv4) : la phrase écrite avant ce retour ne les connaissait pas : le modèle repasse et les dit
        retour["a_faire"] = " ; ".join(x for x in (A_FAIRE_DE_L_ALLERGIE, retour.get("a_faire")) if x)
    except Exception:  # noqa: BLE001
        pass


# --- ce que le moteur commun appelle, sans connaître l'allergie
METIER.prealable = allergie_sans_reponse
METIER.faits_a_donner = poser_les_faits_de_l_allergie
METIER.rouvrir_les_faits_non_dits = rouvrir_l_allergie_non_dite
