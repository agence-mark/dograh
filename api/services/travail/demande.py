"""[.mark] Lot 5 de correctifs-apres-banc-commun (K11) : la demande confiée au fond porte les valeurs de la fiche.

Run 1519 : le modèle de conversation envoie au fond une demande sans valeurs (« avec l'adresse, la commune… »,
le gabarit de la description recopié) ; le fond répond « Manque : … » sept fois de suite. Le fond lit les mêmes
champs que la garde de l'étape : c'est donc le code qui joint à la demande les valeurs de la fiche de l'appel,
le modèle n'a plus à les recopier.

Fonctions pures et indépendantes de l'outil « confier » : le mode « Automatique » du déclenchement d'un outil
(lot 6) construit sa demande par ``joindre_la_fiche``, la même.

Aucun mot de métier : les noms des champs sont ceux de la fiche de l'agent. Sans fiche, ou sans aucune valeur
notée, la demande part telle que le modèle l'a écrite (octet pour octet). ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any, Mapping

from loguru import logger

# L'en-tête du bloc que le code ajoute à la demande (une seule écriture).
ENTETE_DES_VALEURS = "Valeurs de la fiche de l'appel (écrites par le code, à utiliser telles quelles) :"
LONGUEUR_MAX_VALEUR = 300


def _vide(valeur: Any) -> bool:
    if valeur is None:
        return True
    if isinstance(valeur, str):
        return not valeur.strip()
    if isinstance(valeur, (list, tuple, set, dict)):
        return len(valeur) == 0
    return False


def _texte(valeur: Any) -> str:
    if isinstance(valeur, (list, tuple, set)):
        texte = ", ".join(str(v) for v in valeur)
    else:
        texte = str(valeur)
    texte = " ".join(texte.split())
    if len(texte) > LONGUEUR_MAX_VALEUR:
        texte = texte[: LONGUEUR_MAX_VALEUR - 1].rstrip() + "…"
    return texte


def valeurs_de_la_fiche(reglages: Any, fiche: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """Les (champ, valeur) de la fiche, dans l'ordre des champs : seulement les champs remplis, jamais un
    refus de la personne. ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.fiche_au_fil_de_leau import VALEUR_DE_REFUS

        sortie: list[tuple[str, str]] = []
        for champ in tuple(getattr(reglages, "champs", None) or ()):
            valeur = (fiche or {}).get(champ.nom)
            if _vide(valeur):
                continue
            if isinstance(valeur, str) and valeur.strip().casefold() == VALEUR_DE_REFUS:
                continue
            sortie.append((champ.nom, _texte(valeur)))
        return sortie
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] valeurs de la fiche illisibles : {erreur!r}")
        return []


def joindre_la_fiche(demande: Any, reglages: Any, fiche: Mapping[str, Any] | None) -> Any:
    """``demande`` suivie des valeurs de la fiche. Demande vide ou sans valeur à joindre : rendue telle quelle."""
    try:
        if not isinstance(demande, str) or not demande.strip():
            return demande
        valeurs = valeurs_de_la_fiche(reglages, fiche)
        if not valeurs:
            return demande
        lignes = "\n".join(f"- {nom} : {valeur}" for nom, valeur in valeurs)
        return f"{demande.rstrip()}\n\n{ENTETE_DES_VALEURS}\n{lignes}"
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] demande sans les valeurs de la fiche : {erreur!r}")
        return demande


def demande_avec_la_fiche(moteur: Any, demande: Any) -> Any:
    """``joindre_la_fiche`` pour la fiche de l'appel du moteur."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if reglages is None or not isinstance(fiche, dict):
            return demande
        return joindre_la_fiche(demande, reglages, fiche)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] fiche de l'appel illisible pour la demande : {erreur!r}")
        return demande
