"""[.mark] Moteur de la commande : les réglages, le résultat et les petits outils communs aux autres modules du moteur.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from api.services.actions_communes import phrases_d_information as INFO
from api.schemas.workflow_configurations import DEFAULT_COMMANDE_FOIS_AVANT_LA_SORTIE
from api.services.actions_communes.petits_mots import ARTICLES
from api.services.commande import panier as P
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS as MOTIFS_DES_PHRASES, NUMERO_DICTE_RELU



LONGUEUR_NOTE = 200


@dataclass(frozen=True)
class Reglages:
    """Les réglages de construction du module (registre des modules), lus dans la configuration de l'agent."""

    ordre_impose: bool = True  # la zone avant les articles quand le mode en exige une (W6)
    relecture_en_deux_temps: bool = True
    vente_en_plus: bool = True
    notes_libres: bool = True  # E-35 : « bien cuite », « sauce à part » : une note de ligne, sans prix
    fois_avant_la_sortie: int = DEFAULT_COMMANDE_FOIS_AVANT_LA_SORTIE  # M6 : combien de fois la même chose se redit avant la sortie (message à l'équipe) ; réglage du restaurant, défaut du schéma
    mentions_de_remise: int = 1  # T-08 : combien de fois par appel l'agent parle d'une remise de lui-même (0 : seulement sur demande)
    # M108 : la question qui finit la confirmation d'une commande enregistrée (phrase du code réglable, lue par l'action à l'endroit de l'appel) ;
    # ``None`` ou vide : la confirmation est dite seule.
    question_apres_enregistrement: str | None = MOTIFS_DES_PHRASES[APRES_ENREGISTREMENT].variantes_defaut[0]
    question_numero_dicte: str | None = MOTIFS_DES_PHRASES[NUMERO_DICTE_RELU].variantes_defaut[0]  # DC10 ; None : éteinte
    # M118 : la surcouche de l'agent sur la table standard des mots de taille (``tailles.py``) : ``{mot: rang}``, ``None`` retire un mot.
    mots_de_taille: dict[str, Any] | None = None


def _r(statut: str, faits: dict | None = None, suggestion: str = "", manque: str | None = None) -> Resultat:
    return Resultat(statut, faits or {}, suggestion, manque)


def _avec(resultat: Resultat, p: dict[str, Any], **plus: Any) -> Resultat:
    """Le résultat, avec le résumé du panier : le modèle sait toujours où en est la commande."""
    return Resultat(resultat.statut, {**resultat.faits, "panier": {**P.resume(p), **plus}}, resultat.suggestion, resultat.manque)


# --------------------------------------------------------------------------- #
# finaliser : relire, puis enregistrer
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Appelant:
    """Ce que le code sait de l'appelant, jamais le modèle : le numéro qui s'affiche (E.164, ``None`` s'il est masqué) et l'identifiant de l'appel."""

    telephone_affiche: str | None = None
    appel_id: str | None = None


CLE_NOTES_DU_GREFFIER = "notes_du_greffier"  # dans le panier : ce que le greffier a noté (allergie, consigne), posé par la porte à chaque fiche


def cle_de_la_remise(ref: Any) -> str:
    """La clé d'une remise au journal de ce qui est dit (B3, M5)."""
    return f"remise:{ref}"


def _le(nom: str, genre: str | None) -> str:
    """« Le filtre », « La vis », « L'écrou » : l'article défini du nom proposé, d'après son genre (sans mot de métier)."""
    if _sans_accent(nom[:1]) in "aeiouyh":
        return f"L'{nom}"
    return f"{'La' if genre == 'f' else 'Le'} {nom}"


# --------------------------------------------------------------------------- #
# La commande enregistrée reste adressable (lot 4, E10, S8 ; A31, M34) : une commande par appel (E30), changée ou annulée selon la prise
# --------------------------------------------------------------------------- #


def commande_de_l_appel(p: dict[str, Any]) -> dict[str, Any] | None:
    """La commande enregistrée dans CET appel (numéro, numéro court, heure annoncée, total), tant qu'elle n'est pas annulée ; ``None`` sinon."""
    commande = p.get("enregistree")
    return commande if isinstance(commande, dict) and commande.get("numero") and not p.get("annulee") else None


