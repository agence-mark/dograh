"""[.mark] Plan final Partie 1, lot 10 (A6) : le nombre de commandes d'un client suit les commandes vraiment tenues.

Scénario : la remise de fidélité « une commande sur deux » tient à la deuxième commande du client. Il la passe (rang 2, remise), puis demande « ajoutez un coca » : la commande est REMPLACÉE
(l'ancienne annulée, la nouvelle enregistrée). Avant, chaque enregistrement ajoutait 1 et l'annulation ne retirait rien : la remplaçante devenait la troisième et perdait sa remise ; une annulation
laissait aussi le client « fidèle » d'une commande qu'il n'a plus.
"""

from __future__ import annotations

from api.db.bases_clients.restauration_commande import changer_statut
from api.db.bases_clients.restauration_remise import nombre_de_commandes_du_client, remises_applicables
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark import test_restauration_classeur_commande as _classeur
from api.tests.mark.test_restauration_classeur_commande import TEL, brouillon, enregistrer
from api.tests.mark.test_restauration_remises_classeur import PANIER, _poser

commerce = _classeur.commerce


async def _remise_de_fidelite(c, a):
    par_ref = {r["ref"]: r for r in await remises_applicables(c, a, PANIER, JEUDI_MIDI, {"telephone": TEL})}
    return par_ref["FIDE"]["montant"]


async def test_une_annulation_retire_la_commande_du_compte_du_client(commerce):
    c, a = commerce.c, commerce.a
    r = await enregistrer(commerce)
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1
    assert (await changer_statut(c, a, r.faits["numero"], "nouvelle", "annulee", "portail")).statut == "OK"
    assert await nombre_de_commandes_du_client(c, a, TEL) == 0  # avant : 1, une commande que le client n'a plus


async def test_une_commande_remplacee_garde_le_rang_et_la_remise_de_la_commande_qu_elle_remplace(commerce):
    c, a = commerce.c, commerce.a
    await _poser(c, a, "FIDE", "fidelite", {"tous_les": 2}, {"pourcentage": 10}, {})
    await c.execute("INSERT INTO mark.resto_client (site_id, telephone, nb_commandes) VALUES ($1, $2, 1)", a, TEL)
    assert await _remise_de_fidelite(c, a) is not None  # sa deuxième commande : la remise tient
    premiere = await enregistrer(commerce, brouillon(appel_id="appel-a"), jeton="relu-a")
    assert await nombre_de_commandes_du_client(c, a, TEL) == 2
    # « ajoutez un coca » : l'ancienne annulée, la nouvelle enregistrée à sa place (changer_commande_enregistree)
    assert (await changer_statut(c, a, premiere.faits["numero"], "nouvelle", "annulee", "agent")).statut == "OK"
    assert await _remise_de_fidelite(c, a) is not None  # avant : rang 3, la remise était perdue
    await enregistrer(commerce, brouillon(appel_id="appel-a", note="avec un coca"), jeton="relu-b")
    assert await nombre_de_commandes_du_client(c, a, TEL) == 2  # une seule commande tenue de plus, jamais deux
