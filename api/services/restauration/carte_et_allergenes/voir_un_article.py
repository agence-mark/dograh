"""[.mark] Restauration : voir un article (lot 7, E-14, E-15) : sa composition, ses signalements (allergènes, régimes, ingrédients) et « avez-vous des X sans Y ».

Sorti du moteur commun de la commande : ce vocabulaire est celui du métier. Le moteur commun l'appelle par ``moteur.socle.METIER.voir_un_article`` (branché par ``restauration/crochets.inscrire``).
"""

from __future__ import annotations

import re
from typing import Any


from api.services.commande.briques import allergenes_du_produit
from api.services.mots_dits import liste_dite_et, sans_article
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import phrases_d_information as INFO
from api.services.commande.briques import produit_du_moment
from api.services.commande.briques import formule as FO
from api.services.commande.moteur.articles import _option_dite, _un_seul_candidat
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.commande.moteur.socle import Reglages, _avec, _r, _racines
from api.services.restauration.carte_et_allergenes.allergie_de_la_commande import _consigne_d_allergie, _faits_du_prix, _informations_de_la_fiche, _lecture_de_la_formule, _nomme_une_categorie, _option_signale, _regime_dit, _regime_du_catalogue, _regles_d_information, _signalement_dit, _signalements_dits
from api.services.restauration.carte_et_allergenes.signalements import codes_des_signalements

# M104 (appel 2591) : « vous avez des X sans Y ? », « quelque chose sans Y ? », un régime : chercher dans le catalogue ce qui est SANS une chose.
_SANS = re.compile(r"(?<!\w)sans\s+(?P<chose>.+)$", re.IGNORECASE)


def _etat_sans(article: dict, code: str) -> str:
    """``sur`` : la donnée prouve que l'article ET toutes les options de ses choix obligatoires ne contiennent pas ``code`` ; ``contient`` : toutes les façons de le commander en contiennent ;
    ``selon_le_choix`` : une option obligatoire en contient (A3, lot 19 bis : « sans » ne tient pas si le client peut devoir la prendre) ; ``inconnu`` sinon.
    Une donnée absente n'est JAMAIS « sans » (jamais un faux non)."""
    signalements = article.get("signalements")
    dit = allergenes_du_produit.brique_inf1_repondre_depuis_la_donnee(codes_des_signalements(signalements), code)  # lot 15 (INF1)
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


