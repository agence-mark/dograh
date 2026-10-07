"""[.mark] The names of the team found in a text (chantier l-agent-collegue, L3, C12, C13).

``reperer(texte, personnes)`` says which people of the team a text names (the summary, the
record), and how sure it is: ``detectee`` or ``a_confirmer``. Our own modules only
(``normaliser``, ``cle_phonetique``, ``cle_sonore`` and ``rapidfuzz``), never the lexicon of
the transcription (decision of 24/09: proper names go through our modules).
"""

from api.services.noms_personnes.reperage import (  # noqa: F401
    PLANCHER_SON,
    SEUIL_ORTHOGRAPHE,
    Reperage,
    reperer,
)
