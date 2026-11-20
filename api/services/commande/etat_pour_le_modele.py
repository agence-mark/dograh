"""[.mark] Mécanisme commun : l'ÉTAT de la commande en cours, donné au modèle de conversation à chaque requête (agent fiable, Evan, 17/11).

« La conversation est menée par le modèle ; le code apporte la fiabilité. » Le modèle formule toutes ses phrases ; pour poser la bonne question au
bon moment SANS appeler un outil pour la découvrir (deux passages du modèle par tour), il lit ici, en quelques lignes, ce que le code sait : le
mode et l'adresse posés, les lignes prises, le choix obligatoire encore ouvert avec ses options, ce qui manque ENSUITE dans l'ordre de la
commande (mode, adresse quand le mode l'exige, articles, puis à la fin prénom, numéro, règlement), la fermeture et la reprise, le minimum de la zone.

Des faits, jamais une consigne de conduite ni une phrase toute faite. Le texte se calcule SANS ouvrir la source (aucune requête ajoutée à la
requête du modèle) : sur le panier de la fiche, et sur ce que la source a dit pendant les gestes de l'appel, retenu par ``SourceQuiRetient``
(l'ouverture de chaque mode, le minimum de chaque zone, le dernier chiffrage), écrit dans le panier sous ``connu``. Avant tout geste, la
fermeture vient du contexte du décroché (état d'ouverture et réouverture, calculés par le code au décroché).

Le connecteur de la commande le déclare (``Connecteur.etat_pour_le_modele``) ; le mécanisme commun le range dans l'instruction système
(``workflow/etat_des_connecteurs.py``). Aucun mot de métier. ⛔ Ne lève jamais.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from api.services.commande import panier as P
from api.services.mots_dits import liste_dite, liste_dite_et, montant_en_lettres

CLE_CONNU = "connu"  # dans le panier : ce que la source a dit pendant les gestes de l'appel
ENTETE = "[État de la commande, tenu par le code]"

# Ce que ``finaliser`` attend (``question_en_attente`` = ``finaliser.<champ>``), dit comme une information à obtenir.
_ATTENTES_DE_LA_FIN = {
    "prenom": "le prénom",
    "telephone": "le numéro de téléphone",
    "second_numero": "le second numéro",
    "moyen": "le moyen de règlement",
    "moyen_reste": "le règlement du reste",
    "part": "la part réglée du premier moyen",
    "rendu_sur": "le montant donné, pour le rendu",
    "confirmer": "sa réponse à la relecture",
    "en_plus": "sa réponse à la proposition",
    "heure": "le jour et l'heure voulus",
}


# --------------------------------------------------------------------------- #
# Ce que la source dit pendant un geste, retenu (aucune requête de plus)
# --------------------------------------------------------------------------- #


def cle_du_chiffrage(mode: Any, lignes: Any, zone_id: Any) -> str:
    """Ce qui fait qu'un chiffrage vaut encore pour le panier : le mode, la zone et les lignes chiffrées, dans l'ordre."""
    contenu = json.dumps([mode, zone_id, lignes], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(contenu.encode()).hexdigest()[:16]


class SourceQuiRetient:
    """La source d'un geste, telle quelle, qui RETIENT au passage ce qu'elle dit d'utile à l'état : l'ouverture de chaque mode lu, le minimum
    d'une zone retenue, le dernier chiffrage. Tout le reste est délégué sans changement. Écrit dans le panier par ``retenir``, APRÈS le geste
    (un geste peut remplacer le contenu du panier par un essai validé)."""

    def __init__(self, source: Any) -> None:
        self._source = source
        self.ouverture: dict[str, dict[str, Any]] = {}
        self.minimums: dict[str, int] = {}
        self.chiffrage: dict[str, Any] | None = None

    def __getattr__(self, nom: str) -> Any:
        return getattr(self._source, nom)

    async def etat(self, mode: str) -> dict[str, Any]:
        etat = await self._source.etat(mode)
        try:
            vu: dict[str, Any] = {"ouvert": bool(etat.get("ouvert")), "planifiable": bool(etat.get("planifiee_permise"))}
            if not vu["ouvert"]:
                quand = etat.get("reprise") or etat.get("prochaine_ouverture")
                dire = getattr(self._source, "quand_dit", None)
                if quand is not None and dire is not None and hasattr(quand, "astimezone"):
                    vu["reprise"] = await dire(quand)
            self.ouverture[str(mode)] = vu
        except Exception as erreur:  # noqa: BLE001 -- l'état ne coûte jamais le geste
            logger.debug(f"[commande] ouverture non retenue : {erreur!r}")
        return etat

    async def chiffrer(self, mode: str, lignes: list[dict[str, Any]], zone_id: int | None, regles: dict[str, Any]) -> Any:
        r = await self._source.chiffrer(mode, lignes, zone_id, regles)
        try:
            sous_total = (getattr(r, "faits", None) or {}).get("sous_total")
            if isinstance(sous_total, int):
                self.chiffrage = {"cle": cle_du_chiffrage(mode, lignes, zone_id), "sous_total": sous_total}
        except Exception:  # noqa: BLE001
            pass
        return r

    async def verifier_adresse(self, texte: str) -> Any:
        r = await self._source.verifier_adresse(texte)
        try:
            zone = (getattr(r, "faits", None) or {}).get("zone") or {}
            if getattr(r, "statut", None) == "RETENU" and zone.get("id") is not None:
                self.minimums[str(zone["id"])] = int(zone.get("minimum") or 0)
        except Exception:  # noqa: BLE001
            pass
        return r


def retenir(p: dict[str, Any], source: Any) -> None:
    """Écrit dans le panier ce que la source a dit pendant le geste (``SourceQuiRetient``) et les modes qu'elle offre. ⛔ Ne lève jamais."""
    try:
        connu = p.setdefault(CLE_CONNU, {})
        modes = tuple(getattr(source, "modes", ()) or ())
        libelles = getattr(source, "libelles_des_modes", None) or {}
        if modes:
            connu["modes"] = {m: libelles.get(m, m) for m in modes}
            exige = getattr(source, "exige_une_zone", None)
            connu["modes_a_adresse"] = [m for m in modes if exige is not None and exige(m)]
        if isinstance(source, SourceQuiRetient):
            if source.ouverture:
                connu.setdefault("ouverture", {}).update(source.ouverture)
            if source.minimums:
                connu.setdefault("minimums", {}).update(source.minimums)
            if source.chiffrage is not None:
                connu["chiffrage"] = source.chiffrage
    except Exception as erreur:  # noqa: BLE001
        logger.debug(f"[commande] état non retenu : {erreur!r}")


