"""[.mark] The client's own Postgres database: where it is, its schema, its version (B4 to B6).

Chantier ``l-agent-travaille``, L3. One database per client, on a Postgres of its own
(not Dograh's, B5). Attaching a database = choosing its NAME on screen (B4): the server,
the user and the password are the installation's, read from the environment variable
``MARK_BASES_CLIENTS_URL`` (``postgresql://user:password@host:port``), never typed on
screen and never stored in Dograh's database.

The schema is versioned here (B6): ``migrations/NNN-*.sql``, additive only, applied in
order, each one inside its own transaction, each one recording its line in
``mark.schema_version`` (it carries its own ``INSERT``). « Create database » makes the
database and applies them all; « Upgrade » applies those past the current version.

⛔ The password never leaves this module: errors are re-raised without the address.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

# A database behind this installation: a column, a table or a function of a later migration is missing.
ERREURS_SCHEMA_EN_RETARD = (
    asyncpg.UndefinedColumnError,
    asyncpg.UndefinedTableError,
    asyncpg.UndefinedFunctionError,
)

VARIABLE_ENV = "MARK_BASES_CLIENTS_URL"
# Décision d'Evan du 07/10 (n° 317): the OWNER account above only creates and upgrades a
# database. Every usual connection uses this account instead (``postgresql://user:password@
# host:port``, same server): no privilege of its own, it takes ``<base>_ecriture``.
VARIABLE_COMPTE = "MARK_BASES_CLIENTS_COMPTE_URL"
DOSSIER_MIGRATIONS = Path(__file__).parent / "migrations"
# 3 to 53 characters: ``<base>_direction`` must fit in Postgres's 63.
_NOM = re.compile(r"^[a-z][a-z0-9_]{2,52}$")
_MIGRATION = re.compile(r"^(\d{3})-[a-z0-9-]+\.sql$")
DELAI_CONNEXION_S = 5


class BaseClientIndisponible(RuntimeError):
    """The server is not configured, or does not answer. Message safe to show."""


class CompteSansDroits(BaseClientIndisponible):
    """The connection account may not work in this database yet (made before 006, or
    attached without the owner's grant): « Upgrade » gives it its rights."""


class BaseDejaExistante(ValueError):
    """[.mark] « Create » on a name the server already has: never reuse a database silently
    (it may be another client's)."""


class NomDeBaseInvalide(ValueError):
    pass


def verifier_nom(nom: str) -> str:
    if not isinstance(nom, str) or not _NOM.match(nom):
        raise NomDeBaseInvalide(
            "A database name takes lower case letters, digits and underscores, 3 to 53 characters, "
            "starting with a letter."
        )
    if nom in {"postgres", "template0", "template1"}:
        raise NomDeBaseInvalide(f"« {nom} » is a system database.")
    return nom


def serveur_configure() -> bool:
    return bool(os.environ.get(VARIABLE_ENV, "").strip())


def _morceaux(variable: str):
    brut = os.environ.get(variable, "").strip()
    if not brut:
        raise BaseClientIndisponible(
            f"The clients' Postgres is not configured on this installation ({variable})."
        )
    return urlsplit(brut.replace("postgresql+asyncpg://", "postgresql://", 1))


def _dsn(nom_base: str, variable: str = VARIABLE_ENV) -> str:
    morceaux = _morceaux(variable)
    return urlunsplit(
        (morceaux.scheme, morceaux.netloc, f"/{nom_base}", morceaux.query, "")
    )


def role_ecriture(nom_base: str) -> str:
    return f"{verifier_nom(nom_base)}_ecriture"


async def connecter(nom_base: str) -> asyncpg.Connection:
    """The USUAL connection to ONE client's database (n° 317): the installation's connection
    account, as ``<base>_ecriture``. Never shows the address in an error."""
    nom_base = verifier_nom(nom_base)
    connexion = await _connecter(nom_base, VARIABLE_COMPTE)
    try:
        # The name passed the pattern above: a safe identifier.
        await connexion.execute(f'SET ROLE "{role_ecriture(nom_base)}"')
    except Exception:  # noqa: BLE001
        await connexion.close()
        raise CompteSansDroits(
            f"The connection account may not work in « {nom_base} » yet: upgrade the database "
            "(« Client data »)."
        ) from None
    return connexion


async def connecter_proprietaire(nom_base: str) -> asyncpg.Connection:
    """The OWNER's connection: « Create » and « Upgrade » only."""
    return await _connecter(verifier_nom(nom_base))


async def assurer_compte_courant(connexion: asyncpg.Connection, nom_base: str) -> None:
    """With the owner's connection: the connection account exists (no privilege of its
    own, NOINHERIT: it must SET ROLE), may connect to this database and take its
    ``<base>_ecriture``. Its password follows the installation's variable."""
    morceaux = _morceaux(VARIABLE_COMPTE)
    compte, mot_de_passe = morceaux.username, morceaux.password
    if not compte or not mot_de_passe:
        raise BaseClientIndisponible(
            f"{VARIABLE_COMPTE} must carry the connection account and its password."
        )
    attributs = (
        "LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )
    existe = await connexion.fetchval(
        "SELECT 1 FROM pg_roles WHERE rolname = $1", compte
    )
    ordre = await connexion.fetchval(
        f"SELECT format('{'ALTER' if existe else 'CREATE'} ROLE %I {attributs} PASSWORD %L', $1::text, $2::text)",
        compte,
        mot_de_passe,
    )
    await connexion.execute(ordre)
    await connexion.execute(
        await connexion.fetchval(
            "SELECT format('GRANT CONNECT ON DATABASE %I TO %I', $1::text, $2::text)",
            verifier_nom(nom_base),
            compte,
        )
    )
    await connexion.execute(
        await connexion.fetchval(
            "SELECT format('GRANT %I TO %I', $1::text, $2::text)",
            role_ecriture(nom_base),
            compte,
        )
    )


async def _connecter(nom_base: str, variable: str = VARIABLE_ENV) -> asyncpg.Connection:
    try:
        return await asyncpg.connect(
            _dsn(nom_base, variable), timeout=DELAI_CONNEXION_S
        )
    except (BaseClientIndisponible, NomDeBaseInvalide):
        raise
    except asyncpg.InvalidCatalogNameError:
        raise BaseClientIndisponible(
            f"The database « {nom_base} » does not exist on the clients' Postgres."
        ) from None
    except (
        asyncpg.InvalidPasswordError,
        asyncpg.InvalidAuthorizationSpecificationError,
    ):
        if variable == VARIABLE_COMPTE:
            # The connection account does not exist yet, or its password changed:
            # « Upgrade » (the owner) creates it or sets its password again.
            raise CompteSansDroits(
                f"The connection account cannot log in to « {nom_base} » yet: upgrade the "
                "database (« Client data »)."
            ) from None
        raise BaseClientIndisponible(
            "The clients' Postgres refused the owner's account."
        ) from None
    except Exception as erreur:  # noqa: BLE001 -- the message must not carry the DSN
        raise BaseClientIndisponible(
            f"The clients' Postgres does not answer ({type(erreur).__name__})."
        ) from None


@dataclass(frozen=True)
class Migration:
    version: int
    nom: str
    sql: str


def migrations() -> list[Migration]:
    trouvees = []
    for chemin in sorted(DOSSIER_MIGRATIONS.glob("*.sql")):
        m = _MIGRATION.match(chemin.name)
        if m:
            trouvees.append(
                Migration(
                    int(m.group(1)), chemin.name, chemin.read_text(encoding="utf-8")
                )
            )
    versions = [m.version for m in trouvees]
    assert versions == list(range(1, len(versions) + 1)), (
        f"Migrations not numbered 001, 002…: {versions}"
    )
    return trouvees


def version_attendue() -> int:
    return migrations()[-1].version


async def version_de(connexion: asyncpg.Connection) -> int | None:
    """The schema's version, or None when the database has no .mark schema yet."""
    existe = await connexion.fetchval(
        "SELECT to_regclass('mark.schema_version') IS NOT NULL"
    )
    if not existe:
        return None
    return await connexion.fetchval("SELECT max(version) FROM mark.schema_version")


async def appliquer_migrations(connexion: asyncpg.Connection) -> list[int]:
    """Apply every migration past the current version, each in its own transaction."""
    actuelle = await version_de(connexion) or 0
    appliquees = []
    for migration in migrations():
        if migration.version <= actuelle:
            continue
        # 001 is the reference script, which carries its own BEGIN/COMMIT.
        sql = migration.sql.replace("\nBEGIN;\n", "\n").replace("\nCOMMIT;\n", "\n")
        async with connexion.transaction():
            await connexion.execute(sql)
        appliquees.append(migration.version)
    return appliquees


async def creer_base(nom_base: str, *, reprendre: bool = False) -> list[int]:
    """CREATE DATABASE on the clients' Postgres, then every migration. A name the server
    already has is refused (``BaseDejaExistante``) unless ``reprendre`` (tests, scripts)."""
    verifier_nom(nom_base)
    # The server's maintenance database: the only place a CREATE DATABASE can run from.
    maintenance = await _connecter("postgres")
    try:
        existe = await maintenance.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", nom_base
        )
        if existe and not reprendre:
            raise BaseDejaExistante(
                f"A database named « {nom_base} » already exists on the server: choose another "
                "name, or attach it if it is this organization's."
            )
        if not existe:
            # An identifier cannot be a parameter; the name was checked by the pattern above.
            await maintenance.execute(f'CREATE DATABASE "{nom_base}"')
    finally:
        await maintenance.close()
    connexion = await connecter_proprietaire(nom_base)
    try:
        appliquees = await appliquer_migrations(connexion)
        await assurer_compte_courant(connexion, nom_base)
        return appliquees
    finally:
        await connexion.close()


async def ecouter(nom_base: str, canal: str, rappel) -> asyncpg.Connection:
    """A connection that stays open and LISTENs on ``canal`` (``rappel(connexion, pid,
    canal, charge)``). The caller closes it."""
    connexion = await connecter(nom_base)
    try:
        await connexion.add_listener(canal, rappel)
    except Exception:
        await connexion.close()
        raise
    return connexion