# --------------------------------------------------------------------------- #
# voir_produit : la composition et les signalements d'un article (lot 7, E-14, E-15)
# --------------------------------------------------------------------------- #

NON_CONFIRMABLE = INFO.NON_CONFIRMABLE
# Des mots de la langue qui ne nomment rien du catalogue (aucun mot de métier) : ce qui reste nomme une catégorie, un article ou rien.
_MOTS_DE_LA_QUESTION = ARTICLES | {
    "d", "vous", "avez", "auriez", "est", "ce", "que", "qu", "quoi", "qui", "il", "y", "a",
    "en", "pour", "moi", "nous", "quelque", "chose", "choses", "truc", "trucs", "rien", "autre", "aussi", "chez", "votre", "vos",
}
_PLUS_DE_NOMS = 5
_PAS_SUR = INFO.PAS_SUR


def _mots_significatifs(texte: str) -> list[str]:
    """Les mots qui nomment quelque chose, tels qu'ils sont dits (« des tartes » → ``["tartes"]``)."""
    return [m for m in re.findall(r"[\w-]+", texte) if _sans_accent(m) not in _MOTS_DE_LA_QUESTION]


def _sans_accent(mot: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", mot.casefold()) if unicodedata.category(c) != "Mn")


def _racines(texte: str) -> set[str]:
    """Les mots significatifs, sans accent ni marque du pluriel : « Tartes salées » → ``{tarte, salee}``."""
    racines = set()
    for mot in re.findall(r"[\w-]+", texte):
        m = _sans_accent(mot)
        if m in _MOTS_DE_LA_QUESTION:
            continue
        racines.add(m[:-1] if len(m) > 3 and m[-1] in "sx" else m)
    return racines


# --------------------------------------------------------------------------- #
# L'allergie : les faits donnés au modèle par le code (lot 15, D22 ; proposition de Pierre du 19/11, tranchée par Evan le 20/11)
# --------------------------------------------------------------------------- #



# --------------------------------------------------------------------------- #
# retrouver_commande : où en est une commande déjà passée (lot 7, E-15, E-36)
# --------------------------------------------------------------------------- #

STATUTS_PERDUS = frozenset({"refusee", "echec"})  # la commande n'est jamais passée à la préparation : lue par le suivi (``lecture``) et par la porte


# --------------------------------------------------------------------------- #
# Ce que le module du métier branche sur le mécanisme commun
# --------------------------------------------------------------------------- #


class _Metier:
    """Le moteur commun ne connaît aucun vocabulaire de métier (règle « le vocabulaire du métier vit hors du moteur commun »). Il ne garde que le mécanisme
    générique : « un fait bloquant connu de l'appel », que le module du métier branche ici à son import (la restauration y branche l'allergie) :

    - ``prealable(source, p, regles)`` : un préalable avant l'enregistrement (``Resultat`` INCOMPLETE) ou ``None`` ;
    - ``faits_a_donner(ctx, source, p, regles, retour)`` : les faits connus de l'appel que le code donne au modèle dans le retour de la fiche ;
    - ``noter_les_faits_donnes(p)`` : les faits que ``faits_a_donner`` a rendus sont notés « donnés », une fois que la parole a choisi un mode où le modèle les reçoit ;
    - ``voir_un_article(source, p, regles, article, a_eviter)`` : ``lire`` d'un article (composition, signalements)."""

    prealable: Any = None
    faits_a_donner: Any = None
    noter_les_faits_donnes: Any = None
    voir_un_article: Any = None


METIER = _Metier()


async def prealable_du_metier(source: Source, p: dict[str, Any], regles: Reglages) -> Resultat | None:
    return await METIER.prealable(source, p, regles) if METIER.prealable else None


async def faits_du_metier_a_donner(ctx: Any, source: Source, p: dict[str, Any], regles: Reglages, retour: dict[str, Any]) -> Any:
    """Les faits que le métier donne au modèle : rend l'élément de ``Du`` qu'ils posent (``None`` : aucun). La porte l'assemble dans le constat du retour."""
    return await METIER.faits_a_donner(ctx, source, p, regles, retour) if METIER.faits_a_donner else None


def noter_les_faits_donnes(p: dict[str, Any]) -> None:
    if METIER.noter_les_faits_donnes:
        METIER.noter_les_faits_donnes(p)

