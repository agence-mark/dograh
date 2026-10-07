"""[.mark] The after-call chain of a run (A1, A9, A10).

``demarrer(run_id)`` is called at the end of every call (``process_workflow_completion``):
an agent that did not switch the after-call on is left alone (X2, one read). Otherwise
every step is recorded « waiting » on the run and the chain is queued on arq.

``executer(run_id, etapes, tentative)`` runs the steps in order. Each step:

- already « ok » → not redone (a replayed job sends nothing twice);
- succeeds → « ok », with what it did;
- fails → « echec »; the NEXT steps still run (A10). A failure that may pass is retried
  alone, later (``DELAIS_S``); at the last attempt, or when retrying cannot help (a
  setting is missing), it is FINAL: red on screen and mailed to the notification
  addresses (A5). Never silent (R1).

The organization is the one of the run's agent, read on the server; nothing the call
carries chooses it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger

from api.db import db_client
from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.schemas.apres_appel import ETAPES, ApresAppelAgent, ReglagesApresAppel
from api.services.apres_appel import mail as service_mail
from api.services.apres_appel import synthese as service_synthese
from api.services.apres_appel.envoi import construire_envoi
from api.services.apres_appel.modules import (
    MODULES,
    ContexteModule,
    ModuleEnEchec,
    ModuleSansObjet,
)
from api.services.apres_appel.notification import notifier
from api.services.apres_appel.reglages import (
    CleManquante,
    lire_reglages,
    reglages_de_lagent,
    secret,
)
from api.services.base_client.rattachement import nom_de_la_base

TENTATIVES_MAX = 3
DELAIS_S = (60, 300)  # after the 1st and the 2nd attempt
NOM_TACHE = "apres_appel_mark"


class EtapeEnEchec(RuntimeError):
    def __init__(self, message: str, definitif: bool = False):
        super().__init__(message)
        self.definitif = definitif


class EtapeSansObjet(RuntimeError):
    """Nothing to do for this call: « skipped », with the reason."""


def etapes_de(agent: ApresAppelAgent) -> list[str]:
    etapes = ["ecriture"]
    if agent.synthese:
        etapes.append("synthese")
    if agent.mail:
        etapes.append("mail")
    return etapes + [f"module:{m}" for m in agent.modules]


def _maintenant() -> str:
    return datetime.now(UTC).isoformat()


async def _charger(run_id: int):
    run, organization_id = await db_client.get_workflow_run_with_context(run_id)
    if run is None or organization_id is None or run.definition is None:
        return None, None, None
    return (
        run,
        organization_id,
        reglages_de_lagent(run.definition.workflow_configurations),
    )


async def demarrer(run_id: int, enqueue=None) -> bool:
    """Queue the chain if the run's agent switched it on. Never raises."""
    try:
        run, organization_id, agent = await _charger(run_id)
        if run is None or not agent.actif:
            return False
        etapes = etapes_de(agent)
        await db_client.fusionner_apres_appel(
            run_id, racine={"actif": True, "lance_le": _maintenant()}
        )
        for etape in etapes:
            await db_client.fusionner_apres_appel(
                run_id,
                etape=etape,
                valeur={"statut": "en_attente", "tentatives": 0, "le": _maintenant()},
            )
        if enqueue is None:
            from api.tasks.arq import enqueue_job

            enqueue = enqueue_job
        await enqueue(NOM_TACHE, run_id, etapes, 1, _job_id=f"apres-appel-{run_id}")
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] After-call of run {run_id} not started: {erreur!r}")
        return False


# --------------------------------------------------------------------------- #
# The steps
# --------------------------------------------------------------------------- #


async def _base(organization_id: int):
    nom = await nom_de_la_base(organization_id)
    if not nom:
        raise EtapeEnEchec(
            "No client database is attached to this organization (« Client data »).",
            definitif=True,
        )
    try:
        return await connecter(nom)
    except BaseClientIndisponible as erreur:
        raise EtapeEnEchec(str(erreur)) from None


