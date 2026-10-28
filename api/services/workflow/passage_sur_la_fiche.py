"""[.mark] passages-fiables, lot A : le passage d'étape sur la fiche.

Le petit modèle qui parle décide mal seul d'un passage d'étape (il en saute ou en double une sur trois). Ici le **code**
passe quand la fiche le permet, à la manière de Retell (des conditions sur des variables, sans modèle, d'abord) :

- une étape de **collecte** passe quand tous ses champs sont obtenus et que rien n'est « à confirmer » ;
- une porte peut porter une **condition sur la fiche** : « étape complète » ou « champ = valeur » (« refusé » compris) ;
  les conditions sont lues dans l'ordre de l'écran, la première vraie gagne.

Réglages dans le JSON de l'étape (``qui_decide_du_passage``, ``moment_du_passage``, ``delai_du_passage``) et de la porte
(``condition_sur_la_fiche``), aucune migration. ``agent`` (le défaut) = comportement d'avant, à l'octet : ni condition
lue, ni crochet posé. Une étape de collecte dont une porte n'a pas de condition donne « étape complète » à la
**première** porte sans condition seulement (prudence : une porte de sortie ou de refus n'est jamais prise d'elle-même).

Ce module ne décide pas **quand** : c'est le décideur de fin de tour (``decideur_de_fin_de_tour.py``) qui l'appelle, avec
le jeton de visite d'étape. Il porte aussi :

- **la notice d'un tour** : l'étape d'arrivée d'un passage fait par le code reçoit, sur sa première requête, le compte
  rendu « ce qui vient de se passer… L'appelant a entendu : « … ». Ne la répète pas. » (dans une copie du contexte de
  CETTE requête, jamais dans l'historique) ;
- **l'option 2** : sur une étape réglée « attendre le dernier champ », quand un seul champ manque, la requête de l'agent
  attend (au plus le délai) la passe du greffier sur la dernière parole ; si la condition devient vraie, le passage a
  lieu **avant** que l'agent parle, et l'étape d'arrivée parle directement. Sauf vers une fin, un retour au principal
  ou un transfert garanti : l'option 1 joue alors ;
- la trace ``passages_par_le_code`` dans le run.

Aucun mot de métier. ⛔ Ne lève jamais : un passage manqué ne coûte jamais l'appel (l'agent garde la main).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger

from api.services.fiche.traces import CLE_TOUR

CLE_PASSAGES = "passages_par_le_code"
DELAI_PAR_DEFAUT = 1.5
DELAI_MAX = 10.0  # borne côté serveur (l'écran la propose déjà)
SEUIL_PAR_DEFAUT = 0.8
RAISON_FICHE = "fiche"
RAISON_ARBITRE = "arbitre"

AGENT, COLLECTE, CHOIX, LIBRE = "agent", "collecte", "choix", "libre"
APRES_LA_REPONSE, ATTENDRE_LE_DERNIER_CHAMP = "apres_la_reponse", "attendre_le_dernier_champ"

# Le fait du compte rendu de la notice d'un tour (une consigne au modèle, jamais dite à l'appelant).
FAIT_DU_PASSAGE = "le code est passé à l'étape suivante, parce que la fiche ou la conversation le demandait"


@dataclass(frozen=True)
class Reglages:
    """Les réglages de passage d'une étape, lus dans son JSON."""

    qui: str = AGENT
    moment: str = APRES_LA_REPONSE
    delai: float = DELAI_PAR_DEFAUT
    arbitre: bool = False
    seuil: float = SEUIL_PAR_DEFAUT

    @property
    def le_code_lit_la_fiche(self) -> bool:
        return self.qui != AGENT

    @property
    def option_2(self) -> bool:
        return self.qui == COLLECTE and self.moment == ATTENDRE_LE_DERNIER_CHAMP


