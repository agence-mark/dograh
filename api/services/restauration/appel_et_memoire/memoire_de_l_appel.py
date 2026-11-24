"""[.mark] Chantier Partie 1, lot 5 (E23, D53, D58, S15) : la mémoire d'UN appel pour les outils de la commande et de la réservation.

- **Une connexion par appel** (D53, S15) : ouverte au premier geste, gardée jusqu'à la fin de l'appel (``fermer``), partagée par la commande et la
  réservation, un geste à la fois (``asyncio.Lock`` : une connexion ne sert qu'une opération ; Pipecat peut lancer deux outils ensemble). Coupée
  par la base entre deux gestes : rouverte UNE fois ; coupée encore : ``BaseClientIndisponible`` (l'outil le dit comme une panne).
- **Le chargement au décroché** (``lancer_le_chargement``) : sur sa propre connexion, courte, en tâche, sans retarder la phrase d'accueil, il remplit
  l'instantané de l'appel (``db/bases_clients/instantane.py``) par ``SourceClasseur.charger_pour_l_appel`` et range les listes fermées de la fiche
  dans le contexte de l'appel (ligne SA-1 du chantier).
- **Une fiche arrivée avant la fin du chargement** (D58) attend au plus ``attente_du_chargement_ms`` ; au-delà, ou si le chargement a échoué, elle
  lit la base directement (l'instantané se remplit alors à ses lectures), l'écart est journalisé ; jamais une fiche refusée faute de chargement.

Aucun état partagé entre deux appels ni entre deux processus : tout vit dans l'appel, le registre ``_APPELS`` est vidé à sa fin.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.bases_clients.instantane import Instantane
from api.services.restauration.appel_et_memoire.appel import Lieu, base_et_cle_de_l_appel, identifiant_de_l_etablissement

ATTENTE_DU_CHARGEMENT_MS = 300  # D58 : valeur écrite au journal avant la mesure (section latence-lot-5), réglage du module
CLE_ATTENTE = "commande_attente_du_chargement_ms"


@dataclass
class AppelOuvert:
    nom_base: str
    lieu: Lieu | None = None
    connexion: Any = None
    instantane: Instantane | None = None
    verrou: asyncio.Lock = field(default_factory=asyncio.Lock)
    chargement: asyncio.Task | None = None
    chargement_ms: float | None = None
    reouvertures: int = 0
    ouvertures: int = 0
    dernier_geste: float = field(default_factory=time.perf_counter)  # clôture A5 ; durée monotone (``perf_counter``), jamais l'heure réelle : la source d'heure du module est ``horloge`` (D6) : la limite d'inactivité du clavier se lit ici
    au_clavier: bool = False  # Pierre 12 : posé par la fin d'un tour au clavier ; seul un appel au clavier est balayé pour inactivité (un appel à la voix peut se taire plus de 60 s)


_APPELS: dict[str, AppelOuvert] = {}

# L'ouverture d'une connexion, remplaçable par un essai (compter les connexions, simuler une coupure).
CONNECTER: Callable[[str], Awaitable[Any]] = connecter


def _cle(run_id: Any) -> str | None:
    return str(run_id) if run_id else None


def appel_ouvert(run_id: Any) -> AppelOuvert | None:
    cle = _cle(run_id)
    return _APPELS.get(cle) if cle else None


def attente_du_chargement_s(configurations: Any) -> float:
    """D58 : le court délai qu'une fiche attend la fin du chargement (réglage du module, défaut ``ATTENTE_DU_CHARGEMENT_MS``)."""
    valeur = (configurations or {}).get(CLE_ATTENTE, ATTENTE_DU_CHARGEMENT_MS) if isinstance(configurations, dict) else ATTENTE_DU_CHARGEMENT_MS
    if not isinstance(valeur, int) or isinstance(valeur, bool) or not 0 <= valeur <= 5000:
        valeur = ATTENTE_DU_CHARGEMENT_MS
    return valeur / 1000


