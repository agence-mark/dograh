"""[.mark] Chantier fiabilite-orchestration : l'enveloppe des actions (outils HTTP, MCP, connecteurs).

Toute action qu'un agent ou le cerveau de fond appelle passe par cette enveloppe, posée au moment
où ``CustomToolManager`` enregistre son gestionnaire. Elle ne change rien à l'action ; elle lit son
résultat pour :

- **lot 1 (R3, G2)** : écrire les champs de la fiche « remplis par l'outil » (``rempli_par_outil``)
  depuis le résultat de cet outil, et seulement de lui. La valeur : la clé du même nom dans la
  réponse, sinon son statut, sinon la première valeur permise du champ, sinon « oui ». Un échec
  n'écrit rien. La réponse d'un outil HTTP est lue dans son emballage (``data``), jamais l'emballage
  lui-même (chantier ``fiche-lit-la-reponse-de-l-outil``, run 1475). Les contrôles restent ceux du point d'écriture unique (liste fermée comprise).

- **lot 4 bis (F21)** puis **correctifs-apres-banc-v4 (lot 4)** : une action du tour qui dépasse le délai
  de la règle « un outil travaille » fait dire sa phrase par la veille générique du diseur (redites,
  plafonds, sortie de la règle) ; le délai court depuis le lancement de l'action (une attente du
  système) et jamais pendant que l'appelant parle. La règle peut viser cet outil par son nom. Une action
  du cerveau de fond ne la déclenche jamais (le motif « le travail de fond travaille » s'en charge).

- **correctifs-apres-banc-v4 (lot 4)** : un résultat qui dit une panne (erreur de l'outil après ses
  essais, service qui répond « échec ») passe par la règle « un outil échoue » : la phrase, le compteur
  dans l'appel, la sortie de la règle (noter, transférer, raccrocher), puis un compte rendu en français
  dans le résultat que lit le modèle. Un outil sans règle posée ne dit rien de plus qu'avant (le défaut
  du catalogue ne parle que pour un connecteur, qui disait déjà sa phrase).

Les portes, passations, transferts et la fin d'appel n'y passent jamais : ce ne sont pas des actions.
⛔ Ne lève jamais : l'action rend toujours son résultat, l'enveloppe ne fait que regarder.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

# « missing » (connecteur à qui il manque un paramètre) et « incomplet » (garde de l'étape) : rien n'est fait,
# donc rien à écrire (relecture du 20/10).
_ERREURS = frozenset(
    {"error", "erreur", "echec", "échec", "failed", "failure", "ko", "missing", "incomplet"}
)
# Les vraies pannes (la règle « un outil échoue ») : « missing » et « incomplet » ne sont pas des pannes,
# rien n'a été tenté (un paramètre manque, la garde de l'étape retient l'outil).
_PANNES = _ERREURS - {"missing", "incomplet"}


def _normaliser(nom: Any) -> str:
    from api.services.workflow.tools.custom_tool import custom_tool_function_name

    return custom_tool_function_name(str(nom or ""))


def _lire(resultat: Any) -> Any:
    if isinstance(resultat, str):
        try:
            return json.loads(resultat)
        except (TypeError, ValueError):
            return resultat
    return resultat


def _reponse(lu: Any) -> Any:
    """La réponse du service derrière l'action. Un outil HTTP de Dograh l'emballe :
    ``{"status": "success", "status_code": 200, "data": <réponse>}`` (``execute_http_tool``) ; le
    ``status`` de l'emballage dit que l'appel HTTP est passé, pas ce que le service a répondu
    (run 1475 : « success » écrit à la place de « confirme », refusé hors liste). Sans emballage :
    le résultat tel quel."""
    if isinstance(lu, dict) and "status_code" in lu and "data" in lu:
        return _lire(lu["data"])
    return lu


def _dit_un_echec(lu: Any) -> bool:
    if isinstance(lu, dict):
        if lu.get("error") not in (None, "", False):
            return True
        for cle in ("statut", "status"):
            valeur = lu.get(cle)
            if isinstance(valeur, str) and valeur.strip().casefold() in _ERREURS:
                return True
    return False


def est_un_echec(resultat: Any) -> bool:
    """L'emballage en échec (HTTP en erreur), ou la réponse du service en échec (rendue en 200)."""
    lu = _lire(resultat)
    return _dit_un_echec(lu) or _dit_un_echec(_reponse(lu))


def _dit_une_panne(lu: Any) -> bool:
    if isinstance(lu, dict):
        if lu.get("error") not in (None, "", False):
            return True
        for cle in ("statut", "status"):
            valeur = lu.get(cle)
            if isinstance(valeur, str) and valeur.strip().casefold() in _PANNES:
                return True
    return False


def est_une_panne(resultat: Any) -> bool:
    """Le résultat dit une vraie panne (outil en erreur après ses essais, service qui répond un échec),
    non un paramètre manquant ni une étape incomplète. Sert la règle « un outil échoue »."""
    lu = _lire(resultat)
    return _dit_une_panne(lu) or _dit_une_panne(_reponse(lu))


