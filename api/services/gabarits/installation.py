"""[.mark] Chantier Partie 1, lot 17 : installer un restaurant depuis le gabarit et le formulaire seuls (D10, D11, méthode § 11).

L'installation est l'étape « L'agent » (n° 6) du moteur « Nouveau client » (``installation_client/``) quand ses données portent un gabarit :
le moteur la rend atomique (une seule requête la prend), reprenable (bail) et journalisée ; ici, chaque morceau fait est NOTÉ dans le résultat
de l'étape (``ctx.noter``) avant le suivant, si bien qu'une coupure reprend au morceau suivant sans rien doubler :

1. contrôler le formulaire (A présent et cohérent ; style de la liste fermée ; une règle inconnue est signalée, jamais bloquante) ;
2. écrire le formulaire dans la base du client (établissement, horaires, services, zones, paiements, réservation, carte) ;
3. figer la version du gabarit ;
4. créer le groupe : l'accueil, puis un collègue par mission cochée (passages compris) ;
5. écrire les étapes : textes remplis (trous du formulaire, variables d'appel laissées au code), outils, sorties et portes ;
6. appliquer le gabarit de réglages (sans clé ni lexique : M3) ;
7. générer le lexique depuis la carte ;
8. noter la version du gabarit et le commit du fork (``mark_gabarit_applications``) ;
9. écrire les tests obligatoires générés (la porte d'acceptation, D56).

Le verrou (D11) est celui du fork : chez un client, la principale d'un agent est protégée dès sa première publication par une personne
(``protection_principale``) ; ensuite une retouche passe par une branche de brouillon, versionnée, comme la diffusion d'une nouvelle version.

Aucune étape ne dépense : aucun appel au modèle ni à un tiers. ``installer_un_restaurant`` est le script : il ouvre l'installation du client et
joue les étapes du moteur dans l'ordre, les étapes que le formulaire couvre déjà étant passées.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.gabarits import formulaire as F
from api.services.gabarits import gabarit as G
from api.services.gabarits import styles as ST
from api.services.gabarits import trous as T

VARIABLE_DU_COMMIT = "RAILWAY_GIT_COMMIT_SHA"
RODAGE_APPELS = 10  # D28 : dix premiers vrais appels relus
ETAPE_DU_MOTEUR = 6


class ErreurInstallation(Exception):
    """Un refus de l'installation, dit par un code de phrase (``installation_client.etapes.PHRASES``) et ses précisions."""

    def __init__(self, code: str, precisions: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.precisions = precisions or []


# --------------------------------------------------------------------------- outils communs


def commit_du_fork() -> str | None:
    """Le commit du fork qui installe : la variable du déploiement, sinon le dépôt local ; ``None`` si aucun ne le dit."""
    if os.getenv(VARIABLE_DU_COMMIT):
        return os.environ[VARIABLE_DU_COMMIT][:64]
    try:
        sortie = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, cwd=os.path.dirname(__file__))
    except (OSError, subprocess.SubprocessError):
        return None
    return sortie.stdout.strip()[:64] or None if sortie.returncode == 0 else None


def cle_de_l_etablissement(nom: str) -> str:
    from api.services.installation_client.executants import identifiant

    return identifiant(nom)


