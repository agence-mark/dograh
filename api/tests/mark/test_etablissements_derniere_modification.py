"""[.mark] Builder partie 2 (U2 bis, E56) : chaque fiche dit qui l'a modifiée en dernier et d'où (Dograh ou portail).

| Test | Ce qu'il prouve |
|---|---|
| portail | une écriture faite avec la clé de l'organisation et ``X-Mark-Auteur`` : origine « portail » et le nom donné |
| dograh | une écriture faite par un compte de l'équipe (session) : origine « dograh », jamais l'identifiant du compte |
| dernière | la dernière écriture gagne, fiche par fiche |
| sans base | pas de base rattachée : liste vide, rien d'inventé |
| lecture seule | la route ne porte aucune écriture et n'expose que id, origine, auteur, date |
"""

from __future__ import annotations

from api.db.bases_clients import connexion as schema
from api.routes.etablissements import _qui_et_d_ou
from api.tests.mark.test_agents_servis import (  # noqa: F401  (fixtures)
    _client,
    base_v4,
    smtp,
)
from api.tests.mark.test_base_client import _RedisFactice, base_essai  # noqa: F401
from api.tests.mark.test_ecritures_par_element import (  # noqa: F401
    RACINE,
    _garnir,
    _installer,
    _rediriger,
)


def test_l_auteur_du_journal_se_lit_en_origine_et_nom():
    assert _qui_et_d_ou("portail : Camille Dupont (dograh:7)") == ("portail", "Camille Dupont")
    assert _qui_et_d_ou("dograh:12") == ("dograh", None)
    assert _qui_et_d_ou("portail :") == ("portail", None)


async def test_le_portail_est_nomme_la_derniere_ecriture_gagne(base_v4, smtp, db_session, async_session):
    _user, _org, entetes = await _installer(db_session, async_session, base_v4)
    with _rediriger():
        async with _client() as client:
            await _garnir(client, entetes, db_session, _org)
            # RV2 : le remplissage en bloc passe par une session d'équipe ; ce sont ces écritures du portail (clé) qui nomment la dernière modification.
            for ident, nom in (("nord", "Nord"), ("sud", "Sud")):
                assert (await client.patch(f"{RACINE}/etablissements/{ident}", json={"nom": nom + " (portail)"}, headers=entetes)).status_code == 200
            lues = {m["id"]: m for m in (await client.get(f"{RACINE}/etablissements/dernieres-modifications", headers=entetes)).json()}
            assert lues["nord"]["origine"] == "portail" and lues["nord"]["auteur"] == "Camille Dupont"
            assert set(lues["nord"]) == {"id", "origine", "auteur", "le"}
            # Une écriture du compte lui-même, sans le nom du portail : Dograh, sans nom ni identifiant de compte.
            sans_nom = {k: v for k, v in entetes.items() if k != "X-Mark-Auteur"}
            r = await client.patch(f"{RACINE}/etablissements/nord", json={"nom": "Nord bis"}, headers=sans_nom)
            assert r.status_code == 200, r.text
            lues = {m["id"]: m for m in (await client.get(f"{RACINE}/etablissements/dernieres-modifications", headers=entetes)).json()}
            assert lues["nord"]["origine"] == "dograh" and lues["nord"]["auteur"] is None
            assert "dograh:" not in str(lues["nord"])
            # La fiche voisine n'a pas bougé : toujours le portail.
            assert lues["sud"]["origine"] == "portail"


async def test_sans_base_rattachee_la_liste_est_vide(db_session, async_session, base_v4, smtp):
    from api.db.bases_clients import connexion  # noqa: F401
    from api.tests.mark.test_agents_servis import _cle, _groupe_avec_capacites

    user, principal, _specialise = await _groupe_avec_capacites(db_session, async_session)
    cle = await _cle(db_session, principal.organization_id, user.id)
    async with _client() as client:
        r = await client.get(f"{RACINE}/etablissements/dernieres-modifications", headers={"X-API-Key": cle})
    assert r.status_code == 200 and r.json() == []
