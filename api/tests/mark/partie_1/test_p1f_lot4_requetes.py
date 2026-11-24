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
    assert len(lues) == 3 and [l["lignes"][0]["quantite"] for l in lues] == [1, 2, 3]
    assert len([q for q in c.requetes if "resto_commande_ligne" in q]) == 1
    assert await commandes_de_l_appel(commerce.c, commerce.a, "appel-inconnu") == []
