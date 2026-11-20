"""[.mark] Module Restauration, lot 7, étapes 2 et 3 : les douze mécanismes de remise dans le classeur, appliqués au total.

Vraie base, carte de référence, jeudi 12 h. Panier d'essai : 2 Margherita normale (10,90), 1 Regina Mega (20,90), 1 Coca (2,00) = 44,70.

| Test | Ce qu'il prouve |
|---|---|
| douze mécanismes | chacun rend son montant exact au centime ; la liste est fermée (un mécanisme inconnu n'est jamais appliqué ni annoncé) |
| créneau | hors du créneau, la remise ne s'applique pas |
| fidélité | la 10e commande du client reconnu seulement |
| chiffrage | ``chiffrer_panier`` choisit l'ensemble le plus avantageux et dit le total net |
| enregistrement | la remise nommée est recalculée chez nous, le total payé est le net, une ligne de remise chiffrée part à la caisse |
| article offert | l'article offert est ajouté à son prix avec une remise du même montant ; hors rupture seulement |
| cloisonnement | la remise d'un autre établissement ne s'applique jamais |
"""

from __future__ import annotations

import json
import uuid

from api.db.bases_clients.restauration_commande import chiffrer_panier
from api.db.bases_clients.restauration_remise import FAMILLE_DU_MECANISME, MECANISMES, remises_applicables
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.db.bases_clients import connexion as schema
from api.tests.mark.test_base_client import base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import TEL, brouillon, commerce, enregistrer  # noqa: F401

LIGNES = [
    {"code_caisse": "PIZ-MARGHERITA-NORMALE", "prix_unitaire": 1090, "quantite": 2, "produit_id": "P-PIZZAS-TOMATE-MARGHE", "categorie_id": "pizzas-tomate"},
    {"code_caisse": "PIZ-REGINA-MEGA", "prix_unitaire": 2090, "quantite": 1, "produit_id": "P-PIZZAS-TOMATE-REGINA", "categorie_id": "pizzas-tomate"},
    {"code_caisse": "BOI-COCA-COLA-33-CL", "prix_unitaire": 200, "quantite": 1, "produit_id": "P-BOISSONS-COCA-COLA", "categorie_id": "boissons"},
]
PRIX = {"PIZ-REGINA-NORMALE": 1290, "PIZ-REGINA-MEGA": 2090, "PIZ-MARGHERITA-NORMALE": 1090, "BOI-COCA-COLA-33-CL": 200}
PANIER = {"mode": "emporter", "sous_total": 4470, "lignes": LIGNES, "prix_par_code": PRIX}

# (mécanisme, déclencheur, effet, périmètre, montant attendu)
LES_DOUZE = [
    ("pourcentage", {}, {"pourcentage": 10}, {}, 447),
    ("montant", {}, {"montant": 300}, {}, 300),
    ("x_achetes_y_offert", {"achetes": 2}, {"offerts": 1, "perimetre_offert": {"categories": ["boissons"]}}, {"categories": ["pizzas-tomate"]}, 200),
    ("deuxieme_moitie_prix", {"rang": 2}, {"pourcentage": 50}, {"categories": ["pizzas-tomate"]}, 545),
    ("prix_du_jour", {}, {"prix": 900}, {"produits": ["P-PIZZAS-TOMATE-MARGHE"]}, 380),
    ("seuil_panier", {"minimum": 4000}, {"montant": 500}, {}, 500),
    ("passage_en_menu", {"composition": [{"perimetre": {"categories": ["pizzas-tomate"]}}, {"perimetre": {"categories": ["boissons"]}}]}, {"prix": 2000}, {}, 290),
    ("taille_superieure", {}, {"prix_de": "PIZ-REGINA-NORMALE"}, {"codes": ["PIZ-REGINA-MEGA"]}, 800),
    ("offre_famille", {"composition": [{"perimetre": {"categories": ["pizzas-tomate"]}, "quantite": 3}]}, {"prix": 3600}, {}, 670),
    ("creneau", {}, {"pourcentage": 20}, {}, 894),
    ("nouveaute", {}, {"pourcentage": 20}, {"produits": ["P-PIZZAS-TOMATE-REGINA"]}, 418),
    ("fidelite", {"tous_les": 10}, {"pourcentage": 5}, {}, 224),
]


