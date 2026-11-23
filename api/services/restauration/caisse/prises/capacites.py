"""[.mark] Module Restauration, lot 3 : la fiche de capacités d'une prise (``fiches-capacites.md``, figée au lot 0).

Une fiche est DÉCLARATIVE : un objet figé dans le code de la prise, que le reste du système lit. Le reste du système ne
lit jamais le nom du fournisseur, seulement cette fiche (« Une seule règle par capacité » : ``adaptation.py``).
Chaque ``non`` d'une fiche a son test (``test_restauration_prises.py``) : le geste correspondant est refusé par la prise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Valeurs fermées de la fiche. Deux écarts au texte du lot 0, notés au compte rendu : ``lu_et_envoye`` (HubRise lit l'état
# de la caisse ET l'écrit : « lu puis envoyé » de la fiche) et ``aucune`` pour les notifications (le portail n'en reçoit pas).
CarteMode = Literal["lue", "envoyee", "non"]
RupturesMode = Literal["lues", "envoyees", "non"]
EtatMode = Literal["lu", "envoye", "lu_et_envoye", "non"]
AntiDoublon = Literal["fournisseur", "chercher_avant_renvoi", "notre_table"]
Notifications = Literal["signees", "interrogation", "aucune"]

# La liste fermée des étapes qu'une prise sait renvoyer : celles du chemin des statuts du contrat § 3, plus ``imprimee``,
# l'étape propre au journal du ticket de l'imprimante (fiche « Imprimante »).
ETAPES = frozenset({"recue", "acceptee", "en_preparation", "prete", "terminee", "refusee", "annulee", "imprimee"})
# Valeur permise de l'étape renvoyée quand la prise ne sait pas dire où en est la commande (contrat § 3).
ETAPE_INCONNUE = "inconnu"

REPRESENTABLE = frozenset(
    {
        "imbrication", "retrait", "formules", "tva_par_mode", "allergenes",
        "horaires_carte", "plusieurs_paiements", "second_telephone",
    }
)


@dataclass(frozen=True)
class Capacites:
    carte: CarteMode  # on la lit, ou elle nous est envoyée
    carte_notifiee: bool  # un message prévient d'un changement
    ruptures: RupturesMode
    ruptures_posees_par_nous: bool
    etat_restaurant: EtatMode  # normal, débordé, pause, reprise (E-49)
    temps_preparation: bool
    horaires: bool
    commande_non_payee: bool
    controle_avant_creation: bool  # aperçu qui calcule (Innovorder)
    annulation: bool
    etapes: frozenset[str]  # sous-ensemble de ``ETAPES``
    anti_doublon: AntiDoublon
    notifications: Notifications
    clients_lus: bool
    remises_lues: bool  # discounts et deals de la carte (T-07)
    represente: frozenset[str]  # sous-ensemble de ``REPRESENTABLE``
    limites: tuple[str, ...]  # en clair
    adresses_permises: tuple[str, ...]  # liste fermée (D4, faille SSRF)

    def __post_init__(self):
        for nom, permises in (
            ("carte", ("lue", "envoyee", "non")),
            ("ruptures", ("lues", "envoyees", "non")),
            ("etat_restaurant", ("lu", "envoye", "lu_et_envoye", "non")),
            ("anti_doublon", ("fournisseur", "chercher_avant_renvoi", "notre_table")),
            ("notifications", ("signees", "interrogation", "aucune")),
        ):
            if getattr(self, nom) not in permises:
                raise ValueError(f"Capacité {nom} hors de la liste fermée : {getattr(self, nom)!r}")
        hors_etapes = set(self.etapes) - ETAPES
        if hors_etapes:
            raise ValueError(f"Étapes hors de la liste fermée : {sorted(hors_etapes)}")
        hors_liste = set(self.represente) - REPRESENTABLE
        if hors_liste:
            raise ValueError(f"Ce que la prise représente, hors de la liste fermée : {sorted(hors_liste)}")
        if self.ruptures_posees_par_nous and self.ruptures == "non":
            raise ValueError("Une prise sans ruptures ne peut pas en poser.")
        object.__setattr__(self, "etapes", frozenset(self.etapes))
        object.__setattr__(self, "represente", frozenset(self.represente))
        object.__setattr__(self, "limites", tuple(self.limites))
        object.__setattr__(self, "adresses_permises", tuple(self.adresses_permises))

    # Lectures commodes : le reste du système les lit, jamais le nom d'une prise.
    @property
    def lit_l_etat(self) -> bool:
        return self.etat_restaurant in ("lu", "lu_et_envoye")

    @property
    def ecrit_l_etat(self) -> bool:
        return self.etat_restaurant in ("envoye", "lu_et_envoye")