# --------------------------------------------------------------------------- #
# Le texte de l'état
# --------------------------------------------------------------------------- #


def _choix_de_la_ligne(l: dict[str, Any]) -> str:
    details = [c["nom"] for c in l.get("choix") or [] if isinstance(c, dict) and c.get("nom")]
    morceaux = []
    if details:
        morceaux.append("avec " + liste_dite_et(details))
    if l.get("retires"):
        morceaux.append("sans " + liste_dite_et(list(l["retires"])))
    if l.get("note"):
        morceaux.append(str(l["note"]))
    return f" ({' ; '.join(morceaux)})" if morceaux else ""


def _attente_dite(l: dict[str, Any]) -> str:
    q = l.get("attente") or {}
    options = [str(o) for o in q.get("options") or []]
    nom = str(q.get("nom") or "un choix")
    return f"{nom} pour {l.get('article_nom') or l.get('nom')}" + (f" : {liste_dite(options)}" if options else "")


def _ligne(l: dict[str, Any]) -> str:
    attente = l.get("attente") or {}
    nom = (l.get("article_nom") or l.get("nom")) if attente else l.get("nom")
    texte = f"{P.pieces(l) if 'quantite' in l else 1} × {nom}{_choix_de_la_ligne(l)}"
    return texte + (f", {attente.get('nom') or 'un choix'} à choisir" if attente else "")


