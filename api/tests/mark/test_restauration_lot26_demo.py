"""[.mark] Module Restauration, lot 26 (SA-15) : la qualité de l'agent de démo (manques M25 à M31 trouvés en construisant Casa Italia, lot 17).

| Test | Manque | Ce qu'il prouve |
|---|---|---|
| voir sous le minimum | M27 | ``voir_commande`` sous le minimum de la zone rend les lignes ET ce qui manque, jamais un refus |
| commune hors zone | M28 | une commune réelle hors de toute zone rend ``HORS_ZONE`` avec les communes livrées, pas « dans quelle commune ? » |
| nom de rue | M28 | un nom de rue qui est aussi une commune n'est jamais pris pour la commune de livraison |
| commune ambiguë | M28 | un nom porté par plusieurs communes reste à confirmer |
"""

from __future__ import annotations

import pytest

from api.db.bases_clients.restauration_zone import verifier_adresse
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_lot17_minimum import en_livraison_proches  # noqa: F401
from api.tests.mark.test_restauration_zones import _regler


async def test_voir_la_commande_sous_le_minimum_rend_les_lignes_et_ce_qui_manque(en_livraison_proches):
    a = en_livraison_proches
    assert (await a.ajouter(articles="une regina normale")).statut == "OK"  # 12,90 € < 15 €
    r = await a.voir()
    assert r.statut == "OK", r
    assert [(l["nom"], l["quantite"], l["prix_unitaire"]) for l in r.faits["lignes"]] == [("Regina Normale", 1, 1290)]
    assert r.faits["minimum_non_atteint"] == {"minimum": 1500, "manque": 210}
    assert r.faits["total"] is None
    assert "il manque deux euros dix" in r.suggestion and "quinze euros" in r.suggestion
    await a.ajouter(articles="un coca")  # 14,90 € : encore 10 centimes
    r = await a.voir()
    assert r.statut == "OK" and r.faits["minimum_non_atteint"]["manque"] == 10 and len(r.faits["lignes"]) == 2


async def test_voir_la_commande_au_dessus_du_minimum_ne_change_pas(en_livraison_proches):
    a = en_livraison_proches
    await a.ajouter(articles="deux regina normale")
    r = await a.voir()
    assert r.statut == "OK" and "minimum_non_atteint" not in r.faits and r.faits["total"] is not None


async def test_une_commune_reelle_hors_de_toute_zone_est_hors_zone_avec_les_communes_livrees(commerce):  # noqa: F811
    await _regler(commerce)
    for adresse in ("3 rue de la Gare, Pont-Sainte-Maxence", "3 rue de la Gare Pont-Sainte-Maxence", "je suis à Pont Sainte Maxence"):
        r = await verifier_adresse(commerce.c, commerce.a, adresse)
        assert r.statut == "HORS_ZONE", (adresse, r)
        assert r.faits["commune"]["nom"] == "Pont-Sainte-Maxence" and "Chantilly" in r.faits["communes_livrees"]
        assert "Nous ne livrons pas à Pont-Sainte-Maxence." in r.suggestion and "Nous livrons" in r.suggestion and "Chantilly" in r.suggestion


async def test_un_nom_de_rue_n_est_jamais_une_commune_de_livraison(commerce):  # noqa: F811
    await _regler(commerce)
    for adresse in ("rue de Creil", "3 avenue de Compiègne", "rue de Paris"):
        assert (await verifier_adresse(commerce.c, commerce.a, adresse)).statut == "INTROUVABLE", adresse


async def test_un_nom_porte_par_plusieurs_communes_reste_a_confirmer(commerce):  # noqa: F811
    await _regler(commerce)
    r = await verifier_adresse(commerce.c, commerce.a, "5 rue de la Mairie, Saint-Just")
    assert r.statut == "AMBIGU" and len(r.faits["candidats"]) >= 2


