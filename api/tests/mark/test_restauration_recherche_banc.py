"""[.mark] Module Restauration, lot 4 : le banc de dictées (trois mesures, zéro faux sûr) et le contrôle de publication.

| Test | Ce qu'il prouve |
|---|---|
| les trois mesures | bon, ambigu, faux sûr : chaque cas de la grille est classé comme il doit l'être |
| les bancs de départ | trois listes (carte d'essai de Casa Italia, marques d'appareils, carte fictive de sushis riche en homonymes) : ZÉRO faux sûr, et la grande majorité de bonnes réponses |
| le banc est éprouvé | un moteur volontairement trop confiant fait monter le faux sûr (cas rouge connu) : le banc le voit |
| banc tiré de la liste | les dictées que la liste fournit d'elle-même ne font aucun faux sûr, sur les trois listes ; un même nom porté deux fois est attendu ambigu |
| contrôle de publication | une carte qui crée un faux sûr est refusée, avec les dictées en cause ; une carte sûre passe ; le défaut est bloquant |
| par la vraie base | le contrôle se rejoue sur la carte d'un établissement ; une carte qui change devient refusée |
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_banc import (
    AMBIGU,
    INTROUVABLE,
    Dictee,
    charger_un_banc,
    controle_de_publication,
    dictees_synthetiques,
    mesurer,
)
from api.db.bases_clients.recherche_liste_moteur import Reglages, construire_index
from api.db.bases_clients.restauration_carte import importer_carte
from api.services.restauration.controle_liste import CODE_DU_DEFAUT, controler_la_carte, defaut_de_publication
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, resto  # noqa: F401

DOSSIER = Path(__file__).parent / "donnees" / "banc_dictees"
BANCS = sorted(DOSSIER.glob("*.json"))

LISTE = [Element("a", "Tiramisu", (), "Desserts"), Element("b", "Orangina", (), "Boissons"), Element("c", "Fanta Citron", (), "Boissons"), Element("d", "Fanta Orange", (), "Boissons")]


def test_chaque_cas_de_la_grille_est_classe_comme_il_doit_l_etre():
    index = construire_index(LISTE)
    cas = [
        Dictee("tiramisu", "a"),  # RETENU juste : bon
        Dictee("fanta", AMBIGU),  # AMBIGU attendu : bon
        Dictee("kebab", INTROUVABLE),  # INTROUVABLE attendu : bon
        Dictee("tiramisu", "b"),  # RETENU un autre : faux sûr
        Dictee("tiramisu", AMBIGU),  # RETENU alors qu'il fallait une question : faux sûr
        Dictee("tiramisu", INTROUVABLE),  # RETENU alors que rien n'était attendu : faux sûr
        Dictee("fanta", "c"),  # une question là où une réponse sûre était attendue : ambigu (coûte un tour)
        Dictee("kebab", "a"),  # introuvable alors qu'une réponse était attendue : un raté, pas un danger
        Dictee("fanta", INTROUVABLE),  # une question alors que rien n'était attendu : ambigu
    ]
    bilan = mesurer(index, cas)
    assert bilan.resume() == {"total": 9, "bon": 3, "ambigu": 2, "introuvable": 1, "faux_sur": 3}
    assert not bilan.sur and [f["attendu"] for f in bilan.faux_surs] == ["b", AMBIGU, INTROUVABLE]
    assert mesurer(index, cas[:3]).sur


@pytest.mark.parametrize("chemin", BANCS, ids=[b.stem for b in BANCS])
def test_les_bancs_de_depart_ont_zero_faux_sur_et_une_grande_majorite_de_bonnes_reponses(chemin):
    banc = charger_un_banc(chemin)
    bilan = mesurer(banc.index(), banc.dictees)
    assert bilan.faux_surs == [], bilan.faux_surs
    assert bilan.total >= 39 and bilan.bon / bilan.total >= 0.90, bilan.resume()
    assert {d.attendu for d in banc.dictees} >= {INTROUVABLE} and any(d.attendu not in (AMBIGU, INTROUVABLE) for d in banc.dictees)


def test_les_bancs_couvrent_les_trois_familles_de_cas():
    casa = charger_un_banc(DOSSIER / "casa-italia.json")
    dits = {d.dit: d for d in casa.dictees}
    # le cas du run 15503 de départ
    assert dits["une canette de Coca"].attendu == "P-BOISSONS-COCA-COLA" and dits["bouteille de Coca 33 cl"].attendu == "P-BOISSONS-COCA-COLA"
    assert {d.origine for d in casa.dictees} == {"formulation", "erreur de transcription", "homonyme ou nom partagé", "absent"}
    assert {b.stem for b in BANCS} >= {"casa-italia", "marques-d-appareils", "sushi-homonymes-fictif"}


def test_le_banc_est_eprouve_un_moteur_naif_qui_retient_toujours_le_plus_proche_fait_monter_le_faux_sur(monkeypatch):
    from rapidfuzz import process

    from api.db.bases_clients import recherche_liste_banc as module

    def naif(index, texte, reglages=Reglages(), *, exclus=frozenset()):
        noms = {e.element.id: e.element.libelle for e in index.entrees}
        _, _, ident = process.extractOne(texte, noms)
        return {"statut": "RETENU", "retenu": ident, "candidats": [], "options": {}, "question": None, "couche": "naif"}

    for chemin in BANCS:
        banc = charger_un_banc(chemin)
        assert mesurer(banc.index(), banc.dictees).sur  # le vrai moteur : zéro
        with monkeypatch.context() as m:
            m.setattr(module, "chercher_dans_l_index", naif)
            assert mesurer(banc.index(), banc.dictees).faux_sur >= 10, chemin.stem  # le banc VOIT le moteur naïf : « zéro » veut dire quelque chose
    banc = charger_un_banc(DOSSIER / "casa-italia.json")
    # un cas connu : la liste contient un nom que la dictée dit absente : retenue, donc comptée comme faux sûr
    index = construire_index([*banc.elements, Element("x", "Pesto Rosso", (), "Pizzas base crème")], banc.mots_de_categorie)
    assert mesurer(index, [Dictee("un pesto rosso", INTROUVABLE)]).faux_sur == 1


def test_le_banc_tire_de_la_liste_ne_fait_aucun_faux_sur_sur_les_trois_listes():
    for chemin in BANCS:
        banc = charger_un_banc(chemin)
        synth = dictees_synthetiques(banc.elements)
        assert len(synth) >= len(banc.elements), chemin.stem
        bilan = mesurer(banc.index(), synth)
        assert bilan.faux_surs == [], (chemin.stem, bilan.faux_surs[:3])
    deux = [Element("a", "Tiramisu"), Element("b", "Tiramisu"), Element("c", "Orangina")]
    attendus = {d.attendu for d in dictees_synthetiques(deux)}
    assert attendus == {AMBIGU, "c"}  # un même nom deux fois : jamais attendu comme sûr


def test_une_liste_qui_cree_un_faux_sur_est_refusee_avec_les_dictees_en_cause():
    dictees = [Dictee("un tiramisu", INTROUVABLE, "le tiramisu est retiré de la carte"), Dictee("une orangina", "b")]
    avant = construire_index(LISTE)
    assert controle_de_publication(avant, dictees[1:]).ok
    # la carte change : « Tiramisu fraise » remplace « Tiramisu » ; la dictée « le tiramisu n'existe plus » est retenue sur lui
    apres = construire_index([Element("e", "Tiramisu fraise", (), "Desserts"), *LISTE[1:]])
    controle = controle_de_publication(apres, dictees)
    assert not controle.ok and controle.bilan.faux_sur == 1 and "un tiramisu" in controle.raison and "1 faux sûr sur 2" in controle.raison
    defaut = defaut_de_publication(controle, "carte")
    assert defaut.code == CODE_DU_DEFAUT and defaut.gravite == "bloquant" and defaut.parametres["exemples"][0]["retenu"] == "e"
    assert defaut_de_publication(controle_de_publication(avant, dictees[1:])) is None


async def test_le_controle_se_rejoue_sur_la_carte_d_un_etablissement_et_refuse_une_carte_qui_derape(resto):  # noqa: F811
    c, a = resto.c, resto.a
    await importer_carte(c, a, CARTE, "caisse")
    dictees = [Dictee("une canette de coca", "P-BOISSONS-COCA-COLA"), Dictee("un kebab", INTROUVABLE)]
    assert (await controler_la_carte(c, a, dictees)).ok
    # un faux sûr créé par la carte : une dictée dit que le « tiramisu maison » n'existe pas, puis un produit de ce nom arrive
    dictees.append(Dictee("un tiramisu maison", INTROUVABLE))
    assert (await controler_la_carte(c, a, dictees)).ok
    await c.execute("UPDATE mark.resto_produit SET nom = 'Tiramisu maison' WHERE site_id = $1 AND ref = 'P-DESSERTS-TIRAMISU'", a)
    controle = await controler_la_carte(c, a, dictees)
    assert not controle.ok and controle.bilan.faux_surs[0]["dit"] == "un tiramisu maison"
    assert defaut_de_publication(controle).gravite == "bloquant"
