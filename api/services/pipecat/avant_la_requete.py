"""[.mark] passages-fiables : ce que le code fait juste avant qu'une requête parte au cerveau de conversation.

Décision d'Evan (29/10) : chaque brique se remplace ; rien ici ne dépend d'une famille de fournisseurs. Le point d'accroche
est ce que TOUS les services de Pipecat partagent : la trame ``LLMContextFrame`` (c'est elle, et elle seule, qui lance
une inférence : ``LLMService.process_frame``) et le contexte partagé ``LLMContext`` qu'elle porte.

Une requête atteint le cerveau par deux côtés, d'où deux processeurs du même type :

- **avant le cerveau**, la trame DESCENDANTE : la parole de la personne (agrégateur de la personne, par le pont des agents
  au téléphone ; la file du tour au clavier) ;
- **juste après le cerveau**, la trame MONTANTE : une relance (``LLMRunFrame``, par exemple après une porte prise par le
  code) revient de l'agrégateur de l'assistant, en bout de circuit, et remonte vers le cerveau.

Pour chaque requête de conversation (jamais une requête spéculative), dans cet ordre :

1. **l'option 2** (``passage_sur_la_fiche.avant_la_requete``) : étape réglée « attendre le dernier champ », un seul champ
   manque : attente bornée de la passe du greffier, puis passage d'étape AVANT que la requête parte. Le passage réécrit
   le prompt de l'étape (``LLMService._update_settings``, commun à tous) et les outils du contexte partagé : la requête
   qui part parle déjà dans l'étape d'arrivée ;
2. **une condition de la fiche déjà vraie** (``passage_sur_la_fiche.fiche_deja_vraie_avant_la_requete``, D7 du figeage
   v12) : passage AVANT la requête, sans relance, au lieu de « à la fin de la réplique » (qui faisait parler deux étapes
   dans un tour). Seule une porte déjà vraie attend le greffier ;
3. **l'arbitre** (``decideur_de_fin_de_tour.arbitre_avant_la_requete``, décision d'Evan du 29/10) : sur une étape où il
   est allumé, la requête attend sa décision sur la parole de la personne (au plus le délai de l'étape) ; sûre et ≠
   « rester » : même passage que l'option 2, l'étape d'arrivée répond directement. Au-delà du délai, la requête part
   sans lui. Seule attente ajoutée à la réponse par l'arbitre, mesurée (``attente``) ;
4. **l'état de la fiche dans l'instruction système** (``fiche_dans_le_systeme``, D4 du figeage v12, case de l'agent,
   éteinte par défaut) : rangé en dernier dans l'instruction système du service, recalculé à chaque requête, après les
   passages ci-dessus ;
5. **la notice d'un tour** (``passage_sur_la_fiche.contexte_avec_la_notice``) : posée dans une COPIE du contexte, pour
   cette requête seulement ; l'historique n'est pas touché.

⚠️ Requête anticipée (``speculation``) : jamais préparée ici, et si l'anticipation est CONFIRMÉE Pipecat ne relance pas de
requête (``run_llm=not confirms_speculation``) : l'option 2, l'arbitre et la notice d'un tour ne s'appliquent donc pas à ce
tour-là. La détection anticipée n'est pas activée aujourd'hui ; si elle l'était, ce tour partirait sans ces portes (une
requête anticipée ne change jamais d'étape, prouvé par ``test_passages_fiables_seconde_revue``).

Posés seulement sur un agent qui a au moins une étape qui réclame le code, ou l'une des cases « fiche dans le système » et « reconnaître un outil écrit en texte » allumée (``autour_du_cerveau``) : un agent tout éteint
a le circuit de la base, sans processeur de plus. ⛔ Ne lève jamais : dans le doute, la trame passe telle quelle.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


async def preparer_la_requete(moteur: Any, llm: Any, trame: LLMContextFrame) -> LLMContextFrame:
    """L'option 2, la fiche déjà vraie, puis l'arbitre, puis la notice d'un tour, sur la requête que porte ``trame``. Rend la trame à pousser
    (la même, ou une trame neuve sur une copie du contexte). ⛔ Ne lève jamais (l'annulation d'une interruption est
    propagée)."""
    from api.services.workflow import decideur_de_fin_de_tour as decideur
    from api.services.workflow import passage_sur_la_fiche as passage

    if getattr(trame, "speculation", False):
        return trame
    depart = time.monotonic()  # l'attente cumulée (option 2 puis arbitre) ne dépasse jamais le délai de l'étape
    try:
        if passage._derniere_parole_de_la_personne(trame.context):
            passage.oublier_la_porte_prise_avant(moteur)
        if not await passage.avant_la_requete(moteur, llm, trame.context, depart=depart) and not (
            await passage.fiche_deja_vraie_avant_la_requete(moteur, llm, trame.context, depart=depart)
        ):
            await decideur.arbitre_avant_la_requete(moteur, llm, trame.context, depart=depart)
    except asyncio.CancelledError:
        raise
    except Exception as erreur:  # noqa: BLE001 -- jamais à la place du tour
        logger.warning(f"[passage] option 2 ou arbitre en échec : {erreur!r}")
    # figeage-v12 (D4) : l'état de la fiche, calculé APRÈS les passages ci-dessus (l'étape d'arrivée écrit pour la sienne), rangé
    # dans l'instruction système quand la case de l'agent est allumée.
    try:
        if getattr(moteur.active_agent, "llm", None) is llm:
            from api.services.workflow import fiche_dans_le_systeme

            fiche_dans_le_systeme.placer_la_fiche(moteur, llm, list(trame.context.get_messages()))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] état non rangé dans le système : {erreur!r}")
    # agent-facon-tala (C1) : la case « reconnaître un outil écrit en texte » de l'agent actif, posée sur son cerveau.
    try:
        if getattr(moteur.active_agent, "llm", None) is llm:
            from api.services.pipecat.texte_du_cerveau import poser_la_case_outil_ecrit

            poser_la_case_outil_ecrit(moteur, llm)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[cerveau] case « outil écrit » non posée : {erreur!r}")
    copie = passage.contexte_avec_la_notice(moteur, trame.context)
    if copie is None:
        return trame
    return LLMContextFrame(context=copie, speculation=trame.speculation)


class AvantLaRequete(FrameProcessor):
    """Prépare les requêtes qui arrivent au cerveau dans le sens ``sens`` ; tout le reste passe tel quel."""

    def __init__(self, moteur: Any, llm: Any, sens: FrameDirection, **kwargs):
        super().__init__(**kwargs)
        self._moteur = moteur
        self._llm = llm
        self._sens = sens

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == self._sens:
            try:
                frame = await preparer_la_requete(self._moteur, self._llm, frame)
            except asyncio.CancelledError:
                raise
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[passage] requête non préparée : {erreur!r}")
        await self.push_frame(frame, direction)


def autour_du_cerveau(moteur: Any, agent: Any) -> tuple[AvantLaRequete | None, AvantLaRequete | None]:
    """Les deux processeurs à poser autour du cerveau de ``agent`` : (avant, juste après). ``(None, None)`` pour un agent
    qui n'a aucune étape qui réclame le code (le défaut) : son circuit est celui de la base. ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.passage_sur_la_fiche import agent_reclame_le_code

        llm = getattr(agent, "llm", None)
        from api.services.pipecat.texte_du_cerveau import case_outil_ecrit
        from api.services.workflow.fiche_dans_le_systeme import case_allumee

        if moteur is None or llm is None or not (
            agent_reclame_le_code(agent) or case_allumee(agent, moteur) or case_outil_ecrit(agent, moteur)
        ):
            return None, None
        nom = getattr(agent, "visit_id", None) or "agent"
        return (
            AvantLaRequete(moteur, llm, FrameDirection.DOWNSTREAM, name=f"{nom}::AvantLaRequete"),
            AvantLaRequete(moteur, llm, FrameDirection.UPSTREAM, name=f"{nom}::AvantLaRequeteMontante"),
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] processeurs autour du cerveau non posés : {erreur!r}")
        return None, None
