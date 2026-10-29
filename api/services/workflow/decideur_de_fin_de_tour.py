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
            ├─ la réplique pose une question ? ───────── oui → rien ce tour-ci : la personne répond d'abord, la
            │      (rien reporté au tour d'avant)          décision se refait à la fin de la réplique suivante
            ├─ porte déjà prise avant la requête ? ───── oui → ni fiche ni sortie d'impasse : une porte par parole
            ├─ 3. condition sur la fiche vraie ? ─────── attend la passe du greffier de CETTE parole (bornée)
            │      (étape complète, champ = valeur,        oui → prendre_porte_ecrite(porte, relancer=True), STOP
            │       ordre de l'écran, rien « à confirmer »)
            ├─ 5. sortie d'impasse : les signes se comptent à chaque tour comme avant ; la sortie ne joue que si
            │      rien n'a été pris plus haut
            └─ sinon ─────────────────────────────────── l'agent garde la main (comme avant)

    AVANT la requête de l'agent, sur la parole de la personne (``pipecat/avant_la_requete.py``, trames et contexte
    partagé, n'importe quel cerveau) :

    parole de la personne → requête de l'agent
            ├─ option 2 (collecte, un seul champ manquant) : attend la passe du greffier (bornée) ; condition vraie →
            │      passage AVANT que l'agent parle ; délai dépassé → option 1 en fin de réplique
            │      (``passage_sur_la_fiche.avant_la_requete``)
            └─ 4. arbitre (étape où il est allumé) : attend sa décision sur CETTE parole, au plus le délai de l'étape
                   (``arbitre_avant_la_requete``) ; choix ≠ « rester », confiance ≥ seuil, même visite, personne
                   qui ne parle pas → passage AVANT que l'agent parle, l'étape d'arrivée répond directement ; au-delà
                   du délai, la requête part sans lui. Vers une fin, un retour au principal ou un transfert garanti :
                   laissé à l'agent (aucune porte prise par le code).

Décision d'Evan (29/10, après le rebanc) : l'arbitre ne passe plus à la fin de la réplique de l'agent. Appliqué là, il
arrivait après une réplique qui finissait presque toujours par une question : 74 décisions reportées sur 16 appels,
aucune porte passée ; et quand il passait, c'était sur une décision née de la parole d'avant (run 20). Avant la réponse,
la décision et la parole qu'elle juge sont les mêmes, et la question de l'agent n'existe pas encore. Une décision trop
lente n'est donc plus jamais appliquée plus tard : elle ne sert qu'à tracer un désaccord avec l'agent.

Toute décision est liée à la **visite d'étape** où elle est née (``engine.jeton_de_visite()`` : visite de l'agent,
étape, rang d'entrée) : autre jeton, elle est jetée et tracée. Une étape en mode ``agent`` sans arbitre (le défaut) ne
fait rien de plus que le filet puis l'impasse : comportement d'avant.

Latence (Evan, 29/10 : « ne pas ajouter de latence le temps de calculer ce qui s'est passé ») :

- le décideur tourne dans l'événement ``on_assistant_turn_stopped`` de l'agrégateur de l'assistant, enregistré par
  Pipecat SANS ``sync`` (``LLMAssistantAggregator.__init__``) : chaque gestionnaire part dans sa propre tâche, le
  circuit n'attend jamais la décision ;
- une étape qui ne réclame pas le code (le défaut) n'attend RIEN : ni les portes en cours, ni le greffier, ni l'arbitre
  (filet puis impasse, comme la base) ;
- quand il agit, la durée de la décision (``duree_decision``, en secondes, de la fin de la réplique au passage) est
  écrite dans ``passages_par_le_code`` ;
- l'arbitre AVANT la requête ajoute une attente à la réponse de l'agent : elle n'existe que sur une étape où l'arbitre
  est allumé, bornée par le délai de l'étape, et mesurée (``attente`` dans ``arbitre``, ``duree_decision`` dans
  ``passages_par_le_code``).

Une réplique qui pose une question attend une réponse (banc local du 29/10 : runs 19 et 27, passage pris juste après
« … c'est bien ça ? », la personne n'a pas pu confirmer ; run 20, l'arbitre a pris la fin juste après « autre chose ? »,
sur une décision née de la parole d'avant). Le code ne passe donc pas à la fin d'une telle réplique : la décision se
refait sur la réponse. Jamais deux tours de suite dans la même visite d'étape, pour qu'un agent qui pose la question de
l'étape suivante sans passer (passage sauté) soit quand même rattrapé au tour d'après.

Aucun mot de métier. ⛔ Ne lève jamais.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable

from loguru import logger

from api.services.fiche.traces import CLE_TOUR
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


def _l_etape_reclame_le_code(moteur: Any) -> bool:
    """L'étape où l'on est réclame le code (conditions sur la fiche ou arbitre). ⛔ Ne lève jamais (dans le doute : non)."""
    try:
        return passage.l_etape_reclame_le_code(moteur.active_agent.current_node)
    except Exception:  # noqa: BLE001
        return False


def _duree(debut: float) -> float:
    return round(time.monotonic() - debut, 3)


RAISON_QUESTION = "question"
RESULTAT_REPORTE = "reportee_question"
# Ce qui peut suivre le point d'interrogation sans changer le sens : espaces, guillemets, parenthèse fermante.
_APRES_LA_QUESTION = " \t\r\n\"'»”’)]*_"


def la_replique_pose_une_question(texte: str) -> bool:
    """La réplique de l'agent finit par une question."""
    return (texte or "").rstrip(_APRES_LA_QUESTION).endswith("?")


# Le report « une seule fois » vit dans la FICHE de l'appel, pas sur le moteur : au clavier le moteur est reconstruit à
# chaque tour (``text_chat_runner``), un attribut y repartirait à vide et chaque réplique en « ? » reporterait (D8,
# figeage-v12, run 161 : quatre reports de suite, l'étape de collecte ne passait jamais). Forme : ``{etape, tour}``.
CLE_REPORT = "passage_reporte"


def _tour_de_la_personne(moteur: Any) -> int | None:
    fiche = getattr(moteur, "_gathered_context", None)
    tour = fiche.get(CLE_TOUR) if isinstance(fiche, dict) else None
    return tour if isinstance(tour, int) and not isinstance(tour, bool) else None


def _deja_reporte(moteur: Any, etape: Any) -> bool:
    """Un report est rangé dans la fiche pour cette étape, au tour de la personne d'avant ou à celui-ci."""
    fiche = getattr(moteur, "_gathered_context", None)
    report = fiche.get(CLE_REPORT) if isinstance(fiche, dict) else None
    if not isinstance(report, dict) or report.get("etape") != etape:
        return False
    tour, tour_du_report = _tour_de_la_personne(moteur), report.get("tour")
    if tour is None or not isinstance(tour_du_report, int):
        return True
    return tour_du_report >= tour - 1


def _reporter_pour_la_question(moteur: Any, texte: str, jeton: tuple) -> bool:
    """La réplique pose une question et rien n'a été reporté au tour d'avant dans cette étape : la décision est reportée
    (``True``). Sinon le report est effacé et le code décide (``False``). Le report est rangé dans la fiche de l'appel
    (parité clavier / téléphone). ⛔ Ne lève jamais (dans le doute : le code décide)."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        if not isinstance(fiche, dict):
            return False
        etape = jeton[1] if len(jeton) > 1 else None
        if la_replique_pose_une_question(texte) and not _deja_reporte(moteur, etape):
            fiche[CLE_REPORT] = {"etape": etape, "tour": _tour_de_la_personne(moteur)}
            return True
        fiche.pop(CLE_REPORT, None)
        return False
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] report non rangé : {erreur!r}")
        return False


def _tracer_le_report(moteur: Any, noeud: Any, debut: float) -> None:
    """Le report, tracé."""
    passage.tracer(
        moteur, etape=getattr(noeud, "name", None), raison=RAISON_QUESTION, resultat=RESULTAT_REPORTE,
        duree_decision=_duree(debut),
    )


async def _la_fiche(moteur: Any, texte: str, jeton: tuple, debut: float | None = None) -> str | None:
    """L'étape 3 (l'arbitre décide avant la requête, ``arbitre_avant_la_requete``). Rend ``fiche`` si une porte a été
    prise, sinon ``None``."""
    debut = time.monotonic() if debut is None else debut
    agent = moteur.active_agent
    noeud = agent.current_node
    if noeud is None or getattr(noeud, "is_end", False) or moteur.is_call_disposed():
        return None
    r = passage.reglages_du_passage(noeud)
    if not r.le_code_lit_la_fiche:
        return None
    if jeton != moteur.jeton_de_visite():
        return None
    if passage.la_personne_parle(moteur) or passage.un_outil_ou_un_travail_est_en_cours(moteur):
        return None
    # Une réponse sans parole (appels d'outil seuls) : rien n'a été dit, la décision attend la réplique relancée.
    if not (texte or "").strip():
        return None
    # La réplique attend une réponse : rien ce tour-ci, la décision se refait sur la réponse.
    if _reporter_pour_la_question(moteur, texte, jeton):
        _tracer_le_report(moteur, noeud, debut)
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
                    duree_decision=_duree(debut),
                )
        if lue_a_temps:
            if jeton != moteur.jeton_de_visite() or passage.la_personne_parle(moteur):
                return None
            trouvee = passage.porte_a_prendre_sur_la_fiche(moteur, noeud)
            if trouvee is not None:
                arete, lecture = trouvee
                if await passage.passer(
                    moteur,
                    arete,
                    raison=passage.RAISON_FICHE,
                    jeton=jeton,
                    dit=texte,
                    lecture=lecture,
                    detail={"duree_decision": _duree(debut)},
                ):
                    return passage.RAISON_FICHE
                return None
    return None


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
    """La fin d'une réplique de l'agent. Rend qui a pris une porte : ``filet``, ``fiche``, ``impasse``, ou ``None``.
    ⛔ Ne lève jamais."""
    prise: str | None = None
    deja_prise = False
    debut = time.monotonic()
    try:
        # Seule une étape qui réclame le code attend les portes en cours ; sinon rien n'est attendu (comme la base).
        if _l_etape_reclame_le_code(moteur):
            await attendre_les_portes(moteur)
        agent_a_pris = depart is not None and depart != moteur.etat_pour_le_filet()
        # 2. Le filet de fin (existant, inchangé : il a ses propres gardes).
        if await moteur.filet_de_fin(texte, depart):
            prise = "filet"
        elif agent_a_pris:
            # 1. L'agent a pris sa porte : le code ne passe jamais par-dessus ; l'arbitre en désaccord est tracé.
            await _noter_le_desaccord(moteur, jeton, depart)
        elif jeton is not None and passage.porte_prise_avant_la_requete(moteur, jeton):
            # Une porte a déjà été prise sur cette parole, avant la requête : une seule porte par parole.
            deja_prise = True
        elif jeton is not None:
            prise = await _la_fiche(moteur, texte, jeton, debut)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] décision en échec : {erreur!r}")
    # 5. L'impasse : ses signes se comptent à chaque tour ; sa sortie ne joue que si rien n'a été pris.
    try:
        if await fin_de_la_replique(moteur, texte, depart, sortie_permise=prise is None and not deja_prise):
            prise = prise or "impasse"
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[decideur] impasse en échec : {erreur!r}")
    return prise


MOMENT_AVANT = "avant_la_reponse"


async def arbitre_avant_la_requete(moteur: Any, llm: Any, context: Any, *, depart: float | None = None) -> bool:
    """L'arbitre, juste avant la requête de l'agent qui répond à la personne : attend sa décision sur CETTE parole (au
    plus le délai de l'étape) ; sûre et ≠ « rester » : passage AVANT que la requête parte, l'étape d'arrivée répond
    directement (sans relance, comme l'option 2). Vers une fin, un retour au principal ou un transfert garanti : laissé
    à l'agent. ``depart`` : l'instant où la préparation de la requête a commencé (l'option 2 a pu déjà attendre) ; au total la
    requête n'attend jamais plus que le délai de l'étape. Rend ``True`` si la porte a été prise. ⛔ Ne lève jamais (sauf
    l'annulation, propagée)."""
    try:
        agent = moteur.active_agent
        if getattr(agent, "llm", None) is not llm:
            return False
        noeud = agent.current_node
        if noeud is None or getattr(noeud, "is_end", False) or moteur.is_call_disposed():
            return False
        r = passage.reglages_du_passage(noeud)
        arbitre = getattr(moteur, "arbitre", None)
        if not r.arbitre or arbitre is None:
            return False
        if passage.la_personne_parle(moteur) or not passage._derniere_parole_de_la_personne(context):
            return False
        jeton = moteur.jeton_de_visite()
        debut = time.monotonic()
        origine = debut if depart is None else depart
        decision, demandee = await arbitre.attendre(jeton, max(0.0, r.delai - (debut - origine)))
        attente = _duree(debut)
        if decision is None:
            if demandee:
                arbitre_mod.tracer(
                    moteur, etape=getattr(noeud, "name", None), moment=MOMENT_AVANT, resultat="trop_lent",
                    attente=attente, seuil=r.seuil,
                )
            return False
        ligne = {
            "etape": getattr(noeud, "name", None),
            "moment": MOMENT_AVANT,
            "choix": decision.choix,
            "confiance": decision.confiance,
            "etat": decision.etat,
            "seuil": r.seuil,
            "duree": decision.duree,
            "attente": attente,
            **({"temps": decision.temps} if decision.temps is not None else {}),
            **decision.jetons,
        }
        if jeton != moteur.jeton_de_visite() or passage.la_personne_parle(moteur):
            arbitre_mod.tracer(moteur, **ligne, resultat="jetee")
            return False
        if not decision.veut_passer:
            arbitre_mod.tracer(moteur, **ligne, resultat="rien" if decision.etat == arbitre_mod.ETAT_OK else decision.etat)
            return False
        if decision.confiance < r.seuil:
            arbitre_mod.tracer(moteur, **ligne, resultat="sous_le_seuil")
            return False
        arete = moteur._porte_de_l_etape(decision.choix)
        if arete is None:
            arbitre_mod.tracer(moteur, **ligne, resultat="porte_inconnue")
            return False
        # La fiche d'abord (ordre du décideur) : une condition sur la fiche déjà vraie, lue sur CETTE parole dans le
        # même délai, garde la main ; elle se prend à la fin de la réplique, comme avant.
        if passage.portes_a_condition(noeud):
            greffier = getattr(moteur, "greffier", None)
            reste = max(0.0, r.delai - (time.monotonic() - origine))
            lue = True if greffier is None else await greffier.rattraper(reste)
            trouvee = passage.porte_a_prendre_sur_la_fiche(moteur, noeud) if lue else None
            if trouvee is not None:
                # D7 : la fiche garde la main, et elle passe AVANT la requête (sans relance) quand la cible le permet ;
                # sinon (fin, retour au principal, transfert garanti) elle se prend à la fin de la réplique, comme avant.
                fiche_arete, lecture = trouvee
                if jeton == moteur.jeton_de_visite() and passage._cible_sans_relance(moteur, agent, fiche_arete):
                    prise = await passage.passer(
                        moteur, fiche_arete, raison=passage.RAISON_FICHE, jeton=jeton, lecture=lecture, option=2,
                        detail={"duree_decision": _duree(origine)},
                    )
                    if prise:
                        arbitre.oublier()
                    arbitre_mod.tracer(moteur, **ligne, resultat="fiche_avant_la_requete" if prise else "fiche_refusee")
                    return prise
                arbitre_mod.tracer(moteur, **ligne, resultat="fiche_d_abord")
                return False
            if jeton != moteur.jeton_de_visite() or passage.la_personne_parle(moteur):
                arbitre_mod.tracer(moteur, **ligne, resultat="jetee")
                return False
        if not passage._cible_sans_relance(moteur, agent, arete):
            # Une fin, un retour au principal, un transfert garanti : ils ne se prennent pas avant la réponse ; et à la
            # fin de la réplique, la réponse a déjà posé sa question (run 20). L'agent garde sa porte.
            arbitre_mod.tracer(moteur, **ligne, resultat="laissee_a_l_agent")
            return False
        prise = await passage.passer(
            moteur,
            arete,
            raison=passage.RAISON_ARBITRE,
            jeton=jeton,
            option=2,
            detail={"confiance": decision.confiance, "duree_decision": attente},
        )
        if prise:
            arbitre.oublier()
        arbitre_mod.tracer(moteur, **ligne, resultat="prise" if prise else "refusee")
        return prise
    except asyncio.CancelledError:
        raise
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[arbitre] décision avant la requête en échec : {erreur!r}")
        return False


def _brancher_l_arbitre_a_la_conversation(engine: Any) -> None:
    """Quand une réplique de la personne entre dans la conversation (fin de sa parole), l'arbitre part en parallèle de la
    passe du greffier, jamais en l'attendant. Même point d'accroche que le greffier (``declencher_a_la_conversation``).
    Questions posées : le passage sur une étape qui l'allume, le temps quand la case « Laisser l'appelant prendre son
    temps » est allumée ; ni l'un ni l'autre, rien ne part. ⛔ Ne lève jamais."""
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
                from api.services.workflow.laisser_la_parole import case_allumee

                noeud = engine.active_agent.current_node
                r = passage.reglages_du_passage(noeud)
                arbitre = getattr(engine, "arbitre", None)
                if arbitre is None or noeud is None or getattr(noeud, "is_end", False):
                    return
                temps = case_allumee(engine.active_agent, engine)
                if not (r.arbitre or temps):
                    return
                arbitre.lancer(
                    engine.jeton_de_visite(),
                    noeud,
                    engine.context.get_messages(),
                    delai=arbitre_mod.DELAI_PAR_DEFAUT,
                    portes=r.arbitre,
                    temps=temps,
                    seuil_du_temps=r.seuil,
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


def brancher_le_decideur_de_fin_de_tour(engine: Any, assistant_aggregator: Any, service_arbitre: Any = None) -> None:
    """Branche le décideur sur l'agrégateur de l'assistant : au début d'une réplique, l'étape où l'on est et son jeton ; à
    sa fin, ``decider``. Remplace ``brancher_le_filet_de_fin`` et ``brancher_la_sortie_d_impasse``. Téléphone et
    clavier. ⛔ Ne lève jamais."""
    try:
        if service_arbitre is not None:
            # Le cerveau propre de l'arbitre (``arbitre_llm``) ; absent : le greffier, sinon la conversation.
            engine.arbitre_service = service_arbitre
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
