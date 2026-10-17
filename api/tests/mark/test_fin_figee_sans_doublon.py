"""[.mark] Après le banc du 16/10 (C4, scénario 2) : une porte écrite en tête vers un nœud de fin aux
phrases figées tait la suite de la réponse ; le code dit la phrase de fin, jamais deux au revoir.

| Test | Ce qu'il prouve |
|---|---|
| porte en tête vers une fin figée | rien de la réponse n'est dit, la porte part au moteur |
| porte en tête vers une étape ordinaire | la réponse est dite comme avant |
| porte après la phrase | la phrase déjà dite reste dite (rien ne se rattrape), la porte part |
"""

import pytest

from api.tests.mark.test_porte_parlee_processeur import _MontagePortes


class _FinFigee:
    def porte_vers_une_fin_figee(self, nom):
        return nom == "vers_fin"


def _montage():
    montage = _MontagePortes()
    montage.moteur.porte_vers_une_fin_figee = _FinFigee().porte_vers_une_fin_figee
    return montage


@pytest.mark.asyncio
async def test_une_porte_en_tete_vers_une_fin_figee_tait_la_suite():
    montage = _montage()
    ordre = await montage.reponse("→ vers_fin\n", "Je transmets votre demande. Bonne soirée.")
    assert ordre.dit.strip() == ""
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_fin"]


@pytest.mark.asyncio
async def test_une_porte_vers_une_etape_ordinaire_laisse_la_reponse_dite():
    montage = _montage()
    ordre = await montage.reponse("→ vers_panne\n", "Quelle marque ?")
    assert ordre.dit.strip() == "Quelle marque ?"


@pytest.mark.asyncio
async def test_une_porte_apres_la_phrase_ne_tait_rien_de_deja_dit():
    montage = _montage()
    ordre = await montage.reponse("Très bien, bonne soirée.\n", "→ vers_fin\n")
    assert "bonne soirée" in ordre.dit
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_fin"]


@pytest.mark.asyncio
async def test_la_note_du_dernier_tour_est_lue_meme_quand_la_voix_se_tait():
    """Revue du 16/10 : seule la voix se tait ; ce que la réponse note après la porte est écrit."""
    montage = _montage()
    ordre = await montage.reponse("→ vers_fin\nBonne soirée.\n|||\n", '{"motif": "entretien"}')
    assert ordre.dit.strip() == ""
    assert montage.fiche.get("motif") == "entretien"
