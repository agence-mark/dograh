"""[.mark] Module Restauration, lot 26, M34 : le contrôle « chiffres sans source » lit aussi les nombres en lettres que le code dit (``mots_dits``).

| Test | Ce qu'il prouve |
|---|---|
| aller-retour montants | tout montant de 1 centime à 999 euros que ``montant_en_lettres`` écrit est relu au centime près (« un centime », « cinquante centimes », « vingt et un euros neuf ») |
| aller-retour heures | toute heure que ``heure_en_lettres`` écrit (2 h à 23 h 59, une minute isolée comprise) est relue ; « minuit » ; « entre vingt heures et vingt heures trente » |
| quantités | « deux pizzas », « trois Calzone et deux tiramisus » sont lues (le lecteur de nombres laissait « deux » isolé) ; « une pizza » ne se contrôle pas |
| sources | un nombre en lettres donné par un résultat d'outil ou la personne couvre la réplique ; un autre est retenu |
"""

from __future__ import annotations

from api.services.mots_dits import heure_en_lettres, montant_en_lettres, nom_dit
from api.services.workflow import chiffres_sans_source as c


def test_tout_montant_dit_en_lettres_est_relu_au_centime_pres():
    faux = [x for x in range(1, 100000) if c.montants_dits(montant_en_lettres(x)) != {x}]
    assert faux == [], [(x, montant_en_lettres(x)) for x in faux[:5]]
    assert c.montants_dits("cinquante centimes") == {50} and c.montants_dits("un centime") == {1}
    assert c.montants_dits("Cela fait vingt-cinq euros, à vingt heures quinze.") == {2500}


def test_toute_heure_dite_en_lettres_est_relue_et_minuit_aussi():
    faux = [(h, m) for h in range(2, 24) for m in range(60) if (h, m) not in c.heures_dites("pour " + heure_en_lettres(h, m))]
    assert faux == [], faux[:5]
    assert c.heures_dites("prête à minuit") == {(0, 0)}
    assert c.heures_dites("entre vingt heures et vingt heures trente") == {(20, 0), (20, 30)}
    assert c.heures_dites("à vingt-deux heures cinq") == {(22, 5)}
    assert c.heures_dites("Vous avez deux pizzas à vingt heures cinq pizzas") == {(20, 0)}  # « cinq pizzas » est une quantité, pas une minute


def test_les_quantites_en_lettres_sont_lues_et_une_seule_ne_se_controle_pas():
    assert c.quantites_dites("Vous avez deux pizzas.") == {2: "pizzas"}
    assert c.quantites_dites("Il y en a trois Calzone et deux tiramisus") == {3: "Calzone", 2: "tiramisus"}
    assert c.quantites_dites(nom_dit("Pizza", 2, genre="f", commun=True)) == {2: "pizzas"}
    assert c.quantites_dites("une pizza") == {}
    assert c.quantites_dites("deux minutes") == {} and c.quantites_dites("dans deux heures") == {}  # une durée n'est pas une quantité


def test_un_nombre_en_lettres_donne_par_une_source_couvre_la_replique_un_autre_est_retenu():
    messages = [
        {"role": "user", "content": "Je voudrais deux pizzas pour vingt heures trente"},
        {"role": "tool", "content": '{"statut": "OK", "faits": {"total": 2500}}'},
    ]
    s = c.sources_de(messages)
    assert c.chiffres_sans_source("Donc deux pizzas, vingt-cinq euros, à vingt heures trente.", s) == []
    assert c.chiffres_sans_source("Donc trois pizzas, vingt-six euros, à vingt et une heures.", s) == ["26 euros", "21 h", "3 pizzas"]
