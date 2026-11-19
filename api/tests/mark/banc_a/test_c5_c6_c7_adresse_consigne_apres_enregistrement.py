"""[.mark] Banc A, familles C5 (commande de l'appel après l'enregistrement), C6 (adresse) et C7 (consigne pour le livreur jamais demandée).

| Test | Run, tour | Ce que le client voulait |
|---|---|---|
| c5_1 | 2677 t6 | « je la voulais en mega » juste après l'enregistrement : la commande de l'appel est retrouvée (jamais « il n'y a encore rien ») |
| c6_1 | 2647 t1 | « à livrer à Gouvieux » sans rue : la rue est demandée, la livraison n'est pas retenue sur la commune seule |
| c6_2 | 2672 t3 | la rue dite après la commune (« au 9 avenue du Bouteiller ») est reprise dans l'adresse de la commande |
| c6_3 | 2637 t3 | « C'est au 12 rue de la République, Senlis » : l'adresse de la commande ne commence pas par « C'est au » |
| c6_4 | 2671 t2 | adresse et consigne dans la même phrase : adresse retenue, consigne notée à part |
| c7_1 à c7_3 | 2636, 2638, 2639 | livraison sans consigne dite : la consigne pour le livreur est demandée une fois avant l'enregistrement |
| c7_4 | construit | même chose sur un parcours propre de bout en bout |

Lot 3 (D48) : rejoué en fiches (``fiches_des_runs.py``) ; l'adresse de la commande est structurée depuis le lot 1 (``voie``, ``commune``).
"""

import json

import pytest

from api.tests.mark.banc_a.commun import appel_de, base_essai, base_prete, faire_monde, jouer_tour, statuts_du_module, trace  # noqa: F401

pytestmark = pytest.mark.banc_a


def _voie(a) -> str:
    return str((a.p.get("adresse") or {}).get("voie") or "")


@pytest.mark.xfail(strict=True, reason=(
    "lot 4 (a-trancher) : au contrat final la proposition naît après le premier article (B12) ; dans le run 2677 elle venait à la fin, et le « Non » "
    "du tour 4 lui répondait : au contrat il tomberait sur le récapitulatif, sens impossible à transcrire. Le sens (E10, la commande de l'appel "
    "changée après l'enregistrement) est prouvé par partie_1/test_l04_cuisine.py::test_commande_de_l_appel_apres_enregistrement"))
async def test_c5_1_2677_la_commande_de_l_appel_est_retrouvee_apres_l_enregistrement(appel_de):
    a = await appel_de()
    await a.rejouer(2677, jusqu_au_tour=5)
    assert a.p.get("enregistree"), "précondition : la commande doit être enregistrée" + trace(a)
    r = await jouer_tour(a, 2677, 6)
    assert r["statut"] != "INTROUVABLE" and "INTROUVABLE" not in statuts_du_module(r), "la commande de l'appel n'est plus retrouvée" + trace(a)


async def test_c6_1_2647_une_commune_sans_rue_ne_suffit_pas_pour_livrer(appel_de):
    a = await appel_de()
    await a.rejouer(2647, jusqu_au_tour=1)
    assert not a.p.get("zone"), "livraison retenue sur « Gouvieux » seul, aucune rue demandée" + trace(a)


async def test_c6_2_2672_la_rue_dite_apres_la_commune_est_reprise(appel_de):
    a = await appel_de()
    await a.rejouer(2672, jusqu_au_tour=3)
    assert "Bouteiller" in _voie(a), "la rue dite n'est jamais reprise" + trace(a)


async def test_c6_3_2637_l_adresse_n_emporte_pas_les_mots_autour(appel_de):
    a = await appel_de()
    await a.rejouer(2637, jusqu_au_tour=3)
    assert _voie(a) and not _voie(a).lower().startswith("c'est"), "adresse enregistrée avec les mots bruts" + trace(a)


async def test_c6_4_2671_la_consigne_dite_avec_l_adresse_n_est_pas_dans_l_adresse(appel_de):
    a = await appel_de()
    await a.rejouer(2671, jusqu_au_tour=1)
    await jouer_tour(a, 2671, 2)
    assert a.p.get("zone") and "sonnez" not in json.dumps(a.p.get("adresse"), ensure_ascii=False), "la consigne est enregistrée dans l'adresse" + trace(a)


def _demande_la_consigne(a) -> bool:
    return any("consigne" in json.dumps(j["retour"], ensure_ascii=False).lower() or "livreur" in json.dumps(j["retour"], ensure_ascii=False).lower()
               for j in a.journal)


@pytest.mark.parametrize("run", [2636, 2638, 2639])
async def test_c7_la_consigne_pour_le_livreur_est_demandee(appel_de, run):
    a = await appel_de()
    await a.rejouer(run)
    assert _demande_la_consigne(a), f"run {run} : livraison menée jusqu'au bout sans jamais demander de consigne" + trace(a)


async def test_c7_4_parcours_propre_en_livraison(appel_de):
    a = await appel_de()
    await a.jouer_la_fiche("en livraison au 12 rue de la République à Senlis", {"mode_de_retrait": "livraison", "adresse": "12 rue de la République", "commune": "Senlis"})
    await a.jouer_la_fiche("une reine normale", {"ajouter": [{"article": "reine", "quantite": 1, "variante": "Normale"}]})
    await a.jouer_la_fiche("non c'est tout", {"c_est_tout": True, "reponse": {"question_id": "?", "sens": "refuse"}})
    await a.jouer_la_fiche("oui c'est bon, par carte", {"reponse": {"question_id": "?", "sens": "accepte"}, "moyen_de_paiement": "carte_bancaire"})
    await a.jouer_la_fiche("zéro six zéro zéro zéro zéro zéro zéro zéro zéro", {"telephone": "0600000000"})
    r = await a.jouer_la_fiche("Léa", {"prenom": "Léa"})
    assert _demande_la_consigne(a) or r["statut"] != "ENREGISTREE", "enregistrée en livraison sans que la consigne ait été demandée" + trace(a)
