"""[.mark] Moteur de la commande : le règlement : la relecture, le récapitulatif, le moyen de paiement.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from api.schemas.apres_appel import numero_e164
from api.services.actions_communes import parole as PAROLE
from api.services.commande import etape as ETAPE
from api.services.commande import lecture, panier as P
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.commande.moteur.socle import avec_le_panier, _r
from api.services.mots_dits import montant_en_lettres
from api.services.phrases.catalogue import TOTAL_APRES_CORRECTION, TOTAL_RELECTURE


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


def _cle_lue(a: dict[str, Any]) -> str:
    """La clé d'une ligne, lue pareil avant et après un aller-retour JSON (la fiche s'écrit entre deux tours : un tuple y devient une liste)."""
    return json.dumps(a["cle"], ensure_ascii=False)


AJOUTEE, CHANGEE, QUANTITE, RETIREE, HEURE = "ajoutee", "changee", "quantite", "retiree", "heure"  # C6 n° 4 : les gestes de ce qui a changé, des faits (le modèle les dit avec ses mots)


def _ce_qui_a_change(avant: list[dict[str, Any]], apres: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chantier Partie 1, lot 6 (L06-41, ``banc-b2/guichet_candidat.py``) : une ligne se suit par son NUMÉRO quand elle en a un ; la même ligne qui
    change de variante ou de composition est « changée », jamais retirée puis ajoutée. Une relecture d'avant sans numéro garde la comparaison par contenu.
    C6 n° 4 (décision d'Evan 25/11 9 h 30) : des FAITS, jamais des phrases : ``{"geste", "nom", "quantite"}`` ; le modèle les dit avec ses mots, le code dit le nouveau total."""
    def fait(geste: str, l: dict[str, Any]) -> dict[str, Any]:
        return {"geste": geste, "nom": l["nom"], "quantite": l["quantite"]}

    changes: list[dict[str, Any]] = []
    if all(a.get("n") is not None for a in [*avant, *apres]):
        anciens_n = {a["n"]: a for a in avant}
        for n in apres:
            a = anciens_n.get(n["n"])
            if a is None:
                changes.append(fait(AJOUTEE, n))
            elif _cle_lue(a) != _cle_lue(n):
                changes.append(fait(CHANGEE, n))
            elif a["quantite"] != n["quantite"]:
                changes.append(fait(QUANTITE, n))
        nouveaux_n = {n["n"] for n in apres}
        return changes + [fait(RETIREE, a) for a in avant if a["n"] not in nouveaux_n]
    anciens = {_cle_lue(a): a for a in avant}
    nouveaux = {_cle_lue(a): a for a in apres}
    for cle, n in nouveaux.items():
        a = anciens.get(cle)
        if a is None:
            changes.append(fait(AJOUTEE, n))
        elif a["quantite"] != n["quantite"]:
            changes.append(fait(QUANTITE, n))
    return changes + [fait(RETIREE, a) for cle, a in anciens.items() if cle not in nouveaux]


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
    reserves = source.moyens_reserves_au_mode
    acceptes = [m for m in reglages["moyens_paiement"] if m not in reserves or p.get("mode") in reserves[m]]
    moyen, moyen_reste = le_seul_moyen_de_sa_famille(brut.get("moyen"), acceptes), le_seul_moyen_de_sa_famille(brut.get("moyen_reste"), acceptes)
    if not moyen:
        return None, _r(
            "INCOMPLETE", {"moyens": [source.libelles_des_moyens.get(m, m) for m in acceptes], "acceptes": list(acceptes)}, "", "paiement"
        )
    for m in (moyen, moyen_reste):
        if m and m not in acceptes:
            faits = {"moyen": m, "acceptes": list(acceptes), "acceptes_dits": [source.libelles_des_moyens.get(a, a) for a in acceptes]}
            return None, _r("MOYEN_NON_ACCEPTE", faits, "")
    part = brut.get("part")
    if part is None or part >= total:
        moyens = [{"moyen": moyen, "montant": total}]
    elif part <= 0:
        faits = {"montant_illisible": True}
        return None, _r("ARGUMENT_INVALIDE", faits, "", "paiement")
    elif not moyen_reste:
        faits = {"reste": total - part, "reste_dit": montant_en_lettres(total - part)}  # C7 B5 : le montant aussi en lettres (la copie du modèle lit mal des centimes)
        return None, _r("INCOMPLETE", faits, "", "paiement_reste")
    else:
        moyens = [{"moyen": moyen, "montant": part}, {"moyen": moyen_reste, "montant": total - part}]
    paiement: dict[str, Any] = {"moyens": moyens, "rendu_sur": None, "monnaie": 0}
    rendu_sur = brut.get("rendu_sur")
    if rendu_sur:
        # Un billet n'a de sens que pour le règlement qui se paie en main ; la monnaie est calculée sur ce qui est payé avec lui.
        cible = next((m for m in moyens if m["moyen"] == brut.get("moyen_du_billet", "especes")), None)
        if cible is None:
            faits = {"moyen_du_billet": brut.get("moyen_du_billet", "especes")}
            return None, _r("ARGUMENT_INVALIDE", faits, "", "paiement")
        if rendu_sur < cible["montant"]:
            faits = {"montant": cible["montant"], "billet": rendu_sur}
            return None, _r("ARGUMENT_INVALIDE", faits, "", "paiement")
        paiement["rendu_sur"], paiement["monnaie"] = rendu_sur, rendu_sur - cible["montant"]
    return paiement, None


