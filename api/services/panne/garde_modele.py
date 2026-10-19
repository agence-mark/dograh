"""[.mark] Chantier fiabilite-orchestration, lot 4 (F20, F26, C5) : la garde du modèle et le repli.

Au 1463, rien n'a réagi pendant 12,6 s : le délai de garde du modèle n'existait qu'avec le mode panne,
éteint sur tous nos agents. Désormais :

- le **délai de garde** (``delai_garde_modele_s``, 4 s, réglé dans Models sous le cerveau) s'arme
  **pour tous**, sur le service de la conversation, de chaque collègue et du cerveau de fond, mode
  panne allumé ou non (un agent qui avait réglé ``panne.delai_modele_s`` garde sa valeur tant qu'il
  n'a pas la nouvelle) ;
- au **premier** dépassement : la phrase du motif « le modèle tarde » (thème Phrases, « Un instant,
  s'il vous plaît. » par défaut) puis une nouvelle tentative, **chez le cerveau de repli** s'il est
  réglé, sinon chez le même ; au **deuxième** d'affilée : la panne comme avant si le mode panne est
  allumé, sinon une nouvelle tentative, jusqu'à ``TENTATIVES_SANS_PANNE`` ;
- le **cerveau de repli** (``cerveau_de_repli``, et ``travail_llm_repli`` pour le fond) est un
  **outil de dépannage, jamais une obligation** (F26) : aucun par défaut, jamais dans l'onboarding.
  La tentative de repli **emprunte le service de l'agent** (ses outils, sa fiche, sa trace, ses
  réglages) avec la connexion et le modèle du repli, pour cette requête seulement
  (``DelaiModeleMixin``) : il faut donc un fournisseur au protocole compatible OpenAI.

⛔ Ne lève jamais : une garde ne coûte jamais l'appel. Aucun mot de métier.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from api.services.panne.delai_modele import TYPE_EVENEMENT, DelaiModeleDepasse

CLE_DELAI = "delai_garde_modele_s"
CLE_REPLI = "cerveau_de_repli"
CLE_REPLI_DU_FOND = "travail_llm_repli"
DELAI_PAR_DEFAUT_S = 4.0
# Sans mode panne, la garde relance au plus ce nombre de fois d'affilée, puis laisse la main à
# l'appelant (jamais d'appel coupé par la garde seule).
TENTATIVES_SANS_PANNE = 3


def delai_de_garde(run_configs: dict | None) -> float:
    """Le délai de garde de l'agent : le réglage de Models, sinon l'ancien réglage du mode panne,
    sinon 4 s. ⛔ Ne lève jamais."""
    try:
        reglages = run_configs or {}
        valeur = reglages.get(CLE_DELAI)
        if isinstance(valeur, (int, float)) and not isinstance(valeur, bool) and valeur > 0:
            return float(valeur)
        panne = reglages.get("panne")
        if isinstance(panne, dict):
            ancien = panne.get("delai_modele_s")
            if isinstance(ancien, (int, float)) and not isinstance(ancien, bool) and ancien > 0:
                return float(ancien)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[garde] délai de garde illisible : {erreur!r}")
    return DELAI_PAR_DEFAUT_S


@dataclass(frozen=True)
class Repli:
    """La connexion et le modèle d'un cerveau de repli (jamais la clé en clair dans un journal)."""

    client: Any
    modele: str
    fournisseur: str


