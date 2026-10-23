"""[.mark] Lot 7 de correctifs-apres-banc-commun (D-8) : un champ de l'étape peut porter une condition sur la fiche.

La liste des champs d'une étape (``champs_etape``) dit ce que l'étape recueille. Un champ peut n'être attendu que
si la fiche le permet (« mail, si le contrat est souscrit ») : ``conditions_de_champs`` des données de l'étape,
des lignes ``{champ, si, vaut}`` qui ont la forme des conditions des phrases de fin figées (un champ de la fiche,
rempli ou qui vaut une valeur), évaluées par la MÊME fonction (``groupe.passations.condition_tenue``).

Un champ sans condition est toujours attendu (comportement d'avant, octet pour octet). Un champ dont la condition
n'est pas tenue n'est pas attendu : ni dans « Encore attendu », ni dans la garde de l'étape, ni dans l'empreinte
d'une demande, ni dans l'attente du mode automatique ; il ne bloque donc aucune action. Plusieurs lignes sur un
même champ s'additionnent (toutes doivent être tenues). Aucun mot de métier : les noms viennent de l'agent.
⛔ Ne lève jamais : dans le doute, tous les champs déclarés sont attendus (comme avant).
"""

from __future__ import annotations

from typing import Any, Mapping

from loguru import logger


def champs_actifs(noeud: Any, fiche: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Les champs de ``noeud.champs_etape`` attendus pour cette fiche, dans l'ordre de l'étape."""
    champs = tuple(getattr(noeud, "champs_etape", None) or ())
    try:
        conditions = tuple(getattr(noeud, "conditions_de_champs", None) or ())
        if not champs or not conditions:
            return champs
        from api.services.groupe.passations import condition_tenue

        par_champ: dict[str, list[Mapping[str, Any]]] = {}
        for ligne in conditions:
            if isinstance(ligne, Mapping) and ligne.get("champ"):
                par_champ.setdefault(str(ligne["champ"]), []).append(ligne)
        return tuple(
            nom
            for nom in champs
            if all(
                condition_tenue(ligne.get("si"), ligne.get("vaut"), fiche)
                for ligne in par_champ.get(nom, ())
            )
        )
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, tout est attendu
        logger.warning(f"[fiche] conditions des champs de l'étape illisibles : {erreur!r}")
        return champs
