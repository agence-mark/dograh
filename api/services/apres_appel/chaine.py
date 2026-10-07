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
# Decision of Evan, 07/10 (point 3): the test calls, kept out of the after-call by default.
MODES_ESSAI = frozenset({"smallwebrtc", "webrtc", "textchat", "simulated"})
SUJET_PANNE = "À rappeler : appel perdu par une panne"
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


async def _panne_a_ecrire(run, organization_id: int) -> bool:
    panne = (run.gathered_context or {}).get("panne")
    if not (isinstance(panne, dict) and panne.get("a_rappeler")):
        return False
    return bool(await nom_de_la_base(organization_id))


async def _etapes_a_jouer(
    run, organization_id: int, agent: ApresAppelAgent
) -> list[str]:
    """The steps of this run, or [] when the chain does not concern it. ONE rule, read by
    ``demarrer`` and by ``executer`` alike (revue 2)."""
    if est_un_essai_exclu(run, agent):
        return []
    if agent.actif:
        return etapes_de(agent)
    if await _panne_a_ecrire(run, organization_id):
        # L7 (PN1): the outage fallback writes its request « to call back » even for an
        # agent whose after-call is off, as soon as a client database is attached.
        return ["ecriture"]
    return []


def est_un_essai_exclu(run, agent: ApresAppelAgent) -> bool:
    return getattr(run, "mode", None) in MODES_ESSAI and not agent.essais


def _ok(bloc: dict, etape: str) -> bool:
    return ((bloc.get("etapes") or {}).get(etape) or {}).get("statut") == "ok"


async def demarrer(run_id: int, enqueue=None) -> bool:
    """Queue the chain if the run's agent switched it on. Never raises.

    Played again for the same run (``process_workflow_completion`` replayed): a step already
    « ok » is never reset nor queued again (revue 3)."""
    try:
        run, organization_id, agent = await _charger(run_id)
        if run is None:
            return False
        etapes = await _etapes_a_jouer(run, organization_id, agent)
        if not etapes:
            if agent.actif and est_un_essai_exclu(run, agent):
                # Said on the run's « After the call » section, never silent.
                await db_client.fusionner_apres_appel(
                    run_id, racine={"essai": True, "le": _maintenant()}
                )
            return False
        bloc = await db_client.lire_apres_appel(run_id)
        etapes = [e for e in etapes if not _ok(bloc, e)]
        if not etapes:
            return True
        if not bloc.get("lance_le"):
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
        # l-agent-collegue, L2 (C8, C10): the assignee and the transfers, idempotent.
        if ctx.envoi.get("equipe"):
            from api.db.bases_clients.gestes import ecrire_gestes

            await ecrire_gestes(
                connexion,
                resultat.get("appel_id"),
                resultat.get("demande_id"),
                ctx.envoi["equipe"].get("assignee"),
                ctx.envoi["equipe"].get("gestes") or [],
            )
        # l-agent-collegue, L4 (H6): the appointments booked during the call, idempotent.
        if (ctx.envoi.get("hub") or {}).get("rendez_vous"):
            from api.db.bases_clients.hub import ecrire_rendez_vous

            await ecrire_rendez_vous(
                connexion,
                resultat.get("appel_id"),
                resultat.get("demande_id"),
                resultat.get("contact_id"),
                ctx.envoi["hub"]["rendez_vous"],
            )
        # l-agent-collegue, L6 (V6): every verification attempt, idempotent.
        if ctx.envoi.get("verifications"):
            from api.db.bases_clients.dossier import ecrire_verifications

            await ecrire_verifications(
                connexion, resultat.get("appel_id"), ctx.envoi["verifications"]
            )
        # A summary made while the write was failing is written now.
        if (
            bloc.get("synthese")
            and not bloc.get("synthese_ecrite")
            and resultat.get("appel_id")
        ):
            await sql.ecrire_synthese(connexion, resultat["appel_id"], bloc["synthese"])
            resultat["synthese_ecrite"] = True
        # l-agent-collegue, L3 (C11, C12): the names of the team cited in the record (and in
        # a summary already made), only with the agent's switch on.
        await _mentions_des_noms(
            ctx,
            connexion,
            resultat.get("appel_id"),
            _textes_a_lire(ctx) + ([bloc["synthese"]] if bloc.get("synthese") else []),
        )
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
            cle,
            ctx.reglages.synthese,
            lignes,
            fiche,
            noms_equipe=await _noms_de_lequipe(ctx),
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
                # l-agent-collegue, L3 (C12): the names the summary cites.
                await _mentions_des_noms(ctx, connexion, appel_id, [texte])
            finally:
                await connexion.close()
        except Exception as erreur:  # noqa: BLE001 -- the write step will write it later
            logger.warning(
                f"[.mark] Summary of run {ctx.run.id} not written yet: {erreur!r}"
            )
    return {"racine": racine, "detail": ctx.reglages.synthese.modele}


def _equipe_active(ctx: ContexteModule) -> bool:
    """X2: the mentions found by name, and the recipients' mentions, only when the agent's
    « Team known to the agent » is on."""
    from api.services.equipe.appel import interrupteur_allume

    definition = getattr(ctx.run, "definition", None)
    return interrupteur_allume(getattr(definition, "workflow_configurations", None))


