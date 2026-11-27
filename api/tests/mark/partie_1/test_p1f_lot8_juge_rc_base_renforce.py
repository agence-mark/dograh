"""[.mark] Plan final Partie 1, lot 8b-2 (T15, registre ; audit 7c) : le juge ``rc_base`` des combinaisons est RENFORCÉ, jamais assoupli. Il aurait vu T13 (l'adresse changée
après le « oui » qui n'arrive pas en base) et R1 de 7c / T16 (la ligne en attente qu'un refus ramène). Preuve par mutation : le défaut remis dans le code, le juge rougit.

| Cas du juge | Test |
|---|---|
| (a) après un refus de changement, le panier est la base, sauf une ligne en attente qu'aucune fiche refusée n'a complétée (option C) | l'ancien ``remettre`` remis : la ligne que la fiche refusée complétait revient en attente, le juge rougit |
| (b) tant qu'une ligne attend, la base ne bouge pas | une base qui change pendant l'attente : le juge rougit (observation construite) |
| (c) adresse, note et consigne au livreur comparées panier / base | le défaut de T13 remis (``commande_changee`` ne lit que l'empreinte) : le juge rougit |
| (d) « caisse qui ne sait pas annuler » | SANS OBJET : plus de statut de caisse pendant l'appel (§ 17 l.404, plan final Partie 1 ``2026-11-23-plan-final-partie-1.md:404``) ; rien à juger |
"""

from __future__ import annotations

import copy

from api.services.commande import panier as P
from api.tests.mark.partie_1 import combinaisons as C

ADRESSE_1 = {"adresse": "12 rue de la République", "commune": "Senlis"}
ADRESSE_2 = {"adresse": "3 rue de Paris", "commune": "Senlis"}


def _chiffrage_refuse(monkeypatch):
    from api.services.commande.moteur import changement
    from api.services.commande.resultat import Resultat

    async def refuse(*_a, **_k):
        return Resultat("INTERDIT", {"raison": "rupture"}, "")

    monkeypatch.setattr(changement, "chiffrer_le_panier", refuse)


async def _normale(partie: C.Partie) -> C.Observation:
    q = C.question(partie.p)
    return await partie._executer("GX", "normale", {"reponse": {"question_id": q.get("id"), "sens": "autre", "valeurs": ["Normale"]}}, C._inchange)


def _l_ancien_remettre(monkeypatch) -> None:
    """Le défaut de T16 (7c R1) : après un refus, le panier du début de la fiche revient entier, la ligne en attente que la fiche refusée complétait comprise."""
    monkeypatch.setattr(P, "revenir_apres_un_refus", lambda p, avant: (P.remplacer_par(p, avant), [])[1])


def _le_defaut_de_t13(monkeypatch) -> None:
    """Le défaut de T13 (7c R2) : seule l'empreinte dit qu'une commande enregistrée a changé ; l'adresse, la note et la consigne ne sont pas réécrites en base."""
    monkeypatch.setattr(P, "commande_changee", lambda p: P.empreinte(p) != p.get("empreinte_enregistree"))


async def _livree_au_12(faire_monde, monkeypatch) -> C.Partie:
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    await partie._executer("L", "finalement en livraison au 12 rue de la République à Senlis", {"mode_de_retrait": "livraison", **ADRESSE_1}, C._inchange)
    return partie


# --------------------------------------------------------------------------- (c) l'adresse, la note, la consigne

async def test_c_le_juge_voit_une_adresse_qui_n_arrive_pas_en_base(faire_monde, monkeypatch):
    partie = await _livree_au_12(faire_monde, monkeypatch)
    o = await partie._executer("A", "non, c'est au 3 rue de Paris à Senlis", ADRESSE_2, C._inchange)
    assert C.rc_base(o) == [], C.rc_base(o)  # le code d'aujourd'hui réécrit la base : le juge ne dit rien
    partie = await _livree_au_12(faire_monde, monkeypatch)
    _le_defaut_de_t13(monkeypatch)
    o = await partie._executer("A", "non, c'est au 3 rue de Paris à Senlis", ADRESSE_2, C._inchange)
    fautes = C.rc_base(o)
    assert any("adresse" in d for _, d in fautes), (fautes, o.base and o.base.get("adresse"), o.apres.get("adresse"))


async def test_c_le_juge_voit_une_note_et_une_consigne_qui_n_arrivent_pas_en_base(faire_monde, monkeypatch):
    partie = await _livree_au_12(faire_monde, monkeypatch)
    _le_defaut_de_t13(monkeypatch)
    o = await partie._executer("N", "bien cuite s'il vous plaît", {"note_generale": "bien cuite"}, C._inchange)
    assert any("note" in d for _, d in C.rc_base(o)), (C.rc_base(o), o.base and o.base.get("note"))
    o = await partie._executer("CL", "sonnez deux fois", {"consigne_livreur": "sonnez deux fois"}, C._inchange)
    assert any("consigne" in d for _, d in C.rc_base(o)), (C.rc_base(o), o.base and o.base.get("consigne_livreur"))


# --------------------------------------------------------------------------- (a) après un refus

async def test_a_le_juge_voit_la_ligne_en_attente_que_la_fiche_refusee_completait(faire_monde, monkeypatch):
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    await partie.geste("G2")
    _chiffrage_refuse(monkeypatch)
    o = await _normale(partie)
    assert C.rc_base(o) == [], C.rc_base(o)  # option C : la ligne sort, le panier est la base
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    await partie.geste("G2")
    _l_ancien_remettre(monkeypatch)
    o = await _normale(partie)
    assert P.a_completer(o.apres), "la mutation doit faire revenir la ligne en attente"
    assert any("refus" in d for _, d in C.rc_base(o)), C.rc_base(o)


async def test_a_un_refus_qui_ne_touche_pas_la_ligne_en_attente_la_laisse_sans_faute_du_juge(faire_monde, monkeypatch):
    """Le voisin : la ligne en attente qu'aucune fiche refusée n'a complétée reste, le juge ne dit rien."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    await partie.geste("G2")
    o = await partie._executer("G15", "finalement en livraison", {"mode_de_retrait": "livraison"}, C._inchange)
    assert P.a_completer(o.apres) and C.rc_base(o) == [], C.rc_base(o)


# --------------------------------------------------------------------------- (b) la base ne bouge pas tant qu'une ligne attend

async def test_b_le_juge_voit_une_base_qui_bouge_pendant_qu_une_ligne_attend(faire_monde, monkeypatch):
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    o = await partie.geste("G2")
    assert P.a_completer(o.apres) and o.base_avant is not None and C.rc_base(o) == [], C.rc_base(o)
    bougee = copy.deepcopy(o.base)
    bougee["total"] = int(bougee["total"]) + 100
    o.base = bougee
    assert any("attend" in d for _, d in C.rc_base(o)), C.rc_base(o)
