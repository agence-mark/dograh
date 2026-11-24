"""Lot 7b-A, second passage (ligne 87) : les trois outils de LECTURE de l'accueil ne passent pas par la table des raisons d'envoi.

« Vous livrez là ? », « c'est prêt pour quand ? », « vous êtes ouverts ? » : le modèle reçoit le vrai fait. Un mode ou une zone qui manque est un ``A_PRECISER``
(le manque dit), un restaurant en pause ou fermé est un fait lu (``ouvert: false`` et sa reprise), jamais un refus ``rien_a_faire`` ni un envoi indisponible.
La table des raisons ne sert qu'à ``envoyer_un_sms``.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.commande import porte
from api.services.restauration.source_commande import SourceClasseur


async def _accueil(essai_de, nom, arguments):
    e = await essai_de("casa-italia")
    return e, await porte.executer(SimpleNamespace(nom=nom), arguments, e.ctx, 5.0)


async def test_l_heure_sans_mode_demande_le_mode(essai_de):
    """« C'est prêt pour quand ? » avant tout mode dit : le manque est le mode, il n'y a ni refus ni « rien à faire »."""
    e, r = await _accueil(essai_de, "heure_annoncee", {})
    assert r["statut"] == "A_PRECISER" and r["manque"] == "mode", r
    assert not e.p["lignes"]


async def test_l_heure_dont_le_calcul_manque_n_est_pas_un_envoi_indisponible(essai_de, monkeypatch):
    """Le module ne sait pas annoncer l'heure : ce n'est pas la raison d'un envoi de message ; le modèle reçoit le fait tel quel."""

    async def annonce(self, *_a, **_k):
        return None

    monkeypatch.setattr(SourceClasseur, "annonce", annonce)
    _, r = await _accueil(essai_de, "heure_annoncee", {"mode_de_retrait": "emporter"})
    assert r.get("raison") not in ("envoi_indisponible", "envoi_impossible", "deja_fait"), r
    assert r["statut"] == "LU" and r["resultats"][0]["statut_du_module"] == "INDISPONIBLE", r


async def test_la_livraison_en_pause_est_lue_comme_fermee(essai_de):
    """« Vous êtes ouverts en livraison ? » pendant une pause : le fait est lu (``ouvert: false``), la pause et sa raison sont dites au modèle."""
    e = await essai_de("casa-italia")
    await e.monde.c.execute("UPDATE mark.site SET etat_force = 'PAUSE', etat_force_jusqu_a = NULL WHERE id = $1", e.monde.a)
    r = await porte.executer(SimpleNamespace(nom="ouverture_en_ce_moment"), {"mode_de_retrait": "livraison"}, e.ctx, 5.0)
    assert r["statut"] == "LU" and "raison" not in r, r
    assert r["resultats"][0]["statut_du_module"] in ("PAUSE_TYPE", "FERME"), r
    assert any(m["ouvert"] is False for m in r["faits"]["modes"]), r
