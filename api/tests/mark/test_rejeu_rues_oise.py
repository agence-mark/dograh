"""[.mark] Le filet des rues réelles de l'Oise : zéro sûre fausse, aucune sûre juste perdue.

Chantier correctifs-apres-banc-v4 (21/10/2026), sections 6.2 et 6.9 du plan. Rejeu du 21/10 sur
l'annuaire réel : 84 rues tirées au hasard (graine fixe) dans 7 communes de l'Oise, chacune dite
de 5 façons, plus 4 rues inventées par commune (28 cas, moins celles qui existent).

| Défaut | Mesure sur `2b7221dc` | Après |
|---|---|---|
| R1 (n° 384) : deux voies du même nom, types différents, le type dit exact ne tranche pas | 72/84 sûres justes, dite exacte | 84/84 |
| R2 = 6.2 (n° 381) : la clé phonétique seule fait une sûre (« allée des Chênes » -> « Rue des Champs », Creil) | 1 sûre fausse | 0 |
| R3 (n° 385) : « du Vieux Chemin de Meaux », dit sans type, ancré sur « chemin » -> « Rue de Meaux » sûre | 1 sûre fausse | 0 |

Comment une sûre est jugée :
- juste : la rue tirée ;
- « dite comme lue » (forme au type faux seulement) : le type faux dit désigne une AUTRE voie du
  même nom qui existe (« rue André Chenier » pour l'Allée, alors qu'une Rue André Chenier existe).
  R1 lit ce que l'appelant a dit ; c'est la règle du plan (6.9), comptée à part ;
- même nom, autre type (rue inventée seulement) : « allée des Chênes » lue « Avenue des Chênes »
  à Beauvais. Le module ne compare jamais le type (« rue de la République » est une avenue) ;
- tout le reste est une sûre FAUSSE.
"""

import collections
import random

import pytest

from api.services.communes.base import charger_base, normaliser
from api.services.voies import base as base_voies
from api.services.voies.analyse import A_CONFIRMER, SURE, analyser, sans_type

COMMUNES = {
    "60057": "Beauvais",
    "60175": "Creil",
    "60159": "Compiègne",
    "60612": "Senlis",
    "60157": "Clermont",
    "60463": "Nogent-sur-Oise",
    "60589": "Saint-Maximin",
}
TYPES_ECHANGES = {
    "rue": "avenue", "avenue": "rue", "allee": "rue", "impasse": "rue", "place": "rue",
    "chemin": "rue", "boulevard": "avenue", "route": "rue", "quai": "rue", "square": "rue",
    "cours": "rue",
}
ARTICLES = {"de", "du", "des", "la", "le", "les", "l", "d"}
INVENTEES = ["rue des Mimosas Bleus", "allée des Chênes", "rue du Général Truc", "impasse des Lilas Roses"]


@pytest.fixture(scope="module")
def rejeu():
    """Le rejeu du 21/10 (``lot1-rejeux/rues.py`` du plan), par la vraie lecture des rues."""
    base_voies.voies_de.cache_clear()
    communes = charger_base()

    def est_une_commune(mot: str) -> bool:
        return bool(communes.par_nom.get(mot))

    random.seed(7)
    comptes: collections.Counter = collections.Counter()
    fausses: list[str] = []
    for insee, nom in COMMUNES.items():
        voies = base_voies.voies_de(insee)
        rangs = [
            k for k, n in enumerate(voies.noms)
            if len(n.split()) >= 2 and normaliser(n.split()[0]) in TYPES_ECHANGES
        ]
        for k in random.sample(rangs, min(12, len(rangs))):
            officielle = voies.noms[k]
            mots = officielle.split()
            type_voie, reste = normaliser(mots[0]), " ".join(mots[1:])
            sans_article = " ".join(m for m in mots[1:] if normaliser(m) not in ARTICLES) or reste
            formes = {
                "exacte": f"J'habite au 12 {officielle}.",
                "type_faux": f"J'habite au 12 {TYPES_ECHANGES[type_voie]} {reste}.",
                "sans_type": f"J'habite au 12 {reste}.",
                "sans_article": f"C'est 12 {mots[0]} {sans_article}.",
                "minuscule_ville": f"12 {officielle.lower()} à {nom}",
            }
            for forme, phrase in formes.items():
                d = analyser(phrase, voies, nom, est_une_commune=est_une_commune)
                if d.statut != SURE:
                    proposee = d.statut == A_CONFIRMER and any(p.nom == officielle for p in d.propositions)
                    comptes[(forme, "proposée" if proposee else d.statut)] += 1
                elif d.retenue == officielle:
                    comptes[(forme, "sûre juste")] += 1
                elif (
                    forme == "type_faux"
                    and sans_type(normaliser(d.retenue)) == sans_type(normaliser(officielle))
                    and normaliser(d.retenue).split()[0] == TYPES_ECHANGES[type_voie]
                ):
                    comptes[(forme, "dite comme lue")] += 1
                else:
                    comptes[(forme, "SÛRE FAUSSE")] += 1
                    fausses.append(f"{nom}: « {phrase} » -> {d.retenue} (tirée : {officielle})")
        for inventee in INVENTEES:
            if inventee in voies.noms:
                continue
            d = analyser(f"J'habite au 4 {inventee}.", voies, nom, est_une_commune=est_une_commune)
            comptes[("inventée", "cas")] += 1
            if d.statut != SURE:
                continue
            if sans_type(normaliser(d.retenue)) == sans_type(normaliser(inventee)):
                comptes[("inventée", "même nom, autre type")] += 1
            else:
                fausses.append(f"{nom}: « {inventee} » (inventée) -> {d.retenue}")
    base_voies.voies_de.cache_clear()
    return comptes, fausses