def valeur_pour_le_champ(champ: Any, resultat: Any) -> Any:
    """La valeur qu'un résultat d'outil réussi écrit dans ``champ`` (voir l'en-tête), lue dans la
    réponse du service, jamais dans l'emballage d'un outil HTTP. ``None`` : rien à écrire.

    Une réponse HTTP n'écrit que ce qu'elle dit (la clé du champ, sinon son statut) : jamais la
    première valeur permise par défaut. Un service qui répond « lancé » avant d'avoir agi (webhook
    à réponse immédiate) n'écrit donc jamais « confirme » (relecture du 20/10)."""
    brut = _lire(resultat)
    lu = _reponse(brut)
    if isinstance(lu, dict):
        if lu.get(champ.nom) not in (None, ""):
            return lu[champ.nom]
        for cle in ("statut", "status"):
            if isinstance(lu.get(cle), str) and lu[cle].strip():
                return lu[cle].strip()
    if lu is not brut:
        return None
    if champ.valeurs:
        return champ.valeurs[0]
    return "oui"


def remplir_par_l_action(moteur: Any, nom_outil: str, resultat: Any) -> list[str]:
    """Écrit les champs que ``nom_outil`` remplit. Rend les noms des champs écrits. ⛔ Ne lève jamais."""
    ecrits: list[str] = []
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if reglages is None or not isinstance(fiche, dict):
            return ecrits
        cible = _normaliser(nom_outil)
        champs = [
            c
            for c in reglages.champs
            if c.rempli_par_outil and _normaliser(c.rempli_par_outil) == cible
        ]
        if not champs:
            return ecrits
        if est_un_echec(resultat):
            logger.info(f"[fiche] {nom_outil} en échec : {', '.join(c.nom for c in champs)} non écrits")
            return ecrits
        from api.services.workflow.fiche_au_fil_de_leau import (
            SOURCE_ACTION,
            ecrire_dans_la_fiche,
        )

        for champ in champs:
            valeur = valeur_pour_le_champ(champ, resultat)
            if valeur is None:
                logger.info(f"[fiche] {champ.nom} par {nom_outil} : rien dans la réponse, non écrit")
                continue
            verdict = ecrire_dans_la_fiche(
                fiche, reglages, champ.nom, valeur, source=SOURCE_ACTION
            )
            if verdict.statut == "ecrit":
                ecrits.append(champ.nom)
            logger.info(f"[fiche] {champ.nom} par {nom_outil} : {verdict.statut} ({verdict.raison})")
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] résultat de {nom_outil} non lu pour la fiche : {erreur!r}")
    return ecrits


STATUT_INCOMPLET = "incomplet"


def garde_de_l_etape(moteur: Any, agent: Any) -> dict | None:
    """Lot 2 (F9, C3 ; run 1468 : action lancée avec des champs encore « à venir ») : l'étape de
    ``agent`` déclare la liste de ses champs, la case « connu et attendu » est allumée, et des
    champs manquent encore : l'outil ne s'exécute pas, il rend ``{"statut": "incomplet", "manque":
    [...]}`` (le modèle le lit et demande). Sans liste, sans fiche, case éteinte, ou rien ne
    manque : ``None`` (l'outil s'exécute comme avant). ⛔ Ne lève jamais."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        noeud = getattr(agent, "current_node", None)
        champs_etape = tuple(getattr(noeud, "champs_etape", None) or ())
        if reglages is None or not isinstance(fiche, dict) or not champs_etape:
            return None
        if not getattr(reglages, "etiquettes", False):
            return None
        from api.services.fiche.traces import valeurs_des_traces
        from api.services.groupe.notes import champs_attendus, nom_lisible

        manque = champs_attendus(reglages, fiche, champs_etape, valeurs_des_traces(reglages, fiche))
        if not manque:
            return None
        return {"statut": STATUT_INCOMPLET, "manque": [nom_lisible(n) for n in manque]}
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, l'outil s'exécute comme avant
        logger.warning(f"[fiche] garde de l'étape illisible : {erreur!r}")
        return None


Gestionnaire = Callable[[Any], Awaitable[None]]


def envelopper_l_action(
    moteur: Any,
    nom_outil: str,
    gestionnaire: Gestionnaire,
    agent: Any = None,
    *,
    garde: bool = True,
) -> Gestionnaire:
    """Le gestionnaire de l'action, enveloppé : la garde de l'étape d'``agent`` (lot 2), puis son
    résultat lu avant de partir au modèle (lot 1). ``garde=False`` : une action qui agit sur
    l'appel (une action interne qui peut transférer), jamais gardée."""

    async def enveloppe(params: Any) -> None:
        if garde and agent is not None:
            refus = garde_de_l_etape(moteur, agent)
            if refus is not None:
                logger.info(f"[fiche] {nom_outil} retenu : {refus['manque']} manquent")
                await params.result_callback(refus)
                return
        rendre = params.result_callback
        fini = asyncio.Event()
        veille = _veiller_l_outil(moteur, nom_outil, agent, params, fini)

        async def result_callback(resultat: Any, *args: Any, **kwargs: Any) -> None:
            proprietes = kwargs.get("properties")
            # Un résultat intermédiaire (``is_final=False``) n'est pas encore la réponse de l'outil.
            if getattr(proprietes, "is_final", True) is not False:
                fini.set()
                remplir_par_l_action(moteur, nom_outil, resultat)
                resultat, kwargs = await _signaler_la_panne(
                    moteur, nom_outil, agent, params, resultat, kwargs
                )
            await rendre(resultat, *args, **kwargs)

        try:
            params.result_callback = result_callback
        except Exception as erreur:  # noqa: BLE001 -- paramètres figés : l'action passe telle quelle
            logger.debug(f"[fiche] résultat de {nom_outil} non lu : {erreur!r}")
        try:
            await gestionnaire(params)
        finally:
            fini.set()
            # Une veille qui n'a encore rien dit est coupée ; une phrase commencée finit (ses redites
            # s'arrêtent d'elles-mêmes : l'outil n'est plus en cours).
            if veille is not None:
                from api.services.phrases.diseur import DiseurDePhrases

                DiseurDePhrases.arreter_la_veille(veille)

    return enveloppe


