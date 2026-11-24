"""[.mark] Les moyens de paiement : UNE table, avec la correspondance des vocabulaires (plan final Partie 1, lot 1, n° 85 et 132, L3).

Avant : cinq tables (porte de la commande, état montré au modèle, source de la restauration, couche d'accès, ticket) et deux vocabulaires pour la même
chose : la fiche dit ``carte_bancaire`` et ``carte_bancaire_a_la_livraison``, la base garde ``carte`` et ``carte_livraison``. Rien de ce qui est stocké ne
change : la clé de base reste ``carte_livraison``. Ce module ne dit que la correspondance et les mots ; il ne connaît aucune règle de paiement.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Moyen:
    base: str  # la clé stockée en base
    libelle_dit: str  # ce que l'appelant entend (« en espèces »)
    abrege: str  # le ticket, le numéro court
    libelle_caisse: str | None  # ce que la caisse (HubRise) reçoit ; ``None`` : jamais envoyé sous un nom
    fiche: str | None = None  # la clé de la case ``moyen_de_paiement`` de la fiche ; ``None`` : pas un choix de la fiche
    codes_vus_par_le_modele: tuple[str, ...] = ()  # sous quelles clés l'état montré au modèle les nomme
    libelle_du_modele: str | None = None  # ce que l'état montré au modèle dit à la place de la clé
    reserve_aux_modes: tuple[str, ...] | None = None  # ``None`` : tous les modes
    propose_au_formulaire: bool = True


MOYENS = (
    Moyen("carte", "par carte", "CB", "Carte bancaire", fiche="carte_bancaire", codes_vus_par_le_modele=("carte_bancaire", "carte"), libelle_du_modele="carte"),
    Moyen("especes", "en espèces", "ESP", "Espèces", fiche="especes", codes_vus_par_le_modele=("especes",), libelle_du_modele="espèces"),
    Moyen("titre_restaurant", "en titres-restaurant", "TR", "Titre-restaurant", fiche="titre_restaurant", codes_vus_par_le_modele=("titre_restaurant",),
          libelle_du_modele="titre-restaurant"),
    Moyen("cheque", "par chèque", "CHQ", "Chèque"),
    Moyen("en_ligne", "en ligne", "WEB", None, propose_au_formulaire=False),
    Moyen("carte_livraison", "par carte à la livraison", "CBL", "Carte bancaire à la livraison", fiche="carte_bancaire_a_la_livraison",
          codes_vus_par_le_modele=("carte_bancaire_a_la_livraison",), libelle_du_modele="carte à la livraison", reserve_aux_modes=("livraison",)),
)

CLES_DE_BASE = tuple(m.base for m in MOYENS)
MOYENS_PAR_DEFAUT = ("carte", "especes")  # ce que l'établissement accepte tant qu'il n'a rien réglé

MOYEN_DE_BASE_SELON_LA_FICHE = {m.fiche: m.base for m in MOYENS if m.fiche}
LIBELLES_DITS = {m.base: m.libelle_dit for m in MOYENS}
ABREGES = {m.base: m.abrege for m in MOYENS}
LIBELLES_DE_LA_CAISSE = {m.base: m.libelle_caisse for m in MOYENS if m.libelle_caisse}
RESERVES_AU_MODE = {m.base: m.reserve_aux_modes for m in MOYENS if m.reserve_aux_modes}
LIBELLES_POUR_LE_MODELE = {code: m.libelle_du_modele for m in MOYENS if m.libelle_du_modele for code in m.codes_vus_par_le_modele}
MOYENS_DU_FORMULAIRE = tuple(m.base for m in MOYENS if m.propose_au_formulaire)
