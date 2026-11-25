"""[.mark] Lot 7b-C3 : les textes de secours de la carte et des allergènes (régime, signalement d'allergène, lecture d'un article).

Un texte de secours est la phrase qu'un retour de lecture portait déjà dans ``suggestion`` : fonction pure qui ne lit que les faits du retour (``resultat.suggestion == texte(faits)`` est ce que
prouve le test de chaque retour). Un texte qui lit une valeur absente des faits la fait ajouter au retour. Les morceaux de phrase communs (« D'après la fiche », « je ne peux pas le
garantir ») restent ceux du module d'information (``phrases_d_information``), jamais récrits ici.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.actions_communes import phrases_d_information as INFO
from api.services.mots_dits import liste_dite, liste_dite_et

Faits = Mapping[str, Any]

PLUS_DE_NOMS = 5  # le même nombre que ``services.commande.moteur.socle._PLUS_DE_NOMS`` : au plus cinq noms dits, puis « entre autres »


# --------------------------------------------------------------------------- #
# Un régime (végétarien, halal…) : pour un article, ou pour toute la carte
# --------------------------------------------------------------------------- #


def regime_d_un_article(faits: Faits) -> str:
    """``etiquete`` : l'étiquette de l'article le dit ; sinon c'est la case du restaurant (``restaurant``) qui le dit de la carte."""
    if faits.get("etiquete"):
        return f"{INFO.SOURCE_FICHE}, {faits['article']} est {faits['regime']}."
    return f"{INFO.SOURCE_FICHE_DU_RESTAURANT}, la carte est {faits['regime']}."


def regime_du_catalogue(faits: Faits) -> str:
    """Les articles étiquetés (``articles``, cinq dits au plus) ; sans article, la case du restaurant."""
    articles = faits.get("articles")
    if not articles:
        return f"{INFO.SOURCE_FICHE_DU_RESTAURANT}, la carte est {faits['regime']}."
    dits = articles[:PLUS_DE_NOMS]
    entre_autres = ", entre autres," if len(articles) > len(dits) else ""
    verbe = "est" if len(articles) == 1 else "sont"
    return f"{INFO.SOURCE_FICHE}, {liste_dite_et(dits)}{entre_autres} {verbe} {faits['regime']}. {INFO.POUR_LES_AUTRES_NON_GARANTI}"


# --------------------------------------------------------------------------- #
# Un allergène (signalement) : la réponse sur un mot, ou sur plusieurs
# --------------------------------------------------------------------------- #


def _nom_dit(faits: Faits) -> str:
    return f"{faits['article']} {faits['option']}" if faits.get("option") else faits["article"]


def signalement_dit(faits: Faits) -> str:
    """Selon ``faits.signalement`` : ``plusieurs`` (une réponse par allergène, ``par_signalement``), ``liste``, ``present``, ``absent_de_la_fiche``, ``selon_option``, ``inconnu``."""
    sorte = faits["signalement"]
    if sorte == "plusieurs":
        phrase = " ".join(t for t in (signalement_dit(f) for f in faits["par_signalement"]) if t)
        return f"{phrase} Pour le reste de ce que vous citez, {INFO.NON_GARANTI}".strip() if faits.get("mot_inconnu") else phrase
    if sorte == "inconnu":
        if faits.get("hors_liste"):
            return "Pour cette chose, " + INFO.NON_GARANTI
        if faits.get("sans_fiche"):
            return INFO.NON_CONFIRMABLE
        if faits.get("option"):
            return f"Pour {_nom_dit(faits)}, " + INFO.NON_GARANTI
        return "Ça dépend du choix, et " + INFO.NON_GARANTI
    if sorte == "liste":
        presents = faits["presents"]
        phrase = f"{INFO.SOURCE_FICHE}, {_nom_dit(faits)} contient {liste_dite_et(presents)}." if presents else f"{INFO.SOURCE_FICHE}, {_nom_dit(faits)} n'en déclare aucun."
        if faits.get("options_a_confirmer"):
            phrase += " Selon le choix, " + INFO.NON_GARANTI if not faits.get("option") else f" Pour {faits['option']}, " + INFO.NON_GARANTI
        return phrase
    if sorte == "present":
        return f"Oui, {_nom_dit(faits)} contient {faits['libelle']}."
    if sorte == "absent_de_la_fiche":
        return f"{INFO.SOURCE_FICHE}, {_nom_dit(faits)} ne contient pas {faits['libelle']}."
    suite = " Pour les autres, " + INFO.NON_GARANTI if faits.get("autres_a_confirmer") else " Pour les autres, d'après la fiche, non."  # ``selon_option``
    return f"Ça dépend : avec {liste_dite(faits['options_qui_contiennent'])}, oui." + suite