def reglages_du_passage(noeud: Any) -> Reglages:
    """Les réglages de l'étape ``noeud`` ; sans réglage (ou illisible) : ``agent``, tout éteint. ⛔ Ne lève jamais."""
    try:
        donnees = getattr(noeud, "data", None)
        qui = getattr(donnees, "qui_decide_du_passage", None) or AGENT
        if qui not in (AGENT, COLLECTE, CHOIX, LIBRE):
            qui = AGENT
        moment = getattr(donnees, "moment_du_passage", None) or APRES_LA_REPONSE
        delai = getattr(donnees, "delai_du_passage", None)
        arbitre = getattr(donnees, "arbitre", None)
        seuil = getattr(donnees, "seuil_de_l_arbitre", None)
        return Reglages(
            qui=qui,
            moment=moment,
            delai=(
                min(float(delai), DELAI_MAX)
                if isinstance(delai, (int, float)) and not isinstance(delai, bool) and delai > 0
                else DELAI_PAR_DEFAUT
            ),
            # Éteint par défaut, allumé par défaut sur les types « choix » et « libre ».
            arbitre=bool(arbitre) if isinstance(arbitre, bool) else qui in (CHOIX, LIBRE),
            seuil=float(seuil) if isinstance(seuil, (int, float)) and 0 <= seuil <= 1 else SEUIL_PAR_DEFAUT,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] réglages illisibles, l'agent garde la main : {erreur!r}")
        return Reglages()


def l_etape_reclame_le_code(noeud: Any) -> bool:
    """Le code a quelque chose à regarder dans cette étape (conditions sur la fiche ou arbitre) ?"""
    r = reglages_du_passage(noeud)
    return r.le_code_lit_la_fiche or r.arbitre


# ---------------------------------------------------------------------------------------------------------
# Les conditions
# ---------------------------------------------------------------------------------------------------------


def _fiche(moteur: Any) -> dict:
    fiche = getattr(moteur, "_gathered_context", None)
    return fiche if isinstance(fiche, dict) else {}


