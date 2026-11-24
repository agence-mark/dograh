"""Lot 6, reprise B2 : la consigne d'un refus de format dit le bon type de la case (un nombre pour une quantité, du texte pour un nom) et ne parle de
``reponse`` que lorsqu'une question attend. ``ajouter[].quantite`` est obligatoire au contrat (contrats/7.json, ``required`` des éléments d'``ajouter``)."""

from __future__ import annotations

from .aides_de_la_commande import a_emporter, premier_article, question_posee


def _consigne(retour: dict) -> str:
    return str(retour.get("a_faire") or (retour.get("refus") or [{}])[0].get("a_faire") or "")


async def test_ajouter_sans_quantite_est_refuse_avec_le_type_nombre_et_sans_reponse(essai_de):
    e = await essai_de()
    await a_emporter(e)
    assert not question_posee(e)
    retour = await e.tour("une margherita", ajouter=[{"article": "margherita"}])
    consigne = _consigne(retour)
    assert "ajouter[].quantite" in consigne and "en nombre, sans guillemets" in consigne, retour
    assert "en texte" not in consigne and "reponse" not in consigne, consigne
    assert not e.p.get("lignes"), e.p.get("lignes")


async def test_ajouter_sans_article_pendant_une_question_dit_ou_va_la_reponse(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    assert question_posee(e).get("type") == "variante", e.p.get("question")
    retour = await e.tour("normale", ajouter=[{"quantite": 1, "variante": "Normale"}])
    consigne = _consigne(retour)
    assert "ajouter[].article" in consigne and "en texte" in consigne, retour
    assert "reponse" in consigne, consigne


async def test_ajouter_sans_article_sans_question_ne_parle_pas_de_reponse(essai_de):
    e = await essai_de()
    await a_emporter(e)
    assert not question_posee(e)
    retour = await e.tour("une pizza", ajouter=[{"quantite": 1}])
    consigne = _consigne(retour)
    assert "ajouter[].article" in consigne and "en texte" in consigne, retour
    assert "reponse" not in consigne, consigne
