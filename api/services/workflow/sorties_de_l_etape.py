"""[.mark] fiabilite-de-la-conversation, lot C (C2, point 13) : sous chaque sortie, la première chose qui manque.

Le bloc « Tu passes à… Phrase d'arrivée » est écrit une fois dans le prompt de l'étape (``porte_parlee``) ; il ne dit pas
ce que l'étape d'arrivée attend, et le modèle redemande ce qui est déjà dit (ou pose les questions de l'étape suivante
dans celle-ci). Ici, à **chaque requête** (dans le bloc d'état, hors historique : le prompt système ne bouge pas, le
cache est servi), le code calcule pour chaque sortie de l'étape en cours vers une étape **du même agent** la première
chose qui manque là-bas (liste des champs de l'étape d'arrivée dans son ordre, conditions de champs, fiche, traces des
modules du tour) et l'écrit :

- ``Sortie <nom> : là-bas, la première chose qui manque est : <champ>, sauf si elle vient de te le donner.`` ;
- ``Sortie <nom> : là-bas, rien ne manque, pas de question.``

Le code choisit la question, le modèle la formule (le standard du marché : Rasa, Dialogflow). Une étape d'arrivée sans
liste de champs ne reçoit rien. Portée par la case existante « Montrer au modèle ce qui est connu et ce qui est attendu »
(``reglages.etiquettes``) : aucune case nouvelle. Pas de saut d'étape automatique (F-5). Seules les sorties vers une
étape du même agent comptent (revue D1) : l'accueil se tait quand il passe la main à un collègue.

Aucun mot de métier. ⛔ Ne lève jamais : dans le doute, rien n'est écrit.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from loguru import logger

# Une consigne au modèle (jamais dite à l'appelant). La formule du plan (revue D6).
LIGNE_PREMIERE_CHOSE = (
    "Sortie {sortie} : là-bas, la première chose qui manque est : {champ}, sauf si elle vient de te le donner."
)
LIGNE_RIEN_NE_MANQUE = "Sortie {sortie} : là-bas, rien ne manque, pas de question."


def premiere_chose_qui_manque(reglages: Any, fiche: Mapping[str, Any], noeud: Any) -> str | None | bool:
    """Ce que l'étape ``noeud`` attend en premier : le nom du champ, ``None`` si la liste de l'étape est vide (rien à
    dire), ``False`` si la liste est là et que rien ne manque. ⛔ Ne lève jamais (``None`` dans le doute)."""
    try:
        from api.services.fiche.traces import valeurs_des_traces
        from api.services.groupe.notes import champs_attendus
        from api.services.workflow.champs_conditionnels import champs_actifs

        if not tuple(getattr(noeud, "champs_etape", None) or ()):
            return None
        manque = champs_attendus(reglages, fiche, champs_actifs(noeud, fiche), valeurs_des_traces(reglages, fiche))
        return manque[0] if manque else False
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] première chose qui manque illisible : {erreur!r}")
        return None


def lignes_des_sorties(
    reglages: Any, fiche: Mapping[str, Any], sorties: Iterable[tuple[str, Any]]
) -> list[str]:
    """Une ligne par sortie dont l'étape d'arrivée déclare ses champs. ``sorties`` : (nom de la sortie, étape d'arrivée).
    Vide sans étiquettes (la case éteinte). ⛔ Ne lève jamais."""
    try:
        if not getattr(reglages, "etiquettes", False):
            return []
        from api.services.groupe.notes import nom_lisible

        lignes: list[str] = []
        for nom, arrivee in sorties:
            manque = premiere_chose_qui_manque(reglages, fiche, arrivee)
            if manque is None:
                continue
            if manque is False:
                lignes.append(LIGNE_RIEN_NE_MANQUE.format(sortie=nom))
            else:
                lignes.append(LIGNE_PREMIERE_CHOSE.format(sortie=nom, champ=nom_lisible(manque)))
        return lignes
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] sorties de l'étape illisibles : {erreur!r}")
        return []


def sorties_de(noeud: Any, graphe: Any) -> list[tuple[str, Any]]:
    """Les sorties de l'étape ``noeud`` vers une étape du graphe de son agent : (nom de la porte, étape d'arrivée), dans
    l'ordre des portes. ⛔ Ne lève jamais."""
    try:
        arrivees = getattr(graphe, "nodes", None) or {}
        return [
            (arete.get_function_name(), arrivees[arete.target])
            for arete in (getattr(noeud, "out_edges", None) or ())
            if arete.target in arrivees
        ]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] sorties de l'étape non lues : {erreur!r}")
        return []