async def _ouvrir(appel: AppelOuvert) -> Any:
    connexion = await CONNECTER(appel.nom_base)
    connexion.instantane = appel.instantane
    appel.ouvertures += 1
    return connexion


async def _connexion_prete(appel: AppelOuvert) -> Any:
    """La connexion de l'appel, ouverte au premier geste ; coupée par la base : rouverte UNE fois, puis la panne."""
    if appel.connexion is None:
        appel.connexion = await _ouvrir(appel)
    elif appel.connexion.is_closed():
        if appel.reouvertures >= 1:
            raise BaseClientIndisponible("La connexion de l'appel a été coupée deux fois.")
        appel.reouvertures += 1
        logger.warning(f"[.mark] Call connection closed by the database, opened again once ({appel.nom_base})")
        appel.connexion = await _ouvrir(appel)
    return appel.connexion


async def _attendre_le_chargement(appel: AppelOuvert, delai_s: float) -> None:
    tache = appel.chargement
    if tache is None or tache.done():
        if tache is not None and tache.done() and not tache.cancelled() and tache.exception() is not None:
            logger.warning("[.mark] Call loading failed: the tool reads the database directly")
        return
    debut = time.perf_counter()
    fini, _ = await asyncio.wait({tache}, timeout=delai_s)
    if not fini:
        logger.warning(f"[.mark] Call loading not ready after {delai_s * 1000:.0f} ms: the tool reads the database directly")
    elif tache.exception() is not None:
        logger.warning("[.mark] Call loading failed: the tool reads the database directly")
    else:
        logger.debug(f"[.mark] Tool waited {(time.perf_counter() - debut) * 1000:.0f} ms for the call loading")


async def _poser_le_lieu_et_l_instantane(appel: AppelOuvert, connexion: Any, ctx: Any) -> None:
    """La seule écriture du lieu et de l'instantané d'un appel : posés une fois, puis donnés à la connexion qui sert (celle du geste, celle du chargement) et à celle de l'appel."""
    if appel.lieu is None:
        _, cle_lieu = await base_et_cle_de_l_appel(ctx)
        appel.lieu = Lieu(appel.nom_base, await identifiant_de_l_etablissement(connexion, cle_lieu), ctx.organization_id)
    if appel.instantane is None:
        appel.instantane = Instantane(appel.lieu.etablissement_id)
    connexion.instantane = appel.instantane
    if appel.connexion is not None:
        appel.connexion.instantane = appel.instantane


@asynccontextmanager
async def geste(ctx: Any) -> AsyncIterator[tuple[Any, Lieu]]:
    """La connexion et le lieu de l'appel pour UN geste d'outil (D53). Sans appel suivi (``run_id`` absent : un essai, une route) : une connexion
    pour ce geste seulement, comme avant."""
    cle = _cle(getattr(ctx, "run_id", None))
    if cle is None:
        nom_base, cle_lieu = await base_et_cle_de_l_appel(ctx)
        connexion = await CONNECTER(nom_base)
        try:
            yield connexion, Lieu(nom_base, await identifiant_de_l_etablissement(connexion, cle_lieu), ctx.organization_id)
        finally:
            await connexion.close()
        return
    appel = _APPELS.get(cle)
    if appel is None:
        nom_base, _ = await base_et_cle_de_l_appel(ctx)
        appel = _APPELS[cle] = AppelOuvert(nom_base)
    await _attendre_le_chargement(appel, attente_du_chargement_s(getattr(ctx, "configurations", None)))
    async with appel.verrou:
        connexion = await _connexion_prete(appel)
        await _poser_le_lieu_et_l_instantane(appel, connexion, ctx)
        appel.instantane.nouveau_geste()
        appel.dernier_geste = time.perf_counter()
        yield connexion, appel.lieu


