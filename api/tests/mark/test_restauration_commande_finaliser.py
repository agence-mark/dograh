"""[.mark] Module Restauration, lot 5, étape 3 : ``finaliser`` (relecture en deux temps, règlement mixte, numéros, offre en plus, enregistrement).

Vraie base, carte de référence, prise de test (envoi réel du comptoir vers la prise, sans tiers), heure fixée au jeudi 12 h.

Lot 4 de la partie 1 (D49) : réécrit sur la fiche. Les articles se donnent structurés (``commande_sur_la_fiche``) ; la fin est celle du contrat
(M39, M40) : le récapitulatif d'abord et son accord, puis le règlement, le numéro et le prénom, puis l'enregistrement.

| Test | Ce qu'il prouve |
|---|---|
| un manque à la fois | articles, taille, offre en plus (une fois), récapitulatif, règlement, prénom : dans l'ordre, un seul à la fois |
| relecture en deux temps | rien n'est enregistré sans relecture valide ; « oui » sans relecture relit d'abord ; après une correction seul ce qui change est relu |
| enregistrement | total de la carte, numéro unique, heure annoncée, envoi à la prise une fois, le client connu |
| numéro de l'appelant | affiché : jamais demandé, jamais lu (« je garde le numéro qui s'affiche ») ; masqué : demandé ; invalide refusé |
| règlement mixte | titres puis espèces : reste et monnaie calculés par le code ; moyen non accepté et plafond refusés |
| doublon | un second « oui » rend ``DEJA_FAIT`` avec le même numéro ; la prise ne reçoit qu'une commande |
| consigne et allergie | l'habitude est gardée sur la fiche ; l'allergie va sur la commande, jamais sur la fiche (T-16) |
| réglages | offre en plus éteinte : jamais proposée |
| fermé | un restaurant qui ferme entre-temps refuse avec la raison fermée |
"""

from __future__ import annotations


from api.db.bases_clients import horloge
from api.services.commande import moteur, panier
from api.services.commande.moteur import Appelant, Reglages
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.caisse.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark import commande_sur_la_fiche as F
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401

TEL = "+33612345678"


class Appel:
    def __init__(self, commerce, *, affiche: str | None = TEL, prise: PriseTest | None = None, **reglages):
        self.commerce = commerce
        self.prise = prise or PriseTest()
        self.source = SourceClasseur(commerce.c, Lieu(commerce.base, commerce.a, 1), nom_prise="test", prise=self.prise)
        self.p = panier.nouveau()
        self.regles = Reglages(**reglages)
        self.appelant = Appelant(affiche, "appel-final")

    async def pret(self, *articles):
        await moteur.choisir_mode(self.source, self.p, self.regles, "emporter")
        r = await F.ajouter(self.source, self.p, self.regles, *(articles or (A("regina", 1, "Normale"), "coca")))
        assert r.statut == "OK", r
        return self

    async def ajouter(self, *articles):
        return await F.ajouter(self.source, self.p, self.regles, *articles)

    async def finaliser(self, **kw):
        return await moteur.finaliser(self.source, self.p, self.regles, self.appelant, **kw)

    async def jusqu_a_la_relecture(self):
        """La fin jusqu'au récapitulatif (la proposition en plus, une fois, passe avant)."""
        for _ in range(8):
            r = await self.finaliser()
            if r.manque == "relecture":
                return r
            assert r.manque == "vente_en_plus", r
        raise AssertionError("pas de relecture")

    async def confirmer(self, **kw):
        """Son « oui » au récapitulatif, avec ce qu'elle dit de la fin (règlement, prénom) : les cases de fin de la fiche ; puis son « oui » au
        numéro qui s'affiche quand le code le propose (``confirmer_numero``, une fois)."""
        r = await self.finaliser(**{"confirmer": True, "prenom": "Alice", "moyen": "carte", **kw})
        if r.manque == "confirmer_numero":  # C7 (lot 19 bis) : son « oui » passe par la réponse à la question, jamais par un second « confirmer »
            moteur.repondre_au_numero_affiche(self.p, "accepte", self.appelant)
            r = await self.finaliser(**{"confirmer": True, "prenom": "Alice", "moyen": "carte", **kw})
        return r

    async def commandes(self):
        return await self.commerce.c.fetch("SELECT * FROM mark.resto_commande WHERE site_id = $1", self.commerce.a)


