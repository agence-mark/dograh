"""[.mark] Plan final Partie 1, lot 8b-1b (T18, Pierre 26/11 ~18 h) : le prénom changé après le « oui » se compare et se réécrit comme l'adresse : la base a le nouveau
prénom au tour même, la caisse le reçoit à la fin de l'appel, une fois. Le même prénom redit (le cas T12 « Léa. ») ne réécrit rien.

| Test | Ce qu'il prouve |
|---|---|
| prénom changé | la base a Lucie au tour même ; la caisse reçoit Lucie à la fin, un envoi |
| même prénom redit (T12) | rien n'est réécrit (aucun fait de changement), la base garde Léa |
"""

from __future__ import annotations

from api.tests.mark.partie_1 import combinaisons as C


def _prenom(commande: dict | None) -> str | None:
    commande = commande or {}
    return (commande.get("client") or {}).get("prenom") or commande.get("prenom")


async def test_un_prenom_change_apres_le_oui_est_reecrit_en_base_et_part_a_la_fin(faire_monde, monkeypatch):
    """Client (commande enregistrée au nom de Léa) « Oui, c'est bon. » … « Ah, c'est au nom de Lucie, pas Léa. » / avant : le ticket garde Léa / après : la base a Lucie au
    tour même, la caisse reçoit Lucie à la fin de l'appel."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    assert _prenom(await _base(partie)) == "Léa"
    o = await partie._executer("P", "ah, c'est au nom de Lucie, pas Léa", {"prenom": "Lucie"}, C._inchange)
    assert o.apres["client"].get("prenom") == "Lucie", o.apres["client"]
    assert _prenom(o.base) == "Lucie", o.base
    assert partie.e.source.prise.recues == []
    assert await partie.finir_l_appel() == []
    recues = partie.e.source.prise.recues
    assert len(recues) == 1 and _prenom(recues[0]) == "Lucie", recues


async def test_le_meme_prenom_redit_ne_reecrit_rien(faire_monde, monkeypatch):
    """Le cas T12 : « Léa. » redit après l'enregistrement : rien ne change, aucun fait de changement (``remplace``), la base garde Léa."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    o = await partie._executer("P", "Léa", {"prenom": "Léa"}, C._inchange)
    operations = [x.get("operation") for x in (o.retour or {}).get("resultats") or []]
    assert "changer_la_commande_enregistree" not in operations, o.retour
    assert _prenom(o.base) == "Léa", o.base


async def _base(partie: C.Partie) -> dict | None:
    base, _ = await partie._lire_la_base()
    return base