async def _charger(appel: AppelOuvert, ctx: Any, contexte: dict | None, fiche_de_l_appel: dict | None) -> None:
    from api.services.restauration.source_commande import SourceClasseur

    debut = time.perf_counter()
    connexion = await CONNECTER(appel.nom_base)
    gardee = False
    try:
        await _poser_le_lieu_et_l_instantane(appel, connexion, ctx)
        source = SourceClasseur(connexion, appel.lieu)
        listes, objets = await source.charger_pour_l_appel()
        if isinstance(contexte, dict):
            for nom, valeurs in listes.items():
                contexte.setdefault(nom, valeurs)
        if isinstance(fiche_de_l_appel, dict):
            from api.services.commande.contrat import CLE_DES_OBJETS

            fiche_de_l_appel.setdefault(CLE_DES_OBJETS, objets)
        # Clôture A5 (IC1) : la connexion du chargement devient celle de l'appel quand il n'en a pas encore ; le premier geste ne rouvre rien
        # (56 à 66 ms en local pour la première fiche, au-dessus du seuil de 50 ms, contre 5 à 15 pour les suivantes).
        async with appel.verrou:
            if appel.connexion is None:
                appel.connexion, gardee = connexion, True
                appel.ouvertures += 1
    finally:
        if not gardee:
            await connexion.close()
        appel.chargement_ms = (time.perf_counter() - debut) * 1000
        logger.info(f"[.mark] Call loaded in {appel.chargement_ms:.0f} ms")


def lancer_le_chargement(ctx: Any, nom_base: str, *, contexte: dict | None = None, fiche_de_l_appel: dict | None = None) -> asyncio.Task | None:
    """Le chargement de l'appel en tâche (jamais attendu ici : la phrase d'accueil ne l'attend pas). ``ctx`` : l'organisation, le contexte d'appel
    et le run, comme pour un outil. ⛔ Ne lève jamais."""
    cle = _cle(getattr(ctx, "run_id", None))
    if cle is None:
        return None
    try:
        appel = _APPELS.setdefault(cle, AppelOuvert(nom_base))
        appel.chargement = asyncio.get_running_loop().create_task(_charger(appel, ctx, contexte, fiche_de_l_appel))
        appel.chargement.add_done_callback(_journaliser_l_echec)
        return appel.chargement
    except Exception as erreur:  # noqa: BLE001 -- le décroché ne dépend jamais du chargement
        logger.warning(f"[.mark] Call loading not started ({type(erreur).__name__})")
        return None


def charger_au_decroche(
    organization_id: int | None, workflow_run_id: Any, run_configs: Any, contexte: dict, fiche_de_l_appel: dict | None
) -> asyncio.Task | None:
    """Au décroché (``run_pipeline``) : lance le chargement si le module de commande est allumé pour cet agent et que l'organisation a une base
    de client. Rend la tâche, jamais attendue par l'appelant. ⛔ Ne lève jamais : l'appel continue, les outils liront la base."""
    from types import SimpleNamespace

    if not organization_id or not workflow_run_id:
        return None

    async def preparer() -> None:
        from api.services.base_client.rattachement import nom_de_la_base
        from api.services.modules.etat import interrupteur_allume
        from api.services.modules.registre import PAR_CODE

        module = PAR_CODE.get("commande")
        if module is None or not interrupteur_allume(module, run_configs):
            return
        nom_base = await nom_de_la_base(organization_id)
        if not nom_base:
            return
        ctx = SimpleNamespace(organization_id=organization_id, run_id=workflow_run_id, appel=contexte, configurations=run_configs)
        tache = lancer_le_chargement(ctx, nom_base, contexte=contexte, fiche_de_l_appel=fiche_de_l_appel)
        if tache is not None:
            await asyncio.shield(tache)

    try:
        tache = asyncio.get_running_loop().create_task(preparer())
        tache.add_done_callback(_journaliser_l_echec)
        return tache
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Call loading not started ({type(erreur).__name__})")
        return None


