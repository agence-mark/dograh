"""[.mark] Chantier Partie 1, lot 6 (D51) : le tour borné en cas de panne du fournisseur du cerveau.

Le client OpenAI réessaie seul un refus 429 ou une coupure (deux fois, pauses croissantes), sans rien dire : une passe pouvait durer 6 à 20 s.
Le cerveau a désormais UNE nouvelle tentative au plus et un délai par passe (sur le modèle du greffier, ``greffier.sans_nouvelle_tentative``), posés
par la création du client elle-même (``CerveauBorneMixin`` redéfinit ``create_client``, jamais d'écriture de ``llm._client`` après coup) ;
au-delà, l'erreur suit le chemin existant (relance sans flux puis phrase de repli, ``reponse_avalee``). Une lenteur sous le délai ne déclenche
rien (D13 : les lenteurs ponctuelles du fournisseur sont acceptées). Valeurs écrites au journal avant le test (section ``tour-borne``).
"""

from __future__ import annotations

from functools import lru_cache

NOUVELLES_TENTATIVES_AU_PLUS = 1
DELAI_D_UNE_PASSE_S = 5.0  # une passe mesurée : 0,76 s au clavier, 0,99 s au banc ; 95e centile visé du tour : 1,5 s


def _borne(client):
    return client.with_options(max_retries=NOUVELLES_TENTATIVES_AU_PLUS, timeout=DELAI_D_UNE_PASSE_S)


class CerveauBorneMixin:
    """Le client du cerveau naît borné : une nouvelle tentative au plus, un délai par passe.

    Pipecat crée le client par ``create_client`` (chat completions) ou ``_create_client`` (Responses) ; la fabrique .mark redéfinit les deux ici,
    sans toucher au client déjà posé. Placé AVANT le service dans les bases."""

    def create_client(self, *args, **kwargs):
        return _borne(super().create_client(*args, **kwargs))

    def _create_client(self, *args, **kwargs):
        return _borne(super()._create_client(*args, **kwargs))


@lru_cache(maxsize=None)
def service_borne(classe: type) -> type:
    """La classe du service avec la création du client bornée (une seule sous-classe par classe, jamais deux)."""
    return type(classe.__name__, (CerveauBorneMixin, classe), {"__module__": classe.__module__})
