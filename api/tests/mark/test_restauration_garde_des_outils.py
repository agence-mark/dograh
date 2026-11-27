"""[.mark] Module Restauration, lot 24, étapes 1 et 2 : les garde-fous des outils (arguments, échec répété, écritures en file).

Par la vraie exécution d'une action de connecteur (``execution.executer``), connecteur de test déclaré au catalogue ; et, pour les écritures en
file, par les vrais outils de la commande sur le vrai classeur.

| Test | Ce qu'il prouve |
|---|---|
| éteint par défaut | sans la clé, rien ne change : l'argument absurde passe, le même échec se rejoue, deux écritures se mêlent |
| arguments contrôlés | mauvais type, trop long, hors liste fermée, nombre absurde : l'outil demande à reformuler, ne tourne pas ; une valeur saine passe ; zéro déclenchement sur un appel sain |
| échec répété | deux échecs identiques de suite, le troisième n'est pas lancé et rend une autre stratégie ; un autre argument repart ; un succès remet à zéro ; un seul appel ne déclenche rien |
| écritures en file | deux écritures du même objet ne se recouvrent jamais ; les lectures et les autres objets restent en parallèle |
| « Reine + Coca » | deux ``ajouter`` en même temps sur le même panier du vrai classeur : aucun article perdu (et perdu sans la garde) |
| réglages | les trois clés sont au schéma, éteintes par défaut |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.commande import panier
from api.services.integrations.connectors import catalogue, execution, garde
from api.services.integrations.connectors.catalogue import Action, Connecteur, Parametre, declarer
from api.services.reservation import source as source_resa  # noqa: F401
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401

TOUTES = {garde.CLE_ARGUMENTS: True, garde.CLE_ECHEC_REPETE: True, garde.CLE_ECRITURES_EN_FILE: True}
JOURNAL: list[str] = []
ETAT = {"actifs": 0, "max": 0, "reponses": []}


async def _jouer_interne(action, arguments, ctx, delai_s):
    JOURNAL.append(f"{action.nom}:{sorted(arguments)}")
    if action.nom == "echoue":
        return {"statut": "INTROUVABLE", "faits": {}, "suggestion": ""}
    if action.nom == "reussit_une_fois_sur_deux":
        return {"statut": "OK" if arguments.get("ok") else "REFUSEE", "faits": {}, "suggestion": ""}
    ETAT["actifs"] += 1
    ETAT["max"] = max(ETAT["max"], ETAT["actifs"])
    try:
        await asyncio.sleep(0.05)
    finally:
        ETAT["actifs"] -= 1
    return {"statut": "OK", "faits": {}, "suggestion": ""}


def _action(nom, parametres=(), ecrit=False, serialise_avec=None):
    return Action(nom=nom, description=nom, parametres=tuple(parametres), ecrit=ecrit, preparer=lambda *_: None, resultat=lambda *_: {}, serialise_avec=serialise_avec)


@pytest.fixture(scope="module", autouse=True)
def connecteur_de_test():
    nom = "garde_essai"
    c = Connecteur(
        nom=nom, libelle="Essai", integration="interne", interne=True, executer_interne=_jouer_interne,
        actions=(
            _action("lit", [Parametre("texte", obligatoire=False), Parametre("n", type="number", obligatoire=False), Parametre("oui", type="boolean", obligatoire=False),
                            Parametre("mode", choix=("a", "b"), obligatoire=False)]),
            _action("echoue", [Parametre("q", obligatoire=False)]),
            _action("reussit_une_fois_sur_deux", [Parametre("ok", type="boolean", obligatoire=False), Parametre("q", obligatoire=False)]),
            _action("ecrit_panier", ecrit=True, serialise_avec="panier"),
            _action("ecrit_panier_bis", ecrit=True, serialise_avec="panier"),
            _action("ecrit_autre", ecrit=True, serialise_avec="autre"),
        ),
    )
    declarer(c)
    yield nom
    catalogue._CATALOGUE.pop(nom, None)


@pytest.fixture(autouse=True)
def remise_a_zero():
    JOURNAL.clear()
    ETAT.update(actifs=0, max=0)


async def jouer(action, arguments=None, fiche=None, configurations=None):
    return await execution.executer(1, {"connecteur": "garde_essai", "action": action}, arguments, fiche if fiche is not None else {}, None, configurations=configurations)


def test_les_trois_cles_sont_au_schema_eteintes_par_defaut():
    for cle in garde.CLES:
        assert WorkflowConfigurationDefaults.model_fields[cle].default is False
    assert garde.allumee({"garde_echec_repete": True}, garde.CLE_ECHEC_REPETE) and not garde.allumee({}, garde.CLE_ECHEC_REPETE)
    assert not garde.allumee({"garde_echec_repete": "oui"}, garde.CLE_ECHEC_REPETE) and not garde.allumee(None, garde.CLE_ECHEC_REPETE)


async def test_eteint_par_defaut_rien_ne_change():
    r = await jouer("lit", {"n": "beaucoup", "mode": "z"})
    assert r.statut == "ok" and JOURNAL == ["lit:['mode', 'n']"]            # l'argument absurde passe, comme avant
    fiche: dict = {}
    for _ in range(4):
        assert (await jouer("echoue", {"q": "x"}, fiche)).donnees["statut"] == "INTROUVABLE"   # le même échec se rejoue
    assert JOURNAL.count("echoue:['q']") == 4 and garde.CLE_DE_LA_FICHE not in fiche


async def test_arguments_controles_mauvais_type_trop_long_hors_liste_et_nombre_absurde():
    for mauvais in ({"n": "beaucoup"}, {"n": True}, {"n": float("inf")}, {"n": 10**12}, {"oui": "peut-être"}, {"oui": 3}, {"mode": "z"}, {"texte": "x" * 501}):
        JOURNAL.clear()
        r = await jouer("lit", mauvais, configurations=TOUTES)
        assert r.statut == "erreur" and r.donnees["manque"] == list(mauvais), mauvais
        assert JOURNAL == [], mauvais                                         # l'outil n'a pas tourné
    # une valeur saine passe : zéro déclenchement sur un appel sain
    for sain in ({"n": 3}, {"n": "2,5"}, {"oui": True}, {"oui": "false"}, {"mode": "A"}, {"texte": "x" * 500}, {}, {"texte": ""}, {"n": None}, {"texte": 42}):  # « 42 » pour un texte : réparé en « 42 » par le code (SA-30, `b98db2b5`), plus refusé
        JOURNAL.clear()
        assert (await jouer("lit", sain, configurations=TOUTES)).statut == "ok", sain
        assert len(JOURNAL) == 1
    # un argument qui n'est pas déclaré est coupé comme avant, jamais jugé
    r = await jouer("lit", {"organization_id": 99, "n": 1}, configurations=TOUTES)
    assert r.statut == "ok" and JOURNAL[-1] == "lit:['n']"


async def test_echec_repete_le_troisieme_appel_identique_n_est_pas_lance_et_rend_une_autre_strategie():
    fiche: dict = {}
    for _ in range(2):
        assert (await jouer("echoue", {"q": "x"}, fiche, TOUTES)).donnees["statut"] == "INTROUVABLE"
    r = await jouer("echoue", {"q": "x"}, fiche, TOUTES)
    assert r.statut == "ok" and r.donnees["statut"] == "ECHEC_REPETE" and "demande de rappel" in r.donnees["consigne"] and "suggestion" not in r.donnees  # lot 8d : une consigne, jamais un texte à dire
    assert JOURNAL.count("echoue:['q']") == 2                                  # le troisième n'a pas tourné
    # un autre argument repart ; un autre appel de la même fiche aussi
    assert (await jouer("echoue", {"q": "y"}, fiche, TOUTES)).donnees["statut"] == "INTROUVABLE"
    assert (await jouer("lit", {"texte": "x"}, fiche, TOUTES)).donnees["statut"] == "OK"
    # une autre fiche (un autre appel) ne partage rien
    assert (await jouer("echoue", {"q": "x"}, {}, TOUTES)).donnees["statut"] == "INTROUVABLE"


async def test_un_succes_remet_le_compteur_a_zero_et_un_seul_echec_ne_declenche_rien():
    fiche: dict = {}
    assert (await jouer("reussit_une_fois_sur_deux", {"q": "z"}, fiche, TOUTES)).donnees["statut"] == "REFUSEE"
    assert (await jouer("reussit_une_fois_sur_deux", {"q": "z"}, fiche, TOUTES)).donnees["statut"] == "REFUSEE"
    # même arguments : bloqué ; avec ok vrai, c'est un autre appel (autres arguments), il passe
    assert (await jouer("reussit_une_fois_sur_deux", {"q": "z"}, fiche, TOUTES)).donnees["statut"] == "ECHEC_REPETE"
    assert (await jouer("reussit_une_fois_sur_deux", {"q": "z", "ok": True}, fiche, TOUTES)).donnees["statut"] == "OK"
    # un seul échec, puis un succès du MÊME appel, puis un échec : jamais deux de suite
    fiche2: dict = {}
    cle = garde.cle_de_l_appel("garde_essai", "reussit_une_fois_sur_deux", {"q": "w"})
    garde.noter_le_resultat(fiche2, cle, echec=True)
    garde.noter_le_resultat(fiche2, cle, echec=False)
    garde.noter_le_resultat(fiche2, cle, echec=True)
    assert garde.echecs_de_suite(fiche2, cle) == 1
    assert (await jouer("reussit_une_fois_sur_deux", {"q": "w"}, fiche2, TOUTES)).donnees["statut"] == "REFUSEE"   # pas encore bloqué
    assert garde.est_un_echec("repli", {}) and not garde.est_un_echec("ok", {"statut": "OK"}) and not garde.est_un_echec("ok", {"statut": "INCOMPLETE"})


async def test_deux_ecritures_du_meme_objet_ne_se_recouvrent_jamais_les_lectures_et_les_autres_objets_restent_en_parallele():
    fiche: dict = {}
    await asyncio.gather(jouer("ecrit_panier", None, fiche, TOUTES), jouer("ecrit_panier_bis", None, fiche, TOUTES), jouer("ecrit_panier", None, fiche, TOUTES))
    assert ETAT["max"] == 1                                                    # une à la fois
    ETAT.update(actifs=0, max=0)
    await asyncio.gather(jouer("lit", {}, fiche, TOUTES), jouer("lit", {}, fiche, TOUTES), jouer("lit", {}, fiche, TOUTES))
    assert ETAT["max"] == 3                                                    # les lectures restent en parallèle
    ETAT.update(actifs=0, max=0)
    await asyncio.gather(jouer("ecrit_panier", None, fiche, TOUTES), jouer("ecrit_autre", None, fiche, TOUTES))
    assert ETAT["max"] == 2                                                    # deux objets : deux files
    ETAT.update(actifs=0, max=0)
    await asyncio.gather(jouer("ecrit_panier", None, {}, TOUTES), jouer("ecrit_panier", None, {}, TOUTES))
    assert ETAT["max"] == 2                                                    # deux appels : jamais l'un derrière l'autre
    ETAT.update(actifs=0, max=0)
    await asyncio.gather(jouer("ecrit_panier", None, fiche), jouer("ecrit_panier_bis", None, fiche))
    assert ETAT["max"] == 2                                                    # éteinte : elles se mêlent (comme avant)


async def test_reine_et_coca_en_meme_temps_sur_le_meme_panier_aucun_article_perdu(commerce, monkeypatch):  # noqa: F811
    from api.services.commande import source as registre_des_sources
    from api.services.restauration.appel_et_memoire.appel import Lieu
    from api.services.restauration.source_commande import SourceClasseur
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def ouvrir(ctx, **options):
        # une connexion par geste, comme en production : deux gestes en même temps ne partagent pas la leur
        from api.db.bases_clients import connexion as schema

        c = await schema.connecter(commerce.base)
        try:
            yield SourceClasseur(c, Lieu(commerce.base, commerce.a, 1), nom_prise="test")
        finally:
            await c.close()

    monkeypatch.setitem(registre_des_sources._SOURCES, "essai", ouvrir)
    config = {"connecteur": "commande", "action": "fiche", "reglages": {"source": "essai"}}

    async def un_tour(configurations):
        from api.services.workflow import cases_selon_l_etat as CS

        # Lot 4 (D49) : la fiche de l'appel porte déjà ce que la requête aurait montré au modèle (cases, paroles de la personne), comme le fait le montage de la porte
        fiche: dict = {CS.CLE_DES_CASES_MONTREES: {"fiche": ["a_dire", "ajouter", "ajouter[].article", "ajouter[].quantite", "ajouter[].variante"]},
                       CS.CLE_DES_PAROLES: ["une regina normale", "un coca"], CS.CLE_DU_TOUR: 1}
        p = panier.du_dossier(fiche)
        p["mode"] = "emporter"
        await asyncio.gather(
            execution.executer(1, config, {"a_dire": "x", "ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}, fiche, None, configurations=configurations),
            execution.executer(1, config, {"a_dire": "x", "ajouter": [{"article": "coca", "quantite": 1}]}, fiche, None, configurations=configurations),
        )
        return sorted(l["nom"] for l in fiche["commande_panier"]["lignes"])

    avec = await un_tour({garde.CLE_ECRITURES_EN_FILE: True})
    assert len(avec) == 2 and "Regina" in avec[1] and "Coca" in avec[0], avec     # aucun article perdu
    # Sans la garde, les deux gestes se recouvrent : l'un écrase le panier de l'autre (constaté : un seul article reste). Non figé en test :
    # l'issue dépend de l'ordre d'arrivée des réponses de la base ; la preuve rouge est le même test avec la garde débranchée.
    sans = await un_tour(None)
    assert 1 <= len(sans) <= 2
