"""[.mark] Partie 3, sous-lot 9 (§ 5 du plan) : ce que fait chaque étape de « Nouveau client ».

**Chaque étape appelle la route qui existe déjà** (même fonction, même contrôle, même journal) avec le compte de la
personne, dont l'organisation est celle du client (lue dans l'adresse et contrôlée par ``get_user``) ; aucune logique n'est
recopiée ici. Chaque étape est **rejouable sans effet double** : relancée après une coupure, elle lit d'abord ce qui existe
(base déjà rattachée, établissement, personne ou sujet déjà présent, proposition déjà faite, série déjà lancée) et ne refait
que ce qui manque. Une erreur d'une route devient un code de phrase (``etapes.PHRASES``), jamais son texte.

Rien de secret n'est rangé : la clé d'API et le mot de passe du portail (étape 7) sont rendus une fois dans ``montre`` et
ne sont écrits nulle part.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Response

from api.db import db_client

NOM_CLE_PORTAIL = "Portail .mark"


class ErreurEtape(Exception):
    """Un échec d'étape, dit par un code de phrase (``etapes.PHRASES``). ``precisions`` : les fautes de saisie qu'une route a
    rendues en 422 (messages de validation écrits pour l'écran, lus sous le champ), jamais un autre texte du serveur."""

    def __init__(self, code: str, precisions: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.precisions = precisions or []


@dataclass
class Contexte:
    user: Any
    organization_id: int
    installation: dict[str, Any]
    donnees: dict[str, Any]
    resultat_precedent: dict[str, Any] = field(default_factory=dict)
    noter: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    def resultat_de(self, numero: int) -> dict[str, Any]:
        for e in self.installation["etapes"]:
            if e["numero"] == numero:
                return e.get("resultat") or {}
        return {}


@dataclass
class Sortie:
    resultat: dict[str, Any]
    montre: dict[str, Any] | None = None  # rendu une fois à l'écran, jamais rangé


def identifiant(texte: str, separateur: str = "-", longueur: int = 40) -> str:
    """« Site Nord » -> « site-nord » (minuscules, chiffres, séparateur), borné."""
    sans_accent = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    propre = re.sub(r"[^a-z0-9]+", separateur, sans_accent.lower()).strip(separateur)
    return propre[:longueur].strip(separateur) or "x"


def _fautes_de_saisie(erreur: HTTPException) -> list[str]:
    """Les messages d'une faute de validation (422, liste ``{msg, loc}``), bornés ; rien pour tout autre refus."""
    if erreur.status_code != 422 or not isinstance(erreur.detail, list):
        return []
    return [str(d.get("msg"))[:300] for d in erreur.detail[:5] if isinstance(d, dict) and d.get("msg")]


def _code_http(erreur: HTTPException, par_statut: dict[int, str], defaut: str = "inconnue") -> ErreurEtape:
    return ErreurEtape(par_statut.get(erreur.status_code, defaut), _fautes_de_saisie(erreur))


# --- 2. La base du client -------------------------------------------------------------------------------------------------


async def base(ctx: Contexte) -> Sortie:
    from api.routes import base_client as routes
    from api.schemas.base_client import DemandeRattachement
    from api.services.base_client import rattachement

    nom = str(ctx.donnees.get("nom_base") or "").strip()
    mode = ctx.donnees.get("mode") or "creer"
    if not nom:
        raise ErreurEtape("base_nom_requis")
    if await rattachement.nom_de_la_base(ctx.organization_id) == nom:
        return Sortie({"nom_base": nom, "mode": mode, "deja": True})
    try:
        if mode == "rattacher":
            await routes.put_base_client(DemandeRattachement(nom_base=nom), user=ctx.user)
        else:
            await routes.post_creer(DemandeRattachement(nom_base=nom), user=ctx.user)
    except HTTPException as erreur:
        raise _code_http(erreur, {409: "base_prise", 422: "base_refusee", 503: "base_injoignable"}) from None
    return Sortie({"nom_base": nom, "mode": mode})


# --- 3. Établissements et horaires ----------------------------------------------------------------------------------------


async def etablissements(ctx: Contexte) -> Sortie:
    from api.routes import etablissements as routes
    from api.schemas.etablissements import CatalogueEtablissements, Etablissement

    demandes = [e for e in (ctx.donnees.get("etablissements") or []) if str((e or {}).get("nom") or "").strip()]
    if not demandes:
        raise ErreurEtape("etablissement_requis")
    try:
        catalogue = await routes.get_etablissements(user=ctx.user)
    except HTTPException as erreur:
        raise _code_http(erreur, {503: "base_injoignable"}) from None
    presents = {e.id for e in catalogue.etablissements}
    ajoutes: list[str] = []
    nouveaux = list(catalogue.etablissements)
    for demande in demandes:
        nom = str(demande["nom"]).strip()[:100]
        ident = identifiant(nom)
        if ident in presents:
            continue  # rejoué : déjà là, rien de doublé
        horaires = str(demande.get("horaires_ouverture") or "").strip() or None
        try:
            nouveaux.append(Etablissement(id=ident, nom=nom, horaires_ouverture=horaires))
        except ValueError:
            raise ErreurEtape("etablissements_refuses") from None
        presents.add(ident)
        ajoutes.append(ident)
    if ajoutes:
        try:
            await routes.save_etablissements(CatalogueEtablissements(etablissements=nouveaux), user=ctx.user)
        except HTTPException as erreur:
            raise _code_http(erreur, {503: "base_injoignable"}, "etablissements_refuses") from None
        except ValueError:
            raise ErreurEtape("etablissements_refuses") from None
    return Sortie({"etablissements": sorted(presents), "ajoutes": ajoutes})


# --- 4. Équipe et sujets --------------------------------------------------------------------------------------------------


async def equipe(ctx: Contexte) -> Sortie:
    from api.routes import base_client as routes
    from api.schemas.base_client import Equipe, Personne, Sujet

    personnes = [p for p in (ctx.donnees.get("personnes") or []) if str((p or {}).get("prenom") or "").strip()]
    if not personnes:
        raise ErreurEtape("personne_requise")
    try:
        actuelle = await routes.get_equipe(user=ctx.user)
    except HTTPException as erreur:
        raise _code_http(erreur, {409: "base_requise", 503: "base_injoignable"}) from None
    gens = list(actuelle.personnes)
    sujets = list(actuelle.sujets)
    cles = {p.cle for p in gens}
    codes = {s.code for s in sujets}
    cles_demandees: list[str] = []
    try:
        for p in personnes:
            prenom = str(p["prenom"]).strip()[:100]
            nom = (str(p.get("nom") or "").strip() or None) and str(p.get("nom")).strip()[:100]
            cle = identifiant(f"{prenom} {nom or ''}")
            cles_demandees.append(cle)
            if cle in cles:
                continue
            gens.append(
                Personne(cle=cle, prenom=prenom, nom=nom, role=(str(p.get("role") or "").strip() or None), mail=(str(p.get("mail") or "").strip() or None))
            )
            cles.add(cle)
        for s in ctx.donnees.get("sujets") or []:
            libelle = str((s or {}).get("libelle") or "").strip()[:100]
            if not libelle:
                continue
            code = identifiant(libelle, "_", 40)
            if code in codes:
                continue
            destinataires = [cles_demandees[i] for i in (s.get("destinataires") or []) if isinstance(i, int) and 0 <= i < len(cles_demandees)]
            sujets.append(Sujet(code=code, libelle=libelle, destinataires=destinataires))
            codes.add(code)
        complete = Equipe(personnes=gens, sujets=sujets)
    except ValueError:
        raise ErreurEtape("equipe_refusee") from None
    try:
        await routes.put_equipe(complete, user=ctx.user)
    except HTTPException as erreur:
        raise _code_http(erreur, {409: "base_requise", 503: "base_injoignable"}, "equipe_refusee") from None
    return Sortie({"personnes": len(gens), "sujets": len(sujets)})


# --- 5. Logiciels proposés ------------------------------------------------------------------------------------------------


async def logiciels(ctx: Contexte) -> Sortie:
    from api.services.integrations.connectors import propositions, routes

    demandes = [p for p in (ctx.donnees.get("propositions") or []) if (p or {}).get("connecteur")]
    if not demandes:
        raise ErreurEtape("logiciel_requis")
    proposes: list[str] = []
    for p in demandes:
        try:
            nouvelle = propositions.NouvelleProposition(
                connecteur=str(p["connecteur"]), compte=str(p.get("compte") or ctx.installation["nom"])[:60], message=str(p.get("message") or "")[:500]
            )
        except ValueError:
            raise ErreurEtape("logiciel_refuse") from None
        try:
            await routes.post_proposition(nouvelle, user=ctx.user)
        except HTTPException as erreur:
            if erreur.status_code != 409:  # 409 : déjà proposé (rejoué), rien de doublé
                raise _code_http(erreur, {422: "logiciel_refuse"}) from None
        proposes.append(nouvelle.connecteur)
    return Sortie({"proposes": proposes})


# --- 6. L'agent, depuis une recette ---------------------------------------------------------------------------------------


async def agent(ctx: Contexte) -> Sortie:
    """L'agent est créé par la fenêtre de création unique (routes de création existantes, dans l'organisation du client) ;
    l'étape le relit AVEC l'organisation (404 sinon) et lui pose sa branche « Principale »."""
    brut = ctx.donnees.get("workflow_id")
    if not isinstance(brut, int):
        raise ErreurEtape("agent_requis")
    workflow = await db_client.get_workflow(brut, organization_id=ctx.organization_id)
    if workflow is None:
        raise ErreurEtape("agent_introuvable")
    principale = await db_client.obtenir_la_principale(ctx.organization_id, workflow.id)
    return Sortie({"workflow_id": workflow.id, "nom": workflow.name, "branche": principale.nom, "branche_id": principale.id})


# --- 7. Clé d'API du client et fiche du portail ---------------------------------------------------------------------------


async def cle_portail(ctx: Contexte) -> Sortie:
    """Une seule clé « Portail .mark » active : relancée, l'étape archive celle d'une tentative coupée (jamais montrée) avant
    d'en créer une. Montrée une fois ; seul son préfixe est rangé."""
    from api.routes import base_client as routes_base
    from api.routes import user as routes_user
    from api.services.base_client import rattachement
    from api.services.equipe_mark.acces import est_par_cle_api

    if est_par_cle_api(ctx.user):
        raise ErreurEtape("par_une_personne")
    for cle in await db_client.get_api_keys_by_organization(ctx.organization_id, include_archived=False):
        if cle.name == NOM_CLE_PORTAIL and cle.is_active:
            await db_client.archive_api_key(cle.id)
    try:
        creee = await routes_user.create_api_key(routes_user.CreateAPIKeyRequest(name=NOM_CLE_PORTAIL), user=ctx.user)
    except HTTPException:
        raise ErreurEtape("cle_refusee") from None
    base: dict[str, Any] | None = None
    nom_base = await rattachement.nom_de_la_base(ctx.organization_id)
    erreur_portail = None
    if nom_base:
        try:
            connexion = await routes_base.post_connexion_portail(Response(), user=ctx.user)
            base = {"base": connexion.base, "role": connexion.role, "mot_de_passe": connexion.mot_de_passe}
        except HTTPException:
            erreur_portail = "portail_refuse"
    fiche = fiche_portail(ctx.organization_id, ctx.installation["nom"], creee.api_key, creee.key_prefix, base)
    resultat = {"cle_id": creee.id, "cle_prefixe": creee.key_prefix, "base": base["base"] if base else None, "role": base["role"] if base else None}
    if erreur_portail:
        resultat["avertissement"] = erreur_portail
    return Sortie(resultat, montre={"fiche_portail": fiche})


def fiche_portail(
    organization_id: int, nom: str, cle_api: str, prefixe: str, base: dict[str, Any] | None
) -> dict[str, Any]:
    """Ce que le geste « ajouter un client » du portail reçoit (format figé avec SA-8, lot 17 ; voir la fiche SA-7)."""
    return {
        "format": "client-portail-mark",
        "version": 1,
        "organisation_id": organization_id,
        "nom": nom,
        "cle_api": {"valeur": cle_api, "prefixe": prefixe},
        "base": base,
    }


# --- 8. Appels simulés (DÉPENSE) ------------------------------------------------------------------------------------------


async def estimation(organization_id: int, workflow_id: int | None) -> dict[str, Any]:
    """Le montant estimé d'une série sur tous les scénarios de l'agent (coût moyen des appels simulés déjà joués), le plafond
    d'une série et la devise ; ``montant`` vaut ``None`` tant qu'aucun appel n'a été joué (le plafond borne alors la dépense)."""
    from api.services.analyse_run.cout import lire_reglages_fenetre
    from api.services.appel_simule.reglages import (
        lire_reglages,
        lire_scenarios,
        lire_series,
    )
    from api.services.appel_simule.serie import estimer_le_cout

    if workflow_id is None:
        return {"scenarios": 0, "montant": None, "plafond": None, "devise": "USD"}
    scenarios = await lire_scenarios(organization_id, workflow_id)
    reglages = await lire_reglages(organization_id)
    table = await lire_reglages_fenetre(organization_id)
    return {
        "scenarios": len(scenarios),
        "montant": estimer_le_cout(await lire_series(organization_id), workflow_id, len(scenarios)) if scenarios else None,
        "plafond": reglages.plafond,
        "devise": table.devise if table else "USD",
    }


async def appels_simules(ctx: Contexte) -> Sortie:
    from api.routes import appel_simule as routes
    from api.services.appel_simule.reglages import lire_scenarios, lire_series

    workflow_id = ctx.resultat_de(6).get("workflow_id")
    if not isinstance(workflow_id, int):
        raise ErreurEtape("agent_requis")
    deja = ctx.resultat_precedent.get("serie_id")
    if deja:
        return Sortie(dict(ctx.resultat_precedent))
    # Coupure entre le lancement et la note : la série de cet agent lancée par cette personne et encore en cours est reprise.
    for serie in await lire_series(ctx.organization_id):
        if serie.workflow_id == workflow_id and serie.lancee_par == ctx.user.id and serie.etat == "en_cours":
            return Sortie({"serie_id": serie.id, "appels": len(serie.appels), "workflow_id": workflow_id, "repris": True})
    voulus = [str(i) for i in (ctx.donnees.get("scenario_ids") or [])]
    if not voulus:
        voulus = [s.id for s in await lire_scenarios(ctx.organization_id, workflow_id)]
    if not voulus:
        raise ErreurEtape("aucun_scenario")
    try:
        serie = await routes.lancer_serie_simulee(workflow_id, routes.LancementSerie(scenario_ids=voulus), user=ctx.user)
    except HTTPException as erreur:
        raise _code_http(erreur, {409: "serie_refusee", 404: "agent_introuvable"}, "serie_refusee") from None
    resultat = {"serie_id": serie.id, "appels": len(serie.appels), "workflow_id": workflow_id, "cout_estime": serie.cout_estime, "devise": serie.devise}
    if ctx.noter is not None:
        await ctx.noter(resultat)
    return Sortie(resultat)


# --- 9. Récapitulatif -----------------------------------------------------------------------------------------------------


async def recapitulatif(ctx: Contexte) -> Sortie:
    """Ce qui est fait, ce qui est passé, et la liste « Prêt à publier » de l'agent (la même que la fenêtre Publier)."""
    from api.services.preparation import liste as liste_pret

    workflow_id = ctx.resultat_de(6).get("workflow_id")
    pret: list[dict[str, Any]] = []
    if isinstance(workflow_id, int):
        try:
            pret = await liste_pret.lire_la_liste(ctx.organization_id, workflow_id)
        except Exception:  # noqa: BLE001 -- le récapitulatif se rend même si la liste ne se lit pas
            pret = []
    from api.services.preparation import A_FAIRE, BLOQUANT

    return Sortie(
        {
            "workflow_id": workflow_id,
            "branche": ctx.resultat_de(6).get("branche"),
            "pret_a_publier": {
                "lignes": len(pret),
                "a_faire": sum(1 for l in pret if l.get("etat") == A_FAIRE),
                "bloquants": sum(1 for l in pret if l.get("etat") == BLOQUANT),
            },
            "passees": [e["numero"] for e in ctx.installation["etapes"] if e["etat"] == "passee"],
        }
    )


EXECUTANTS: dict[int, Callable[[Contexte], Awaitable[Sortie]]] = {
    2: base,
    3: etablissements,
    4: equipe,
    5: logiciels,
    6: agent,
    7: cle_portail,
    8: appels_simules,
    9: recapitulatif,
}
