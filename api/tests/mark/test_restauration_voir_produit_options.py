"""[.mark] M88 (appel 2574) : l'allergène d'une option de produit, dans ``voir_produit``.

« Il y a des fruits à coque dans le tiramisu pistache ? » rendait ``AMBIGU`` avec UN seul candidat (le Tiramisu) ; et, retenu, le Tiramisu
dont la fiche dit ``gluten, oeufs, lait`` aurait été dit « ne contient pas les fruits à coque » alors que l'option Pistache en contient.

| Test | Ce qu'il prouve |
|---|---|
| tiramisu pistache | un seul candidat + le reste dit = une option : retenu avec l'option, et l'option nommée « Pistache » contient les fruits à coque |
| tiramisu seul | le choix obligatoire compte : « ça dépend », l'option qui en contient est nommée, jamais « ne contient pas » |
| option inconnue | une option sans donnée : « je ne peux pas le garantir », jamais « ne contient pas » |
| option connue | quand la donnée de l'option existe, elle est lue (absent d'après la fiche) |
| reste qui n'est pas une option | le doute reste un doute (``AMBIGU``) : jamais une réponse sur l'article de base |
| nom d'option | lecture au mot entier, « sans » n'est jamais une présence |
"""

from __future__ import annotations

from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.services.restauration.carte_et_allergenes import voir_un_article as VOIR

TIRAMISU = "P-DESSERTS-TIRAMISU"


async def _appel(commerce):
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    # La fiche de démo (composition-demo.json) : la base du tiramisu, sans ses parfums.
    await commerce.c.execute("UPDATE mark.resto_produit SET allergenes = '{gluten,oeufs,lait}' WHERE ref = $1", TIRAMISU)
    return Appel(commerce)


def _vu(appel):

    return lambda produit, signale=None: VOIR.voir_produit(appel.source, appel.p, appel.regles, produit, signale)


async def test_tiramisu_pistache_retenu_avec_l_option_et_contient_les_fruits_a_coque(commerce):
    vu = _vu(await _appel(commerce))
    r = await vu("tiramisu pistache", "fruits à coque")
    assert r.statut == "OK", r
    assert r.faits["signalement"] == "present" and r.faits["code"] == "fruits_a_coque" and r.faits["option"] == "Pistache"
    assert r.suggestion.startswith("Oui") and "Pistache" in r.suggestion
    # la composition aussi : plus de doute sur l'article
    assert (await vu("tiramisu pistache")).statut == "OK"


async def test_tiramisu_sans_option_dit_que_ca_depend_et_nomme_l_option(commerce):
    vu = _vu(await _appel(commerce))
    r = await vu("tiramisu", "fruits à coque")
    assert r.statut == "OK" and r.faits["signalement"] == "selon_option"
    assert r.faits["options_qui_contiennent"] == ["Pistache"]
    assert "Pistache" in r.suggestion and "ne contient pas" not in r.suggestion
    # les autres parfums n'ont aucune donnée : jamais garantis
    assert "garantir" in r.suggestion


async def test_option_sans_donnee_jamais_ne_contient_pas(commerce):
    vu = _vu(await _appel(commerce))
    r = await vu("tiramisu classic", "fruits à coque")
    assert r.statut == "OK" and r.faits["signalement"] == "inconnu" and r.faits["option"] == "Classic"
    assert "ne contient pas" not in r.suggestion and "garantir" in r.suggestion and "équipe" in r.suggestion
    # la liste des signalements, demandée sans en nommer un : la réserve de l'option est dite
    liste = await vu("tiramisu classic", "des allergies")
    assert liste.faits["signalement"] == "liste" and "garantir" in liste.suggestion


async def test_option_dont_la_donnee_existe_est_lue(commerce):
    appel = await _appel(commerce)
    lire = appel.source.article

    async def article_avec_donnee(ref, mode):
        fiche = await lire(ref, mode)
        for g in fiche["groupes"]:
            for o in g["options"]:
                o["signalements"] = [] if o["nom"] == "Classic" else o["signalements"]
        return fiche

    appel.source.article = article_avec_donnee
    vu = _vu(appel)
    r = await vu("tiramisu classic", "fruits à coque")
    assert r.faits["signalement"] == "absent_de_la_fiche" and r.suggestion.startswith("D'après la fiche")


async def test_un_reste_qui_n_est_pas_une_option_reste_un_doute(commerce):
    vu = _vu(await _appel(commerce))
    assert (await vu("tiramisu zzzz", "fruits à coque")).statut == "AMBIGU"


def test_le_nom_d_une_option_au_mot_entier_et_sans_jamais_une_presence():
    from api.services.restauration.signalements import codes_nommes

    assert codes_nommes("Pistache") == ["fruits_a_coque"]
    assert codes_nommes("Double cheese") == []  # « ble » n'est pas le blé
    assert codes_nommes("Pâte sans gluten") == []
    assert codes_nommes("Supplément œuf") == ["oeufs"]
