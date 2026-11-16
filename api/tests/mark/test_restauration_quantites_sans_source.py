"""[.mark] Module Restauration, lot 24 : le contrôle des QUANTITÉS dans « chiffre sans source » (W15), même clé ``garde_chiffre_sans_source``.

| Test | Ce qu'il prouve |
|---|---|
| lecture | « trois pizzas », « 2 desserts » sont des quantités ; « deux minutes », « le 14 novembre », « 20 h 30 », « 12,90 € », « un instant », « un » ne le sont pas |
| quantité sans source | « vous avez trois pizzas » alors qu'aucune source ne donne trois : retenu ; le détail dit la quantité |
| zéro déclenchement | la quantité que la personne a dite, que l'outil a rendue (chiffre, lettres, JSON) ou qui est dans une date de la source : rien n'est retenu |
| rouge | sans le contrôle des quantités, le cas rouge passe |
"""

from __future__ import annotations

import json

from api.services.workflow import chiffres_sans_source as c


def test_lecture_des_quantites_et_ce_qui_n_en_est_pas_une():
    assert c.quantites_dites("Vous avez trois pizzas et 2 desserts.") == {3: "pizzas", 2: "desserts"}
    for pas_une_quantite in (
        "Dans deux minutes", "le 14 novembre", "à 20 h 30", "12,90 €", "un instant", "un café", "vers vingt heures", "pour 5 euros", "samedi 14 novembre",
        "23 degrés", "à 13 euros 41", "dans trois jours",
    ):
        assert c.quantites_dites(pas_une_quantite) == {}, pas_une_quantite
    assert c.quantites_dites(None) == {} and c.quantites_dites(12) == {}


def _sources(*, personne="", outil=None):
    messages = [{"role": "user", "content": personne}] if personne else []
    if outil is not None:
        messages.append({"role": "tool", "content": json.dumps(outil)})
    return c.sources_de(messages)


def test_une_quantite_qu_aucune_source_ne_donne_est_retenue_et_dite_dans_le_detail():
    assert c.chiffres_sans_source("Vous avez trois pizzas.", _sources(personne="Une pizza s'il vous plaît")) == ["3 pizzas"]
    assert c.chiffres_sans_source("Cela fait quatre desserts et cinq boissons.", _sources(outil={"statut": "OK", "faits": {"articles": 4}})) == ["5 boissons"]


def test_zero_declenchement_quand_la_source_donne_la_quantite_ou_une_date():
    assert c.chiffres_sans_source("Vous avez trois pizzas.", _sources(personne="Je voudrais trois pizzas")) == []
    assert c.chiffres_sans_source("Vous avez 3 pizzas.", _sources(personne="trois pizzas")) == []
    assert c.chiffres_sans_source("Vous avez trois pizzas.", _sources(outil={"faits": {"panier": {"articles": 3}}})) == []
    assert c.chiffres_sans_source("Pour quatre personnes.", _sources(personne="une table pour quatre")) == []
    # une réplique de l'agent ne fonde rien
    sources = c.sources_de([{"role": "assistant", "content": "Vous avez trois pizzas."}])
    assert c.chiffres_sans_source("Vous avez trois pizzas.", sources) == ["3 pizzas"]
    # les montants et les heures restent contrôlés comme avant, sans doublon avec les quantités
    assert c.chiffres_sans_source("Cela fait 13 euros 41 à 20 h 30.", _sources()) == ["13 euros 41", "20 h 30"]


def test_rouge_sans_le_controle_des_quantites_le_cas_connu_passe(monkeypatch):
    monkeypatch.setattr(c, "quantites_dites", lambda texte: {})
    assert c.chiffres_sans_source("Vous avez trois pizzas.", _sources()) == []
