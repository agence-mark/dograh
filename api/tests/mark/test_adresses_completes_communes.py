"""[.mark] Les adresses complètes « numéro, rue, code, ville » : la commune ET la rue sûres, rien d'autre.

Chantier correctifs-apres-banc-v4 (21/10/2026), section 6.8 du plan (C1 à C5). Défauts anciens,
jamais couverts par le filet des 687 phrases (``test_corpus_communes_zero_perte.py``), rejoués par
la vraie entrée (``analyser_message``) le 21/10 :

| # | Défaut | Rejoué sur `2b7221dc` | Cause trouvée sur la trace |
|---|---|---|---|
| C1 (n° 383) | « 12 avenue Foch, 60000 Beauvais » | « 60000 » à confirmer (Beauvais ou Allonne) | le mot à trois mots d'un type de voie est pris pour la rue, même avec le code postal entre les deux |
| C1 bis | « 12 Rue du Général de Gaulle, 60180 Nogent-sur-Oise » | « Gaulle » proposée (Gauville) | le dernier mot de la rue, collé au code, est ancré par le code |
| C2 (n° 225) | « Longueau dans l'Oise » | Longueau (Somme) sûre | le département dit ne retient aucune commune qu'il porte |
| C3 (n° 225) | « Maxence dans l'Oise » | Maxent (Ille-et-Vilaine) | un morceau de nom composé ne fait pas candidate la commune du département |
| C4 (n° 209) | « 5 rue du vieux moulin pont saint maxence » | rien | la commune collée à la rue n'a ni amorce ni code |
| C5 (n° 282) | « soixante cinq cent cinquante vernayon à la » | Vernon (Eure) sûre | une commune qui ne porte aucune lecture du code dit, quand une commune du code ressemble aux mots |

Le filet : 7 communes de l'Oise du rejeu et 5 hors Oise, trois tournures chacune (virgule, tout en
minuscules sans ponctuation, « à <ville>, <code> »). Chaque phrase : la commune sûre, la seule
détection ; la rue sûre dans les rues de la commune. Magasin : Saint-Maximin (Oise), comme le banc.
"""

import pytest

from api.services.communes.analyse import A_CONFIRMER, SURE
from api.services.communes.base import charger_base
from api.services.nombres.lecture import analyser_message
from api.services.voies import base as base_voies
from api.services.voies.analyse import SURE as VOIE_SURE
from api.services.voies.analyse import analyser as analyser_voie

ADRESSES = [
    ("60057", "Beauvais", "Avenue Foch"),
    ("60175", "Creil", "Rue de la République"),
    ("60159", "Compiègne", "Rue Solférino"),
    ("60612", "Senlis", "Rue de Meaux"),
    ("60157", "Clermont", "Rue de la République"),
    ("60463", "Nogent-sur-Oise", "rue du Général de Gaulle"),
    ("60589", "Saint-Maximin", "Rue Jean Jaurès"),
    ("80021", "Amiens", "Rue des Trois-Cailloux"),
    ("59350", "Lille", "Rue Nationale"),
    ("76540", "Rouen", "Rue Jeanne d'Arc"),
    ("78646", "Versailles", "Avenue de Paris"),
    ("51454", "Reims", "Rue de Vesle"),
]


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees("60589")


@pytest.fixture(autouse=True)
def annuaire_reel():
    base_voies.voies_de.cache_clear()
    yield
    base_voies.voies_de.cache_clear()


def _formes(insee, ville, rue, code):
    return [
        f"12 {rue}, {code} {ville}",
        f"12 {rue.lower()} {code} {ville.lower()}",
        f"12 {rue} à {ville}, {code}",
    ]


def _lu(texte, base, magasin):
    return [
        (d.statut, d.lectures[0].commune.nom, d.lectures[0].commune.dep)
        for d in analyser_message(texte, base, magasin).detections
    ]


def test_le_filet_porte_sept_communes_de_l_oise_et_cinq_autres(base):
    deps = [base.commune(insee).dep for insee, _, _ in ADRESSES]
    assert deps.count("60") == 7 and len(deps) == 12


