"""[.mark] 6.1 : la fiche écrit la rue officielle à la place du type de voie DIT, jamais à côté.

Chantier correctifs-apres-banc-v4 (21/10/2026), question n° 380. Banc v4 du 20/10 : « 12 rue
Foch » devenait « 12 rue Avenue Foch ». `_avec_le_type_de_voie` cherchait seulement le DÉBUT
exact du nom officiel devant la portée reconnue ; un type dit différent du type officiel (« rue »
contre « avenue ») restait, et le nom officiel entier s'insérait derrière lui.

Correction : la portée s'étend aussi sur le type de voie dit et les mots de liaison qui précèdent
le nom reconnu (lexique du module des rues, jamais une liste de plus).

| Test | Ce qu'il prouve |
|---|---|
| tableau (29 cas) | type identique, différent, absent, pluriel, abrégé, liaison, numéro bis, numéro dans le nom, deux adresses, nom qui contient un type (« Grande Rue », « Vieux Chemin »), partie déformée |
| bout en bout, trace du module | la vraie lecture des rues (annuaire de l'Oise) puis le vrai outil de la fiche écrivent « 12 Avenue Foch » |
| bout en bout, rue relue | la commune confirmée, la rue « à confirmer » relue dans ses rues s'écrit « 12 Avenue Foch » |

Rouge sur `2b7221dc` : 19 cas du tableau sur 29, et les deux bouts en bout (« 12 rue Avenue Foch »).
"""

import pytest

from api.services.pipecat.lecture_appelant import _trace_voie
from api.services.voies import base as base_voies
from api.services.voies.analyse import SURE, analyser
from api.services.workflow.fiche_au_fil_de_leau import lire_rue
from api.tests.mark.test_fiche_correctifs_modules import Appel, _reglages

BEAUVAIS = {"nom": "Beauvais", "code_insee": "60057", "departement": "Oise", "codes_postaux": ["60000"]}
COMMUNE = {"nom": "commune", "origine": "dicte"}
ADRESSE = {"nom": "adresse_intervention", "origine": "dicte"}

# (ce que le modèle a noté, ce que le module des rues a entendu, la voie officielle, attendu)
CAS = [
    ("12 rue Foch", "foch", "Avenue Foch", "12 Avenue Foch"),
    ("12 avenue Foch", "foch", "Avenue Foch", "12 Avenue Foch"),
    ("12 Foch", "foch", "Avenue Foch", "12 Avenue Foch"),
    ("12 rue des Lilas", "lilas", "Impasse des Lilas", "12 Impasse des Lilas"),
    ("12 des Lilas", "lilas", "Impasse des Lilas", "12 Impasse des Lilas"),
    ("12 bis rue Foch", "foch", "Avenue Foch", "12 bis Avenue Foch"),
    ("12 rue Jean Jaurès", "jaures", "Avenue Jean Jaurès", "12 Avenue Jean Jaurès"),
    ("12 rue Jean Jaurès", "jean jaures", "Avenue Jean Jaurès", "12 Avenue Jean Jaurès"),
    ("12 rue Jean Joress", "joress", "Rue Jean Jaurès", "12 Rue Jean Jaurès"),
    ("12 rue de la Préfecture", "prefecture", "Rue de la Préfecture", "12 Rue de la Préfecture"),
    ("12 avenue de la Préfecture", "prefecture", "Rue de la Préfecture", "12 Rue de la Préfecture"),
    ("12 grande rue", "grande rue", "Grande Rue", "12 Grande Rue"),
    ("12 rue Foch, 60000 Beauvais", "foch", "Avenue Foch", "12 Avenue Foch, 60000 Beauvais"),
    ("12 rues Foch", "foch", "Avenue Foch", "12 Avenue Foch"),
    ("12 rue d'Alger", "alger", "Cour d'Alger", "12 Cour d'Alger"),
    ("5 rue Jeanne Achète", "jeanne achete", "Place Jeanne Hachette", "5 Place Jeanne Hachette"),
    ("8 rue du 8 Mai 1945", "mai 1945", "Rue du 8 Mai 1945", "8 Rue du 8 Mai 1945"),
    ("12 rue Foch et 3 rue Carnot", "foch", "Avenue Foch", "12 Avenue Foch et 3 rue Carnot"),
    ("12 chemin du Vieux Moulin", "vieux moulin", "Rue du Vieux Moulin", "12 Rue du Vieux Moulin"),
    ("12 rond point de l'Europe", "europe", "Place de l'Europe", "12 Place de l'Europe"),
    ("Bâtiment B, 12 rue Foch", "foch", "Avenue Foch", "Bâtiment B, 12 Avenue Foch"),
    ("12 av Foch", "foch", "Avenue Foch", "12 Avenue Foch"),
    ("12, boulevard Foch", "foch", "Avenue Foch", "12, Avenue Foch"),
    ("12 rue Saint-Lazare", "saint lazare", "Square Saint Lazare", "12 Square Saint Lazare"),
    ("12 rue de l'Église", "eglise", "Place de l'Église", "12 Place de l'Église"),
    (
        "12 rue du Vieux Chemin de Meaux",
        "vieux chemin de meaux",
        "Rue du Vieux Chemin de Meaux",
        "12 Rue du Vieux Chemin de Meaux",
    ),
    (
        "12 Vieux Chemin de Meaux",
        "vieux chemin de meaux",
        "Rue du Vieux Chemin de Meaux",
        "12 Rue du Vieux Chemin de Meaux",
    ),
    ("6 rue Danton", "danton", "Rue Danton", "6 Rue Danton"),
    ("6 rue d'antan", "d antan", "Rue Danton", "6 Rue Danton"),
]


