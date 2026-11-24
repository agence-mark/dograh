"""[.mark] Chantier Partie 1, lot 17 : la diffusion d'une version du gabarit (D11, D59), les retouches d'un agent, le rodage (D28) et le
forçage de la porte réservé à l'équipe .mark (D32).

**Diffuser** une version à tous les agents installés depuis le gabarit, d'UNE organisation ou de TOUTES :

* la portée « toutes les organisations » est réservée à un rôle de l'équipe .mark qui porte ``gabarits.diffuser_toutes_organisations`` (jamais une
  clé d'API) ; sans elle, refus 403, journalisé ; la portée « une organisation » reste soumise au cloisonnement habituel (l'organisation de la
  session) ;
* refusée tant que la porte d'acceptation (les tests obligatoires) d'un seul client visé n'est pas verte ;
* sans écraser les retouches propres d'un agent : par texte (prompt, accueil), outils et sorties, une fusion à trois (ce que l'ancienne version
  avait installé, ce que l'agent porte, ce que la nouvelle installe) ; une retouche sur un morceau que la nouvelle version change aussi est un
  CONFLIT, qui refuse la diffusion pour cet agent, avec la raison ;
* elle écrit la nouvelle version dans une branche de brouillon par agent (la principale reste protégée) ; la publication passe ensuite par la
  porte (les tests rejoués sur ce brouillon), c'est l'arrêt « déploiement » ;
* journalisée : qui, quoi, quand, portée, résultat agent par agent (``mark_gabarit_diffusions`` et le journal de l'équipe).
"""

from __future__ import annotations

import copy
from typing import Any

from loguru import logger

from api.db import db_client
from api.db.gabarits_client import CLE_DES_IDENTIFIANTS, etapes_de
from api.services.gabarits import formulaire as F
from api.services.gabarits.forme import FormeAMonter, exiger_la_forme_actuelle
from api.services.gabarits import gabarit as G
from api.services.gabarits import installation as I
from api.services.gabarits import styles as ST
from api.services.gabarits import trous as T

PERMISSION_TOUTES = "gabarits.diffuser_toutes_organisations"
PORTEES = ("organisation", "toutes")
NOM_DE_BRANCHE = "Gabarit {nom} v{version}"


class RefusDiffusion(Exception):
    def __init__(self, statut: int, code: str, message: str):
        super().__init__(message)
        self.statut = statut
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- les retouches d'un agent


def _morceaux(forme: dict[str, Any]) -> dict[str, Any]:
    """Les morceaux comparés : chaque nœud (texte, accueil, outils) et l'ensemble des sorties."""
    morceaux = {f"noeud:{i}": n for i, n in (forme.get("noeuds") or {}).items()}
    morceaux["sorties"] = forme.get("sorties") or []
    return morceaux


def retouches(base: dict[str, Any], actuelle: dict[str, Any]) -> list[str]:
    """Les morceaux de l'agent qui diffèrent de ce que le gabarit avait installé (la base) : ses retouches propres."""
    exiger_la_forme_actuelle(base)
    b, a = _morceaux(base), _morceaux(actuelle)
    return sorted(k for k in set(b) | set(a) if b.get(k) != a.get(k))


