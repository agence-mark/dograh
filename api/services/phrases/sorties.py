"""[.mark] Chantier correctifs-apres-banc-v4 (lot 4, 4.5) : exécuter la sortie d'une règle (« Ensuite »).

Une sortie se compose de trois éléments facultatifs, toujours dans cet ordre : **dire** une phrase de
sortie (par le diseur : verrous, variantes, trace), **noter dans la fiche** un champ et une valeur de
sa liste (par le point d'écriture unique de la fiche, refus de l'illisible compris), puis une **action
finale** : continuer, laisser le modèle reprendre, transférer à une personne de l'équipe, raccrocher.

Le code ne pilote pas la conversation : il dit une phrase de sortie, il tient la fiche, il transfère ou
raccroche seulement quand la règle le demande. Rien de métier ici : le champ, la valeur, la destination
et les mots sont des données de la règle.

⛔ Ne lève jamais : une sortie qui échoue est journalisée et rendue dans ``IssueDeSortie`` (le modèle
reprend alors la main, jamais un silence définitif).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.schemas.phrases_du_code import (
    ACTION_CONTINUER,
    ACTION_MODELE,
    ACTION_ALLER_A_UNE_ETAPE,
    ACTION_RACCROCHER,
    ACTION_RENDRE_LA_MAIN,
    ACTION_TRANSFERER,
)
from api.services.phrases.regles import PhraseResolue

# Le temps laissé à une phrase de sortie pour finir avant de raccrocher ou de transférer.
ATTENTE_MAX_PHRASE_S = 20.0
# Posé sur le moteur dès qu'une sortie « transférer » part : aucune autre n'y entre dans cet appel.
DRAPEAU_TRANSFERT = "_sortie_de_transfert_en_cours"


@dataclass
class IssueDeSortie:
    """Ce que la sortie a fait : le compte rendu du modèle (et la trace) le lisent."""

    action: str = ACTION_MODELE
    dit: str | None = None
    notes: list[str] = field(default_factory=list)
    # Ce qui n'est plus possible après la sortie (ex. : transférer), pour le compte rendu.
    interdit: list[str] = field(default_factory=list)
    # La sortie a-t-elle pris l'appel en main (transfert lancé, appel raccroché) ?
    prise_en_main: bool = False
    erreurs: list[str] = field(default_factory=list)
    # L'action finale (transférer, raccrocher) d'une sortie lancée PENDANT un appel de fonction : elle
    # ne s'attend jamais dans l'échéance de l'appel, elle part en tâche détachée après la remise du
    # résultat (``lancer_apres``). ``None`` : rien à faire après.
    apres: Any = None

    @property
    def le_modele_reprend(self) -> bool:
        return not self.prise_en_main and self.action in (ACTION_MODELE, ACTION_CONTINUER)


def _noter_dans_la_fiche(moteur: Any, phrase: PhraseResolue, issue: IssueDeSortie) -> None:
    note = phrase.ensuite.noter
    if note is None:
        return
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if reglages is None or not isinstance(fiche, dict):
            issue.erreurs.append("pas de fiche dans cet appel")
            logger.info(f"[sortie] note {note.champ} : pas de fiche, non écrite")
            return
        from api.services.workflow.fiche_au_fil_de_leau import SOURCE_ACTION, ecrire_dans_la_fiche

        verdict = ecrire_dans_la_fiche(fiche, reglages, note.champ, note.valeur, source=SOURCE_ACTION)
        logger.info(f"[sortie] {note.champ} : {verdict.statut} ({verdict.raison})")
        if verdict.statut == "ecrit":
            issue.notes.append(f"{note.champ} = {verdict.valeur}")
        else:
            issue.erreurs.append(f"{note.champ} non écrit ({verdict.raison})")
    except Exception as erreur:  # noqa: BLE001
        issue.erreurs.append(f"{note.champ} non écrit")
        logger.warning(f"[sortie] note non écrite : {erreur!r}")


async def _attendre_la_phrase(moteur: Any, parole: Any) -> None:
    if parole is None:
        return
    try:
        await asyncio.wait_for(parole.wait(), timeout=ATTENTE_MAX_PHRASE_S)
        drain = getattr(moteur, "drain_call_pipeline", None)
        if drain is not None and getattr(moteur, "sans_sortie_audio", False) is not True:
            await drain()
    except Exception as erreur:  # noqa: BLE001
        logger.debug(f"[sortie] fin de phrase illisible : {erreur!r}")


async def transferer_a(moteur: Any, destination: str) -> tuple[bool, str | None]:
    """Transfère l'appel à la personne de l'équipe ``destination`` (sa clé, dans la liste fermée de
    l'appel), par le gestionnaire de transfert d'appel de Dograh : même chemin téléphone, même transfert
    simulé en essai, même trace du renvoi. ``(lancé, raison)`` : ``lancé`` faux si rien n'est parti.
    ⛔ Ne lève jamais."""
    try:
        from api.services.equipe.appel import cles_de_lappel
        from api.services.equipe.diriger import personne_de_la_copie

        manager = getattr(moteur, "_custom_tool_manager", None)
        if manager is None:
            return False, "pas de gestionnaire de transfert dans cet appel"
        contexte = getattr(moteur, "_call_context_vars", None) or {}
        cles, etablissement = cles_de_lappel(contexte)
        if destination not in cles:
            return False, "destination hors de la liste de l'équipe"
        organisation = await manager.get_organization_id()
        personne = await personne_de_la_copie(organisation, destination, etablissement) if organisation else None
        if personne is None or not (personne.joignable_par_transfert and personne.telephone):
            return False, "personne non joignable par transfert"
        outil = SimpleNamespace(
            tool_uuid=None,
            name="sortie_transfert",
            category="transfer_call",
            cible_transfert_humain=f"personne:{personne.cle}",
            definition={
                "type": "transfer_call",
                "config": {
                    "destination_source": "static",
                    "destination": personne.telephone,
                    "timeout": 30,
                    "messageType": "none",
                },
            },
        )
        rendu: dict[str, Any] = {}

        async def au_resultat(resultat: Any, *args: Any, **kwargs: Any) -> None:
            rendu["resultat"] = resultat

        params = SimpleNamespace(arguments={}, result_callback=au_resultat, llm=None, tool_call_id=None)
        from api.services.tests_rejouables.simulation import simuler_si_rejeu

        # Au rejeu d'un test, le transfert est simulé (rien ne part) ; hors rejeu, le gestionnaire tel quel.
        gestionnaire = simuler_si_rejeu(
            moteur, "transfer_call", "sortie_transfert", manager._create_transfer_call_handler(outil, "sortie_transfert")
        )
        await gestionnaire(params)
        statut = (rendu.get("resultat") or {}).get("status") if isinstance(rendu.get("resultat"), dict) else None
        if statut in ("transfer_success", "success"):
            return True, None
        return False, f"transfert non abouti ({statut or 'sans résultat'})"
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[sortie] transfert non lancé : {erreur!r}")
        return False, "transfert non lancé"


def transfert_refuse(moteur: Any) -> str | None:
    """Pourquoi une sortie « transférer » ne part pas, ou ``None``. Hors état OUVERT ou SUR_RENDEZ_VOUS
    (même règle que le montrage de l'outil de transfert au modèle : sans état d'ouverture, permis), ou
    si une sortie de transfert est déjà passée dans cet appel (jamais de réentrée, quel que soit le
    motif). ⛔ Ne lève jamais."""
    try:
        if getattr(moteur, DRAPEAU_TRANSFERT, False) is True:
            return "une sortie de transfert est déjà passée dans cet appel"
        from api.services.annonce.constantes import OUVERT, SUR_RENDEZ_VOUS

        variables = getattr(moteur, "_call_context_vars", None) or {}
        etat = variables.get("etat_ouverture")
        if etat and etat not in (OUVERT, SUR_RENDEZ_VOUS):
            return "l'entreprise n'est pas ouverte"
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[sortie] état d'ouverture illisible : {erreur!r}")
    return None


def lancer_apres(moteur: Any, issue: IssueDeSortie) -> None:
    """Lance l'action finale détachée d'une sortie, une fois le résultat de l'outil remis. ⛔ Ne lève
    jamais."""
    try:
        if issue.apres is None:
            return
        tache = asyncio.get_running_loop().create_task(issue.apres(), name="sortie:apres")
        taches = moteur.__dict__.setdefault("_taches_de_sortie", set())
        taches.add(tache)
        tache.add_done_callback(taches.discard)
        issue.apres = None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[sortie] action finale non lancée : {erreur!r}")


async def _reprendre_la_parole(moteur: Any) -> None:
    """Le transfert détaché n'a pas abouti : le modèle reprend la main (jamais un silence définitif)."""
    try:
        from pipecat.frames.frames import LLMRunFrame

        agent = getattr(moteur, "active_agent", None)
        if agent is not None and not moteur.is_call_disposed():
            await agent.queue_frame(LLMRunFrame())
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[sortie] reprise de la parole impossible : {erreur!r}")


async def executer(
    moteur: Any,
    diseur: Any,
    phrase: PhraseResolue,
    *,
    agent: Any = None,
    etape: str | None = None,
    rang: int = 0,
    sans_voix: bool = False,
    raison_de_fin: str | None = None,
    differer: bool = False,
) -> IssueDeSortie:
    """Dire, noter, puis l'action finale de la règle ``phrase``. ``sans_voix`` : la phrase de sortie est
    déjà dite par l'appelant (rien à dire ici). ``raison_de_fin`` : la raison de fin d'appel quand l'action
    raccroche (celle du silence garde la sienne). ``differer`` : appelé pendant un appel de fonction (échec
    d'un outil, du fond, d'un transfert) : l'action finale n'est pas attendue ici, elle est rendue dans
    ``issue.apres`` pour partir après la remise du résultat. ⛔ Ne lève jamais."""
    issue = IssueDeSortie(action=phrase.action_de_sortie)
    try:
        sortie = phrase.ensuite
        parole = None
        if sortie.phrases and not sans_voix:
            parole = await diseur.dire_la_sortie(phrase, agent, etape=etape, rang=rang)
            if parole is not None:
                issue.dit = getattr(parole, "text", None)
                try:
                    diseur.coupures.marquer_compte_rendu(parole)
                except Exception:  # noqa: BLE001
                    pass
        _noter_dans_la_fiche(moteur, phrase, issue)
        action = issue.action
        if action == ACTION_TRANSFERER:
            refus = transfert_refuse(moteur)
            if refus is not None:
                # Refusé : le modèle reprend, et « transférer » n'est plus possible.
                issue.action = ACTION_MODELE
                issue.erreurs.append(refus)
                issue.interdit.append("transférer")
            else:
                setattr(moteur, DRAPEAU_TRANSFERT, True)
                destination = sortie.destination or ""

                async def transferer() -> None:
                    await _attendre_la_phrase(moteur, parole)
                    lance, raison = await transferer_a(moteur, destination)
                    if not lance:
                        logger.info(f"[sortie] transfert non abouti : {raison}")
                        await _reprendre_la_parole(moteur)

                if differer:
                    issue.apres = transferer
                    issue.prise_en_main = True
                else:
                    await _attendre_la_phrase(moteur, parole)
                    lance, raison = await transferer_a(moteur, destination)
                    if lance:
                        issue.prise_en_main = True
                    else:
                        issue.action = ACTION_MODELE
                        issue.erreurs.append(raison or "transfert non lancé")
                        issue.interdit.append("transférer")
        elif action in (ACTION_RENDRE_LA_MAIN, ACTION_ALLER_A_UNE_ETAPE):
            # fiabilite-de-la-conversation, lot A : la sortie du garde-fou d'impasse. Le code change l'étape de
            # lui-même une fois la phrase dite ; sans étape choisie (ou introuvable), la main revient à l'accueil.
            cible = sortie.destination if action == ACTION_ALLER_A_UNE_ETAPE else None

            async def rendre_la_main() -> None:
                await _attendre_la_phrase(moteur, parole)
                if not await moteur.sortir_de_l_impasse(agent, etape_cible=cible):
                    logger.info("[sortie] la main n'a pas pu être rendue : le modèle reprend")
                    # Revue du 26/10 (R-2) : muet depuis la décision du garde-fou, il reparle.
                    from api.services.pipecat.main_passee import rendre_la_parole

                    rendre_la_parole(getattr(agent or getattr(moteur, "active_agent", None), "llm", None))
                    await _reprendre_la_parole(moteur)

            issue.prise_en_main = True
            if differer:
                issue.apres = rendre_la_main
            else:
                await rendre_la_main()
        elif action == ACTION_RACCROCHER:
            from pipecat.utils.enums import EndTaskReason

            raison_fin = raison_de_fin or EndTaskReason.END_CALL.value

            async def raccrocher() -> None:
                await _attendre_la_phrase(moteur, parole)
                await moteur.end_call_with_reason(raison_fin)

            issue.prise_en_main = True
            if differer:
                issue.apres = raccrocher
            else:
                await raccrocher()
        logger.info(
            f"[sortie] {phrase.motif.id} : dit={issue.dit!r} notes={issue.notes} action={issue.action} "
            f"prise_en_main={issue.prise_en_main} erreurs={issue.erreurs}"
        )
    except asyncio.CancelledError:
        raise
    except Exception as erreur:  # noqa: BLE001 -- une sortie ne coûte jamais l'appel
        issue.action = ACTION_MODELE
        issue.prise_en_main = False
        issue.erreurs.append("sortie en échec")
        logger.warning(f"[sortie] {phrase.motif.id} en échec : {erreur!r}")
    return issue