@pytest.mark.parametrize(("insee", "ville", "rue"), ADRESSES)
def test_adresse_complete_commune_et_rue_sures(base, magasin, insee, ville, rue):
    commune = base.commune(insee)
    voies = base_voies.voies_de(insee)
    assert rue in voies.noms, f"{rue} absente de l'annuaire de {ville}"
    for texte in _formes(insee, ville, rue, commune.cps[0]):
        assert _lu(texte, base, magasin) == [(SURE, commune.nom, commune.dep)], texte
        detection = analyser_voie(texte, voies, commune.nom)
        assert (detection.statut, detection.retenue) == (VOIE_SURE, rue), texte


def test_C1_le_code_postal_clot_le_nom_de_la_rue(base, magasin):
    assert _lu("J'habite trois avenue Foch, 60000 Beauvais.", base, magasin) == [(SURE, "Beauvais", "60")]
    assert _lu("5 rue Pasteur, 60600 Clermont.", base, magasin) == [(SURE, "Clermont", "60")]


def test_C1_le_dernier_mot_de_la_rue_colle_au_code_n_est_pas_une_commune(base, magasin):
    lu = _lu("12 Rue du Général de Gaulle, 60180 Nogent-sur-Oise", base, magasin)
    assert lu == [(SURE, "Nogent-sur-Oise", "60")]


def test_C2_le_departement_dit_empeche_la_sure_d_un_autre(base, magasin):
    detections = analyser_message("J'habite à Longueau dans l'Oise.", base, magasin).detections
    assert len(detections) == 1 and detections[0].statut == A_CONFIRMER
    noms = [(l.commune.nom, l.commune.dep) for l in detections[0].lectures]
    assert ("Saint-Martin-Longueau", "60") in noms[:2]


def test_C2_sans_commune_du_departement_qui_porte_ces_mots_rien_ne_change(base, magasin):
    """Filet des 687 : « Gisor dans l'Oise » reste Gisors (Eure) sûre, comme en production."""
    assert _lu("Gisor dans l'Oise", base, None) == [(SURE, "Gisors", "27")]


def test_C3_un_morceau_de_nom_trouve_la_commune_du_departement(base, magasin):
    detections = analyser_message("C'est à Maxence dans l'Oise.", base, magasin).detections
    assert len(detections) == 1 and detections[0].statut == A_CONFIRMER
    assert detections[0].lectures[0].commune.nom == "Pont-Sainte-Maxence"


def test_C4_la_ville_dite_juste_apres_la_rue(base, magasin):
    lu = _lu("5 rue du vieux moulin pont saint maxence", base, magasin)
    assert lu == [(SURE, "Pont-Sainte-Maxence", "60")]


def test_C4_sans_rue_de_cette_commune_rien_n_est_lu(base, magasin):
    """« Hugo » n'est pas lue après « rue Victor » : la rue n'est pas une rue d'une commune lue."""
    assert _lu("12 rue Victor Hugo", base, magasin) == []


def test_C5_une_ville_lointaine_ne_passe_pas_sure_contre_le_code(base, magasin):
    detections = analyser_message("soixante cinq cent cinquante vernayon à la", base, magasin).detections
    assert all(d.statut != SURE for d in detections)
    codes = [d for d in detections if d.code_postal_entendu]
    assert codes and codes[0].lectures[0].commune.nom == "Verneuil-en-Halatte"


def test_C5_sans_commune_du_code_qui_ressemble_rien_ne_change(base, magasin):
    """Filet des 687 : le code entendu (60560) n'est pas celui de la commune, mais aucune commune
    de ce code ne ressemble aux mots : Verneuil-en-Halatte reste sûre, comme en production."""
    lu = _lu("Vers néanalate, soixante mille cinq cent soixante, cinq cent cinquante.", base, magasin)
    assert (SURE, "Verneuil-en-Halatte", "60") in lu
