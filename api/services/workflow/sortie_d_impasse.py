"""[.mark] fiabilite-de-la-conversation, lot A (point 14) : le garde-fou de sortie d'impasse.

Quand la conversation tourne en rond, le code le voit (il compte, il ne lit jamais le métier), avertit le modèle deux
fois, puis reprend la main lui-même. Rien ici ne sait de quoi parle l'appel : les étapes, les champs et les mots sont des
données.

**Les signes** (comptés par le code) :

1. dans l'étape en cours, l'agent redit une réplique identique (après normalisation) à l'une de ses deux précédentes, hors
   phrases du code (dont celles d'attente), hors phrases entre guillemets du prompt de l'étape ;
2. une demande au fond **identique** (règle B1 du lot B, ``demandes_deja_faites``, jamais recopiée) à une demande déjà faite
   dans l'étape. Comptée au moment où la demande PART, même pendant une attente, et même si B2 la refuse (D-3) ;
3. seulement dans une étape qui a des champs attendus encore vides (D11) : trois tours de suite sans champ nouveau (un
   champ lu par un module au tour même compte comme nouveau), sans sortie prise, sans résultat d'outil ; le signe tombe une
   fois ;
4. sur tout l'appel (D15) : l'agent entre une troisième fois dans une même étape.

**Aucun des signes 1 et 3 ne compte pendant une attente du système** (D2) : un travail de fond en cours, un tour qui porte un
appel d'outil, et le tour qui suit. Le signe 2 n'est pas concerné (chaque demande ouvre une attente).

**La riposte graduée** (seuil de 2 signes) : au 2e signe une notice au modèle (temps 1), au signe suivant une seconde (temps 2),
au signe suivant le code dit la phrase du motif « impasse » du catalogue puis change l'étape (temps 3) ; à la deuxième impasse
de l'appel, le motif « impasse répétée ». Les compteurs des signes 1 à 3 repartent à chaque changement d'étape et après le
temps 3 ; celui du signe 4 jamais. Tout vit dans la fiche de l'appel (``impasse``), qui survit d'un tour à l'autre au clavier.

⛔ Ne lève jamais : une impasse mal comptée ne coûte jamais l'appel.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any

from loguru import logger

from api.services.fiche.traces import CLE_TOUR

CLE_IMPASSE = "impasse"

SIGNE_REPLIQUE = "replique_redite"
SIGNE_DEMANDE = "demande_identique"
SIGNE_RIEN_DE_NOUVEAU = "rien_de_nouveau"
SIGNE_ETAPE_REVISITEE = "etape_revisitee"

# Revue D-1 du plan : deux signes, puis un par temps (Copilot Studio : deux reprises ; Dialogflow : trois).
SIGNES_AU_TEMPS_1 = 2
TEMPS_FINAL = 3
# Signe 4 (D15) : la troisième entrée dans une même étape.
ENTREES_POUR_LE_SIGNE_4 = 3
# Signe 3 (D11) : trois tours de suite sans champ nouveau.
TOURS_SANS_CHAMP = 3
# Signe 1 : une réplique de moins de trois mots (« d'accord », « très bien ») se redit naturellement.
MOTS_MIN_D_UNE_REPLIQUE = 3

# Consignes au modèle (jamais dites à l'appelant) : génériques, aucun métier.
NOTICE_TEMPS_1 = (
    "Tu tournes en rond avec la personne. Repars de ce qu'elle a déjà dit, ne redemande rien de ce qui est noté, "
    "et pose une seule question sur ce qui manque, ou prends ta sortie."
)
NOTICE_TEMPS_2 = (
    "Tu tournes toujours en rond. Pose une seule question fermée, à deux choix, sur ce qui manque, rien d'autre."
)

_MOTS = re.compile(r"\w+", re.UNICODE)
_ENTRE_GUILLEMETS = re.compile(r"«\s*(.+?)\s*»|“\s*(.+?)\s*”|\"\s*(.+?)\s*\"", re.DOTALL)
_LONGUEUR_JOURNAL = 30


def _fiche(moteur: Any) -> dict | None:
    fiche = getattr(moteur, "_gathered_context", None)
    return fiche if isinstance(fiche, dict) else None


def _tour(moteur: Any) -> int | None:
    fiche = _fiche(moteur)
    tour = fiche.get(CLE_TOUR) if fiche is not None else None
    return tour if isinstance(tour, int) else None


def _etat(moteur: Any) -> dict | None:
    """L'état du garde-fou, rangé dans la fiche de l'appel. ``None`` sans fiche."""
    fiche = _fiche(moteur)
    if fiche is None:
        return None
    etat = fiche.get(CLE_IMPASSE)
    if not isinstance(etat, dict):
        etat = {
            "etape": None,
            "signes": 0,
            "temps": 0,
            "repliques": [],
            "tours_sans_champ": 0,
            "signature": None,
            "signe_rien_de_nouveau": False,
            "visites": {},
            "impasses": 0,
            "notice": None,
            "notice_tour": None,
            "a_declencher": False,
            "attente_precedente": False,
            "tour_signe_replique": None,
            "tour_evalue": None,
            "journal": [],
        }
        fiche[CLE_IMPASSE] = etat
    return etat


def _remettre_a_zero(etat: dict) -> None:
    """Les compteurs des signes 1 à 3 et la riposte : à chaque changement d'étape, et après le temps 3."""
    etat.update(
        signes=0,
        temps=0,
        repliques=[],
        tours_sans_champ=0,
        signe_rien_de_nouveau=False,
        notice=None,
        notice_tour=None,
        a_declencher=False,
        tour_signe_replique=None,
        tour_evalue=None,
    )