@pytest.fixture(autouse=True)
def annuaire_reel():
    """L'annuaire réel du dépôt, lu par le chemin réel (décompression comprise)."""
    base_voies.voies_de.cache_clear()
    yield
    base_voies.voies_de.cache_clear()


def test_le_tableau_couvre_au_moins_vingt_cas():
    assert len(CAS) >= 20


@pytest.mark.parametrize(("note", "entendu", "officielle", "attendu"), CAS)
def test_la_voie_officielle_remplace_le_type_dit(note, entendu, officielle, attendu):
    fiche = {
        "tour_appelant": 1,
        "voies_verifiees": [
            {
                "etape": "adresse",
                "entendu": entendu,
                "statut": "sure",
                "voie_retenue": officielle,
                "propositions": [{"nom": officielle, "score": 100.0}],
                "tour": 1,
            }
        ],
    }
    lecture = lire_rue(note, fiche)
    assert (lecture.valeur, lecture.sure) == (attendu, True)


@pytest.mark.asyncio
async def test_bout_en_bout_la_trace_du_module_puis_l_outil_de_la_fiche():
    """Le banc du 20/10 : l'appelant dit « rue Foch », la rue officielle est l'avenue."""
    parole = "J'habite au 12 rue Foch."
    detection = analyser(parole, base_voies.voies_de("60057"), "Beauvais")
    assert (detection.statut, detection.retenue) == (SURE, "Avenue Foch")

    appel = Appel(_reglages(ADRESSE))
    appel.dit(parole, agent_avant="Quelle est votre adresse ?")
    appel.trace("voies_verifiees", **_trace_voie(detection, "adresse"))
    await appel.note(adresse_intervention="12 rue Foch")
    assert appel.fiche["adresse_intervention"] == "12 Avenue Foch"
    assert appel.sure("adresse_intervention")


@pytest.mark.asyncio
async def test_bout_en_bout_la_rue_relue_apres_la_commune():
    """La commune confirmée, la rue notée « à confirmer » est relue (``analyser_les_rues``)."""
    appel = Appel(_reglages(COMMUNE, ADRESSE))
    appel.dit("Alors j'habite au 12 rue Foch à Bovet", agent_avant="Quelle est votre adresse ?")
    appel.trace(
        "communes_verifiees",
        entendu="Bovet",
        statut="a_confirmer",
        commune_retenue=None,
        propositions=[BEAUVAIS],
    )
    await appel.note(commune="Bovet", adresse_intervention="12 rue Foch")
    assert not appel.sure("adresse_intervention")
    appel.dit("Oui, c'est bien ça.", agent_avant="Est-ce que vous êtes à Beauvais dans l'Oise ?")
    await appel.note(commune="Beauvais")
    assert appel.sure("commune") and appel.sure("adresse_intervention"), appel.fiche
    assert appel.fiche["adresse_intervention"] == "12 Avenue Foch"
