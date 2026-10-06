"""Les séries de l'appelant simulé (.mark, chantier langwatch-et-fenetre-du-run, lot 3, L9 à L13,
L18, L19, Q1 à Q3).

``lancer_serie`` (route) valide la demande, prend le verrou de l'organisation (une série à la
fois), estime le coût, inscrit la série et la met en file ARQ. ``jouer_serie`` (tâche ARQ) joue
les appels, ``simultanes`` à la fois (1 par défaut, L13), chacun ainsi :

1. un run ``simulated`` est créé avec son jeton à usage unique (``entree.creer_run_simule``) ;
2. le lanceur Scenario tourne dans son propre environnement (L19), par sous-processus : entrée
   JSON sur stdin, clés par l'environnement du sous-processus seulement, verdict sur la ligne
   ``MARK_VERDICT`` ; aucune variable ``LANGWATCH_*`` n'est transmise ;
3. si l'agent renvoie l'appel, la décision du scénario (accepté, refusé, sans réponse) est donnée
   au renvoi simulé : aucun vrai numéro n'est composé (``MODES_DE_TEST``) ;
4. le run fini, son analyse (celle de la fenêtre) donne le coût et le pire tour ; le verdict,
   les critères, le raisonnement du juge et la conversation sont rangés dans ``run.extra``.

Avant chaque appel : la série s'arrête si l'appel suivant risque de dépasser le plafond (Q3), ou
si quelqu'un l'a arrêtée à l'écran. Rien de propre à un métier ici : les mots d'un métier vivent
dans les scénarios écrits à l'écran.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import tempfile
import uuid
from pathlib import Path

import redis.asyncio as aioredis
from loguru import logger

from api.constants import BACKEND_API_ENDPOINT, REDIS_URL
from api.db import db_client
from api.enums import WorkflowRunState
from api.schemas.appel_simule import ReglagesAppelantSimule, ScenarioSimule
from api.services.analyse_run.cout import lire_reglages_fenetre
from api.services.analyse_run.du_run import analyser_le_run
from api.services.appel_simule.entree import CLE_EXTRA, adresse_ws, creer_run_simule
from api.services.appel_simule.reglages import (
    AppelDeSerie,
    SerieSimulee,
    ecrire_serie,
    lire_reglages,
    lire_scenarios,
    lire_serie,
    lire_series,
    maintenant,
)
from api.services.workflow.renvoi_en_test import donner_la_decision, renvoi_en_attente
from api.services.workflow_run_failure import mark_workflow_run_failed

PYTHON_SIMULATEUR = "/opt/venv-simulateur/bin/python"
LANCEUR = Path(__file__).resolve().parents[3] / "simulateur" / "jouer.py"
MARQUE = "MARK_VERDICT "
DELAI_PAR_TOUR_S = 45
DELAI_FIN_DU_RUN_S = 180
VERROU_S = 6 * 3600
INTERVALLE_S = 0.5

# Des consignes génériques de comportement d'un appelant au téléphone (L10) : aucun métier.
COMPORTEMENTS = {
    "presse": "Tu es pressé : tu vas droit au but et tu montres ton impatience si ça traîne.",
    "coupe_la_parole": "Il t'arrive de couper la parole à l'agent avant qu'il ait fini.",
    "hesite": "Tu hésites parfois (« euh… »), tu te reprends, tu corriges un détail que tu viens de donner.",
    "se_tait": "Une fois dans l'appel, tu laisses passer un long silence avant de répondre.",
}
PROBABILITE_COUPURE = 0.3


class SerieRefusee(ValueError):
    """La demande ne peut pas être lancée ; le message dit pourquoi, en anglais (écran)."""


_redis: aioredis.Redis | None = None


async def _client_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _cle_verrou(organization_id: int) -> str:
    return f"mark:appel-simule:serie:{organization_id}"


def _cle_arret(serie_id: str) -> str:
    return f"mark:appel-simule:arret:{serie_id}"


# --- Ce que reçoit le lanceur --------------------------------------------------------------------


def consigne_de_l_appelant(
    reglages: ReglagesAppelantSimule, scenario: ScenarioSimule
) -> str:
    morceaux = [
        reglages.appelant.consigne.strip(),
        f"Ton rôle : {scenario.role.strip()}",
    ]
    if scenario.consigne.strip():
        morceaux.append(scenario.consigne.strip())
    morceaux += [
        phrase
        for champ, phrase in COMPORTEMENTS.items()
        if getattr(scenario.comportements, champ)
    ]
    return "\n\n".join(morceaux)


def base_ws(endpoint: str = BACKEND_API_ENDPOINT) -> str:
    """L'adresse publique de l'API en WebSocket : le simulateur traverse le même chemin qu'un
    appel (réseau compris)."""
    if endpoint.startswith("https://"):
        return "wss://" + endpoint.removeprefix("https://")
    if endpoint.startswith("http://"):
        return "ws://" + endpoint.removeprefix("http://")
    return endpoint


def entree_du_lanceur(
    adresse: str, reglages: ReglagesAppelantSimule, scenario: ScenarioSimule
) -> dict:
    return {
        "adresse": adresse,
        "scenario": {
            "nom": scenario.nom,
            "description": scenario.role,
            "criteres": scenario.criteres,
            "tours_max": scenario.tours_max,
        },
        "appelant": {
            "modele": reglages.appelant.modele,
            "consigne": consigne_de_l_appelant(reglages, scenario),
            "voix": f"elevenlabs/{reglages.voix.voix}",
            "temperature": reglages.appelant.temperature,
            "coupe_la_parole": (
                PROBABILITE_COUPURE if scenario.comportements.coupe_la_parole else 0.0
            ),
        },
        "juge": {"modele": reglages.juge.modele, "consigne": reglages.juge.consigne},
    }


def environnement(cle_modele: str, cle_voix: str, dossier: str) -> dict[str, str]:
    """L'environnement du sous-processus, construit de zéro : rien de l'API n'y passe (aucune clé
    d'un autre service, aucune variable ``LANGWATCH_*``), seulement les deux clés choisies à
    l'écran et de quoi faire tourner Python. Scenario exige un répertoire personnel (son cache)."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": dossier,
        "SCENARIO_CACHE_DIR": dossier,
        "SCENARIO_HEADLESS": "true",
        "SCENARIO_DISABLE_SIMULATION_REPORT_INFO": "1",
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        "SIMULATEUR_CLE_MODELE": cle_modele,
        "ELEVENLABS_API_KEY": cle_voix,
    }


