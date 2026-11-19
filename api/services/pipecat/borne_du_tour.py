"""[.mark] Chantier Partie 1, lot 6 (D51) : le tour borné en cas de panne du fournisseur du cerveau.

Le client OpenAI réessaie seul un refus 429 ou une coupure (deux fois, pauses croissantes), sans rien dire : une passe pouvait durer 6 à 20 s.
Le cerveau a désormais UNE nouvelle tentative au plus et un délai par passe (sur le modèle du greffier, ``greffier.sans_nouvelle_tentative``) ;
au-delà, l'erreur suit le chemin existant (relance sans flux puis phrase de repli, ``reponse_avalee``). Une lenteur sous le délai ne déclenche
rien (D13 : les lenteurs ponctuelles du fournisseur sont acceptées). Valeurs écrites au journal avant le test (section ``tour-borne``).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

NOUVELLES_TENTATIVES_AU_PLUS = 1
DELAI_D_UNE_PASSE_S = 5.0  # une passe mesurée : 0,76 s au clavier, 0,99 s au banc ; 95e centile visé du tour : 1,5 s


def borner_le_cerveau(llm: Any) -> Any:
    """Le cerveau de conversation avec une nouvelle tentative au plus et un délai par passe. ⛔ Ne lève jamais ; rend ``llm``."""
    client = getattr(llm, "_client", None)
    if client is None or not hasattr(client, "with_options"):
        return llm
    try:
        llm._client = client.with_options(max_retries=NOUVELLES_TENTATIVES_AU_PLUS, timeout=DELAI_D_UNE_PASSE_S)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[cerveau] client non borné : {type(erreur).__name__}")
    return llm