def _journaliser(etat: dict, moteur: Any, **entree: Any) -> None:
    etat["journal"] = [*etat["journal"][-(_LONGUEUR_JOURNAL - 1) :], {"tour": _tour(moteur), **entree}]


def _cle_de_l_etape(agent: Any, noeud: Any) -> str:
    return f"{getattr(agent, 'workflow_id', None)}:{getattr(noeud, 'id', None)}"


# ---------------------------------------------------------------------------------------------------------
# Compter un signe et monter la riposte
# ---------------------------------------------------------------------------------------------------------


def noter_un_signe(moteur: Any, nature: str) -> int:
    """Un signe de plus dans l'étape en cours ; monte la riposte d'un temps au plus. Rend le nombre de signes.
    ⛔ Ne lève jamais."""
    try:
        etat = _etat(moteur)
        if etat is None:
            return 0
        etat["signes"] += 1
        n = etat["signes"]
        cible = min(max(n - SIGNES_AU_TEMPS_1 + 1, 0), TEMPS_FINAL)
        _journaliser(etat, moteur, signe=nature, signes=n)
        if cible > etat["temps"]:
            etat["temps"] = cible
            etat["notice_tour"] = _tour(moteur)
            if cible == 1:
                etat["notice"] = NOTICE_TEMPS_1
            elif cible == 2:
                etat["notice"] = NOTICE_TEMPS_2
            else:
                etat["notice"] = None
                etat["a_declencher"] = True
            _journaliser(etat, moteur, temps=cible)
            logger.info(f"[impasse] {nature} : {n} signes, temps {cible}")
        return n
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] signe non compté : {erreur!r}")
        return 0


def entrer_dans_l_etape(moteur: Any, agent: Any, noeud: Any) -> None:
    """Le changement d'étape remet à zéro les signes 1 à 3 ; la troisième entrée dans une même étape est le signe 4
    (compteur de visites jamais remis à zéro). Une entrée répétée dans la même étape (le clavier la rejoue à chaque tour)
    ne compte pas. ⛔ Ne lève jamais."""
    try:
        etat = _etat(moteur)
        if etat is None or noeud is None:
            return
        cle = _cle_de_l_etape(agent, noeud)
        if etat["etape"] == cle:
            return
        _remettre_a_zero(etat)
        etat["etape"] = cle
        etat["signature"] = _signature_des_champs(moteur, noeud)
        visites = etat["visites"]
        visites[cle] = int(visites.get(cle) or 0) + 1
        if not getattr(noeud, "is_end", False) and visites[cle] >= ENTREES_POUR_LE_SIGNE_4:
            noter_un_signe(moteur, SIGNE_ETAPE_REVISITEE)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] entrée dans l'étape non notée : {erreur!r}")


