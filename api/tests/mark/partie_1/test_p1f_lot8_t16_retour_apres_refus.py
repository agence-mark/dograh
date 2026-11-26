"""[.mark] Plan final Partie 1, lot 8b-1b (T16, R1 de l'audit 7c, option C ; règle A2 de Pierre « tout ou rien ») : un changement refusé d'une commande enregistrée.
Quand la fiche refusée COMPLÉTAIT une ligne en attente (sa taille), cette ligne sort, et ce qui l'accompagnait sans être écrit en base sort aussi : le panier redevient la
commande enregistrée ; le modèle reçoit les noms retirés (``lignes_en_attente_retirees``). Une fiche refusée qui ne touchait pas la ligne en attente la laisse, et sa question
reste. Tests de ``1aad7a51`` (``test_p1f_lot7c_longues.py``), le cas « caisse qui ne sait pas annuler » retiré (§ 17 l.404) ; le second par un chiffrage refusé.
"""

from __future__ import annotations

from api.services.commande import panier as P
from api.tests.mark.partie_1 import combinaisons as C


def _chiffrage_refuse(monkeypatch):
    from api.services.commande.moteur import changement
    from api.services.commande.resultat import Resultat

    vrai = changement.chiffrer_le_panier

    async def refuse(*_a, **_k):
        return Resultat("INTERDIT", {"raison": "rupture"}, "")

    monkeypatch.setattr(changement, "chiffrer_le_panier", refuse)
    return lambda: monkeypatch.setattr(changement, "chiffrer_le_panier", vrai)


async def _normale(partie: C.Partie) -> C.Observation:
    q = C.question(partie.p)
    return await partie._executer("GX", "normale", {"reponse": {"question_id": q.get("id"), "sens": "autre", "valeurs": ["Normale"]}}, C._inchange)


def _faits_du_changement(o: C.Observation) -> dict:
    ops = {x.get("operation"): x for x in (o.retour or {}).get("resultats") or []}
    return (ops.get("changer_la_commande_enregistree") or {}).get("faits") or {}


async def test_un_changement_refuse_revient_a_la_commande_enregistree_sans_la_ligne_qu_il_completait(faire_monde, monkeypatch):
    """Client (commande enregistrée, une margherita) « Une regina. » / « Normale. » (refusé : le chiffrage) / avant : la regina revient en attente, la taille est redemandée sans
    fin, une margherita suivante ne part jamais / après : « Je ne peux pas l'ajouter ; la regina est retirée, vous voulez autre chose ? » (le modèle, d'après les faits) ; le
    panier redevient la commande enregistrée ; « Encore une margherita normale. » part en base."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    enregistre = C.lignes_de(partie.p)
    await partie.geste("G2")
    remettre = _chiffrage_refuse(monkeypatch)
    o = await _normale(partie)
    assert C.lignes_de(o.apres) == enregistre and not P.a_completer(o.apres), dict(C.lignes_de(o.apres))
    assert C.question(o.apres).get("type") != "variante" and not C.rc9(o), C.question(o.apres)
    assert _faits_du_changement(o).get("lignes_en_attente_retirees") == ["Regina"], _faits_du_changement(o)
    remettre()
    o = await partie.geste("G6")
    assert C.lignes_de(o.apres) == {C.MARGHERITA: 2} and not P.a_completer(o.apres), dict(C.lignes_de(o.apres))
    assert sum(int(l.get("quantite") or 0) for l in (o.base or {}).get("lignes") or []) == 2 and not C.rc_base(o), (o.base, C.rc_base(o))


async def test_un_changement_refuse_revient_a_la_commande_enregistree_meme_quand_la_ligne_en_attente_accompagnait_un_retrait(faire_monde, monkeypatch):
    """L'autre chemin : la fiche qui ajoute une ligne sans sa taille garde aussi ce qu'elle change d'autre (le retrait de la margherita) sans l'écrire en base ; un refus au tour
    suivant qui complète la ligne ramène TOUT à la commande enregistrée (tout ou rien). Client (commande enregistrée, une margherita) « Une regina, et enlevez la première. » /
    « Normale. » (refusé : le chiffrage) / avant : panier sans margherita, la regina en attente / après : le panier redevient la commande enregistrée, la margherita."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    enregistre = C.lignes_de(partie.p)
    o = await partie.fusion(("G2", "G7"))
    assert C.lignes_de(o.apres) == {C.REGINA: 1} and P.a_completer(o.apres), dict(C.lignes_de(o.apres))
    _chiffrage_refuse(monkeypatch)
    o = await _normale(partie)
    assert C.lignes_de(o.apres) == enregistre and not P.a_completer(o.apres), dict(C.lignes_de(o.apres))
    assert sum(int(l.get("quantite") or 0) for l in (o.base or {}).get("lignes") or []) == 1 and not C.rc_base(o), (o.base, C.rc_base(o))


async def test_un_refus_qui_ne_complete_pas_la_ligne_en_attente_la_laisse_et_sa_question_reste(faire_monde, monkeypatch):
    """Le voisin (refus 9) : Client (commande enregistrée, une margherita) « Une regina. » / « Finalement en livraison. » (sans adresse : refusé, l'adresse manque) / la regina
    n'était pas complétée par cette fiche : elle reste en attente, sa taille se redemande ; la base garde la commande enregistrée."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    await partie.geste("G2")
    o = await partie._executer("G15", "finalement en livraison", {"mode_de_retrait": "livraison"}, C._inchange)
    assert C.lignes_de(o.apres).get(C.REGINA) == 1 and P.a_completer(o.apres), dict(C.lignes_de(o.apres))
    assert o.apres.get("mode") == "emporter" and C.question(o.apres).get("type") == "variante", (o.apres.get("mode"), C.question(o.apres))
    assert sum(int(l.get("quantite") or 0) for l in (o.base or {}).get("lignes") or []) == 1 and (o.base or {}).get("mode") == "emporter", o.base
