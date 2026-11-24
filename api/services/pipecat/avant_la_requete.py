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
   sans lui. Seule attente ajoutée à la réponse par l'arbitre, mesurée (``attente``) ; puis, sous-lot 21, **la porte
   « sinon »** (``passage_sur_la_fiche.sinon_avant_la_requete``) quand rien n'a passé sur cette parole ;
4. **l'état de la fiche dans l'instruction système** (``fiche_dans_le_systeme``, D4 du figeage v12, case de l'agent,
   éteinte par défaut) : rangé en dernier dans l'instruction système du service, recalculé à chaque requête, après les
   passages ci-dessus ;
4 bis. **l'état des connecteurs** (``etat_des_connecteurs``, agent fiable du 17/11) : quand un outil de la requête appartient à un
   connecteur qui déclare un état, ce texte de faits est rangé après celui de la fiche ; sinon rien n'est touché ;
5. **la notice d'un tour** (``passage_sur_la_fiche.contexte_avec_la_notice``) : posée dans une COPIE du contexte, pour
   cette requête seulement ; l'historique n'est pas touché ;
6. **les cases selon l'état** (``cases_selon_l_etat``, Partie 1, lot 2) : chaque outil d'un connecteur qui les déclare ne garde que ses cases
   visibles, et les cases montrées sont gardées dans le tour (D52) ; une erreur retient la requête, jamais avalée.

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

from pipecat.frames.frames import Frame, LLMContextFrame, TTSSpeakFrame
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
        if (
            not await passage.avant_la_requete(moteur, llm, trame.context, depart=depart)
            and not await passage.fiche_deja_vraie_avant_la_requete(moteur, llm, trame.context, depart=depart)
            and not await decideur.arbitre_avant_la_requete(moteur, llm, trame.context, depart=depart)
        ):
            # Sous-lot 21 : rien n'a passé sur cette parole, la porte « sinon » de l'étape (s'il y en a une).
            await passage.sinon_avant_la_requete(moteur, llm, trame.context, depart=depart)
    except asyncio.CancelledError:
        raise
    except Exception as erreur:  # noqa: BLE001 -- jamais à la place du tour
        logger.warning(f"[passage] option 2 ou arbitre en échec : {erreur!r}")
    return await preparer_la_forme(moteur, llm, trame)


async def preparer_la_forme(moteur: Any, llm: Any, trame: LLMContextFrame) -> LLMContextFrame:
    """Chantier Partie 1, lot 6 : la FORME de la requête (l'état de la fiche et des connecteurs dans l'instruction système, les notices, les
    portes fermées, les cases selon l'état gardées dans le tour), sans les passages d'étape qui lisent la parole de la personne. Appelée par
    ``preparer_la_requete`` après ces passages, et par ``AgentRuntime.run_llm`` pour une requête lancée directement au cerveau (l'ouverture
    d'une étape sans phrase d'accueil, une relance) : celle-ci ne traverse pas les processeurs posés devant lui. Constat de l'appel 6 du
    chantier : l'agent de commande qui ouvre après une passation partait sans ses cases, et sa première fiche était refusée
    (« cases_pas_ouvertes »). Lève ``CasesIllisibles`` comme la requête ordinaire (D52)."""
    from api.services.workflow import passage_sur_la_fiche as passage

    # P3 (lot 19 bis) : le modèle part pour une requête : il reçoit tous les résultats rendus, aucune lecture n'attend plus la relance.
    try:
        from api.services.actions_communes.parole import la_lecture_est_vue

        la_lecture_est_vue(getattr(moteur, "_gathered_context", None))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[parole] lecture vue non notée : {erreur!r}")
    # figeage-v12 (D4) : l'état de la fiche, calculé APRÈS les passages ci-dessus (l'étape d'arrivée écrit pour la sienne), rangé
    # dans l'instruction système quand la case de l'agent est allumée.
    try:
        if getattr(moteur.active_agent, "llm", None) is llm:
            from api.services.workflow import fiche_dans_le_systeme

            fiche_dans_le_systeme.placer_la_fiche(moteur, llm, list(trame.context.get_messages()))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] état non rangé dans le système : {erreur!r}")
    # Agent fiable (17/11) : l'état que tiennent les connecteurs des outils de CETTE requête (ce qui est pris, ce qui manque ensuite), rangé en
    # dernier dans l'instruction système ; aucun outil d'un connecteur à état : rien n'est touché.
    try:
        if getattr(moteur.active_agent, "llm", None) is llm:
            from api.services.workflow import etat_des_connecteurs

            etat_des_connecteurs.placer_l_etat(moteur, llm, trame.context.tools)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[etat] état des connecteurs non rangé : {erreur!r}")
    # agent-facon-tala (C1) : la case « reconnaître un outil écrit en texte » de l'agent actif, posée sur son cerveau.
    try:
        if getattr(moteur.active_agent, "llm", None) is llm:
            from api.services.pipecat.texte_du_cerveau import poser_la_case_outil_ecrit

            poser_la_case_outil_ecrit(moteur, llm)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[cerveau] case « outil écrit » non posée : {erreur!r}")
    copie = passage.contexte_avec_la_notice(moteur, trame.context)
    # [.mark] U3 quinquies, couche 3 : lit la parole de la personne en parallèle, pose le rappel du résultat d'avant (jamais attendu).
    from api.services.securite import ecoute as ecoute_securite

    rappel = ecoute_securite.contexte_avec_le_rappel(moteur, copie if copie is not None else trame.context)
    if rappel is not None:
        copie = rappel
    # [.mark] L3e : le garde-fou urgence (mots et tournures, aucun appel de modèle), sur la parole de la personne.
    from api.services.securite import urgence as garde_urgence

    notice_urgence = await garde_urgence.surveiller(moteur, trame.context)
    if notice_urgence:
        avec_la_notice = garde_urgence.contexte_avec_la_notice(copie if copie is not None else trame.context, notice_urgence)
        if avec_la_notice is not None:
            copie = avec_la_notice
    # [.mark] Agent fiable (17/11) : les portes fermées par l'état (une action ouverte), retirées de CETTE requête.
    from api.services.workflow import portes_fermees

    sans_portes = portes_fermees.contexte_sans_les_portes_fermees(moteur, copie if copie is not None else trame.context)
    if sans_portes is not None:
        copie = sans_portes
    # [.mark] Partie 1, lot 2 (E26, D52) : les cases selon l'état, sur la même copie ; les cases montrées sont gardées dans le tour. Une erreur
    # n'est jamais avalée : ``CasesIllisibles`` remonte et la requête ne part pas avec toutes les cases.
    from api.services.workflow import cases_selon_l_etat

    avec_les_cases = cases_selon_l_etat.contexte_avec_les_cases_de_l_etat(moteur, copie if copie is not None else trame.context)
    if avec_les_cases is not None:
        copie = avec_les_cases
    if copie is None:
        return trame
    return LLMContextFrame(context=copie, speculation=trame.speculation)