async def repli_de(
    run_configs: dict | None,
    user_config: Any,
    organization_id: int | None,
    cle: str = CLE_REPLI,
    *,
    correlation_id: str | None = None,
) -> Repli | None:
    """Le cerveau de repli réglé sous ``cle``, construit ; ``None`` sans réglage ou s'il ne se
    construit pas (journalisé : l'agent garde la garde sans repli). ⛔ Ne lève jamais."""
    try:
        if not (run_configs or {}).get(cle) or user_config is None:
            return None
        from api.services.pipecat.greffier import (
            configuration_d_un_cerveau_annexe,
            resoudre_le_bloc_annexe,
        )
        from api.services.pipecat.service_factory import create_llm_service

        bloc = await resoudre_le_bloc_annexe(run_configs, organization_id, cle, "fallback brain")
        if not bloc:
            return None
        configuration = configuration_d_un_cerveau_annexe(
            user_config, bloc, objet="fallback brain", nom_du_reglage="Fallback model"
        )
        service = create_llm_service(configuration, correlation_id=correlation_id)
        client = getattr(service, "_client", None)
        modele = getattr(getattr(service, "_settings", None), "model", None)
        if client is None or not modele:
            logger.warning("[garde] cerveau de repli sans connexion compatible : ignoré")
            return None
        return Repli(client=client, modele=str(modele), fournisseur=str(configuration.llm.provider))
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[garde] cerveau de repli non construit : {type(erreur).__name__}")
        return None


class GardeDuModele:
    """La réponse du code à UN service de modèle trop lent (un par service : conversation, collègue
    ou fond). ``relancer()`` relance la génération de ce service ; ``parle`` : un service qui parle
    à l'appelant (le fond ne parle jamais)."""

    def __init__(
        self,
        moteur: Any,
        llm: Any,
        relancer: Callable[[], Awaitable[None]],
        *,
        parle: bool,
        agent: Any = None,
        repli: Repli | None = None,
    ):
        self.moteur = moteur
        self.llm = llm
        self.relancer = relancer
        self.parle = parle
        self.agent = agent
        self.repli = repli
        self.compteur = 0
        self.total = 0

    def brancher(self, delai_s: float) -> bool:
        """Arme le délai sur le service et branche ses deux événements. ``False`` : un service
        sans la garde (autre classe), rien ne change. ⛔ Ne lève jamais."""
        try:
            if not hasattr(self.llm, "mark_delai_modele_s"):
                return False
            self.llm.mark_delai_modele_s = delai_s
            self.llm.mark_repli = self.repli
            self.llm.event_handler("on_delai_modele_depasse")(self._depasse)
            self.llm.event_handler("on_reponse_modele_commencee")(self._commencee)
            return True
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[garde] délai de garde non armé : {erreur!r}")
            return False

    async def _commencee(self, _service) -> None:
        self.compteur = 0

    async def _journaliser(self, depassement: DelaiModeleDepasse) -> None:
        try:
            fiche = getattr(self.moteur, "_gathered_context", None)
            if isinstance(fiche, dict):
                fiche["depassements_modele"] = fiche.get("depassements_modele", 0) + 1
            from api.services.analyse_run.incidents_appel import ATTRIBUT_JOURNAL

            journal = getattr(self.moteur, ATTRIBUT_JOURNAL, None)
            if journal is not None:
                await journal.append(
                    {
                        "type": TYPE_EVENEMENT,
                        "payload": {
                            "attempt": self.compteur,
                            "moment": depassement.moment,
                            "delay_secs": depassement.delai_s,
                            "fallback": self.repli.fournisseur if self.repli else None,
                            "speaks": self.parle,
                        },
                    }
                )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[garde] dépassement non journalisé : {erreur!r}")

    async def _depasse(self, _service, depassement: DelaiModeleDepasse) -> None:
        self.compteur += 1
        self.total += 1
        await self._journaliser(depassement)
        try:
            if self.compteur == 1:
                if self.parle:
                    from api.services.phrases.catalogue import MODELE_TARDE

                    diseur = getattr(self.moteur, "phrases", None)
                    if diseur is not None:
                        await diseur.dire(MODELE_TARDE, self.agent)
                if self.repli is not None:
                    self.llm._mark_tentative_au_repli = True
                    logger.info(f"[garde] seconde tentative chez le repli ({self.repli.fournisseur})")
                await self.relancer()
                return
            from api.services.panne.declencheurs import gardien_de

            gardien = gardien_de(self.moteur) if self.parle else None
            if gardien is not None:
                # ⛔ Mode panne allumé : comme avant, la panne puis la fin de l'appel.
                try:
                    await gardien.declencher(
                        "modele_lent", "modele", f"{depassement.moment} > {depassement.delai_s} s"
                    )
                finally:
                    from pipecat.utils.enums import EndTaskReason

                    await self.moteur.end_call_with_reason(
                        EndTaskReason.PIPELINE_ERROR.value, abort_immediately=True
                    )
                return
            if self.compteur <= TENTATIVES_SANS_PANNE:
                await self.relancer()
            else:
                logger.warning("[garde] modèle toujours lent : la main reste à l'appelant")
        except Exception as erreur:  # noqa: BLE001 -- une garde ne coûte jamais l'appel
            logger.error(f"[garde] réponse au dépassement en échec : {erreur!r}")