# --------------------------------------------------------------------------- #
# M25 : la vente en plus propose UN article précis, et l'offre atteinte se dit sans l'article offert
# --------------------------------------------------------------------------- #

from api.services.commande import moteur  # noqa: E402
from api.tests.mark.test_restauration_commande_finaliser import Appel as AppelFinal  # noqa: E402
from api.tests.mark.test_restauration_remises_classeur import _poser  # noqa: E402


async def _offre_deux_pizzas_une_boisson(commerce):
    await _poser(
        commerce.c, commerce.a, "DEUX-UNE", "x_achetes_y_offert", {"achetes": 2}, {"offerts": 1, "perimetre_offert": {"categories": ["boissons"]}},
        {"categories": ["pizzas-tomate"]},
    )
    await commerce.c.execute("UPDATE mark.resto_remise SET phrase = '2 pizzas achetées, une boisson offerte.' WHERE ref = 'DEUX-UNE'")


async def test_la_vente_en_plus_propose_la_boisson_precise_quand_le_panier_n_en_a_pas(commerce):  # noqa: F811
    a = await AppelFinal(commerce).pret("une regina normale")
    r = await a.finaliser()
    assert (r.statut, r.manque) == ("INCOMPLETE", "vente_en_plus")
    proposition = r.faits["proposition"]
    assert proposition["raison"] == "categorie_manquante" and proposition["nom"] == "Coca-Cola" and proposition["prix"] == 200
    assert r.suggestion == "Avec cela, je vous propose un Coca-Cola à deux euros. Je vous l'ajoute ?"
    assert "quelque chose" not in r.suggestion


async def test_la_meilleure_vente_passe_devant(commerce):  # noqa: F811
    await commerce.c.execute(
        "INSERT INTO mark.resto_surcouche (site_id, objet, ref, etoile) VALUES ($1, 'produit', 'P-BOISSONS-ORANGINA', true)", commerce.a
    )
    r = await (await AppelFinal(commerce).pret("une regina normale")).finaliser()
    assert r.faits["proposition"]["nom"] == "Orangina" and r.faits["proposition"]["etoile"] is True


async def test_apres_la_boisson_le_dessert_puis_plus_rien_de_generique(commerce):  # noqa: F811
    a = await AppelFinal(commerce).pret("une regina normale et un coca")
    r = await a.finaliser()
    assert r.manque == "vente_en_plus" and r.faits["proposition"]["raison"] == "categorie_manquante"
    assert r.faits["proposition"]["nom"] == "Mousse au chocolat" and "une mousse au chocolat" in r.suggestion  # genre et nom commun accordés
    complet = await AppelFinal(commerce).pret("une regina normale, un coca et une mousse au chocolat")
    r = await complet.finaliser()
    assert r.manque == "prenom", r  # rien de pertinent à proposer : la commande continue, sans question générique


async def test_une_boisson_en_rupture_ou_l_alcool_ne_sont_jamais_proposes(commerce):  # noqa: F811
    from api.db.bases_clients.restauration_carte import poser_rupture

    assert (await poser_rupture(commerce.c, commerce.a, "BOI-COCA-COLA-33-CL", False, None, "portail")).statut == "OK"
    r = await (await AppelFinal(commerce).pret("une regina normale")).finaliser()
    assert r.faits["proposition"]["nom"] == "Coca-Cola Zéro"  # le suivant de la carte : la rupture n'est jamais proposée
    assert r.faits["proposition"]["nom"] not in {"Bière de Senlis", "Gustave", "Heineken", "Chianti"}  # jamais un alcool