def _textes_a_lire(ctx: ContexteModule) -> list[str]:
    from api.services.equipe.mentions import textes_de_la_fiche

    return textes_de_la_fiche(ctx.envoi.get("champs") or [], ctx.agent)


async def _mentions_des_noms(ctx: ContexteModule, connexion, appel_id, textes: list[str]) -> None:
    """L3 (C11 to C13): ``nom_cite`` mentions. Never fails the step: a mention not written
    is logged (the call and its summary are what the step is for)."""
    if not appel_id or not _equipe_active(ctx):
        return
    try:
        from api.db.bases_clients.equipe import lire_equipe
        from api.db.bases_clients.gestes import ecrire_mentions
        from api.services.equipe.mentions import mentions_des_noms

        personnes = [p for p in (await lire_equipe(connexion)).personnes if p.actif]
        await ecrire_mentions(connexion, appel_id, mentions_des_noms(personnes, textes))
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] Mentions of run {ctx.run.id} not written: {erreur!r}")


async def _noms_de_lequipe(ctx: ContexteModule) -> list[str]:
    """l-agent-collegue, C6: the team's names for the summary, only when the agent's
    « Team known to the agent » is on (X2). Read from the in-memory copy; never raises."""
    from api.services.equipe.appel import interrupteur_allume, noms_pour_la_synthese

    definition = getattr(ctx.run, "definition", None)
    if not interrupteur_allume(getattr(definition, "workflow_configurations", None)):
        return []
    try:
        from api.services.etablissements.copie import lire_copie_complete

        return noms_pour_la_synthese(
            (await lire_copie_complete(ctx.organization_id)).equipe
        )
    except Exception as erreur:  # noqa: BLE001 -- the summary goes on without the names
        logger.warning(f"[.mark] Team names not given to the summary: {erreur!r}")
        return []


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
    if (envoi.get("demande") or {}).get("nee_d_une_panne"):
        # Decision of Evan, 07/10 (form, point 7). The mails are written in French.
        sujet = SUJET_PANNE
    elif (envoi.get("demande") or {}).get("a_rappeler"):
        # l-agent-collegue, R-3 and V6: a call-back to make, said in the subject.
        sujet = f"À rappeler : {motif}"[:150]
    lignes = [
        f"Appel du {_heure_locale(envoi.get('debut'), ctx.fuseau)}",
        f"Numéro : {envoi.get('numero_appelant') or 'inconnu'}",
    ]
    if (envoi.get("demande") or {}).get("a_rappeler") and (envoi.get("demande") or {}).get("resume"):
        lignes.append(f"À faire : {envoi['demande']['resume']}")
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
        # l-agent-collegue, C8: a request passed on to a person goes to her first; the
        # routing by subject only when she has no mail (or is no longer active).
        from api.db.bases_clients.gestes import destinataire_assigne

        destinataires = await destinataire_assigne(
            connexion, (ctx.envoi.get("demande") or {}).get("assignee")
        ) or await sql.destinataires_de(
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
        deja = ((bloc.get("etapes") or {}).get("mail") or {}).get("envoye_a")
        if deja:
            # Revue 4 (A10): the mail left at an earlier try; never send it again, only
            # write its rows if that is what failed.
            adresses = list(deja)
            if not ((bloc.get("etapes") or {}).get("mail") or {}).get("actions_notees"):
                await _noter_mails(ctx, bloc, connexion, adresses)
            return _mail_fait(adresses)
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
        # Marked as sent on the run BEFORE anything else can fail.
        await db_client.fusionner_apres_appel(
            ctx.run.id,
            etape="mail",
            valeur={"envoye_a": adresses, "envoye_le": _maintenant()},
        )
        await _noter_mails(ctx, bloc, connexion, adresses)
        # l-agent-collegue, L3 (C11): the people the mail went to are certain mentions.
        if bloc.get("appel_id") and _equipe_active(ctx):
            from api.db.bases_clients.gestes import ecrire_mentions
            from api.services.equipe.mentions import mentions_des_destinataires

            try:
                await ecrire_mentions(
                    connexion, bloc["appel_id"], mentions_des_destinataires(destinataires)
                )
            except Exception as erreur:  # noqa: BLE001 -- the mail left: never resend it
                logger.error(f"[.mark] Recipient mentions of run {ctx.run.id} not written: {erreur!r}")
    finally:
        await connexion.close()
    return _mail_fait(adresses)


async def _noter_mails(
    ctx: ContexteModule, bloc: dict, connexion, adresses: list[str]
) -> None:
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
    await db_client.fusionner_apres_appel(
        ctx.run.id, etape="mail", valeur={"actions_notees": True}
    )


def _mail_fait(adresses: list[str]) -> dict:
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
                    if e.get(
                        "deja"
                    ):  # sent by an earlier try: its row is already there
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
    permises = await _etapes_a_jouer(run, organization_id, agent)
    if not permises:
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
    for etape in [e for e in (etapes or permises) if e in permises]:
        bloc = await db_client.lire_apres_appel(run_id)
        if _ok(bloc, etape):
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
