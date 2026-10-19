"""[.mark] Chantier fiabilite-orchestration (F18, F23) : la phrase en vigueur pour un motif.

Trois niveaux (F18) : l'**étape**, sinon l'**agent**, sinon le **principal** (ses règles de portée
« groupe »), sinon le **défaut** du catalogue. Un spécialisé reprend donc la phrase du principal
tant qu'il n'a pas la sienne. La résolution dit le niveau d'où vient la phrase (la carte l'affiche).

⛔ Ne lève jamais : une règle illisible est ignorée (journalisée), le niveau suivant s'applique.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger

from api.schemas.phrases_du_code import (
    PORTEE_AGENT,
    PORTEE_ETAPE,
    PORTEE_GROUPE,
    ReglePhrase,
)
from api.services.phrases.catalogue import MOTIFS, Motif

CLE_REGLES = "phrases_regles"

NIVEAU_ETAPE = "etape"
NIVEAU_AGENT = "agent"
NIVEAU_PRINCIPAL = "principal"
NIVEAU_DEFAUT = "defaut"


@dataclass(frozen=True)
class PhraseResolue:
    motif: Motif
    variantes: tuple[str, ...]
    delai_s: float | None
    active: bool
    niveau: str

    @property
    def dite(self) -> bool:
        return self.active and bool(self.variantes)


def regles_de(reglages: Mapping[str, Any] | None) -> list[ReglePhrase]:
    """Les règles lisibles de ces réglages d'agent, dans leur ordre. ⛔ Ne lève jamais."""
    brutes = (reglages or {}).get(CLE_REGLES) if isinstance(reglages, Mapping) else None
    regles: list[ReglePhrase] = []
    for brute in brutes or []:
        try:
            regles.append(
                brute if isinstance(brute, ReglePhrase) else ReglePhrase.model_validate(brute)
            )
        except Exception as erreur:  # noqa: BLE001 -- une règle illisible ne coûte pas l'appel
            logger.warning(f"[phrases] règle illisible ignorée : {erreur!r}")
    return regles


def _depuis_la_regle(regle: ReglePhrase, motif: Motif, niveau: str) -> PhraseResolue:
    return PhraseResolue(
        motif=motif,
        variantes=tuple(regle.variantes),
        delai_s=(
            (regle.delai_s if regle.delai_s is not None else motif.delai_defaut_s)
            if motif.a_un_delai
            else None
        ),
        active=regle.active,
        niveau=niveau,
    )


def defaut_du_motif(motif: Motif) -> PhraseResolue:
    return PhraseResolue(
        motif=motif,
        variantes=motif.variantes_defaut,
        delai_s=motif.delai_defaut_s,
        active=motif.actif_par_defaut,
        niveau=NIVEAU_DEFAUT,
    )


def resoudre(
    motif_id: str,
    *,
    reglages_agent: Mapping[str, Any] | None = None,
    reglages_principal: Mapping[str, Any] | None = None,
    etape: str | None = None,
) -> PhraseResolue | None:
    """La phrase en vigueur pour ``motif_id`` chez cet agent, à cette étape. ``None`` : motif
    inconnu. ``reglages_principal`` peut être les réglages de l'agent lui-même (il est le
    principal, ou un agent seul) : ses règles « groupe » valent alors pour lui."""
    motif = MOTIFS.get(motif_id)
    if motif is None:
        return None
    try:
        propres = [r for r in regles_de(reglages_agent) if r.motif == motif_id]
        if etape:
            for regle in propres:
                if regle.portee == PORTEE_ETAPE and regle.etape == etape:
                    return _depuis_la_regle(regle, motif, NIVEAU_ETAPE)
        for regle in propres:
            if regle.portee == PORTEE_AGENT:
                return _depuis_la_regle(regle, motif, NIVEAU_AGENT)
        # Une règle « groupe » posée sur un agent qui n'est pas le principal vaut pour lui seul.
        for regle in propres:
            if regle.portee == PORTEE_GROUPE:
                return _depuis_la_regle(regle, motif, NIVEAU_AGENT)
        if reglages_principal is not None and reglages_principal is not reglages_agent:
            for regle in regles_de(reglages_principal):
                if regle.motif == motif_id and regle.portee == PORTEE_GROUPE:
                    return _depuis_la_regle(regle, motif, NIVEAU_PRINCIPAL)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] résolution de {motif_id} illisible : {erreur!r}")
    return defaut_du_motif(motif)
