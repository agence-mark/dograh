"""[.mark] C7 B4 (F4) : le suivi d'une commande porte au modèle ce que ses textes de secours disaient.

« Pas juste une suppression » (Evan 25/11 ~10 h) : le texte « Vous en avez plusieurs : la 12 pour dix-neuf heures ou la 14. Laquelle ? » sort du retour (le modèle parle,
8 h 45) ; les candidats (numéro court, heure dite) restent dans les faits du suivi. Le suivi reste ``A_PRECISER`` tant qu'il manque quelque chose, lu sur le manque (plus sur le texte).
"""

from __future__ import annotations

from api.services.actions_communes.resultat import Resultat
from api.services.commande import porte

DEUX = [{"numero_court": "12", "statut": "envoyee", "mode": "emporter", "quand_dit": "midi"},
        {"numero_court": "14", "statut": "envoyee", "mode": "emporter", "quand_dit": "dix-neuf heures"}]


async def _suivi(essai_de, monkeypatch, commandes: list[dict], appel: dict | None = None) -> dict:
    e = await essai_de()
    if appel is not None:
        e.ctx.appel = appel

    async def retrouver(numero=None, telephone=None):
        return Resultat("OK", {"commandes": commandes})
    monkeypatch.setattr(e.source, "retrouver", retrouver)
    e.dit("ma commande, elle en est où ?")
    return await porte.executer_la_fiche_du_service({"retrouver_une_commande_enregistree": {}, "a_dire": "x"}, e.ctx)


async def test_f4_deux_commandes_le_modele_recoit_les_deux_heures(essai_de, monkeypatch):
    """Client « Ma commande, elle en est où ? » (deux commandes du jour) / avant : « Vous en avez plusieurs, laquelle ? » / après : « J'en vois deux, celle de midi et celle de
    ce soir : c'est laquelle ? » : les deux ``quand_dit`` sont dans les faits, le suivi reste à préciser."""
    r = await _suivi(essai_de, monkeypatch, DEUX)
    faits = r["resultats"][0]["faits"]
    assert [c.get("quand_dit") for c in faits.get("candidats") or []] == ["midi", "dix-neuf heures"], r
    assert r["statut"] == "A_PRECISER" and r["manque"] == "reference", r


async def test_f4_voisin_sans_numero_le_suivi_reste_a_preciser(essai_de, monkeypatch):
    """Voisin : numéro masqué, rien à chercher : ``A_PRECISER``, manque ``reference`` (jamais un ``FAIT`` muet), même sans texte de secours."""
    r = await _suivi(essai_de, monkeypatch, DEUX, appel={})
    assert r["statut"] == "A_PRECISER" and r["manque"] == "reference", r


async def test_f4_voisin_une_seule_commande_est_lue_telle_quelle(essai_de, monkeypatch):
    r = await _suivi(essai_de, monkeypatch, DEUX[:1])
    faits = r["resultats"][0]["faits"]
    assert r["statut"] == "FAIT" and faits["quand_dit"] == "midi" and "candidats" not in faits, r
