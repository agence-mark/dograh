"""Lot 20 (banc final, n9) : la demande transmise au collègue garde les noms dits par l'appelant (« napoli » n'est pas « napolitaine »)."""

from api.services.workflow import passage_unique


def test_la_demande_recopie_les_noms_sans_les_corriger():
    assert "jamais corrigés" in passage_unique.DESCRIPTION_DEMANDE