def compter_la_demande(moteur: Any, agent: Any, demande: Any) -> None:
    """Signe 2 : l'agent envoie au travail de fond une demande identique (règle B1) à une demande déjà faite dans
    l'étape. Appelé quand la demande PART, avant la décision de B2. ⛔ Ne lève jamais."""
    try:
        from api.services.travail.demande_identique import demandes_deja_faites, identifiant_de_l_etape

        if _etat(moteur) is None:
            return
        if demandes_deja_faites(moteur, demande, identifiant_de_l_etape(getattr(agent, "current_node", None))):
            noter_un_signe(moteur, SIGNE_DEMANDE)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] demande identique non comptée : {erreur!r}")


# ---------------------------------------------------------------------------------------------------------
# Signes 1 et 3 : lus à la fin de chaque réplique de l'agent
# ---------------------------------------------------------------------------------------------------------


def _cle_de_texte(texte: Any) -> str:
    return " ".join(_MOTS.findall(str(texte or "").casefold()))


def _phrases_a_ignorer(moteur: Any, noeud: Any) -> list[str]:
    """Les phrases que l'agent a le droit de redire : celles du code (dont les attentes) et celles que le prompt de
    l'étape met entre guillemets. Normalisées, de la plus longue à la plus courte."""
    cles: set[str] = set()
    fiche = _fiche(moteur) or {}
    from api.services.phrases.diseur import CLE_TRACE

    for entree in fiche.get(CLE_TRACE) or []:
        if isinstance(entree, dict):
            cles.add(_cle_de_texte(entree.get("texte")))
    prompt = getattr(noeud, "prompt", None)
    if isinstance(prompt, str):
        for trouve in _ENTRE_GUILLEMETS.findall(prompt):
            cles.add(_cle_de_texte(next((t for t in trouve if t), "")))
    return sorted((c for c in cles if c), key=len, reverse=True)


def _reste_de_la_replique(texte: str, moteur: Any, noeud: Any) -> str | None:
    """La réplique normalisée, privée des phrases qu'elle a le droit de redire. ``None`` : il n'en reste pas assez pour
    être une réplique de l'agent."""
    cle = f" {_cle_de_texte(texte)} "
    for phrase in _phrases_a_ignorer(moteur, noeud):
        cle = cle.replace(f" {phrase} ", " ")
    reste = " ".join(cle.split())
    return reste if len(reste.split()) >= MOTS_MIN_D_UNE_REPLIQUE else None


def _signature_des_champs(moteur: Any, noeud: Any) -> list | None:
    """Ce que l'étape attend encore et ce que la fiche porte pour ses champs : change dès qu'un champ est noté, corrigé
    ou lu par un module au tour même. ``None`` si l'étape n'attend aucun champ (le signe 3 n'existe pas)."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = _fiche(moteur)
        if reglages is None or fiche is None or noeud is None:
            return None
        from api.services.fiche.traces import valeurs_des_traces
        from api.services.groupe.notes import champs_attendus
        from api.services.workflow.champs_conditionnels import champs_actifs

        champs = champs_actifs(noeud, fiche)
        if not champs:
            return None
        manque = champs_attendus(reglages, fiche, champs, valeurs_des_traces(reglages, fiche))
        if not manque:
            return None
        return [list(manque), [str(fiche.get(c)) for c in champs]]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] champs de l'étape illisibles : {erreur!r}")
        return None


def _attente_du_systeme(moteur: Any, etat: dict) -> bool:
    """Un travail de fond en cours, un tour qui porte un appel d'outil, ou le tour qui suit (D2)."""
    from api.services.workflow.plafond_d_outils import appels_du_tour

    en_attente = _un_travail_est_en_cours(moteur) or appels_du_tour(moteur) > 0
    precedente = bool(etat.get("attente_precedente"))
    etat["attente_precedente"] = en_attente
    return en_attente or precedente