async def _poser(c, site, ref, mecanisme, declencheur, effet, perimetre, **plus):
    await c.execute(
        "INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, declencheur, effet, perimetre, etat, cumul, moment) "
        "VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, 'active', $8, $9::jsonb)",
        site, ref, f"Remise {ref}", mecanisme, json.dumps(declencheur), json.dumps(effet), json.dumps(perimetre), plus.get("cumul", "exclusive"),
        json.dumps(plus["moment"]) if plus.get("moment") else None,
    )


async def test_les_douze_mecanismes_chacun_son_montant_au_centime(commerce):
    c, a = commerce.c, commerce.a
    assert len(MECANISMES) == 12 and len(set(MECANISMES)) == 12 and set(FAMILLE_DU_MECANISME) == set(MECANISMES)
    assert [m for m, *_ in LES_DOUZE] == list(MECANISMES) or {m for m, *_ in LES_DOUZE} == set(MECANISMES)
    await c.execute("INSERT INTO mark.resto_client (site_id, telephone, nb_commandes) VALUES ($1, $2, 9)", a, TEL)
    for mecanisme, declencheur, effet, perimetre, _ in LES_DOUZE:
        await _poser(c, a, mecanisme, mecanisme, declencheur, effet, perimetre, moment={"jours": [4]} if mecanisme == "creneau" else None)
    par_ref = {r["ref"]: r for r in await remises_applicables(c, a, PANIER, JEUDI_MIDI, {"telephone": TEL})}
    for mecanisme, *_, attendu in LES_DOUZE:
        assert par_ref[mecanisme]["montant"] == attendu, (mecanisme, par_ref[mecanisme]["montant"], attendu)
        assert par_ref[mecanisme]["chiffree"] is True


async def test_un_mecanisme_inconnu_n_est_jamais_applique_ni_annonce(commerce, base_prete):
    c, a = commerce.c, commerce.a
    # Depuis la 031 la base refuse d'écrire un mécanisme hors liste : pour jouer une ligne écrite AVANT la contrainte, le propriétaire la retire ici (la garde de la couche reste la dernière).
    proprietaire = await schema.connecter_proprietaire(base_prete)
    try:
        await proprietaire.execute("ALTER TABLE mark.resto_remise DROP CONSTRAINT IF EXISTS resto_remise_mecanisme_ferme")
    finally:
        await proprietaire.close()
    await _poser(c, a, "BIDON", "bonus_mystere", {}, {"pourcentage": 50}, {})
    assert await remises_applicables(c, a, PANIER, JEUDI_MIDI) == []


async def test_creneau_hors_du_creneau_et_fidelite_a_la_dixieme(commerce):
    c, a = commerce.c, commerce.a
    await _poser(c, a, "VENDREDI", "creneau", {}, {"pourcentage": 20}, {}, moment={"jours": [5]})
    await _poser(c, a, "FIDE", "fidelite", {"tous_les": 10}, {"pourcentage": 50}, {})
    par_ref = {r["ref"]: r for r in await remises_applicables(c, a, PANIER, JEUDI_MIDI, {"telephone": TEL})}
    assert par_ref["VENDREDI"]["montant"] is None            # on est jeudi
    assert par_ref["FIDE"]["montant"] is None                 # client inconnu : première commande
    await c.execute("INSERT INTO mark.resto_client (site_id, telephone, nb_commandes) VALUES ($1, $2, 8)", a, TEL)
    assert {r["ref"]: r for r in await remises_applicables(c, a, PANIER, JEUDI_MIDI, {"telephone": TEL})}["FIDE"]["montant"] is None   # 9e
    await c.execute("UPDATE mark.resto_client SET nb_commandes = 9 WHERE site_id = $1", a)
    assert {r["ref"]: r for r in await remises_applicables(c, a, PANIER, JEUDI_MIDI, {"telephone": TEL})}["FIDE"]["montant"] == 2235  # 10e : moitié


