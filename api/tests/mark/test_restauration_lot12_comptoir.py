"""[.mark] Module Restauration, lot 12 (compléments) : les réglages de l'écran branchés au comptoir.

Vraie base, rôle ``_ecriture``, heure fixée au jeudi 12 h. Le comptoir lit ce que l'écran « Réglages restaurant » écrit.

| Test | Ce qu'il prouve |
|---|---|
| numéro court | ``numero_mode`` : ``aucun`` garde le préfixe fixe, ``type`` donne E/L/S, ``moyen`` donne CB/ESP/TR et le préfixe mixte quand deux moyens règlent |
| titre-restaurant et alcool | un produit marqué alcool n'est pas payable en titre (refus ``PLAFOND_TITRE_RESTAURANT``, raison ``alcool``) ; réglage éteint : permis |
| titre-restaurant sans rendu | un billet seul sur un titre est refusé (``MOYEN_NON_ACCEPTE``) ; sur des espèces ou réglage éteint : permis |
| notes libres | éteint, la note dite à l'agent est refusée et rien n'est écrit ; allumé, elle passe |
| pause du téléphone | la pause de la caisse ferme le téléphone (T-05) ; décoché, plus |
| sources par objet | tenu ici : l'état de la caisse n'est plus lu ni appliqué, ses ruptures non plus ; un objet absent suit la caisse |
| fermeture exceptionnelle | un jour de fermeture : l'agent le dit, le lendemain rouvert |
"""

from __future__ import annotations

import json
from datetime import timedelta

from api.db.bases_clients.restauration_carte import etat_combine
from api.services.commande import moteur
from api.services.restauration.caisse import synchro_caisse
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import (  # noqa: F401
    brouillon,
    commerce,
    enregistrer,
)
from api.tests.mark.test_restauration_commande_finaliser import Appel


async def _regler(commerce, **colonnes):
    for cle, valeur in colonnes.items():
        await commerce.c.execute(f"UPDATE mark.resto_reglage SET {cle} = $2 WHERE site_id = $1", commerce.a, valeur)


def _paiement(*moyens, **plus):
    return {"moyens": [{"moyen": m, "montant": v} for m, v in moyens], **plus}


# --------------------------------------------------------------------------- #
# Numéro court
# --------------------------------------------------------------------------- #


async def test_le_numero_court_suit_le_mode_de_numero_et_le_prefixe_mixte(commerce):
    numero = lambda r: r.faits["numero_court"]  # noqa: E731
    assert numero(await enregistrer(commerce, brouillon(appel_id="n1"))) == "C1"  # aucun : le préfixe fixe
    await _regler(commerce, numero_mode="type")
    assert numero(await enregistrer(commerce, brouillon(appel_id="n2"))) == "E2"
    await _regler(commerce, numero_mode="moyen")
    assert numero(await enregistrer(commerce, brouillon(appel_id="n3"))) == "CB3"
    assert numero(await enregistrer(commerce, brouillon(appel_id="n4", paiement=_paiement(("especes", 2380))))) == "ESP4"
    assert numero(await enregistrer(commerce, brouillon(appel_id="n5", paiement=_paiement(("titre_restaurant", 1000), ("carte", 1380))))) == "MIX5"
    await _regler(commerce, prefixe_mixte="XM")
    assert numero(await enregistrer(commerce, brouillon(appel_id="n6", paiement=_paiement(("titre_restaurant", 1000), ("carte", 1380))))) == "XM6"
    # un règlement réparti sur deux moyens (une part payée, le reste au retrait) est aussi mixte
    reparti = brouillon(appel_id="n7", paiement={"moyens": [{"moyen": "carte", "montant": 1000}], "reste_par_moyen": {"especes": 1380}})
    assert numero(await enregistrer(commerce, reparti)) == "XM7"


# --------------------------------------------------------------------------- #
# Titre-restaurant
# --------------------------------------------------------------------------- #


async def _marquer_alcool(commerce, code: str):
    produit = await commerce.c.fetchval("SELECT produit_ref FROM mark.resto_declinaison WHERE code_caisse = $1", code)
    await commerce.c.execute(
        "INSERT INTO mark.resto_surcouche (site_id, objet, ref, alcool) VALUES ($1, 'produit', $2, true) "
        "ON CONFLICT (site_id, objet, ref) DO UPDATE SET alcool = true", commerce.a, produit,
    )


async def test_un_produit_alcool_n_est_pas_payable_en_titre_restaurant_sauf_reglage_eteint(commerce):
    await _marquer_alcool(commerce, "BOI-COCA-COLA-33-CL")  # 2 pizzas (2180) + la boisson (200) = 2380 ; la boisson sert d'alcool à l'essai
    r = await enregistrer(commerce, brouillon(appel_id="a1", paiement=_paiement(("titre_restaurant", 2380))))
    assert (r.statut, r.faits["raison"], r.faits["plafond"], r.faits["montant"]) == ("PLAFOND_TITRE_RESTAURANT", "alcool", 2180, 2380)
    # la part sans alcool en titre, le reste en carte : permis
    assert (await enregistrer(commerce, brouillon(appel_id="a2", paiement=_paiement(("titre_restaurant", 2180), ("carte", 200))))).statut == "ENREGISTREE"
    # réglage éteint : le titre paie tout
    await _regler(commerce, titre_alcool_exclu=False)
    assert (await enregistrer(commerce, brouillon(appel_id="a3", paiement=_paiement(("titre_restaurant", 2380))))).statut == "ENREGISTREE"
    # sans alcool dans la commande, rien ne change (réglage rallumé)
    await _regler(commerce, titre_alcool_exclu=True)
    sans = brouillon(appel_id="a4", lignes=[{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 2}], paiement=_paiement(("titre_restaurant", 2180)))
    assert (await enregistrer(commerce, sans)).statut == "ENREGISTREE"


