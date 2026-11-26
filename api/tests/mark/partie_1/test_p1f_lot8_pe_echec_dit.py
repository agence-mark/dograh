"""[.mark] Lot 8, PE-3 (Q9, point d'étape 7b-C du 26/11) : une commande est dite « enregistrée » tant que son renvoi automatique peut marcher, « pas passée » seulement quand il est abandonné.

Décision : ``bilan-point-d-etape-7b-c.md:277``. ``echec`` est l'abandon : ``envoi_caisse.py`` y passe au dernier essai (``TENTATIVES_MAX``), à l'heure promise proche, ou pour une erreur
de notre code ou un accès retiré ; la reprise (``commandes_a_reprendre``) ne lit que ``nouvelle`` et ``envoyee``. Tant que la commande est ``nouvelle`` ou ``envoyee``, même au dernier
essai avant l'abandon, le modèle reçoit ``enregistree``.
Client « Ma commande, elle en est où ? » / commande ``nouvelle`` au troisième essai : « Elle est bien enregistrée. » / commande ``echec`` : « Elle n'a pas pu passer : je laisse un message ? ».
"""

from __future__ import annotations

from api.services.actions_communes.resultat import Resultat
from api.services.commande import porte
from api.services.commande.moteur.socle import etat_dit

COMMANDE = {"numero_court": "12", "mode": "emporter", "quand_dit": "midi"}


async def _suivi(essai_de, monkeypatch, commande: dict) -> dict:
    e = await essai_de()

    async def retrouver(numero=None, telephone=None):
        return Resultat("OK", {"commandes": [{**COMMANDE, **commande}]})
    monkeypatch.setattr(e.source, "retrouver", retrouver)
    e.dit("ma commande, elle en est où ?")
    return await porte.executer_la_fiche_du_service({"retrouver_une_commande_enregistree": {}, "a_dire": "x"}, e.ctx)


async def test_une_commande_nouvelle_au_troisieme_essai_est_dite_enregistree(essai_de, monkeypatch):
    for statut in ("nouvelle", "envoyee"):
        r = await _suivi(essai_de, monkeypatch, {"statut": statut, "tentatives": 3})
        faits = r["resultats"][0]["faits"]
        assert faits["etat"] == "enregistree" and not r.get("a_faire"), (statut, r)


async def test_une_commande_en_echec_est_dite_pas_passee_avec_l_offre_du_message(essai_de, monkeypatch):
    r = await _suivi(essai_de, monkeypatch, {"statut": "echec", "tentatives": 5})
    assert r["resultats"][0]["faits"]["etat"] == "pas_passee" and r.get("a_faire"), r


def test_la_valeur_fermee_ne_depend_que_du_statut():
    assert [etat_dit(s) for s in ("nouvelle", "envoyee", "echec", "refusee", "annulee")] == ["enregistree", "enregistree", "pas_passee", "pas_passee", "annulee"]
