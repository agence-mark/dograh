"""[.mark] Mécanisme commun : l'état du panier pendant l'appel, dans la fiche de l'appel (``commande_panier``).

Un simple dictionnaire sérialisable : il survit à un compactage du contexte, il s'écrit avec la fiche, et une panne en emporte le contenu
(il se joint au message laissé à l'équipe, W24). Le modèle ne le voit jamais directement : il le lit par ``voir_commande``.

Une ligne : ``{n, ref, nom, code, quantite, choix, retires, note, attente}``. ``code`` vide : la déclinaison n'est pas choisie.
``attente`` : la question encore ouverte pour cette ligne (un choix obligatoire), jamais une ligne perdue (W16).
Toute modification du panier invalide la relecture déjà faite (``relecture`` redevient vide) : on ne confirme jamais ce qu'on n'a pas relu.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from api.services.commande import etape as ETAPE

CLE = "commande_panier"


def nouveau() -> dict[str, Any]:
    return {
        "version": 0,
        "mode": None,
        "zone": None,  # {id, nom}
        "adresse": None,
        "commune_hors_zone": None,  # lot 4 (B12, conversation 2) : la commune dite et refusée ; les articles sont pris, la zone reste exigée à la fin
        "heure_voulue": None,  # ISO, commande planifiée (lot 6) ; l'instant de ``moment_voulu``, posé avec lui par ``moteur.poser_le_moment``
        "moment_voulu": None,  # ``MomentVoulu`` en JSON (chantier Partie 1, lot 1) : l'instant avec fuseau et les mots dits
        "heure_voulue_dite": None,  # la même heure, dite par la source (relecture)
        "moment_du_jour": None,  # M85 : « soir », « matin »… dit avec le jour, lu avec l'heure dite ensuite ({moment, jour})
        "a_planifier": False,  # D15 : fermé maintenant, commande pour un créneau d'une prochaine ouverture
        "lignes": [],
        "prochaine_ligne": 1,  # lot 4 (M33) : le numéro de la prochaine ligne créée, jamais réutilisé dans l'appel
        "client": {},
        "paiement": None,
        "reglement_voulu": {},  # n° 30 : le règlement tel que dit (moyen, part, moyen du reste, billet), écrit UNE fois à la commande ; le total vient à la fin
        "note": None,
        "etape": ETAPE.EN_COURS,  # l'étape de la commande (``etape.py``, seul module qui l'écrit)
        "relecture": None,  # {version, jeton, lignes, total}
        "vente_en_plus_faite": False,
        "enregistree": None,  # {numero, numero_court, heure_annoncee, total}
        "derniere_lecture": None,  # ce qui a été relu la dernière fois : après une correction, seul ce qui a changé est relu
        "derniere_lecture_mode": None,
        "mentions_de_remise": 0,  # combien de fois l'agent a parlé d'une remise de lui-même (T-08)
        "remises_du_code": [],  # les remises auxquelles ces codes donnent droit (références) : dites une fois, quand elles s'appliquent
        "codes_dits": [],  # lot 14 (OFF3) : les codes de remise que l'appelant a dits ET que l'établissement connaît (jamais un code deviné)
        "presse": False,  # l'appelant est pressé : aucune offre dite de soi-même, relecture comprise
        "remise_refusee": False,  # l'appelant a dit non : plus jamais de lui-même
        "consigne": None,  # une habitude à retenir pour le prochain appel, écrite à l'enregistrement
        # SA-33 : ce que l'appelant a dit avant que la commande ait ses préalables (mode, zone), gardé tel quel et pris dès qu'ils sont posés.
        "dits_en_attente": [],
        # Lot 6 (E15, E22) : ce que le greffier a noté (précaution, consigne), une proposition jointe à la note de la commande, jamais une case posée.
        "notes_du_greffier": {},
    }


def serialisable(valeur: Any) -> Any:
    """Une copie de ``valeur`` que la fiche de l'appel peut écrire en JSON : une date ou une heure devient son texte ISO.
    Ce que la source rend (l'heure annoncée est un ``datetime``) ne doit jamais entrer tel quel dans le panier."""
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {k: serialisable(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [serialisable(v) for v in valeur]
    return valeur


def du_dossier(fiche: dict | None) -> dict[str, Any]:
    """Le panier de l'appel, créé au premier besoin. Sans fiche (un essai isolé) : un panier jetable."""
    if not isinstance(fiche, dict):
        return nouveau()
    existant = fiche.get(CLE)
    if not isinstance(existant, dict) or "lignes" not in existant:
        existant = fiche[CLE] = nouveau()
    return ETAPE.monter(existant, empreinte)


def repartir_de_zero(fiche: dict | None) -> dict[str, Any]:
    """Un panier neuf (après une commande enregistrée : la suivante est une autre commande). Le client reste connu, et le mode aussi : le panier neuf est donc une commande commencée (``_action_ouverte`` la voit dès le mode)."""
    ancien = du_dossier(fiche)
    neuf = nouveau()
    neuf["client"] = dict(ancien.get("client") or {})
    neuf["mode"] = ancien.get("mode")
    neuf["zone"] = ancien.get("zone")
    neuf["adresse"] = ancien.get("adresse")
    if isinstance(fiche, dict):
        fiche[CLE] = neuf
    return neuf


def remplacer_par(p: dict[str, Any], autre: dict[str, Any]) -> None:
    """La SEULE restauration permise d'un panier entier : le dictionnaire de l'appel garde son identité (la fiche le tient) et prend l'état ``autre`` : l'essai validé
    (``prealables._valider``), le panier d'avant restauré quand un changement est refusé (``changement.remettre``), le panier neuf d'une nouvelle commande (DC5,
    ``registre.repartir``). L'étape vient avec cet état : c'est celle qu'il portait ; ce n'est pas une transition, c'est un état déjà cohérent qu'on reprend."""
    p.clear()
    p.update(autre)


def numeroter_les_lignes(p: dict[str, Any]) -> None:
    """``ligne_id`` stable (lot 4, M33) : une ligne reçoit son numéro à sa création et le garde ; un numéro n'est jamais réutilisé dans l'appel
    (après un retrait, « la ligne 2 » désigne toujours la même ligne, celle que l'état a montrée au modèle)."""
    suivant = max([int(p.get("prochaine_ligne") or 1), *(int(l.get("n") or 0) + 1 for l in p["lignes"])])
    for ligne in p["lignes"]:
        if not ligne.get("n"):
            ligne["n"] = suivant
            suivant += 1
    p["prochaine_ligne"] = suivant


def moyen_du_paiement(p: dict[str, Any]) -> str | None:
    """C3 (lot 19 bis) : le moyen de règlement posé dans le panier, lu à l'endroit où ``regler`` l'écrit (``paiement.moyen``) ; une valeur calculée (``moyens[0]``) vaut aussi.
    Une seule clé lue partout (vue de l'état, état du modèle) : avant, la vue lisait ``moyens[0]`` et le moyen n'était jamais montré."""
    paiement = p.get("paiement") if isinstance(p.get("paiement"), dict) else {}
    if paiement.get("moyen"):
        return str(paiement["moyen"])
    moyens = paiement.get("moyens")
    return str(moyens[0].get("moyen")) if isinstance(moyens, list) and moyens and isinstance(moyens[0], dict) and moyens[0].get("moyen") else None


CLES_DU_REGLEMENT = ("moyen_de_paiement", "rendu_sur", "part", "moyen_reste")


def vouloir_le_reglement(p: dict[str, Any], dit: dict[str, Any]) -> None:
    """n° 30 : ce que la personne dit du règlement s'écrit dans la commande (``reglement_voulu``), seul endroit qui le garde : un autre moyen redit sans part
    remplace le règlement entier (Pierre 10) et un moyen autre qu'espèces ne se règle pas sur un billet (C3)."""
    from api.services.actions_communes.moyens_de_paiement import MOYEN_DE_BASE_SELON_LA_FICHE as BASE

    voulu = p.setdefault("reglement_voulu", {})
    autre = BASE.get(dit.get("moyen_de_paiement"), dit.get("moyen_de_paiement"))
    if autre and voulu.get("moyen_de_paiement") not in (None, autre) and "part" not in dit and "moyen_reste" not in dit:
        effacer_le_partage(p)
    voulu.update({k: (BASE.get(v, v) if k in ("moyen_de_paiement", "moyen_reste") else v) for k, v in dit.items() if k in CLES_DU_REGLEMENT})
    if "rendu_sur" not in dit and autre and autre != "especes" and (p.get("paiement") or {}).get("moyen_reste") != "especes":
        effacer_le_billet(p)


def effacer_le_billet(p: dict[str, Any]) -> None:
    """C3 : un moyen autre qu'espèces ne se règle pas sur un billet : le billet dit avant est effacé (dans la fiche de fin et dans le règlement), il ne repart plus à chaque fiche."""
    (p.get("reglement_voulu") or {}).pop("rendu_sur", None)
    if isinstance(p.get("paiement"), dict):
        p["paiement"].pop("rendu_sur", None)


def effacer_le_partage(p: dict[str, Any]) -> None:
    """Pierre 10 : un autre moyen redit SANS part (« finalement tout en espèces » après « 25 euros en titres, le reste en carte ») remplace le règlement entier : la part, le
    moyen du reste et le billet dits avant sont effacés (dans la fiche de fin et dans le règlement), comme C3 le fait pour le billet seul."""
    for cle in ("part", "moyen_reste", "rendu_sur"):
        (p.get("reglement_voulu") or {}).pop(cle, None)
        if isinstance(p.get("paiement"), dict):
            p["paiement"].pop(cle, None)


def toucher(p: dict[str, Any]) -> None:
    """Le panier a changé : la version avance, la relecture et l'accord donné à la relecture ne valent plus (C1, lot 19 bis : sans cela, le panier changé après le « oui » était enregistré sans
    nouvelle relecture) ; les lignes nouvelles sont numérotées."""
    p["version"] += 1
    ETAPE.transition(p, ETAPE.PANIER_TOUCHE)
    numeroter_les_lignes(p)


def toucher_si_change(essai: dict[str, Any], avant: dict[str, Any]) -> None:
    """``toucher`` seulement quand les lignes ont vraiment changé : « mettez-en deux » quand il y en a déjà deux ne change rien, la relecture et l'accord valent encore."""
    if essai["lignes"] != avant["lignes"]:
        toucher(essai)


def pieces(ligne: dict[str, Any]) -> int:
    """C4 : la quantité d'une ligne telle que la personne la dit et l'entend : en PIÈCES quand l'article est vendu par lot (la ligne compte des lots, ``quantite``, pour la caisse), sinon la quantité."""
    lot = ligne.get("lot_de_vente")
    return int(ligne.get("quantite") or 0) * int(lot) if lot else int(ligne.get("quantite") or 0)


def a_completer(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [l for l in p["lignes"] if l.get("attente")]


def lignes_pretes(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [l for l in p["lignes"] if not l.get("attente") and l.get("code")]


def pour_le_chiffrage(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Les lignes complètes au format que la source chiffre : ``code``, ``quantite``, ``choix``, ``retires``, ``note``."""
    return [
        {"code": l["code"], "quantite": l["quantite"], "choix": l["choix"], "retires": list(l["retires"]), "note": l.get("note"), "poids_g": l.get("poids_g")}
        for l in lignes_pretes(p)
    ]


def empreinte(p: dict[str, Any]) -> str:
    """Ce qui fait qu'une relecture vaut encore : le mode, la zone, le moment voulu et chaque ligne prête, dans l'ordre."""
    contenu = {
        "mode": p["mode"], "zone": (p.get("zone") or {}).get("id"), "heure": p.get("heure_voulue"),
        "lignes": [(l["code"], l["quantite"], l["choix"], sorted(l["retires"]), l.get("note"), l.get("poids_g")) for l in lignes_pretes(p)],
    }
    return hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def resume(p: dict[str, Any]) -> dict[str, Any]:
    """Ce que chaque retour d'outil dit du panier (court : le détail est dans ``voir_commande``)."""
    gardes = len(p.get("dits_en_attente") or [])
    return {
        "mode": p["mode"], "zone": (p.get("zone") or {}).get("nom"), "articles": sum(l["quantite"] for l in p["lignes"]),
        "a_completer": len(a_completer(p)),
        # SA-33 : dit seulement quand quelque chose attend un préalable (le modèle sait qu'il n'a rien à redemander).
        **({"gardes_en_attente": gardes} if gardes else {}),
    }
