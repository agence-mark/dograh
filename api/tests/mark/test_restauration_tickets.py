"""[.mark] Module Restauration, lot 10, étape 5 : la surveillance des tickets de l'imprimante (confirmation perdue, ticket non imprimé, imprimante muette).

| Test | Ce qu'il prouve |
|---|---|
| confirmation perdue | un ticket récupéré sans confirmation depuis plus de 3 minutes est remis en file (l'imprimante le revoit) ; au bout de 3 tentatives il n'est plus remis |
| alerte | un ticket libéré et non imprimé depuis le seuil (3 minutes, réglable) alerte UNE fois : ``ticket.erreur`` et un message aux personnes d'Équipe avec la commande jointe ; rejoué, rien de plus |
| imprimé, planifié | un ticket imprimé n'alerte jamais ; un ticket planifié pas encore libéré non plus |
| imprimante muette | un ticket qui attend et aucune interrogation : la liaison passe « en erreur » ; l'interrogation suivante la remet « ok » |
| cloisonnement | une autre base, donnée en dehors de la liste, n'est pas touchée ; le seuil d'un établissement ne change pas celui d'un autre |
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.db.bases_clients.horloge import horloge
from api.services.restauration import envoi_caisse as ec
from api.services.restauration import tickets as tk
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import _evenements
from api.tests.mark.test_restauration_envoi_caisse import Secours, _commande
from api.tests.mark.test_restauration_imprimante import _avec_imprimante


async def _ticket(base: str, org: int, etab: int) -> str:
    numero = await _commande(base, etab)
    await ec.envoyer_la_commande(org, base, etab, numero, secours=Secours())
    return numero


async def _vieillir_le_ticket(base: str, numero: str, minutes: int, **colonnes) -> None:
    c = await schema.connecter(base)
    try:
        passe = horloge(base).maintenant() - timedelta(minutes=minutes)
        await c.execute("UPDATE mark.resto_ticket SET maj_le = $2, cree_le = $2 WHERE numero = $1", uuid.UUID(numero), passe)
        for colonne, valeur in colonnes.items():
            await c.execute(f"UPDATE mark.resto_ticket SET {colonne} = $2 WHERE numero = $1", uuid.UUID(numero), valeur)
    finally:
        await c.close()


async def _ticket_en_base(base: str, etab: int, numero: str) -> dict:
    c = await schema.connecter(base)
    try:
        return await lia.le_ticket(c, etab, numero)
    finally:
        await c.close()


async def test_une_confirmation_perdue_remet_le_ticket_en_file_trois_fois_au_plus(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base)
    numero = await _ticket(cas.base_a, cas.a, etab)
    async with client_http() as c:
        await c.get(chemin, params={"type": "text/plain", "token": numero})  # l'imprimante l'a récupéré, la confirmation ne vient jamais
        assert (await _ticket_en_base(cas.base_a, etab, numero))["statut"] == "recupere"
        secours = Secours()
        # trop récent : rien
        assert (await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours))[str(cas.a)]["remis_en_file"] == 0
        await _vieillir_le_ticket(cas.base_a, numero, 5)
        assert (await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours))[str(cas.a)]["remis_en_file"] == 1
        assert (await c.post(chemin, json={"statusCode": "200 OK"})).json()["jobToken"] == numero  # l'imprimante le revoit
        # deux récupérations de plus restent sans confirmation : à la troisième tentative, il n'est plus remis
        for _ in range(2):
            await c.get(chemin, params={"type": "text/plain", "token": numero})
            await _vieillir_le_ticket(cas.base_a, numero, 5)
            await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours)
        assert (await _ticket_en_base(cas.base_a, etab, numero))["tentatives"] == 3
        assert (await _ticket_en_base(cas.base_a, etab, numero))["statut"] == "recupere"  # plus remis : une personne doit regarder (alerte)
        await _vieillir_le_ticket(cas.base_a, numero, 5)
        assert (await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours))[str(cas.a)]["remis_en_file"] == 0


async def test_un_ticket_non_imprime_alerte_une_seule_fois_avec_la_commande(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base)
    numero = await _ticket(cas.base_a, cas.a, etab)
    imprime = await _ticket(cas.base_a, cas.a, etab)
    planifie = await _ticket(cas.base_a, cas.a, etab)
    base = await schema.connecter(cas.base_a)
    try:
        await base.execute("UPDATE mark.resto_ticket SET statut = 'imprime' WHERE numero = $1", uuid.UUID(imprime))
        await base.execute("UPDATE mark.resto_ticket SET liberer_le = $2 WHERE numero = $1", uuid.UUID(planifie), horloge(cas.base_a).maintenant() + timedelta(hours=5))
    finally:
        await base.close()
    for n in (numero, imprime, planifie):
        await _vieillir_le_ticket(cas.base_a, n, 10, **({"liberer_le": horloge(cas.base_a).maintenant() + timedelta(hours=5)} if n == planifie else {}))
    secours = Secours()
    bilan = await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours)
    assert bilan[str(cas.a)]["alertes"] == 1 and len(secours.messages) == 1  # ni l'imprimé, ni le planifié pas encore libéré
    organisation, sujet, texte = secours.messages[0]
    assert organisation == cas.a and "C7" in sujet and "non imprimée" in sujet and "1 x Reine" in texte and "imprimante" in texte
    assert ("ticket.erreur", {"numero": numero, "code": "non_imprime"}) in await _evenements(cas.a, etab)
    await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours)
    assert len(secours.messages) == 1  # une seule fois


async def test_une_imprimante_muette_met_la_liaison_en_erreur_et_son_retour_la_remet_ok(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base)
    await _ticket(cas.base_a, cas.a, etab)  # un ticket attend, l'imprimante ne s'est jamais manifestée
    secours = Secours()
    await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours)
    base = await schema.connecter(cas.base_a)
    try:
        liaison = await lia.liaison(base, etab)
        assert (liaison["etat"], liaison["derniere_erreur"]) == ("erreur", "caisse_injoignable")
    finally:
        await base.close()
    async with client_http() as c:
        await c.post(chemin, json={"statusCode": "200 OK"})  # elle revient
    base = await schema.connecter(cas.base_a)
    try:
        assert (await lia.liaison(base, etab))["etat"] == "ok"
    finally:
        await base.close()
    assert ("caisse.liaison", {"etat": "ok"}) in await _evenements(cas.a, etab)


async def test_la_surveillance_ne_touche_que_les_bases_donnees_et_chaque_etablissement_a_son_seuil(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base)
    voisin = cas.sites_a[1]
    async with client_http() as c:
        autre = await c.post(f"/api/v1/restauration/etablissements/{voisin}/imprimante", json={}, headers={"X-API-Key": cas.cle_a})
    assert autre.status_code == 200
    numero, numero_voisin = await _ticket(cas.base_a, cas.a, etab), await _ticket(cas.base_a, cas.a, voisin)
    for n in (numero, numero_voisin):
        await _vieillir_le_ticket(cas.base_a, n, 10)
    base = await schema.connecter(cas.base_a)
    try:
        await base.execute("UPDATE mark.resto_liaison SET alerte_sans_reponse_min = 30 WHERE site_id = $1", voisin)  # le voisin tolère 30 minutes
    finally:
        await base.close()
    secours = Secours()
    bilan = await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours)
    assert bilan[str(cas.a)]["alertes"] == 1 and (await _ticket_en_base(cas.base_a, voisin, numero_voisin))["statut"] == "en_file"
    # une autre base, jamais donnée : rien n'y est touché
    chez_b = await _commande(cas.base_b, cas.sites_b[0])
    base = await schema.connecter(cas.base_b)
    try:
        await base.execute("INSERT INTO mark.resto_imprimante (site_id, jeton_empreinte) VALUES ($1, $2)", cas.sites_b[0], lia.empreinte("x"))
        await base.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'imprimante')", cas.sites_b[0])
        await lia.creer_le_ticket(base, cas.sites_b[0], chez_b)
    finally:
        await base.close()
    await _vieillir_le_ticket(cas.base_b, chez_b, 60)
    await tk.surveiller_les_tickets(None, bases=[(cas.a, cas.base_a)], secours=secours)
    assert (await _ticket_en_base(cas.base_b, cas.sites_b[0], chez_b))["statut"] == "en_file" and len(secours.messages) == 1