# --------------------------------------------------------------------------- #
# Un manque à la fois
# --------------------------------------------------------------------------- #


async def test_un_manque_a_la_fois_dans_l_ordre(commerce):
    a = Appel(commerce)
    r = await a.finaliser()
    assert (r.statut, r.manque) == ("INCOMPLETE", "mode")
    await moteur.choisir_mode(a.source, a.p, a.regles, "emporter")
    assert (await a.finaliser()).manque == "articles"
    await a.ajouter("regina")
    r = await a.finaliser()
    assert (r.statut, r.manque) == ("CHOIX_OBLIGATOIRE", "taille")  # la taille avant tout le reste
    await F.repondre(a.source, a.p, a.regles, "normale")
    r = await a.finaliser()
    assert (r.statut, r.manque) == ("INCOMPLETE", "vente_en_plus")
    assert (await a.finaliser()).manque == "relecture"  # l'offre en plus n'est faite qu'une fois ; le récapitulatif ensuite
    assert (await a.finaliser(confirmer=True)).manque == "paiement"  # après son accord : le règlement
    assert (await a.finaliser(moyen="carte")).manque == "confirmer_numero"  # le numéro qui s'affiche, proposé une fois
    moteur.repondre_au_numero_affiche(a.p, "accepte", a.appelant)  # C7 (lot 19 bis) : son « oui » est la réponse à la question
    assert (await a.finaliser(moyen="carte", confirmer=True)).manque == "prenom"
    assert await a.commandes() == []  # rien n'est enregistré avant d'avoir tout


async def test_un_numero_refuse_est_demande_une_fois_puis_le_numero_affiche_est_repropose(commerce):
    """N° 44 (Evan, 23/11) : « Quel numéro je note ? » n'est dit qu'une fois par refus ; si la personne ne dicte rien, le code lui repropose le numéro qui
    s'affiche (le « déjà demandé » se lit au journal du dit, plus de drapeau). Une fois noté, rien ne revient."""
    a = await Appel(commerce).pret()
    await a.jusqu_a_la_relecture()
    assert (await a.finaliser(confirmer=True)).manque == "paiement"
    assert (await a.finaliser(moyen="carte")).manque == "confirmer_numero"
    moteur.repondre_au_numero_affiche(a.p, "refuse", a.appelant)
    r = await a.finaliser(moyen="carte", confirmer=True)
    assert (r.manque, r.suggestion) == ("telephone", "")  # C6 n° 10 (décision d'Evan 25/11 9 h 30) : le modèle demande le numéro, le code ne dit rien
    r = await a.finaliser(moyen="carte", confirmer=True)  # elle n'a rien dicté : la question n'est pas redite, le numéro affiché est reproposé
    assert r.manque == "confirmer_numero" and "Quel numéro je note" not in r.suggestion, (r.manque, r.suggestion)
    moteur.repondre_au_numero_affiche(a.p, "accepte", a.appelant)
    assert (await a.finaliser(moyen="carte", confirmer=True)).manque == "prenom"
    assert a.p["client"]["telephone"] == TEL


async def test_l_offre_en_plus_n_est_jamais_redemandee(commerce):
    a = await Appel(commerce).pret()
    assert (await a.finaliser()).manque == "vente_en_plus"
    await a.ajouter("tiramisu")  # il ajoute quelque chose : la commande change
    assert (await a.finaliser()).manque != "vente_en_plus"