async def _ecriture(ctx: ContexteModule, bloc: dict) -> dict:
    connexion = await _base(ctx.organization_id)
    try:
        resultat = await sql.recevoir_appel(connexion, ctx.envoi)
        # A summary made while the write was failing is written now.
        if (
            bloc.get("synthese")
            and not bloc.get("synthese_ecrite")
            and resultat.get("appel_id")
        ):
            await sql.ecrire_synthese(connexion, resultat["appel_id"], bloc["synthese"])
            resultat["synthese_ecrite"] = True
    except Exception as erreur:  # noqa: BLE001
        raise EtapeEnEchec(
            f"The client's database refused the call ({type(erreur).__name__}: {erreur})."
        ) from None
    finally:
        await connexion.close()
    racine = {
        "appel_id": resultat.get("appel_id"),
        "demande_id": resultat.get("demande_id"),
        "autre_demande_ouverte_id": resultat.get("autre_demande_ouverte_id"),
    }
    if resultat.get("synthese_ecrite"):
        racine["synthese_ecrite"] = True
    detail = (
        "already written (replay)"
        if resultat.get("doublon")
        else (
            f"call {resultat.get('appel_id')}"
            + (
                f", request {resultat['demande_id']}"
                if resultat.get("demande_id")
                else ", no request"
            )
        )
    )
    return {"racine": racine, "detail": detail}


async def _synthese(ctx: ContexteModule, bloc: dict, analyse: dict) -> dict:
    try:
        cle = await secret(
            ctx.reglages.synthese.cle, ctx.organization_id, "mistral", "the summary"
        )
    except CleManquante as erreur:
        raise EtapeEnEchec(str(erreur), definitif=True) from None
    lignes = (analyse.get("conversation") or {}).get("lines") or []
    fiche = {c["nom"]: c["valeur"] for c in ctx.envoi.get("champs") or []}
    try:
        texte, _usage = await service_synthese.resumer(
            cle, ctx.reglages.synthese, lignes, fiche
        )
    except service_synthese.SyntheseImpossible as erreur:
        if not any(l.get("text") for l in lignes):
            raise EtapeSansObjet(str(erreur)) from None
        raise EtapeEnEchec(str(erreur)) from None
    racine = {"synthese": texte, "synthese_ecrite": False}
    appel_id = bloc.get("appel_id")
    if appel_id:
        try:
            connexion = await _base(ctx.organization_id)
            try:
                await sql.ecrire_synthese(connexion, appel_id, texte)
                racine["synthese_ecrite"] = True
            finally:
                await connexion.close()
        except Exception as erreur:  # noqa: BLE001 -- the write step will write it later
            logger.warning(
                f"[.mark] Summary of run {ctx.run.id} not written yet: {erreur!r}"
            )
    return {"racine": racine, "detail": ctx.reglages.synthese.modele}


def _heure_locale(iso: str | None, fuseau: str | None) -> str:
    try:
        moment = datetime.fromisoformat(iso or "")
        return moment.astimezone(ZoneInfo(fuseau or "Europe/Paris")).strftime(
            "%d/%m/%Y à %H:%M"
        )
    except Exception:  # noqa: BLE001
        return (iso or "")[:16].replace("T", " ")


def texte_du_mail(ctx: ContexteModule, bloc: dict) -> tuple[str, str]:
    envoi = ctx.envoi
    motif = envoi.get("motif") or "—"
    sujet = f"Nouvelle demande : {motif}"[:150]
    lignes = [
        f"Appel du {_heure_locale(envoi.get('debut'), ctx.fuseau)}",
        f"Numéro : {envoi.get('numero_appelant') or 'inconnu'}",
    ]
    if bloc.get("autre_demande_ouverte_id"):
        lignes.append(
            f"⚠ Une autre demande ouverte vient du même numéro (n° {bloc['autre_demande_ouverte_id']})."
        )
    lignes.append("")
    lignes.append("Résumé :")
    lignes.append(bloc.get("synthese") or "(résumé indisponible)")
    lignes.append("")
    lignes.append("Fiche :")
    for champ in envoi.get("champs") or []:
        lignes.append(f"- {champ['nom']} : {champ['valeur']}")
    if bloc.get("demande_id"):
        lignes.append("")
        lignes.append(
            f"Demande n° {bloc['demande_id']}, appel n° {bloc.get('appel_id')}."
        )
    return sujet, "\n".join(lignes)


