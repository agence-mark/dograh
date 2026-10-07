"""[.mark] The clients' own databases, one per client (chantier l-agent-travaille, L3).

Not Dograh's database: a Postgres of its own (B5), reached with ``asyncpg`` by its
NAME and the installation's server (``MARK_BASES_CLIENTS_URL``). Every SQL statement
sent to a client's database lives here (the boundary of ``api/db/``).

- ``connexion``    where it is, its versioned schema (``migrations/``), create and upgrade.
- ``referentiel``  the establishments and sentences written and read.
- ``equipe``       the team and the routing.
- ``etat``         its state on screen and its retention policy.
"""
