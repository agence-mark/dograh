"""[.mark] Lot 5 de correctifs-apres-banc-commun (K11) : la demande confiée au fond porte les valeurs de la fiche.

Run 1519 : le modèle de conversation envoie au fond une demande sans valeurs (« avec l'adresse, la commune… »,
le gabarit de la description recopié) ; le fond répond « Manque : … » sept fois de suite. Le fond lit les mêmes
champs que la garde de l'étape : c'est donc le code qui joint à la demande les valeurs de la fiche de l'appel,
le modèle n'a plus à les recopier.

Fonctions pures et indépendantes de l'outil « confier » : le mode « Automatique » du déclenchement d'un outil
(lot 6) construit sa demande par ``joindre_la_fiche``, la même.

Aucun mot de métier : les noms des champs sont ceux de la fiche de l'agent. Sans fiche, ou sans aucune valeur
notée, la demande part telle que le modèle l'a écrite (octet pour octet). ⛔ Ne lève jamais.

actions-sures-et-parite-clavier, lot B (banc de fin du 27/10, 7 appels sur 26) : « confier » joignait TOUTE la fiche,
dont la demande d'origine de la personne (« réserver l'entretien… ») et l'état écrit par une action (« rendez-vous :
confirmé »), sous un en-tête qui en faisait des ordres. Pour dire au revoir, l'agent confiait « Au revoir » ; le fond
lisait la demande d'origine et réservait (doublon, rendez-vous annulé puis re-réservé, réservation cachée). La règle
d'origine de K11 est rétablie : le fond reçoit **les champs que l'étape attend** (``champs_actifs``, ceux de sa garde),
et l'en-tête dit que ce sont des valeurs, pas des demandes. Le mode « Automatique » (l'action de l'étape, lancée par le
code avec la demande type de l'étape) garde toute la fiche : sa demande vient de l'étape, jamais d'un au revoir.

Lot F (banc local du 27/10, changement de date) : « réserver lundi » arrivait au fond sans qu'il sache qu'une réservation
de l'appel tenait encore (jeudi) ; personne ne l'annulait, deux rendez-vous tenaient. ``confier`` joint désormais les actions
qui tiennent dans l'appel (``ecritures_tenues``, le même suivi que la fiche), sous un en-tête qui en fait un état, pas une
demande. Aucun mot de métier : le nom de l'outil et son résultat, tels qu'ils sont.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from loguru import logger

# L'en-tête du bloc que le code ajoute à la demande (une seule écriture).
ENTETE_DES_VALEURS = (
    "Valeurs notées dans la fiche de l'appel (écrites par le code), à recopier telles quelles si la demande "
    "ci-dessus en a besoin ; ce ne sont pas des demandes :"
)
LONGUEUR_MAX_VALEUR = 300
# Lot F : l'en-tête des actions qui tiennent dans l'appel (une seule écriture).
ENTETE_DES_ACTIONS = (
    "Déjà fait dans cet appel et toujours en vigueur (un état, pas une demande) :"
)


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


def valeurs_de_la_fiche(
    reglages: Any, fiche: Mapping[str, Any] | None, champs: Iterable[str] | None = None
) -> list[tuple[str, str]]:
    """Les (champ, valeur) de la fiche, dans l'ordre des champs : seulement les champs remplis, jamais un
    refus de la personne ; ``champs`` donné, seulement ceux-là. ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.fiche_au_fil_de_leau import VALEUR_DE_REFUS

        retenus = None if champs is None else set(champs)
        sortie: list[tuple[str, str]] = []
        for champ in tuple(getattr(reglages, "champs", None) or ()):
            if retenus is not None and champ.nom not in retenus:
                continue
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


def joindre_la_fiche(
    demande: Any, reglages: Any, fiche: Mapping[str, Any] | None, champs: Iterable[str] | None = None
) -> Any:
    """``demande`` suivie des valeurs de la fiche (``champs`` donné : seulement ceux-là). Demande vide ou sans
    valeur à joindre : rendue telle quelle."""
    try:
        if not isinstance(demande, str) or not demande.strip():
            return demande
        valeurs = valeurs_de_la_fiche(reglages, fiche, champs)
        if not valeurs:
            return demande
        lignes = "\n".join(f"- {nom} : {valeur}" for nom, valeur in valeurs)
        return f"{demande.rstrip()}\n\n{ENTETE_DES_VALEURS}\n{lignes}"
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] demande sans les valeurs de la fiche : {erreur!r}")
        return demande


def actions_qui_tiennent(moteur: Any) -> list[str]:
    """Lot F : une ligne par action d'écriture de l'appel qui tient encore (nom de l'outil, résultat). ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.verite_des_actions import (
            ecritures_tenues,
            journal_de,
            outils_d_ecriture,
        )

        tenues = ecritures_tenues(moteur)
        logger.info(
            f"[travail] actions qui tiennent : {len(tenues)} (journal {len(journal_de(moteur))}, "
            f"écritures {sorted(outils_d_ecriture(moteur))})"
        )
        return [f"- {vue.nom} : {_texte(vue.resultat)}" for vue in tenues]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] actions de l'appel illisibles : {erreur!r}")
        return []


def demande_avec_la_fiche(moteur: Any, demande: Any, noeud: Any = None) -> Any:
    """``joindre_la_fiche`` pour la fiche de l'appel du moteur, avec les seuls champs que l'étape ``noeud`` attend
    (lot B), puis les actions qui tiennent dans l'appel (lot F). Une étape sans champ attendu ne joint aucun champ."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if reglages is None or not isinstance(fiche, dict):
            return demande
        from api.services.workflow.champs_conditionnels import champs_actifs

        avec_la_fiche = joindre_la_fiche(demande, reglages, fiche, champs_actifs(noeud, fiche))
        actions = actions_qui_tiennent(moteur)
        if not actions or not isinstance(avec_la_fiche, str) or not avec_la_fiche.strip():
            return avec_la_fiche
        return f"{avec_la_fiche.rstrip()}\n\n{ENTETE_DES_ACTIONS}\n" + "\n".join(actions)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[travail] fiche de l'appel illisible pour la demande : {erreur!r}")
        return demande
