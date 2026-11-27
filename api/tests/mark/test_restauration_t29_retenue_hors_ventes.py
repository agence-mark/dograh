"""[.mark] Plan final Partie 1, T29 (créé par 8b-1a, rangé aux reprises de 8b-1b) : une commande ``retenue`` (l'agent ; elle part à la fin de l'appel) n'est pas une vente
tant qu'elle n'est pas partie en caisse ; restée ``retenue`` (appel planté, filet abandonné après l'alerte), elle n'en est jamais une. Chiffres du restaurant seulement.

| Test | Ce qu'il prouve |
|---|---|
| purge | une ``retenue`` purgée n'entre ni dans le chiffre d'affaires, ni dans les frais, ni dans les remises du récapitulatif ; elle reste comptée parmi les commandes |
| remises de l'écran | une ``retenue`` ne compte ni une utilisation de la remise, ni son chiffre d'affaires |
| commandes planifiées | une ``retenue`` pour demain n'est pas « à venir » pour le restaurant, ni dans son chiffre d'affaires à venir |
"""

from __future__ import annotations

from datetime import timedelta

from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_commande import commandes_planifiees
from api.db.bases_clients.restauration_purge import purger
from api.db.bases_clients.restauration_remise_ecran import remises_pour_l_ecran
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce, enregistrer  # noqa: F401

AVEC_REMISE = {"remises": [{"ref": "DIX"}], "paiement": {"moyens": [{"moyen": "carte", "montant": 2142}]}}


async def _remise_dix(commerce) -> int:
    return await commerce.c.fetchval(
        "INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, effet, etat) VALUES ($1, 'DIX', 'Dix', 'pourcentage', '{\"pourcentage\": 10}', 'active') RETURNING id",
        commerce.a,
    )


async def _une_retenue_et_une_vente(commerce, **plus) -> None:
    """Une commande de l'agent (``retenue``) et la même écrite par le portail (``nouvelle``, envoyée tout de suite)."""
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        retenue = await enregistrer(commerce, brouillon(appel_id="agent", **plus))
        vente = await enregistrer(commerce, brouillon(appel_id="portail", cree_par="portail", **plus))
    assert retenue.statut == vente.statut == "ENREGISTREE", (retenue, vente)
    statuts = sorted(r["statut"] for r in await commerce.c.fetch("SELECT statut FROM mark.resto_commande WHERE site_id = $1", commerce.a))
    assert statuts == ["nouvelle", "retenue"], statuts


async def test_t29_une_retenue_purgee_n_entre_pas_dans_le_chiffre_d_affaires(commerce):  # noqa: F811
    await _remise_dix(commerce)
    await _une_retenue_et_une_vente(commerce, **AVEC_REMISE)
    c, a = commerce.c, commerce.a
    await c.execute("UPDATE mark.resto_commande SET cree_le = cree_le - interval '40 days' WHERE site_id = $1", a)
    assert (await purger(c, JEUDI_MIDI - timedelta(days=30)))["commandes"] == 2
    recap = await c.fetchrow(
        "SELECT sum(nb_commandes)::int AS nb, sum(chiffre_affaires)::int AS ca, sum(remises)::int AS remises FROM mark.resto_recap_jour WHERE site_id = $1", a)
    assert (recap["nb"], recap["ca"], recap["remises"]) == (2, 2142, 238), dict(recap)


async def test_t29_une_retenue_ne_compte_pas_dans_les_remises_de_l_ecran(commerce):  # noqa: F811
    remise = await _remise_dix(commerce)
    await _une_retenue_et_une_vente(commerce, **AVEC_REMISE)
    lignes = {x["id"]: x for x in await remises_pour_l_ecran(commerce.c, commerce.a)}
    assert (lignes[remise]["utilisations"], lignes[remise]["ca_centimes"]) == (1, 2142), lignes[remise]


async def test_t29_une_retenue_n_est_pas_une_commande_planifiee_a_venir(commerce):  # noqa: F811
    c, a = commerce.c, commerce.a
    demain = JEUDI_MIDI + timedelta(days=1)
    await c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = true, jours_a_l_avance = 2, delai_minimal = 60 WHERE site_id = $1 AND type = 'emporter'", a)
    await _une_retenue_et_une_vente(commerce, heure_voulue=demain)
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        releve = await commandes_planifiees(c, a, demain.replace(hour=0), demain.replace(hour=23))
    assert (releve["nombre"], releve["chiffre_affaires"]) == (1, 2380), releve
