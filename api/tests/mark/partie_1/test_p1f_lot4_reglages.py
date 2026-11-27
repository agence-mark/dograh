"""[.mark] Plan final Partie 1, lot 4 (n° 132) : l'enregistrement d'une commande lit les réglages de l'établissement UNE fois.

Avant : ``enregistrer_commande`` lisait la ligne de réglage trois fois par trois chemins (module, moyens et plafond, préfixe du numéro), chacune à la base
quand l'enregistrement se joue hors d'un appel. Règle : ``reglages_de_l_enregistrement`` lit la ligne une fois, ``reglages_de_paiement`` en est un extrait.
"""

from __future__ import annotations

import sys

from api.db.bases_clients import restauration_reglage as REGLAGE
from api.db.bases_clients.restauration_commande import enregistrer_commande
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce  # noqa: F401


def _lu_par_l_enregistrement() -> bool:
    """Vrai si la requête en cours part de ``enregistrer_commande`` lui-même (directement, ou par une fonction de lecture des réglages qu'il appelle),
    pas d'un autre module (carte, créneau, annonce) qui lit ses propres réglages."""
    cadre, dessous = sys._getframe(2), None
    while cadre is not None:
        if cadre.f_code.co_name in ("enregistrer_commande", "_controler_la_commande"):  # 8b-1b : ses contrôles, partagés avec la réécriture
            return dessous is None or dessous in ("reglages_de_l_enregistrement", "reglages_du_module", "reglages_de_paiement", "ligne_de_reglage")
        dessous, cadre = cadre.f_code.co_name, cadre.f_back
    return False


class _Compteur:
    """Une connexion qui compte les lectures de la ligne de réglage faites par l'enregistrement."""

    def __init__(self, c):
        self._c = c
        self.lectures_des_reglages = 0

    def __getattr__(self, nom):
        cible = getattr(self._c, nom)
        if nom not in ("fetch", "fetchrow", "fetchval"):
            return cible

        async def lire(requete, *args, **kw):
            if "FROM mark.resto_reglage WHERE" in requete and _lu_par_l_enregistrement():
                self.lectures_des_reglages += 1
            return await cible(requete, *args, **kw)

        return lire


async def test_l_enregistrement_lit_la_ligne_de_reglage_une_seule_fois(commerce):
    c = _Compteur(commerce.c)
    r = await enregistrer_commande(c, commerce.a, brouillon(), "relu-1")
    assert r.statut == "ENREGISTREE", r
    assert c.lectures_des_reglages == 1


async def test_les_moyens_et_le_plafond_viennent_de_la_meme_lecture_que_le_module(commerce):
    tout = await REGLAGE.reglages_de_l_enregistrement(commerce.c, commerce.a)
    assert await REGLAGE.reglages_de_paiement(commerce.c, commerce.a) == {
        cle: tout[cle] for cle in ("moyens_paiement", "plafond_titre", "titre_alcool_exclu", "titre_sans_rendu", "notes_libres")}
    assert tout["plafond_titre"] == 2500 and tout["prefixe_numero_court"] == "C"
    assert tout["module"] == await REGLAGE.reglages_du_module(commerce.c, commerce.a)
