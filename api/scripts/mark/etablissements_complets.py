"""[.mark] cloture-code, F-8 : recopie des valeurs communes dans les établissements existants, côté Dograh.

La règle d'Evan du 22/10 : un établissement a ses propres règles complètes, aucune valeur n'est héritée de
l'organisation. Pour qu'aucun client existant n'entende autre chose au téléphone, ce script écrit dans
chaque champ VIDE d'un établissement ce qu'un appel y lisait avant la règle (``plan_complets``) : horaires et
adresse de l'agent qui le sert par ses numéros (s'ils concordent), sinon l'adresse de l'organisation ;
annonces de fermeture et de pause de l'organisation ; contenus des phrases placées au niveau de
l'établissement. Une valeur déjà posée n'est JAMAIS remplacée.

Ce qui vit dans la base du client (règles du planificateur, fenêtre du tour de rôle, types de rendez-vous,
réglages des modules, contenus des phrases) est recopié par la migration additive 021 (« Mettre à niveau »
dans « Données du client ») : les deux gestes ne remplissent que du vide, dans n'importe quel ordre.

À blanc par défaut : compte et liste, n'écrit rien. ``--ecrire`` écrit. Rejoué, il ne trouve plus rien.
À lancer au déploiement, une fois, avec l'environnement de l'API (``api/.env``) :

    python -m api.scripts.mark.etablissements_complets              # à blanc
    python -m api.scripts.mark.etablissements_complets --ecrire     # écrit
    python -m api.scripts.mark.etablissements_complets --organisation 12 [--ecrire]

Ce qu'il ne tranche pas (``à décider``) : des horaires ou une adresse que les agents disent autrement que
l'établissement, ou différemment entre eux. Rien n'est écrit pour ceux-là. Aucun secret n'est lu ni affiché.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field

from loguru import logger

AUTEUR = "script etablissements-complets"


@dataclass
class Bilan:
    """Ce que le script a vu (ou fait) pour une organisation."""

    organization_id: int
    etablissements: int = 0
    valeurs: int = 0
    deja_a_jour: int = 0
    ecrit: bool = False
    actions: list[str] = field(default_factory=list)
    a_decider: list[str] = field(default_factory=list)
    a_signaler: list[str] = field(default_factory=list)
    erreur: str | None = None


async def traiter_organisation(organization_id: int, ecrire: bool) -> Bilan:
    """Une organisation : lit (lecture stricte : une source illisible n'est jamais réécrite), planifie, écrit
    si ``ecrire``. Ne lève pas : une erreur est dans ``Bilan.erreur`` et rien n'est écrit."""
    from api.schemas.etablissements import CatalogueEtablissements, Etablissement
    from api.services.annonce.stockage import lire_annonce_ouverture_strict
    from api.services.etablissements import reprise, stockage
    from api.services.etablissements.complets import plan_complets
    from api.services.organization_preferences import get_organization_preferences

    bilan = Bilan(organization_id)
    try:
        catalogue = await stockage.lire_etablissements_strict(organization_id)
        bilan.etablissements = len(catalogue.etablissements)
        if not catalogue.etablissements:
            return bilan
        preferences = await get_organization_preferences(organization_id)
        plan = plan_complets(
            catalogue,
            await reprise.lire_agents(organization_id),
            getattr(preferences, "adresse_etablissement", None),
            await lire_annonce_ouverture_strict(organization_id),
            await stockage.lire_phrases_strict(organization_id),
        )
        bilan.valeurs = len(plan.actions)
        bilan.deja_a_jour = plan.deja_a_jour
        bilan.actions = [f"{a.cible} · {a.champ}" for a in plan.actions]
        bilan.a_decider = list(plan.a_decider)
        bilan.a_signaler = list(plan.a_signaler)
        if not ecrire or not plan.fiches:
            return bilan
        complet = CatalogueEtablissements(
            etablissements=[
                Etablissement.model_validate({**f.model_dump(), **plan.fiches[f.id]}) if f.id in plan.fiches else f
                for f in catalogue.etablissements
            ]
        )
        await stockage.enregistrer_etablissements(organization_id, complet, AUTEUR)
        bilan.ecrit = True
    except Exception as erreur:  # noqa: BLE001 -- une organisation en échec n'arrête pas les autres
        bilan.erreur = f"{type(erreur).__name__}: {erreur}"
    return bilan


async def organisations_avec_etablissements() -> list[int]:
    """Les organisations dont le miroir porte des établissements (écrit à chaque enregistrement)."""
    from api.db import db_client
    from api.enums import OrganizationConfigurationKey

    lignes = await db_client.get_all_configurations_by_key(OrganizationConfigurationKey.ETABLISSEMENTS.value)
    return sorted({int(ligne["organization_id"]) for ligne in lignes})


async def executer(ecrire: bool, organisation: int | None = None) -> list[Bilan]:
    ids = [organisation] if organisation is not None else await organisations_avec_etablissements()
    return [await traiter_organisation(i, ecrire) for i in ids]


def rendre(bilans: list[Bilan], ecrire: bool) -> str:
    lignes = ["Écrit." if ecrire else "À blanc : rien n'est écrit (--ecrire pour écrire)."]
    for b in bilans:
        etat = "erreur" if b.erreur else ("écrit" if b.ecrit else ("à écrire" if b.valeurs else "rien à faire"))
        lignes.append(
            f"Organisation {b.organization_id} : {b.etablissements} établissement(s), {b.valeurs} valeur(s) "
            f"{'écrite(s)' if b.ecrit else 'à recopier'}, {b.deja_a_jour} déjà posée(s) : {etat}"
        )
        lignes += [f"  + {a}" for a in b.actions]
        lignes += [f"  ? à décider : {a}" for a in b.a_decider]
        lignes += [f"  ! à signaler : {a}" for a in b.a_signaler]
        if b.erreur:
            lignes.append(f"  ✗ {b.erreur}")
    total = sum(b.valeurs for b in bilans)
    lignes.append(f"Total : {total} valeur(s) {'écrite(s)' if ecrire else 'à recopier'}, {len(bilans)} organisation(s).")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ecrire", action="store_true", help="écrit (sinon : à blanc)")
    parser.add_argument("--organisation", type=int, default=None, help="une seule organisation")
    args = parser.parse_args(argv)
    bilans = asyncio.run(executer(args.ecrire, args.organisation))
    print(rendre(bilans, args.ecrire))
    if any(b.erreur for b in bilans):
        logger.warning("[.mark] Établissements complets : au moins une organisation en échec, rien d'écrit pour elle.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
