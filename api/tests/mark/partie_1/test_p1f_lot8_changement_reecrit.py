"""[.mark] Plan final Partie 1, lot 8b-1b (E4 ; décision d'Evan du 24/11, plan § 17 l.404 : plus de changement ni d'annulation en caisse pendant l'appel) : une commande
retenue au « oui » puis changée réécrit SA ligne en base (même numéro, même numéro court, même clé anti-doublon) ; rien ne part ni ne s'annule en caisse pendant l'appel ; à la
fin, la caisse reçoit la dernière version, une fois.

| Test | Ce qu'il prouve |
|---|---|
| changé après le « oui » | une seule ligne pour l'appel, la même, réécrite au tour même ; la caisse ne reçoit rien, n'annule rien ; à la fin, un envoi, la dernière version |
"""

from __future__ import annotations

from api.tests.mark.partie_1 import combinaisons as C


async def _lignes_de_l_appel(partie: C.Partie) -> list[dict]:
    return [dict(r) for r in await partie.e.monde.c.fetch(
        "SELECT numero::text AS numero, numero_court, cle_doublon, statut FROM mark.resto_commande WHERE appel_id = $1", str(partie.e.ctx.run_id))]


async def test_un_changement_apres_le_oui_reecrit_la_meme_ligne_et_la_caisse_recoit_la_derniere_version_a_la_fin(faire_monde, monkeypatch):
    """Client (commande retenue, une margherita) « Encore une margherita normale. » / avant : une nouvelle ligne, l'ancienne annulée et son annulation dite à la caisse /
    après : la même ligne porte deux margheritas, au tour même ; la caisse ne reçoit rien pendant l'appel, puis les deux margheritas une fois à la fin."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    avant = await _lignes_de_l_appel(partie)
    assert len(avant) == 1 and avant[0]["statut"] == "retenue", avant
    o = await partie.geste("G6")
    assert C.lignes_de(o.apres) == {C.MARGHERITA: 2}, dict(C.lignes_de(o.apres))
    apres = await _lignes_de_l_appel(partie)
    assert [(l["numero"], l["numero_court"], l["cle_doublon"], l["statut"]) for l in apres] == [
        (avant[0]["numero"], avant[0]["numero_court"], avant[0]["cle_doublon"], "retenue")], apres
    assert str(o.apres["enregistree"]["numero"]) == avant[0]["numero"], o.apres["enregistree"]
    assert sum(int(l.get("quantite") or 0) for l in (o.base or {}).get("lignes") or []) == 2 and not C.rc_base(o), (o.base, C.rc_base(o))
    assert partie.e.source.prise.recues == [] and partie.e.source.prise.annulees == [], (partie.e.source.prise.recues, partie.e.source.prise.annulees)
    assert await partie.finir_l_appel() == []
    recues = partie.e.source.prise.recues
    assert [str(r["numero"]) for r in recues] == [avant[0]["numero"]] and partie.e.source.prise.annulees == [], recues
    assert sum(int(l.get("quantite") or 0) for l in recues[0].get("lignes") or []) == 2, recues[0].get("lignes")
