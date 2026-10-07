"""[.mark] The hub: the common format of the client's database and one translator per
software (chantier l-agent-collegue, L4, H1 to H9).

- H1: the common format IS the schema of the client's database (contact, address, request,
  appointment, resource, person, ``lien_externe``). The agent's actions read and write it.
- H2: a translator is ONE module per software (``connectors/actions/<software>.py``), in three
  parts: the connection (Nango), the correspondence (a declarative table, hub field <->
  software field), the operations (read, search, create, update, each tied to the API).
- H3: ``httpx`` through Nango's relay by default (no key leaves Nango). An official library
  of a software is allowed when it brings real value, pinned (R5), with a token asked from
  Nango at the moment of the call (``nango.jeton_a_la_demande``) and never stored.
- H4: an MCP helps WRITE a translator, never runs during a call.
- H5: read on demand, no mass copy: what a call reads or writes is kept in the hub with its
  ``lien_externe``.

Modules:

- ``traducteurs``  the declaration of a translator, the correspondence, the registry, one
  operation through the relay of THIS organization's connection.
- ``agenda``       the agenda domain in the common format: who is busy when, book an
  appointment. The planner (L5) uses only this; a new calendar software is a new
  translator, the hub does not change.
- ``choix``        which translator an organization uses for each domain (« Integrations »).
"""