ATTENTE_AU_CLAVIER_S = 10.0  # le clavier n'a pas de phrase d'accueil qui couvre le chargement : le premier tour l'attend, borné


async def charger_au_clavier(
    organization_id: int | None, workflow_run_id: Any, run_configs: Any, contexte: dict, fiche_de_l_appel: dict | None
) -> None:
    """Chantier Partie 1, lot 6 : le même chargement qu'au décroché, sur le chemin du CLAVIER (``text_chat_runner``), qui ne passe pas par
    ``run_pipeline``. Sans lui, un essai au clavier n'avait ni les listes fermées de la fiche ni les objets de la carte (vu sur le chantier,
    appel 4). Le premier tour l'attend (``ATTENTE_AU_CLAVIER_S`` au plus) ; les listes vont dans le contexte du run, que le clavier enregistre,
    les objets dans la fiche de l'appel, que le point de reprise garde : les tours suivants ne rechargent rien. ⛔ Ne lève jamais."""
    try:
        from api.services.commande.contrat import CLE_DES_OBJETS

        if isinstance(fiche_de_l_appel, dict) and CLE_DES_OBJETS in fiche_de_l_appel:
            return
        tache = charger_au_decroche(organization_id, workflow_run_id, run_configs, contexte, fiche_de_l_appel)
        if tache is not None:
            await asyncio.wait_for(asyncio.shield(tache), ATTENTE_AU_CLAVIER_S)
    except Exception as erreur:  # noqa: BLE001 -- le tour continue, les outils liront la base
        logger.warning(f"[.mark] Keyboard call loading failed ({type(erreur).__name__}): the tools read the database directly")


def _journaliser_l_echec(tache: asyncio.Task) -> None:
    if not tache.cancelled() and tache.exception() is not None:
        logger.warning(f"[.mark] Call loading failed ({type(tache.exception()).__name__}): the tools read the database directly")


INACTIVITE_AU_CLAVIER_S = 60.0  # clôture A5 : un appel au clavier sans geste depuis ce délai est fermé (sa connexion n'attend pas un tour qui ne viendra plus)


async def fin_du_tour_au_clavier(run_id: Any, *, termine: bool) -> None:
    """Clôture A5 (IC1, audit de la latence § 4, point 1 a) : à la fin d'un tour au clavier, l'appel est GARDÉ (connexion, instantané, lieu) pour
    le tour suivant, comme à la voix ; il est fermé quand la partie est finie (``termine`` : l'appel est terminé, ou le tour a levé). Les appels
    sans geste depuis ``INACTIVITE_AU_CLAVIER_S`` sont fermés au passage : la fuite corrigée par ``8fd23a6d`` (97 connexions pour 100 parties)
    ne revient pas, et un tour ne relit plus toute la carte (40 ms par fiche au jeu 3 contre 5). ⛔ Ne lève jamais."""
    try:
        if termine:
            await fermer(run_id)
        if (courant := _APPELS.get(_cle(run_id) or "")) is not None:
            courant.au_clavier = True
        maintenant = time.perf_counter()
        for cle in [c for c, a in _APPELS.items() if a.au_clavier and c != _cle(run_id) and maintenant - a.dernier_geste > INACTIVITE_AU_CLAVIER_S]:
            if not ((a := _APPELS.get(cle)) and a.verrou.locked()):
                await fermer(cle)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Keyboard call not closed cleanly ({type(erreur).__name__})")


async def fermer(run_id: Any) -> None:
    """À la fin de l'appel : le chargement arrêté s'il tourne encore, la connexion fermée, l'appel oublié. ⛔ Ne lève jamais."""
    appel = _APPELS.pop(_cle(run_id) or "", None)
    if appel is None:
        return
    try:
        if appel.chargement is not None and not appel.chargement.done():
            appel.chargement.cancel()
        if appel.connexion is not None and not appel.connexion.is_closed():
            await appel.connexion.close()
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Call connection not closed cleanly ({type(erreur).__name__})")