def phrase_si_les_cases_sont_illisibles(moteur: Any, llm: Any = None) -> str:
    """P8 (lot 19 bis) : ce que dit le code quand les cases du tour sont illisibles et que la requête ne part pas : le repli du point de contact (la question en attente, sinon ce qui
    manque), sinon la phrase réglée de l'agent (« pas compris », lot 7b ligne 29). Avant : une ligne au journal et plus aucune réponse, à chaque tour, jusqu'au raccrochage. ⛔ Ne lève jamais."""
    from api.services.pipecat.reponse_avalee import phrase_de_repli_reglee

    try:
        from api.services.actions_communes.repli import repli_dit_par_le_code
        from api.services.workflow import parole_de_la_fiche as PF

        fiche = getattr(moteur, "_gathered_context", None)
        connecteur = PF._connecteur_de_l_etape(moteur)
        p = PF.dossier_de_la_parole(fiche, connecteur)
        repli = repli_dit_par_le_code(p, getattr(connecteur, "texte_du_manque", None), fiche)
        if isinstance(repli, str) and repli.strip():
            return repli.strip()
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[cases] repli non lu : {erreur!r}")
    return phrase_de_repli_reglee(llm)


def requete_retenue(moteur: Any, erreur: Exception, llm: Any = None) -> str:
    """Lot 7a (ligne 124) : la requête d'un tour ou d'une ouverture n'est pas partie parce que les cases sont illisibles (D52) : UNE fonction pour les deux endroits (``AvantLaRequete`` au tour,
    ``AgentRuntime.run_llm`` à l'ouverture). Une ligne au journal, et rend la phrase du repli du code (P8). ⛔ Ne lève jamais (``phrase_si_les_cases_sont_illisibles``)."""
    logger.error(f"[cases] requête retenue : {erreur}")
    return phrase_si_les_cases_sont_illisibles(moteur, llm)


async def _forme_de_l_ouverture(moteur: Any, llm: Any, trame: LLMContextFrame) -> LLMContextFrame:
    """La forme de la requête d'ouverture (``AgentRuntime.run_llm``) : des cases illisibles écrivent le même journal qu'au tour (``requete_retenue``) avant de remonter ; la phrase du repli que rend ``requete_retenue`` est portée par
    l'erreur (``a_dire``), l'ouverture la dit (lot 7b, ligne 29 : plus de silence)."""
    from api.services.workflow.cases_selon_l_etat import CasesIllisibles

    try:
        return await preparer_la_forme(moteur, llm, trame)
    except CasesIllisibles as erreur:
        erreur.a_dire = requete_retenue(moteur, erreur, llm)
        raise


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
            from api.services.workflow.cases_selon_l_etat import CasesIllisibles

            try:
                frame = await preparer_la_requete(self._moteur, self._llm, frame)
            except asyncio.CancelledError:
                raise
            except CasesIllisibles as erreur:
                # D52 : la requête ne part pas avec toutes les cases ; le tour échoue, visible au journal ; P8 : la phrase du code est dite (jamais un tour muet).
                await self.push_frame(TTSSpeakFrame(text=requete_retenue(self._moteur, erreur, self._llm)), FrameDirection.DOWNSTREAM)
                return
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

        from api.services.securite.ecoute import ecoute_allumee
        from api.services.securite.urgence import urgence_allumee
        from api.services.workflow.portes_fermees import agent_a_une_porte_fermable

        if moteur is None or llm is None or not (
            agent_reclame_le_code(agent) or case_allumee(agent, moteur) or case_outil_ecrit(agent, moteur) or ecoute_allumee(agent) or urgence_allumee(agent)
            or agent_a_une_porte_fermable(agent)
        ):
            return None, None
        nom = getattr(agent, "visit_id", None) or "agent"
        try:
            # lot 6 : la même forme pour une requête lancée directement au cerveau (``AgentRuntime.run_llm``)
            agent.preparer_la_forme = lambda trame: _forme_de_l_ouverture(moteur, llm, trame)
        except Exception:  # noqa: BLE001 -- un agent sans attribut libre garde l'ancien chemin
            pass
        return (
            AvantLaRequete(moteur, llm, FrameDirection.DOWNSTREAM, name=f"{nom}::AvantLaRequete"),
            AvantLaRequete(moteur, llm, FrameDirection.UPSTREAM, name=f"{nom}::AvantLaRequeteMontante"),
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] processeurs autour du cerveau non posés : {erreur!r}")
        return None, None
