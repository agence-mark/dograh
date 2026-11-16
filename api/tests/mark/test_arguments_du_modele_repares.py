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


async def test_l_outil_de_commande_prend_l_article_recu_en_liste(appel_de_test):
    jouer = appel_de_test.jouer
    r = await jouer("choisir_mode", mode="à emporter", articles=["une regina normale"])
    assert r["statut"] == "OK", r
    ajout = await jouer("ajouter", articles=["un coca"])
    assert ajout["statut"] == "OK" and ajout["faits"]["panier"]["articles"] >= 1, ajout


async def test_avec_la_garde_des_arguments_allumee_une_liste_n_est_plus_refusee(appel_de_test):
    """Le cas de production : avec ``garde_arguments_controles``, la liste de Gemma rendait ``missing`` et l'article n'était jamais pris."""
    from api.services.integrations.connectors import garde

    appel_de_test.moteur.configurations_des_modules = {garde.CLE_ARGUMENTS: True}
    r = await appel_de_test.jouer("choisir_mode", mode="à emporter", articles=["une regina normale"])
    assert r.get("status") != "missing" and r["statut"] == "OK", r
    assert [l["nom"] for l in appel_de_test.fiche["commande_panier"]["lignes"]] == ["Regina Normale"]