def _etat_sans_pour_tous(article: dict, codes: list[str], mot_inconnu: bool = False) -> str:
    """Pierre 9 : l'état « sans » pour plusieurs allergènes dits (« lait et poisson ») : ``sur`` seulement s'il l'est pour TOUS ; ``contient`` dès qu'un seul y est
    (l'article n'est pas « sans » le tout) ; ``selon_le_choix`` puis ``inconnu`` sinon. Un mot d'allergie que la source ne reconnaît pas (« kiwi ») : jamais ``sur``,
    « à confirmer par l'équipe »."""
    etats = [_etat_sans(article, c) for c in codes]
    for gagnant in ("contient", "selon_le_choix", "inconnu"):
        if gagnant in etats:
            return gagnant
    return "inconnu" if mot_inconnu else "sur"


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
    codes, mot_inconnu = _signalements_dits(source, chose) if chose else ([], False)  # Pierre 9 : TOUS les allergènes dits, jamais le dernier seul
    code = codes[0] if codes else None
    if code is None:
        if regime is None:
            return None
        if texte and getattr(source, "regime_dit", lambda _t: None)(texte) is None and not await _nomme_une_categorie(source, p, texte):
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
    mot = liste_dite_et([sans_article((catalogue.get("libelles") or {}).get(c, c)) for c in codes])
    etats = [(a, _etat_sans_pour_tous(a, codes, mot_inconnu)) for a in articles]
    surs = [a["nom"] for a, e in etats if e == "sur"]
    selon = [a["nom"] for a, e in etats if e == "selon_le_choix"]
    contiennent = sum(1 for _, e in etats if e == "contient")
    inconnus = sum(1 for _, e in etats if e == "inconnu")
    faits = {"recherche": "sans", "code": code, **({"codes": codes} if len(codes) > 1 else {}), "categories": categories, "sans": surs, "contiennent": contiennent, "inconnus": inconnus, **({"selon_le_choix": selon} if selon else {})}
    if surs:
        faits = {**faits, "mot": mot, **INFO.consigne_si_liste(surs)}  # la liste est entière, le modèle en dit quelques-uns s'il y en a plusieurs (Q8) ; ``mot`` est la chose évitée, que le modèle dit
        return _r("OK", faits, "")
    if contiennent and not inconnus and not selon:
        return _r("OK", faits, "")  # les faits disent combien en contiennent : le modèle le dit
    return _r("OK", {**faits, "a_faire": INFO.CONSIGNE_NON_GARANTI}, "")  # rien n'est écrit pour le reste : la proposition du module commun, en consigne


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
        return _r("OK", {"recherche": "ingredient", "articles": [], "inconnus": 0, "renseigne": False}, "")  # C7 B5 : ``renseigne`` faux, le modèle dit qu'il ne peut pas confirmer
    catalogue = await lire(p.get("mode") or source.modes[0])
    articles = catalogue.get("articles") or []
    voulu = _racines(categorie or "")
    if voulu:
        dans = [a for a in articles if a.get("categorie") and voulu <= _racines(a["categorie"])]
        articles = dans or articles
    etats = [(a, _contient_l_ingredient(source, a.get("ingredients"), chose)) for a in articles]
    trouves = list(dict.fromkeys(a["nom"] for a, e in etats if e is (True if contient else False)))
    inconnus = sum(1 for _, e in etats if e is None)
    faits = {"recherche": "ingredient", "chose": chose, "contient": contient, "articles": trouves, "inconnus": inconnus, **INFO.consigne_si_liste(trouves)}  # Q8
    return _r("OK", faits, "")


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
        return _r("ARGUMENT_INVALIDE", {}, "", "produit")
    cherche = await source.chercher(produit.strip())
    trouve, dit_en_plus = await _un_seul_candidat(source, cherche, produit.strip())
    if trouve.statut != "RETENU":
        return _avec(trouve, p)
    fiche = await source.article(trouve.faits["retenu"], p.get("mode") or source.modes[0])
    if fiche is None:
        return _avec(_r("INTROUVABLE", {}, ""), p)
    option = _option_dite(fiche, dit_en_plus) if dit_en_plus else None
    if dit_en_plus and option is None:
        return _avec(cherche, p)  # le reste dit n'est pas une option certaine : le doute reste un doute
    nom = fiche["nom"]
    info = await _regles_d_information(source)
    if not signale:
        # B5 (D11, FOR13-A) : ce que la lecture rend au modèle (ce qui est servi avec ; pour une formule, sa condition et son justificatif aussi), il
        # le dit : c'est noté au journal comme la règle de l'article, que le code ne redit donc pas à l'ajout (avant : « servi avec » dit deux fois)
        from api.services.commande.briques import inclus_par_rubrique

        # une formule rend toutes ses règles ; un autre article ne rend que ce qui est servi avec
        for regle in FO.regle_a_dire_a_l_ajout(fiche).get("regle_a_dire") or []:
            if fiche.get("formule") or regle["id"] == inclus_par_rubrique.id_de_la_rubrique(fiche):
                J.noter(p, f"regle:{regle['id']}")
        du_moment = produit_du_moment.brique_art3_texte_du_jour(fiche)
        if du_moment is not None:  # ART3 : un produit du moment se lit par son texte du jour, tel que saisi, jamais par ses ingrédients
            return _avec(_r("OK", {"article": nom, **du_moment}, ""), p)  # C7 B5 : le texte du jour (ou ``renseigne`` faux) est un fait, le modèle le dit
        if fiche.get("formule"):  # lot 11 : une formule se lit par ses étapes et ses règles ; son prix est un fait, dit par le modèle (C6 n° 11)
            return _avec(_lecture_de_la_formule(fiche), p)
        composition = list(fiche.get("ingredients") or [])
        avec = {"option": option["nom"]} if option else {}
        avec.update({"servi_avec": fiche["servi_avec"]} if fiche.get("servi_avec") else {})  # FOR13 : ce qui est servi avec, d'après la rubrique
        avec.update(_informations_de_la_fiche(fiche, info))  # lot 15 (INF3, INF4, INF5, INF7) : régimes, épice, nutrition, ce qui est écrit pour le halal
        prix = _faits_du_prix(fiche)  # PRX5 : le prix « à partir de », un fait que le modèle dit (C6 n° 11)
        if not composition:
            return _avec(_r("OK", {"article": nom, "renseigne": False, **avec, **prix}, ""), p)
        faits = {"article": nom, "renseigne": True, "ingredients": composition, **avec, **prix}
        return _avec(_r("OK", faits, ""), p)  # C7 B5 (Evan 25/11 8 h 45) : les ingrédients sont des faits, le modèle les dit
    regime = getattr(source, "regime_dit", lambda _t: None)(signale)
    if regime is not None:
        return _avec(_regime_dit(source, fiche, regime, info), p)
    if info.get("allergies_renvoyees_au_restaurant"):  # D22 : le restaurant a choisi de renvoyer toute question d'allergène vers lui
        faits = {"article": nom, "signalement": "renvoye_au_restaurant", "equipe_confirme": True, **_consigne_d_allergie(info)}
        return _avec(_r("OK", faits, ""), p)
    dit = _signalement_dit(source, fiche, option, signale)
    return _avec(Resultat(dit.statut, {**dit.faits, **_consigne_d_allergie(info)}, dit.suggestion, dit.manque), p)

