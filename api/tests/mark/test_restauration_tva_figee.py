"""[.mark] Module Restauration, lot 26, M14 : le taux de TVA figé sur chaque ligne, sur les frais et sur les remises, et le récapitulatif ventilé par taux.

Les prix de la carte sont TTC (contrat comptoir-classeur). Taux en millièmes de pour cent (10 % = 10000), comme ``tva_par_mode`` de la carte.

| Test | Ce qu'il prouve |
|---|---|
| taux figés | chaque ligne porte le taux de son produit pour le mode, les frais et la remise celui de la plus grande part du panier ; la carte change après, la commande garde les siens |
| HT + TVA = TTC | ``resto_tva_par_jour`` : par taux, HT + TVA = TTC au centime, la somme des taux = le total des commandes |
| purge | après la purge des 30 jours, la ventilation est la même (récapitulatif par taux), sans doubler si rejouée |
| taux inconnu | une commande d'avant la migration (lignes sans taux) tombe dans le taux -1 : jamais un HT inventé |
"""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte
from api.db.bases_clients.restauration_commande import enregistrer_commande, taux_majoritaire
from api.db.bases_clients.restauration_purge import purger
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401  (fixture)

TEL = "+33612345678"
# 2 margheritas à 10,90 (10 %) + une Heineken à 4,00 (20 %) + 3,00 de frais - 10 % de remise sur 25,80
LIGNES = [{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 2}, {"code_caisse": "ALC-HEINEKEN-33-CL"}]


async def _livraison(commerce, appel="a1", quand=JEUDI_MIDI):
    await commerce.c.execute(
        "INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, effet, etat) VALUES ($1, 'DIX', 'Dix', 'pourcentage', '{\"pourcentage\": 10}', 'active') "
        "ON CONFLICT DO NOTHING", commerce.a,
    )
    with horloge.remplacer(commerce.base, quand):
        return await enregistrer_commande(
            commerce.c, commerce.a,
            {"mode": "livraison", "client": {"telephone": TEL, "prenom": "Alice"}, "lignes": copy.deepcopy(LIGNES), "appel_id": appel,
             "adresse": {"voie": "1 rue X", "commune": "Senlis"}, "zone_id": commerce.zones["Senlis"], "remises": [{"ref": "DIX"}],
             "paiement": {"moyens": [{"moyen": "carte", "montant": 2622}]}},
            "relu",
        )


async def _ventilation(c, site, jour_debut=None, jour_fin=None):
    jour_debut = jour_debut or (JEUDI_MIDI - timedelta(days=60)).date()
    jour_fin = jour_fin or (JEUDI_MIDI + timedelta(days=2)).date()
    return [dict(r) for r in await c.fetch("SELECT * FROM mark.resto_tva_par_jour($1, $2, $3)", site, jour_debut, jour_fin)]


async def test_les_taux_sont_figes_sur_les_lignes_les_frais_et_les_remises(commerce):
    r = await _livraison(commerce)
    assert r.statut == "ENREGISTREE" and r.faits["total"] == 2622, r
    c = commerce.c
    numero = r.faits["numero"]
    lignes = await c.fetch("SELECT code_caisse, taux_tva FROM mark.resto_commande_ligne WHERE numero = $1::uuid ORDER BY rang", numero)
    assert [(l["code_caisse"], l["taux_tva"]) for l in lignes] == [("PIZ-MARGHERITA-NORMALE", 10000), ("ALC-HEINEKEN-33-CL", 20000)]
    ligne = await c.fetchrow("SELECT taux_tva_frais, frais, remises FROM mark.resto_commande WHERE numero = $1::uuid", numero)
    assert (ligne["taux_tva_frais"], ligne["frais"]) == (10000, 300)
    import json
    remises = json.loads(ligne["remises"]) if isinstance(ligne["remises"], str) else ligne["remises"]
    assert [(x["montant"], x["taux_tva"]) for x in remises] == [(258, 10000)]
    # la carte change APRÈS : la pizza passe à 5,5 % ; la commande déjà prise garde son taux
    nouvelle = copy.deepcopy(CARTE)
    for p in nouvelle["produits"]:
        if p["id"] == "P-PIZZAS-TOMATE-MARGHE":
            p["tva_par_mode"] = {"sur_place": 5500, "emporter": 5500, "livraison": 5500}
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        await importer_carte(c, commerce.a, nouvelle, "caisse")
    assert await c.fetchval("SELECT taux_tva FROM mark.resto_commande_ligne WHERE numero = $1::uuid AND rang = 1", numero) == 10000


