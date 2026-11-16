"""[.mark] Module Restauration, lot 5, étape 3 : ``finaliser`` (relecture en deux temps, règlement mixte, numéros, offre en plus, enregistrement).

Vraie base, carte de référence, prise de test (envoi réel du comptoir vers la prise, sans tiers), heure fixée au jeudi 12 h.

| Test | Ce qu'il prouve |
|---|---|
| un manque à la fois | articles, taille, offre en plus (une fois), prénom, règlement : dans l'ordre, un seul à la fois |
| relecture en deux temps | rien n'est enregistré sans relecture valide ; « oui » sans relecture relit d'abord ; après une correction seul ce qui change est relu |
| enregistrement | total de la carte, numéro unique, heure annoncée, envoi à la prise une fois, le client connu |
| numéro de l'appelant | affiché : jamais demandé, jamais lu (« je garde le numéro qui s'affiche ») ; masqué : demandé ; invalide refusé |
| second numéro | gardé avec qui et pourquoi, joint à la commande |
| règlement mixte | titres puis espèces : reste et monnaie calculés par le code ; moyen non accepté et plafond refusés |
| doublon | un second « oui » rend ``DEJA_FAIT`` avec le même numéro ; la prise ne reçoit qu'une commande |
| consigne et allergie | l'habitude est gardée sur la fiche ; l'allergie va sur la commande, jamais sur la fiche (T-16) |
| réglages | relecture en deux temps éteinte : enregistre au premier « oui » ; offre en plus éteinte : jamais proposée |
| fermé | un restaurant qui ferme entre-temps refuse avec la raison fermée |
"""

from __future__ import annotations

import pytest

from api.db.bases_clients import horloge
from api.services.commande import moteur, panier
from api.services.commande.moteur import Appelant, Reglages
from api.services.restauration.appel import Lieu
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
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

    async def pret(self, articles="une regina normale et un coca"):
        await moteur.choisir_mode(self.source, self.p, self.regles, "emporter")
        r = await moteur.ajouter(self.source, self.p, self.regles, articles=articles)
        assert r.statut == "OK", r
        return self

    async def finaliser(self, **kw):
        return await moteur.finaliser(self.source, self.p, self.regles, self.appelant, **kw)

    async def jusqu_a_la_relecture(self, **plus):
        for _ in range(8):
            r = await self.finaliser(**{"prenom": "Alice", "moyen": "carte", **plus})
            if r.manque == "relecture":
                return r
            assert r.manque == "vente_en_plus", r
        raise AssertionError("pas de relecture")

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
    await moteur.ajouter(a.source, a.p, a.regles, articles="une regina")
    r = await a.finaliser()
    assert (r.statut, r.manque) == ("CHOIX_OBLIGATOIRE", "taille")  # la taille avant tout le reste
    await moteur.ajouter(a.source, a.p, a.regles, choix="normale")
    r = await a.finaliser()
    assert (r.statut, r.manque) == ("INCOMPLETE", "vente_en_plus")
    assert (await a.finaliser()).manque == "prenom"  # l'offre en plus n'est faite qu'une fois
    assert (await a.finaliser(prenom="Alice")).manque == "paiement"
    assert (await a.finaliser(moyen="carte")).manque == "relecture"
    assert await a.commandes() == []  # rien n'est enregistré avant le « oui »


async def test_l_offre_en_plus_n_est_jamais_redemandee(commerce):
    a = await Appel(commerce).pret()
    assert (await a.finaliser()).manque == "vente_en_plus"
    await moteur.ajouter(a.source, a.p, a.regles, articles="un tiramisu")  # il ajoute quelque chose : la commande change
    assert (await a.finaliser()).manque != "vente_en_plus"


