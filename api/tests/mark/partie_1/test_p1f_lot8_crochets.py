"""[.mark] Partie 1, lot 8a (C1, 75) : un module allumé a ses crochets ; le métier s'inscrit au démarrage de chaque processus qui joue des appels.

Comportement égal : rien de ce que la personne entend ne change. Rouge si l'allergie n'est pas branchée, et rouge sans ``inscrire()`` dans l'ouvrier arq.
"""

from __future__ import annotations

import inspect

import pytest

from api.services.commande.moteur import socle
from api.services.modules import crochets
from api.services.modules.registre import MODULES, PAR_CODE, Module, Texte
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as allergie
from api.services.restauration.carte_et_allergenes import voir_un_article

ALLUMEE = {"commande_sur_catalogue": True, "verification_communes": False}  # « verification_communes » : un autre module, éteint
ETEINTE = {"commande_sur_catalogue": False, "verification_communes": False}


@pytest.fixture
def metier_debranche():
    """Le métier débranché le temps du test, rebranché à la sortie (la suite le garde inscrit)."""
    socle.enregistrer_metier()
    try:
        yield
    finally:
        crochets.au_demarrage()


def _branche() -> bool:
    return (
        socle.METIER.prealable is allergie.allergie_sans_reponse
        and socle.METIER.faits_a_donner is allergie.poser_les_faits_de_l_allergie
        and socle.METIER.noter_les_faits_donnes is allergie.noter_les_faits_a_dire
        and socle.METIER.voir_un_article is voir_un_article.voir_produit
    )


def test_un_module_allume_a_ses_crochets():
    """Tout crochet déclaré se résout en une fonction ; ceux de la restauration y sont tous (retirer l'un d'eux rougit ce test)."""
    restauration = PAR_CODE["restauration"]
    for nom in crochets.CROCHETS:
        assert getattr(restauration, nom), f"la restauration doit déclarer son crochet {nom}"
    for module in MODULES:
        for nom in crochets.CROCHETS:
            if chemin := getattr(module, nom):
                fonction = crochets.resoudre(chemin)
                assert callable(fonction), (module.code, nom)
                assert inspect.iscoroutinefunction(fonction) is (nom != "au_demarrage"), (module.code, nom)  # le démarrage est synchrone, les crochets d'appel asynchrones


def test_sans_inscrire_rien_n_est_branche_et_au_demarrage_branche_l_allergie(metier_debranche):
    assert socle.METIER.prealable is None and socle.METIER.faits_a_donner is None and socle.METIER.voir_un_article is None
    crochets.au_demarrage()
    assert _branche()


async def test_le_prealable_du_metier_est_celui_de_l_allergie_une_fois_inscrit(metier_debranche):
    assert await socle.prealable_du_metier(None, {}, None) is None  # sans métier, aucun préalable
    crochets.au_demarrage()
    assert socle.METIER.prealable is allergie.allergie_sans_reponse


async def test_l_ouvrier_arq_inscrit_le_metier_au_demarrage(metier_debranche):
    """Un appel joué par l'ouvrier (série simulée, clôture d'une partie au clavier inactive) a la même allergie que l'API."""
    from api.tasks.arq import WorkerSettings

    assert WorkerSettings.on_startup is not None
    await WorkerSettings.on_startup({})
    assert _branche()


# ---- l'appelant commun : seuls les modules allumés, un crochet qui lève ne coupe rien


@pytest.fixture
def faux_modules(monkeypatch):
    joues: list[str] = []

    def marquer(nom):
        async def crochet(_argument):
            joues.append(nom)

        return crochet

    async def qui_leve(_argument):
        joues.append("leve")
        raise RuntimeError("le crochet tombe : 06 12 34 56 78")

    fonctions = {"a": marquer("a"), "b": marquer("b"), "leve": qui_leve}
    un = Module("un", Texte("one", "un"), "commande_sur_catalogue", au_decroche="leve")
    deux = Module("deux", Texte("two", "deux"), "commande_sur_catalogue", au_decroche="a", fin_de_l_appel="b")
    eteint = Module("trois", Texte("three", "trois"), "verification_communes", au_decroche="b")  # un autre interrupteur, éteint
    monkeypatch.setattr(crochets, "MODULES", (un, deux, eteint))
    monkeypatch.setattr(crochets, "resoudre", lambda chemin: fonctions[chemin])
    return joues


def _decroche(configurations):
    return crochets.Decroche(crochets.CONTEXTE, {}, configurations, 1, 2, 3)


async def test_seuls_les_modules_allumes_jouent_leur_crochet(faux_modules):
    await crochets.au_decroche(_decroche(ALLUMEE))
    assert faux_modules == ["leve", "a"]  # « trois » est éteint : jamais joué


async def test_un_module_eteint_ne_joue_rien(faux_modules):
    await crochets.au_decroche(_decroche(ETEINTE))
    assert faux_modules == []


async def test_un_crochet_qui_leve_ne_coupe_ni_l_appel_ni_les_autres(faux_modules):
    await crochets.au_decroche(_decroche(ALLUMEE))  # ne lève pas : « a » est joué après « leve »
    assert faux_modules == ["leve", "a"]


async def test_sans_configuration_connue_aucun_module_n_est_ecarte(faux_modules):
    """La fin d'un tour au clavier ne connaît pas la configuration de l'agent : tous les modules déclarant le crochet sont joués (comme avant)."""
    await crochets.fin_de_l_appel(crochets.FinDeLAppel(3, None))
    assert faux_modules == ["b"]


async def test_un_echec_est_journalise_sans_la_valeur_de_l_erreur(faux_modules):
    from loguru import logger

    lignes: list[str] = []
    ident = logger.add(lambda m: lignes.append(str(m)), level="ERROR")
    try:
        await crochets.au_decroche(_decroche(ALLUMEE))
    finally:
        logger.remove(ident)
    journal = "".join(lignes)
    assert "failed" in journal and "RuntimeError" in journal
    assert "06 12 34 56 78" not in journal  # jamais un numéro en clair


def test_la_restauration_se_joue_avec_l_interrupteur_de_la_commande():
    assert crochets.est_allume(PAR_CODE["restauration"], ALLUMEE) is True
    assert crochets.est_allume(PAR_CODE["restauration"], ETEINTE) is False
    assert crochets.est_allume(PAR_CODE["restauration"], None) is True