async def test_le_chiffrage_choisit_le_plus_avantageux_et_dit_le_total_net(commerce):
    c, a = commerce.c, commerce.a
    await _poser(c, a, "DIX", "pourcentage", {}, {"pourcentage": 10}, {})                 # 2 x 10,90 + 2,00 = 23,80 : 2,38
    await _poser(c, a, "DEUX", "montant", {}, {"montant": 500}, {})                        # 5,00 : la meilleure exclusive
    await _poser(c, a, "CUM1", "montant", {}, {"montant": 100}, {}, cumul="cumulable")
    r = await chiffrer_panier(c, a, "emporter", [{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 2}, {"code_caisse": "BOI-COCA-COLA-33-CL"}])
    assert r.statut == "OK"
    assert [(x["ref"], x["montant"]) for x in r.faits["remises"]] == [("DEUX", 500)]
    assert (r.faits["sous_total"], r.faits["total_remises"], r.faits["total"]) == (2380, 500, 1880)
    # sans remise valable : rien ne change, le total est celui d'avant
    await c.execute("UPDATE mark.resto_remise SET etat = 'suspendue'")
    r = await chiffrer_panier(c, a, "emporter", [{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 2}, {"code_caisse": "BOI-COCA-COLA-33-CL"}])
    assert (r.faits["remises"], r.faits["total"]) == ([], 2380)


async def test_la_remise_nommee_est_recalculee_le_total_paye_est_le_net_et_la_caisse_recoit_la_ligne(commerce):
    c, a = commerce.c, commerce.a
    await _poser(c, a, "BOIS", "x_achetes_y_offert", {"achetes": 2}, {"offerts": 1, "perimetre_offert": {"categories": ["boissons"]}}, {"categories": ["pizzas-tomate"]})
    b = brouillon(remises=[{"ref": "BOIS", "montant": 99999}], paiement={"moyens": [{"moyen": "carte", "montant": 2180}]})
    r = await enregistrer(commerce, b)
    assert (r.statut, r.faits["total"]) == ("ENREGISTREE", 2180), r        # 23,80 - la boisson offerte 2,00 = 21,80
    ligne = await c.fetchrow("SELECT remises, sous_total, total FROM mark.resto_commande WHERE numero = $1", uuid.UUID(r.faits["numero"]))
    assert json.loads(ligne["remises"]) == [{"nom": "Remise BOIS", "montant": 200, "taux_tva": 10000, "ref_caisse": None}]  # M14 : le taux figé sur la remise and (ligne["sous_total"], ligne["total"]) == (2380, 2180)
    # un règlement au prix plein ne couvre plus le total net
    refus = await enregistrer(commerce, brouillon(remises=[{"ref": "BOIS"}], appel_id="plein"))
    assert refus.statut == "INCOMPLETE" and refus.manque == "paiement"
    # une remise qui ne s'applique pas à ce panier (une seule pizza) est refusée
    seule = brouillon(remises=[{"ref": "BOIS"}], appel_id="une", lignes=[{"code_caisse": "PIZ-MARGHERITA-NORMALE"}], paiement={"moyens": [{"moyen": "carte", "montant": 1090}]})
    r = await enregistrer(commerce, seule)
    assert (r.statut, r.faits["raison"]) == ("REFUSEE", "remise_inconnue")


async def test_un_article_offert_part_a_son_prix_avec_une_remise_du_meme_montant(commerce):
    c, a = commerce.c, commerce.a
    await _poser(c, a, "SEUIL", "seuil_panier", {"minimum": 2000}, {"offert": {"codes": ["BOI-COCA-COLA-33-CL"]}}, {})
    b = {"lignes": [{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 2}]}
    chiffre = await chiffrer_panier(c, a, "emporter", b["lignes"])
    assert [(o["code_caisse"], o["prix_unitaire"]) for o in chiffre.faits["offerts"]] == [("BOI-COCA-COLA-33-CL", 200)]
    assert (chiffre.faits["total_remises"], chiffre.faits["total"]) == (200, 2180)
    r = await enregistrer(commerce, brouillon(lignes=b["lignes"], remises=[{"ref": "SEUIL"}], paiement={"moyens": [{"moyen": "carte", "montant": 2180}]}))
    assert (r.statut, r.faits["total"]) == ("ENREGISTREE", 2180), r
    lignes = await c.fetch("SELECT code_caisse, prix_unitaire, quantite FROM mark.resto_commande_ligne WHERE numero = $1 ORDER BY rang", uuid.UUID(r.faits["numero"]))
    assert [(l["code_caisse"], l["prix_unitaire"], l["quantite"]) for l in lignes] == [("PIZ-MARGHERITA-NORMALE", 1090, 2), ("BOI-COCA-COLA-33-CL", 200, 1)]
    ligne = await c.fetchrow("SELECT sous_total, total, remises FROM mark.resto_commande WHERE numero = $1", uuid.UUID(r.faits["numero"]))
    assert (ligne["sous_total"], ligne["total"]) == (2380, 2180) and json.loads(ligne["remises"])[0]["montant"] == 200
    # l'article offert en rupture : la remise ne s'applique pas
    from api.db.bases_clients.restauration_carte import poser_rupture

    await poser_rupture(c, a, "BOI-COCA-COLA-33-CL", False, None, "portail")
    sans = await chiffrer_panier(c, a, "emporter", b["lignes"])
    assert (sans.faits["remises"], sans.faits["total"]) == ([], 2180 + 200 - 200)