async def test_l_offre_atteinte_est_dite_sans_l_article_offert_au_panier(commerce):  # noqa: F811
    await _offre_deux_pizzas_une_boisson(commerce)
    a = await AppelFinal(commerce, vente_en_plus=False).pret("deux regina normale")
    r = await moteur.remises_disponibles(a.source, a.p, a.regles)
    assert r.faits["a_dire"] is True and r.faits["moment"] == "offre_atteinte", r
    assert r.faits["remise"]["choix"][0] == "Coca-Cola" and "Coca-Cola" in r.suggestion and "deux pizzas achetées" in r.suggestion
    assert not any(c.isdigit() for c in r.suggestion)
    # une seule fois (T-08)
    assert (await moteur.remises_disponibles(a.source, a.p, a.regles)).faits["raison"] == "deja_dite"


async def test_l_offre_presque_atteinte_est_dite_avec_ce_qui_manque(commerce):  # noqa: F811
    await _offre_deux_pizzas_une_boisson(commerce)
    a = await AppelFinal(commerce, vente_en_plus=False).pret("une regina normale")
    r = await moteur.remises_disponibles(a.source, a.p, a.regles)
    assert r.faits["moment"] == "offre_presque_atteinte" and r.faits["remise"]["manque_articles"] == 1 and "Il vous manque encore un article" in r.suggestion


async def test_l_offre_ne_se_dit_ni_a_un_appelant_presse_ni_apres_un_refus(commerce):  # noqa: F811
    await _offre_deux_pizzas_une_boisson(commerce)
    a = await AppelFinal(commerce, vente_en_plus=False).pret("deux regina normale")
    assert (await moteur.remises_disponibles(a.source, a.p, a.regles, presse=True)).faits["raison"] == "presse"
    b = await AppelFinal(commerce, vente_en_plus=False, mentions_de_remise=3).pret("deux regina normale")
    assert (await moteur.remises_disponibles(b.source, b.p, b.regles, refus=True)).faits["raison"] == "refusee"


async def test_la_vente_en_plus_propose_l_article_offert_et_compte_comme_une_mention(commerce):  # noqa: F811
    await _offre_deux_pizzas_une_boisson(commerce)
    a = await AppelFinal(commerce).pret("deux regina normale")
    r = await a.finaliser()
    assert r.manque == "vente_en_plus" and r.faits["proposition"]["raison"] == "offre", r
    assert r.suggestion == "Remise DEUX-UNE : vous avez droit à un Coca-Cola offert. Je vous l'ajoute ?"
    assert a.p["mentions_de_remise"] == 1
    # après un refus de l'appelant, la vente en plus ne parle plus de l'offre : elle propose ce qui manque, sans la mentionner
    b = await AppelFinal(commerce, mentions_de_remise=3).pret("deux regina normale")
    b.p["remise_refusee"] = True
    r = await b.finaliser()
    assert r.faits["proposition"]["raison"] == "categorie_manquante" and "offert" not in r.suggestion


# --------------------------------------------------------------------------- #
# M26 : ce que le moteur dit des lignes est accordé
# --------------------------------------------------------------------------- #


async def test_les_lignes_sont_dites_avec_le_bon_genre_et_le_bon_nombre(commerce):  # noqa: F811
    a = AppelFinal(commerce, vente_en_plus=False)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert (await moteur.ajouter(a.source, a.p, a.regles, articles="deux tiramisu, une regina normale et une eau")).statut in ("OK", "CHOIX_OBLIGATOIRE")
    phrase = moteur._phrase_des_lignes([dict(l, quantite=l["quantite"]) for l in a.p["lignes"]])
    assert "deux tiramisus" in phrase and "une Regina Normale" in phrase and "une eau" in phrase, phrase
    assert "un Regina" not in phrase and "une Tiramisu" not in phrase


# --------------------------------------------------------------------------- #
# M22 : l'étiquette « Dernière commande » du client reconnu
# --------------------------------------------------------------------------- #

from api.db.bases_clients import horloge  # noqa: E402
from api.db.bases_clients.restauration_client import derniere_commande_du_client  # noqa: E402
from api.services.restauration.appel import Lieu  # noqa: E402
from api.services.restauration.etiquettes import phrase_de_la_derniere_commande  # noqa: E402
from api.services.restauration.source_commande import SourceClasseur  # noqa: E402
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI  # noqa: E402
from api.tests.mark.test_restauration_classeur_commande import TEL, enregistrer  # noqa: E402


