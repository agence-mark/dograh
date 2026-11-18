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
"""

import pytest

from api.tests.mark.banc_a.commun import appel_de, faire_monde, base_essai, base_prete, jouer_reel, trace  # noqa: F401

pytestmark = pytest.mark.banc_a


async def test_c5_1_2677_la_commande_de_l_appel_est_retrouvee_apres_l_enregistrement(appel_de):
    a = await appel_de()
    a.greffier(prenom="Paul", numero_dicte="0600000000", mode_de_paiement="carte")
    await a.rejouer(2677, jusqu_au_tour=5)
    assert a.p.get("enregistree"), "précondition : la commande doit être enregistrée\n" + trace(a)
    r = await jouer_reel(a, 2677, 6)  # modifier {ligne: "Salmone Normale", mots: "...je la voulais en mega..."}
    assert "rien" not in (r.get("suggestion") or "").lower() and r["statut"] != "INTROUVABLE", "la commande de l'appel n'est plus retrouvée" + trace(a)


async def test_c6_1_2647_une_commune_sans_rue_ne_suffit_pas_pour_livrer(appel_de):
    a = await appel_de()
    await a.rejouer(2647, jusqu_au_tour=1)
    assert not a.p.get("zone"), "livraison retenue sur « Gouvieux » seul, aucune rue demandée" + trace(a)


async def test_c6_2_2672_la_rue_dite_apres_la_commune_est_reprise(appel_de):
    a = await appel_de()
    await a.rejouer(2672, jusqu_au_tour=3)
    assert "Bouteiller" in (a.p.get("adresse") or ""), "la rue notée par le greffier n'est jamais reprise" + trace(a)


async def test_c6_3_2637_l_adresse_n_emporte_pas_les_mots_autour(appel_de):
    a = await appel_de()
    await a.rejouer(2637, jusqu_au_tour=3)
    assert not (a.p.get("adresse") or "").lower().startswith("c'est"), "adresse enregistrée avec les mots bruts" + trace(a)


async def test_c6_4_2671_la_consigne_dite_avec_l_adresse_n_est_pas_dans_l_adresse(appel_de):
    a = await appel_de()
    await a.rejouer(2671, jusqu_au_tour=1, en_retard=("adresse_livraison", "commune", "consigne_livreur"))
    await jouer_reel(a, 2671, 2, outil="type_de_commande")
    # En production ce tour a rendu INTROUVABLE/commune ; ici la base de communes de test retient Chantilly. Dans les deux cas la consigne ne doit pas
    # rester collée à l'adresse de la commande.
    assert a.p.get("zone") and "sonnez" not in (a.p.get("adresse") or ""), "adresse + consigne dans la phrase : la consigne est enregistrée dans l'adresse" + trace(a)


def _demande_la_consigne(a) -> bool:
    return any(
        j["retour"].get("manque") == "consigne" or "livreur" in (j["retour"].get("suggestion") or "").lower() or "consigne" in (j["retour"].get("suggestion") or "").lower()
        for j in a.journal
    )


@pytest.mark.parametrize("run", [2636, 2638, 2639])
async def test_c7_la_consigne_pour_le_livreur_est_demandee(appel_de, run):
    a = await appel_de()
    a.greffier(numero_dicte="0600000000")
    await a.rejouer(run)
    assert _demande_la_consigne(a), f"run {run} : livraison menée jusqu'au bout sans jamais demander de consigne" + trace(a)


async def test_c7_4_parcours_propre_en_livraison(appel_de):
    a = await appel_de()
    a.greffier(type_de_commande="en livraison", adresse_livraison="12 rue de la République", commune="Senlis")
    await a.jouer("type_de_commande", {"mode": "livraison", "adresse": "12 rue de la République, 60300 Senlis", "mots": "en livraison au 12 rue de la République à Senlis"})
    await a.jouer("ajouter_au_panier", {"articles": "une reine normale", "mots": "une reine normale", "sens": "autre"})
    await a.jouer("valider_la_commande", {"mots": "non c'est tout", "sens": "refus", "en_plus": False})
    await a.jouer("valider_la_commande", {"mots": "oui c'est bon", "sens": "accord"})
    await a.jouer("valider_la_commande", {"mots": "par carte", "moyen": "carte", "sens": "autre"})
    await a.jouer("valider_la_commande", {"mots": "zéro six zéro zéro zéro zéro zéro zéro zéro zéro", "telephone": "0600000000", "sens": "autre"})
    r = await a.jouer("valider_la_commande", {"mots": "Léa", "prenom": "Léa", "sens": "autre"})
    assert _demande_la_consigne(a) or r["statut"] != "ENREGISTREE", "enregistrée en livraison sans que la consigne ait été demandée" + trace(a)