async def test_la_remise_d_un_autre_etablissement_ne_s_applique_jamais(commerce):
    c, a, b = commerce.c, commerce.a, commerce.b
    await _poser(c, b, "AUTRE", "montant", {}, {"montant": 500}, {})
    assert await remises_applicables(c, a, PANIER, JEUDI_MIDI) == []
    r = await enregistrer(commerce, brouillon(remises=[{"ref": "AUTRE"}]))
    assert (r.statut, r.faits["raison"]) == ("REFUSEE", "remise_inconnue")


# --------------------------------------------------------------------------- #
# Par les outils de l'agent : ce qui est dit est ce qui est appliqué
# --------------------------------------------------------------------------- #


async def test_ce_que_l_agent_dit_est_ce_qui_part_a_la_caisse(commerce):
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    c, a = commerce.c, commerce.a
    await _poser(c, a, "DIX", "pourcentage", {}, {"pourcentage": 10}, {})
    appel = await Appel(commerce, vente_en_plus=False).pret(A("regina", 1, "Normale"), "coca")          # 12,90 + 2,00 = 14,90
    vu = await moteur.voir_commande(appel.source, appel.p, appel.regles)
    assert vu.faits["total"] == 1341 and vu.faits["total_remises"] == 149                         # 14,90 - 1,49
    assert [(r["nom"], r["montant"]) for r in vu.faits["remises"]] == [("Remise DIX", 149)]
    assert "économisez" in vu.suggestion
    relecture = await appel.jusqu_a_la_relecture()
    # B12 (lot 6, journal L06-41) : la relecture ne nomme plus la remise ; elle dit le total net, qui est juste
    assert relecture.faits["total"] == 1341 and "Remise DIX" not in relecture.suggestion and "treize euros quarante et un" in relecture.suggestion
    fait = await appel.confirmer()
    assert fait.statut in ("ENREGISTREE", "TRANSMISE"), fait
    envoyee = appel.prise.recues[0]
    assert envoyee["total"] == 1341 and [(r["nom"], r["montant"]) for r in envoyee["remises"]] == [("Remise DIX", 149)]
    ligne = await c.fetchrow("SELECT total, remises FROM mark.resto_commande WHERE numero = $1", uuid.UUID(fait.faits["numero"]))
    assert ligne["total"] == 1341 and json.loads(ligne["remises"])[0]["montant"] == 149


async def test_la_fidelite_reconnait_le_numero_qui_s_affiche(commerce):
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    c, a = commerce.c, commerce.a
    await _poser(c, a, "FIDE", "fidelite", {"tous_les": 5}, {"pourcentage": 50}, {})
    await c.execute("INSERT INTO mark.resto_client (site_id, telephone, nb_commandes) VALUES ($1, $2, 4)", a, TEL)
    appel = await Appel(commerce, vente_en_plus=False).pret(A("regina", 1, "Normale"))                  # 12,90
    appel.p["client"]["telephone_affiche"] = TEL                                                    # posé par l'action à chaque geste
    vu = await moteur.voir_commande(appel.source, appel.p, appel.regles)
    assert (vu.faits["total_remises"], vu.faits["total"]) == (645, 645)
    appel.p["client"].pop("telephone_affiche")                                                      # numéro masqué : pas de client reconnu
    vu = await moteur.voir_commande(appel.source, appel.p, appel.regles)
    assert (vu.faits["total_remises"], vu.faits["total"]) == (0, 1290)


# --------------------------------------------------------------------------- #
# La parole des remises (T-08)
# --------------------------------------------------------------------------- #


