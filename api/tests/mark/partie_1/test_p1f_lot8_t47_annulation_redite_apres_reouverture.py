"""[.mark] Lot 8, T47 (Pierre, 28/11 : option A) : RC3 accepte le fait de l'annulation redit quand la fiche annule une commande ROUVERTE depuis la dernière annulation.

E15 (accord donné, réglé par carte) / « On vide et on annule, pour dix-neuf heures. » → annulée, puis l'heure rouvre la commande (8b-2 : annuler = vider puis recommander) ;
le modèle dit « C'est annulé » (T43 M2) et demande ce qui manque / « On vide et on annule. » → la commande rouverte est annulée de nouveau : le modèle redit « C'est annulé »,
c'est la réponse à une nouvelle demande, pas une redite. Rejoué à midi (« pour dix-neuf heures » est alors acceptée ; à 20 h elle est refusée et la commande reste annulée).
Rien de rouvert, l'annulation redite reste une faute RC3 (la garde ci-dessous)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from api.services.commande import porte as PORTE
from api.tests.mark.partie_1 import combinaisons as C

MIDI = datetime(2026, 11, 13, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))  # vendredi midi : Casa Italia est ouvert, « pour dix-neuf heures » est acceptée


async def _jouer(monde, monkeypatch, suite: tuple[str, ...]) -> C.Resultat:
    with C.horloge.remplacer(monde.base, MIDI):
        return await C.jouer(monde, monkeypatch, "E15", suite)


async def test_l_annulation_redite_apres_la_reouverture_n_est_pas_une_redite(faire_monde, monkeypatch):
    """E15 → G14+G18 · G14 : la seconde annulation porte sur la commande rouverte par l'heure ; le juge n'y voit plus de redite (aucune faute)."""
    monde = await faire_monde("casa-italia")
    r = await _jouer(monde, monkeypatch, ("G14+G18", "G14"))
    assert r.atteint and r.joues == 2, r
    assert not r.fautes, r.fautes


async def test_rien_de_rouvert_rien_n_est_redit(faire_monde, monkeypatch):
    """E15 → G14 · G20 : annulée, puis « c'est tout » ; rien n'est rouvert, l'annulation n'est pas redite (aucune faute)."""
    monde = await faire_monde("casa-italia")
    r = await _jouer(monde, monkeypatch, ("G14", "G20"))
    assert r.atteint and r.joues == 2, r
    assert not r.fautes, r.fautes


def _redit_l_annulation(origine):
    def redite(p, dernier, *a, **k):
        textes = origine(p, dernier, *a, **k)
        if p.get("annulee") and not (textes or {}).get("fait_accompli"):
            return {"suffixe": "", "chiffres_exiges": {}, "fait_accompli": {"fait": "annulee_en_cours"}, "a_faire": PORTE.A_FAIRE_DE_L_ANNULATION_EN_COURS}
        return textes

    return redite


async def test_garde_le_code_qui_redit_l_annulation_sans_reouverture_est_une_faute(faire_monde, monkeypatch):
    """Mutation du code : la commande déjà annulée, toute fiche redit « C'est annulé » ; rien n'a été rouvert : le juge le voit (RC3)."""
    monde = await faire_monde("casa-italia")
    monkeypatch.setattr(PORTE, "textes_du_code", _redit_l_annulation(PORTE.textes_du_code))
    r = await _jouer(monde, monkeypatch, ("G14", "G20"))
    assert r.atteint and r.joues == 2, r
    assert any(pas == "G20" and regle == "RC3" for pas, regle, _ in r.fautes), r.fautes
