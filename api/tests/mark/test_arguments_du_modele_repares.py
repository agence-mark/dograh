"""[.mark] Le code répare les erreurs fréquentes du modèle au lieu de les refuser (vu en production, appel 2554 : Gemma 4 envoie
``{"articles": ["une Regina"], "choix": "normale"}``, l'article n'était jamais pris).

| Test | Ce qu'il prouve |
|---|---|
| liste de textes | un paramètre texte reçu en liste est joint par « , » |
| nombre en texte | un nombre dit en texte est converti, un texte qui n'en est pas un est rendu tel quel |
| booléen en texte | « true » / « oui » deviennent vrais |
| non déclaré | un paramètre non déclaré est toujours retiré |
| de bout en bout | l'outil de commande prend l'article quand ``articles`` arrive en liste |
"""

from __future__ import annotations

from api.services.integrations.connectors.catalogue import Action, Parametre
from api.services.integrations.connectors.execution import arguments_permis
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401


def _action() -> Action:
    return Action(
        nom="x", description="", parametres=(Parametre("texte"), Parametre("n", type="number"), Parametre("b", type="boolean", obligatoire=False)),
        ecrit=False, preparer=lambda *a: None, resultat=lambda *a: None,
    )


def test_un_texte_recu_en_liste_est_joint():
    assert arguments_permis(_action(), {"texte": ["une Regina", "un coca"], "n": 1})["texte"] == "une Regina, un coca"
    assert arguments_permis(_action(), {"texte": ["une Regina"], "n": 1})["texte"] == "une Regina"
    assert "texte" not in arguments_permis(_action(), {"texte": [], "n": 1})


def test_un_nombre_en_texte_est_converti_sinon_rendu_tel_quel():
    assert arguments_permis(_action(), {"texte": "a", "n": "2"})["n"] == 2
    assert arguments_permis(_action(), {"texte": "a", "n": "2,5"})["n"] == 2.5
    assert arguments_permis(_action(), {"texte": "a", "n": "deux"})["n"] == "deux"
    assert arguments_permis(_action(), {"texte": 12, "n": 1})["texte"] == "12"


def test_un_booleen_en_texte_est_converti_et_le_non_declare_retire():
    r = arguments_permis(_action(), {"texte": "a", "n": 1, "b": "oui", "intrus": "x"})
    assert r["b"] is True and "intrus" not in r




