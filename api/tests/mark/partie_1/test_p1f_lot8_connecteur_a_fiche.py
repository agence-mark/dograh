"""[.mark] Lot 8, 8c-2 (111) : les crochets facultatifs d'un connecteur « à fiche » (commande, réservation, service) sont DÉCLARÉS ensemble, par un ``Protocol``
(``ConnecteurAFiche``, ``connectors/catalogue.py``) : rien n'est déplacé (C1), les champs de ``Connecteur`` restent à plat, mais la liste est écrite une fois, avec son
type. Les trois connecteurs du métier la satisfont ; chaque membre est un champ de ``Connecteur``."""

from __future__ import annotations

import dataclasses
import typing

from api.services.integrations.connectors import catalogue as CAT

CROCHETS = {
    "action_ouverte", "etat_pour_le_modele", "etat_de_l_appel", "dossier_de_la_parole", "objet_en_cours", "valeur_du_manque", "cases_visibles",
    "actions_a_cases", "sans_tiers", "forme_selon_l_etat", "etat_final", "porte_la_fiche", "porte_la_lecture", "issue_de_fin",
}


def test_le_protocol_declare_les_quatorze_crochets_et_chacun_est_un_champ_du_connecteur():
    membres = set(typing.get_protocol_members(CAT.ConnecteurAFiche))
    assert CROCHETS <= membres, CROCHETS - membres
    assert membres - CROCHETS <= {"issues_reservees"}  # 8c-2 (112) : le quinzième est la liste des issues que le connecteur réserve
    assert membres <= {champ.name for champ in dataclasses.fields(CAT.Connecteur)}


def test_commande_reservation_et_service_satisfont_le_protocol():
    for nom in ("commande", "reservation", "service"):
        c = CAT.connecteur(nom)
        assert c is not None and isinstance(c, CAT.ConnecteurAFiche), nom
        assert c.porte_la_fiche == "fiche", nom
