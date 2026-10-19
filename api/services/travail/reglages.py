"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D13) : les réglages du cerveau de fond d'un agent.

Cinq clés JSON de ``workflow_configurations`` (aucune migration) : ``travail_actif`` (faux),
``travail_llm`` (vide = le cerveau de conversation de l'agent), ``travail_consigne`` (vide = aucune
consigne ajoutée par le code, à rédiger avec Evan), ``travail_outils`` (liste d'UUID),
``travail_delai_max_s`` (60). Lecture seule, jamais d'exception : un réglage illisible = éteint.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

CLE_ACTIF = "travail_actif"
CLE_LLM = "travail_llm"
CLE_CONSIGNE = "travail_consigne"
CLE_OUTILS = "travail_outils"
CLE_DELAI = "travail_delai_max_s"
CLES_DU_TRAVAIL = (CLE_ACTIF, CLE_LLM, CLE_CONSIGNE, CLE_OUTILS, CLE_DELAI)

# Le nom technique de l'outil que le cerveau de conversation appelle (générique : aucun métier).
NOM_OUTIL = "confier_le_travail"
# Lot 1 de fiabilite-orchestration (F2) : l'appelant peut toujours annuler pendant l'attente.
NOM_OUTIL_ANNULER = "annuler_le_travail"
# Le nom sous lequel les jetons du fond entrent dans le coût de l'appel (``processor|||model``).
NOM_DU_COUT = "travail"
USAGE_TRAVAIL = "travail"
# La clé de la fiche de l'appel où chaque travail est tracé.
CLE_TRAVAUX = "travaux"
DELAI_PAR_DEFAUT_S = 60
# La consigne du cerveau de fond : VIDE tant qu'elle n'est pas rédigée avec Evan (séance prompts
# d'après le chantier). Le code n'écrit aucune phrase de métier ni aucune consigne à sa place.
CONSIGNE_PAR_DEFAUT = ""


@dataclass(frozen=True)
class ReglagesTravail:
    """Ce que l'écran a réglé pour le travail en arrière-plan d'UN agent."""

    actif: bool = False
    llm: dict | None = None
    consigne: str = ""
    outils: tuple[str, ...] = ()
    delai_max_s: int = DELAI_PAR_DEFAUT_S

    @classmethod
    def depuis(cls, reglages: dict | None) -> "ReglagesTravail":
        """Les réglages d'un agent (``workflow_configurations`` de sa définition). Éteint si la
        case est éteinte ou si un réglage est illisible (journalisé, jamais une exception)."""
        brut = {cle: (reglages or {}).get(cle) for cle in CLES_DU_TRAVAIL}
        if brut[CLE_ACTIF] is not True:
            return cls()
        try:
            from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

            valides = WorkflowConfigurationDefaults.model_validate(
                {cle: valeur for cle, valeur in brut.items() if valeur is not None}
            )
        except Exception as erreur:  # noqa: BLE001 -- l'appel part sans cerveau de fond
            logger.warning(
                f"[travail] réglages du cerveau de fond illisibles, éteint : {erreur!r}"
            )
            return cls()
        consigne = (valides.travail_consigne or "").strip() or CONSIGNE_PAR_DEFAUT
        return cls(
            actif=bool(valides.travail_actif),
            llm=dict(valides.travail_llm) if valides.travail_llm else None,
            consigne=consigne,
            outils=tuple(valides.travail_outils),
            delai_max_s=int(valides.travail_delai_max_s),
        )
