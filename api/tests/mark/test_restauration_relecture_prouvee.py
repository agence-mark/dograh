"""[.mark] Module Restauration, lot 24, étape 4 : le jeton de relecture (« aucune commande enregistrée sans relecture validée »).

Vraie base, carte de référence, prise de test, heure fixée au jeudi 12 h.

| Test | Ce qu'il prouve |
|---|---|
| jeton lié à la version | le « oui » vaut pour CE qui a été relu : un article ajouté, une quantité, un retrait, un choix, une note de ligne ou le mode changés depuis la relecture invalident le jeton ; la relecture est refaite, rien n'est enregistré |
| jeton neuf à chaque relecture | deux relectures donnent deux jetons ; l'enregistrement reçoit celui de la dernière |
| sans jeton | la couche d'accès refuse un jeton vide ou absent : ``INCOMPLETE`` ``relecture``, rien d'écrit |
| le oui du modèle | ``confirmer`` sans relecture préalable relit d'abord (jamais d'enregistrement au premier appel) |
"""

from __future__ import annotations

from api.db.bases_clients.restauration_commande import enregistrer_commande
from api.services.commande import moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import Appel


async def test_un_changement_depuis_la_relecture_invalide_le_jeton_et_rien_n_est_enregistre(commerce):  # noqa: F811
    a = await Appel(commerce, vente_en_plus=False).pret("une regina normale et un coca")
    premiere = await a.jusqu_a_la_relecture()
    jeton = a.p["relecture"]["jeton"]
    assert premiere.manque == "relecture" and jeton
    # chaque sorte de changement : le « oui » ne vaut plus, la relecture est refaite avec un jeton neuf
    changements = [
        lambda: moteur.ajouter(a.source, a.p, a.regles, articles="une margherita normale"),
        lambda: moteur.modifier(a.source, a.p, a.regles, ligne="coca", quantite=2),
        lambda: moteur.retirer(a.source, a.p, a.regles, ligne="coca"),
        lambda: moteur.modifier(a.source, a.p, a.regles, ligne="regina", note="bien cuite"),
        lambda: moteur.choisir_mode(a.source, a.p, a.regles, "sur place"),
    ]
    for geste in changements:
        r = await geste()
        assert r.statut in ("OK", "INCOMPLETE"), r
        assert a.p["relecture"] is None                                       # la relecture faite ne vaut plus
        oui = await a.finaliser(prenom="Alice", moyen="carte", confirmer=True)
        assert oui.manque == "relecture", oui                                 # refaite, pas enregistrée
        assert await a.commandes() == []
        nouveau = a.p["relecture"]["jeton"]
        assert nouveau and nouveau != jeton
        jeton = nouveau
    # la dernière relecture est valide : le « oui » enregistre, avec CE jeton
    fait = await a.finaliser(confirmer=True)
    assert fait.statut in ("ENREGISTREE", "TRANSMISE"), fait
    assert len(await a.commandes()) == 1


async def test_un_oui_au_premier_appel_relit_d_abord_et_deux_relectures_deux_jetons(commerce):  # noqa: F811
    a = await Appel(commerce, vente_en_plus=False).pret("une regina normale")
    d_emblee = await a.finaliser(prenom="Alice", moyen="carte", confirmer=True)
    assert d_emblee.manque == "relecture" and await a.commandes() == []
    premier = a.p["relecture"]["jeton"]
    # le même panier relu une seconde fois sans « oui » : un jeton neuf, et c'est le dernier qui compte
    a.p["relecture"] = None
    await a.finaliser(prenom="Alice", moyen="carte")
    assert a.p["relecture"]["jeton"] != premier
    assert (await a.finaliser(confirmer=True)).statut in ("ENREGISTREE", "TRANSMISE")
    assert len(await a.commandes()) == 1


async def test_la_couche_d_acces_refuse_un_jeton_vide_ou_absent(commerce):  # noqa: F811
    for jeton in (None, "", "   "):
        r = await enregistrer_commande(commerce.c, commerce.a, brouillon(appel_id=f"j-{jeton!r}"), jeton)
        assert (r.statut, r.manque) == ("INCOMPLETE", "relecture")
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0