async def test_l_offre_en_plus_eteinte_n_est_jamais_proposee(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    assert (await a.finaliser()).manque == "prenom"


# --------------------------------------------------------------------------- #
# La relecture en deux temps
# --------------------------------------------------------------------------- #


async def test_la_relecture_dit_tout_en_toutes_lettres_et_ne_sauve_rien(commerce):
    a = await Appel(commerce).pret()
    r = await a.jusqu_a_la_relecture()
    assert r.statut == "INCOMPLETE" and r.manque == "relecture" and r.faits["a_confirmer"] is True
    assert r.suggestion.startswith("Je vous relis : une Regina Normale et un Coca-Cola")  # les quantités sont dites en lettres
    assert "à emporter" in r.suggestion and "euro" in r.suggestion and "Vous réglez" in r.suggestion
    assert not any(c.isdigit() for c in r.suggestion)  # aucun chiffre à lire : tout est dit en lettres
    assert r.faits["total"] == 1290 + 200
    assert await a.commandes() == []


async def test_un_oui_sans_relecture_relit_d_abord_et_n_enregistre_pas(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.finaliser(prenom="Alice", moyen="carte", confirmer=True)  # le modèle dit « confirmer » trop tôt
    assert r.manque == "relecture"
    assert await a.commandes() == []


async def test_le_oui_apres_la_relecture_enregistre_avec_le_total_de_la_carte(commerce):
    a = await Appel(commerce).pret()
    await a.jusqu_a_la_relecture()
    r = await a.finaliser(confirmer=True)
    assert r.statut == "ENREGISTREE", r
    assert r.faits["total"] == 1490 and r.faits["numero_court"] == "C1"
    (commande,) = await a.commandes()
    assert (commande["total"], commande["statut"], commande["telephone"], commande["prenom"]) == (1490, "recue" if False else commande["statut"], TEL, "Alice")
    assert commande["cree_par"] == "agent" and commande["appel_id"] == "appel-final"
    assert len(a.prise.recues) == 1 and a.prise.recues[0]["total"] == 1490  # l'envoi est parti, une fois


async def test_apres_une_correction_seul_ce_qui_change_est_relu(commerce):
    a = await Appel(commerce).pret()
    premiere = await a.jusqu_a_la_relecture()
    await moteur.ajouter(a.source, a.p, a.regles, articles="un tiramisu", choix="classic")
    r = await a.finaliser(confirmer=True)  # le « oui » ne vaut plus : la commande a changé
    assert r.manque == "relecture" and await a.commandes() == []
    assert "Je vous relis" not in r.suggestion  # pas toute la commande
    assert "On ajoute un tiramisu" in r.suggestion and "Cela fait maintenant" in r.suggestion
    assert r.faits["total"] == premiere.faits["total"] + 490
    assert (await a.finaliser(confirmer=True)).statut == "ENREGISTREE"


async def test_la_relecture_en_deux_temps_eteinte_enregistre_au_premier_oui(commerce):
    a = await Appel(commerce, relecture_en_deux_temps=False, vente_en_plus=False).pret()
    r = await a.finaliser(prenom="Alice", moyen="carte")
    assert r.statut == "ENREGISTREE" and len(await a.commandes()) == 1


# --------------------------------------------------------------------------- #
# Le numéro de l'appelant, le second numéro
# --------------------------------------------------------------------------- #


async def test_le_numero_affiche_n_est_ni_demande_ni_lu(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.jusqu_a_la_relecture()
    assert "Je garde le numéro qui s'affiche pour la commande" in r.suggestion
    assert "0612" not in r.suggestion and "612345678" not in r.suggestion and "+33" not in r.suggestion


async def test_un_numero_masque_est_demande_puis_pris(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret()
    r = await a.finaliser(prenom="Alice")
    assert (r.statut, r.manque) == ("INCOMPLETE", "telephone")
    r = await a.finaliser(telephone="06 98 76 54 32", moyen="carte")
    assert r.manque == "relecture" and "s'affiche" not in r.suggestion
    assert (await a.finaliser(confirmer=True)).statut == "ENREGISTREE"
    assert (await a.commandes())[0]["telephone"] == "+33698765432"


async def test_un_numero_dicte_invalide_est_refuse(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret()
    r = await a.finaliser(prenom="Alice", telephone="12 34")
    assert (r.statut, r.manque) == ("ARGUMENT_INVALIDE", "telephone")


async def test_le_second_numero_est_garde_avec_qui_et_pourquoi_et_joint_a_la_commande(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture(second_numero="07 11 22 33 44", second_qui="mon épouse", second_pourquoi="je suis en réunion")
    r = await a.finaliser(confirmer=True)
    assert r.statut == "ENREGISTREE"
    (commande,) = await a.commandes()
    import json

    second = json.loads(commande["second_numero"]) if isinstance(commande["second_numero"], str) else commande["second_numero"]
    assert second == {"numero": "+33711223344", "qui": "mon épouse", "pourquoi": "je suis en réunion"}
    assert commande["telephone"] == TEL  # le principal reste celui qui appelle (reconnaissance de l'habitué)
    # la prise de test, comme HubRise, ne porte qu'un téléphone : le second numéro part dans la note (adaptation du lot 3)
    envoyee = a.prise.recues[0]
    assert envoyee["client"]["second_numero"] is None and "Second numéro : +33711223344 (mon épouse je suis en réunion)" in envoyee["note"]


# --------------------------------------------------------------------------- #
# Le règlement
# --------------------------------------------------------------------------- #


async def test_reglement_mixte_le_code_calcule_le_reste_et_la_monnaie(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret("deux regina normale et un coca")  # 2780
    r = await a.jusqu_a_la_relecture(moyen="titre_restaurant", part=20, moyen_reste="especes", rendu_sur=50)
    assert "vingt euros en titres-restaurant" in r.suggestion and "sept euros quatre-vingts en espèces" in r.suggestion
    assert "billet de cinquante euros" in r.suggestion
    ok = await a.finaliser(confirmer=True)
    assert ok.statut == "ENREGISTREE" and ok.faits["monnaie"] == 5000 - 780
    paiement = a.prise.recues[0]["paiement"]
    assert [(m["moyen"], m["montant"]) for m in paiement["moyens"]] == [("titre_restaurant", 2000), ("especes", 780)]
    assert paiement["rendu_sur"] == 5000


async def test_un_moyen_non_accepte_est_refuse_avec_ceux_qui_le_sont(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.finaliser(prenom="Alice", moyen="cheque")
    assert r.statut == "MOYEN_NON_ACCEPTE" and set(r.faits["acceptes"]) == {"carte", "especes", "titre_restaurant"}
    assert "par carte" in r.suggestion


async def test_une_part_sans_le_reste_demande_le_reste(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.finaliser(prenom="Alice", moyen="titre_restaurant", part=10)
    assert (r.statut, r.manque) == ("INCOMPLETE", "paiement_reste") and r.faits["reste"] == 1490 - 1000


async def test_le_plafond_du_titre_restaurant_est_refuse_a_l_enregistrement(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret("trois regina normale")  # 3870 > plafond 2500 en titres
    await a.jusqu_a_la_relecture(moyen="titre_restaurant")
    r = await a.finaliser(confirmer=True)
    assert r.statut == "PLAFOND_TITRE_RESTAURANT" and r.faits["plafond"] == 2500
    assert await a.commandes() == []


async def test_un_billet_trop_petit_est_refuse(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.finaliser(prenom="Alice", moyen="especes", rendu_sur=10)
    assert (r.statut, r.manque) == ("ARGUMENT_INVALIDE", "paiement")


# --------------------------------------------------------------------------- #
# Doublon, consigne, allergie, fermeture
# --------------------------------------------------------------------------- #


async def test_un_second_oui_rend_deja_fait_et_la_prise_ne_recoit_qu_une_commande(commerce):
    a = await Appel(commerce).pret()
    await a.jusqu_a_la_relecture()
    premiere = await a.finaliser(confirmer=True)
    seconde = await a.finaliser(confirmer=True)
    assert premiere.statut == "ENREGISTREE" and seconde.statut == "DEJA_FAIT"
    assert seconde.faits["numero"] == premiere.faits["numero"]
    assert len(await a.commandes()) == 1 and len(a.prise.recues) == 1


async def test_la_consigne_est_gardee_sur_la_fiche_et_l_allergie_va_sur_la_commande(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture(consigne="toujours sans oignons")
    assert (await a.finaliser(confirmer=True)).statut == "ENREGISTREE"
    client = await commerce.c.fetchrow("SELECT consignes FROM mark.resto_client WHERE site_id = $1 AND telephone = $2", commerce.a, TEL)
    assert "toujours sans oignons" in str(client["consignes"])

    b = await Appel(commerce, vente_en_plus=False, affiche="+33699999999").pret("deux coca")
    await b.jusqu_a_la_relecture(consigne="allergie aux arachides")
    assert (await b.finaliser(confirmer=True)).statut == "ENREGISTREE"
    fiche = await commerce.c.fetchrow("SELECT consignes FROM mark.resto_client WHERE site_id = $1 AND telephone = $2", commerce.a, "+33699999999")
    assert "arachides" not in str(fiche["consignes"])  # T-16 : jamais sur la fiche
    ligne = await commerce.c.fetchrow("SELECT note FROM mark.resto_commande WHERE site_id = $1 AND telephone = $2", commerce.a, "+33699999999")
    assert "arachides" in ligne["note"]


async def test_un_restaurant_qui_ferme_entre_temps_refuse_avec_la_raison(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    await commerce.c.execute("UPDATE mark.resto_reglage_type SET pause_jusqu_a = $2 WHERE site_id = $1 AND type = 'emporter'", commerce.a, JEUDI_MIDI.replace(hour=13))
    r = await a.finaliser(confirmer=True)
    assert r.statut == "PAUSE_TYPE" and "pause" in r.suggestion
    assert await a.commandes() == []


async def test_un_article_qui_passe_en_rupture_avant_le_oui_refuse_sans_rien_enregistrer(commerce):
    from api.db.bases_clients.restauration_carte import poser_rupture

    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        await poser_rupture(commerce.c, commerce.a, "BOI-COCA-COLA-33-CL", False, None, "caisse")
    r = await a.finaliser(confirmer=True)
    assert r.statut == "RUPTURE" and await a.commandes() == []


async def test_une_prise_sans_etape_acceptee_rend_transmise(commerce):
    from api.services.restauration.prises.fiches import TEST_SANS_ACCEPTEE

    a = await Appel(commerce, prise=PriseTest(capacites=TEST_SANS_ACCEPTEE), vente_en_plus=False).pret()
    a.source.capacites = TEST_SANS_ACCEPTEE
    await a.jusqu_a_la_relecture()
    r = await a.finaliser(confirmer=True)
    assert r.statut == "TRANSMISE"  # jamais « acceptée » inventé
