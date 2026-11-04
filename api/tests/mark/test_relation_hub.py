"""[.mark] Builder partie 2, U3 septies (lot H1, E78) : le Hub « Relation clients », ses routes et le lien d'entrée signé.

Vraie application, vraie base de test, vrais rôles. Rien n'est envoyé (ni mail, ni SMS) : le Hub n'en envoie aucun.

| Test | Ce qu'il prouve |
|---|---|
| clé d'une autre organisation | une clé ne lit ni n'écrit les fils d'un autre client ; un fil étranger est un 404 |
| Hub fermé aux clés | chaque route du Hub renvoie 403 à une clé, même celle d'un client existant |
| portail fermé aux sessions | les routes du portail renvoient 403 à une session, même d'équipe |
| compte sans rôle | un compte sans rôle d'équipe n'entre pas au Hub |
| note interne | jamais rendue par le portail (fil, liste, dernier message) ; notes sur un client sans route côté portail |
| échange complet | demande de logiciel, réponse de .mark, états, suivi, lecture |
| lien d'entrée | rendu une fois, empreinte seule en base, usage unique, expiré refusé, autre client refusé sans consommer |
| permission du lien | un rôle sans ``clients.ouvrir_portail`` ne crée pas de lien |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from api.db import db_client
from api.services.relation import hub
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

R = "/api/v1/relation"
P = "/api/v1/organizations/relation"

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


async def _cle(db, organisation_id, user_id, auteur="portail : Paul"):
    _modele, brute = await db.create_api_key(organisation_id, "portail", created_by=user_id)
    return {"X-API-Key": brute, "X-Mark-Auteur": auteur}


async def _monde(db, suffixe):
    a = await creer_organisation(db, f"rel-a-{suffixe}")
    b = await creer_organisation(db, f"rel-b-{suffixe}")
    admin, jeton = await creer_compte(
        db, f"rel-admin-{suffixe}@example.com", role="Administrateur", organisations=[a, b]
    )
    return a, b, admin, jeton


async def test_une_cle_ne_touche_pas_les_fils_d_un_autre_client(db_session):
    a, b, admin, _ = await _monde(db_session, "iso")
    cle_a = await _cle(db_session, a, admin.id)
    cle_b = await _cle(db_session, b, admin.id)
    async with client_http() as c:
        cree = await c.post(f"{P}/fils", json={"sujet": "Showroom", "texte": "Bonjour"}, headers=cle_a)
        assert cree.status_code == 201, cree.text
        fil_id = cree.json()["id"]

        assert [f["id"] for f in (await c.get(f"{P}/fils", headers=cle_a)).json()] == [fil_id]
        assert (await c.get(f"{P}/fils", headers=cle_b)).json() == []
        assert (await c.get(f"{P}/fils/{fil_id}", headers=cle_b)).status_code == 404
        ecrit = await c.post(f"{P}/fils/{fil_id}/messages", json={"texte": "intrus"}, headers=cle_b)
        assert ecrit.status_code == 404
        # Le fil de A n'a reçu aucun message de B.
        assert len((await c.get(f"{P}/fils/{fil_id}", headers=cle_a)).json()["messages"]) == 1

    # En base : une organisation ne lit jamais les lignes d'une autre.
    assert await db_client.lire_fil_relation(b, fil_id, avec_internes=True) is None
    assert await db_client.ajouter_message_relation(b, fil_id, cote="client", auteur="x", texte="y") is None
    assert await db_client.modifier_fil_relation(b, fil_id, {"etat": "clos"}) is False
    assert await db_client.lister_fils_relation([b]) == []


async def test_le_hub_est_ferme_a_toute_cle_d_api(db_session):
    a, b, admin, _ = await _monde(db_session, "cle")
    async with client_http() as c:
        fil = (
            await c.post(f"{P}/fils", json={"sujet": "S", "texte": "T"}, headers=await _cle(db_session, a, admin.id))
        ).json()["id"]
        for cle in (await _cle(db_session, a, admin.id), await _cle(db_session, b, admin.id)):
            for methode, chemin, corps in (
                ("get", "/clients", None),
                ("get", "/file", None),
                ("get", "/fils", None),
                ("get", f"/clients/{a}/fils/{fil}", None),
                ("post", f"/clients/{a}/fils/{fil}/messages", {"cote": "mark", "texte": "x"}),
                ("patch", f"/clients/{a}/fils/{fil}", {"etat": "clos"}),
                ("get", f"/clients/{a}/notes", None),
                ("post", f"/clients/{a}/notes", {"texte": "x"}),
                ("get", "/avis", None),
                ("post", f"/clients/{a}/temoignages", {"texte": "x", "auteur": "y"}),
                ("get", "/entrees", None),
                ("post", f"/clients/{a}/entree", {}),
            ):
                reponse = await getattr(c, methode)(f"{R}{chemin}", headers=cle, **({"json": corps} if corps else {}))
                assert reponse.status_code == 403, (methode, chemin, reponse.status_code)


async def test_le_portail_est_ferme_aux_sessions_et_le_hub_aux_comptes_sans_role(db_session):
    a, _b, _admin, jeton = await _monde(db_session, "ses")
    _, jeton_simple = await creer_compte(db_session, "rel-simple@example.com", organisations=[a])
    async with client_http() as c:
        assert (await c.get(f"{P}/fils", headers=entetes(jeton, a))).status_code == 403
        assert (
            await c.post(f"{P}/entree/verifier", json={"jeton": "x" * 20}, headers=entetes(jeton, a))
        ).status_code == 403
        assert (await c.get(f"{R}/clients", headers=entetes(jeton_simple, a))).status_code == 403
        assert (await c.get(f"{R}/clients", headers=entetes(jeton))).status_code == 200


async def test_une_note_interne_ne_sort_jamais_par_l_api_du_client(db_session):
    a, _b, admin, jeton = await _monde(db_session, "note")
    cle = await _cle(db_session, a, admin.id)
    async with client_http() as c:
        fil = (await c.post(f"{P}/fils", json={"sujet": "SMS", "texte": "Pas de SMS le dimanche ?"}, headers=cle)).json()
        h = entetes(jeton)
        interne = await c.post(
            f"{R}/clients/{a}/fils/{fil['id']}/messages",
            json={"cote": "interne", "texte": "SECRET-INTERNE a regler avec Pierre"},
            headers=h,
        )
        assert interne.status_code == 201, interne.text
        note = await c.post(f"{R}/clients/{a}/notes", json={"texte": "SECRET-NOTE client prefere le matin"}, headers=h)
        assert note.status_code == 201
        await c.post(f"{R}/clients/{a}/temoignages", json={"texte": "SECRET-TEMOIGNAGE", "auteur": "P"}, headers=h)

        # Le Hub voit tout.
        vu = (await c.get(f"{R}/clients/{a}/fils/{fil['id']}", headers=h)).json()
        assert [m["cote"] for m in vu["messages"]] == ["client", "interne"]
        # Le portail ne voit que les deux côtés de l'échange, partout où un fil sort.
        sorties = [
            (await c.get(f"{P}/fils/{fil['id']}", headers=cle)).text,
            (await c.get(f"{P}/fils", headers=cle)).text,
        ]
        for brut in sorties:
            assert "SECRET" not in brut
        assert (await c.get(f"{P}/fils", headers=cle)).json()[0]["dernier"]["cote"] == "client"
        # Aucune route des notes ou des témoignages côté portail.
        for chemin in ("notes", "temoignages", "avis", "entrees"):
            assert (await c.get(f"{P}/{chemin}", headers=cle)).status_code in (404, 405)
        # Une note interne n'est pas une réponse : le fil reste à traiter.
        assert vu["etat"] == "nouveau"


async def test_echange_complet_demande_de_logiciel_et_suivi(db_session):
    a, _b, admin, jeton = await _monde(db_session, "ech")
    cle = await _cle(db_session, a, admin.id, auteur="portail : Martine Leroy")
    async with client_http() as c:
        h = entetes(jeton)
        refus = await c.post(f"{P}/fils", json={"sorte": "demande_logiciel", "sujet": "S", "texte": "T"}, headers=cle)
        assert refus.status_code == 422  # une demande de logiciel nomme le logiciel
        fil = (
            await c.post(
                f"{P}/fils",
                json={"sorte": "demande_logiciel", "sujet": "Gazoleen", "texte": "Poser les RDV", "logiciel": "Gazoleen"},
                headers=cle,
            )
        ).json()
        assert fil["etat_demande"] == "nouvelle" and fil["messages"][0]["auteur"] == "Martine Leroy"

        brut = await c.get(f"{R}/clients", headers=h)
        assert brut.status_code == 200, brut.text
        compte = {x["id"]: x for x in brut.json()}[a]
        assert compte["ouverts"] == 1 and compte["non_lus"] == 1 and compte["demandes_nouvelles"] == 1
        assert [f["id"] for f in (await c.get(f"{R}/file", headers=h)).json()] == [fil["id"]]

        # Lire le fil le marque lu ; se le donner à soi ; le proposer ; répondre.
        await c.get(f"{R}/clients/{a}/fils/{fil['id']}", headers=h)
        patch = await c.patch(
            f"{R}/clients/{a}/fils/{fil['id']}",
            json={"suivi": "moi", "etat_demande": "a_coder", "etat": "en_cours"},
            headers=h,
        )
        assert patch.status_code == 204
        await c.post(f"{R}/clients/{a}/fils/{fil['id']}/messages", json={"cote": "mark", "texte": "On le code."}, headers=h)

        mes = (await c.get(f"{R}/fils", params={"suivi": "moi"}, headers=h)).json()
        assert [f["id"] for f in mes] == [fil["id"]] and mes[0]["etat"] == "repondu"
        assert mes[0]["etat_demande"] == "a_coder" and mes[0]["lu_par_mark"] is True
        assert (await c.get(f"{R}/fils", params={"sorte": "demande_logiciel", "q": "gazol"}, headers=h)).json()
        assert (await c.get(f"{R}/fils", params={"q": "inexistant"}, headers=h)).json() == []

        # Le client lit la réponse ; sa relance remet le fil à traiter.
        lu = (await c.get(f"{P}/fils/{fil['id']}", headers=cle)).json()
        assert [m["cote"] for m in lu["messages"]] == ["client", "mark"] and lu["etat_demande"] == "a_coder"
        await c.post(f"{P}/fils/{fil['id']}/messages", json={"texte": "Merci"}, headers=cle)
        assert (await c.get(f"{R}/clients/{a}/fils/{fil['id']}", headers=h)).json()["etat"] == "nouveau"

        # Un client que le compte n'ouvre pas, ou qui n'existe pas : 404.
        assert (await c.get(f"{R}/clients/999999/notes", headers=h)).status_code == 404
        assert (await c.patch(f"{R}/clients/{a}/fils/{fil['id']}", json={}, headers=h)).status_code == 422


async def test_lien_d_entree_usage_unique_une_minute_pour_un_seul_client(db_session):
    a, b, admin, jeton = await _monde(db_session, "lien")
    cle_a = await _cle(db_session, a, admin.id)
    cle_b = await _cle(db_session, b, admin.id)
    async with client_http() as c:
        h = entetes(jeton)
        cree = await c.post(f"{R}/clients/{a}/entree", json={"motif": "Vérifier l'alerte"}, headers=h)
        assert cree.status_code == 201, cree.text
        lien = cree.json()
        assert lien["valable_secondes"] == 60

        # Seule l'empreinte est gardée : le jeton n'est écrit nulle part.
        async with db_client.async_session() as session:
            lignes = (await session.execute(text("SELECT empreinte_jeton FROM mark_relation_entrees"))).scalars().all()
        assert hub.empreinte(lien["jeton"]) in lignes and lien["jeton"] not in lignes

        # La clé d'un AUTRE client est refusée, et ne consomme pas le lien.
        assert (await c.post(f"{P}/entree/verifier", json={"jeton": lien["jeton"]}, headers=cle_b)).status_code == 403
        bon = await c.post(f"{P}/entree/verifier", json={"jeton": lien["jeton"]}, headers=cle_a)
        assert bon.status_code == 200 and bon.json()["motif"] == "Vérifier l'alerte"
        assert bon.json()["auteur"]
        # Rejoué : refusé.
        assert (await c.post(f"{P}/entree/verifier", json={"jeton": lien["jeton"]}, headers=cle_a)).status_code == 403
        # Inconnu : refusé de la même façon.
        assert (await c.post(f"{P}/entree/verifier", json={"jeton": "inconnu-" * 4}, headers=cle_a)).status_code == 403

        # Expiré : refusé.
        await db_client.creer_entree_relation(
            a, admin.id, "Evan", None, hub.empreinte("jeton-expire-000000"), datetime.now(UTC) - timedelta(seconds=1)
        )
        assert (
            await c.post(f"{P}/entree/verifier", json={"jeton": "jeton-expire-000000"}, headers=cle_a)
        ).status_code == 403

        # La trace est dans les entrées du Hub, avec l'usage.
        entrees = (await c.get(f"{R}/entrees", headers=h)).json()
        mienne = next(e for e in entrees if e["id"] == lien["entree_id"])
        assert mienne["utilise_le"] is not None and mienne["client"] == "rel-a-lien"
        assert "jeton" not in mienne


async def test_ouvrir_un_portail_exige_la_permission(db_session):
    a, _b, _admin, _ = await _monde(db_session, "perm")
    _, jeton_membre = await creer_compte(db_session, "rel-membre@example.com", role="Membre", organisations=[a])
    async with client_http() as c:
        refuse = await c.post(f"{R}/clients/{a}/entree", json={}, headers=entetes(jeton_membre, a))
        assert refuse.status_code == 403
        assert "clients.ouvrir_portail" in refuse.text


async def test_un_fil_se_confie_a_un_membre_de_l_equipe_et_pas_a_n_importe_qui(db_session):
    # V4 : la liste « Suivi par » de la maquette. La liste est réservée à l'équipe, sans adresse ; le suivi ne va qu'à un membre connu.
    a, _b, admin, jeton = await _monde(db_session, "suiv")
    collegue, jeton_collegue = await creer_compte(db_session, "rel-collegue@example.com", role="Membre", organisations=[a])
    _, jeton_simple = await creer_compte(db_session, "rel-sans-role@example.com", organisations=[a])
    cle = await _cle(db_session, a, admin.id)
    async with client_http() as c:
        h = entetes(jeton)
        fil = (await c.post(f"{P}/fils", json={"sujet": "SMS", "texte": "Un rappel ?"}, headers=cle)).json()
        membres = await c.get(f"{R}/membres", headers=h)
        assert membres.status_code == 200, membres.text
        assert {"id": collegue.id, "nom": "rel-collegue"} in membres.json()
        assert all(set(m) == {"id", "nom"} for m in membres.json())  # jamais une adresse
        assert "@" not in membres.text
        # Ni un compte sans rôle, ni le portail d'un client, ne lisent la liste.
        assert (await c.get(f"{R}/membres", headers=entetes(jeton_simple, a))).status_code == 403
        assert (await c.get(f"{R}/membres", headers=cle)).status_code == 403
        # Confier le suivi à un collègue : le fil dit qui, la liste « mes fils » de ce collègue le contient.
        ok = await c.patch(f"{R}/clients/{a}/fils/{fil['id']}", json={"suivi_par": collegue.id}, headers=h)
        assert ok.status_code == 204, ok.text
        vu = (await c.get(f"{R}/clients/{a}/fils/{fil['id']}", headers=h)).json()
        assert (vu["suivi_par"], vu["suivi_nom"]) == (collegue.id, "rel-collegue")
        assert [f["id"] for f in (await c.get(f"{R}/fils", params={"suivi": "moi"}, headers=entetes(jeton_collegue))).json()] == [fil["id"]]
        # Un identifiant qui n'est pas un membre de l'équipe : refusé, rien n'a bougé.
        inconnu = await c.patch(f"{R}/clients/{a}/fils/{fil['id']}", json={"suivi_par": 987654}, headers=h)
        assert inconnu.status_code == 422
        assert (await c.get(f"{R}/clients/{a}/fils/{fil['id']}", headers=h)).json()["suivi_par"] == collegue.id
        # Un client que le compte n'ouvre pas : 404, même avec un membre valide.
        assert (await c.patch(f"{R}/clients/999999/fils/{fil['id']}", json={"suivi_par": collegue.id}, headers=h)).status_code == 404
