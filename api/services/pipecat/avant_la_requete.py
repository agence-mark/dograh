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
2. **l'arbitre** (``decideur_de_fin_de_tour.arbitre_avant_la_requete``, décision d'Evan du 29/10) : sur une étape où il
   est allumé, la requête attend sa décision sur la parole de la personne (au plus le délai de l'étape) ; sûre et ≠
   « rester » : même passage que l'option 2, l'étape d'arrivée répond directement. Au-delà du délai, la requête part
   sans lui. Seule attente ajoutée à la réponse par l'arbitre, mesurée (``attente``) ;
3. **la notice d'un tour** (``passage_sur_la_fiche.contexte_avec_la_notice``) : posée dans une COPIE du contexte, pour
   cette requête seulement ; l'historique n'est pas touché.

⚠️ Requête anticipée (``speculation``) : jamais préparée ici, et si l'anticipation est CONFIRMÉE Pipecat ne relance pas de
requête (``run_llm=not confirms_speculation``) : l'option 2, l'arbitre et la notice d'un tour ne s'appliquent donc pas à ce
tour-là. La détection anticipée n'est pas activée aujourd'hui ; si elle l'était, ce tour partirait sans ces portes (une
requête anticipée ne change jamais d'étape, prouvé par ``test_passages_fiables_seconde_revue``).

Posés seulement sur un agent qui a au moins une étape qui réclame le code (``autour_du_cerveau``) : un agent tout éteint
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
    """L'option 2, puis l'arbitre, puis la notice d'un tour, sur la requête que porte ``trame``. Rend la trame à pousser
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
        if not await passage.avant_la_requete(moteur, llm, trame.context, depart=depart):
            await decideur.arbitre_avant_la_requete(moteur, llm, trame.context, depart=depart)
    except asyncio.CancelledError:
        raise
    except Exception as erreur:  # noqa: BLE001 -- jamais à la place du tour
        logger.warning(f"[passage] option 2 ou arbitre en échec : {erreur!r}")
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
        if moteur is None or llm is None or not agent_reclame_le_code(agent):
            return None, None
        nom = getattr(agent, "visit_id", None) or "agent"
        return (
            AvantLaRequete(moteur, llm, FrameDirection.DOWNSTREAM, name=f"{nom}::AvantLaRequete"),
            AvantLaRequete(moteur, llm, FrameDirection.UPSTREAM, name=f"{nom}::AvantLaRequeteMontante"),
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] processeurs autour du cerveau non posés : {erreur!r}")
        return None, None
