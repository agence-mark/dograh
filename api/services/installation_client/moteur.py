"""[.mark] Partie 3, sous-lot 9 (SE-5, O-2, § 5 du plan) : le moteur de « Nouveau client ».

* ``demarrer`` crée l'organisation (route existante ``POST /organizations``, même fonction) et son installation (étape 1
  faite) ; relancé sur un identifiant déjà pris par un client dont l'installation est ouverte et accessible, il la REPREND ;
* ``executer`` prend une étape (atomique : un double clic n'exécute qu'une fois), appelle son exécutant (``executants``), la
  ferme « faite » ou « erreur » avec une phrase précise. Une étape faite ou passée est sautée. Les étapes se font dans l'ordre.
  Une étape qui dépense est refusée sans confirmation. Une étape restée « en cours » après une coupure (processus arrêté,
  connexion perdue) se reprend une fois son bail écoulé ;
* ``passer`` laisse de côté une étape passable ; ``lire`` et ``ouvertes`` rendent l'état ;
* chaque geste est écrit au journal de l'équipe (qui, quoi, quand, quel client).

Tout se lit et s'écrit avec l'organisation de l'appelant (l'adresse, contrôlée par ``get_user``) : l'installation d'un
client n'est ni lue ni reprise depuis un autre.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db import db_client
from api.db.installation_client_client import InstallationDejaOuverte
from api.services.equipe_mark.acces import est_par_cle_api, journaliser
from api.services.installation_client import executants
from api.services.installation_client.etapes import ETAPES, etape, phrase

# Une étape « en cours » depuis plus longtemps est tenue pour coupée et se reprend.
BAIL_S = 600
ETATS_CLOS = ("faite", "passee")


class RefusInstallation(Exception):
    def __init__(self, statut: int, code: str, *, estimation: dict[str, Any] | None = None):
        super().__init__(code)
        self.statut = statut
        self.code = code
        self.estimation = estimation

    def detail(self) -> dict[str, Any]:
        corps: dict[str, Any] = {"code": self.code, **(phrase(self.code) or {})}
        if self.estimation is not None:
            corps["estimation"] = self.estimation
        return corps


def _resultat_montrable(numero: int, resultat: dict[str, Any]) -> dict[str, Any]:
    """Ce qui est rangé ne contient aucun secret ; on le rend tel quel (identifiants, noms, préfixes)."""
    return dict(resultat or {})


async def vue(installation: dict[str, Any]) -> dict[str, Any]:
    organisation = installation["organization_id"]
    par_numero = {e["numero"]: e for e in installation["etapes"]}
    etapes = []
    for definition in ETAPES:
        e = par_numero.get(definition.numero) or {"etat": "a_faire", "resultat": {}}
        etapes.append(
            {
                "numero": definition.numero,
                "cle": definition.cle,
                "titre": definition.titre,
                "passable": definition.passable,
                "depense": definition.depense,
                "etat": e["etat"],
                "le": e.get("le"),
                "par": e.get("par"),
                "erreur": phrase(e.get("derniere_erreur")) if e["etat"] == "erreur" else None,
                "code_erreur": e.get("derniere_erreur") if e["etat"] == "erreur" else None,
                "resultat": _resultat_montrable(definition.numero, e.get("resultat") or {}),
            }
        )
    prochaine = next((e["numero"] for e in etapes if e["etat"] not in ETATS_CLOS), None)
    workflow_id = (par_numero.get(6, {}).get("resultat") or {}).get("workflow_id")
    complement: dict[str, Any] = {}
    if prochaine == 8:
        complement["estimation"] = await executants.estimation(organisation, workflow_id)
    if prochaine == 6:
        agents = await db_client.get_all_workflows_for_listing(organization_id=organisation, status="active")
        complement["agents_du_client"] = [{"id": a.id, "nom": a.name} for a in agents[:20]]
    return {
        "id": installation["id"],
        "organization_id": organisation,
        "nom": installation["nom"],
        "etat": installation["etat"],
        "cree_le": installation["cree_le"],
        "etapes": etapes,
        "prochaine": prochaine,
        **complement,
    }


async def _ouverte(organization_id: int) -> dict[str, Any]:
    installation = await db_client.installation_ouverte(organization_id)
    if installation is None:
        raise RefusInstallation(404, "installation_introuvable")
    return installation


async def demarrer(user, nom: str, identifiant: str) -> dict[str, Any]:
    from api.services.builder.constantes import organisation_bibliotheque
    from api.services.equipe_mark import espaces
    from api.services.equipe_mark.acces import acces_de, organisation_accessible
    from api.services.organization_membership import (
        OrganizationProviderIdTakenError,
        create_organization_for_user,
    )

    if est_par_cle_api(user):
        raise RefusInstallation(403, "par_une_personne")
    try:
        organisation = await create_organization_for_user(user, provider_id=identifiant, select=False)
    except OrganizationProviderIdTakenError:
        # Rejoué (double clic, réponse perdue) : l'installation ouverte de ce client, s'il est accessible, est reprise.
        existante = await db_client.get_organization_by_provider_id(identifiant)
        if existante is not None and await organisation_accessible(
            user.id, existante.id, await acces_de(user), organisation_bibliotheque()
        ):
            ouverte = await db_client.installation_ouverte(existante.id)
            if ouverte is not None:
                return await vue(ouverte)
        raise RefusInstallation(409, "nom_pris") from None
    await espaces.definir_nom_affichage(organisation.id, nom)
    try:
        installation = await db_client.creer_installation(organisation.id, nom, user.id)
    except InstallationDejaOuverte:
        installation = await _ouverte(organisation.id)
    await journaliser(user, "installation.demarrer", organisation.id, {"nom": nom, "etape": 1})
    return await vue(installation)


async def lire(organization_id: int) -> dict[str, Any]:
    return await vue(await _ouverte(organization_id))


async def ouvertes(user) -> list[dict[str, Any]]:
    """Les installations ouvertes des clients que le rôle du compte ouvre (filtre dans la requête)."""
    from api.services.equipe_mark import espaces

    visibles = [e["id"] for e in await espaces.lister_espaces(user) if e["espace"] == "client"]
    lignes = await db_client.installations_ouvertes(visibles)
    resume = []
    for l in lignes:
        prochaine = next((e["numero"] for e in l["etapes"] if e["etat"] not in ETATS_CLOS), None)
        faites = sum(1 for e in l["etapes"] if e["etat"] in ETATS_CLOS)
        erreur = any(e["etat"] == "erreur" for e in l["etapes"])
        resume.append(
            {"id": l["id"], "organization_id": l["organization_id"], "nom": l["nom"], "cree_le": l["cree_le"], "prochaine": prochaine, "faites": faites, "erreur": erreur}
        )
    return resume


async def executer(user, organization_id: int, numero: int, donnees: dict[str, Any], *, confirmer: bool = False) -> dict[str, Any]:
    if numero == 1:
        # L'étape 1 est faite à la création ; la rejouer ne refait rien.
        return {"installation": await lire(organization_id), "sautee": True, "montre": None, "echec": None}
    definition = etape(numero)
    installation = await _ouverte(organization_id)
    actuelle = next(e for e in installation["etapes"] if e["numero"] == numero)
    if actuelle["etat"] in ETATS_CLOS:
        return {"installation": await vue(installation), "sautee": True, "montre": None, "echec": None}
    if definition.depense and not confirmer:
        workflow_id = next((e["resultat"] or {} for e in installation["etapes"] if e["numero"] == 6), {}).get("workflow_id")
        raise RefusInstallation(409, "confirmation_requise", estimation=await executants.estimation(organization_id, workflow_id))
    if not await db_client.prendre_etape(organization_id, installation["id"], numero, user.id, bail_s=BAIL_S):
        relue = await _ouverte(organization_id)
        etat = next(e for e in relue["etapes"] if e["numero"] == numero)["etat"]
        if etat in ETATS_CLOS:  # l'autre requête du double clic l'a faite
            return {"installation": await vue(relue), "sautee": True, "montre": None, "echec": None}
        raise RefusInstallation(409, "en_cours" if etat == "en_cours" else "ordre")

    async def noter(resultat: dict[str, Any]) -> None:
        await db_client.noter_resultat(organization_id, installation["id"], numero, resultat)

    contexte = executants.Contexte(
        user=user,
        organization_id=organization_id,
        installation=installation,
        donnees=donnees or {},
        resultat_precedent=dict(actuelle.get("resultat") or {}),
        noter=noter,
    )
    echec: str | None = None
    precisions: list[str] = []
    sortie: executants.Sortie | None = None
    try:
        sortie = await executants.EXECUTANTS[numero](contexte)
    except executants.ErreurEtape as erreur:
        echec = erreur.code
        precisions = erreur.precisions
    except Exception as erreur:  # noqa: BLE001 -- l'étape s'arrête proprement ; jamais le texte de l'erreur à l'écran
        logger.warning(f"[.mark] Installation step {numero} of organization {organization_id} failed ({type(erreur).__name__}).")
        echec = "inconnue"
    if echec is not None:
        await db_client.finir_etape(organization_id, installation["id"], numero, etat="erreur", user_id=user.id, erreur=echec)
        await journaliser(user, "installation.etape", organization_id, {"etape": numero, "cle": definition.cle, "etat": "erreur", "code": echec})
        return {"installation": await lire(organization_id), "sautee": False, "montre": None, "echec": {"code": echec, **(phrase(echec) or {}), "precisions": precisions}}
    assert sortie is not None
    await db_client.finir_etape(organization_id, installation["id"], numero, etat="faite", user_id=user.id, resultat=sortie.resultat)
    await journaliser(user, "installation.etape", organization_id, {"etape": numero, "cle": definition.cle, "etat": "faite"})
    if numero == 9:
        await db_client.terminer_installation(organization_id, installation["id"])
        await journaliser(user, "installation.terminer", organization_id, {"nom": installation["nom"]})
        finale = await db_client.installation_ouverte(organization_id, installation_id=installation["id"])
        return {"installation": await vue(finale), "sautee": False, "montre": sortie.montre, "echec": None}
    return {"installation": await lire(organization_id), "sautee": False, "montre": sortie.montre, "echec": None}


async def passer(user, organization_id: int, numero: int) -> dict[str, Any]:
    definition = etape(numero)
    if not definition.passable:
        raise RefusInstallation(422, "non_passable")
    installation = await _ouverte(organization_id)
    avant = [e for e in installation["etapes"] if e["numero"] < numero and e["etat"] not in ETATS_CLOS]
    if avant:
        raise RefusInstallation(409, "ordre")
    if not await db_client.passer_etape(organization_id, installation["id"], numero, user.id):
        relue = await _ouverte(organization_id)
        etat = next(e for e in relue["etapes"] if e["numero"] == numero)["etat"]
        if etat not in ETATS_CLOS:
            raise RefusInstallation(409, "en_cours")
        return await vue(relue)
    await journaliser(user, "installation.etape", organization_id, {"etape": numero, "cle": definition.cle, "etat": "passee"})
    return await lire(organization_id)
