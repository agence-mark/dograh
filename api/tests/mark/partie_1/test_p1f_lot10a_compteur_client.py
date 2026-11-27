"""[.mark] Plan final Partie 1, lot 10 (A6) : le nombre de commandes d'un client suit les commandes vraiment tenues.

Scénario : la remise de fidélité « une commande sur deux » tient à la deuxième commande du client. Il la passe (rang 2, remise), puis la change d'un appel à l'autre (A9, avant qu'elle soit préparée) : la commande est REMPLACÉE
(l'ancienne annulée, la nouvelle enregistrée ; jamais en caisse pendant un appel, plan § 17). Avant, chaque enregistrement ajoutait 1 et l'annulation ne retirait rien : la remplaçante devenait la troisième et perdait sa remise ; une annulation
laissait aussi le client « fidèle » d'une commande qu'il n'a plus.

Depuis 8b-1a (E2, ``restauration_commande.py:1007`` ; plan final § 17 l.403 : la commande part en caisse une fois, à la fin de l'appel), une commande de l'agent naît
``retenue`` : elle compte pour le client dès le « oui » ; la fin de l'appel la fait passer ``retenue -> nouvelle`` sans la recompter, ou ``retenue -> annulee`` qui la
retire. Les tests jouent donc la fin de l'appel avant les gestes du portail ou de la caisse.
"""

from __future__ import annotations

from api.db.bases_clients.instantane import oublier
from api.db.bases_clients.restauration_commande import SORTIES_DU_COMPTE, TRANSITIONS, changer_statut
from api.db.bases_clients.restauration_remise import nombre_de_commandes_du_client, remises_applicables
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark import test_restauration_classeur_commande as _classeur
from api.tests.mark.test_restauration_classeur_commande import TEL, brouillon, enregistrer
from api.tests.mark.test_restauration_remises_classeur import PANIER, _poser

commerce = _classeur.commerce


async def _fin_de_l_appel(c, a, numero, vers="nouvelle"):
    """Le geste de la fin de l'appel (``caisse/envoi_a_la_fin``) : accordée, elle part (``nouvelle``) ; jamais réaccordée, elle est annulée."""
    assert (await changer_statut(c, a, numero, "retenue", vers, "agent")).statut == "OK"


async def _remise_de_fidelite(c, a):
    par_ref = {r["ref"]: r for r in await remises_applicables(c, a, PANIER, JEUDI_MIDI, {"telephone": TEL})}
    return par_ref["FIDE"]["montant"]


async def test_une_annulation_retire_la_commande_du_compte_du_client(commerce):
    c, a = commerce.c, commerce.a
    r = await enregistrer(commerce)
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1
    await _fin_de_l_appel(c, a, r.faits["numero"])
    assert (await changer_statut(c, a, r.faits["numero"], "nouvelle", "annulee", "portail")).statut == "OK"
    assert await nombre_de_commandes_du_client(c, a, TEL) == 0  # avant : 1, une commande que le client n'a plus


async def test_une_commande_remplacee_garde_le_rang_et_la_remise_de_la_commande_qu_elle_remplace(commerce):
    c, a = commerce.c, commerce.a
    await _poser(c, a, "FIDE", "fidelite", {"tous_les": 2}, {"pourcentage": 10}, {})
    await c.execute("INSERT INTO mark.resto_client (site_id, telephone, nb_commandes) VALUES ($1, $2, 1)", a, TEL)
    assert await _remise_de_fidelite(c, a) is not None  # sa deuxième commande : la remise tient
    premiere = await enregistrer(commerce, brouillon(appel_id="appel-a"), jeton="relu-a")
    assert await nombre_de_commandes_du_client(c, a, TEL) == 2
    await _fin_de_l_appel(c, a, premiere.faits["numero"])
    # changement d'un appel à l'autre : l'ancienne annulée, la nouvelle enregistrée à sa place
    assert (await changer_statut(c, a, premiere.faits["numero"], "nouvelle", "annulee", "agent")).statut == "OK"
    assert await _remise_de_fidelite(c, a) is not None  # avant : rang 3, la remise était perdue
    remplacante = await enregistrer(commerce, brouillon(appel_id="appel-a", note="autre version"), jeton="relu-b")
    assert await nombre_de_commandes_du_client(c, a, TEL) == 2  # une seule commande tenue de plus, jamais deux
    await _fin_de_l_appel(c, a, remplacante.faits["numero"])
    assert await nombre_de_commandes_du_client(c, a, TEL) == 2  # la fin de l'appel ne la recompte pas


async def test_une_commande_refusee_par_la_caisse_sort_du_compte_du_client(commerce):
    c, a = commerce.c, commerce.a
    r = await enregistrer(commerce)
    await _fin_de_l_appel(c, a, r.faits["numero"])
    assert (await changer_statut(c, a, r.faits["numero"], "nouvelle", "refusee", "agent")).statut == "OK"
    assert await nombre_de_commandes_du_client(c, a, TEL) == 0


