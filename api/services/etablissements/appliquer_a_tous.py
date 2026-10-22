"""[.mark] cloture-code, D152 (Evan, 22/10) : « Appliquer à tous les établissements ».

Recopie UN réglage d'un établissement (la source) dans tous les autres établissements de l'organisation.
La valeur est lue sur la source par le serveur ; l'écran n'envoie que quel réglage. Dograh fait tout sans
restriction : le filtre « ceux que le compte voit » est celui du portail, pas d'ici.

Deux chemins, une seule règle (tout ou rien) :

- les champs de la fiche (horaires, adresse, annonces) et les contenus de phrases s'écrivent comme tout
  enregistrement de fiche : par le catalogue, en une transaction dans la base du client (ou, sans base, en
  une seule écriture du miroir) ; les déclencheurs journalisent établissement par établissement ;
- les règles du planificateur, les types de rendez-vous et les réglages terrain des modules vivent dans la
  base du client (``api/db/bases_clients/appliquer_a_tous.py``), en une transaction aussi.

L'organisation est celle du compte (``selected_organization_id``) : le catalogue lu est le sien, et la
base écrite est celle qui lui est rattachée. La route prend le verrou des fiches autour de l'appel.

Aucun mot de métier : des noms de champs.
"""

from __future__ import annotations

from pydantic import ValidationError

from api.db.bases_clients.connexion import ERREURS_SCHEMA_EN_RETARD, connecter
from api.db.bases_clients.appliquer_a_tous import appliquer_a_tous as appliquer_dans_la_base
from api.db.bases_clients.planificateur import ReferenceInconnue
from api.schemas.appliquer_a_tous import (
    CHAMPS_DE_FICHE,
    DemandeAppliquerATous,
    EtablissementTouche,
    ResultatAppliquerATous,
)
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.services.etablissements.stockage import (
    enregistrer_etablissements,
    lire_phrases_strict,
    nom_de_la_base_strict,
)


class RefusAppliquer(Exception):
    """Un refus qu'on peut montrer ; rien n'a été écrit. ``code`` : le statut HTTP."""

    def __init__(self, message: str, code: int = 422):
        super().__init__(message)
        self.code = code


def _vide(valeur) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


async def appliquer_a_tous(
    organization_id: int,
    catalogue: CatalogueEtablissements,
    source_id: str,
    demande: DemandeAppliquerATous,
    auteur: str,
) -> ResultatAppliquerATous:
    """``catalogue``: les établissements enregistrés de l'organisation (lecture stricte, faite par la route)."""
    source = next((e for e in catalogue.etablissements if e.id == source_id), None)
    if source is None:
        raise RefusAppliquer(f"Establishment « {source_id} » not found.", 404)
    autres = [e for e in catalogue.etablissements if e.id != source_id]
    if not autres:
        raise RefusAppliquer("There is no other establishment to apply it to.", 409)

    if demande.reglage in ("fiche", "phrase"):
        await _ecrire_la_fiche(organization_id, catalogue, source, demande, auteur)
    else:
        await _ecrire_dans_la_base(organization_id, source_id, demande, auteur)
    return ResultatAppliquerATous(
        source=source_id,
        reglage=demande.reglage,
        cle=demande.cle,
        etablissements=[EtablissementTouche(id=e.id, nom=e.nom) for e in autres],
    )


async def _ecrire_la_fiche(
    organization_id: int,
    catalogue: CatalogueEtablissements,
    source: Etablissement,
    demande: DemandeAppliquerATous,
    auteur: str,
) -> None:
    if demande.reglage == "fiche":
        if demande.cle not in CHAMPS_DE_FICHE:
            raise RefusAppliquer(f"« {demande.cle} » is not a field that is applied to all the establishments.")
        valeur = source.model_dump()[demande.cle]
        vide = _vide(valeur)

        def modifiee(e: Etablissement) -> dict:
            return {demande.cle: None if vide else valeur}
    else:
        try:
            phrases = await lire_phrases_strict(organization_id)
        except Exception:  # noqa: BLE001 -- unreadable: nothing can be judged, nothing is written
            raise RefusAppliquer("The sentences of this organization cannot be read. Nothing was changed.", 500) from None
        if demande.cle not in {p.variable for p in phrases.phrases if p.niveau == "etablissement"}:
            raise RefusAppliquer(f"« {demande.cle} » is not a sentence placed at the establishment's level.")
        contenu = source.phrases.get(demande.cle)

        def modifiee(e: Etablissement) -> dict:
            reste = {v: c for v, c in e.phrases.items() if v != demande.cle}
            return {"phrases": reste if _vide(contenu) else {**reste, demande.cle: contenu}}

    try:
        nouveau = CatalogueEtablissements(
            etablissements=[
                e if e.id == source.id else Etablissement.model_validate({**e.model_dump(), **modifiee(e)})
                for e in catalogue.etablissements
            ]
        )
    except ValidationError as erreur:
        raise RefusAppliquer(
            "; ".join(f"{'.'.join(str(p) for p in m['loc'])}: {m['msg']}" for m in erreur.errors(include_url=False))
        ) from None
    # Un seul enregistrement, donc une seule transaction : le catalogue entier, sans prérempli (aucun lieu neuf).
    await enregistrer_etablissements(organization_id, nouveau, auteur, preremplir=False)


async def _ecrire_dans_la_base(
    organization_id: int, source_id: str, demande: DemandeAppliquerATous, auteur: str
) -> None:
    nom = await nom_de_la_base_strict(organization_id)
    if not nom:
        raise RefusAppliquer("Attach a client database first: these settings live there.", 409)
    connexion = await connecter(nom)
    try:
        try:
            await appliquer_dans_la_base(connexion, source_id, demande.reglage, demande.cle, auteur)
        except ReferenceInconnue as erreur:
            raise RefusAppliquer(str(erreur)) from None
        except ERREURS_SCHEMA_EN_RETARD:
            raise RefusAppliquer(
                "The client database is behind this installation: click « Upgrade » in the theme "
                "« Client data », then try again. Nothing was changed.",
                409,
            ) from None
    finally:
        await connexion.close()
    # La copie que lisent les appels se refait (jamais une raison d'échouer : ``publier_copie`` ne lève pas).
    from api.services.etablissements.copie import publier_copie

    await publier_copie(organization_id)
