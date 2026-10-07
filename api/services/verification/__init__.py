"""[.mark] The caller's verification and the reading of his record (chantier l-agent-collegue, L6).

V1: THE CODE DECIDES, NEVER THE MODEL. The agent receives the data of a record only AFTER a
verification the code made; it cannot disclose what it does not hold.

- ``etat``      the verification state of THIS call, kept in Redis under the organization and the
                run (never in the record the model's extraction writes, never a parameter): a
                model that claims « the caller is verified » changes nothing. No answer stored,
                the SMS code only as a salted digest.
- ``comparer``  how a control answer is compared to the record (by our modules, no model).
- ``source``    where a record is read: the client's database (the hub, V4), or the translator
                of the software that holds the records (V3), in the hub's common format.
- ``action``    the two internal actions of the connector ``dossier``: ``verifier_appelant`` and
                ``lire_dossier``.
- ``reglages``  the organization's settings (« Caller verification »).
"""
