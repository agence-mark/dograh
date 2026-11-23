"""[.mark] Moteur de la commande : la lecture : voir la carte et la commande, remises, composition et signalements d'un article, retrouver une commande.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import copy
import re
from typing import Any
from loguru import logger

from api.services.commande import panier as P
from api.services.commande.briques import art3, inf1
from api.services.commande.briques import formule as FO
from api.services.mots_dits import liste_dite, liste_dite_et, montant_en_lettres, phrase_nette
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.actions_communes import journal_du_dit as J
from api.services.commande.moteur.socle import NON_CONFIRMABLE, Reglages, _PAS_SUR, _PERDUES, _PLUS_DE_NOMS, _avec, _dit, _mots_significatifs, _phrase_d_une_remise_appliquee, _r, _racines, _sans_accent, cle_de_la_remise
from api.services.commande.moteur.prealables import _chiffrer
from api.services.commande.moteur.articles import _minimum_non_atteint, _option_dite, _phrase_des_lignes, _un_seul_candidat
from api.services.commande.moteur.allergie import _consigne_d_allergie, _faits_du_prix, _informations_de_la_fiche, _lecture_de_la_formule, _nomme_une_categorie, _option_signale, _regime_dit, _regime_du_catalogue, _regles_d_information, _signalement_dit, _signalements_dits
from api.services.commande.moteur.socle import Appelant


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
        if J.une_fois(p, cle_de_la_remise(r["ref"])):
            p["mentions_de_remise"] += 1
            await _noter_dite(source, r["ref"], appel_id)
            return _avec(_r("OK", {"a_dire": True, "moment": "appliquee", "remise": {"nom": r["nom"], "montant": r["montant"]}}, _phrase_d_une_remise_appliquee(r)), p)
    # M25 : une offre « X achetés, Y offerts d'une autre sorte » ATTEINTE ou presque, même sans l'article offert au panier.
    offres = []
    if chiffre is not None and chiffre.statut == "OK" and getattr(source, "offres_a_portee", None) is not None:
        offres = await source.offres_a_portee(p["mode"], chiffre.faits.get("lignes") or [])
    for o in offres:
        if J.deja_dit(p, cle_de_la_remise(o["ref"])):
            continue
        if o["etat"] == "atteinte" and o.get("proposition"):
            p["mentions_de_remise"] += 1
            J.noter(p, cle_de_la_remise(o["ref"]))
            await _noter_dite(source, o["ref"], appel_id)
            debut = _dit(o["phrase"]) if o.get("phrase") else f"{_dit(o['nom'])} : vous y avez droit."
            phrase = f"{debut} Qu'est-ce qui vous ferait plaisir : {liste_dite(o['choix'])} ?"
            faits = {"a_dire": True, "moment": "offre_atteinte", "remise": {"nom": o["nom"], "choix": o["choix"], "prix": o["proposition"]["prix"]}}
            return _avec(_r("OK", faits, phrase), p)
        if o["etat"] == "presque":
            p["mentions_de_remise"] += 1
            J.noter(p, cle_de_la_remise(o["ref"]))
            await _noter_dite(source, o["ref"], appel_id)
            faits = {"a_dire": True, "moment": "offre_presque_atteinte", "remise": {"nom": o["nom"], "manque_articles": o["manque"]}}
            return _avec(_r("OK", faits, f"Il vous manque encore un article pour avoir {_dit(o['nom'])}."), p)
    sous_total = chiffre.faits["sous_total"] if chiffre is not None and chiffre.statut == "OK" else 0
    for r in en_cours:
        minimum = r.get("minimum")
        if minimum and not J.deja_dit(p, cle_de_la_remise(r["ref"])) and sous_total and minimum * 7 // 10 <= sous_total < minimum:
            p["mentions_de_remise"] += 1
            J.noter(p, cle_de_la_remise(r["ref"]))
            await _noter_dite(source, r["ref"], appel_id)
            reste = minimum - sous_total
            return _avec(
                _r("OK", {"a_dire": True, "moment": "seuil_presque_atteint", "remise": {"nom": r["nom"], "manque": reste}},
                   f"Il vous manque {montant_en_lettres(reste)} pour avoir {_dit(r['nom'])}."),
                p,
            )
    return _avec(_r("OK", {"a_dire": False, "raison": "rien_a_dire"}), p)

# M104 (appel 2591) : « vous avez des X sans Y ? », « quelque chose sans Y ? », un régime : chercher dans le catalogue ce qui est SANS une chose.
_SANS = re.compile(r"(?<!\w)sans\s+(?P<chose>.+)$", re.IGNORECASE)


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
    mot = liste_dite_et([_sans_article((catalogue.get("libelles") or {}).get(c, c)) for c in codes])
    etats = [(a, _etat_sans_pour_tous(a, codes, mot_inconnu)) for a in articles]
    surs = [a["nom"] for a, e in etats if e == "sur"]
    selon = [a["nom"] for a, e in etats if e == "selon_le_choix"]
    contiennent = sum(1 for _, e in etats if e == "contient")
    inconnus = sum(1 for _, e in etats if e == "inconnu")
    faits = {"recherche": "sans", "code": code, **({"codes": codes} if len(codes) > 1 else {}), "categories": categories, "sans": surs, "contiennent": contiennent, "inconnus": inconnus, **({"selon_le_choix": selon} if selon else {})}
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
        # B5 (D11, FOR13-A) : ce que la lecture rend au modèle (ce qui est servi avec ; pour une formule, sa condition et son justificatif aussi), il
        # le dit : c'est noté au journal comme la règle de l'article, que le code ne redit donc pas à l'ajout (avant : « servi avec » dit deux fois)
        regle = FO.regle_a_dire_a_l_ajout(fiche).get("regle_a_dire")
        from api.services.commande.briques import for13

        if regle and (fiche.get("formule") or regle == for13.phrase_de_la_rubrique(fiche)):
            J.noter(p, f"regle:{regle}")
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
