"""[.mark] Moteur de la commande : le règlement : la relecture, le récapitulatif, le moyen de paiement.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from api.schemas.apres_appel import numero_e164
from api.services.commande import etape as ETAPE
from api.services.commande import lecture, panier as P, phrases_dites_par_le_code as PHRASES_DITES, textes_de_secours as TS
from api.services.commande.phrases_du_manque import Manque, phrase_du_manque
from api.services.mots_dits import liste_dite_et, montant_en_lettres, nombre_en_lettres
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.commande.moteur.socle import _avec, _r
from api.services.commande.moteur.articles import _ligne_dite, _phrase_des_lignes


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


def _majuscule(texte: str) -> str:
    """La première lettre en majuscule, le reste tel quel (``capitalize`` mettrait le reste en minuscules)."""
    return texte[:1].upper() + texte[1:]


def _cle_lue(a: dict[str, Any]) -> str:
    """La clé d'une ligne, lue pareil avant et après un aller-retour JSON (la fiche s'écrit entre deux tours : un tuple y devient une liste)."""
    return json.dumps(a["cle"], ensure_ascii=False)


def _ce_qui_a_change(avant: list[dict[str, Any]], apres: list[dict[str, Any]]) -> list[str]:
    """Chantier Partie 1, lot 6 (L06-41, ``banc-b2/guichet_candidat.py``) : une ligne se suit par son NUMÉRO quand elle en a un ; la même ligne qui
    change de variante ou de composition est « changée » (« C'est changé : Margherita Mega »), jamais retirée puis ajoutée. Une relecture d'avant
    sans numéro garde la comparaison par contenu."""
    if all(a.get("n") is not None for a in [*avant, *apres]):
        anciens_n = {a["n"]: a for a in avant}
        dits = []
        for n in apres:
            a = anciens_n.get(n["n"])
            if a is None:
                dits.append(f"on ajoute {_ligne_dite(n)}")
            elif _cle_lue(a) != _cle_lue(n):
                dits.append(f"c'est changé : {n['nom']}")
            elif a["quantite"] != n["quantite"]:
                dits.append(PHRASES_DITES.ligne_passe_a(nom=n["nom"], quantite=nombre_en_lettres(n["quantite"])))
        nouveaux_n = {n["n"] for n in apres}
        dits += [f"on retire {a['nom']}" for a in avant if a["n"] not in nouveaux_n]
        return dits
    anciens = {_cle_lue(a): a for a in avant}
    nouveaux = {_cle_lue(a): a for a in apres}
    dits: list[str] = []
    for cle, n in nouveaux.items():
        a = anciens.get(cle)
        if a is None:
            dits.append(f"on ajoute {_ligne_dite(n)}")
        elif a["quantite"] != n["quantite"]:
            dits.append(PHRASES_DITES.ligne_passe_a(nom=n["nom"], quantite=nombre_en_lettres(n["quantite"])))
    for cle, a in anciens.items():
        if cle not in nouveaux:
            dits.append(f"on retire {a['nom']}")
    return dits


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
    reserves = getattr(source, "moyens_reserves_au_mode", None) or {}
    acceptes = [m for m in reglages["moyens_paiement"] if m not in reserves or p.get("mode") in reserves[m]]
    moyen, moyen_reste = le_seul_moyen_de_sa_famille(brut.get("moyen"), acceptes), le_seul_moyen_de_sa_famille(brut.get("moyen_reste"), acceptes)
    if not moyen:
        return None, _r(
            "INCOMPLETE", {"moyens": [source.libelles_des_moyens.get(m, m) for m in acceptes], "acceptes": list(acceptes)}, phrase_du_manque(Manque.PAIEMENT), "paiement"
        )
    for m in (moyen, moyen_reste):
        if m and m not in acceptes:
            faits = {"moyen": m, "acceptes": list(acceptes), "acceptes_dits": [source.libelles_des_moyens.get(a, a) for a in acceptes]}
            return None, _r("MOYEN_NON_ACCEPTE", faits, TS.moyen_non_accepte(faits))
    part = brut.get("part")
    if part is None or part >= total:
        moyens = [{"moyen": moyen, "montant": total}]
    elif part <= 0:
        faits = {"montant_illisible": True}
        return None, _r("ARGUMENT_INVALIDE", faits, TS.quel_montant(faits), "paiement")
    elif not moyen_reste:
        faits = {"reste": total - part}
        return None, _r("INCOMPLETE", faits, TS.et_le_reste(faits), "paiement_reste")
    else:
        moyens = [{"moyen": moyen, "montant": part}, {"moyen": moyen_reste, "montant": total - part}]
    paiement: dict[str, Any] = {"moyens": moyens, "rendu_sur": None, "monnaie": 0}
    rendu_sur = brut.get("rendu_sur")
    if rendu_sur:
        # Un billet n'a de sens que pour le règlement qui se paie en main ; la monnaie est calculée sur ce qui est payé avec lui.
        cible = next((m for m in moyens if m["moyen"] == brut.get("moyen_du_billet", "especes")), None)
        if cible is None:
            faits = {"moyen_du_billet": brut.get("moyen_du_billet", "especes")}
            return None, _r("ARGUMENT_INVALIDE", faits, TS.sur_quel_reglement(faits), "paiement")
        if rendu_sur < cible["montant"]:
            faits = {"montant": cible["montant"], "billet": rendu_sur}
            return None, _r("ARGUMENT_INVALIDE", faits, TS.billet_insuffisant(faits), "paiement")
        paiement["rendu_sur"], paiement["monnaie"] = rendu_sur, rendu_sur - cible["montant"]
    return paiement, None


def dire_le_rendu_de_monnaie(paiement: dict[str, Any]) -> str:
    """Lot 4 (C11) : le rendu calculé par le code, dit mot pour mot dans la confirmation ; rien quand il n'y a pas de monnaie à rendre."""
    monnaie = int(paiement.get("monnaie") or 0)
    if monnaie <= 0 or not paiement.get("rendu_sur"):
        return ""
    return PHRASES_DITES.rendu_de_monnaie(billet=montant_en_lettres(paiement["rendu_sur"]), monnaie=montant_en_lettres(monnaie))


def _relecture_deja_dite(p: dict[str, Any], total: int) -> Resultat:
    """M106/M107 (appels 2592, 2593) : la fin rappelée sans rien de nouveau (souvent sur une question de la personne pendant le récapitulatif) :
    rien n'est redit ; la parole revient au modèle avec les faits. Le récapitulatif reste valable : un « oui » ensuite le valide."""
    return _avec(
        _r("INCOMPLETE", {"total": total, "a_confirmer": True, "relecture_deja_dite": True, "rien_de_nouveau": True}, "", "reponse_a_la_relecture"),
        p, total=total,
    )


def poser_la_relecture(source: Source, p: dict[str, Any], chiffre: Resultat) -> Resultat:
    """Lot 4 (M38) : LA relecture, la seule (le récapitulatif et le total, avant le règlement, le numéro et le prénom ; appel 2631, Evan, 18/11).
    Tout la première fois, seulement ce qui a changé après une correction. Un jeton en prouve la lecture."""
    avant, maintenant = p.get("derniere_lecture"), _instantane(p)
    total = chiffre.faits["total"]
    if avant and p.get("derniere_lecture_mode") == p["mode"]:
        changes = _ce_qui_a_change(avant, maintenant)
        if p.get("heure_voulue_dite") and p.get("heure_voulue_dite") != p.get("derniere_lecture_heure"):
            changes.append(f"c'est pour {p['heure_voulue_dite']}")  # B3 (RC10) : l'heure fait partie de la relecture ; changée, elle se redit
        phrase = PHRASES_DITES.relecture_apres_changement(changes=_majuscule(liste_dite_et(changes)) + ". " if changes else "", total=montant_en_lettres(total))
    else:
        lignes = P.lignes_pretes(p)
        if not any(r.get("mecanisme") == "x_achetes_y_offert" for r in chiffre.faits.get("remises") or []):
            # la ligne née de l'offre n'est « offerte » que tant que l'offre vaut (une pizza retirée : elle redevient payante, et se relit ainsi)
            lignes = [{**l, "offerte_dite": False} for l in lignes]
        corps = _phrase_des_lignes(lignes)
        if p["mode"]:
            corps += f", {source.libelles_des_modes.get(p['mode'], p['mode'])}"
        if p.get("heure_voulue_dite"):
            corps += f", pour {p['heure_voulue_dite']}"
        offerts = [] if p.get("presse") else chiffre.faits.get("offerts") or []
        if offerts:
            corps += ", plus " + _phrase_des_lignes([{"quantite": o["quantite"], "nom": o["nom"], "choix": [], "retires": []} for o in offerts]) + " offert"
        # L06-41 (``banc-b2/guichet_candidat.py`` ``recap``) : la relecture ne nomme pas la remise ; le total la compte, la ligne offerte le dit.
        phrase = PHRASES_DITES.relecture_complete(corps=corps, total=montant_en_lettres(total))
    ancienne = p.get("relecture") or {}
    # B3 (M5, C3 b, RC10) : un accord vaut pour la relecture que la personne a entendue ; une relecture qui repart (l'heure, un article changés
    # après le « oui ») se pose et se dit, jamais validée en silence par le « oui » suivant
    meme_relecture = ancienne.get("empreinte") == P.empreinte(p) and ancienne.get("total") == total
    ETAPE.transition(p, ETAPE.RELECTURE_POSEE, l_accord_vaut=meme_relecture, relecture={
        "empreinte": P.empreinte(p), "jeton": uuid.uuid4().hex, "version": p["version"], "telephone": p["client"].get("telephone"),
        "recapitulatif": True, "total": total,
    })
    p["derniere_lecture"], p["derniere_lecture_mode"], p["derniere_lecture_heure"] = maintenant, p["mode"], p.get("heure_voulue_dite")
    return _avec(
        _r("INCOMPLETE", {"total": total, "lignes": [{"nom": l["nom"], "quantite": P.pieces(l)} for l in P.lignes_pretes(p)], "a_confirmer": True}, phrase, "relecture"),
        p, total=total,
    )


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
            return None, _avec(_r("ARGUMENT_INVALIDE", faits, TS.quel_montant(faits), "paiement"), p)
        p["paiement"] = {**(p.get("paiement") or {}), **{k: v for k, v in brut.items() if v is not None}}
    paiement, refus = await _le_reglement(source, p, total, p.get("paiement") or {})
    if refus is not None:
        if refus.manque in ("paiement", "paiement_reste"):
            p["paiement"] = None if refus.manque == "paiement" else p["paiement"]
        return None, _avec(refus, p)
    return paiement, None