def rendu_de_monnaie(paiement: dict[str, Any]) -> dict[str, int] | None:
    """Lot 4 (C11) : le rendu calculé par le code, en faits (``billet``, ``monnaie``, en centimes) ; ``None`` quand il n'y a pas de monnaie à rendre. C6 n° 5 (décision d'Evan 25/11 9 h 30) :
    la porte le dit par le motif réglé ``rendu_de_monnaie``, après la confirmation du modèle."""
    monnaie = int(paiement.get("monnaie") or 0)
    if monnaie <= 0 or not paiement.get("rendu_sur"):
        return None
    return {"billet": int(paiement["rendu_sur"]), "monnaie": monnaie}


def _relecture_deja_dite(p: dict[str, Any], total: int) -> Resultat:
    """M106/M107 (appels 2592, 2593) : la fin rappelée sans rien de nouveau (souvent sur une question de la personne pendant le récapitulatif) :
    rien n'est redit ; la parole revient au modèle avec les faits. Le récapitulatif reste valable : un « oui » ensuite le valide."""
    return avec_le_panier(
        _r("INCOMPLETE", {"total": total, "a_confirmer": True, "relecture_deja_dite": True, "rien_de_nouveau": True}, "", "reponse_a_la_relecture"),
        p, total=total,
    )


def relecture_entendue(p: dict[str, Any]) -> bool:
    """C6 : la relecture posée a été ENTENDUE : la phrase réglée de son total, qui porte la question, a été dite (journal du dit, au jeton de la relecture). Un « oui » ne vaut accord que pour elle ;
    sinon (relance échouée, phrase « pas compris », coupure de parole) la relecture se repose et le total se redit."""
    return PAROLE.total_dit(p, (p.get("relecture") or {}).get("jeton"))


def _ligne_a_relire(l: dict[str, Any]) -> dict[str, Any]:
    """Une ligne de la relecture donnée au modèle en faits (C6 : il la dit avec ses mots) : la quantité, le nom, les choix, les retraits, la note, offerte ou non. Aucune phrase."""
    return {"nom": l["nom"], "quantite": P.pieces(l), "choix": [c["nom"] for c in l.get("choix") or [] if c.get("nom")], "retires": list(l.get("retires") or []),
            "note": l.get("note") or None, "offerte": bool(l.get("offerte_dite"))}


