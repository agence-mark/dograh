"""[.mark] Module Restauration, lot 3 : les prises, leurs fiches de capacités, leur prise de test.

| Test | Ce qu'il prouve |
|---|---|
| fiches | les quatre fiches existent, sont valides (listes fermées) et disent ce que ``fiches-capacites.md`` dit |
| chaque ``non`` | pour chaque fiche, chaque capacité à ``non`` fait REFUSER le geste (``GesteNonPermis``) ; chaque ``oui`` le laisse passer |
| fiche invalide | une valeur hors liste fermée est refusée à la construction |
"""

from __future__ import annotations

import dataclasses

import pytest

from api.services.restauration.prises import fiches
from api.services.restauration.prises.capacites import Capacites
from api.services.restauration.prises.prise import GesteNonPermis, Prise, prise_de


class PriseMuette(Prise):
    """Une prise dont tous les gestes réussissent à vide : seul le garde de la fiche est éprouvé."""

    def __init__(self, nom, capacites):
        super().__init__(capacites)
        self.nom = nom

    async def faire_annuler(self, numero): return "ok"
    async def faire_chercher(self, numero): return {}
    async def faire_lire_carte(self): return {}
    async def faire_envoyer_carte(self, carte): return None
    async def faire_lire_ruptures(self): return []
    async def faire_poser_rupture(self, code, disponible, fin): return None
    async def faire_lire_etat(self): return {}
    async def faire_poser_etat(self, etat): return None
    async def faire_lire_client(self, telephone): return {}
    async def faire_lire_remises(self): return []


# geste -> (appel, ce que la fiche doit dire pour qu'il passe)
GESTES = {
    "annuler une commande": (lambda p: p.annuler_commande("n"), lambda c: c.annulation),
    "chercher une commande par notre numéro": (lambda p: p.chercher_commande("n"), lambda c: c.anti_doublon == "chercher_avant_renvoi"),
    "lire la carte": (lambda p: p.lire_carte(), lambda c: c.carte == "lue"),
    "envoyer la carte": (lambda p: p.envoyer_carte({}), lambda c: c.carte == "envoyee"),
    "lire les ruptures": (lambda p: p.lire_ruptures(), lambda c: c.ruptures == "lues"),
    "poser une rupture": (lambda p: p.poser_rupture("X", False), lambda c: c.ruptures_posees_par_nous),
    "lire l'état du restaurant": (lambda p: p.lire_etat(), lambda c: c.etat_restaurant in ("lu", "lu_et_envoye")),
    "écrire l'état du restaurant": (lambda p: p.poser_etat({}), lambda c: c.etat_restaurant in ("envoye", "lu_et_envoye")),
    "lire un client": (lambda p: p.lire_client("+33600000000"), lambda c: c.clients_lus),
    "lire les remises": (lambda p: p.lire_remises(), lambda c: c.remises_lues),
}


def test_les_quatre_fiches_disent_ce_que_la_note_dit():
    assert set(fiches.FICHES) == {"hubrise", "imprimante", "portail", "test"}
    h, i, p = fiches.HUBRISE, fiches.IMPRIMANTE, fiches.PORTAIL
    assert (h.carte, h.carte_notifiee, h.ruptures, h.ruptures_posees_par_nous) == ("lue", True, "lues", True)
    assert h.etat_restaurant == "lu_et_envoye" and h.controle_avant_creation is False and h.annulation is True
    assert h.anti_doublon == "chercher_avant_renvoi" and h.notifications == "signees"
    assert "imbrication" not in h.represente and "second_telephone" not in h.represente
    assert {"retrait", "formules", "tva_par_mode", "allergenes", "plusieurs_paiements"} <= h.represente
    assert h.adresses_permises == ("https://api.hubrise.com/v1", "https://manager.hubrise.com")
    assert (i.carte, i.ruptures, i.etat_restaurant, i.annulation) == ("non", "non", "non", False)
    assert i.anti_doublon == "notre_table" and i.notifications == "interrogation" and i.adresses_permises == ()
    assert {"second_telephone", "plusieurs_paiements"} <= i.represente
    assert p.notifications == "aucune" and p.anti_doublon == "notre_table" and p.adresses_permises == ()
    assert p.represente == dataclasses.replace(p).represente and "imbrication" in p.represente
    assert "acceptee" in fiches.TEST.etapes and "acceptee" not in fiches.TEST_SANS_ACCEPTEE.etapes
    assert fiches.TEST.adresses_permises == ()


@pytest.mark.parametrize("nom", ["hubrise", "imprimante", "portail", "test"])
async def test_chaque_non_d_une_fiche_refuse_le_geste_et_chaque_oui_le_laisse_passer(nom):
    capacites = fiches.FICHES[nom]
    prise = PriseMuette(nom, capacites)
    for geste, (appel, permis) in GESTES.items():
        if permis(capacites):
            await appel(prise)  # passe : rien levé
        else:
            with pytest.raises(GesteNonPermis) as e:
                await appel(prise)
            assert e.value.geste == geste and e.value.prise == nom


async def test_le_garde_mord_une_capacite_changee_change_le_resultat():
    ouverte = dataclasses.replace(fiches.IMPRIMANTE, annulation=True)
    await PriseMuette("x", ouverte).annuler_commande("n")
    with pytest.raises(GesteNonPermis):
        await PriseMuette("x", fiches.IMPRIMANTE).annuler_commande("n")


def test_une_fiche_hors_des_listes_fermees_est_refusee():
    base = fiches.HUBRISE
    for champ, valeur in (("carte", "partout"), ("notifications", "fax"), ("etapes", frozenset({"cuite"})), ("represente", frozenset({"magie"}))):
        with pytest.raises(ValueError):
            dataclasses.replace(base, **{champ: valeur})
    with pytest.raises(ValueError):
        dataclasses.replace(base, ruptures="non", ruptures_posees_par_nous=True)
    assert isinstance(base, Capacites)


def test_la_prise_test_n_existe_que_posee_par_un_test():
    from api.services.restauration.prises.prise import PrisePasBranchee

    with pytest.raises(PrisePasBranchee):
        prise_de("test")
    with pytest.raises(PrisePasBranchee):
        prise_de("hubrise")  # fiche présente, prise branchée au lot 9
