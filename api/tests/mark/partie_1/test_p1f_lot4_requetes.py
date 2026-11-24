"""[.mark] Plan final Partie 1, lot 4 (n° 135) : les commandes d'un appel se lisent en deux requêtes, jamais une par commande."""

from __future__ import annotations

from api.db.bases_clients.restauration_commande import enregistrer_commande
from api.db.bases_clients.restauration_salle_ecran import commandes_de_l_appel
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce  # noqa: F401


class _Compte:
    def __init__(self, c):
        self._c, self.requetes = c, []

    def __getattr__(self, nom):
        cible = getattr(self._c, nom)
        if nom != "fetch":
            return cible

        async def lire(requete, *args, **kw):
            self.requetes.append(requete)
            return await cible(requete, *args, **kw)

        return lire


async def test_les_commandes_d_un_appel_et_leurs_lignes_se_lisent_en_deux_requetes(commerce):
    for i in range(3):
        r = await enregistrer_commande(commerce.c, commerce.a, brouillon(appel_id="appel-x", lignes=[{"code_caisse": "BOI-COCA-COLA-33-CL", "quantite": i + 1}],
                                                                           paiement={"moyens": [{"moyen": "carte", "montant": 200 * (i + 1)}]}), f"relu-{i}")
        assert r.statut == "ENREGISTREE", r
    c = _Compte(commerce.c)
    lues = await commandes_de_l_appel(c, commerce.a, "appel-x")
    assert len(lues) == 3 and sorted(l["lignes"][0]["quantite"] for l in lues) == [1, 2, 3]
    assert len([q for q in c.requetes if "resto_commande_ligne" in q]) == 1
    assert await commandes_de_l_appel(commerce.c, commerce.a, "appel-inconnu") == []


def test_les_etapes_d_une_application_se_lisent_sans_la_cle_technique_des_identifiants():
    """N° 138 : une seule écriture de la clé ``_ids`` (rangement et lecture), plus de filtre « commence par _ » dans chaque lecteur."""
    from api.db.gabarits_client import CLE_DES_IDENTIFIANTS, avec_les_identifiants, etapes_de

    etapes = {"accueil": 12, "commande": 7}
    rangee = avec_les_identifiants(etapes)
    assert rangee == {"accueil": 12, "commande": 7, CLE_DES_IDENTIFIANTS: [7, 12]}
    assert etapes_de(rangee) == etapes


async def test_une_base_injoignable_repond_503_sans_jamais_montrer_son_texte_interne(monkeypatch):
    """N° 140 : le texte interne de ``BaseClientIndisponible`` ne part pas à l'écran, par aucun des routeurs du module (une seule ouverture de la base)."""
    import pytest
    from fastapi import HTTPException

    from api.db.bases_clients.connexion import BaseClientIndisponible
    from api.routes import restauration_base as RB

    async def nom(_organisation):
        return "base_x"

    async def connecter(_nom):
        raise BaseClientIndisponible("password authentication failed for user mark_ecriture at 10.0.0.5")

    monkeypatch.setattr(RB.rattachement, "nom_de_la_base", nom)
    monkeypatch.setattr(RB, "connecter", connecter)
    for ouvrir in (lambda: RB.connexion_de_l_organisation(1), lambda: RB.connexion_de_l_etablissement(1, 2)):
        with pytest.raises(HTTPException) as e:
            await ouvrir()
        assert e.value.status_code == 503 and e.value.detail == RB.BASE_INDISPONIBLE and "password" not in str(e.value.detail)


async def test_un_compteur_d_offre_en_panne_ne_defait_pas_la_commande_mais_se_voit_au_journal(commerce, monkeypatch, caplog):
    """N° 99 (zone de la couche d'accès) : l'erreur du compteur n'est plus avalée sans journal."""
    from api.db.bases_clients import restauration_commande as RC

    async def casse(*_a, **_k):
        raise RuntimeError("table absente")

    monkeypatch.setattr(RC, "noter_l_acceptation", casse)
    r = await RC.enregistrer_commande(commerce.c, commerce.a, brouillon(), "relu-1")
    assert r.statut == "ENREGISTREE"
    assert any("Offer acceptance not counted" in m.getMessage() and m.exc_info for m in caplog.records)