def _action_du_agent(agent: Any, moteur: Any, params: Any) -> Any | None:
    """L'agent qui porte cette action, ``None`` si elle vient du cerveau de fond (qui a son propre motif)."""
    cible = agent if agent is not None else getattr(moteur, "active_agent", None)
    appelant = getattr(params, "llm", None)
    if appelant is not None and appelant is not getattr(cible, "llm", None):
        return None
    return cible


def _veiller_l_outil(
    moteur: Any, nom_outil: str, agent: Any, params: Any, fini: asyncio.Event
) -> asyncio.Task | None:
    """F21 : la veille de « un outil travaille » pour cet appel d'outil (veille générique du diseur :
    délai, redites, plafonds, sortie). ``None`` : règle éteinte, pas de diseur, ou action du cerveau de
    fond. ⛔ Ne lève jamais."""
    try:
        from api.services.phrases.catalogue import OUTIL_TARDE
        from api.services.phrases.diseur import DiseurDePhrases

        diseur = getattr(moteur, "phrases", None)
        if not isinstance(diseur, DiseurDePhrases):
            return None
        cible = _action_du_agent(agent, moteur, params)
        if cible is None:
            return None
        phrase = diseur.phrase(OUTIL_TARDE, cible, outil=nom_outil)
        if phrase is None or not phrase.dite:
            return None
        return diseur.lancer_la_veille(
            OUTIL_TARDE,
            lambda: not fini.is_set(),
            nom="phrase:outil_tarde",
            agent=cible,
            outil=nom_outil,
            phrase=phrase,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] veille de l'outil illisible : {erreur!r}")
        return None


def _avec_le_compte_rendu(resultat: Any, compte: str) -> Any:
    """Le compte rendu standard dans le résultat que lit le modèle (jamais un message à part)."""
    if not compte:
        return resultat
    if isinstance(resultat, dict):
        return {**resultat, "compte_rendu": compte}
    if isinstance(resultat, str):
        return f"{resultat}\n{compte}"
    return resultat


async def _signaler_la_panne(
    moteur: Any, nom_outil: str, agent: Any, params: Any, resultat: Any, kwargs: dict
) -> tuple[Any, dict]:
    """Le résultat dit une panne : la règle « un outil échoue » (phrase, compteur, sortie), puis le
    compte rendu dans le résultat. La phrase entre dans l'historique APRÈS le résultat de l'outil (la
    case de l'appel en cours est complétée par ce résultat, la phrase vient derrière) : mesuré au lot 0,
    0/10 répétition. Une sortie qui a pris l'appel en main (transfert lancé, appel raccroché) : le modèle
    n'est pas relancé. ⛔ Ne lève jamais : sans règle posée, le résultat part tel quel."""
    try:
        from api.services.phrases.catalogue import MOTIFS, OUTIL_ECHOUE
        from api.services.phrases.compte_rendu import compte_rendu
        from api.services.phrases.diseur import DiseurDePhrases

        diseur = getattr(moteur, "phrases", None)
        if not isinstance(diseur, DiseurDePhrases) or not est_une_panne(resultat):
            return resultat, kwargs
        cible = _action_du_agent(agent, moteur, params)
        if cible is None:
            return resultat, kwargs
        probleme = await diseur.signaler_un_probleme(
            OUTIL_ECHOUE, cible, outil=nom_outil, seulement_si_posee=True
        )
        if probleme.dit is None and probleme.issue is None:
            return resultat, kwargs
        issue = probleme.issue
        compte = compte_rendu(
            MOTIFS[OUTIL_ECHOUE].fait_fr,
            dit=probleme.dit,
            notes=probleme.notes,
            interdits=issue.interdit if issue is not None else (),
        )
        resultat = _avec_le_compte_rendu(resultat, compte)
        if issue is not None and issue.prise_en_main:
            from pipecat.frames.frames import FunctionCallResultProperties

            kwargs = {**kwargs, "properties": FunctionCallResultProperties(run_llm=False)}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] panne de {nom_outil} non signalée : {erreur!r}")
    return resultat, kwargs
