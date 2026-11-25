"""[.mark] Moteur de la commande : poser le mode et vérifier l'adresse. Ce sont les gestes qui reprennent ce qui était dit avant eux (SA-33) : ils importent donc ``articles`` ;
``articles`` importe ``prealables`` et jamais l'inverse (le cycle est cassé par le découpage, sans branchement à l'import)."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from api.services.commande import panier as P
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.commande.moteur.articles import _reprendre_les_dits
from api.services.commande.moteur.prealables import (
    CLES_DE_L_ETAT,
    _minimum_de_l_adresse,
    _mode_dit,
    _rien_n_est_pris,
    _valider,
    adresse_verifiee,
    annoncer_la_fermeture,
    chiffrer_le_panier,
    exiger_une_voie,
    garder_l_heure,
    mode_implique_par_l_adresse,
    proposer_un_autre_mode_hors_zone,
    question_du_mode,
    retenir_la_seule_commune_livree,
)
from api.services.commande.moteur.socle import Reglages, _avec, _r


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
            _r(etat["statut"], {"mode": choisi, **{k: etat.get(k) for k in CLES_DE_L_ETAT}}, annoncer_la_fermeture(p, etat)),
            p,
        )
    await garder_l_heure(source, p, heure_voulue)
    r = await _poser_le_mode(source, p, regles, choisi, a_planifier)
    if not a_planifier or r.statut != "OK":
        return r
    # Fermé mais planifiable : le résultat dit la fermeture et propose le créneau ; la question en cours (zone, articles) suit, sinon l'heure.
    # Appel 2610 : la fermeture déjà dite avec la question du mode ne se redit pas.
    fermeture = annoncer_la_fermeture(p, etat)
    heure_voulue_dite = None
    dire = getattr(source, "quand_dit", None)
    if p.get("heure_voulue") and dire:
        # Appel 2566 : l'heure est déjà dite et gardée, c'est déjà l'accord pour plus tard ; la proposition de « plus tard » n'est pas refaite (le modèle la
        # tournait en « est-ce que cela vous convient ? »). Le résultat dit pour quand la commande est prise ; le créneau se vérifie à ``finaliser``.
        heure_voulue_dite = await dire(datetime.fromisoformat(p["heure_voulue"]))
        fermeture = f"Commande pour {heure_voulue_dite}."
    faits = {**r.faits, **{k: etat.get(k) for k in CLES_DE_L_ETAT}, "a_planifier": True, **({"heure_voulue_dite": heure_voulue_dite} if heure_voulue_dite else {})}
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
    chiffre = await chiffrer_le_panier(source, essai, regles)
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
        chiffre = await chiffrer_le_panier(source, essai, regles)
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