async def test_la_derniere_commande_du_client_reconnu_est_dite_comme_a_l_oral(commerce):  # noqa: F811
    source = SourceClasseur(commerce.c, Lieu(commerce.base, commerce.a, 1), nom_prise="test")
    assert await derniere_commande_du_client(commerce.c, commerce.a, TEL) is None  # jamais commandé
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        assert (await enregistrer(commerce)).statut == "ENREGISTREE"  # 2 Margherita normale + 1 Coca-Cola, à emporter
        derniere = await derniere_commande_du_client(commerce.c, commerce.a, TEL)
    assert derniere["mode"] == "emporter" and [(l["nom"], l["quantite"]) for l in derniere["lignes"]] == [("Margherita Normale", 2), ("Coca-Cola", 1)]
    assert derniere["lignes"][0]["categorie"] == "Pizzas base tomate"
    assert phrase_de_la_derniere_commande(derniere, source) == "deux Margherita Normale et un Coca-Cola, à emporter"
    assert not any(c.isdigit() for c in phrase_de_la_derniere_commande(derniere, source))  # ni prix ni chiffre
    assert await derniere_commande_du_client(commerce.c, commerce.a, "+33699999999") is None  # un autre numéro : rien
    assert await derniere_commande_du_client(commerce.c, commerce.b, TEL) is None  # un autre établissement : rien
    assert phrase_de_la_derniere_commande(None, source) == ""


async def test_une_derniere_commande_annulee_n_est_pas_proposee(commerce):  # noqa: F811
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        r = await enregistrer(commerce)
        await commerce.c.execute("UPDATE mark.resto_commande SET statut = 'annulee' WHERE numero = $1::uuid", str(r.faits["numero"]))
        assert await derniere_commande_du_client(commerce.c, commerce.a, TEL) is None


# --------------------------------------------------------------------------- #
# M19 : « carte à la livraison » dans la liste fermée des moyens de paiement
# --------------------------------------------------------------------------- #


async def test_la_carte_a_la_livraison_est_un_moyen_de_paiement_du_classeur(commerce):  # noqa: F811
    import asyncpg

    from api.tests.mark.test_restauration_classeur_commande import brouillon

    await commerce.c.execute("UPDATE mark.resto_reglage SET moyens_paiement = '{carte,especes,carte_livraison}' WHERE site_id = $1", commerce.a)
    with pytest.raises(asyncpg.CheckViolationError):  # la liste reste fermée : un moyen inconnu est toujours refusé par la base
        await commerce.c.execute("UPDATE mark.resto_reglage SET moyens_paiement = '{carte,bitcoin}' WHERE site_id = $1", commerce.a)
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        b = brouillon(paiement={"moyens": [{"moyen": "carte_livraison", "montant": 2380}]})
        r = await enregistrer(commerce, b)
    assert r.statut == "ENREGISTREE", r
    source = SourceClasseur(commerce.c, Lieu(commerce.base, commerce.a, 1), nom_prise="test")
    assert source.libelles_des_moyens["carte_livraison"] == "par carte à la livraison"
    assert "carte_livraison" in (await source.reglages())["moyens_paiement"]


# --------------------------------------------------------------------------- #
# M29 : les compositions de la carte réelle de Casa Italia dans la carte d'essai de référence
# --------------------------------------------------------------------------- #