def poser_la_relecture(source: Source, p: dict[str, Any], chiffre: Resultat) -> Resultat:
    """Lot 4 (M38) : LA relecture, la seule (le récapitulatif et le total, avant le règlement, le numéro et le prénom ; appel 2631, Evan, 18/11).
    Tout la première fois, seulement ce qui a changé après une correction. Un jeton en prouve la lecture.
    C6 (décision d'Evan 25/11 9 h 30) : le CODE ne compose plus la phrase. Il rend les faits (lignes, mode, heure, offerts, ou ce qui a changé) ; le modèle relit avec ses mots ;
    le code dit ensuite la phrase réglée du total (``motif_du_total`` : « total_relecture » ou « total_apres_correction »), avec la question."""
    avant, maintenant = p.get("derniere_lecture"), _instantane(p)
    total = chiffre.faits["total"]
    faits: dict[str, Any] = {"total": total, "a_confirmer": True}
    if avant and p.get("derniere_lecture_mode") == p["mode"]:
        changes = _ce_qui_a_change(avant, maintenant)
        if p.get("heure_voulue_dite") and p.get("heure_voulue_dite") != p.get("derniere_lecture_heure"):
            changes.append({"geste": HEURE, "heure": p["heure_voulue_dite"]})  # B3 (RC10) : l'heure fait partie de la relecture ; changée, elle se redit
        faits["ce_qui_a_change"] = changes
        motif_du_total = TOTAL_APRES_CORRECTION
    else:
        lignes = P.lignes_pretes(p)
        if not any(r.get("mecanisme") == "x_achetes_y_offert" for r in chiffre.faits.get("remises") or []):
            # la ligne née de l'offre n'est « offerte » que tant que l'offre vaut (une pizza retirée : elle redevient payante, et se relit ainsi)
            lignes = [{**l, "offerte_dite": False} for l in lignes]
        faits["lignes"] = [_ligne_a_relire(l) for l in lignes]
        if p["mode"]:
            faits["mode_dit"] = source.libelles_des_modes.get(p["mode"], p["mode"])  # « mode_dit » : jamais une écriture du mode (test du lot 2)
        if p.get("heure_voulue_dite"):
            faits["heure"] = p["heure_voulue_dite"]
        offerts = [] if p.get("presse") else chiffre.faits.get("offerts") or []
        if offerts:
            faits["offerts"] = [{"nom": o["nom"], "quantite": o["quantite"]} for o in offerts]
        # L06-41 (``banc-b2/guichet_candidat.py`` ``recap``) : la relecture ne nomme pas la remise ; le total la compte, la ligne offerte le dit.
        motif_du_total = TOTAL_RELECTURE
    ancienne = p.get("relecture") or {}
    # B3 (M5, C3 b, RC10) : un accord vaut pour la relecture que la personne a entendue ; une relecture qui repart (l'heure, un article changés
    # après le « oui ») se pose et se dit, jamais validée en silence par le « oui » suivant
    meme_relecture = ancienne.get("empreinte") == P.empreinte(p) and ancienne.get("total") == total
    ETAPE.transition(p, ETAPE.RELECTURE_POSEE, l_accord_vaut=meme_relecture, relecture={
        "empreinte": P.empreinte(p), "jeton": uuid.uuid4().hex, "version": p["version"], "telephone": p["client"].get("telephone"),
        "recapitulatif": True, "total": total, "motif_du_total": motif_du_total,
    })
    p["derniere_lecture"], p["derniere_lecture_mode"], p["derniere_lecture_heure"] = maintenant, p["mode"], p.get("heure_voulue_dite")
    return avec_le_panier(_r("INCOMPLETE", faits, "", "relecture"), p, total=total)


async def regler(
    source: Source, p: dict[str, Any], total: int, *, moyen: str | None = None, rendu_sur: Any = None, part: Any = None, moyen_reste: str | None = None,
) -> tuple[dict | None, Resultat | None]:
    """Lot 4 (M39) : le règlement. Ce qui est dit maintenant remplace ce qui l'était (E3) ; un règlement déjà dit n'est jamais redemandé (C11).
    Rend ``(paiement, None)`` ou ``(None, refus)`` (moyen manquant, non accepté, montant invalide)."""
    if moyen or part is not None or moyen_reste or rendu_sur is not None:
        brut = {"moyen": moyen, "part": _centimes(part) if part is not None else None, "moyen_reste": moyen_reste,
                "rendu_sur": _centimes(rendu_sur) if rendu_sur is not None else None}
        if (part is not None and brut["part"] is None) or (rendu_sur is not None and brut["rendu_sur"] is None):
            faits = {"montant_illisible": True}
            return None, avec_le_panier(_r("ARGUMENT_INVALIDE", faits, "", "paiement"), p)
        p["paiement"] = {**(p.get("paiement") or {}), **{k: v for k, v in brut.items() if v is not None}}
    paiement, refus = await _le_reglement(source, p, total, p.get("paiement") or {})
    if refus is not None:
        if refus.manque in ("paiement", "paiement_reste"):
            p["paiement"] = None if refus.manque == "paiement" else p["paiement"]
        return None, avec_le_panier(refus, p)
    return paiement, None