async def test_l_agent_ne_parle_d_une_remise_de_lui_meme_qu_une_fois_jamais_presse_jamais_apres_un_non(commerce):
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    c, a = commerce.c, commerce.a
    await _poser(c, a, "DIX", "pourcentage", {}, {"pourcentage": 10}, {})
    await c.execute("UPDATE mark.resto_remise SET phrase = 'Dix pour cent de moins sur la commande.' WHERE ref = 'DIX'")
    await _poser(c, a, "SEUIL", "seuil_panier", {"minimum": 2000}, {"montant": 300}, {}, cumul="cumulable")
    # un client pressé : rien, et ça ne compte pas
    appel = await Appel(commerce, vente_en_plus=False).pret(A("regina", 1, "Normale"))
    r = await moteur.remises_disponibles(appel.source, appel.p, appel.regles, presse=True)
    assert (r.statut, r.faits["a_dire"], r.faits["raison"]) == ("OK", False, "presse")
    # une première fois : la remise qui s'applique, dans la phrase du restaurant
    r = await moteur.remises_disponibles(appel.source, appel.p, appel.regles)
    assert r.faits["a_dire"] is True and r.faits["moment"] == "appliquee" and r.suggestion == "Dix pour cent de moins sur la commande."
    # la limite par appel (1 par défaut) : plus rien de lui-même
    r = await moteur.remises_disponibles(appel.source, appel.p, appel.regles)
    assert (r.faits["a_dire"], r.faits["raison"]) == (False, "deja_dite")
    # mais l'appelant qui demande est toujours répondu
    r = await moteur.remises_disponibles(appel.source, appel.p, appel.regles, demande=True)
    assert r.faits["a_dire"] is True and {x["nom"] for x in r.faits["remises"]} == {"Remise DIX", "Remise SEUIL"}
    # un non : plus jamais de lui-même, même si la limite le permet
    neuf = await Appel(commerce, vente_en_plus=False, mentions_de_remise=3).pret(A("regina", 1, "Normale"))
    assert (await moteur.remises_disponibles(neuf.source, neuf.p, neuf.regles, refus=True)).faits["raison"] == "refusee"
    assert (await moteur.remises_disponibles(neuf.source, neuf.p, neuf.regles)).faits["raison"] == "refusee"
    # zéro : seulement sur demande
    zero = await Appel(commerce, vente_en_plus=False, mentions_de_remise=0).pret(A("regina", 1, "Normale"))
    assert (await moteur.remises_disponibles(zero.source, zero.p, zero.regles)).faits["raison"] == "deja_dite"


async def test_un_seuil_presque_atteint_est_dit_une_fois_avec_ce_qui_manque(commerce):
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    c, a = commerce.c, commerce.a
    await _poser(c, a, "SEUIL", "seuil_panier", {"minimum": 1500}, {"montant": 300}, {})
    appel = await Appel(commerce, vente_en_plus=False).pret(A("margherita", 1, "Normale"), "coca")      # 10,90 + 2,00 = 12,90 : 86 % du seuil
    r = await moteur.remises_disponibles(appel.source, appel.p, appel.regles)
    assert (r.faits["moment"], r.faits["remise"]["manque"]) == ("seuil_presque_atteint", 210) and "deux euros dix" in r.suggestion.lower().replace("-", " ")
    assert (await moteur.remises_disponibles(appel.source, appel.p, appel.regles)).faits["a_dire"] is False
    # loin du seuil : rien à dire
    loin = await Appel(commerce, vente_en_plus=False).pret("coca")
    assert (await moteur.remises_disponibles(loin.source, loin.p, loin.regles)).faits["raison"] == "rien_a_dire"


# --------------------------------------------------------------------------- #
# voir_produit : composition et signalements (E-14, E-15)
# --------------------------------------------------------------------------- #


