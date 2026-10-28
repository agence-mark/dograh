"""[.mark] passages-fiables (R3) : le décideur unique de fin de tour.

Quatre choses regardaient la même fin de réponse de l'agent et pouvaient prendre une porte : le filet de fin, la
sortie d'impasse, et maintenant le passage sur la fiche (lot A) et l'arbitre (lot B). Un seul module les ordonne : le
premier qui prend une porte gagne, **une seule porte par tour**. Branché à la place de ``brancher_le_filet_de_fin`` et
de ``brancher_la_sortie_d_impasse``, au téléphone (``run_pipeline.py``) **et** au clavier (``text_chat_runner.py``).

    fin de la réponse de l'agent (téléphone ET clavier)
            │
            ├─ attendre les portes en cours (post-scriptum, tâches de porte du moteur), bornée
            ├─ la personne parle déjà ? ─────────────── oui → rien de nouveau (on revoit au tour suivant)
            ├─ outil ou travail de fond en cours ? ──── oui → rien de nouveau
            │
            ├─ 1. l'agent a écrit/appelé sa porte ────── oui (l'étape a changé depuis le début de la réplique) → STOP
            ├─ 2. filet de fin (au revoir sans porte) ── oui → sortie retour (existant, déplacé, inchangé), STOP
            ├─ 3. condition sur la fiche vraie ? ─────── attend la passe du greffier de CETTE parole (bornée)
            │      (étape complète, champ = valeur,        oui → prendre_porte_ecrite(porte, relancer=True), STOP
            │       ordre de l'écran, rien « à confirmer »)
            ├─ 4. arbitre : choix ≠ « rester », ──────── oui → prendre_porte_ecrite(choix, relancer=True), STOP
            │      confiance ≥ seuil, même visite
            ├─ 5. sortie d'impasse : les signes se comptent à chaque tour comme avant ; la sortie ne joue que si
            │      rien n'a été pris plus haut
            └─ sinon ─────────────────────────────────── l'agent garde la main (comme avant)

    option 2 (collecte, un seul champ manquant) : la requête de l'agent attend la passe (bornée) ; condition vraie →
    passage AVANT que l'agent parle ; délai dépassé → option 1 (``passage_sur_la_fiche.avant_la_requete``).

Toute décision est liée à la **visite d'étape** où elle est née (``engine.jeton_de_visite()`` : visite de l'agent,
étape, rang d'entrée) : autre jeton, elle est jetée et tracée. Une étape en mode ``agent`` sans arbitre (le défaut) ne
fait rien de plus que le filet puis l'impasse : comportement d'avant.

Aucun mot de métier. ⛔ Ne lève jamais.
"""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

from loguru import logger

from api.services.groupe.passations import est_la_note_de_passation, est_un_resultat_de_travail
from api.services.workflow import arbitre as arbitre_mod
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.sortie_d_impasse import fin_de_la_replique

# L'attente des portes en cours avant de décider (téléphone : une porte dite en fin de réponse est prise dans une tâche).
DELAI_DES_PORTES = 1.5


async def attendre_les_portes(moteur: Any, delai: float = DELAI_DES_PORTES) -> None:
    """Laisse finir les portes en cours : celles du post-scriptum, puis les tâches de porte du moteur. Bornée. ⛔ Ne lève jamais."""
    try:
        await asyncio.sleep(0)
        taches: set[asyncio.Task] = set(getattr(moteur, "_taches_de_porte", None) or ())
        for lot in getattr(moteur, "portes_du_post_scriptum", None) or ():
            taches |= set(lot)
        if taches:
            await asyncio.wait(taches, timeout=delai)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] attente des portes en échec : {erreur!r}")


