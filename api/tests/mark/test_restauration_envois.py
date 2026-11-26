"""[.mark] Module Restauration, lot 7, étape 8 : les envois après action (SMS), éteints par défaut, configurés à un seul endroit (``resto_envoi``).

Vraie base ; l'envoi de SMS du fork (``sms_restauration.envoyer_un_sms``) est remplacé par un enregistreur : jamais un tiers appelé.

| Test | Ce qu'il prouve |
|---|---|
| éteint par défaut | aucune ligne, ou une ligne ``actif`` faux : rien ne part, pour chaque déclencheur ; un déclencheur hors de la liste fermée non plus |
| commande enregistrée | allumé : le texte de l'établissement, ses trous remplis par le code (prénom, numéro court, heure), au numéro de la commande, une fois, à la fin de l'appel (§ 17) |
| réservation | enregistrée, modifiée, annulée : chacune son déclencheur, au numéro de la réservation ; éteint : rien |
| à la demande | ``envoyer_un_message`` : éteint, il dit qu'il ne peut pas ; allumé, il envoie la carte ou l'avis au numéro qui s'affiche, jamais un numéro dicté ; une seule fois |
| cloisonnement | l'envoi allumé d'un autre établissement ne part jamais pour celui-ci |
| panne | un envoi qui lève ne défait pas l'action : faux, dit au journal |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.commande import moteur, panier
from api.services.commande.moteur import Appelant
from api.services.restauration.envois_et_sms import envois
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.envois_et_sms import sms_restauration as sms_resto
from api.services.restauration.envois_et_sms.sms_restauration import Envoi
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.caisse.envoi_a_la_fin import envoyer_les_commandes_retenues
from api.services.restauration.source_reservation import SourceReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import TEL, Appel
from api.tests.mark.test_restauration_reservation import SAMEDI_20H, demande, salle  # noqa: F401


@pytest.fixture
def envoyes(monkeypatch):
    liste: list[dict] = []

    async def faux(organization_id, destinataire, modele, fiche, cle_unique):
        if cle_unique in {e["cle"] for e in liste}:
            return Envoi.DEJA_FAIT                         # la clé à usage unique : le même message n'est jamais envoyé deux fois
        liste.append({"org": organization_id, "a": destinataire, "modele": modele, "fiche": fiche, "cle": cle_unique})
        return Envoi.PARTI

    monkeypatch.setattr(sms_resto, "envoyer_un_sms", faux)

    async def emettre(*a, **k):
        return None

    monkeypatch.setattr(flux, "emettre", emettre)
    return liste


async def _allumer(c, etablissement, declencheur, texte="Merci {{prenom}} : {{numero_court}} à {{heure}}", actif=True):
    await c.execute("INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', $2, $3, $4)", etablissement, declencheur, texte, actif)


async def _finir_l_appel(boutique, a):
    """Lot 8b-1a (§ 17) : le SMS part à la fin de l'appel, avec la commande (jamais au « oui »)."""
    await envoyer_les_commandes_retenues(boutique.c, 7, boutique.base, a.appelant.appel_id, {panier.CLE: a.p})


async def _passer_la_commande(boutique, a):
    await a.jusqu_a_la_relecture()
    fait = await a.confirmer()
    assert fait.statut in ("ENREGISTREE", "TRANSMISE"), fait
    await _finir_l_appel(boutique, a)
    return fait


async def test_eteint_par_defaut_aucune_ligne_ou_ligne_eteinte_rien_ne_part(commerce, envoyes):  # noqa: F811
    c = commerce.c
    a = await Appel(commerce, vente_en_plus=False).pret("une regina normale")
    await _allumer(c, commerce.a, envois.COMMANDE_ENREGISTREE, actif=False)
    await _passer_la_commande(commerce, a)
    assert envoyes == []
    for declencheur in envois.DECLENCHEURS:
        assert await envois.envoyer_apres(c, 7, commerce.a, declencheur, TEL, {}, "x") is False
    # hors de la liste fermée, même une ligne allumée ne part pas
    await _allumer(c, commerce.a, "bonus", actif=True)
    assert await envois.envoyer_apres(c, 7, commerce.a, "bonus", TEL, {}, "y") is False and envoyes == []
    assert await c.fetchval("SELECT count(*) FROM mark.resto_envoi WHERE actif AND declencheur = 'bonus'") == 1


async def test_commande_enregistree_allume_le_texte_de_l_etablissement_trous_remplis_par_le_code(commerce, envoyes):  # noqa: F811
    await _allumer(commerce.c, commerce.a, envois.COMMANDE_ENREGISTREE)
    a = await Appel(commerce, vente_en_plus=False).pret("une regina normale")
    fait = await _passer_la_commande(commerce, a)
    assert len(envoyes) == 1
    e = envoyes[0]
    assert (e["org"], e["a"], e["modele"]) == (7, TEL, "Merci {{prenom}} : {{numero_court}} à {{heure}}")
    assert e["fiche"] == {"prenom": "Alice", "numero_court": fait.faits["numero_court"], "heure": "12:20", "quand": "12:20"}
    # rejouer la fin de l'appel n'envoie pas une seconde fois
    await _finir_l_appel(commerce, a)
    assert len(envoyes) == 1