def lire_le_verdict(sortie: str) -> dict:
    lignes = [lg for lg in sortie.splitlines() if lg.startswith(MARQUE)]
    if not lignes:
        return {"error": "the simulator gave no verdict"}
    try:
        verdict = json.loads(lignes[-1].removeprefix(MARQUE))
    except json.JSONDecodeError:
        return {"error": "the simulator's verdict is unreadable"}
    return verdict if isinstance(verdict, dict) else {"error": "unexpected verdict"}


def _masquer(texte: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            texte = texte.replace(secret, "***")
    return texte


async def lancer_le_lanceur(
    entree: dict, env: dict[str, str], delai_s: float, secrets: list[str]
) -> dict:
    processus = await asyncio.create_subprocess_exec(
        PYTHON_SIMULATEUR,
        str(LANCEUR),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        sortie, erreurs = await asyncio.wait_for(
            processus.communicate(json.dumps(entree).encode()), timeout=delai_s
        )
    except asyncio.TimeoutError:
        processus.kill()
        await processus.wait()
        return {"error": f"the simulator did not finish within {int(delai_s)} s"}
    except BaseException:
        # Tâche annulée (arrêt du worker, délai de la tâche) : l'appel ne continue pas à
        # dépenser sans personne pour le suivre (revue du 05/10).
        if processus.returncode is None:
            processus.kill()
        raise
    if processus.returncode not in (0, 1):
        logger.warning(
            f"[appel simulé] lanceur sorti en {processus.returncode} : "
            f"{_masquer(erreurs.decode(errors='replace'), secrets)[-1500:]}"
        )
    verdict = lire_le_verdict(sortie.decode(errors="replace"))
    if "error" in verdict:
        verdict["error"] = _tronquer(_masquer(str(verdict["error"]), secrets))
    return verdict


def _tronquer(texte: str, debut: int = 150, fin: int = 650) -> str:
    """Le début (le type d'erreur) et la fin (souvent la raison du fournisseur), pas seulement les
    500 premiers caractères, qui étaient des en-têtes HTTP le 06/10."""
    if len(texte) <= debut + fin + 3:
        return texte
    return f"{texte[:debut]} … {texte[-fin:]}"


# --- Pendant et après l'appel --------------------------------------------------------------------


async def suivre_le_renvoi(run_id: int, decision: str, fin: asyncio.Event) -> None:
    """Donne la décision du scénario au renvoi simulé, s'il est demandé. « Sans réponse » : rien,
    le délai de l'outil expire et le renvoi échoue, comme un poste qui ne décroche pas."""
    if decision == "sans_reponse":
        return
    while not fin.is_set():
        try:
            if await renvoi_en_attente(run_id):
                await donner_la_decision(run_id, decision == "accepte")
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[appel simulé] renvoi du run {run_id} : {erreur!r}")
        try:
            await asyncio.wait_for(fin.wait(), timeout=INTERVALLE_S)
        except asyncio.TimeoutError:
            pass


async def attendre_la_fin_du_run(run_id: int, organization_id: int, delai_s: float):
    """Le run relu une fois terminé (état « completed »), ou tel quel au délai."""
    loop = asyncio.get_running_loop()
    fin = loop.time() + delai_s
    run = await db_client.get_workflow_run(run_id, organization_id=organization_id)
    while (
        run is not None
        and run.state != WorkflowRunState.COMPLETED.value
        and loop.time() < fin
    ):
        await asyncio.sleep(1)
        run = await db_client.get_workflow_run(run_id, organization_id=organization_id)
    return run


def cout_de_l_appelant(verdict: dict, duree_s: float | None, table) -> dict:
    """Ce que coûte le simulateur lui-même : sa voix (caractères dits) et la transcription de
    l'agent (bornée par la durée de l'appel), au tarif de la table ; ses appels au modèle ne
    sont pas comptés par Scenario et restent « unpriced »."""
    caracteres = sum(
        len(m.get("content") or "")
        for m in verdict.get("messages") or []
        if m.get("role") == "user"
    )
    prix = {(l.brique, l.modele.strip()): l for l in (table.lignes if table else [])}
    total, sans_prix = 0.0, ["llm: simulated caller and judge"]
    voix = prix.get(("tts", "eleven_v3"))
    if voix and voix.par_million_caracteres is not None:
        total += caracteres / 1_000_000 * voix.par_million_caracteres
    else:
        sans_prix.append("tts: eleven_v3")
    transcription = prix.get(("stt", "scribe_v1"))
    if transcription and transcription.par_minute is not None and duree_s:
        total += duree_s / 60 * transcription.par_minute
    else:
        sans_prix.append("stt: scribe_v1")
    return {"total": round(total, 4), "characters": caracteres, "unpriced": sans_prix}


def resultat_de_l_appel(
    verdict: dict, analyse: dict, scenario: ScenarioSimule, cout_appelant: dict
) -> dict:
    """Le verdict rangé dans le run : celui du juge, plus le seuil de latence du scénario."""
    latence = analyse.get("latency") or {}
    pire = (latence.get("stats") or {}).get("worst_silence_secs")
    echecs = list(verdict.get("failed_criteria") or [])
    reussi = bool(verdict.get("success")) and "error" not in verdict
    if (
        scenario.latence_max_s is not None
        and pire is not None
        and pire > scenario.latence_max_s
    ):
        reussi = False
        echecs.append(f"latency: worst turn {pire:.2f} s > {scenario.latence_max_s} s")
    cout_agent = (analyse.get("summary") or {}).get("cost") or {}
    return {
        "success": reussi,
        "error": verdict.get("error"),
        "reasoning": verdict.get("reasoning"),
        "passed_criteria": verdict.get("passed_criteria") or [],
        "failed_criteria": echecs,
        "messages": verdict.get("messages") or [],
        "worst_silence_secs": pire,
        "median_silence_secs": (latence.get("stats") or {}).get("median_silence_secs"),
        "incidents": len((analyse.get("incidents") or {}).get("items") or []),
        "agent_cost": cout_agent.get("total")
        if cout_agent.get("status") == "ok"
        else None,
        "agent_cost_partial": bool(cout_agent.get("partial"))
        or cout_agent.get("status") != "ok",
        "caller_cost": cout_appelant["total"],
        "caller_unpriced": cout_appelant["unpriced"],
        "total_time": verdict.get("total_time"),
    }


# --- Clés ----------------------------------------------------------------------------------------


async def cle_d_identifiant(
    organization_id: int, credential_uuid: str | None
) -> str | None:
    """La clé d'un identifiant enregistré dans Dograh, lu dans l'organisation (jamais ailleurs)."""
    if not credential_uuid:
        return None
    identifiant = await db_client.get_credential_by_uuid(
        credential_uuid, organization_id
    )
    if identifiant is None:
        return None
    donnees = identifiant.credential_data or {}
    for champ in ("api_key", "token", "header_value", "password"):
        valeur = donnees.get(champ)
        if isinstance(valeur, str) and valeur.strip():
            return valeur.strip()
    return None


def _cle_supprimee(quoi: str) -> str:
    """P16 : une clé choisie puis supprimée de la bibliothèque (ou inutilisable) se nomme."""
    return (
        f"The {quoi} chosen in the simulated caller settings was deleted or is unusable: "
        "pick another in « Keys »."
    )


async def _cles(
    organization_id: int, reglages: ReglagesAppelantSimule
) -> tuple[str, str]:
    if reglages.appelant.identifiant != reglages.juge.identifiant:
        raise SerieRefusee(
            "The simulated caller and the judge must use the same model key."
        )
    cle_modele = await cle_d_identifiant(organization_id, reglages.appelant.identifiant)
    if not cle_modele:
        raise SerieRefusee(
            _cle_supprimee("model key")
            if reglages.appelant.identifiant
            else "Choose the model key of the simulated caller in its settings."
        )
    cle_voix = await cle_d_identifiant(organization_id, reglages.voix.identifiant)
    if not cle_voix:
        raise SerieRefusee(
            _cle_supprimee("ElevenLabs key")
            if reglages.voix.identifiant
            else "Choose the ElevenLabs key of the simulated caller's voice."
        )
    if not reglages.voix.voix.strip():
        raise SerieRefusee("Choose the simulated caller's voice.")
    return cle_modele, cle_voix


# --- Lancer une série ----------------------------------------------------------------------------


PRIX_DU_SIMULATEUR = (("tts", "eleven_v3"), ("stt", "scribe_v1"))


def prix_manquants_du_simulateur(table) -> list[str]:
    """Sans ces prix, le coût d'un appel simulé vaudrait 0 et le plafond ne jouerait jamais
    (revue du 05/10) : la série est refusée tant qu'ils manquent."""
    if table is None:
        return [f"{brique} {modele}" for brique, modele in PRIX_DU_SIMULATEUR]
    presents = {(l.brique, l.modele.strip()) for l in table.lignes}
    return [f"{b} {m}" for b, m in PRIX_DU_SIMULATEUR if (b, m) not in presents]


def estimer_le_cout(
    series: list[SerieSimulee], workflow_id: int, nombre: int
) -> float | None:
    """Coût moyen des appels simulés déjà joués pour cet agent × nombre d'appels ; ``None`` tant
    qu'aucun n'a été joué (l'écran dit « unknown until the first call »)."""
    couts = [
        appel.cout
        for serie in series
        if serie.workflow_id == workflow_id
        for appel in serie.appels
        if appel.cout is not None
    ]
    if not couts:
        return None
    return round(statistics.fmean(couts) * nombre, 4)


async def lancer_serie(
    organization_id: int, user_id: int, workflow_id: int, scenario_ids: list[str]
) -> SerieSimulee:
    workflow = await db_client.get_workflow(
        workflow_id, organization_id=organization_id
    )
    if workflow is None:
        raise SerieRefusee("Agent not found.")
    reglages = await lire_reglages(organization_id)
    if not scenario_ids:
        raise SerieRefusee("Pick at least one scenario.")
    if len(scenario_ids) > reglages.taille_max_serie:
        raise SerieRefusee(
            f"A series is {reglages.taille_max_serie} calls at most (simulated caller settings)."
        )
    disponibles = {s.id: s for s in await lire_scenarios(organization_id, workflow_id)}
    inconnus = [i for i in scenario_ids if i not in disponibles]
    if inconnus:
        raise SerieRefusee("A scenario is not filed with this agent.")
    await _cles(organization_id, reglages)
    table = await lire_reglages_fenetre(organization_id)
    manquants = prix_manquants_du_simulateur(table)
    if manquants:
        raise SerieRefusee(
            "The spending cap needs prices: add "
            + ", ".join(manquants)
            + " to the run window's price table (organization settings)."
        )

    serie = SerieSimulee(
        id=str(uuid.uuid4()),
        workflow_id=workflow_id,
        lancee_le=maintenant(),
        lancee_par=user_id,
        plafond=reglages.plafond,
        devise=table.devise if table else "USD",
        cout_estime=estimer_le_cout(
            await lire_series(organization_id), workflow_id, len(scenario_ids)
        ),
        appels=[
            AppelDeSerie(scenario_id=i, scenario_nom=disponibles[i].nom)
            for i in scenario_ids
        ],
    )
    redis = await _client_redis()
    if not await redis.set(
        _cle_verrou(organization_id), serie.id, nx=True, ex=VERROU_S
    ):
        raise SerieRefusee("A series is already playing for this organization.")
    try:
        await ecrire_serie(organization_id, serie)
        from api.tasks.arq import enqueue_job
        from api.tasks.function_names import FunctionNames

        await enqueue_job(FunctionNames.JOUER_SERIE_SIMULEE, organization_id, serie.id)
    except Exception:
        await redis.delete(_cle_verrou(organization_id))
        raise
    return serie


async def arreter_serie(organization_id: int, serie_id: str) -> bool:
    serie = await lire_serie(organization_id, serie_id)
    if serie is None or serie.etat != "en_cours":
        return False
    await (await _client_redis()).set(_cle_arret(serie_id), "1", ex=VERROU_S)
    return True


# --- La tâche de fond ----------------------------------------------------------------------------


async def _jouer_un_appel(
    organization_id: int,
    workflow,
    serie: SerieSimulee,
    appel: AppelDeSerie,
    scenario: ScenarioSimule,
    reglages: ReglagesAppelantSimule,
    cles: tuple[str, str],
    table,
) -> None:
    run, jeton = await creer_run_simule(
        workflow,
        user_id=serie.lancee_par,
        organization_id=organization_id,
        simulation={
            "serie_id": serie.id,
            "scenario_id": scenario.id,
            "scenario_nom": scenario.nom,
        },
    )
    appel.run_id, appel.etat = run.id, "en_cours"
    await ecrire_serie(organization_id, serie)

    fin = asyncio.Event()
    renvoi = asyncio.create_task(suivre_le_renvoi(run.id, scenario.renvoi, fin))
    with tempfile.TemporaryDirectory(prefix="appel-simule-") as dossier:
        try:
            verdict = await lancer_le_lanceur(
                entree_du_lanceur(
                    adresse_ws(base_ws(), run.id, jeton), reglages, scenario
                ),
                environnement(*cles, dossier),
                delai_s=scenario.tours_max * DELAI_PAR_TOUR_S,
                secrets=[*cles, jeton],
            )
        finally:
            fin.set()
            await renvoi

    lu = await db_client.get_workflow_run(run.id, organization_id=organization_id)
    if (
        "error" in verdict
        and lu is not None
        and lu.state == WorkflowRunState.INITIALIZED.value
    ):
        # Le simulateur ne s'est jamais branché : rien à attendre, le run est clos en échec.
        await mark_workflow_run_failed(run.id, "The simulated caller never connected")
    else:
        lu = await attendre_la_fin_du_run(run.id, organization_id, DELAI_FIN_DU_RUN_S)
    analyse = await analyser_le_run(lu, organization_id) if lu is not None else {}
    duree = ((lu.usage_info or {}) if lu is not None else {}).get(
        "call_duration_seconds"
    )
    resultat = resultat_de_l_appel(
        verdict, analyse, scenario, cout_de_l_appelant(verdict, duree, table)
    )
    extra = dict((lu.extra if lu is not None else None) or {})
    simulation = dict(extra.get(CLE_EXTRA) or {})
    simulation["resultat"] = resultat
    await db_client.update_workflow_run(run_id=run.id, extra={CLE_EXTRA: simulation})

    appel.etat = "echec" if resultat["error"] else "joue"
    appel.reussi = None if resultat["error"] else resultat["success"]
    appel.erreur = resultat["error"]
    appel.cout = round((resultat["agent_cost"] or 0) + resultat["caller_cost"], 4)
    serie.cout = round(serie.cout + appel.cout, 4)
    if resultat["agent_cost_partial"] and not resultat["error"]:
        # Un modèle de l'agent sans prix : le coût compté serait faux, le plafond aussi.
        serie.etat = "arretee"
        serie.raison = (
            "the agent's cost could not be fully priced (a model is missing from the "
            "price table): the cap could not be guaranteed"
        )
    serie.cout_partiel = (
        True  # les appels au modèle du simulateur ne sont jamais chiffrés
    )


async def jouer_serie(organization_id: int, serie_id: str) -> None:
    redis = await _client_redis()
    serie = await lire_serie(organization_id, serie_id)
    try:
        if serie is None or serie.etat != "en_cours":
            return
        reglages = await lire_reglages(organization_id)
        workflow = await db_client.get_workflow(
            serie.workflow_id, organization_id=organization_id
        )
        if workflow is None:
            raise SerieRefusee("Agent not found.")
        cles = await _cles(organization_id, reglages)
        table = await lire_reglages_fenetre(organization_id)
        scenarios = {
            s.id: s for s in await lire_scenarios(organization_id, serie.workflow_id)
        }
        places = asyncio.Semaphore(reglages.simultanes)
        verrou_serie = asyncio.Lock()
        en_vol = [0]  # appels partis, pas encore comptés
        un_appel_fini = asyncio.Event()

        async def autoriser() -> bool:
            """Le plafond compte aussi les appels en cours (revue du 05/10) ; tant qu'aucun
            appel n'est fini, son coût est inconnu : un seul appel en vol à la fois."""
            while True:
                async with verrou_serie:
                    if await redis.get(_cle_arret(serie.id)):
                        serie.etat, serie.raison = "arretee", "stopped from the screen"
                    if serie.etat != "en_cours":
                        return False
                    joues = [a.cout for a in serie.appels if a.cout is not None]
                    if joues or en_vol[0] == 0:
                        prochain = statistics.fmean(joues) if joues else 0.0
                        if serie.cout + (en_vol[0] + 1) * prochain > serie.plafond:
                            serie.etat = "arretee_plafond"
                            serie.raison = f"the next call would exceed the cap ({serie.plafond} {serie.devise})"
                            return False
                        en_vol[0] += 1
                        return True
                    un_appel_fini.clear()
                await un_appel_fini.wait()

        async def un_appel(appel: AppelDeSerie) -> None:
            async with places:
                if not await autoriser():
                    return
                try:
                    await jouer_l_appel(appel)
                finally:
                    async with verrou_serie:
                        en_vol[0] -= 1
                        un_appel_fini.set()
                        await ecrire_serie(organization_id, serie)

        async def jouer_l_appel(appel: AppelDeSerie) -> None:
            scenario = scenarios.get(appel.scenario_id)
            if scenario is None:
                appel.etat, appel.erreur = "echec", "scenario deleted"
                return
            try:
                await _jouer_un_appel(
                    organization_id,
                    workflow,
                    serie,
                    appel,
                    scenario,
                    reglages,
                    cles,
                    table,
                )
            except Exception as erreur:  # noqa: BLE001
                logger.error(
                    f"[appel simulé] série {serie.id} : {erreur!r}", exc_info=True
                )
                appel.etat, appel.erreur = "echec", type(erreur).__name__

        await asyncio.gather(*(un_appel(a) for a in serie.appels))
        if serie.etat == "en_cours":
            serie.etat = "terminee"
    except asyncio.CancelledError:
        # Worker arrêté ou délai de la tâche atteint : la série ne reste pas « en cours ».
        if serie is not None:
            serie.etat, serie.raison = "echec", "interrupted (worker stopped)"
        raise
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[appel simulé] série {serie_id} : {erreur!r}", exc_info=True)
        if serie is not None:
            serie.etat = "echec"
            serie.raison = (
                str(erreur)
                if isinstance(erreur, SerieRefusee)
                else type(erreur).__name__
            )
    finally:
        if serie is not None:
            serie.terminee_le = maintenant()
            await ecrire_serie(organization_id, serie)
        # Le verrou n'est rendu que s'il est bien celui de CETTE série.
        if await redis.get(_cle_verrou(organization_id)) == serie_id:
            await redis.delete(_cle_verrou(organization_id))
        await redis.delete(_cle_arret(serie_id))
