"""[.mark] The establishments of an organization (chantier l-agent-travaille).

- ``stockage``  where the catalogue is written and read (Dograh's row).
- ``copie``     the in-memory copy the CALL reads (Redis, a few milliseconds, B3).
- ``appel``     which establishment a call serves, and the values it inherits.
"""
