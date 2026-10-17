"""[.mark] Lot 2 d'orchestrateur-trois-cerveaux (B2, D5) : le filet de fin d'appel d'un collègue.

Un collègue a deux sorties : clore l'appel, ou rendre la main à l'accueil. Quand sa réplique contient
une formule de fin (« au revoir », « bonne journée »…) **et** qu'il n'a pris aucune porte, le code prend
lui-même la sortie « retour » : l'accueil reçoit l'appel sur son étape de retour et conclut depuis là,
par sa fin figée. Sans ce filet, un collègue qui dit au revoir en texte reste muet dans une étape
sans porte : l'appel pend.

⛔ Ce n'est pas un rail : le dialogue n'est jamais guidé, le code ne déclenche rien tant que le
collègue parle de la demande. Une case par agent (« End-of-call safety net »), **éteinte par défaut** ;
un agent sans la case, ou hors d'un groupe, se comporte exactement comme avant.

Les formules sont des **données** : la phrase ``formules_de_fin`` du catalogue de phrases de
l'organisation (une formule par ligne), lue dans le contexte de l'appel comme toute phrase du catalogue.
Une organisation qui n'en a pas écrit garde la liste ci-dessous, la même que celle de l'écran.

Tout est pur ou ne lève jamais : un échec ne coûte jamais l'appel.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Mapping

from loguru import logger

from api.services.groupe.passations import agent_principal_de, est_une_etape_de_retour

CLE_FILET = "filet_de_fin"
VARIABLE_FORMULES = "formules_de_fin"
# Les formules reconnues quand l'organisation n'a pas écrit les siennes (la même liste à l'écran).
FORMULES_PAR_DEFAUT = ("au revoir", "bonne journée", "bonne soirée")
# La trace du geste, dans ``porte_reecrite`` : la valeur de ``ecrite``.
TRACE_FILET = "filet_de_fin"


def _normaliser(texte: Any) -> str:
    """Minuscules, sans accent, espaces simples : « Bonne journée ! » ~ « bonne journee »."""
    decompose = unicodedata.normalize("NFKD", str(texte or ""))
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accent.casefold().split())


def formules_de(contexte: Mapping[str, Any] | None) -> list[str]:
    """Les formules de fin reconnues : la phrase ``formules_de_fin`` du catalogue (une par ligne), sinon
    la liste par défaut. ⛔ Ne lève jamais."""
    try:
        brut = (contexte or {}).get(VARIABLE_FORMULES)
        if isinstance(brut, str) and brut.strip():
            lignes = [ligne.strip() for ligne in brut.splitlines() if ligne.strip()]
            if lignes:
                return lignes
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[filet] formules de fin illisibles, celles par défaut : {erreur!r}")
    return list(FORMULES_PAR_DEFAUT)


def contient_une_formule(texte: str | None, formules: Iterable[str]) -> bool:
    """La réplique contient-elle une des formules (accents et casse ignorés) ? Une formule de
    plusieurs mots se cherche comme un tout, sur des mots entiers. ⛔ Ne lève jamais."""
    try:
        cherche = f" {_normaliser(texte)} "
        # La ponctuation sépare les mots : « Bonne journée, au revoir. » doit être trouvée.
        cherche = "".join(c if c.isalnum() else " " for c in cherche)
        cherche = " " + " ".join(cherche.split()) + " "
        for formule in formules:
            motif = " ".join("".join(c if c.isalnum() else " " for c in _normaliser(formule)).split())
            if motif and f" {motif} " in cherche:
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


def filet_allume(reglages_agent: Mapping[str, Any] | None) -> bool:
    """La case « End-of-call safety net » de l'agent, dans un groupe, sur un collègue seulement."""
    try:
        reglages = reglages_agent or {}
        return reglages.get(CLE_FILET) is True and agent_principal_de(reglages) is not None
    except Exception:  # noqa: BLE001
        return False


def porte_de_retour(noeud: Any, graphe: Any) -> Any:
    """L'arête de l'étape qui mène à une étape « retour au principal » (la sortie « retour »), ou
    ``None`` : un collègue qui n'est pas sur une étape qui rend la main n'a pas de filet. ⛔ Ne lève jamais."""
    try:
        if noeud is None or getattr(noeud, "is_end", False):
            return None
        return next(
            (
                e
                for e in noeud.out_edges
                if est_une_etape_de_retour(graphe.nodes[e.target]) and not graphe.nodes[e.target].is_end
            ),
            None,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[filet] sortie retour illisible : {erreur!r}")
        return None


def brancher_le_filet_de_fin(engine: Any, assistant_aggregator: Any) -> None:
    """Branche le filet sur l'agrégateur de l'assistant : au début d'une réplique, l'étape où l'on
    est ; à sa fin, ``engine.filet_de_fin``. Téléphone et clavier. ⛔ Ne lève jamais."""
    try:
        depart: dict[str, Any] = {}

        @assistant_aggregator.event_handler("on_assistant_turn_started")
        async def _debut(_aggregator):
            try:
                depart["etat"] = engine.etat_pour_le_filet()
            except Exception:  # noqa: BLE001
                depart["etat"] = None

        @assistant_aggregator.event_handler("on_assistant_turn_stopped")
        async def _fin(_aggregator, message):
            try:
                await engine.filet_de_fin(getattr(message, "content", None) or "", depart.pop("etat", None))
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[filet] fin d'appel non traitée : {erreur!r}")

    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[filet] non branché : {erreur!r}")