def _fermeture(p: dict[str, Any], connu: dict[str, Any], appel: dict[str, Any]) -> str | None:
    """La fermeture en ce moment et la reprise : du mode posé, sinon de tous les modes connus, sinon du contexte du décroché."""
    if p.get("heure_voulue"):
        return None  # une heure voulue est gardée : la commande est pour plus tard, la fermeture de maintenant ne compte plus
    ouverture = connu.get("ouverture") or {}
    modes = connu.get("modes") or {}
    mode = p.get("mode")
    if mode and mode in ouverture:
        vus = {mode: ouverture[mode]}
    else:
        vus = {m: v for m, v in ouverture.items() if not modes or m in modes}
    if vus:
        fermes = {m: v for m, v in vus.items() if not v.get("ouvert")}
        if not fermes:
            return None
        quoi = "fermé en ce moment" if len(fermes) == len(vus) else f"fermé en ce moment {liste_dite_et([modes.get(m, m) for m in fermes])}"
        reprises = sorted({str(v["reprise"]) for v in fermes.values() if v.get("reprise")})
        texte = quoi.capitalize() + (f", reprise : {liste_dite_et(reprises)}" if reprises else "")
        if any(v.get("planifiable") for v in fermes.values()):
            texte += " ; une commande pour plus tard est possible"
        return texte + "."
    from api.services.pipecat.etat_ouverture import CLE_ETAT, CLE_REOUVERTURE, OUVERT

    etat = str((appel or {}).get(CLE_ETAT) or "").strip()
    if not etat or etat == OUVERT:
        return None
    reouverture = str((appel or {}).get(CLE_REOUVERTURE) or "").strip()
    dit = {"FERME": "fermé", "PAUSE": "en pause"}.get(etat, etat.lower().replace("_", " "))
    return f"Établissement {dit} en ce moment" +(f", réouverture : {reouverture}." if reouverture else ".")


def _minimum(p: dict[str, Any], connu: dict[str, Any]) -> str | None:
    zone_id = (p.get("zone") or {}).get("id")
    minimum = (connu.get("minimums") or {}).get(str(zone_id)) if zone_id is not None else None
    if not minimum:
        return None
    dit = montant_en_lettres(int(minimum))
    chiffrage = connu.get("chiffrage") or {}
    pretes = P.pour_le_chiffrage(p)
    if not pretes:
        return f"Minimum de commande pour cette adresse : {dit}."
    if chiffrage.get("cle") == cle_du_chiffrage(p.get("mode"), pretes, zone_id) and isinstance(chiffrage.get("sous_total"), int):
        manque = int(minimum) - chiffrage["sous_total"]
        if manque > 0:
            return f"Minimum de commande pour cette adresse : {dit}, pas atteint (il manque {montant_en_lettres(manque)})."
        return None  # atteint : rien à en dire
    return f"Minimum de commande pour cette adresse : {dit}."


def _notes(fiche: Any) -> dict[str, Any]:
    """Ce que le greffier a noté (``extracted_variables`` ou la fiche elle-même)."""
    if not isinstance(fiche, dict):
        return {}
    notes = fiche.get("extracted_variables")
    return notes if isinstance(notes, dict) else fiche


def _consigne_a_demander(p: dict[str, Any], connu: dict[str, Any], notes: dict[str, Any] | None) -> bool:
    """Le mode exige une adresse, elle est retenue, et le greffier n'a noté aucune consigne pour le livreur (pas même « aucune »)."""
    return bool(p.get("mode") in (connu.get("modes_a_adresse") or []) and p.get("zone") and not (notes or {}).get("consigne_livreur"))


