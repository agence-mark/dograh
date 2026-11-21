"""Lot 20 (banc final, n9) : la demande transmise au collègue garde les noms dits par l'appelant (« napoli » n'est pas « napolitaine »)."""

from api.services.workflow import passage_unique


def test_la_demande_recopie_les_noms_sans_les_corriger():
    assert "jamais corrigés" in passage_unique.DESCRIPTION_DEMANDE


def test_une_question_sur_un_plat_va_a_la_commande():
    """Lot 20 (n11) : « la Napoli contient des anchois ? » partait au service, qui ne lit pas la carte ; la commande la lit."""
    from api.services.gabarits.installation import _cibles_du_passage

    assert "une question sur un plat de la carte" in _cibles_du_passage()["commande"]


def test_le_service_rend_la_main_pour_la_commande_en_cours():
    """Lot 20 (n6) : « pour ma commande, c'est tout » après une question hors sujet : le service gardait l'appel (« une nouvelle commande » seulement)."""
    from api.services.gabarits.installation import _sorties_du_rendu

    assert "sa commande en cours" in _sorties_du_rendu("service")["rendre_la_main"]