def test_zero_sure_fausse(rejeu):
    _, fausses = rejeu
    assert fausses == []


def test_le_rejeu_lit_bien_ses_84_rues_et_28_inventees(rejeu):
    comptes, _ = rejeu
    for forme in ("exacte", "type_faux", "sans_type", "sans_article", "minuscule_ville"):
        assert sum(v for (f, _), v in comptes.items() if f == forme) == 84, forme
    assert comptes[("inventée", "cas")] == 28


def test_aucune_sure_juste_perdue_et_r1_tranche_par_le_type_dit(rejeu):
    """Base `2b7221dc` : 72 sûres justes par forme (71 sans type). Après : 84 quand le type
    dit est celui de la rue ; sans type, les homonymes restent à confirmer (12)."""
    comptes, _ = rejeu
    assert comptes[("exacte", "sûre juste")] == 84
    assert comptes[("sans_article", "sûre juste")] == 84
    assert comptes[("minuscule_ville", "sûre juste")] == 84
    assert comptes[("sans_type", "sûre juste")] >= 72
    assert comptes[("type_faux", "sûre juste")] >= 72


def _lire(phrase: str, insee: str, nom: str):
    base_voies.voies_de.cache_clear()
    return analyser(phrase, base_voies.voies_de(insee), nom)


def test_6_2_la_cle_phonetique_seule_ne_fait_pas_une_sure():
    """« chênes » et « champs » rendent tous deux « CHAN » : à confirmer, jamais sûre."""
    d = _lire("J'habite au 4 allée des Chênes.", "60175", "Creil")
    assert d.statut != SURE
    assert d.statut == A_CONFIRMER and d.propositions[0].nom == "Rue des Champs"


@pytest.mark.parametrize(
    ("phrase", "insee", "nom", "attendue"),
    [
        ("J'habite au 12 avenue Foche.", "60057", "Beauvais", "Avenue Foch"),
        ("J'habite au 4 impasse des Lila.", "60057", "Beauvais", "Rue des Lilas"),
        ("J'habite au 12 rue Foch.", "60057", "Beauvais", "Avenue Foch"),
    ],
)
def test_6_2_une_ressemblance_ecrite_ou_sonore_reste_sure(phrase, insee, nom, attendue):
    d = _lire(phrase, insee, nom)
    assert (d.statut, d.retenue) == (SURE, attendue)


def test_r1_le_type_dit_tranche_entre_deux_homonymes():
    d = _lire("J'habite au 12 Rue de la Préfecture.", "60057", "Beauvais")
    assert (d.statut, d.retenue) == (SURE, "Rue de la Préfecture")


@pytest.mark.parametrize(
    "phrase",
    ["J'habite au 12 de la Préfecture.", "J'habite au 12 avenue de la Préfecture."],
)
def test_r1_type_absent_ou_qui_ne_designe_aucune_reste_a_confirmer(phrase):
    d = _lire(phrase, "60057", "Beauvais")
    assert d.statut == A_CONFIRMER
    assert {p.nom for p in d.propositions[:2]} == {"Rue de la Préfecture", "Place de la Préfecture"}


def test_r3_un_type_dans_le_nom_n_ancre_pas_la_suite():
    d = _lire("J'habite au 12 du Vieux Chemin de Meaux.", "60612", "Senlis")
    assert (d.statut, d.retenue) == (SURE, "Rue du Vieux Chemin de Meaux")


def test_r3_sans_voie_de_ce_nom_rien_ne_change():
    """« au bout de la rue » : aucun nom de voie de Senlis ne contient « bout de la rue »."""
    d = _lire("J'habite au 12 au bout de la rue de Meaux.", "60612", "Senlis")
    assert (d.statut, d.retenue) == (SURE, "Rue de Meaux")
