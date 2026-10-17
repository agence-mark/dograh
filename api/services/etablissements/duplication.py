"""[.mark] Chantier agents-specialises, lot 4 (F2, M2): a new fiche made from an existing one.

A copy takes everything that describes the PLACE (name apart): address, hours, announcements,
sentences, terms of the trade vocabulary, and -- with a client database -- the appointment
settings and the appointment types of the source. It NEVER takes what is specific to the
line: the called numbers, the second number, the transfer number, nor the immediate closure
(a copied closure would shut a shop that never asked for it). The person fills those on the
new fiche.

Pure: no storage here, the route reads and writes. Nothing here knows a trade.
"""

from __future__ import annotations

from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.planificateur import Planificateur

# What a copy leaves empty, for the screen to say (field names, no wording of a trade).
NON_COPIE = ("numeros", "second_numero", "numero_transfert", "etat_force", "etat_force_jusqu_a")


class SourceInconnue(ValueError):
    """The fiche to copy does not exist. Safe to show."""


class IdentifiantPris(ValueError):
    """The new identifier is already a fiche's. Safe to show."""


def dupliquer(catalogue: CatalogueEtablissements, source: str, identifiant: str, nom: str) -> Etablissement:
    """The new fiche (validated like any other); the catalogue is not changed."""
    origine = next((e for e in catalogue.etablissements if e.id == source), None)
    if origine is None:
        raise SourceInconnue(f"The fiche « {source} » does not exist.")
    if any(e.id == identifiant for e in catalogue.etablissements):
        raise IdentifiantPris(f"The identifier « {identifiant} » already belongs to a fiche.")
    valeurs = origine.model_dump()
    valeurs.update(
        id=identifiant,
        nom=nom,
        numeros=[],
        second_numero=None,
        numero_transfert=None,
        etat_force=None,
        etat_force_jusqu_a=None,
    )
    return Etablissement.model_validate(valeurs)


def reglages_dupliques(planificateur: Planificateur, source: str, nouvelle: str) -> tuple[Planificateur, int, bool]:
    """The planner's rules with the source's copied under the new fiche.

    Returns ``(planificateur, number of types copied, settings copied)``. Without anything
    of the source's to copy, the SAME object comes back.
    """
    propres = planificateur.par_etablissement.get(source)
    types = [t for t in planificateur.types if t.etablissement == source]
    if propres is None and not types:
        return planificateur, 0, False
    par_etablissement = dict(planificateur.par_etablissement)
    if propres is not None:
        par_etablissement[nouvelle] = propres.model_copy(deep=True)
    copies = [t.model_copy(update={"etablissement": nouvelle}) for t in types]
    return (
        planificateur.model_copy(
            update={"par_etablissement": par_etablissement, "types": [*planificateur.types, *copies]}
        ),
        len(copies),
        propres is not None,
    )
