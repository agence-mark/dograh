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

VARIABLE_ENV = "MARK_BASES_CLIENTS_URL"
DOSSIER_MIGRATIONS = Path(__file__).parent / "migrations"
_NOM = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
_MIGRATION = re.compile(r"^(\d{3})-[a-z0-9-]+\.sql$")
DELAI_CONNEXION_S = 5


class BaseClientIndisponible(RuntimeError):
    """The server is not configured, or does not answer. Message safe to show."""


class NomDeBaseInvalide(ValueError):
    pass


def verifier_nom(nom: str) -> str:
    if not isinstance(nom, str) or not _NOM.match(nom):
        raise NomDeBaseInvalide(
            "A database name takes lower case letters, digits and underscores, 3 to 63 characters, "
            "starting with a letter."
        )
    if nom in {"postgres", "template0", "template1"}:
        raise NomDeBaseInvalide(f"« {nom} » is a system database.")
    return nom


def serveur_configure() -> bool:
    return bool(os.environ.get(VARIABLE_ENV, "").strip())


def _dsn(nom_base: str) -> str:
    brut = os.environ.get(VARIABLE_ENV, "").strip()
    if not brut:
        raise BaseClientIndisponible(
            f"The clients' Postgres is not configured on this installation ({VARIABLE_ENV})."
        )
    morceaux = urlsplit(brut.replace("postgresql+asyncpg://", "postgresql://", 1))
    return urlunsplit(
        (morceaux.scheme, morceaux.netloc, f"/{nom_base}", morceaux.query, "")
    )


async def connecter(nom_base: str) -> asyncpg.Connection:
    """A connection to ONE client's database. Never shows the address in an error."""
    return await _connecter(verifier_nom(nom_base))


async def _connecter(nom_base: str) -> asyncpg.Connection:
    try:
        return await asyncpg.connect(_dsn(nom_base), timeout=DELAI_CONNEXION_S)
    except (BaseClientIndisponible, NomDeBaseInvalide):
        raise
    except asyncpg.InvalidCatalogNameError:
        raise BaseClientIndisponible(
            f"The database « {nom_base} » does not exist on the clients' Postgres."
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


async def creer_base(nom_base: str) -> list[int]:
    """CREATE DATABASE on the clients' Postgres, then every migration."""
    verifier_nom(nom_base)
    # The server's maintenance database: the only place a CREATE DATABASE can run from.
    maintenance = await _connecter("postgres")
    try:
        existe = await maintenance.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", nom_base
        )
        if not existe:
            # An identifier cannot be a parameter; the name was checked by the pattern above.
            await maintenance.execute(f'CREATE DATABASE "{nom_base}"')
    finally:
        await maintenance.close()
    connexion = await connecter(nom_base)
    try:
        return await appliquer_migrations(connexion)
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