async def _mail(ctx: ContexteModule, bloc: dict) -> dict:
    if not ctx.envoi.get("demande"):
        raise EtapeSansObjet("No request in this call (nothing noted).")
    connexion = await _base(ctx.organization_id)
    try:
        destinataires = await sql.destinataires_de(
            connexion,
            (ctx.envoi.get("demande") or {}).get("sujet"),
            ctx.envoi.get("etablissement"),
        )
        if not destinataires:
            raise EtapeEnEchec(
                "No recipient for this request: route its subject, or mark a default recipient (« Team and routing »).",
                definitif=True,
            )
        adresses = [d["mail"] for d in destinataires]
        sujet, texte = texte_du_mail(ctx, bloc)
        try:
            await service_mail.envoyer(
                ctx.reglages.smtp, ctx.organization_id, adresses, sujet, texte
            )
        except service_mail.MailImpossible as erreur:
            definitif = erreur.definitif
            for adresse in adresses:
                await sql.noter_action(
                    connexion,
                    appel_id=bloc.get("appel_id"),
                    demande_id=bloc.get("demande_id"),
                    canal="mail",
                    destinataire=adresse,
                    statut="echec",
                    erreur=str(erreur),
                    reessais=ctx.tentative - 1,
                )
            raise EtapeEnEchec(str(erreur), definitif=definitif) from None
        for adresse in adresses:
            await sql.noter_action(
                connexion,
                appel_id=bloc.get("appel_id"),
                demande_id=bloc.get("demande_id"),
                canal="mail",
                destinataire=adresse,
                statut="envoyee",
                reessais=ctx.tentative - 1,
            )
    finally:
        await connexion.close()
    return {
        "detail": ", ".join(adresses),
        "envois": [
            {"canal": "mail", "destinataire": a, "statut": "envoyee"} for a in adresses
        ],
    }


async def _module(nom: str, ctx: ContexteModule, bloc: dict) -> dict:
    executeur = MODULES.get(nom)
    if executeur is None:
        raise EtapeEnEchec(f"Unknown module « {nom} ».", definitif=True)
    ctx.ecriture = {k: bloc.get(k) for k in ("appel_id", "demande_id")}
    ctx.synthese = bloc.get("synthese")
    try:
        resultat = await executeur(ctx)
    except ModuleSansObjet as erreur:
        raise EtapeSansObjet(str(erreur)) from None
    except ModuleEnEchec as erreur:
        raise EtapeEnEchec(str(erreur), definitif=erreur.definitif) from None
    if bloc.get("appel_id"):
        try:
            connexion = await _base(ctx.organization_id)
            try:
                for e in resultat.envois:
                    if e.get("deja"):  # sent by an earlier try: its row is already there
                        continue
                    await sql.noter_action(
                        connexion,
                        appel_id=bloc.get("appel_id"),
                        demande_id=bloc.get("demande_id"),
                        canal=e["canal"],
                        destinataire=e.get("destinataire"),
                        statut=e.get("statut", "envoyee"),
                        reessais=ctx.tentative - 1,
                    )
            finally:
                await connexion.close()
        except Exception as erreur:  # noqa: BLE001 -- the sending is done; its row is a trace
            logger.warning(
                f"[.mark] Action row of module {nom} not written: {erreur!r}"
            )
    return {"detail": resultat.detail, "envois": resultat.envois}


# --------------------------------------------------------------------------- #
# The chain
# --------------------------------------------------------------------------- #


