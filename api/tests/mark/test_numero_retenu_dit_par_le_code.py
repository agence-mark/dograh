"""[.mark] SA-34 (M78) : un numéro dicté puis corrigé est DIT PAR LE CODE tel que retenu (appel 2568 : le modèle relisait « cinquante-cinq » de mémoire
alors que le code avait « cinquante-six »). Mécanisme commun à la commande et à la réservation, aucun mot de métier."""

from __future__ import annotations

import pytest
from api.services.commande.resultat import Resultat, avec_numeros_retenus, numero_est_dit, phrase_du_numero_retenu
from api.services.mots_dits import numero_en_lettres
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import Appel
from api.tests.mark.test_restauration_reservation import salle  # noqa: F401

DIT_55 = "zéro six, vingt-deux, trente-trois, quarante-quatre, cinquante-cinq"
DIT_56 = "zéro six, vingt-deux, trente-trois, quarante-quatre, cinquante-six"


def test_un_numero_se_dit_par_paires_avec_son_zero():
    assert numero_en_lettres("+33622334456") == DIT_56
    assert numero_en_lettres("+33605060708") == "zéro six, zéro cinq, zéro six, zéro sept, zéro huit"
    assert numero_en_lettres("+33100000000").startswith("zéro un, zéro zéro")
    assert numero_en_lettres("+14155550123").startswith("plus ")  # un autre indicatif n'est jamais deviné


def test_le_numero_retenu_est_un_fait_la_phrase_est_celle_du_motif():
    # C6 n° 10 (décision d'Evan 25/11 9 h 30) : le résultat ne compose plus « Je note le … » ; la porte dit le motif réglé ``numero_retenu``
    r = avec_numeros_retenus(Resultat("INCOMPLETE", {}, "À quel nom ?", "prenom"), "+33622334456")
    assert r.suggestion == "À quel nom ?" and r.faits["numero_retenu_dit"] == DIT_56 and numero_est_dit(r.faits)
    assert phrase_du_numero_retenu(None, r.faits) == f"Je note le {DIT_56}."
    assert avec_numeros_retenus(Resultat("INCOMPLETE", {}, "x", "prenom"), None).faits == {}


async def test_un_numero_dicte_puis_corrige_est_dit_tel_que_retenu(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False, question_numero_dicte=None).pret("une regina normale")  # DC10 éteint : le numéro retenu est dit par ``numero_retenu`` (C6 n° 10)
    r = await a.finaliser(prenom="Alice", telephone="0622334455")
    assert r.faits["numero_retenu_dit"] == DIT_55
    r = await a.finaliser(telephone="0622334456")
    # C6 n° 10 (décision d'Evan 25/11 9 h 30) : le numéro est un fait, dit par le motif réglé avec une suite du code ; la relecture déjà dite n'en a pas : il attend la suivante
    assert "numero_retenu_dit" not in r.faits and a.p["client"]["telephone"] == "+33622334456", r
    r = await a.finaliser(confirmer=True, moyen="carte", prenom="Alice")
    assert r.statut == "ENREGISTREE" and r.faits["numero_retenu_dit"] == DIT_56, r  # dit avec la confirmation, tel que retenu, jamais de mémoire


async def test_dc10_allume_le_numero_n_est_dit_que_par_sa_question(commerce):
    """C6 n° 10 : DC10 allumé, le numéro dicté n'est pas dit à la relecture (``numero_retenu``) puis redit par la question ``numero_dicte_relu`` : la question seule le dit."""
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret("une regina normale")
    r = await a.finaliser(prenom="Alice", telephone="0622334456")
    assert "numero_retenu_dit" not in r.faits, r
    r = await a.finaliser(confirmer=True, moyen="carte", prenom="Alice")
    assert r.manque == "confirmer_numero_dicte" and DIT_56 in r.suggestion, r


async def test_un_numero_deja_dit_n_est_pas_redit(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False, question_numero_dicte=None).pret("une regina normale")  # DC10 éteint : le numéro retenu est dit par ``numero_retenu`` (C6 n° 10)
    await a.finaliser(prenom="Alice", telephone="0622334456")
    r = await a.finaliser(telephone="0622334456")
    assert "numero_retenu_dit" not in r.faits and "Je note" not in r.suggestion


async def test_le_numero_qui_s_affiche_n_est_jamais_relu(commerce):
    a = await Appel(commerce, affiche="+33622334456", vente_en_plus=False).pret("une regina normale")
    r = await a.finaliser(prenom="Alice")
    assert "numero_retenu_dit" not in r.faits and "Je note" not in (r.suggestion or "")
    r = await a.finaliser(telephone="0622334456")  # le même numéro, redonné : toujours pas relu
    assert "numero_retenu_dit" not in r.faits


async def test_un_numero_invalide_garde_son_refus(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret("une regina normale")
    r = await a.finaliser(prenom="Alice", telephone="12 34")
    assert r.statut == "ARGUMENT_INVALIDE" and "numero_retenu_dit" not in r.faits
    assert r.suggestion == "" and r.manque == "telephone" and r.faits["numero_illisible"] is True  # C7 B5 (Evan 25/11 8 h 45) : le modèle le redemande d'après le fait


# test_le_second_numero_retenu_est_dit_aussi : supprimé au lot 4 (D49), la fiche du contrat n'a plus de case pour un second numéro (a-trancher.md, SA-2 « second numéro sans case dans la fiche »)


# --- la réservation : même geste, même mécanisme -----------------------------------------------------------------


async def test_reservation_le_numero_corrige_est_dit_tel_que_retenu_et_l_affiche_jamais(salle):
    from api.tests.mark.test_restauration_reservation_outils import Appel as AppelResa

    a = AppelResa(salle, affiche=None)
    base = {"jour": "samedi", "heure": "20h", "personnes": 2, "prenom": "Alice"}
    r = await a.reserver(**base, telephone="0622334455")
    assert r.faits["numero_retenu_dit"] == DIT_55
    r = await a.reserver(telephone="0622334456")
    assert r.faits["numero_retenu_dit"] == DIT_56 and "cinquante-cinq" not in str(r.faits)  # C6 n° 10 (décision d'Evan 25/11 9 h 30)
    assert r.manque == "relecture"
    avec_affiche = AppelResa(salle)  # le numéro s'affiche : jamais relu
    r = await avec_affiche.reserver(**base)
    assert "numero_retenu_dit" not in r.faits


@pytest.mark.xfail(strict=True, reason="À trancher (a-trancher.md, nettoyeur passage 2) : ``reservation/action._retour`` n'existe plus ; la fiche de réservation ne dit par le code que la relecture et la confirmation (``textes_du_code``), pas la phrase du numéro retenu")
def test_les_gestes_qui_portent_un_numero_sont_dits_par_le_code():
    from api.services.reservation.porte import textes_du_code

    r = avec_numeros_retenus(Resultat("INCOMPLETE", {}, "À quel nom ?", "prenom"), "+33622334456")
    assert "avant" in textes_du_code({}, r, "reserver", None, False)