def _a_la_fin(p: dict[str, Any], notes: dict[str, Any] | None = None) -> list[str]:
    """Appel 2631 (Evan, 18/11) : ce qui reste à obtenir après le récapitulatif, dans l'ordre (règlement, numéro, prénom) ; ce que le greffier a
    déjà noté est obtenu : jamais redemandé."""
    client = p.get("client") or {}
    notes = notes or {}
    manque = []
    if _consigne_a_demander(p, p.get(CLE_CONNU) or {}, notes):
        manque.append("une consigne pour le livreur")
    if not p.get("paiement") and not notes.get("moyen_de_paiement"):
        manque.append("règlement")
    if not client.get("telephone") and not client.get("telephone_affiche") and not notes.get("telephone"):
        manque.append("numéro de téléphone")
    if not client.get("prenom") and not notes.get("prenom"):
        manque.append("prénom")
    return manque


# --------------------------------------------------------------------------- #
# Le texte de l'état, au format de la version finale (chantier Partie 1, lot 2, étape 8 ; port de ``banc-b13/commande_b13.py`` ``etat_texte_v6``
# et de la ligne B de B8, ``appel_b13.py`` ``lignes_b13``). Les mots sont ceux du banc, jamais réécrits.
# --------------------------------------------------------------------------- #

LIGNE_B = "- Rien n'est changé tant que tu n'as pas rempli la fiche."
# Lot 6 (E15, G07 ; D54) : les champs du greffier sous leurs noms de la version finale (``banc-b13/commande_b13.py`` ``NOMS_GREFFIER``, noms
# renommés de ``textes_b13.GREFFIER_RENOMS`` et ``noms_b13.GREFFIER30``) : aucun ne porte le nom d'un outil ; un nom partagé avec une case a son sens
# (déclaré au glossaire). Ce qu'il note est une PROPOSITION, montrée comme telle ; seule la fiche écrit dans la commande.
CHAMPS_DU_GREFFIER = {"mode_de_retrait": "mode de retrait", "adresse": "adresse", "commune": "commune", "consigne_livreur": "consigne pour le livreur",
                      "moyen_de_paiement": "moyen de paiement", "prenom": "prénom", "telephone": "numéro de téléphone", "allergie": "allergie"}
LIGNE_DU_GREFFIER = "- Noté par le greffier (une proposition ; seule la fiche écrit dans la commande) : "


def ligne_de_l_appel(fiche: Any) -> str:
    """La ligne de la commande dans l'état de l'appel montré à l'accueil (``banc-b13/commande_b13.py`` ``etat_appel_v6``, mot pour mot)."""
    p = fiche.get(P.CLE) if isinstance(fiche, dict) else None
    p = p if isinstance(p, dict) and "lignes" in p else P.nouveau()
    if p.get("enregistree") and not p.get("annulee"):
        e = p["enregistree"] or {}
        return f"- Commande de cet appel : enregistrée (numéro {e.get('numero_court') or e.get('numero')})."
    if p.get("annulee"):
        return "- Commande de cet appel : annulée."
    if p.get("lignes") or p.get("mode"):
        lignes = " ; ".join(f"{P.pieces(l)} × {_libelle_de_la_ligne(l)}" for l in p["lignes"]) or "aucune ligne"
        return f"- Commande de cet appel : commencée, pas encore enregistrée ({lignes})."
    return "- Commande de cet appel : aucune."


def ligne_du_greffier(fiche: Any) -> str | None:
    notes = _notes(fiche)
    g = [(k, v) for k, v in notes.items() if k in CHAMPS_DU_GREFFIER and isinstance(v, str) and v.strip()]
    return LIGNE_DU_GREFFIER + " ; ".join(f"{CHAMPS_DU_GREFFIER[k]} « {v} »" for k, v in g) + "." if g else None
NOMS_DES_QUESTIONS = {"relecture": "récapitulatif", "proposition": "proposition", "variante": "variante", "ambiguite": "précision", "reprise": "reprise", "etape": "étape", "heure_proposee": "heure proposée", "numero_affiche": "numéro qui s'affiche"}
LIBELLES_DES_MODES = {"emporter": "à emporter", "livraison": "en livraison", "sur_place": "sur place"}
LIBELLES_DES_MOYENS = {"carte_bancaire": "carte", "carte": "carte", "especes": "espèces", "titre_restaurant": "titre-restaurant", "carte_bancaire_a_la_livraison": "carte à la livraison"}