async def _fiche_puis_arbitre(moteur: Any, texte: str, jeton: tuple) -> str | None:
    """Les étapes 3 et 4. Rend ``fiche`` ou ``arbitre`` si une porte a été prise, sinon ``None``."""
    agent = moteur.active_agent
    noeud = agent.current_node
    if noeud is None or getattr(noeud, "is_end", False) or moteur.is_call_disposed():
        return None
    r = passage.reglages_du_passage(noeud)
    if not (r.le_code_lit_la_fiche or r.arbitre):
        return None
    if jeton != moteur.jeton_de_visite():
        return None
    if passage.la_personne_parle(moteur) or passage.un_outil_ou_un_travail_est_en_cours(moteur):
        return None
    # 3. Les conditions sur la fiche.
    if passage.portes_a_condition(noeud):
        lue_a_temps = True
        greffier = getattr(moteur, "greffier", None)
        if greffier is not None:
            lue_a_temps = await greffier.rattraper(r.delai)
            if not lue_a_temps:
                passage.tracer(
                    moteur,
                    etape=getattr(noeud, "name", None),
                    raison=passage.RAISON_FICHE,
                    resultat="greffier_sans_reponse",
                )
        if lue_a_temps:
            if jeton != moteur.jeton_de_visite() or passage.la_personne_parle(moteur):
                return None
            trouvee = passage.porte_a_prendre_sur_la_fiche(moteur, noeud)
            if trouvee is not None:
                arete, lecture = trouvee
                if await passage.passer(
                    moteur, arete, raison=passage.RAISON_FICHE, jeton=jeton, dit=texte, lecture=lecture
                ):
                    return passage.RAISON_FICHE
                return None
    # 4. L'arbitre.
    if not r.arbitre:
        return None
    arbitre = getattr(moteur, "arbitre", None)
    if arbitre is None:
        return None
    decision = await arbitre.resultat(jeton)
    arbitre.oublier()
    if decision is None:
        return None
    ligne = {
        "etape": getattr(noeud, "name", None),
        "choix": decision.choix,
        "confiance": decision.confiance,
        "etat": decision.etat,
        "seuil": r.seuil,
        "duree": decision.duree,
        **decision.jetons,
    }
    if jeton != moteur.jeton_de_visite() or passage.la_personne_parle(moteur):
        arbitre_mod.tracer(moteur, **ligne, resultat="jetee")
        return None
    if not decision.veut_passer:
        arbitre_mod.tracer(moteur, **ligne, resultat="rien" if decision.etat == arbitre_mod.ETAT_OK else decision.etat)
        return None
    if decision.confiance < r.seuil:
        arbitre_mod.tracer(moteur, **ligne, resultat="sous_le_seuil")
        return None
    arete = moteur._porte_de_l_etape(decision.choix)
    if arete is None:
        arbitre_mod.tracer(moteur, **ligne, resultat="porte_inconnue")
        return None
    prise = await passage.passer(
        moteur,
        arete,
        raison=passage.RAISON_ARBITRE,
        jeton=jeton,
        dit=texte,
        detail={"confiance": decision.confiance},
    )
    arbitre_mod.tracer(moteur, **ligne, resultat="prise" if prise else "refusee")
    return passage.RAISON_ARBITRE if prise else None


async def _noter_le_desaccord(moteur: Any, jeton_debut: tuple | None, depart: tuple | None) -> None:
    """L'agent a pris une porte pendant sa réponse : l'arbitre (s'il a répondu à propos de la même étape) était-il
    d'accord ? Le désaccord est tracé, il nourrit la file de tri (lot G). ⛔ Ne lève jamais."""
    try:
        arbitre = getattr(moteur, "arbitre", None)
        if arbitre is None or jeton_debut is None:
            return
        decision = await arbitre.resultat(jeton_debut)
        arbitre.oublier()
        if decision is None or not decision.veut_passer:
            return
        agent = moteur.active_agent
        graphe_avant = agent.workflow.nodes
        vers = None
        for noeud in graphe_avant.values():
            if noeud.id == jeton_debut[1]:
                arete = next((e for e in noeud.out_edges if e.get_function_name() == decision.choix), None)
                vers = arete.target if arete is not None else None
        if vers is not None and vers != getattr(agent.current_node, "id", None):
            arbitre_mod.tracer_un_desaccord(
                moteur,
                etape_de_depart=jeton_debut[1],
                arbitre=decision.choix,
                confiance=decision.confiance,
                agent_arrive_a=getattr(agent.current_node, "name", None),
            )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] désaccord non noté : {erreur!r}")