async def executer(
    run_id: int, etapes: list[str] | None = None, tentative: int = 1, enqueue=None
) -> dict:
    """Run these steps (all the agent's when None). Returns the block as recorded."""
    run, organization_id, agent = await _charger(run_id)
    if run is None:
        logger.warning(f"[.mark] After-call: run {run_id} not found")
        return {}
    if not agent.actif:
        return await db_client.lire_apres_appel(run_id)
    from api.services.analyse_run.du_run import analyser_le_run

    reglages: ReglagesApresAppel = await lire_reglages(organization_id)
    analyse = await analyser_le_run(run, organization_id)
    sujets: list[dict] = []
    try:
        connexion = await _base(organization_id)
        try:
            sujets = await sql.sujets_actifs(connexion)
        finally:
            await connexion.close()
    except Exception:  # noqa: BLE001 -- the write step reports the database
        pass
    envoi = construire_envoi(run, analyse, agent, sujets)
    from api.services.apres_appel.taches import _fuseau

    contexte = ContexteModule(
        organization_id=organization_id,
        run=run,
        reglages=reglages,
        agent=agent,
        envoi=envoi,
        tentative=tentative,
    )
    contexte.fuseau = str(await _fuseau(organization_id))
    for etape in etapes or etapes_de(agent):
        bloc = await db_client.lire_apres_appel(run_id)
        if ((bloc.get("etapes") or {}).get(etape) or {}).get("statut") == "ok":
            continue
        await db_client.fusionner_apres_appel(
            run_id,
            etape=etape,
            valeur={"statut": "en_cours", "tentatives": tentative, "le": _maintenant()},
        )
        try:
            if etape == "ecriture":
                fait = await _ecriture(contexte, bloc)
            elif etape == "synthese":
                fait = await _synthese(contexte, bloc, analyse)
            elif etape == "mail":
                fait = await _mail(contexte, bloc)
            elif etape.startswith("module:"):
                fait = await _module(etape.split(":", 1)[1], contexte, bloc)
            else:
                raise EtapeEnEchec(f"Unknown step « {etape} ».", definitif=True)
        except EtapeSansObjet as raison:
            await db_client.fusionner_apres_appel(
                run_id,
                etape=etape,
                valeur={
                    "statut": "ignoree",
                    "detail": str(raison),
                    "definitive": True,
                    "le": _maintenant(),
                },
            )
            continue
        except Exception as erreur:  # noqa: BLE001 -- A10: the next steps still run
            definitif = (
                getattr(erreur, "definitif", False) or tentative >= TENTATIVES_MAX
            )
            message = (
                str(erreur)
                if isinstance(erreur, EtapeEnEchec)
                else f"{type(erreur).__name__}: {erreur}"
            )
            prochaine = None
            if not definitif:
                delai = DELAIS_S[min(tentative - 1, len(DELAIS_S) - 1)]
                prochaine = (datetime.now(UTC) + timedelta(seconds=delai)).isoformat()
            await db_client.fusionner_apres_appel(
                run_id,
                etape=etape,
                valeur={
                    "statut": "echec",
                    "detail": message,
                    "definitive": definitif,
                    "prochaine_tentative": prochaine,
                    "le": _maintenant(),
                },
            )
            if definitif:
                await _signaler(organization_id, run, etape, message, tentative)
            else:
                await _reessayer(run_id, etape, tentative + 1, delai, enqueue)
            continue
        await db_client.fusionner_apres_appel(
            run_id,
            etape=etape,
            valeur={
                "statut": "ok",
                "detail": fait.get("detail"),
                "definitive": True,
                "envois": fait.get("envois") or [],
                "prochaine_tentative": None,
                "le": _maintenant(),
            },
            racine=fait.get("racine"),
        )
    return await db_client.lire_apres_appel(run_id)


async def _reessayer(
    run_id: int, etape: str, tentative: int, delai: int, enqueue=None
) -> None:
    if enqueue is None:
        from api.tasks.arq import enqueue_job

        enqueue = enqueue_job
    try:
        await enqueue(
            NOM_TACHE,
            run_id,
            [etape],
            tentative,
            _job_id=f"apres-appel-{run_id}-{etape}-{tentative}",
            _defer_by=delai,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Retry of step {etape} of run {run_id} not queued: {erreur!r}"
        )


async def _signaler(
    organization_id: int, run, etape: str, message: str, tentative: int
) -> None:
    from api.constants import UI_APP_URL

    lien = f"{UI_APP_URL}/workflow/{run.workflow_id}/run/{run.id}" if UI_APP_URL else ""
    texte = (
        f"L'étape « {etape} » de l'après-appel a échoué définitivement ({tentative} tentative(s)).\n"
        f"Agent : {getattr(run.workflow, 'name', run.workflow_id)} · appel n° {run.id}\n"
        f"Cause : {message}\n\n"
        f"Le détail et le bouton « Retry » sont dans la section « After the call » de la fenêtre du run.\n{lien}"
    )
    envoyes = await notifier(
        organization_id, f"Après-appel en échec : {etape}, appel {run.id}", texte
    )
    await db_client.fusionner_apres_appel(
        run.id, etape=etape, valeur={"notifie_a": envoyes, "notifie_le": _maintenant()}
    )


async def relancer(run_id: int, etape: str, enqueue=None) -> None:
    """« Retry » on screen: the step again, its attempts counted from 1."""
    if enqueue is None:
        from api.tasks.arq import enqueue_job

        enqueue = enqueue_job
    await db_client.fusionner_apres_appel(
        run_id,
        etape=etape,
        valeur={"statut": "en_attente", "tentatives": 0, "le": _maintenant()},
    )
    await enqueue(
        NOM_TACHE,
        run_id,
        [etape],
        1,
        _job_id=f"apres-appel-{run_id}-{etape}-manuel-{int(datetime.now(UTC).timestamp())}",
    )


async def tache_apres_appel(
    _ctx, run_id: int, etapes: list[str] | None = None, tentative: int = 1
) -> None:
    """The arq job."""
    try:
        await executer(run_id, etapes, tentative)
    except Exception as erreur:
        logger.error(f"[.mark] After-call of run {run_id} interrupted: {erreur!r}")
        raise


__all__ = [
    "ETAPES",
    "demarrer",
    "executer",
    "relancer",
    "tache_apres_appel",
    "texte_du_mail",
]