async def test_pas_de_rendu_sur_un_titre_restaurant_sauf_reglage_eteint(commerce):
    seul = brouillon(appel_id="r1", paiement=_paiement(("titre_restaurant", 2380), rendu_sur=5000))
    r = await enregistrer(commerce, seul)
    assert (r.statut, r.faits["raison"]) == ("MOYEN_NON_ACCEPTE", "sans_rendu")
    # le billet sur des espèces : permis
    especes = brouillon(appel_id="r2", paiement=_paiement(("titre_restaurant", 1000), ("especes", 1380), rendu_sur=2000))
    assert (await enregistrer(commerce, especes)).statut == "ENREGISTREE"
    await _regler(commerce, titre_sans_rendu=False)
    assert (await enregistrer(commerce, brouillon(appel_id="r3", paiement=_paiement(("titre_restaurant", 2380), rendu_sur=5000)))).statut == "ENREGISTREE"


# --------------------------------------------------------------------------- #
# Notes libres
# --------------------------------------------------------------------------- #


async def test_une_note_libre_est_refusee_quand_le_reglage_est_eteint(commerce):
    await _regler(commerce, notes_libres=False)
    # lot 4 (D49) : la note de la commande est la case ``note_generale`` de la fiche, posée par ``moteur.noter_la_commande``
    from api.services.commande import reglages

    a = await Appel(commerce).pret()
    eteint = reglages.reglages_de_la_commande({"commande_notes_libres": False})
    r = moteur.noter_la_commande(a.p, eteint, "sans oignons")
    assert (r.statut, r.faits["raison"]) == ("HORS_CARTE", "notes_non_acceptees")
    assert a.p.get("note") is None and await a.commandes() == []
    # sans note, la commande avance ; allumé, la note passe
    assert (await a.finaliser()).manque in ("vente_en_plus", "relecture")
    assert moteur.noter_la_commande(a.p, reglages.reglages_de_la_commande({"commande_notes_libres": True}), "sans oignons") is None
    assert a.p["note"] == "sans oignons"


# --------------------------------------------------------------------------- #
# Pause du téléphone, sources, fermetures
# --------------------------------------------------------------------------- #


async def test_la_pause_de_la_caisse_ferme_le_telephone_sauf_si_decoche_ou_si_l_etat_est_tenu_ici(commerce):
    c, a = commerce.c, commerce.a
    await c.execute("INSERT INTO mark.resto_etat_caisse (site_id, mode) VALUES ($1, 'pause')", a)
    await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type) VALUES ($1, 'sur_place') ON CONFLICT DO NOTHING", a)
    e = await etat_combine(c, a, "emporter", JEUDI_MIDI)
    assert (e["ouvert"], e["raison"]) == (False, "caisse_pause")  # T-05 : par défaut, la pause de la caisse met le téléphone en pause
    await _regler(commerce, pause_caisse_pause_telephone=False)
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI))["ouvert"] is True
    await _regler(commerce, pause_caisse_pause_telephone=True, sources=json.dumps({"etat": "ici"}))
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI))["ouvert"] is True  # l'état est tenu ici : la pause de la caisse n'est plus lue
    await _regler(commerce, sources=json.dumps({"carte": "ici"}))
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI))["ouvert"] is False  # un autre objet tenu ici ne change rien à l'état


async def test_un_objet_tenu_ici_n_est_plus_lu_chez_la_caisse(commerce):
    c, a = commerce.c, commerce.a
    await _regler(commerce, sources=json.dumps({"etat": "ici", "ruptures": "ici"}))
    assert await synchro_caisse.appliquer_l_etat(c, 1, a, {"mode": "pause"}) is False
    assert await c.fetchval("SELECT count(*) FROM mark.resto_etat_caisse WHERE site_id = $1", a) == 0
    ruptures = [{"code_caisse": "BOI-COCA-COLA-33-CL", "disponible": False}]
    assert await synchro_caisse.appliquer_les_ruptures(c, 1, a, ruptures, complet=True) == 0
    assert await c.fetchval("SELECT count(*) FROM mark.resto_rupture WHERE site_id = $1", a) == 0
    # un objet absent suit la caisse : l'état est lu et appliqué
    await _regler(commerce, sources=json.dumps({"ruptures": "ici"}))
    assert await synchro_caisse.appliquer_l_etat(c, 1, a, {"mode": "pause"}) is True
    assert await c.fetchval("SELECT mode FROM mark.resto_etat_caisse WHERE site_id = $1", a) == "pause"
    await _regler(commerce, sources=json.dumps({}))
    assert await synchro_caisse.appliquer_les_ruptures(c, 1, a, ruptures, complet=True) == 1


async def test_un_jour_de_fermeture_exceptionnelle_l_agent_le_dit_et_le_lendemain_rouvre(commerce):
    c, a = commerce.c, commerce.a
    debut = JEUDI_MIDI.replace(hour=0, minute=0)
    await c.execute("INSERT INTO mark.fermeture (site_id, du, au, motif) VALUES ($1, $2, $3, 'Mariage')", a, debut, debut + timedelta(days=1))
    e = await etat_combine(c, a, "emporter", JEUDI_MIDI)
    assert (e["ouvert"], e["raison"]) == (False, "fermeture_exceptionnelle")
    assert (await etat_combine(c, a, "emporter", JEUDI_MIDI + timedelta(days=1)))["ouvert"] is True
    # l'agent dit la fermeture à l'appelant
    r = await enregistrer(commerce, brouillon(appel_id="f1"))
    assert r.statut != "ENREGISTREE"