def empreinte(valeur: Any) -> str:
    return hashlib.sha256(json.dumps(valeur, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def forme_de_l_agent(definition: dict | None) -> dict[str, Any]:
    """Ce qui fait l'agent au sens du gabarit (textes, outils, sorties), sans positions ni identifiants d'écran : la base des retouches."""
    d = definition or {}
    noeuds = {
        str(n.get("id")): {
            "type": n.get("type"),
            "prompt": (n.get("data") or {}).get("prompt"),
            "greeting": (n.get("data") or {}).get("greeting"),
            "outils": sorted((n.get("data") or {}).get("tool_uuids") or []),
        }
        for n in d.get("nodes") or []
    }
    sorties = sorted(
        (str(a.get("source")), str(a.get("target")), (a.get("data") or {}).get("condition"), bool((a.get("data") or {}).get("fermee_si_action_ouverte")))
        for a in d.get("edges") or []
    )
    return {"noeuds": noeuds, "sorties": [list(s) for s in sorties]}


async def _base_du_client(organization_id: int):
    from api.db.bases_clients import connexion as schema
    from api.services.base_client import rattachement

    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise ErreurInstallation("base_requise")
    return await schema.connecter(nom)


async def application_qui_tient_la_cle(organization_id: int, gabarit_nom: str, cle: str) -> int | None:
    """L'agent principal de l'application déjà installée dans CETTE organisation pour l'établissement de clé ``cle`` ; ``None`` si la clé est libre
    (lot 19 bis, S9). Paginé par identifiant."""
    apres = 0
    while True:
        page = await db_client.applications_du_gabarit(gabarit_nom, organization_id=organization_id, apres_id=apres)
        if not page:
            return None
        for a in page:
            if (a.get("formulaire") or {}).get("cle") == cle:
                return a["workflow_id"]
        apres = page[-1]["id"]


# --------------------------------------------------------------------------- le lexique (généré, puis régénéré à chaque synchronisation)


async def lexique_depuis_la_carte(organization_id: int, connexion, etablissement_id: int) -> dict[str, int]:
    """Les noms de la carte entrent au lexique de l'organisation (``restauration/lexique_liste.py``, dans la limite du fournisseur) ; ce
    qu'une personne a écrit au lexique n'est jamais touché."""
    from api.db.bases_clients.restauration_carte import carte_du_restaurant
    from api.db.bases_clients.restauration_client import elements_de_la_carte
    from api.services.restauration.lexique_liste import remplir_le_lexique

    carte = await carte_du_restaurant(connexion, etablissement_id)
    elements, _ = elements_de_la_carte(carte)
    plafond = await _plafond_de_l_organisation(organization_id)
    r = await remplir_le_lexique(organization_id, elements, plafond)
    return {"ajoutes": r.ajoutes, "deja_presents": r.deja_presents, "a_ecouter": r.a_ecouter}


async def _plafond_de_l_organisation(organization_id: int):
    """Le plafond du fournisseur de transcription de l'organisation (même lecture que le budget du lexique) ; ``None`` s'il ne se lit pas :
    rien n'est alors coché « à écouter » (règle du module Lexique)."""
    from api.services.configuration.ai_model_configuration import get_resolved_ai_model_configuration
    from api.services.configuration.plafond_lexique import plafond_du_lexique

    try:
        stt = getattr((await get_resolved_ai_model_configuration(organization_id=organization_id)).effective, "stt", None)
    except Exception:  # noqa: BLE001 -- un fournisseur illisible ne bloque pas l'installation
        return None
    fournisseur = getattr(stt, "provider", None)
    return plafond_du_lexique(str(getattr(fournisseur, "value", fournisseur)) if fournisseur else None, getattr(stt, "model", None))


async def apres_l_import_de_la_carte(organization_id: int, connexion, etablissement_id: int, bilan: dict[str, Any]) -> None:
    """Après l'import de la carte par la caisse (``synchro_caisse.importer_la_caisse``) : le lexique suit la nouvelle carte, et les tests générés
    des agents installés qui servent l'établissement sont régénérés. ⛔ Ne lève jamais : une synchronisation ne rate pas pour eux."""
    if bilan.get("carte") is None:
        return
    try:
        await lexique_depuis_la_carte(organization_id, connexion, etablissement_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Lexicon not regenerated after the till sync of establishment {etablissement_id} ({type(erreur).__name__}).")
    try:
        from api.services.gabarits import tests_generes

        for application in await db_client.applications_de_l_etablissement(organization_id, etablissement_id):
            await tests_generes.regenerer(organization_id, application["workflow_id"])
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Generated tests not regenerated after the till sync of establishment {etablissement_id} ({type(erreur).__name__}).")


# --------------------------------------------------------------------------- les étapes du gabarit sur les agents


def _cibles_du_passage() -> dict[str, str]:
    """La phrase de chaque cible de ``passer_a`` dans le rendu versé (« cible commande : … »)."""
    from api.services.gabarits.restauration.textes import rendu

    passer = next(o for o in rendu("accueil", "accueil") if o["function"]["name"] == "passer_a")["function"]["description"]
    return dict(m.split(" : ", 1) for m in passer.split(" cible ")[1:])


def _sorties_du_rendu(etape: str) -> dict[str, str]:
    from api.services.gabarits.restauration.textes import rendu

    etat = {"accueil": "accueil", "commande": "vide", "reservation": "vide", "service": "service"}[etape]
    return {o["function"]["name"]: o["function"]["description"] for o in rendu(etape, etat)}


async def _outil_d_action(organization_id: int, user_id: int, connecteur: str, action: str, nom: str) -> str:
    """L'outil de l'action dans l'organisation : repris s'il existe (même connecteur, même action), créé sinon, avec la description de l'action
    du catalogue (le contrat, jamais un texte écrit ici)."""
    from api.services.integrations.connectors.catalogue import connecteur as du_catalogue

    for o in await db_client.get_tools_for_organization(organization_id, status="active", category="integration"):
        config = ((o.definition or {}).get("config")) or {}
        if config.get("connecteur") == connecteur and config.get("action") == action:
            return o.tool_uuid
    a = du_catalogue(connecteur).action(action)
    cree = await db_client.create_tool(
        organization_id=organization_id,
        user_id=user_id,
        name=nom,
        description=a.description,
        category="integration",
        definition={"schema_version": 1, "type": "integration", "config": {"connecteur": connecteur, "action": action}},
    )
    return cree.tool_uuid


def _noeud(i: str, type_: str, nom: str, prompt: str, *, x: int = 0, y: int = 0, outils=(), global_: bool = True, **plus) -> dict:
    data = {"name": nom, "prompt": prompt, "allow_interrupt": type_ == "startCall", "add_global_prompt": global_}
    if type_ == "startCall":
        data["is_start"] = True
    if type_ == "endCall":
        data["is_end"] = True
    if outils:
        data["tool_uuids"] = list(outils)
    data.update(plus)
    return {"id": i, "type": type_, "position": {"x": x, "y": y}, "data": data}


def _sortie(a: str, b: str, nom: str, condition: str, *, fermee_si_action_ouverte: bool = False) -> dict:
    data = {"label": nom, "condition": condition, "identifiant": nom}
    if fermee_si_action_ouverte:
        data["fermee_si_action_ouverte"] = True
    return {"id": f"{a}-{b}", "source": a, "target": b, "data": data}


async def definition_de_l_etape(
    g: G.Gabarit, etape: str, valeurs: dict[str, str], organization_id: int, user_id: int, passages: list[str]
) -> dict[str, Any]:
    """La définition d'un agent du groupe, construite depuis le gabarit seul (et les outils de passage déjà posés sur l'accueil)."""
    e = g.definition["etapes"][etape]
    fixes = g.definition["noeuds_fixes"]
    sorties_du_rendu = _sorties_du_rendu(etape)
    nodes: list[dict] = []
    general_commun: str | None = None
    for rang, n in enumerate(e["noeuds"]):
        general, mission = G.prompts_de_l_etape(g, n["texte"], valeurs)
        general_commun = general_commun or general
        outils: list[str] = []
        for nom in n.get("outils", []):
            d = G.outil(g, nom, etape)
            if "capacite_manquante" in d:
                continue  # dit au résultat de l'installation et dans a-trancher.md, jamais remplacé par un autre outil
            outils.append(await _outil_d_action(organization_id, user_id, d["connecteur"], d["action"], nom))
        if n.get("passages"):
            outils = [*passages, *outils]  # B13 : les passages en tête
        plus: dict[str, Any] = {}
        if n["type"] == "startCall" and etape == "accueil":
            plus["greeting"] = T.remplir(g.textes[g.definition["accueil_au_decroche"]["texte"]].strip(), valeurs, trous=set(g.trous))
            plus["delayed_start_duration"] = g.definition["accueil_au_decroche"]["delai_avant_s"]
        if n.get("etape_de_retour"):
            plus["etape_de_retour"] = True
        nodes.append(_noeud(n["id"], n["type"], n["id"], mission, y=240 * rang, outils=outils, **plus))
    nodes.insert(0, {"id": "g", "type": "globalNode", "position": {"x": -400, "y": 0}, "data": {"name": "Prompt général", "prompt": general_commun}})
    nodes.append(_noeud("fin", "endCall", "fin", fixes["fin"]["prompt"], x=400, y=240, global_=False, premiere_replique=fixes["fin"]["premiere_replique"]))
    edges = []
    if any(s["sortie"] == "rendre_la_main" for s in e["sorties"]):
        nodes.append(
            _noeud("retour", "agentNode", "retour", fixes["retour"]["prompt"], x=400, global_=False,
                   premiere_replique=fixes["retour"]["premiere_replique"], retour_au_principal=True)
        )
    for s in e["sorties"]:
        cible = "fin" if s["sortie"] == "fin" else "retour"
        edges.append(_sortie(s["de"], cible, s["sortie"], sorties_du_rendu[s["sortie"]], fermee_si_action_ouverte=bool(s.get("fermee_si_action_ouverte"))))
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.75}}


async def _passages_de_l_accueil(organization_id: int, agents: dict[str, int]) -> list[str]:
    """Les outils de passage que le groupe a posés vers chaque collègue, leur cible et leur texte réglés d'après le rendu versé (B13)."""
    from api.enums import ToolCategory

    vers = {wid: etape for etape, wid in agents.items() if etape != "accueil"}
    phrases = _cibles_du_passage()
    ordre = [e for e in G.charger().definition["etapes"] if e != "accueil"]
    tries: list[tuple[int, str]] = []
    for o in await db_client.get_tools_for_organization(organization_id, status="active", category=ToolCategory.TRANSFER_AGENT.value):
        config = dict(((o.definition or {}).get("config")) or {})
        etape = vers.get(config.get("workflow_id"))
        if etape is None:
            continue
        if config.get("cible") != etape or (o.description or "") != phrases[etape]:
            config["cible"] = etape
            await db_client.update_tool(o.tool_uuid, organization_id, description=phrases[etape], definition={**(o.definition or {}), "config": config})
        tries.append((ordre.index(etape), o.tool_uuid))
    return [u for _, u in sorted(tries)]


async def appliquer_les_reglages(g: G.Gabarit, organization_id: int, agents: dict[str, int], cle: str) -> None:
    """Le gabarit de réglages sur chaque agent du groupe (brouillon), sections entières, puis la part propre à l'agent et son établissement.
    Le principal transmet ensuite ses réglages communs à ses collègues (même geste qu'un enregistrement)."""
    from api.services.groupe.groupe import recopier_dans_les_specialises
    from api.services.modeles_reglages import classement as cl
    from api.services.modeles_reglages import service as modeles

    for etape, wid in agents.items():
        brouillon = await db_client.get_draft_version(wid)
        base = dict(getattr(brouillon, "workflow_configurations", None) or {})
        nouveau, _ = modeles.calculer_l_application(
            g.reglages["modele"], list(cl.SECTIONS), base, reglees_par_le_principal=modeles.cles_reglees_par_le_principal(base)
        )
        nouveau.update(copy.deepcopy(g.reglages["agent"]))
        nouveau["etablissement_id"] = cle
        await db_client.update_workflow(
            workflow_id=wid, name=None, workflow_definition=None, template_context_variables=None, workflow_configurations=nouveau,
            organization_id=organization_id,
        )
    await recopier_dans_les_specialises(agents["accueil"], organization_id)


# --------------------------------------------------------------------------- l'installation (étape 6 du moteur)


async def installer(
    user: Any,
    organization_id: int,
    formulaire: dict[str, Any],
    *,
    progres: dict[str, Any] | None = None,
    noter: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Installe un restaurant depuis le gabarit et le formulaire ; reprend après ``progres`` (ce que la tentative coupée a noté). Rend le
    résultat de l'étape : l'agent principal et ses collègues, l'établissement, les signalements B, la version du gabarit et du fork."""
    from api.services.groupe import groupe
    from api.db.bases_clients.restauration_formulaire import ecrire_le_formulaire, faits_de_l_etablissement

    fait: dict[str, Any] = dict(progres or {})

    async def note(**champs: Any) -> None:
        fait.update(champs)
        if noter is not None:
            await noter(dict(fait))

    g = G.charger()
    f = F.completer(formulaire)
    # Lot 19 bis (S6) : le progrès noté est celui d'UN formulaire (son empreinte) ; repris avec un autre, l'installation repart de zéro, jamais la clé et les agents
    # de l'un sous le formulaire de l'autre. (Un progrès noté avant ce correctif n'a pas d'empreinte : il est tenu pour celui du formulaire reçu.)
    du_formulaire = empreinte(f)
    if fait.get("empreinte_formulaire") not in (None, du_formulaire):
        fait = {}
    fait["empreinte_formulaire"] = du_formulaire
    controle = F.controler(f)
    if not controle.creation_permise:
        raise ErreurInstallation("gabarit_formulaire_incomplet", [f"A:{c}" for c in controle.a_manquer])
    try:
        ST.valider(f.get("style"))
    except ST.StyleInconnu:
        raise ErreurInstallation("gabarit_style_inconnu", [str(f.get("style"))[:40]]) from None
    valeurs = T.valeurs_des_trous(g.trous, f, ST.textes())
    cle = fait.get("cle") or cle_de_l_etablissement(f["nom_etablissement"])

    connexion = await _base_du_client(organization_id)
    try:
        if "etablissement_id" not in fait:
            # Lot 19 bis (S9) : la clé tirée du nom est celle de l'établissement ; une clé déjà tenue par un autre agent installé est refusée, jamais réécrite.
            tenu_par = await application_qui_tient_la_cle(organization_id, g.nom, cle)
            if tenu_par is not None:
                raise ErreurInstallation("gabarit_restaurant_deja_installe", [str(tenu_par)])
            ecrit = await ecrire_le_formulaire(connexion, cle, f, f"installation:{getattr(user, 'id', '')}")
            await note(cle=cle, etablissement_id=ecrit["etablissement_id"], carte=ecrit["carte"])
        faits = await faits_de_l_etablissement(connexion, fait["etablissement_id"])
        controle = F.controler(f, faits)
        if "gabarit" not in fait:
            fige = await G.figer(g)
            await note(gabarit={"nom": fige["nom"], "version": fige["version"], "empreinte": fige["empreinte"]})

        agents: dict[str, int] = dict(fait.get("agents") or {})
        nom = f["nom_etablissement"].strip()[:60]
        if "accueil" not in agents:
            principal, _dossier = await groupe.creer_principal(nom=f"{nom} · accueil", organization_id=organization_id, user_id=user.id, dossier_parent_id=None)
            agents["accueil"] = principal
            await note(agents=dict(agents))
        for etape in g.etapes_des_missions(f["missions"]):
            if etape not in agents:
                agents[etape] = await groupe.creer_specialise(principal_id=agents["accueil"], nom=f"{nom} · {etape}", organization_id=organization_id, user_id=user.id)
                await note(agents=dict(agents))

        if not fait.get("etapes_ecrites"):
            passages = await _passages_de_l_accueil(organization_id, agents)
            formes: dict[str, Any] = {}
            for etape, wid in agents.items():
                definition = await definition_de_l_etape(g, etape, valeurs, organization_id, user.id, passages if etape == "accueil" else [])
                await db_client.update_workflow(
                    workflow_id=wid, name=None, workflow_definition=definition, template_context_variables=None, workflow_configurations=None,
                    organization_id=organization_id,
                )
                formes[etape] = forme_de_l_agent(definition)
            await note(etapes_ecrites=True, formes=formes)

        if not fait.get("reglages"):
            await appliquer_les_reglages(g, organization_id, agents, cle)
            await note(reglages=True)

        if "lexique" not in fait:
            await note(lexique=await lexique_depuis_la_carte(organization_id, connexion, fait["etablissement_id"]))

        commit = fait.get("commit_fork") or commit_du_fork()
        application = await db_client.ecrire_l_application(
            organization_id,
            agents["accueil"],
            gabarit_nom=g.nom,
            gabarit_version=g.version,
            commit_fork=commit,
            agents={**agents, "_ids": sorted(agents.values())},
            trous={k: v for k, v in valeurs.items()},
            formulaire={k: v for k, v in f.items() if k != "carte"} | {"etablissement_id": fait["etablissement_id"], "cle": cle},
            retouches={"base": fait["formes"]},
            empreinte_retouches=empreinte(fait["formes"]),
        )
        await note(commit_fork=commit, application_id=application["id"])

        if not fait.get("tests_generes"):
            from api.services.gabarits import tests_generes

            ecrits = await tests_generes.generer(organization_id, application, connexion, b_manquer=controle.b_manquer)
            await note(tests_generes=ecrits)

    finally:
        await connexion.close()

    return {
        "workflow_id": agents["accueil"],
        "agents": agents,
        "etablissement_id": fait["etablissement_id"],
        "cle": cle,
        "gabarit": fait["gabarit"],
        "commit_fork": fait.get("commit_fork"),
        "b_manquer": controle.b_manquer,
        "signalements": controle.signalements,
        "outils_sans_action": sorted(G.outils_sans_action(g)),
        "tests_generes": fait.get("tests_generes"),
    }


async def par_le_moteur(ctx: Any) -> Any:
    """L'étape 6 du moteur quand ses données portent ``gabarit`` : l'installation, reprise depuis le résultat noté d'une tentative coupée."""
    from api.services.installation_client.executants import ErreurEtape, Sortie

    if ctx.donnees.get("gabarit") != G.RESTAURATION:
        raise ErreurEtape("gabarit_inconnu")
    try:
        resultat = await installer(ctx.user, ctx.organization_id, dict(ctx.donnees.get("formulaire") or {}), progres=ctx.resultat_precedent, noter=ctx.noter)
    except ErreurInstallation as erreur:
        raise ErreurEtape(erreur.code, erreur.precisions) from None
    principale = await db_client.obtenir_la_principale(ctx.organization_id, resultat["workflow_id"])
    return Sortie({**resultat, "nom": f"{ctx.donnees['formulaire']['nom_etablissement']} · accueil", "branche": principale.nom, "branche_id": principale.id})


async def installer_un_restaurant(user: Any, organization_id: int, formulaire: dict[str, Any], *, nom_base: str) -> dict[str, Any]:
    """Le script : un restaurant installé par le formulaire seul, étape après étape du moteur « Nouveau client » (l'installation du client est
    ouverte si elle manque ; les étapes que le formulaire couvre sont passées). Rejoué, il reprend où il s'était arrêté."""
    from api.db.installation_client_client import InstallationDejaOuverte
    from api.services.installation_client import moteur

    if await db_client.installation_ouverte(organization_id) is None:
        try:
            await db_client.creer_installation(organization_id, formulaire["nom_etablissement"], user.id)
        except InstallationDejaOuverte:
            pass
    vue: dict[str, Any] | None = None
    for numero, donnees in (
        (2, {"nom_base": nom_base, "mode": "rattacher"}),
        (3, None),
        (4, None),
        (5, None),
        (ETAPE_DU_MOTEUR, {"gabarit": G.RESTAURATION, "formulaire": formulaire}),
        (7, None),
        (8, None),
        (9, {}),
    ):
        ouverte = await db_client.installation_ouverte(organization_id)
        if ouverte is None:
            break  # déjà terminée (rejouée après le récapitulatif)
        etat = next(e["etat"] for e in ouverte["etapes"] if e["numero"] == numero)
        if etat in moteur.ETATS_CLOS:
            continue
        if donnees is None:
            vue = await moteur.passer(user, organization_id, numero)
            continue
        sortie = await moteur.executer(user, organization_id, numero, donnees)
        vue = sortie["installation"]
        if sortie["echec"] is not None:
            return {"echec": {"etape": numero, **sortie["echec"]}, "installation": vue, "application": None}
    resultat_6 = next((e["resultat"] for e in (vue or {}).get("etapes", []) if e["numero"] == ETAPE_DU_MOTEUR), {})
    application = await db_client.application_de(organization_id, resultat_6["workflow_id"]) if resultat_6.get("workflow_id") else None
    return {"echec": None, "installation": vue, "etape_6": resultat_6, "application": application}