def etape_complete(moteur: Any, noeud: Any) -> bool:
    """Tous les champs actifs de la liste de l'étape sont obtenus (``champs_attendus`` vide, un champ lu par un module
    compte) ET aucun n'est « à confirmer » (``fiche_etat[champ].sure`` faux). Une étape sans liste de champs n'est jamais
    complète. ⛔ Ne lève jamais (dans le doute : fausse)."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = _fiche(moteur)
        if reglages is None or not tuple(getattr(noeud, "champs_etape", None) or ()):
            return False
        from api.services.fiche.traces import valeurs_des_traces
        from api.services.groupe.notes import champs_attendus
        from api.services.workflow.champs_conditionnels import champs_actifs
        from api.services.workflow.fiche_au_fil_de_leau import CLE_ETAT

        actifs = champs_actifs(noeud, fiche)
        if champs_attendus(reglages, fiche, actifs, valeurs_des_traces(reglages, fiche)):
            return False
        etat = fiche.get(CLE_ETAT) or {}
        return not any(isinstance(etat.get(c), dict) and etat[c].get("sure") is False for c in actifs)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] étape complète illisible : {erreur!r}")
        return False


def _condition_de(arete: Any) -> Any:
    condition = getattr(getattr(arete, "data", None), "condition_sur_la_fiche", None)
    if condition is None:
        return None
    if getattr(condition, "etape_complete", False) or str(getattr(condition, "champ", None) or "").strip():
        return condition
    return None


def _champ_vaut(moteur: Any, champ: str, vaut: Any) -> bool:
    from api.services.groupe.passations import condition_tenue
    from api.services.workflow.fiche_au_fil_de_leau import CLE_ETAT

    fiche = _fiche(moteur)
    if not condition_tenue(champ, vaut, fiche):
        return False
    etat = (fiche.get(CLE_ETAT) or {}).get(champ)
    return not (isinstance(etat, dict) and etat.get("sure") is False)


def portes_a_condition(noeud: Any) -> list[tuple[Any, dict]]:
    """Les portes de l'étape qui portent une condition sur la fiche, dans l'ordre de l'écran, avec leur lecture : ``{type:
    etape_complete}`` ou ``{type: champ, champ, vaut}``. Une étape de collecte donne « étape complète » à la première
    porte sans condition. Vide pour une étape ``agent``."""
    r = reglages_du_passage(noeud)
    if not r.le_code_lit_la_fiche:
        return []
    lues: list[tuple[Any, dict]] = []
    implicite_donnee = False
    for arete in getattr(noeud, "out_edges", None) or ():
        condition = _condition_de(arete)
        if condition is not None:
            if getattr(condition, "etape_complete", False):
                lues.append((arete, {"type": "etape_complete"}))
            else:
                lues.append(
                    (arete, {"type": "champ", "champ": condition.champ.strip(), "vaut": (condition.vaut or "").strip()})
                )
        elif r.qui == COLLECTE and not implicite_donnee:
            implicite_donnee = True
            lues.append((arete, {"type": "etape_complete", "implicite": True}))
    return lues


def porte_a_prendre_sur_la_fiche(moteur: Any, noeud: Any) -> tuple[Any, dict] | None:
    """La première porte, dans l'ordre de l'écran, dont la condition est vraie sur la fiche d'aujourd'hui, avec la
    condition lue ; ``None`` sinon. ⛔ Ne lève jamais."""
    try:
        for arete, lecture in portes_a_condition(noeud):
            if lecture["type"] == "etape_complete":
                vraie = etape_complete(moteur, noeud)
            else:
                vraie = _champ_vaut(moteur, lecture["champ"], lecture.get("vaut"))
            if vraie:
                return arete, lecture
        return None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] conditions illisibles : {erreur!r}")
        return None


# ---------------------------------------------------------------------------------------------------------
# Ce que le code sait de l'appel
# ---------------------------------------------------------------------------------------------------------


def la_personne_parle(moteur: Any) -> bool:
    """Un tour de la personne est ouvert (même signe que le moniteur d'appel). ⛔ Ne lève jamais."""
    try:
        return bool(getattr(getattr(moteur, "call_monitor", None), "appelant_parle", False))
    except Exception:  # noqa: BLE001
        return False


def un_outil_ou_un_travail_est_en_cours(moteur: Any) -> bool:
    """Un appel d'outil du cerveau de conversation ou un travail de fond est en cours. ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.sortie_d_impasse import _un_travail_est_en_cours

        llm = getattr(getattr(moteur, "active_agent", None), "llm", None)
        taches = getattr(llm, "_function_call_tasks", None)
        return bool(taches) or _un_travail_est_en_cours(moteur)
    except Exception:  # noqa: BLE001
        return False


def tracer(moteur: Any, **entree: Any) -> None:
    """Une ligne de plus dans ``passages_par_le_code``. ⛔ Ne lève jamais."""
    try:
        fiche = _fiche(moteur)
        fiche.setdefault(CLE_PASSAGES, []).append({"tour": fiche.get(CLE_TOUR), **entree})
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] trace non écrite : {erreur!r}")


# ---------------------------------------------------------------------------------------------------------
# Passer
# ---------------------------------------------------------------------------------------------------------


def _cible_sans_relance(moteur: Any, agent: Any, arete: Any) -> bool:
    """Option 2 : la porte mène-t-elle vers une étape qui n'est ni une fin, ni un retour au principal, ni un transfert
    garanti ? Sinon l'option 1 joue."""
    from api.services.groupe.passations import est_une_etape_de_retour

    cible = agent.workflow.nodes[arete.target]
    if cible.is_end or est_une_etape_de_retour(cible) or getattr(cible, "retour_au_principal", False):
        return False
    return not moteur._transfert_garanti_s_applique(agent, arete.target)


async def passer(
    moteur: Any,
    arete: Any,
    *,
    raison: str,
    jeton: tuple,
    dit: str = "",
    lecture: dict | None = None,
    option: int = 1,
    detail: dict | None = None,
) -> bool:
    """Prend la porte ``arete`` par le code. Refuse (et le trace) si la visite d'étape n'est plus celle où la décision
    est née, ou si la personne parle. Option 1 : l'étape d'arrivée reparle (``relancer``), avec la notice d'un tour.
    Option 2 : avant la requête de l'agent, sans relance. Rend ``True`` si la porte est prise. ⛔ Ne lève jamais."""
    try:
        agent = moteur.active_agent
        noeud = agent.current_node
        base = {
            "etape": getattr(noeud, "name", None),
            "porte": arete.get_function_name(),
            "vers": getattr(agent.workflow.nodes.get(arete.target), "name", None),
            "raison": raison,
            "option": option,
            "condition": lecture,
            **(detail or {}),
        }
        if jeton != moteur.jeton_de_visite():
            tracer(moteur, **base, resultat="jetee_autre_visite")
            return False
        if la_personne_parle(moteur):
            tracer(moteur, **base, resultat="jetee_la_personne_parle")
            return False
        if not moteur.agent_can_act(agent) or moteur.transfer_coordinator.in_progress:
            tracer(moteur, **base, resultat="jetee_appel_occupe")
            return False
        relancer = option == 1

        async def prendre() -> bool:
            if relancer:
                cible = agent.workflow.nodes.get(arete.target)
                poser_la_notice(moteur, agent, dit, (agent.visit_id, getattr(cible, "id", arete.target)))
            etat = await moteur.prendre_porte_ecrite(arete.get_function_name(), relancer=relancer)
            if etat != "prise":
                _vider_la_notice(moteur)
            tracer(moteur, **base, resultat="prise" if etat == "prise" else etat)
            return etat == "prise"

        # Le passage lui-même (changement d'étape, extraction) n'est jamais coupé par une interruption : il va
        # jusqu'au bout dans sa tâche (comme ``_porte_protegee``). Seule l'attente du greffier, avant, est interruptible.
        tache = asyncio.get_running_loop().create_task(prendre())
        taches = getattr(moteur, "notes_en_cours", None)
        if taches is not None:
            taches.add(tache)
            tache.add_done_callback(taches.discard)
        return await asyncio.shield(tache)
    except Exception as erreur:  # noqa: BLE001 -- l'agent garde la main
        logger.error(f"[passage] passage par le code en échec : {erreur!r}")
        _vider_la_notice(moteur)
        return False


# ---------------------------------------------------------------------------------------------------------
# Avant la requête du cerveau de conversation : notice d'un tour, option 2
#
# Ni crochet ni méthode d'une famille de fournisseurs : ces deux fonctions ne lisent que le contexte partagé de Pipecat
# (``LLMContext``). Elles sont appelées par le processeur de trames posé autour du cerveau
# (``pipecat/avant_la_requete.py``), au téléphone et au clavier, quel que soit le service (décision d'Evan, 29/10).
# ---------------------------------------------------------------------------------------------------------


def _vider_la_notice(moteur: Any) -> None:
    """Plus de notice en attente. ⛔ Ne lève jamais."""
    try:
        moteur._notice_de_passage = None
        moteur._notice_cle = None
    except Exception:  # noqa: BLE001
        pass


def poser_la_notice(moteur: Any, agent: Any, dit: str, arrivee: tuple | None = None) -> None:
    """La notice du tour d'arrivée : le compte rendu standard, montré sur la prochaine requête de conversation.
    ``arrivee`` = (visite de l'agent, étape d'arrivée) : à la consommation, une notice dont l'étape n'est plus celle
    où l'on est (retour au principal, autre passage) est jetée, jamais montrée plus tard."""
    from api.services.phrases.compte_rendu import compte_rendu

    moteur._notice_de_passage = compte_rendu(FAIT_DU_PASSAGE, dit=(dit or "").strip() or None, crochets=True)
    moteur._notice_cle = arrivee


def _inserer_avant_la_derniere_parole(messages: list, texte: str) -> list | None:
    """Une COPIE de ``messages`` avec ``texte`` juste avant la dernière parole de la personne (même place que l'état de
    la fiche, ``inserer_l_etat``) ; ``None`` sans parole de la personne. Les messages propres à un fournisseur (objets,
    non dictionnaires) sont laissés tels quels."""
    from api.services.groupe.passations import est_la_note_de_passation

    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user" and not est_la_note_de_passation(m):
            return [*messages[:i], {"role": "user", "content": texte}, *messages[i:]]
    return None


def contexte_avec_la_notice(moteur: Any, context: Any) -> Any | None:
    """La notice d'un tour, consommée : une COPIE du contexte avec la notice, pour CETTE requête seulement ; le contexte
    partagé (l'historique) n'est pas touché. ``None`` sans notice en attente. ⛔ Ne lève jamais."""
    try:
        notice = getattr(moteur, "_notice_de_passage", None)
        if not notice:
            return None
        cle = getattr(moteur, "_notice_cle", None)
        _vider_la_notice(moteur)
        if cle is not None:
            courant = moteur.jeton_de_visite()
            if (courant[0], courant[1]) != tuple(cle):
                logger.info("[passage] notice jetée : l'étape d'arrivée n'est plus celle-ci")
                return None
        messages = _inserer_avant_la_derniere_parole(list(context.get_messages()), notice)
        if messages is None:
            return None
        from pipecat.processors.aggregators.llm_context import LLMContext

        return LLMContext(messages=messages, tools=context.tools, tool_choice=context.tool_choice)
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[passage] notice non montrée : {erreur!r}")
        return None


def agent_reclame_le_code(agent: Any) -> bool:
    """L'agent a au moins une étape qui réclame le code (conditions sur la fiche ou arbitre). Sinon rien n'est posé
    autour de son cerveau. ⛔ Ne lève jamais."""
    try:
        noeuds = getattr(getattr(agent, "workflow", None), "nodes", None) or {}
        return any(l_etape_reclame_le_code(n) for n in noeuds.values())
    except Exception:  # noqa: BLE001
        return False


def _derniere_parole_de_la_personne(context: Any) -> bool:
    """La requête répond à la personne (et non à un résultat d'outil ou à une relance) : son dernier message est le sien."""
    from api.services.groupe.passations import est_la_note_de_passation, est_un_resultat_de_travail

    messages = list(context.get_messages()) if hasattr(context, "get_messages") else []
    if not messages:
        return False
    dernier = messages[-1]
    return (
        isinstance(dernier, dict)
        and dernier.get("role") == "user"
        and not est_un_resultat_de_travail(dernier)
        and not est_la_note_de_passation(dernier)
    )


async def avant_la_requete(moteur: Any, llm: Any, context: Any) -> bool:
    """L'option 2, juste avant la requête de l'agent. Étape réglée « attendre le dernier champ » : un seul champ manque ;
    la requête attend la passe du greffier sur la dernière parole (au plus le délai de l'étape) ; si une condition devient
    vraie, le passage a lieu avant que l'agent parle. Délai dépassé, vers une fin, un retour ou un transfert garanti,
    la personne qui parle : rien, l'option 1 jouera. Rend ``True`` si la porte a été prise. ⛔ Ne lève jamais."""
    try:
        agent = moteur.active_agent
        if getattr(agent, "llm", None) is not llm:
            return False
        noeud = agent.current_node
        r = reglages_du_passage(noeud)
        greffier = getattr(moteur, "greffier", None)
        if not r.option_2 or greffier is None or getattr(noeud, "is_end", False):
            return False
        if la_personne_parle(moteur) or not _derniere_parole_de_la_personne(context):
            return False
        reglages = getattr(moteur, "_fiche", None)
        fiche = _fiche(moteur)
        if reglages is None:
            return False
        from api.services.fiche.traces import valeurs_des_traces
        from api.services.groupe.notes import champs_attendus
        from api.services.workflow.champs_conditionnels import champs_actifs

        manque = champs_attendus(
            reglages, fiche, champs_actifs(noeud, fiche), valeurs_des_traces(reglages, fiche)
        )
        if len(manque) != 1:
            return False
        jeton = moteur.jeton_de_visite()
        if not await greffier.rattraper(r.delai):
            tracer(moteur, etape=getattr(noeud, "name", None), option=2, resultat="delai_option_1_jouera", raison=RAISON_FICHE)
            return False
        if jeton != moteur.jeton_de_visite() or la_personne_parle(moteur):
            return False
        trouvee = porte_a_prendre_sur_la_fiche(moteur, noeud)
        if trouvee is None:
            return False
        arete, lecture = trouvee
        if not _cible_sans_relance(moteur, agent, arete):
            return False
        return await passer(moteur, arete, raison=RAISON_FICHE, jeton=jeton, lecture=lecture, option=2)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[passage] option 2 non jouée : {erreur!r}")
        return False