def test_le_taux_des_frais_est_celui_de_la_plus_grande_part_du_panier():
    ligne = lambda taux, prix, n=1: {"taux_tva": taux, "prix_unitaire": prix, "quantite": n}  # noqa: E731
    assert taux_majoritaire([ligne(10000, 1000, 2), ligne(20000, 400)]) == 10000
    assert taux_majoritaire([ligne(5500, 500), ligne(20000, 500)]) == 20000  # égalité : le plus haut
    assert taux_majoritaire([ligne(None, 500)]) is None
    assert taux_majoritaire([ligne(None, 900), ligne(10000, 100)]) == 10000  # le taux inconnu ne compte pas


async def test_ht_plus_tva_font_le_ttc_au_centime_par_taux(commerce):
    r = await _livraison(commerce)
    v = await _ventilation(commerce.c, commerce.a)
    par_taux = {x["taux"]: x for x in v}
    # 10 % : 2 x 10,90 + 3,00 de frais - 2,58 de remise = 22,22 ; 20 % : 4,00
    assert (par_taux[10000]["ttc"], par_taux[10000]["ht"], par_taux[10000]["tva"]) == (2222, 2020, 202)
    assert (par_taux[20000]["ttc"], par_taux[20000]["ht"], par_taux[20000]["tva"]) == (400, 333, 67)
    assert all(x["ht"] + x["tva"] == x["ttc"] for x in v)
    assert sum(x["ttc"] for x in v) == r.faits["total"]


async def test_une_commande_annulee_n_entre_pas_dans_la_ventilation(commerce):
    r = await _livraison(commerce)
    await commerce.c.execute("UPDATE mark.resto_commande SET statut = 'annulee' WHERE numero = $1::uuid", r.faits["numero"])
    assert await _ventilation(commerce.c, commerce.a) == []


async def test_la_ventilation_survit_a_la_purge_sans_doubler(commerce):
    c = commerce.c
    vieux = JEUDI_MIDI - timedelta(days=40)
    await _livraison(commerce, appel="vieux", quand=vieux)
    await _livraison(commerce, appel="recent", quand=JEUDI_MIDI - timedelta(days=2))
    avant = await _ventilation(c, commerce.a)
    assert len(avant) == 4 and sum(x["ttc"] for x in avant) == 2 * 2622
    bilan = await purger(c, JEUDI_MIDI - timedelta(days=30))
    assert bilan["commandes"] == 1
    assert await c.fetchval("SELECT count(*) FROM mark.resto_recap_jour_taux") == 2
    assert await _ventilation(c, commerce.a) == avant  # la même, un jour résumé et un jour détaillé
    await purger(c, JEUDI_MIDI - timedelta(days=30))
    assert await _ventilation(c, commerce.a) == avant  # rejouée : rien de plus


async def test_une_commande_sans_taux_est_dans_le_taux_inconnu(commerce):
    r = await _livraison(commerce)
    await commerce.c.execute("UPDATE mark.resto_commande_ligne SET taux_tva = NULL WHERE numero = $1::uuid", r.faits["numero"])
    await commerce.c.execute("UPDATE mark.resto_commande SET taux_tva_frais = NULL WHERE numero = $1::uuid", r.faits["numero"])
    v = await _ventilation(commerce.c, commerce.a)
    inconnu = next(x for x in v if x["taux"] == -1)
    assert (inconnu["ht"], inconnu["tva"]) == (None, None) and inconnu["ttc"] == 2180 + 400 + 300
    assert sum(x["ttc"] for x in v) == 2622
