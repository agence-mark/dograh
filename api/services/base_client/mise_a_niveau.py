"""[.mark] Chantier agents-specialises, lot 9 (D3) : mettre à niveau TOUTES les bases des clients.

À chaque déploiement, chaque base rattachée à une organisation passe à la version que cette installation
attend, une par une. Trois garanties, chacune testée :

- **jamais deux fois une migration** : un verrou de la base (``pg_try_advisory_lock``) serre une mise à niveau à
  la fois par base, et ``appliquer_migrations`` ne rejoue que ce qui dépasse la version écrite ;
- **un échec sur une base n'arrête pas les autres** : il est RAPPORTÉ (la base, la cause), jamais levé ;
- **un résultat qu'on peut lire** : pour chaque base, la version avant et après, et ce qui a été appliqué.

Le compte propriétaire (``MARK_BASES_CLIENTS_URL``) est le seul à créer ou à mettre à niveau ; rien ici ne
l'affiche, et un message d'erreur ne porte jamais l'adresse du serveur (``connexion.py``).

Lancé dans le conteneur du service ``api`` (l'image n'emporte que ``./api``) :

    python -m api.services.base_client.mise_a_niveau

Une ligne par base : OK (version avant -> après), IGNORÉE (une autre mise à niveau est en cours), ÉCHEC (la
cause). Code de sortie 1 s'il y a au moins un échec (l'échec d'une base n'arrête pas les autres), 0 sinon.
Sur Railway : ``railway ssh --service api -- python -m api.services.base_client.mise_a_niveau``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from api.db.bases_clients.connexion import (
    BaseClientIndisponible,
    appliquer_migrations,
    assurer_compte_courant,
    connecter_proprietaire,
    version_attendue,
    version_de,
)

# Un nombre de verrou propre à la mise à niveau des bases clientes (le nom de la base fait la portée).
CLE_VERROU = 7_015_015


@dataclass
class ResultatBase:
    organisation_id: int
    base: str
    avant: int | None = None
    apres: int | None = None
    appliquees: list[int] = field(default_factory=list)
    erreur: str | None = None
    ignoree: str | None = None

    @property
    def reussie(self) -> bool:
        return self.erreur is None

    def ligne(self) -> str:
        """Une ligne lisible, jamais un secret : l'organisation, la base, la version."""
        if self.erreur:
            return f"ÉCHEC  org {self.organisation_id}  {self.base}  : {self.erreur}"
        if self.ignoree:
            return f"IGNORÉE org {self.organisation_id}  {self.base}  : {self.ignoree}"
        if self.appliquees:
            return f"OK     org {self.organisation_id}  {self.base}  : {self.avant} -> {self.apres} ({self.appliquees})"
        return f"OK     org {self.organisation_id}  {self.base}  : déjà à la version {self.apres}"


async def mettre_a_niveau_une_base(organisation_id: int, nom_base: str) -> ResultatBase:
    """Une base : verrou, migrations, compte courant. Ne lève jamais."""
    resultat = ResultatBase(organisation_id, nom_base)
    try:
        connexion = await connecter_proprietaire(nom_base)
    except Exception as erreur:  # noqa: BLE001 -- une base injoignable n'arrête pas les autres
        resultat.erreur = _dire(erreur)
        return resultat
    verrouillee = False
    try:
        verrouillee = bool(
            await connexion.fetchval("SELECT pg_try_advisory_lock($1)", CLE_VERROU)
        )
        if not verrouillee:
            resultat.ignoree = "une autre mise à niveau est en cours sur cette base"
            return resultat
        resultat.avant = await version_de(connexion)
        resultat.appliquees = await appliquer_migrations(connexion)
        # Le compte courant reçoit ses droits sur les tables que la migration vient de créer.
        await assurer_compte_courant(connexion, nom_base)
        resultat.apres = await version_de(connexion)
    except Exception as erreur:  # noqa: BLE001
        resultat.erreur = _dire(erreur)
    finally:
        if verrouillee:
            try:
                await connexion.execute("SELECT pg_advisory_unlock($1)", CLE_VERROU)
            except Exception:  # noqa: BLE001 -- la connexion se ferme, le verrou tombe avec elle
                pass
        await connexion.close()
    return resultat


def _dire(erreur: Exception) -> str:
    if isinstance(erreur, BaseClientIndisponible):
        return str(erreur)  # déjà sans adresse ni mot de passe
    return f"{type(erreur).__name__} : {str(erreur).splitlines()[0][:200] if str(erreur) else ''}".strip(
        " :"
    )


async def mettre_a_niveau_toutes_les_bases(
    bases: list[tuple[int, str]] | None = None,
) -> list[ResultatBase]:
    """Chaque base rattachée, une par une. ``bases`` : ``[(organisation, nom)]`` (les tests) ; absent :
    la liste des organisations rattachées. Une base nommée par deux organisations n'est mise à niveau
    qu'une fois (la seconde est signalée : c'est une anomalie de rattachement)."""
    if bases is None:
        from api.services.base_client.rattachement import organisations_rattachees

        bases = await organisations_rattachees()
    resultats: list[ResultatBase] = []
    vues: dict[str, int] = {}
    for organisation_id, nom_base in bases:
        if nom_base in vues:
            resultats.append(
                ResultatBase(
                    organisation_id,
                    nom_base,
                    erreur=f"la base est aussi rattachée à l'organisation {vues[nom_base]} : à corriger",
                )
            )
            continue
        vues[nom_base] = organisation_id
        resultat = await mettre_a_niveau_une_base(organisation_id, nom_base)
        if not resultat.reussie:
            logger.error(
                f"[.mark] Client database upgrade failed (org {organisation_id}, {nom_base}): {resultat.erreur}"
            )
        resultats.append(resultat)
    return resultats


def version_cible() -> int:
    return version_attendue()


async def _principal() -> int:
    resultats = await mettre_a_niveau_toutes_les_bases()
    if not resultats:
        print("Aucune base rattachée : rien à mettre à niveau.")
        return 0
    print(f"Version attendue : {version_cible()}")
    for r in resultats:
        print(r.ligne())
    echecs = [r for r in resultats if not r.reussie]
    print(f"{len(resultats) - len(echecs)} base(s) à jour, {len(echecs)} en échec.")
    return 1 if echecs else 0


if __name__ == "__main__":
    import asyncio
    import sys

    sys.exit(asyncio.run(_principal()))