def _un_travail_est_en_cours(moteur: Any) -> bool:
    """Le temps 3 attend la fin du travail de fond : rendre la main avec un résultat en route le perdrait."""
    from api.services.travail.agent import ligne_du_travail

    return ligne_du_travail(moteur) is not None


def _signe_de_la_replique(moteur: Any, etat: dict, noeud: Any, texte: str, tour: int | None) -> bool:
    reste = _reste_de_la_replique(texte, moteur, noeud)
    if reste is None:
        return False
    deja = reste in etat["repliques"]
    etat["repliques"] = [*etat["repliques"][-1:], reste]
    if not deja or (tour is not None and etat.get("tour_signe_replique") == tour):
        return False
    etat["tour_signe_replique"] = tour
    return True


def _signe_rien_de_nouveau(moteur: Any, etat: dict, noeud: Any) -> bool:
    signature = _signature_des_champs(moteur, noeud)
    if signature is None:
        etat["tours_sans_champ"] = 0
        etat["signature"] = None
        return False
    if signature != etat.get("signature"):
        etat.update(signature=signature, tours_sans_champ=0, signe_rien_de_nouveau=False)
        return False
    etat["tours_sans_champ"] += 1
    if etat["tours_sans_champ"] >= TOURS_SANS_CHAMP and not etat["signe_rien_de_nouveau"]:
        etat["signe_rien_de_nouveau"] = True
        return True
    return False


async def fin_de_la_replique(moteur: Any, texte: str, depart: tuple | None) -> bool:
    """À la fin de chaque réplique de l'agent : signes 1 et 3, puis, si la riposte est au temps 3, la sortie.
    ``depart`` : où l'on était au début de la réplique ; si l'étape a changé pendant elle, rien ne compte. Rend ``True``
    si le code a repris la main. ⛔ Ne lève jamais."""
    try:
        etat = _etat(moteur)
        if etat is None or moteur.is_call_disposed():
            return False
        agent = moteur.active_agent
        noeud = getattr(agent, "current_node", None)
        if noeud is None or getattr(noeud, "is_end", False):
            return False
        sans_changement = depart is None or depart == moteur.etat_pour_le_filet()
        tour = _tour(moteur)
        if sans_changement and not _attente_du_systeme(moteur, etat):
            if _signe_de_la_replique(moteur, etat, noeud, texte, tour):
                noter_un_signe(moteur, SIGNE_REPLIQUE)
            # Le tour d'un appelant n'est évalué qu'une fois pour le signe 3 (un tour peut porter plusieurs répliques).
            if tour is None or etat.get("tour_evalue") != tour:
                etat["tour_evalue"] = tour
                if _signe_rien_de_nouveau(moteur, etat, noeud):
                    noter_un_signe(moteur, SIGNE_RIEN_DE_NOUVEAU)
        if etat["a_declencher"] and not _un_travail_est_en_cours(moteur):
            return await sortir(moteur)
        return False
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] fin de réplique non traitée : {erreur!r}")
        return False


# ---------------------------------------------------------------------------------------------------------
# Temps 3 : dire, puis changer l'étape
# ---------------------------------------------------------------------------------------------------------


