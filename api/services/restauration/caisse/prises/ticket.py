"""[.mark] Module Restauration, lot 10 : le TICKET de commande de l'imprimante (fonctions PURES, aucun réseau).

Un ticket est une liste de lignes ``(style, texte)`` (``titre``, ``gras``, ``texte``, ``separateur``, ``total``) rendue en deux formats que la fiche CloudPRNT sait
servir : ``text/vnd.star.markup`` (Star Document Markup : ``[align: centre]``, ``[bold: on]``, ``[magnify: width 2; height 2]``, ``[cut: feed; partial]``, tags lus
dans la documentation de Star) et ``text/plain``. Les deux sont en UTF-8 : les accents, la cédille, « œ » et « € » du texte de la commande restent tels quels.

Le texte venu de la commande (nom d'un plat, note, prénom, adresse) est ASSAINI avant d'entrer dans le balisage : ``[`` et ``]`` y deviennent ``(`` et ``)``, les retours à la
ligne et les caractères de contrôle disparaissent : une note de client ne peut jamais injecter une balise (cut, magnify…) dans le ticket.

Rendus en clair (la fiche de l'imprimante le dit) : le second numéro, le paiement mixte (« TR 20 € + ESP 4,50 € (rendre sur 50 €) », E-34), les retraits, les notes de ligne.
Une commande planifiée imprimée tout de suite porte « PROGRAMMÉE » en tête (T-11, mode « immédiat »).
"""

from __future__ import annotations

import re
import unicodedata

from api.services.actions_communes.moyens_de_paiement import ABREGES
from api.services.actions_communes.euros import en_euros
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

MEDIA_MARKUP = "text/vnd.star.markup"
MEDIA_TEXTE = "text/plain"
MEDIAS = (MEDIA_MARKUP, MEDIA_TEXTE)  # l'ordre dit notre préférence ; l'imprimante choisit parmi ce qu'elle sait

NOM_DU_MODE = {"emporter": "À EMPORTER", "livraison": "LIVRAISON", "sur_place": "SUR PLACE"}
LARGEUR = 32  # colonnes d'un ticket 58 mm ; le texte long passe à la ligne, jamais coupé en plein mot si l'on peut

_CONTROLES = re.compile(r"[\x00-\x1f\x7f]+")


def assainir(texte: Any) -> str:
    """Le texte d'un client rendu sûr pour le balisage et la page : NFC, sans caractère de contrôle, sans crochets."""
    brut = unicodedata.normalize("NFC", "" if texte is None else str(texte))
    return _CONTROLES.sub(" ", brut).replace("[", "(").replace("]", ")").strip()


def _paiement(paiement: dict) -> str | None:
    moyens = (paiement or {}).get("moyens") or []
    if not moyens:
        return None
    morceaux = [f"{ABREGES.get(m['moyen'], str(m['moyen']).upper())} {en_euros(m['montant'])}" for m in moyens]
    ligne = " + ".join(morceaux)
    rendu = (paiement or {}).get("rendu_sur")
    if isinstance(rendu, int) and rendu > 0:
        ligne += f" (rendre sur {en_euros(rendu)})"
    return ligne