async def decider(moteur: Any, texte: str, depart: tuple | None, jeton: tuple | None) -> str | None:
    """La fin d'une réplique de l'agent. Rend qui a pris une porte : ``filet``, ``fiche``, ``arbitre``, ``impasse``, ou
    ``None``. ⛔ Ne lève jamais."""
    prise: str | None = None
    try:
        await attendre_les_portes(moteur)
        agent_a_pris = depart is not None and depart != moteur.etat_pour_le_filet()
        # 2. Le filet de fin (existant, inchangé : il a ses propres gardes).
        if await moteur.filet_de_fin(texte, depart):
            prise = "filet"
        elif agent_a_pris:
            # 1. L'agent a pris sa porte : le code ne passe jamais par-dessus ; l'arbitre en désaccord est tracé.
            await _noter_le_desaccord(moteur, jeton, depart)
        elif jeton is not None:
            prise = await _fiche_puis_arbitre(moteur, texte, jeton)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] décision en échec : {erreur!r}")
    # 5. L'impasse : ses signes se comptent à chaque tour ; sa sortie ne joue que si rien n'a été pris.
    try:
        if await fin_de_la_replique(moteur, texte, depart, sortie_permise=prise is None):
            prise = prise or "impasse"
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] impasse en échec : {erreur!r}")
    return prise


def _brancher_l_arbitre_a_la_conversation(engine: Any) -> None:
    """Quand une réplique de la personne entre dans la conversation (fin de sa parole), l'arbitre part en parallèle de la
    passe du greffier, jamais en l'attendant. Même point d'accroche que le greffier (``declencher_a_la_conversation``).
    Hors étape qui l'allume, rien ne part. ⛔ Ne lève jamais."""
    try:
        contexte = getattr(engine, "context", None)
        ajouter = getattr(contexte, "add_message", None)
        ajouter_plusieurs = getattr(contexte, "add_messages", None)
        if ajouter is None or ajouter_plusieurs is None:
            return
        if getattr(contexte, "_mark_arbitre_branche", False):
            return

        def apres(messages: Iterable[Any]) -> None:
            try:
                if not any(
                    isinstance(m, dict)
                    and m.get("role") == "user"
                    and not est_un_resultat_de_travail(m)
                    and not est_la_note_de_passation(m)
                    for m in messages
                ):
                    return
                noeud = engine.active_agent.current_node
                r = passage.reglages_du_passage(noeud)
                arbitre = getattr(engine, "arbitre", None)
                if arbitre is None or not r.arbitre or getattr(noeud, "is_end", False):
                    return
                arbitre.lancer(
                    engine.jeton_de_visite(),
                    noeud,
                    engine.context.get_messages(),
                    delai=arbitre_mod.DELAI_PAR_DEFAUT,
                )
            except Exception as erreur:  # noqa: BLE001 -- jamais l'appel
                logger.error(f"[arbitre] non déclenché : {erreur!r}")

        def add_message(message, *args, **kwargs):
            resultat = ajouter(message, *args, **kwargs)
            apres([message])
            return resultat

        def add_messages(messages, *args, **kwargs):
            messages = list(messages)
            resultat = ajouter_plusieurs(messages, *args, **kwargs)
            apres(messages)
            return resultat

        contexte.add_message = add_message
        contexte.add_messages = add_messages
        contexte._mark_arbitre_branche = True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[arbitre] non branché à la conversation : {erreur!r}")


def brancher_le_decideur_de_fin_de_tour(engine: Any, assistant_aggregator: Any) -> None:
    """Branche le décideur sur l'agrégateur de l'assistant : au début d'une réplique, l'étape où l'on est et son jeton ; à
    sa fin, ``decider``. Remplace ``brancher_le_filet_de_fin`` et ``brancher_la_sortie_d_impasse``. Téléphone et
    clavier. ⛔ Ne lève jamais."""
    try:
        if getattr(engine, "arbitre", None) is None:
            engine.arbitre = arbitre_mod.ArbitreDuPassage(engine)
        _brancher_l_arbitre_a_la_conversation(engine)
        depart: dict[str, Any] = {}

        @assistant_aggregator.event_handler("on_assistant_turn_started")
        async def _debut(_aggregator):
            try:
                depart["etat"] = engine.etat_pour_le_filet()
                depart["jeton"] = engine.jeton_de_visite()
            except Exception:  # noqa: BLE001
                depart["etat"], depart["jeton"] = None, None

        @assistant_aggregator.event_handler("on_assistant_turn_stopped")
        async def _fin(_aggregator, message):
            try:
                await decider(
                    engine,
                    getattr(message, "content", None) or "",
                    depart.pop("etat", None),
                    depart.pop("jeton", None),
                )
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[decideur] fin de réplique non traitée : {erreur!r}")

    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] non branché : {erreur!r}")