async def test_une_commande_en_echec_reste_dans_le_compte_du_client(commerce):
    """Décision du coordinateur : une commande en échec (caisse injoignable) est une commande que le client a passée et que le restaurant doit encore saisir : elle RESTE dans son compte.
    Seules « annulée » et « refusée » la retirent. Son renvoi (echec -> envoyee) ne change rien."""
    c, a = commerce.c, commerce.a
    r = await enregistrer(commerce)
    await _fin_de_l_appel(c, a, r.faits["numero"])
    assert (await changer_statut(c, a, r.faits["numero"], "nouvelle", "echec", "agent")).statut == "OK"
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1  # avant : 0
    assert (await changer_statut(c, a, r.faits["numero"], "echec", "envoyee", "agent")).statut == "OK"
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1


async def test_un_statut_rejoue_ne_retire_rien_deux_fois(commerce):
    c, a = commerce.c, commerce.a
    premiere = await enregistrer(commerce, brouillon(appel_id="appel-1"), jeton="relu-1")
    seconde = await enregistrer(commerce, brouillon(appel_id="appel-2"), jeton="relu-2")
    for r in (premiere, seconde):
        await _fin_de_l_appel(c, a, r.faits["numero"])
    assert await nombre_de_commandes_du_client(c, a, TEL) == 2
    assert (await changer_statut(c, a, premiere.faits["numero"], "nouvelle", "annulee", "portail")).statut == "OK"
    assert (await changer_statut(c, a, premiere.faits["numero"], "nouvelle", "annulee", "portail")).statut == "DEJA_FAIT"  # le même geste rejoué
    assert (await changer_statut(c, a, premiere.faits["numero"], "envoyee", "annulee", "portail")).statut == "DEJA_FAIT"  # un autre départ, même arrivée
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1  # une seule fois retirée, l'autre commande reste tenue


async def test_oui_puis_raccroche_la_commande_compte_une_fois(commerce):
    """Client fidèle : « Oui, c'est bon. » puis il raccroche. Sa commande compte au « oui » (``retenue``) et la fin de l'appel ne la recompte pas ; une fin rejouée non plus."""
    c, a = commerce.c, commerce.a
    r = await enregistrer(commerce)
    assert await c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1::uuid", r.faits["numero"]) == "retenue"
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1
    await _fin_de_l_appel(c, a, r.faits["numero"])
    assert (await changer_statut(c, a, r.faits["numero"], "retenue", "nouvelle", "agent")).statut == "DEJA_FAIT"  # deux fins : un seul geste
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1


async def test_oui_puis_j_annule_la_commande_ne_compte_pas(commerce):
    """Client fidèle : « Oui. » puis « Finalement j'annule. » : la commande ``retenue`` est annulée ; elle ne compte pas, et rejouée ne retire rien de plus."""
    c, a = commerce.c, commerce.a
    await enregistrer(commerce, brouillon(appel_id="appel-avant"), jeton="relu-avant")  # une commande d'avant, tenue
    r = await enregistrer(commerce)
    assert await nombre_de_commandes_du_client(c, a, TEL) == 2
    await _fin_de_l_appel(c, a, r.faits["numero"], "annulee")
    assert (await changer_statut(c, a, r.faits["numero"], "retenue", "annulee", "agent")).statut == "DEJA_FAIT"
    assert (await changer_statut(c, a, r.faits["numero"], "retenue", "nouvelle", "agent")).statut == "INTERDIT"  # une annulée ne part jamais
    assert await nombre_de_commandes_du_client(c, a, TEL) == 1


async def test_pour_tout_pas_permis_le_compte_vaut_les_commandes_ni_annulees_ni_refusees(commerce):
    """Règle (reprise 7) : le compte vaut « les commandes ni annulées ni refusées ». Preuve pas à pas, donc pour toute suite de pas permis : pour CHAQUE pas permis de la table des
    transitions, le compte bouge de -1 exactement quand la commande passe d'un statut tenu à « annulée » ou « refusée », et de 0 dans tous les autres cas ; aucune sortie ne revient en arrière."""
    c, a = commerce.c, commerce.a
    assert SORTIES_DU_COMPTE == {"annulee", "refusee"}
    for de in SORTIES_DU_COMPTE:
        assert TRANSITIONS[de] <= SORTIES_DU_COMPTE  # une commande sortie ne redevient jamais tenue : sinon il faudrait ajouter 1
    r = await enregistrer(commerce)
    numero = r.faits["numero"]
    pas = [(de, vers) for de, suites in TRANSITIONS.items() for vers in sorted(suites)]
    assert len(pas) > 20
    for de, vers in pas:
        tenue_avant = 0 if de in SORTIES_DU_COMPTE else 1
        await c.execute("UPDATE mark.resto_commande SET statut = $2 WHERE numero = $1::uuid", numero, de)
        await c.execute("UPDATE mark.resto_client SET nb_commandes = $3 WHERE site_id = $1 AND telephone = $2", a, TEL, tenue_avant)
        oublier(c, ("nb_commandes_du_client", a, TEL))
        assert (await changer_statut(c, a, numero, de, vers, "portail")).statut == "OK", (de, vers)
        attendu = 0 if vers in SORTIES_DU_COMPTE else 1
        assert await nombre_de_commandes_du_client(c, a, TEL) == attendu, (de, vers)
