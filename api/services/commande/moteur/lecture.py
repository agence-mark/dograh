"""[.mark] Moteur de la commande : la lecture : voir la carte et la commande, remises, composition et signalements d'un article, retrouver une commande.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import copy
from typing import Any
from loguru import logger

from api.services.commande import panier as P
from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES, textes_de_secours as TS
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.actions_communes import journal_du_dit as J
from api.services.commande.moteur.socle import NON_CONFIRMABLE, Reglages, _PERDUES, _avec, phrase_d_une_remise_appliquee, _r, cle_de_la_remise
from api.services.commande.moteur.prealables import chiffrer_le_panier
from api.services.commande.moteur.articles import _minimum_non_atteint, _phrase_des_lignes
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
        faits = {"lignes": [], "total": 0, "vide": True}
        return _avec(_r("OK", faits, TS.commande_vide_a_lire(faits)), p)
    chiffre = await chiffrer_le_panier(source, p, regles)
    minimum = _minimum_non_atteint(chiffre)  # M27 : sous le minimum de la zone, le panier se lit quand même ; on dit ce qui manque
    if minimum is not None:
        sans_zone = copy.deepcopy(p)
        sans_zone["zone"] = None
        chiffre = await chiffrer_le_panier(source, sans_zone, regles)
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
    remises = chiffre.faits.get("remises") or []
    offerte = bool(chiffre.faits.get("livraison_offerte")) and total is not None  # lot 14 (OFF4) : le code dit que la livraison est offerte
    faits = {
        "lignes": lignes, "sous_total": chiffre.faits["sous_total"], "frais": chiffre.faits["frais"], "total": total,
        "remises": [{"nom": r["nom"], "montant": r["montant"]} for r in remises], "total_remises": chiffre.faits.get("total_remises", 0),
        "offerts": chiffre.faits.get("offerts") or [], **({"livraison_offerte": True} if offerte else {}),
        **({"minimum_non_atteint": minimum} if minimum is not None else {}),
    }
    return _avec(_r("OK", faits, TS.la_commande_se_lit({**faits, "lignes_dites": _phrase_des_lignes(P.lignes_pretes(p))})), p, total=total)


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
    chiffre = await chiffrer_le_panier(source, p, regles) if p["lignes"] and p["mode"] and not P.a_completer(p) else None
    appliquees = (chiffre.faits.get("remises") or []) if chiffre is not None and chiffre.statut == "OK" else []
    if demande:
        if not en_cours:
            faits = {"a_dire": False, "raison": "aucune", "remises": []}
            return _avec(_r("OK", faits, TS.pas_d_offre(faits)), p)
        dites = [{"nom": r["nom"], "phrase": r["phrase"]} for r in en_cours]
        for r in en_cours:
            await _noter_dite(source, r["ref"], appel_id)
        faits = {"a_dire": True, "remises": dites, "appliquees": [r["nom"] for r in appliquees]}
        return _avec(_r("OK", faits, TS.offres_en_ce_moment(faits)), p)
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
            return _avec(_r("OK", {"a_dire": True, "moment": "appliquee", "remise": {"nom": r["nom"], "montant": r["montant"]}}, phrase_d_une_remise_appliquee(r)), p)
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
            faits = {"a_dire": True, "moment": "offre_atteinte", "remise": {"nom": o["nom"], "phrase": o.get("phrase"), "choix": o["choix"], "prix": o["proposition"]["prix"]}}
            return _avec(_r("OK", faits, TS.offre_atteinte(faits)), p)
        if o["etat"] == "presque":
            p["mentions_de_remise"] += 1
            J.noter(p, cle_de_la_remise(o["ref"]))
            await _noter_dite(source, o["ref"], appel_id)
            faits = {"a_dire": True, "moment": "offre_presque_atteinte", "remise": {"nom": o["nom"], "manque_articles": o["manque"]}}
            return _avec(_r("OK", faits, TS.offre_presque_atteinte(faits)), p)
    sous_total = chiffre.faits["sous_total"] if chiffre is not None and chiffre.statut == "OK" else 0
    for r in en_cours:
        minimum = r.get("minimum")
        if minimum and not J.deja_dit(p, cle_de_la_remise(r["ref"])) and sous_total and minimum * 7 // 10 <= sous_total < minimum:
            p["mentions_de_remise"] += 1
            J.noter(p, cle_de_la_remise(r["ref"]))
            await _noter_dite(source, r["ref"], appel_id)
            reste = minimum - sous_total
            faits = {"a_dire": True, "moment": "seuil_presque_atteint", "remise": {"nom": r["nom"], "manque": reste}}
            return _avec(_r("OK", faits, TS.seuil_presque_atteint(faits)), p)
    return _avec(_r("OK", {"a_dire": False, "raison": "rien_a_dire"}), p)



async def retrouver_commande(source: Source, p: dict[str, Any], regles: Reglages, appelant: "Appelant", numero: str | None = None) -> Resultat:
    """Retrouve une commande du jour : par son numéro (``numero``, court ou long), sinon par le numéro qui s'affiche. Le statut est LU dans le classeur,
    jamais deviné. À l'appelant on ne dit que « enregistrée » et l'heure (E-36) : les étapes de la préparation servent le suivi, pas l'appel. Une commande
    annulée ou qui n'est pas passée est dite telle quelle ; plusieurs commandes : on demande laquelle. Aucune plainte ici : le passage de main est celui de l'équipe."""
    if numero and numero.strip():
        trouve = await source.retrouver(numero=numero.strip())
    elif appelant.telephone_affiche:
        trouve = await source.retrouver(telephone=appelant.telephone_affiche)
    else:
        return _avec(_r("INCOMPLETE", {}, TS.quel_numero_de_commande({}), "reference"), p)
    if trouve.statut != "OK":
        faits = {"cherche_par": "numero" if numero and numero.strip() else "telephone_affiche"}
        return _avec(_r("INTROUVABLE", faits, TS.commande_introuvable(faits)), p)
    commandes = trouve.faits.get("commandes") or []
    if len(commandes) > 1:
        faits = {"candidats": [{"numero_court": c["numero_court"], "quand_dit": c.get("quand_dit")} for c in commandes]}
        return _avec(_r("AMBIGU", faits, TS.commandes_plusieurs(faits), "reference"), p)
    c = commandes[0]
    faits = {"numero_court": c["numero_court"], "statut": c["statut"], "mode": c["mode"], "quand_dit": c.get("quand_dit")}
    if c["statut"] == "annulee":
        phrase = TS.commande_annulee(faits)
    elif c["statut"] in _PERDUES:
        phrase = "Cette commande n'est pas passée à la préparation : je laisse un message à l'équipe qui vous rappelle."
    else:
        phrase = PHRASES_DITES.enregistree_retrouvee(c.get("quand_dit"))
    return _avec(_r("OK", faits, phrase), p)