async def test_reservation_chaque_geste_son_declencheur_au_numero_de_la_reservation(salle, envoyes, monkeypatch):  # noqa: F811
    from api.services.restauration import source_reservation

    monkeypatch.setattr(source_reservation.flux, "emettre", lambda *a, **k: _rien())
    c = salle.c
    source = SourceReservation(c, Lieu(salle.base, salle.a, 1))
    ctx = SimpleNamespace(organization_id=7)
    cree = await source.creer({"debut": SAMEDI_20H, "personnes": 2, "prenom": "Alice", "telephone": TEL, "appel_id": "a"})
    await source.apres_le_geste("reserver", cree, ctx)
    assert envoyes == []                                                       # éteint par défaut
    for declencheur in (envois.RESERVATION_ENREGISTREE, envois.RESERVATION_MODIFIEE, envois.RESERVATION_ANNULEE):
        await _allumer(c, salle.a, declencheur, f"{declencheur} {{{{prenom}}}} {{{{quand}}}}")
    cree2 = await source.creer({"debut": SAMEDI_20H, "personnes": 2, "prenom": "Bob", "telephone": "+33611111111", "appel_id": "b"})
    await source.apres_le_geste("reserver", cree2, ctx)
    modifie = await source.modifier(cree2.faits["numero"], {"personnes": 3})
    await source.apres_le_geste("modifier_reservation", modifie, ctx)
    annule = await source.annuler(cree2.faits["numero"])
    await source.apres_le_geste("annuler_reservation", annule, ctx)
    assert [(e["a"], e["modele"].split()[0]) for e in envoyes] == [
        ("+33611111111", envois.RESERVATION_ENREGISTREE), ("+33611111111", envois.RESERVATION_MODIFIEE), ("+33611111111", envois.RESERVATION_ANNULEE),
    ]
    assert envoyes[0]["fiche"]["prenom"] == "Bob" and "samedi quatorze novembre" in envoyes[0]["fiche"]["quand"]


async def _rien():
    return None


async def test_envoyer_un_message_eteint_dit_qu_il_ne_peut_pas_allume_envoie_au_numero_qui_s_affiche_une_fois(commerce, envoyes):  # noqa: F811
    a = Appel(commerce)
    r = await moteur.envoyer_un_message(a.source, a.p, a.regles, a.appelant, "carte", 7)
    # C7 B12 (T9, rouge depuis 9cd42f70, C7a) : « Je ne peux pas envoyer de message pour le moment. » est sorti du retour (décision d'Evan 25/11 8 h 45, le modèle parle) ;
    # le statut INDISPONIBLE le porte (table de traduction des secours, n° 71)
    assert (r.statut, r.suggestion) == ("INDISPONIBLE", "") and envoyes == []
    await _allumer(commerce.c, commerce.a, envois.CARTE, "La carte : https://exemple.fr/carte")
    r = await moteur.envoyer_un_message(a.source, a.p, a.regles, a.appelant, "Carte", 7)
    assert (r.statut, r.faits["envoye"]) == ("OK", True) and [e["a"] for e in envoyes] == [TEL]
    assert envoyes[0]["modele"] == "La carte : https://exemple.fr/carte"            # le texte de l'établissement, jamais celui du modèle
    assert (await moteur.envoyer_un_message(a.source, a.p, a.regles, a.appelant, "carte", 7)).statut == "DEJA_FAIT" and len(envoyes) == 1
    # l'avis n'est pas allumé : indisponible ; un numéro masqué : indisponible ; une demande hors liste : argument invalide
    assert (await moteur.envoyer_un_message(a.source, a.p, a.regles, a.appelant, "avis", 7)).statut == "INDISPONIBLE"
    assert (await moteur.envoyer_un_message(a.source, a.p, a.regles, Appelant(None, "x"), "carte", 7)).statut == "INDISPONIBLE"
    assert (await moteur.envoyer_un_message(a.source, a.p, a.regles, a.appelant, "promo", 7)).statut == "ARGUMENT_INVALIDE"
    assert (await moteur.envoyer_un_message(a.source, a.p, a.regles, a.appelant, None, 7)).statut == "ARGUMENT_INVALIDE"


async def test_l_envoi_allume_d_un_autre_etablissement_ne_part_jamais_ici(commerce, envoyes):  # noqa: F811
    await _allumer(commerce.c, commerce.b, envois.COMMANDE_ENREGISTREE)
    a = await Appel(commerce, vente_en_plus=False).pret("une regina normale")
    await _passer_la_commande(commerce, a)
    assert envoyes == []


async def test_un_envoi_qui_leve_ne_defait_pas_l_action(commerce, monkeypatch):  # noqa: F811
    async def casse(*a, **k):
        raise RuntimeError("compte absent")

    monkeypatch.setattr(sms_resto, "envoyer_un_sms", casse)
    await _allumer(commerce.c, commerce.a, envois.COMMANDE_ENREGISTREE)
    assert await envois.envoyer_apres(commerce.c, 7, commerce.a, envois.COMMANDE_ENREGISTREE, TEL, {}, "z") is False
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_envoi") == 1