def fusion_a_trois(base: dict[str, Any], actuelle: dict[str, Any], nouvelle: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(morceaux à prendre de la nouvelle version, conflits). Un morceau retouché que la nouvelle version ne change pas : la retouche est gardée ;
    retouché ET changé par la nouvelle version (autrement que la retouche) : conflit."""
    exiger_la_forme_actuelle(base)
    b, a, n = _morceaux(base), _morceaux(actuelle), _morceaux(nouvelle)
    prendre, conflits = [], []
    for k in sorted(set(b) | set(a) | set(n)):
        retouche = b.get(k) != a.get(k)
        change = b.get(k) != n.get(k)
        if change and not retouche:
            prendre.append(k)
        elif change and retouche and a.get(k) != n.get(k):
            conflits.append(k)
    return prendre, conflits


def appliquer_la_fusion(definition_actuelle: dict, definition_nouvelle: dict, prendre: list[str]) -> dict:
    """La définition de l'agent, où seuls les morceaux à prendre viennent de la nouvelle version (les retouches restent)."""
    sortie = copy.deepcopy(definition_actuelle)
    nouveaux = {str(n["id"]): n for n in definition_nouvelle.get("nodes") or []}
    for k in prendre:
        if k == "sorties":
            sortie["edges"] = copy.deepcopy(definition_nouvelle.get("edges") or [])
            continue
        ident = k.split(":", 1)[1]
        actuels = [n for n in sortie.get("nodes") or [] if str(n["id"]) != ident]
        if ident in nouveaux:
            actuels.append(copy.deepcopy(nouveaux[ident]))
        sortie["nodes"] = actuels
    return sortie


ABSENT = "<absent>"  # un réglage que la version retire ; jamais une valeur écrite


def etat_des_reglages(reglages: dict[str, Any]) -> dict[str, Any]:
    """Ce que le gabarit de réglages pose sur un agent vierge (lot 19 bis, S4) : la part « modèle » appliquée par le même calcul que l'installation, puis la
    part « agent ». Pure."""
    from api.services.modeles_reglages import classement as cl
    from api.services.modeles_reglages import service as modeles

    pose, _ = modeles.calculer_l_application(reglages.get("modele") or {}, list(cl.SECTIONS), {}, reglees_par_le_principal=frozenset())
    pose.update(copy.deepcopy(reglages.get("agent") or {}))
    return pose


def fusion_des_reglages(base: dict[str, Any], actuels: dict[str, Any], nouveaux: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fusion à trois des RÉGLAGES d'un agent installé, clé par clé (lot 19 bis, S4) : ``base`` ce que l'ancienne version posait, ``actuels`` ce que l'agent porte,
    ``nouveaux`` ce que la nouvelle pose. Rend (réglages à prendre : clé -> valeur, ``ABSENT`` si la version la retire ; clés en conflit). Même règle que les
    textes : une clé que la version change et que le client n'a pas retouchée est prise ; retouchée ET changée par la version (autrement que pareil) : conflit."""
    prendre: dict[str, Any] = {}
    conflits: list[str] = []
    for cle in sorted(set(base) | set(nouveaux)):
        avant, apres, ici = base.get(cle, ABSENT), nouveaux.get(cle, ABSENT), actuels.get(cle, ABSENT)
        if avant == apres:
            continue
        if ici == avant:
            prendre[cle] = apres
        elif ici != apres:
            conflits.append(cle)
    return prendre, conflits


async def _reglages_de_la_version(nom: str, version: int, g: G.Gabarit) -> dict[str, Any] | None:
    """Le gabarit de réglages d'une version déjà figée en base (``None`` si on ne la retrouve pas)."""
    if version == g.version:
        return g.reglages
    figee = await db_client.lire_le_gabarit(nom, version)
    return ((figee or {}).get("contenu") or {}).get("reglages")


async def noeuds_du_gabarit(organization_id: int, workflow_id: int, graphe: dict[str, Any]) -> frozenset[str]:
    """Les nœuds de ``graphe`` dont le texte est celui que le gabarit a installé pour cet agent, sans un mot changé (vide pour un agent qui
    ne vient pas d'un gabarit). Lu par le contrôle du prompt : un texte prouvé du gabarit n'est pas rejugé tant qu'on n'y a pas touché."""
    application = await db_client.application_de(organization_id, workflow_id)
    if application is None:
        return frozenset()
    etape = next((e for e, wid in etapes_de(application["agents"]).items() if wid == workflow_id), None)
    base = ((application.get("retouches") or {}).get("base") or {}).get(etape) if etape else None
    if not base:
        return frozenset()
    installes = {i: n.get("prompt") for i, n in (base.get("noeuds") or {}).items()}
    return frozenset(
        str(n.get("id")) for n in graphe.get("nodes") or []
        if installes.get(str(n.get("id"))) and installes[str(n.get("id"))] == (n.get("data") or {}).get("prompt")
    )


async def retouches_de_l_agent(organization_id: int, application: dict[str, Any], etape: str) -> list[str]:
    """Les retouches propres d'un agent installé (son brouillon courant contre ce que le gabarit avait installé)."""
    wid = application["agents"][etape]
    brouillon = await _etat_actuel(wid)  # Pierre E : son brouillon, sinon sa version en ligne (un agent publié n'a plus de brouillon)
    base = (application.get("retouches") or {}).get("base", {}).get(etape) or {}
    return retouches(base, I.forme_de_l_agent(getattr(brouillon, "workflow_json", None)))


# --------------------------------------------------------------------------- la porte d'acceptation d'un client


async def porte_verte(organization_id: int, application: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """Vrai quand aucun test obligatoire d'aucun agent du client n'est rouge, jamais joué ou joué sur un autre brouillon (même lecture que
    le contrôle « Tests obligatoires »)."""
    from api.services.builder.tests_agent import publication as garde

    problemes: list[dict[str, Any]] = []
    for etape, wid in etapes_de(application["agents"]).items():
        brouillon = await _etat_actuel(wid)  # Pierre E : un agent PUBLIÉ (le cas normal en production) n'a plus de brouillon : la porte lit alors sa version en ligne
        for p in await garde.problemes_des_tests_obligatoires(
            organization_id, wid, getattr(brouillon, "version_number", None), garde.empreinte_du_brouillon_publie(brouillon)
        ):
            problemes.append({"agent": wid, "etape": etape, **p})
    return not problemes, problemes


# --------------------------------------------------------------------------- la diffusion


async def _peut_diffuser_partout(user: Any) -> bool:
    from api.services.equipe_mark.acces import est_par_cle_api
    from api.services.equipe_mark.droits_effectifs import permissions_de

    return not est_par_cle_api(user) and PERMISSION_TOUTES in await permissions_de(user)


async def _toutes_les_applications(nom: str, organization_id: int | None) -> list[dict[str, Any]]:
    """Paginé par identifiant : aucune liste n'est lue d'un bloc."""
    sortie, apres = [], 0
    while True:
        page = await db_client.applications_du_gabarit(nom, organization_id=organization_id, apres_id=apres)
        if not page:
            return sortie
        sortie += page
        apres = page[-1]["id"]


async def _ecrire_sur_une_branche(organization_id: int, wid: int, user_id: int, nom: str, definition: dict, reglages: dict | None = None) -> dict[str, Any]:
    from api.db import branche_ouverte
    from api.db.branches_client import ErreurDeBranche
    from api.services.branches import service as branches

    agent = await db_client.get_workflow(wid, organization_id=organization_id)
    existante = next((b for b in await db_client.lister_les_branches(organization_id, wid) if b.nom == nom), None)
    if existante is None:
        try:
            branche = await branches.creer(organization_id, agent, nom, depuis_version=None, user_id=user_id, protegee=False)
        except ErreurDeBranche as erreur:
            return {"etat": "refusee", "raison": erreur.code}
        branch_id = branche["id"]
    else:
        branch_id = existante.id
    avant = branche_ouverte.courante()
    branche_ouverte.ouvrir(branch_id, user_id)
    try:
        await db_client.update_workflow(
            workflow_id=wid, name=None, workflow_definition=definition, template_context_variables=None, workflow_configurations=reglages,
            organization_id=organization_id,
        )
    finally:
        branche_ouverte.ouvrir(avant.branch_id, avant.user_id)
    return {"etat": "branche_prete", "branche_id": branch_id}


async def diffuser(user: Any, *, nom: str, version: int, portee: str, organization_id: int | None) -> dict[str, Any]:
    """Diffuse la version ``version`` du gabarit ``nom``. ``organization_id`` : l'organisation de la SESSION pour la portée « organisation »
    (jamais lue dans le corps d'une requête). Rend la ligne du journal des diffusions."""
    from api.services.equipe_mark.acces import est_par_cle_api, journaliser

    if portee not in PORTEES:
        raise RefusDiffusion(422, "portee", "The scope is « organisation » or « toutes ».")
    if est_par_cle_api(user):
        raise RefusDiffusion(403, "par_une_personne", "A template is broadcast by a member of the .mark team, never by an API key.")
    cible_org = organization_id if portee == "organisation" else None
    if portee == "toutes" and not await _peut_diffuser_partout(user):
        await journaliser(user, "gabarits.diffuser_refuse", organization_id, {"gabarit": nom, "version": version, "portee": portee, "raison": "permission"})
        await db_client.noter_une_diffusion(nom=nom, version=version, portee=portee, organization_id=None, par_user_id=user.id, statut="refusee",
                                            resultat={"raison": "permission", "permission": PERMISSION_TOUTES})
        raise RefusDiffusion(403, "permission", f"Broadcasting to every organization needs the permission « {PERMISSION_TOUTES} ».")
    g = G.charger(nom)
    if g.version != version:
        raise RefusDiffusion(404, "version", "This version of the template is not the one this server carries.")
    await G.figer(g)
    applications = await _toutes_les_applications(nom, cible_org)
    resultat: dict[str, Any] = {"agents": {}, "portes_rouges": []}
    for a in applications:
        verte, problemes = await porte_verte(a["organization_id"], a)
        if not verte:
            resultat["portes_rouges"].append({"organisation": a["organization_id"], "agent": a["workflow_id"], "problemes": len(problemes)})
    if resultat["portes_rouges"]:
        ligne = await db_client.noter_une_diffusion(nom=nom, version=version, portee=portee, organization_id=cible_org, par_user_id=user.id,
                                                    statut="refusee", resultat=resultat)
        await journaliser(user, "gabarits.diffuser_refuse", organization_id, {"gabarit": nom, "version": version, "portee": portee, "raison": "porte"})
        raise RefusDiffusion(409, "porte_rouge", f"Diffusion refused: {len(resultat['portes_rouges'])} client(s) whose required tests are not green (log {ligne['id']}).")
    for a in applications:
        resultat["agents"][str(a["workflow_id"])] = await _diffuser_une_application(user, g, a)
    conflits = [k for k, v in resultat["agents"].items() if any(x.get("etat") in ("conflit", "refusee") for x in v.values())]
    statut = "partielle" if conflits else "faite"
    ligne = await db_client.noter_une_diffusion(nom=nom, version=version, portee=portee, organization_id=cible_org, par_user_id=user.id,
                                                statut=statut, resultat=resultat)
    await journaliser(user, "gabarits.diffuser", organization_id, {"gabarit": nom, "version": version, "portee": portee, "statut": statut,
                                                                    "agents": len(applications), "diffusion": ligne["id"]})
    return ligne


async def _etat_actuel(wid: int) -> Any:
    """Ce que l'agent porte maintenant : son brouillon, sinon sa version en ligne (une principale publiée n'a plus de brouillon)."""
    brouillon = await db_client.get_draft_version(wid)
    if brouillon is not None:
        return brouillon
    en_ligne = await db_client.get_workflow_versions(wid, limit=1, status="published")
    return en_ligne[0] if en_ligne else None


def valeurs_des_trous_de_l_application(g: G.Gabarit, a: dict[str, Any]) -> dict[str, str]:
    """Les trous de la version ``g`` recalculés depuis le formulaire de l'application (lot 19 bis, S5), jamais ceux figés à l'installation : un trou que la
    version ajoute y est cherché. ``TrouManquant`` si le formulaire ne le porte pas."""
    valeurs = T.valeurs_des_trous(g.trous, F.completer(a["formulaire"]), ST.textes())
    for nom in g.trous:
        if nom not in valeurs:
            raise T.TrouManquant(nom)
    return valeurs


async def _diffuser_une_application(user: Any, g: G.Gabarit, a: dict[str, Any]) -> dict[str, Any]:
    org = a["organization_id"]
    base_par_etape = (a.get("retouches") or {}).get("base") or {}
    versions_des_reglages = (a.get("retouches") or {}).get("reglages_version") or {}
    etapes = etapes_de(a["agents"])
    # Première phase : tout est calculé AVANT la première écriture ; une application dont un trou manque est refusée entière (S5), rien n'est écrit sur ses branches.
    try:
        valeurs = valeurs_des_trous_de_l_application(g, a)
        passages, passages_a_poser = await I._passages_a_poser(org, etapes)  # lu seulement : rien n'est écrit pendant le calcul
        plans: dict[str, dict[str, Any]] = {}
        for etape, wid in etapes.items():
            actuel = await _etat_actuel(wid)
            actuelle_def = getattr(actuel, "workflow_json", None) or {}
            actuels = getattr(actuel, "workflow_configurations", None) or {}
            nouvelle_def = await I.definition_de_l_etape(g, etape, valeurs, org, user.id, passages)
            nouvelle_forme = I.forme_de_l_agent(nouvelle_def)
            prendre, conflits = fusion_a_trois(base_par_etape.get(etape) or {}, I.forme_de_l_agent(actuelle_def), nouvelle_forme)
            version_base = versions_des_reglages.get(etape, a["gabarit_version"])
            anciens = await _reglages_de_la_version(g.nom, version_base, g)
            a_prendre, en_conflit = fusion_des_reglages(etat_des_reglages(anciens or g.reglages), actuels, etat_des_reglages(g.reglages))
            plans[etape] = {"wid": wid, "actuelle_def": actuelle_def, "actuels": actuels, "nouvelle_def": nouvelle_def, "forme": nouvelle_forme, "prendre": prendre,
                            "conflits": conflits, "reglages_a_prendre": a_prendre, "reglages_en_conflit": en_conflit}
    except T.TrouManquant as erreur:
        return {"application": {"etat": "refusee", "raison": "trou_manquant", "trou": str(erreur)}}
    except ST.StyleInconnu:
        return {"application": {"etat": "refusee", "raison": "style_inconnu"}}
    except FormeAMonter:  # une base d'ancienne forme : l'application est refusée seule, la diffusion « toutes » continue (le script de montée la rattrape)
        return {"application": {"etat": "refusee", "raison": "forme_a_monter"}}
    await I._poser_les_passages(org, passages_a_poser)  # la première écriture : tout est calculé
    par_etape: dict[str, Any] = {}
    en_attente: dict[str, Any] = {}
    nouvelle_base, versions = dict(base_par_etape), dict(versions_des_reglages)
    refus = False
    for etape, p in plans.items():
        morceaux_en_conflit = [*p["conflits"], *(f"reglages:{k}" for k in p["reglages_en_conflit"])]
        if morceaux_en_conflit:
            refus = True
            par_etape[etape] = {"etat": "conflit", "raison": "retouche sur un morceau que la nouvelle version change aussi", "morceaux": morceaux_en_conflit}
            continue
        pris = [*p["prendre"], *(f"reglages:{k}" for k in p["reglages_a_prendre"])]
        if not pris:
            par_etape[etape] = {"etat": "inchange"}
            nouvelle_base[etape], versions[etape] = p["forme"], g.version  # déjà en ligne : la base suit tout de suite
            continue
        reglages = None
        if p["reglages_a_prendre"]:
            reglages = copy.deepcopy(p["actuels"])
            for cle, valeur in p["reglages_a_prendre"].items():
                if valeur == ABSENT:
                    reglages.pop(cle, None)
                else:
                    reglages[cle] = copy.deepcopy(valeur)
        definition = appliquer_la_fusion(p["actuelle_def"], p["nouvelle_def"], p["prendre"]) if p["prendre"] else p["actuelle_def"]
        nom = NOM_DE_BRANCHE.format(nom=g.nom, version=g.version)
        ecrite = await _ecrire_sur_une_branche(org, p["wid"], user.id, nom, definition, reglages)
        par_etape[etape] = {**ecrite, "pris": pris, "retouches_gardees": retouches(base_par_etape.get(etape) or {}, I.forme_de_l_agent(p["actuelle_def"]))}
        if ecrite.get("etat") == "branche_prete":
            en_attente[etape] = {"branche_id": ecrite["branche_id"], "forme": p["forme"]}
        else:
            refus = True
    # Lot 19 bis (S3) : la base des retouches et la version ne suivent QUE ce qui est en ligne ; une branche attend sa fusion (``noter_la_fusion``).
    retouches_a_jour = {**(a.get("retouches") or {}), "base": nouvelle_base, "reglages_version": versions}
    retouches_a_jour.pop("en_attente", None)
    champs: dict[str, Any] = {"empreinte_retouches": I.empreinte(nouvelle_base)}
    if en_attente:
        retouches_a_jour["en_attente"] = {"version": g.version, "trous": valeurs, "etapes": en_attente, "refus": refus}
    elif not refus:
        champs.update(gabarit_version=g.version, trous=dict(valeurs))
    champs["retouches"] = retouches_a_jour
    await db_client.ecrire_l_application(org, a["workflow_id"], **champs)
    if "gabarit_version" in champs:
        await _regenerer_les_tests(org, a["workflow_id"])
    return par_etape


async def _regenerer_les_tests(org: int, workflow_id: int) -> None:
    """Les tests générés suivent la version du gabarit (lot 19 bis, S3). Ne lève jamais : la diffusion et la fusion sont faites."""
    from api.services.gabarits import tests_generes

    try:
        await tests_generes.regenerer(org, workflow_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Generated tests not regenerated after the template went live on agent {workflow_id} ({type(erreur).__name__}).")


async def noter_la_fusion(organization_id: int, workflow_id: int, branch_id: int) -> bool:
    """Lot 19 bis (S3) : la branche d'une diffusion vient d'entrer dans la principale : la base des retouches de cet agent et la version de ses réglages
    suivent la version diffusée ; quand plus aucune branche de cette diffusion n'attend (et qu'aucun agent n'est en conflit ou refusé), la version du gabarit
    de l'application, ses trous et ses tests générés suivent aussi. Rend vrai si la branche était celle d'une diffusion. Rejouable sans effet double."""
    a = await db_client.application_de(organization_id, workflow_id)
    if a is None:
        return False
    retouches_a_jour = copy.deepcopy(a.get("retouches") or {})
    attente = retouches_a_jour.get("en_attente") or {}
    etape = next((e for e, v in (attente.get("etapes") or {}).items() if v.get("branche_id") == branch_id and a["agents"].get(e) == workflow_id), None)
    if etape is None:
        return False
    # Pierre E : ce que la fiche portait AVANT, gardé pour « défaire la fusion » (la fiche revenait pas à la version d'avant : elle restait à la version diffusée)
    retouches_a_jour.setdefault("fusions", {})[str(branch_id)] = {
        "etape": etape, "forme_avant": copy.deepcopy((retouches_a_jour.get("base") or {}).get(etape)), "reglages_version_avant": (retouches_a_jour.get("reglages_version") or {}).get(etape),
        "attente_avant": copy.deepcopy(attente), "gabarit_version_avant": a["gabarit_version"], "trous_avant": copy.deepcopy(a["trous"]),
    }
    retouches_a_jour.setdefault("base", {})[etape] = attente["etapes"].pop(etape)["forme"]
    retouches_a_jour.setdefault("reglages_version", {})[etape] = attente["version"]
    champs: dict[str, Any] = {"empreinte_retouches": I.empreinte(retouches_a_jour["base"])}
    fini = not attente["etapes"] and not attente.get("refus")
    if fini:
        champs.update(gabarit_version=attente["version"], trous=dict(attente["trous"]))
        retouches_a_jour.pop("en_attente")
    champs["retouches"] = retouches_a_jour
    await db_client.ecrire_l_application(organization_id, a["workflow_id"], **champs)
    if fini:
        await _regenerer_les_tests(organization_id, a["workflow_id"])
    return True


async def noter_le_defaire(organization_id: int, workflow_id: int, branch_id: int) -> bool:
    """Pierre E : la fusion d'une branche de diffusion est DÉFAITE : la base des retouches, la version des réglages, la version du gabarit, les trous et l'attente de la diffusion
    reviennent à ce qu'ils étaient avant elle (la fiche restait à la version diffusée alors que l'agent revenait en arrière). Rejouable : sans trace, rien."""
    a = await db_client.application_de(organization_id, workflow_id)
    if a is None:
        return False
    retouches_a_jour = copy.deepcopy(a.get("retouches") or {})
    avant = (retouches_a_jour.get("fusions") or {}).pop(str(branch_id), None)
    if avant is None:
        return False
    etape = avant["etape"]
    base = retouches_a_jour.setdefault("base", {})
    if avant["forme_avant"] is None:
        base.pop(etape, None)
    else:
        base[etape] = avant["forme_avant"]
    versions = retouches_a_jour.setdefault("reglages_version", {})
    if avant["reglages_version_avant"] is None:
        versions.pop(etape, None)
    else:
        versions[etape] = avant["reglages_version_avant"]
    retouches_a_jour["en_attente"] = avant["attente_avant"]
    champs: dict[str, Any] = {"empreinte_retouches": I.empreinte(base), "retouches": retouches_a_jour}
    if a["gabarit_version"] != avant["gabarit_version_avant"]:
        champs.update(gabarit_version=avant["gabarit_version_avant"], trous=avant["trous_avant"])
    await db_client.ecrire_l_application(organization_id, a["workflow_id"], **champs)
    if "gabarit_version" in champs:
        await _regenerer_les_tests(organization_id, a["workflow_id"])
    return True


# --------------------------------------------------------------------------- le rodage (D28)


async def etat_du_rodage(organization_id: int, workflow_id: int) -> dict[str, Any] | None:
    """« En rodage » jusqu'à ce que les dix premiers vrais appels soient relus ; lu par le portail. ``None`` : agent non installé ici."""
    a = await db_client.application_de(organization_id, workflow_id)
    if a is None:
        return None
    relus = len(a["rodage_relus"])
    return {"en_rodage": relus < I.RODAGE_APPELS, "relus": relus, "a_relire": max(0, I.RODAGE_APPELS - relus), "seuil": I.RODAGE_APPELS}


async def noter_un_appel_relu(organization_id: int, workflow_id: int, run_id: int) -> dict[str, Any] | None:
    """Un vrai appel d'un agent du groupe, de CETTE organisation, marqué relu (une fois). ``None`` : l'appel n'est pas d'ici, ou c'est un essai."""
    from api.services.apres_appel.chaine import MODES_ESSAI

    a = await db_client.application_de(organization_id, workflow_id)
    if a is None:
        return None
    run = await db_client.get_workflow_run(run_id, organization_id=organization_id)
    if run is None or run.workflow_id not in a["agents"].get(CLE_DES_IDENTIFIANTS, []) or str(run.mode) in MODES_ESSAI:
        return None
    await db_client.noter_un_appel_relu(organization_id, a["workflow_id"], run_id)
    return await etat_du_rodage(organization_id, workflow_id)


# --------------------------------------------------------------------------- le forçage de la porte (D32)


def tests_generes_rouges(refus: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Les tests générés (porte d'acceptation) parmi les tests obligatoires qui bloquent une publication."""
    return [t for t in (refus or {}).get("tests_obligatoires") or [] if str(t.get("slug") or "").startswith("genere-")]


async def forcage_permis(user: Any, refus: dict[str, Any] | None) -> bool:
    """D32 : une publication dont des tests GÉNÉRÉS sont rouges ne se force que par une session de l'équipe .mark (un rôle d'équipe), jamais par
    la clé du client ni par le portail ; les autres refus gardent la règle d'avant (toujours forçable avec une raison)."""
    if not tests_generes_rouges(refus):
        return True
    from api.services.equipe_mark.acces import acces_de, est_par_cle_api

    return not est_par_cle_api(user) and await acces_de(user) is not None