def poser_la_reponse_perdue(moteur: Any, agent: Any, llm: Any) -> None:
    from api.services.phrases.catalogue import REPONSE_PERDUE
    from api.services.phrases.diseur import DiseurDePhrases
    from api.services.pipecat.reponse_avalee import ATTRIBUT_PHRASE_DE_REPLI

    diseur = getattr(moteur, "phrases", None)
    if isinstance(diseur, DiseurDePhrases):
        setattr(llm, ATTRIBUT_PHRASE_DE_REPLI, lambda: diseur.prendre(REPONSE_PERDUE, agent))


async def garder_l_agent(
    moteur: Any, agent: Any, *, reglages: dict | None = None, user_config: Any = None
) -> GardeDuModele | None:
    """Arme la garde sur le service de conversation de ``agent`` (premier agent ou collègue), avec
    son cerveau de repli s'il en a un. ``reglages`` et ``user_config`` : ceux de l'appel pour le
    premier agent (ses champs ne sont pas encore posés). Une fois par service. ⛔ Ne lève jamais.

    Lot 4 bis : pose aussi sur ce service sa phrase « la réponse du modèle est perdue » (la règle de
    cet agent, lue au moment de la dire), que le filet du flux vide dit à sa place."""
    try:
        llm = getattr(agent, "llm", None)
        if llm is None or getattr(llm, "_mark_garde", None) is not None:
            return getattr(llm, "_mark_garde", None)
        poser_la_reponse_perdue(moteur, agent, llm)
        reglages = reglages if reglages is not None else (getattr(agent, "reglages", None) or {})
        configuration = user_config if user_config is not None else getattr(agent, "user_config", None)
        # L'organisation n'est lue (en base) que si un repli est réglé : le cas rare (F26).
        repli = (
            await repli_de(reglages, configuration, await moteur._get_organization_id())
            if reglages.get(CLE_REPLI)
            else None
        )

        async def relancer() -> None:
            if moteur.is_call_disposed() or not moteur.agent_can_act(agent):
                return
            moteur.expect_response()
            await agent.run_llm(moteur.context)

        garde = GardeDuModele(moteur, llm, relancer, parle=True, agent=agent, repli=repli)
        if not garde.brancher(delai_de_garde(reglages)):
            return None
        llm._mark_garde = garde
        return garde
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[garde] agent non gardé : {erreur!r}")
        return None


async def garder_le_fond(moteur: Any, agent: Any, service: Any, contexte: Callable[[], Any]) -> None:
    """Arme la garde sur le service du cerveau de fond de ``agent`` (délai de l'agent, repli du
    fond). La relance rejoue la requête du fond sur son propre contexte. ⛔ Ne lève jamais."""
    try:
        if service is None or getattr(service, "_mark_garde", None) is not None:
            return
        from pipecat.frames.frames import LLMContextFrame

        reglages = getattr(agent, "reglages", None) or {}
        repli = (
            await repli_de(
                reglages,
                getattr(agent, "user_config", None),
                await moteur._get_organization_id(),
                CLE_REPLI_DU_FOND,
            )
            if reglages.get(CLE_REPLI_DU_FOND)
            else None
        )

        async def relancer() -> None:
            ctx = contexte()
            if ctx is not None and not moteur.is_call_disposed():
                await service.queue_frame(LLMContextFrame(ctx))

        garde = GardeDuModele(moteur, service, relancer, parle=False, agent=agent, repli=repli)
        if garde.brancher(delai_de_garde(reglages)):
            service._mark_garde = garde
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[garde] fond non gardé : {erreur!r}")