async def sortir(moteur: Any) -> bool:
    """Le temps 3 : la phrase du motif « impasse » (« impasse répétée » à la deuxième impasse de l'appel), puis la suite
    réglée dans « Ensuite » (par défaut : la main revient à l'accueil, fiche gardée). Un motif éteint ne dit rien et laisse
    le modèle. ⛔ Ne lève jamais."""
    try:
        from api.services.phrases.catalogue import IMPASSE, IMPASSE_REPETEE
        from api.services.phrases.sorties import lancer_apres

        etat = _etat(moteur)
        if etat is None or moteur.transfer_coordinator.in_progress:
            return False
        agent = moteur.active_agent
        motif = IMPASSE_REPETEE if etat["impasses"] >= 1 else IMPASSE
        phrase = moteur.phrases.phrase(motif, agent)
        _remettre_a_zero(etat)
        if phrase is None or not phrase.active:
            _journaliser(etat, moteur, motif=motif, eteint=True)
            return False
        etat["impasses"] += 1
        _journaliser(etat, moteur, motif=motif, impasse=etat["impasses"])
        probleme = await moteur.phrases.signaler_un_probleme(motif, agent, differer=True)
        if probleme.issue is None:
            return False
        lancer_apres(moteur, probleme.issue)
        return probleme.issue.prise_en_main
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] sortie non lancée : {erreur!r}")
        return False


# ---------------------------------------------------------------------------------------------------------
# Branchements
# ---------------------------------------------------------------------------------------------------------

_MARQUE = "_mark_notice_d_impasse"


def notice_a_montrer(moteur: Any) -> str | None:
    """La notice du temps 1 ou 2, tant qu'elle vaut : le tour où elle est née et le suivant. ⛔ Ne lève jamais."""
    try:
        fiche = _fiche(moteur)
        etat = fiche.get(CLE_IMPASSE) if fiche is not None else None
        if not isinstance(etat, dict) or not etat.get("notice"):
            return None
        tour, ne = _tour(moteur), etat.get("notice_tour")
        if tour is not None and isinstance(ne, int) and not (ne <= tour <= ne + 1):
            return None
        return etat["notice"]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] notice illisible : {erreur!r}")
        return None


def montrer_l_impasse(moteur: Any, llm: Any) -> bool:
    """Chaque requête de CONVERSATION de ``llm`` reçoit la notice du garde-fou, juste avant la dernière parole de
    l'appelant (``inserer_l_etat``, comme la ligne du travail en cours). Rien n'entre dans l'historique ni dans le prompt
    système ; sans notice, la requête est inchangée. Une fois par service. ⛔ Ne lève jamais."""
    try:
        if getattr(llm, _MARQUE, False):
            return True
        if not (hasattr(llm, "get_chat_completions") and hasattr(llm, "build_chat_completion_params")):
            return False
        from api.services.workflow.fiche_au_fil_de_leau import inserer_l_etat

        en_conversation: ContextVar[bool] = ContextVar("impasse_en_conversation", default=False)
        obtenir = llm.get_chat_completions
        construire = llm.build_chat_completion_params

        async def get_chat_completions(context):
            jeton = en_conversation.set(True)
            try:
                return await obtenir(context)
            finally:
                en_conversation.reset(jeton)

        def build_chat_completion_params(params_from_context):
            params = construire(params_from_context)
            if en_conversation.get():
                try:
                    notice = notice_a_montrer(moteur)
                    if notice:
                        cle = "messages" if "messages" in params else "input"
                        params[cle] = inserer_l_etat(list(params[cle]), notice)
                except Exception as erreur:  # noqa: BLE001
                    logger.error(f"[impasse] notice non montrée : {erreur!r}")
            return params

        llm.get_chat_completions = get_chat_completions
        llm.build_chat_completion_params = build_chat_completion_params
        setattr(llm, _MARQUE, True)
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] notice non branchée : {erreur!r}")
        return False


def brancher_la_sortie_d_impasse(engine: Any, assistant_aggregator: Any) -> None:
    """Branche le garde-fou sur l'agrégateur de l'assistant : au début d'une réplique, l'étape où l'on est ; à sa fin,
    les signes 1 et 3 et, au temps 3, la sortie. Téléphone et clavier. ⛔ Ne lève jamais."""
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
                await fin_de_la_replique(engine, getattr(message, "content", None) or "", depart.pop("etat", None))
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[impasse] réplique non traitée : {erreur!r}")

    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[impasse] non branché : {erreur!r}")
