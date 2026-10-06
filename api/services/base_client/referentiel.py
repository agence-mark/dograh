"""[.mark] The referential read from the client's database, CHECKED as the screen checks it (B2).

A value written in the database that Dograh would not accept on screen (hours that do
not parse, a number not in international format) is REFUSED: not taken (the previous
value, from the copy in memory, stays) and reported (decision of Evan, 06/10, option A:
« refus notifié »). One bad row never empties the others.

The SQL is in ``api/db/bases_clients/referentiel.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.db.bases_clients.referentiel import lignes_du_referentiel
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.lexique_metier import TermeLexique
from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.phrases import CataloguePhrases, Phrase


@dataclass
class Referentiel:
    etablissements: CatalogueEtablissements = field(
        default_factory=CatalogueEtablissements
    )
    phrases: CataloguePhrases = field(default_factory=CataloguePhrases)
    refus: list[str] = field(default_factory=list)


async def lire_referentiel(
    connexion, avant: CatalogueEtablissements | None = None
) -> Referentiel:
    """The establishments and sentences as a call reads them, and what was refused.

    ``avant``: the copy currently in memory; a refused value keeps its value from it.
    """
    from api.services.pipecat.etat_ouverture import (
        HorairesInvalides,
        vers_expression_osm,
    )

    refus: list[str] = []
    precedents = {e.id: e for e in (avant.etablissements if avant else [])}
    lignes = await lignes_du_referentiel(connexion)
    sites, numeros, surcharges, lignes_phrases = (
        lignes.sites,
        lignes.numeros,
        lignes.surcharges,
        lignes.phrases,
    )

    phrases: list[Phrase] = []
    for ligne in lignes_phrases:
        try:
            phrases.append(Phrase(**dict(ligne)))
        except Exception as erreur:  # noqa: BLE001
            refus.append(f"sentence « {ligne['variable']} »: {erreur}")

    etablissements: list[Etablissement] = []
    for site in sites:
        cle = site["cle"]
        precedent = precedents.get(cle)
        horaires = site["horaires_texte"]
        if horaires:
            try:
                vers_expression_osm(horaires)
            except HorairesInvalides as erreur:
                refus.append(
                    f"{site['nom']}: hours refused ({erreur}); the previous hours are kept"
                )
                horaires = precedent.horaires_ouverture if precedent else None
        adresse = None
        if site["adresse_insee"] and site["adresse_cp"]:
            try:
                adresse = AdresseEtablissement(
                    code_postal=site["adresse_cp"].strip(),
                    code_insee=site["adresse_insee"].strip(),
                    commune=site["adresse_commune"] or "",
                    voie=site["adresse_voie"],
                )
            except Exception as erreur:  # noqa: BLE001
                refus.append(f"{site['nom']}: address refused ({erreur})")
                adresse = precedent.adresse if precedent else None
        termes = []
        for brut in site["termes_lexique"]:
            try:
                termes.append(TermeLexique.model_validate(brut))
            except Exception as erreur:  # noqa: BLE001
                refus.append(f"{site['nom']}: term refused ({erreur})")
        donnees = {
            "id": cle,
            "nom": site["nom"],
            "numeros": [n["numero"] for n in numeros if n["site_id"] == site["id"]],
            "second_numero": site["second_numero"],
            "numero_transfert": site["numero_transfert"],
            "adresse": adresse,
            "horaires_ouverture": horaires,
            "annonce_fermeture": site["annonce_fermeture"],
            "annonce_pause": site["annonce_pause"],
            "phrases": {
                s["variable"]: s["contenu"]
                for s in surcharges
                if s["site_id"] == site["id"]
            },
            "termes_lexique": termes,
        }
        try:
            etablissements.append(Etablissement.model_validate(donnees))
        except Exception as erreur:  # noqa: BLE001 -- one bad row never empties the others
            refus.append(
                f"{site['nom']}: refused ({erreur}); the previous values are kept"
            )
            if precedent is not None:
                etablissements.append(precedent)
    try:
        catalogue = CatalogueEtablissements(etablissements=etablissements)
    except Exception as erreur:  # noqa: BLE001 -- e.g. one number on two sites
        refus.append(
            f"establishments refused as a whole ({erreur}); the previous copy is kept"
        )
        catalogue = avant or CatalogueEtablissements()
    try:
        catalogue_phrases = CataloguePhrases(phrases=phrases)
    except Exception as erreur:  # noqa: BLE001
        refus.append(f"sentences refused as a whole ({erreur})")
        catalogue_phrases = CataloguePhrases()
    return Referentiel(etablissements=catalogue, phrases=catalogue_phrases, refus=refus)
