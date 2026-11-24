"""[.mark] Moteur de la commande : les préalables : le mode, la zone, l'heure, l'ouverture, l'adresse, le chiffrage.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from api.db.bases_clients import dates_futures
from api.services.commande import lecture, panier as P
from api.services.mots_dits import liste_dite, montant_en_lettres
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.types import Adresse, MomentVoulu
from api.services.commande.moteur.socle import Reglages, _avec, _r, _sans_accent, reprendre_les_dits


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
    if not J.deja_dit(p, J.FERMETURE) and not p.get("heure_voulue"):
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


async def chiffrer_le_panier(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat:
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
    P.remplacer_par(p, essai)


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
    if p.get("heure_voulue") != moment.debut:
        P.toucher(p)  # l'heure fait partie de l'empreinte : la relecture entendue et l'accord ne valent plus (avant : la porte le déduisait en comparant les empreintes)
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
    repris = await reprendre_les_dits(source, p, regles)
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
        repris = await reprendre_les_dits(source, p, regles)
        if repris is not None and repris.faits.get("ajoutes"):
            faits["ajoutes"] = repris.faits["ajoutes"]
    if r.statut == "RETENU":
        repris = await reprendre_les_dits(source, p, regles)
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


async def verifier_le_creneau(source: Source, p: dict[str, Any]) -> Resultat | None:
    """Lot 4 (E28, M48, appel 2667) : l'heure voulue posée tient-elle (ouvert à cette heure, délai minimal, jours à l'avance, place) ? Appelée par
    l'opération qui pose l'heure, à chaque correction et avant le récapitulatif. ``None`` : elle tient (et son texte dit est posé) ; sinon le refus
    de la source, et l'heure n'est pas gardée (on en demande une autre)."""
    if not p.get("heure_voulue") or not p.get("mode"):
        return None
    verifier = getattr(source, "verifier_un_creneau", None)
    refus = await verifier(p["mode"], datetime.fromisoformat(p["heure_voulue"])) if verifier else None
    if refus is not None:
        P.toucher(p)  # l'heure retirée change l'empreinte, comme l'heure posée
        p["heure_voulue"] = p["heure_voulue_dite"] = p["moment_voulu"] = None
        return _avec(refus, p)
    dire = getattr(source, "quand_dit", None)
    p["heure_voulue_dite"] = await dire(datetime.fromisoformat(p["heure_voulue"])) if dire else None
    return None


def annoncer_la_fermeture(p: dict[str, Any], etat: dict[str, Any]) -> str:
    """Lot 4 (M07, appel 2649) : la phrase de la fermeture, dite UNE fois par appel (un drapeau du panier, lu partout) ; ensuite, rien."""
    if not J.une_fois(p, J.FERMETURE):  # B3 (M5) : au journal de ce qui est dit, plus un drapeau à part
        return ""
    return etat.get("phrase") or "Nous ne prenons pas de commande en ce moment."