def _nom_d_etape(nom: str) -> str:
    """Le nom court d'une étape de formule, comme l'état du banc le dit (``formule_b12.libelle``) : « Boisson 33 cl du menu » → « boisson 33 cl »."""
    return nom.split(" de la ")[0].split(" du ")[0].lower()


def _libelle_de_la_ligne(l: dict[str, Any]) -> str:
    """Le libellé d'une ligne tel que la carte le donne (E4, ambiguïté 17), ses retraits entre parenthèses. Point de contrôle du lot 7 (f307) : une
    ligne de formule dit chaque étape choisie et son choix, comme l'état du banc (B11 point 7a, ``formule_b12.libelle``) ; sans eux, le modèle ne
    savait pas que la boisson était un choix de la ligne et retirait tout le menu pour la changer."""
    nom = str(l.get("nom") or "")
    if l.get("attente"):
        nom = f"{l.get('article_nom') or nom}, variante à choisir"
    parts = []
    if l.get("formule_id"):
        parts += [f"{_nom_d_etape(str(c['etape']))} : {c['nom']}" for c in l.get("choix") or [] if isinstance(c, dict) and c.get("etape") and c.get("nom")]
    retires = [str(r) for r in l.get("retires") or []]
    if retires:
        parts.append(f"sans {', '.join(retires)}")
    return nom + (f" ({' ; '.join(parts)})" if parts else "")


def _voie(adresse: Any) -> str | None:
    return adresse.get("voie") if isinstance(adresse, dict) else (str(adresse) if adresse else None)


def _commune(p: dict[str, Any]) -> str | None:
    adresse = p.get("adresse")
    return (adresse.get("commune") if isinstance(adresse, dict) else None) or p.get("commune_dite")


def _question(q: dict[str, Any]) -> str:
    if q.get("type") == "proposition" and q.get("article_propose"):
        quoi = q["article_propose"] + (f", offert ({q.get('offre') or 'offre'})" if q.get("offerte") else ", son prix dit par le code")
        return f"- Question en attente : {q['id']} (proposition) : {quoi} ; réponses : accepte, refuse, autre."
    if q.get("type") == "etape":
        return f"- Question en attente : {q['id']} (étape) : « {q.get('texte') or ''} » ; sa réponse : son choix, dans valeurs."
    return f"- Question en attente : {q['id']} ({NOMS_DES_QUESTIONS.get(q.get('type'), q.get('type'))}) : « {q.get('texte') or ''} » ; réponses : accepte, refuse, autre."


def ce_qui_manque_ensuite(p: dict[str, Any], connu: dict[str, Any]) -> str | None:
    """Ce qui manque ensuite, dans l'ordre de la commande, aux mots de la version finale (``guichet_candidat.manque``, vocabulaire de B8)."""
    if p.get("enregistree") or p.get("annulee"):
        return None
    if not p.get("mode"):
        modes = list((connu.get("modes") or {}).values()) or ["à emporter", "en livraison"]
        return f"le mode de retrait ({liste_dite(modes)})"
    a_adresse = p["mode"] in (connu.get("modes_a_adresse") or ["livraison"])
    if a_adresse and not p.get("zone"):
        if not _voie(p.get("adresse")) and not _commune(p):
            return "l'adresse de livraison (numéro, rue et commune)"
        return "la commune de livraison" if not _commune(p) else "l'adresse (numéro et rue)"
    if not p.get("lignes"):
        return "les articles"
    if P.a_completer(p):
        return "une variante à choisir"
    if not p.get("relecture"):
        return "d'autres articles, ou qu'elle dise qu'elle a tout dit"
    if not p.get("relecture_acceptee"):
        return "son accord sur le récapitulatif"
    client = p.get("client") or {}
    if not p.get("paiement"):
        return "le moyen de paiement"
    if not (client.get("telephone") or client.get("telephone_affiche")):
        return "le numéro de téléphone"
    if not client.get("prenom"):
        return "le prénom"
    return None