async def test_voir_produit_composition_seulement_signalement_seulement_sur_demande_inconnu_jamais_dit_sans(commerce):
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    c, a = commerce.c, commerce.a
    appel = Appel(commerce)
    vu = lambda produit, allergie=None: moteur.voir_produit(appel.source, appel.p, appel.regles, produit, allergie)  # noqa: E731
    # la composition : « il y a quoi dans la regina » ; jamais un allergène de soi-même
    r = await vu("la regina")
    assert r.statut == "OK" and "mozzarella" in r.faits["ingredients"] and "signalement" not in r.faits
    assert "gluten" not in r.suggestion.lower() and "allerg" not in r.suggestion.lower()
    # une fiche sans allergènes renseignés : INCONNU, jamais « sans »
    r = await vu("la regina", "les cacahuètes")
    assert r.faits["signalement"] == "inconnu" and r.suggestion == "Je ne peux pas vous le confirmer."
    # la fiche renseignée : présent / absent d'après la fiche
    await c.execute("UPDATE mark.resto_produit SET allergenes = '{gluten,lait}' WHERE ref = 'P-PIZZAS-TOMATE-REGINA'")
    r = await vu("la regina", "le gluten")
    assert (r.faits["signalement"], r.faits["code"]) == ("present", "gluten") and r.suggestion == "Oui, Regina contient le gluten."
    r = await vu("la regina", "cacahuètes")
    assert r.faits["signalement"] == "absent_de_la_fiche" and r.suggestion.startswith("D'après la fiche")
    # aucun allergène connu (liste vide) n'est pas inconnu
    await c.execute("UPDATE mark.resto_produit SET allergenes = '{}' WHERE ref = 'P-PIZZAS-TOMATE-REGINA'")
    assert (await vu("la regina", "le lait")).faits["signalement"] == "absent_de_la_fiche"
    # un produit sans composition renseignée : « je ne peux pas vous le confirmer », sans passer la main
    await c.execute("UPDATE mark.resto_produit SET ingredients = '[]'::jsonb WHERE ref = 'P-PIZZAS-TOMATE-REGINA'")
    r = await vu("la regina")
    assert (r.faits["renseigne"], r.suggestion) == (False, "Je ne peux pas vous le confirmer.")
    # un produit ambigu ou inconnu : le statut fermé de la recherche
    assert (await vu("zzzzzz")).statut == "INTROUVABLE"
    assert (await vu(None)).statut == "ARGUMENT_INVALIDE"


# --------------------------------------------------------------------------- #
# reconnaitre_le_client : habitudes écrites par finaliser, relues à l'appel suivant
# --------------------------------------------------------------------------- #


async def test_les_habitudes_ecrites_a_la_commande_sont_relues_a_l_appel_suivant_et_jointes_si_confirmees(commerce):
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    c = commerce.c
    premier = await Appel(commerce, vente_en_plus=False).pret(A("regina", 1, "Normale"))
    await premier.jusqu_a_la_relecture()
    premier.p["habitude"] = "sonner au deuxième"  # une habitude retenue (M41)
    fait = await premier.confirmer()
    assert fait.statut in ("ENREGISTREE", "TRANSMISE"), fait
    # l'appel suivant : le numéro qui s'affiche reconnaît Alice et relit son habitude
    suivant = await Appel(commerce, vente_en_plus=False).pret("coca")
    suivant.p["client"]["telephone_affiche"] = TEL
    r = await moteur.reconnaitre_le_client(suivant.source, suivant.p, suivant.regles)
    assert r.faits["connu"] is True and r.faits["prenom"] == "Alice" and r.faits["consignes"] == ["sonner au deuxième"]
    assert "toujours d'actualité" in r.suggestion and suivant.p.get("note") is None
    # confirmée : jointe à la note de la commande, qui part avec elle
    r = await moteur.reconnaitre_le_client(suivant.source, suivant.p, suivant.regles, confirmer_consignes=True)
    assert r.faits["jointes_a_la_commande"] is True
    await suivant.jusqu_a_la_relecture()
    fait = await suivant.confirmer()
    note = await c.fetchval("SELECT note FROM mark.resto_commande WHERE numero = $1", uuid.UUID(fait.faits["numero"]))
    assert note == "sonner au deuxième"
    # un numéro masqué ou inconnu : rien à dire
    masque = await Appel(commerce, affiche=None).pret("coca")
    assert (await moteur.reconnaitre_le_client(masque.source, masque.p, masque.regles)).faits["raison"] == "numero_masque"
    autre = await Appel(commerce).pret("coca")
    autre.p["client"]["telephone_affiche"] = "+33699999999"
    assert (await moteur.reconnaitre_le_client(autre.source, autre.p, autre.regles)).faits["raison"] == "inconnu"