async def test_l_offre_en_plus_eteinte_n_est_jamais_proposee(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    assert (await a.finaliser()).manque == "relecture"


# --------------------------------------------------------------------------- #
# La relecture en deux temps
# --------------------------------------------------------------------------- #


async def test_la_relecture_dit_tout_en_toutes_lettres_et_ne_sauve_rien(commerce):
    a = await Appel(commerce).pret()
    r = await a.jusqu_a_la_relecture()
    assert r.statut == "INCOMPLETE" and r.manque == "relecture" and r.faits["a_confirmer"] is True
    # C6 n° 3b (décision d'Evan 25/11 9 h 30) : la relecture rend des faits, le modèle la dit ; le code dira la phrase réglée du total. Lot 4 (M38, D49) : le règlement se demande ensuite
    assert r.suggestion == "" and [(l["nom"], l["quantite"]) for l in r.faits["lignes"]] == [("Regina Normale", 1), ("Coca-Cola", 1)], r
    assert "emporter" in r.faits["mode_dit"] and "moyens" not in r.faits
    assert r.faits["total"] == 1290 + 200
    assert await a.commandes() == []


async def test_un_oui_sans_relecture_relit_d_abord_et_n_enregistre_pas(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.confirmer()  # le modèle dit « confirmer » trop tôt
    assert r.manque == "relecture"
    assert await a.commandes() == []


async def test_le_oui_apres_la_relecture_enregistre_avec_le_total_de_la_carte(commerce):
    a = await Appel(commerce).pret()
    await a.jusqu_a_la_relecture()
    r = await a.confirmer()
    assert r.statut == "ENREGISTREE", r
    assert r.faits["total"] == 1490 and r.faits["numero_court"] == "C1"
    (commande,) = await a.commandes()
    assert (commande["total"], commande["statut"], commande["telephone"], commande["prenom"]) == (1490, "recue" if False else commande["statut"], TEL, "Alice")
    assert commande["cree_par"] == "agent" and commande["appel_id"] == "appel-final"
    assert len(a.prise.recues) == 1 and a.prise.recues[0]["total"] == 1490  # l'envoi est parti, une fois


async def test_apres_une_correction_seul_ce_qui_change_est_relu(commerce):
    a = await Appel(commerce).pret()
    premiere = await a.jusqu_a_la_relecture()
    await a.ajouter(A("tiramisu", supplements=["classic"]))
    r = await a.confirmer()  # le « oui » ne vaut plus : la commande a changé
    assert r.manque == "relecture" and await a.commandes() == []
    # C6 n° 4 (décision d'Evan 25/11 9 h 30) : pas toute la commande, seulement ce qui a changé, en faits
    assert "lignes" not in r.faits and any(c["geste"] == "ajoutee" and "iramisu" in c["nom"] for c in r.faits["ce_qui_a_change"]), r
    assert r.faits["total"] == premiere.faits["total"] + 490
    assert (await a.confirmer()).statut == "ENREGISTREE"


# test_la_relecture_en_deux_temps_eteinte_enregistre_au_premier_oui : supprimé au lot 4 (D49), une seule fin (M39, M40), le réglage n'est plus lu ; sens repris par partie_1/test_l04_cuisine.py::test_une_seule_relecture.


# --------------------------------------------------------------------------- #
# Le numéro de l'appelant, le second numéro
# --------------------------------------------------------------------------- #


# test_le_numero_affiche_n_est_ni_demande_ni_lu : réécrit au lot 4 (D49) : la relecture ne porte plus le numéro (M38, il se dit après le règlement, ``identifier``) ; la fin ne le lit pas
async def test_le_numero_affiche_n_est_pas_lu_dans_la_relecture(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.jusqu_a_la_relecture()
    # C6 (décision d'Evan 25/11 9 h 30) : la relecture n'a plus de phrase ; ses faits ne portent pas le numéro dicté
    assert r.suggestion == "" and "612345678" not in str(r.faits.get("lignes")) and "telephone" not in r.faits


async def test_un_numero_masque_est_demande_puis_pris(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret()
    r = await a.jusqu_a_la_relecture()
    assert "s'affiche" not in r.suggestion
    r = await a.confirmer()
    assert (r.statut, r.manque) == ("INCOMPLETE", "telephone")
    r = await a.confirmer(telephone="06 98 76 54 32")
    assert r.manque == "confirmer_numero_dicte", r  # DC10 : le numéro dicté relu, il attend son « oui »
    moteur.repondre_au_numero_dicte(a.p, "accepte")
    assert (await a.confirmer()).statut == "ENREGISTREE"
    assert (await a.commandes())[0]["telephone"] == "+33698765432"


async def test_un_numero_dicte_invalide_est_refuse(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.confirmer(telephone="12 34")
    assert (r.statut, r.manque) == ("ARGUMENT_INVALIDE", "telephone")


# test_le_second_numero_est_garde_avec_qui_et_pourquoi_et_joint_a_la_commande : supprimé au lot 4 (D49), la fiche du contrat (lot 2) n'a pas de case pour un second numéro ; consigné dans a-trancher.md.


# --------------------------------------------------------------------------- #
# Le règlement
# --------------------------------------------------------------------------- #


async def test_reglement_mixte_le_code_calcule_le_reste_et_la_monnaie(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret(A("regina", 2, "Normale"), "coca")  # 2780
    await a.jusqu_a_la_relecture()
    ok = await a.confirmer(moyen="titre_restaurant", part=20, moyen_reste="especes", rendu_sur=50)
    assert ok.statut == "ENREGISTREE" and ok.faits["monnaie"] == 5000 - 780
    assert "quarante-deux euros vingt" in ok.suggestion  # le rendu de monnaie dit à la confirmation (C11)
    paiement = a.prise.recues[0]["paiement"]
    assert [(m["moyen"], m["montant"]) for m in paiement["moyens"]] == [("titre_restaurant", 2000), ("especes", 780)]
    assert paiement["rendu_sur"] == 5000


async def test_un_moyen_non_accepte_est_refuse_avec_ceux_qui_le_sont(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.confirmer(moyen="cheque")
    assert r.statut == "MOYEN_NON_ACCEPTE" and set(r.faits["acceptes"]) == {"carte", "especes", "titre_restaurant"}
    assert "par carte" in r.suggestion


async def test_une_part_sans_le_reste_demande_le_reste(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.confirmer(moyen="titre_restaurant", part=10)
    assert (r.statut, r.manque) == ("INCOMPLETE", "paiement_reste") and r.faits["reste"] == 1490 - 1000


async def test_le_plafond_du_titre_restaurant_est_refuse_a_l_enregistrement(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret(A("regina", 3, "Normale"))  # 3870 > plafond 2500 en titres
    await a.jusqu_a_la_relecture()
    r = await a.confirmer(moyen="titre_restaurant")
    assert r.statut == "PLAFOND_TITRE_RESTAURANT" and r.faits["plafond"] == 2500
    assert await a.commandes() == []


async def test_un_billet_trop_petit_est_refuse(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.confirmer(moyen="especes", rendu_sur=10)
    assert (r.statut, r.manque) == ("ARGUMENT_INVALIDE", "paiement")


# --------------------------------------------------------------------------- #
# Doublon, consigne, allergie, fermeture
# --------------------------------------------------------------------------- #


async def test_un_second_oui_rend_deja_fait_et_la_prise_ne_recoit_qu_une_commande(commerce):
    a = await Appel(commerce).pret()
    await a.jusqu_a_la_relecture()
    premiere = await a.confirmer()
    seconde = await a.confirmer()
    assert premiere.statut == "ENREGISTREE" and seconde.statut == "DEJA_FAIT"
    assert seconde.faits["numero"] == premiere.faits["numero"]
    assert len(await a.commandes()) == 1 and len(a.prise.recues) == 1


async def test_la_consigne_est_gardee_sur_la_fiche_et_l_allergie_va_sur_la_commande(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    a.p["habitude"] = "toujours sans oignons"  # une habitude retenue (M41, retenir_une_habitude)
    assert (await a.confirmer()).statut == "ENREGISTREE"
    client = await commerce.c.fetchrow("SELECT consignes FROM mark.resto_client WHERE site_id = $1 AND telephone = $2", commerce.a, TEL)
    assert "toujours sans oignons" in str(client["consignes"])

    b = await Appel(commerce, vente_en_plus=False, affiche="+33699999999").pret(A("coca", 2))
    await b.jusqu_a_la_relecture()
    b.p["habitude"] = "allergie aux arachides"
    assert (await b.confirmer()).statut == "ENREGISTREE"
    fiche = await commerce.c.fetchrow("SELECT consignes FROM mark.resto_client WHERE site_id = $1 AND telephone = $2", commerce.a, "+33699999999")
    assert "arachides" not in str(fiche["consignes"])  # T-16 : jamais sur la fiche
    ligne = await commerce.c.fetchrow("SELECT note FROM mark.resto_commande WHERE site_id = $1 AND telephone = $2", commerce.a, "+33699999999")
    assert "arachides" in ligne["note"]


async def test_un_restaurant_qui_ferme_entre_temps_refuse_avec_la_raison(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    await commerce.c.execute("UPDATE mark.resto_reglage_type SET pause_jusqu_a = $2 WHERE site_id = $1 AND type = 'emporter'", commerce.a, JEUDI_MIDI.replace(hour=13))
    r = await a.confirmer()
    assert r.statut == "PAUSE_TYPE" and "pause" in r.suggestion
    assert await a.commandes() == []


async def test_un_article_qui_passe_en_rupture_avant_le_oui_refuse_sans_rien_enregistrer(commerce):
    from api.db.bases_clients.restauration_carte import poser_rupture

    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        await poser_rupture(commerce.c, commerce.a, "BOI-COCA-COLA-33-CL", False, None, "caisse")
    r = await a.confirmer()
    assert r.statut == "RUPTURE" and await a.commandes() == []


async def test_une_prise_sans_etape_acceptee_rend_transmise(commerce):
    from api.services.restauration.caisse.prises.fiches import TEST_SANS_ACCEPTEE

    a = await Appel(commerce, prise=PriseTest(capacites=TEST_SANS_ACCEPTEE), vente_en_plus=False).pret()
    a.source.capacites = TEST_SANS_ACCEPTEE
    await a.jusqu_a_la_relecture()
    r = await a.confirmer()
    assert r.statut == "TRANSMISE"  # jamais « acceptée » inventé


async def test_les_manques_des_lignes_ne_passent_pas_derriere_l_adresse(commerce):
    """Régression de l'audit du lot 2 : ordre imposé éteint et livraison sans zone, une commande sans ligne (ou avec une variante qui attend) ne part pas à la relecture."""

    a = Appel(commerce, ordre_impose=False)
    a.p["mode"] = "livraison"
    r = await moteur.finaliser(a.source, a.p, a.regles, a.appelant)
    assert r.manque == "articles", r
    from api.services.commande import etat_pour_le_modele as EM
    from api.services.commande.phrases_du_manque import Manque

    attend = {**panier.nouveau(), "mode": "livraison", "lignes": [{"n": 1, "quantite": 1, "code": "x", "attente": {"nom": "taille"}}]}
    assert EM.manque_des_lignes(attend) is Manque.VARIANTE and EM.manque_des_lignes({**attend, "lignes": []}) is Manque.ARTICLES
    assert EM.ce_qui_manque({**attend, "lignes": []}, {})[0] is Manque.ADRESSE_ET_COMMUNE  # l'état garde son ordre (l'adresse d'abord) ; la fin, non


async def test_une_quantite_redite_a_l_identique_ne_touche_pas_le_panier_donc_la_relecture_ne_repart_pas(commerce):
    """Lot 3, n° 8 : « mettez-en deux » quand il y en a déjà deux ne change rien : la relecture entendue vaut encore (le panier n'est pas « touché »)."""
    a = await Appel(commerce).pret(A("regina", 2, "Normale"))
    await a.jusqu_a_la_relecture()
    avant, version = a.p["etape"], a.p["version"]
    ligne = str(a.p["lignes"][0]["n"])
    await moteur.modifier(a.source, a.p, a.regles, ligne=ligne, quantite=2)
    assert a.p["etape"] == avant == "a_relire" and a.p["version"] == version and a.p["relecture"], "rien n'a changé : la relecture reste"
    await moteur.modifier(a.source, a.p, a.regles, ligne=ligne, quantite=3)
    assert a.p["etape"] == "en_cours" and a.p["relecture"] is None, "une vraie quantité change le panier : la relecture repart"