def _moyen_pose(p: dict[str, Any]) -> str | None:
    moyen = P.moyen_du_paiement(p)  # C3 : la clé que ``regler`` écrit
    return LIBELLES_DES_MOYENS.get(moyen, moyen) if moyen else None


def texte(fiche: dict | None, appel: dict | None = None) -> str | None:
    """L'état de la commande, au format de la version finale. ⛔ Ne lève jamais."""
    try:
        p = fiche.get(P.CLE) if isinstance(fiche, dict) else None
        p = p if isinstance(p, dict) and "lignes" in p else P.nouveau()
        connu = p.get(CLE_CONNU) if isinstance(p.get(CLE_CONNU), dict) else {}
        lignes_de_l_etat = [ENTETE]
        enregistree = p.get("enregistree")
        if enregistree and not p.get("annulee"):
            numero = (enregistree or {}).get("numero_court") or (enregistree or {}).get("numero")
            lignes_de_l_etat.append(
                f"- Commande de cet appel enregistrée (numéro {numero}) : la changer passe par changer_quantite ou les cases du mode de retrait, de "
                "l'adresse et de l'heure ; l'annuler, par annuler_une_commande_enregistree."
            )
        if p.get("annulee"):
            lignes_de_l_etat.append("- Commande de cet appel annulée : rien n'est enregistré.")
        mode = p.get("mode")
        libelle = (connu.get("modes") or {}).get(mode) or LIBELLES_DES_MODES.get(mode) or mode
        pour = f", pour {p['heure_voulue_dite']}" if p.get("heure_voulue_dite") else ""
        lignes_de_l_etat.append("- Mode de retrait : " + (libelle or "pas encore dit") + pour + ".")
        if mode and mode in (connu.get("modes_a_adresse") or ["livraison"]):
            lignes_de_l_etat.append(
                f"- Adresse : {_voie(p.get('adresse')) or '(rue pas encore dite)'} ; commune : {_commune(p) or '(pas encore dite)'} ; consigne pour le livreur : "
                f"{p.get('consigne_livreur') or 'pas encore dite'}."
            )
        if p.get("lignes"):
            lignes_de_l_etat.append("- Lignes : " + " ; ".join(f"ligne {l['n']} : {P.pieces(l)} × {_libelle_de_la_ligne(l)}" for l in p["lignes"]) + ".")
        else:
            lignes_de_l_etat.append("- Lignes : aucune.")
        client = p.get("client") or {}
        moyen = _moyen_pose(p)
        infos = [f"moyen de paiement {moyen}" if moyen else None, f"numéro de téléphone {client['telephone']}" if client.get("telephone") else None,
                 f"prénom {client['prenom']}" if client.get("prenom") else None]
        infos = [i for i in infos if i]
        if infos:
            lignes_de_l_etat.append("- Déjà posé : " + ", ".join(infos) + ".")
        if p.get("note"):
            lignes_de_l_etat.append(f"- Notes de la commande : « {p['note']} ».")
        q = p.get("question") if isinstance(p.get("question"), dict) else None
        lignes_de_l_etat.append(_question(q) if q else "- Question en attente : aucune.")
        manque = ce_qui_manque_ensuite(p, connu)
        if manque and not q:
            lignes_de_l_etat.append(f"- Ce qui manque ensuite : {manque}.")
        if q and q.get("type") == "relecture" and not p.get("relecture_acceptee"):
            lignes_de_l_etat.append("- Cases ouvertes avec le récapitulatif : moyen_de_paiement, rendu_sur, part, moyen_reste, telephone, prenom ; le code les prend après son accord.")
        greffier = ligne_du_greffier(fiche)
        if greffier:
            lignes_de_l_etat.append(greffier)
        objet = bool((p.get("lignes") or mode or enregistree) and not p.get("annulee"))
        if objet or q:
            lignes_de_l_etat.append(LIGNE_B)
        return "\n".join(lignes_de_l_etat)
    except Exception as erreur:  # noqa: BLE001 -- l'état ne coûte jamais la requête
        logger.warning(f"[commande] état pour le modèle non calculé : {erreur!r}")
        return None