def lignes_du_ticket(commande: dict[str, Any], *, fuseau: str = "Europe/Paris", programmee: bool = False) -> list[tuple[str, str]]:
    """Le ticket en lignes ``(style, texte)`` d'après la commande du format commun (``commande_complete``)."""
    sortie: list[tuple[str, str]] = []
    if programmee:
        sortie.append(("titre", "PROGRAMMÉE"))
    sortie.append(("titre", f"N° {assainir(commande.get('numero_court') or str(commande['numero'])[:8])}"))
    sortie.append(("gras", NOM_DU_MODE.get(commande.get("mode"), assainir(commande.get("mode")).upper())))
    heure = commande.get("heure_annoncee") or commande.get("heure_voulue")
    if isinstance(heure, datetime):
        local = heure.astimezone(ZoneInfo(fuseau))
        sortie.append(("gras", f"Prête {local.strftime('%d/%m')} à {local.strftime('%H:%M')}"))
    sortie.append(("separateur", ""))
    client = commande.get("client") or {}
    if client.get("prenom"):
        sortie.append(("texte", assainir(client["prenom"])))
    if client.get("telephone"):
        sortie.append(("texte", f"Tél : {assainir(client['telephone'])}"))
    second = client.get("second_numero")
    if second and second.get("numero"):
        qui = " ".join(assainir(x) for x in (second.get("qui"), second.get("pourquoi")) if x)
        sortie.append(("texte", f"2e n° : {assainir(second['numero'])}" + (f" ({qui})" if qui else "")))
    adresse = commande.get("adresse")
    if isinstance(adresse, dict) and adresse:
        voie = adresse.get("voie") or adresse.get("ligne") or ""
        sortie.append(("texte", assainir(f"{voie} {adresse.get('code_postal') or ''} {adresse.get('commune') or ''}")))
    sortie.append(("separateur", ""))
    for ligne in commande.get("lignes") or []:
        sortie.append(("gras", f"{ligne['quantite']} x {assainir(ligne['nom'])}"))
        for choix in ligne.get("choix") or []:
            sortie.append(("texte", f"  + {assainir(choix.get('nom') or choix.get('option_code'))}"))
            for sous in choix.get("choix") or []:  # le choix imbriqué s'imprime en clair (la fiche le dit)
                sortie.append(("texte", f"    + {assainir(sous.get('nom') or sous.get('option_code'))}"))
        if ligne.get("retires"):
            sortie.append(("texte", "  Sans : " + ", ".join(assainir(r) for r in ligne["retires"])))
        if ligne.get("note"):
            sortie.append(("texte", f"  > {assainir(ligne['note'])}"))
    sortie.append(("separateur", ""))
    for remise in commande.get("remises") or []:
        sortie.append(("texte", f"{assainir(remise.get('nom'))} : -{en_euros(remise['montant'])}"))
    if commande.get("frais"):
        sortie.append(("texte", f"Livraison : {en_euros(commande['frais'])}"))
    sortie.append(("total", f"TOTAL {en_euros(commande['total'])}"))
    paiement = _paiement(commande.get("paiement") or {})
    if paiement:
        sortie.append(("texte", paiement))
    if commande.get("note"):
        sortie.append(("texte", f"Note : {assainir(commande['note'])}"))
    return sortie


def _couper(texte: str) -> list[str]:
    mots, lignes, courante = texte.split(" "), [], ""
    for mot in mots:
        if courante and len(courante) + 1 + len(mot) > LARGEUR:
            lignes.append(courante)
            courante = mot
        else:
            courante = f"{courante} {mot}".strip()
    return lignes + [courante] if courante else lignes or [""]


def en_texte(lignes: list[tuple[str, str]]) -> bytes:
    """``text/plain`` en UTF-8."""
    corps: list[str] = []
    for style, texte in lignes:
        if style == "separateur":
            corps.append("-" * LARGEUR)
        else:
            corps.extend(_couper(texte.upper() if style == "titre" else texte))
    return ("\n".join(corps) + "\n\n\n").encode("utf-8")


def en_markup(lignes: list[tuple[str, str]]) -> bytes:
    """``text/vnd.star.markup`` en UTF-8 : balises de Star Document Markup, texte assaini (``assainir`` a retiré les crochets)."""
    corps: list[str] = ["[align: left]"]
    for style, texte in lignes:
        if style == "separateur":
            corps.append("[bold: off]" + "-" * LARGEUR)
        elif style == "titre":
            corps.append(f"[align: centre][magnify: width 2; height 2][bold: on]{texte}[magnify][bold: off][align: left]")
        elif style == "total":
            corps.append(f"[bold: on][magnify: width 2]{texte}[magnify][bold: off]")
        elif style == "gras":
            corps.append(f"[bold: on]{texte}[bold: off]")
        else:
            corps.append(texte)
    corps.append("[cut: feed; partial]")
    return ("\n".join(corps) + "\n").encode("utf-8")


def rendre(commande: dict[str, Any], media: str, *, fuseau: str = "Europe/Paris", programmee: bool = False) -> bytes:
    """Le ticket dans le type de média demandé par l'imprimante (``MEDIAS``) ; un autre type : ``ValueError``."""
    lignes = lignes_du_ticket(commande, fuseau=fuseau, programmee=programmee)
    if media == MEDIA_MARKUP:
        return en_markup(lignes)
    if media == MEDIA_TEXTE:
        return en_texte(lignes)
    raise ValueError(f"Type de média non servi : {media!r}")
