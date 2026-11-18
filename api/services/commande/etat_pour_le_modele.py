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
    texte = f"{l.get('quantite', 1)} × {nom}{_choix_de_la_ligne(l)}"
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
    if not p.get("paiement") and not notes.get("mode_de_paiement"):
        manque.append("règlement")
    if not client.get("telephone") and not client.get("telephone_affiche") and not notes.get("numero_dicte"):
        manque.append("numéro de téléphone")
    if not client.get("prenom") and not notes.get("prenom"):
        manque.append("prénom")
    return manque


def _ensuite(p: dict[str, Any], connu: dict[str, Any], notes: dict[str, Any] | None = None) -> str | None:
    modes = connu.get("modes") or {}
    if not p.get("mode"):
        return "le mode" + (f" ({liste_dite(list(modes.values()))})" if modes else "")
    if p["mode"] in (connu.get("modes_a_adresse") or []) and not p.get("zone"):
        doute = p.get("adresse_en_doute") or {}
        candidats = [str(c.get("nom")) for c in doute.get("candidats") or [] if isinstance(c, dict) and c.get("nom")]
        if candidats:
            return f"la commune de l'adresse « {doute.get('texte')} » ({liste_dite(candidats)})"
        return "l'adresse"
    if _consigne_a_demander(p, connu, notes) and not p.get("lignes"):
        # Evan (18/11) : la consigne pour le livreur se demande juste après l'adresse ; « aucune » notée par le greffier vaut réponse.
        return "une consigne pour le livreur (code, étage, interphone)"
    en_attente = P.a_completer(p)
    if en_attente:
        return _attente_dite(en_attente[0])
    attente = str(p.get("question_en_attente") or "")
    outil, _, champ = attente.partition(".")
    if outil == "finaliser" and champ in _ATTENTES_DE_LA_FIN:
        return _ATTENTES_DE_LA_FIN[champ]
    if champ == "heure":
        return _ATTENTES_DE_LA_FIN["heure"]
    if not p.get("lignes"):
        return "les articles"
    return "d'autres articles, ou qu'elle a tout dit"


def texte(fiche: dict | None, appel: dict | None = None) -> str | None:
    """L'état de la commande en quelques lignes de faits, ou ``None`` quand il n'y a rien à dire. ⛔ Ne lève jamais."""
    try:
        p = fiche.get(P.CLE) if isinstance(fiche, dict) else None
        p = p if isinstance(p, dict) and "lignes" in p else P.nouveau()
        connu = p.get(CLE_CONNU) if isinstance(p.get(CLE_CONNU), dict) else {}
        appel = appel if isinstance(appel, dict) else {}
        lignes = [ENTETE]
        enregistree = p.get("enregistree")
        if enregistree and p.get("lignes"):
            numero = (enregistree or {}).get("numero_court")
            lignes.append(f"- Commande enregistrée{f' (numéro {numero})' if numero else ''}. Une nouvelle commande repartirait de zéro.")
            return "\n".join(lignes)
        mode = p.get("mode")
        if mode:
            libelle = (connu.get("modes") or {}).get(mode) or p.get("mode_dit") or mode
            pour = f", pour {p['heure_voulue_dite']}" if p.get("heure_voulue_dite") else (", pour plus tard" if p.get("a_planifier") and p.get("heure_voulue") else "")
            lignes.append(f"- Mode : {libelle}{pour}.")
        if p.get("zone"):
            lignes.append(f"- Adresse : {p.get('adresse') or ''} (zone {p['zone'].get('nom')}).".replace(":  (", ": ("))
        if p.get("lignes"):
            lignes.append("- Pris : " + " ; ".join(_ligne(l) for l in p["lignes"]) + ".")
        else:
            lignes.append("- Pris : rien pour l'instant.")
        gardes = [str(d.get("articles")) for d in p.get("dits_en_attente") or [] if isinstance(d, dict) and d.get("articles")]
        if gardes:
            lignes.append(f"- Dit avant le mode ou l'adresse, gardé et pris dès qu'ils sont posés : {' ; '.join(gardes)}.")
        for fait in (_minimum(p, connu), _fermeture(p, connu, appel)):
            if fait:
                lignes.append(f"- {fait}")
        notes = _notes(fiche)
        ensuite = _ensuite(p, connu, notes)
        if ensuite:
            lignes.append(f"- Ce qui manque ensuite : {ensuite}.")
        fin = _a_la_fin(p, notes) if p.get("lignes") and not str(p.get("question_en_attente") or "").startswith("finaliser.") else []
        if fin:
            lignes.append(f"- Encore à obtenir quand elle aura tout dit : {liste_dite_et(fin)}.")
        return "\n".join(lignes)
    except Exception as erreur:  # noqa: BLE001 -- l'état ne coûte jamais la requête
        logger.warning(f"[commande] état pour le modèle non calculé : {erreur!r}")
        return None
