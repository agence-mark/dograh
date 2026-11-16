"""[.mark] Module Restauration, lot 26 (M26) : la mise en mots commune, jamais « 25,00 euros », « 5 h 11 » ni « un Chaise ».

| Test | Ce qu'il prouve |
|---|---|
| montants | en toutes lettres, comme on les dit (« douze euros cinquante », « quatre-vingts euros ») |
| heures et durées | « dix-neuf heures trente », « minuit », « une heure trente » |
| noms accordés | genre et nombre : « une pizza moitié-moitié », « deux tiramisus », nom propre invariable |
| phrases écrites par une personne | les chiffres passent en lettres, un seul point final |
| phrases du classeur | le minimum de zone, l'annonce d'heure et la phrase d'une offre n'ont plus un seul chiffre à lire |
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from api.db.bases_clients import annonce_heure
from api.services import mots_dits as parole
from api.services.mots_dits import (
    chiffres_en_lettres, duree_en_lettres, genre_du_mot, heure_en_lettres, montant_en_lettres, nom_dit, phrase_nette, pluriel_du_mot,
)

PARIS = ZoneInfo("Europe/Paris")


def test_les_montants_se_disent_en_toutes_lettres():
    assert montant_en_lettres(2500) == "vingt-cinq euros"
    assert montant_en_lettres(1250) == "douze euros cinquante"
    assert montant_en_lettres(8000) == "quatre-vingts euros"
    assert montant_en_lettres(100) == "un euro"
    assert montant_en_lettres(50) == "cinquante centimes"
    assert montant_en_lettres(0) == "zéro euro"


def test_les_heures_et_les_durees_se_disent():
    assert heure_en_lettres(19, 30) == "dix-neuf heures trente"
    assert heure_en_lettres(5, 11) == "cinq heures onze"
    assert heure_en_lettres(0, 0) == "minuit"
    assert duree_en_lettres(30) == "trente minutes"
    assert duree_en_lettres(1) == "une minute"
    assert duree_en_lettres(60) == "une heure"
    assert duree_en_lettres(90) == "une heure trente"
    assert duree_en_lettres(125) == "deux heures cinq"


def test_une_heure_du_matin_s_accorde_au_feminin():
    assert heure_en_lettres(1, 0) == "une heure"
    assert heure_en_lettres(21, 1) == "vingt et une heures un"


def test_un_nom_s_accorde_en_genre_et_en_nombre():
    assert nom_dit("Pizza moitié-moitié", 1, genre="f", commun=True) == "une pizza moitié-moitié"
    assert nom_dit("Pizza moitié-moitié", 2, genre="f", commun=True) == "deux pizzas moitié-moitié"
    assert nom_dit("Tiramisu", 2, genre="m", commun=True) == "deux tiramisus"
    assert nom_dit("Regina Normale", 1, genre="f") == "une Regina Normale"
    assert nom_dit("Regina Normale", 3, genre="f") == "trois Regina Normale"  # un nom propre n'a pas de pluriel
    assert nom_dit("Coca-Cola 33 cl", 2, genre="m") == "deux Coca-Cola 33 cl"
    assert nom_dit("Joint", 1) == "un Joint"  # genre inconnu : « un », comme avant


def test_le_pluriel_et_le_genre_des_mots_pieges():
    assert [pluriel_du_mot(m) for m in ("joint", "vis", "bateau", "cheval", "moitié-moitié", "prix")] == ["joints", "vis", "bateaux", "chevaux", "moitié-moitié", "prix"]
    assert genre_du_mot("commande") == "f" and genre_du_mot("mot") == "m" and genre_du_mot("table") == "f"
    assert genre_du_mot("zèbre", {"zèbre": "m"}) == "m"


def test_les_chiffres_d_une_phrase_ecrite_passent_en_lettres():
    assert chiffres_en_lettres("2 joints offerts dès 25,00 € d'achat") == "deux joints offerts dès vingt-cinq euros d'achat"
    assert chiffres_en_lettres("12,50 euros") == "douze euros cinquante"
    assert chiffres_en_lettres("20 % ce soir") == "vingt pour cent ce soir"
    assert chiffres_en_lettres("dès 19 h 30") == "dès dix-neuf heures trente"
    assert chiffres_en_lettres("code A12 et réf 4B") == "code A12 et réf 4B"  # collé à des lettres : jamais touché


def test_un_seul_point_final():
    assert phrase_nette("En ce moment : une offre..") == "En ce moment : une offre."
    assert phrase_nette("Deux offres .  .") == "Deux offres ."


def test_l_annonce_d_heure_n_a_plus_un_chiffre_a_lire():
    quart = datetime(2026, 11, 12, 20, 15, tzinfo=PARIS)
    fixe = annonce_heure.Annonce("heure_fixe", quart, 30)
    tranche = annonce_heure.Annonce("tranche", quart, 30, quart, datetime(2026, 11, 12, 20, 30, tzinfo=PARIS))
    duree = annonce_heure.Annonce("duree", quart, 30)
    longue = annonce_heure.Annonce("duree", quart, 90)
    assert annonce_heure.dite(fixe, PARIS) == "à vingt heures quinze"
    assert annonce_heure.dite(tranche, PARIS) == "entre vingt heures quinze et vingt heures trente"
    assert annonce_heure.dite(duree, PARIS) == "dans trente minutes"
    assert annonce_heure.dite(longue, PARIS) == "dans une heure trente"
    for annonce in (fixe, tranche, duree, longue):
        assert not re.search(r"\d", annonce_heure.dite(annonce, PARIS))


def test_le_module_commun_ne_dit_aucun_mot_du_metier():
    corps = open(parole.__file__, encoding="utf-8").read()
    assert not re.search(r"restaura(?!tion)|pizza|burger|boisson|dessert|ticket|caisse|livraison|\bcarte\b|\bmenu|\bplat\b|\bsalle", corps, re.IGNORECASE)
