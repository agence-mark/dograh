"""[.mark] Plan final Partie 1, lot 8b-1b (E6, n° 93, A8 ; Pierre 27/11 ~4 h, registre T24 (2)) : pendant l'appel, annuler la commande retenue ne lit ni ne touche la caisse.
La ligne passe à « annulee » en base au tour même (le filet ne peut jamais l'envoyer) ; aucune annulation n'est dite à la caisse, maintenant ou plus tard (rien « à dire ») ;
la confirmation en deux temps (DC4) est toujours posée, que la caisse sache annuler ou non.

| Test | Ce qu'il prouve |
|---|---|
| annulée après le « oui » | DC4 posée puis « oui » : annulée en base, rien dit ni gardé « à dire » pour la caisse ; à la fin de l'appel, rien ne part |
| caisse qui ne sait pas annuler (A8) | DC4 posée quand même, « oui » : annulée (avant : refus « annulation impossible » ou « déjà en préparation », faux) |
"""

from __future__ import annotations

import pytest

from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.partie_1 import combinaisons as C


async def _annuler(partie: C.Partie) -> C.Observation:
    o = await partie._executer("A", "finalement j'annule", {"annuler_une_commande_enregistree": True}, C._inchange)
    q = C.question(o.apres)
    assert q.get("type") == "annulation_enregistree", (q, o.retour)  # DC4, premier temps : la question est posée, rien n'est annulé
    return await partie._executer("O", "oui", {"reponse": {"question_id": q.get("id"), "sens": "accepte"}}, C._inchange)


@pytest.mark.parametrize("caisse_sait_annuler", [True, False], ids=["caisse_qui_annule", "caisse_sans_annulation_A8"])
async def test_annulee_apres_le_oui_rien_n_est_dit_a_la_caisse_et_rien_ne_part_a_la_fin(faire_monde, monkeypatch, caisse_sait_annuler):
    """Client (commande retenue) « Finalement j'annule. » / modèle « Vous voulez vraiment annuler la commande de … ? » / « Oui. » / avant : l'annulation d'une commande
    que la caisse n'a jamais reçue lui est dite (ou gardée « à dire »), et une caisse qui ne sait pas annuler fait refuser (« déjà en préparation ») / après : « C'est annulé. »,
    la ligne est annulée en base, la caisse n'entend parler de rien."""
    if not caisse_sait_annuler:
        monkeypatch.setattr(SourceClasseur, "permet_l_annulation", lambda self: False, raising=False)
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    numero = str(partie.p["enregistree"]["numero"])
    o = await _annuler(partie)
    assert o.apres.get("annulee") and not o.apres.get("enregistree"), o.retour
    c, a = partie.e.monde.c, partie.e.monde.a
    ligne = await c.fetchrow("SELECT statut, annulation_a_dire_le FROM mark.resto_commande WHERE numero::text = $1", numero)
    assert ligne["statut"] == "annulee" and ligne["annulation_a_dire_le"] is None, dict(ligne)
    assert partie.e.source.prise.annulees == [] and partie.e.source.prise.recues == [], (partie.e.source.prise.annulees, partie.e.source.prise.recues)
    assert await partie.finir_l_appel() == []
    assert partie.e.source.prise.recues == [] and partie.e.source.prise.annulees == []
    assert await c.fetchval("SELECT count(*) FROM mark.resto_commande WHERE site_id = $1 AND annulation_a_dire_le IS NOT NULL", a) == 0