async def test_les_pizzas_de_la_carte_d_essai_ont_leur_composition_et_l_inconnu_reste_inconnu(commerce):  # noqa: F811
    from api.tests.mark.test_restauration_classeur_carte import CARTE

    par_nom = {(p["categorie_id"], p["nom"]): [i["nom"] for i in p["ingredients"]] for p in CARTE["produits"]}
    pizzas = [(k, v) for k, v in par_nom.items() if k[0].startswith("pizzas-")]
    assert len(pizzas) == 29 and all(v for _, v in pizzas), [k for k, v in pizzas if not v]  # TOUTES les pizzas
    assert par_nom[("pizzas-tomate", "Calzone")] == ["jambon", "champignons", "œuf"]
    assert par_nom[("pizzas-tomate", "Regina")] == ["sauce tomate", "mozzarella", "jambon", "champignons"]  # celle du lot 0, inchangée
    assert par_nom[("pates", "Bolognese")] == [] and par_nom[("pates", "Capelletto Tartufo")] == []  # la carte réelle ne dit rien : inconnu
    assert par_nom[("desserts", "Tiramisu")] == [] and par_nom[("entrees", "Calamars frits")] == []
    # « il y a quoi dans la Calzone ? » reçoit une réponse ; « dans la Bolognese ? » reste « je ne peux pas vous le confirmer »
    a = AppelFinal(commerce)
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    r = await moteur.voir_produit(a.source, a.p, a.regles, "calzone")
    assert r.faits["renseigne"] is True and r.suggestion == "Dans Calzone, il y a jambon, champignons et œuf."
    r = await moteur.voir_produit(a.source, a.p, a.regles, "bolognese")
    assert r.faits["renseigne"] is False and r.suggestion == moteur.NON_CONFIRMABLE


# M38 (SA-18) : le comptoir branche la colonne « Dite » (l'offre rendue à dire) et « Acceptée » (la commande enregistrée qui la porte).
async def test_une_offre_dite_puis_acceptee_fait_monter_dite_et_acceptee(commerce):  # noqa: F811
    from api.db.bases_clients.restauration_remise_offre import compter_les_offres

    await _offre_deux_pizzas_une_boisson(commerce)
    a = await AppelFinal(commerce, vente_en_plus=False).pret("deux regina normale et un coca")
    dite = await moteur.remises_disponibles(a.source, a.p, a.regles, appel_id="appel-final")
    assert dite.faits["a_dire"] is True, dite
    [(remise_id, (dites, acceptees))] = (await compter_les_offres(commerce.c, commerce.a)).items()
    assert (dites, acceptees) == (1, 0)
    r = await a.jusqu_a_la_relecture()
    r = await a.finaliser(prenom="Alice", moyen="carte", confirmer=True)
    assert r.statut == "ENREGISTREE", r
    assert (await compter_les_offres(commerce.c, commerce.a))[remise_id] == (1, 1)


async def test_une_offre_appliquee_sans_avoir_ete_dite_n_est_pas_comptee(commerce):  # noqa: F811
    from api.db.bases_clients.restauration_remise_offre import compter_les_offres

    await _offre_deux_pizzas_une_boisson(commerce)
    a = await AppelFinal(commerce, vente_en_plus=False).pret("deux regina normale et un coca")
    await a.jusqu_a_la_relecture()
    r = await a.finaliser(prenom="Alice", moyen="carte", confirmer=True)
    assert r.statut == "ENREGISTREE", r
    assert await compter_les_offres(commerce.c, commerce.a) == {}


async def test_un_compteur_d_offre_en_echec_ne_defait_jamais_la_commande(commerce, monkeypatch):  # noqa: F811
    from api.db.bases_clients import restauration_commande

    async def casse(*_a, **_k):
        raise RuntimeError("table absente")

    monkeypatch.setattr(restauration_commande, "noter_l_acceptation", casse)
    a = await AppelFinal(commerce, vente_en_plus=False).pret("deux regina normale et un coca")
    await a.jusqu_a_la_relecture()
    r = await a.finaliser(prenom="Alice", moyen="carte", confirmer=True)
    assert r.statut == "ENREGISTREE" and len(await a.commandes()) == 1
