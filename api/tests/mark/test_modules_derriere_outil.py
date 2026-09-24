"""[.mark] Lot 3 de « la fiche au fil de l'eau » : les modules derrière l'outil.

Plan : `Labo-agent-vocal/plans/2026-09-23-plan-fiche-au-fil-de-leau.md` (D7, D13, D23,
D24, D37, D42).

Le trajet visé : le modèle appelle `noter_information(commune="Chantilly")`, l'outil
reprend ce que le module a DÉJÀ trouvé sur la phrase entière de l'appelant, et
écrit la valeur normalisée ; le modèle n'a jamais vu de note entre crochets.

| Test | Ce qu'il prouve |
|---|---|
| T3.1 | Une commune passée par l'outil ressort résolue (nom officiel + code INSEE) |
| T3.2 | Une rue passée par l'outil est cherchée dans la commune déjà tranchée |
| T3.3 | Une épellation passée par l'outil est lue par le code |
| T3.4 | Interrupteur allumé : aucune note n'entre dans le texte lu par le modèle |
| T3.5 | Interrupteur allumé : la réécriture a bien lieu (nombres en chiffres) |
| T3.6 | Une ambiguïté renvoie `{statut: "ambigu", options}` et le modèle est relancé |
| T3.7 | Interrupteur éteint : notes et réécriture inchangées |

⛔ Les chemins « sûrs » passent par les VRAIS modules (vraie liste des communes,
index de rues de test) : des traces écrites à la main ne prouveraient pas que
l'outil lit ce que les modules écrivent vraiment.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.schemas.organization_preferences import AdresseEtablissement
from api.services.communes.mention import MARQUE as MARQUE_COMMUNE
from api.services.epellation.mention import MARQUE as MARQUE_EPELLATION
from api.services.nombres.mention import MARQUE as MARQUE_NOMBRES
from api.services.pipecat.lecture_appelant import lire_message_tape
from api.services.pipecat.verification_communes import consigner_dans
from api.services.voies import base as base_voies
from api.services.voies.mention import MARQUE as MARQUE_VOIE
from api.services.workflow.fiche_au_fil_de_leau import (
    CONSIGNE_AMBIGU,
    ReglagesFiche,
    creer_gestionnaire,
    ecrire_dans_la_fiche,
    lire_commune,
    lire_rue,
)

DONNEES = Path(__file__).parent / "donnees"
MAGASIN = AdresseEtablissement(
    code_postal="60740", code_insee="60589", commune="Saint-Maximin"
)
STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)
PANNE = SimpleNamespace(
    name="panne", extraction_variables=[SimpleNamespace(name="symptome")]
)
MARQUES = (MARQUE_COMMUNE, MARQUE_VOIE, MARQUE_EPELLATION, MARQUE_NOMBRES)

REGLAGES = {
    "conversion_nombres_transcription": True,
    "verification_communes": True,
    "verification_voies": True,
    "lecture_epellation": True,
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom"},
        {"nom": "commune"},
        {"nom": "code_postal"},
        {"nom": "adresse_intervention"},
        {"nom": "telephone"},
        {"nom": "motif", "origine": "deduit"},
    ],
}
ETEINT = {**REGLAGES, "fiche_au_fil_de_leau": False}


@pytest.fixture(autouse=True)
def index_de_test(monkeypatch, tmp_path):
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", DONNEES / "voies")
    monkeypatch.setattr(base_voies, "EXPORT", "test-2026-09-16")
    monkeypatch.setattr(base_voies, "DOSSIER_TRAVAIL", tmp_path / "voies")
    base_voies.voies_de.cache_clear()
    yield
    base_voies.voies_de.cache_clear()


def _reglages() -> ReglagesFiche:
    reglages = ReglagesFiche.depuis(REGLAGES)
    assert reglages is not None
    return reglages


async def _appel(*phrases: str, reglages: dict = REGLAGES) -> tuple[dict, list[str]]:
    """Fait passer les phrases de l'appelant par les vrais modules, à l'étape
    « panne » (D9 : la fiche décide, pas l'étape). Rend (fiche, textes lus)."""
    fiche: dict = {}
    lus = []
    for phrase in phrases:
        lus.append(
            await lire_message_tape(
                phrase,
                reglages,
                STT_FRANCAIS,
                MAGASIN,
                PANNE,
                consigner_dans(lambda: fiche),
            )
        )
    return fiche, lus


# --- D42 : le lecteur de chaque champ ----------------------------------------


@pytest.mark.parametrize(
    "nom, lecteur",
    [
        ("commune", "commune"),
        ("commune_chantier", "commune"),
        ("adresse_intervention", "rue"),
        ("rue", "rue"),
        ("nom", "aucun"),
        ("code_postal", "aucun"),
    ],
)
def test_lecteur_deduit_du_nom(nom, lecteur):
    champ = ChampFiche(nom=nom)
    assert champ.lecteur_effectif == lecteur
    # ⛔ Gardé vide : relu par l'écran, il doit revenir tel qu'envoyé (24/09).
    assert champ.lecteur is None
    assert ChampFiche.model_validate(champ.model_dump(mode="json")) == champ


def test_lecteur_explicite_garde():
    assert ChampFiche(nom="ville", lecteur="commune").lecteur_effectif == "commune"
    assert ChampFiche(nom="commune", lecteur="aucun").lecteur_effectif == "aucun"


def test_un_champ_ne_peut_pas_s_appeler_comme_le_code_insee_d_une_commune():
    from api.schemas.fiche_agent import verifier_champs

    with pytest.raises(ValueError):
        verifier_champs(
            [
                ChampFiche(nom="commune"),
                ChampFiche(nom="commune_insee", lecteur="aucun"),
            ]
        )


# --- T3.1 à T3.3 : par les vrais modules --------------------------------------


@pytest.mark.asyncio
async def test_T3_1_commune_resolue_par_le_code_postal_de_la_phrase_entiere():
    """D23 : le modèle ne note que « creil » ; le module a tranché sur « creil 60100 »."""
    fiche, _ = await _appel("c'est à creil 60100")
    verdict = ecrire_dans_la_fiche(fiche, _reglages(), "commune", "creil")
    assert verdict.statut == "ecrit" and verdict.suite is None
    assert fiche["commune"] == "Creil"
    assert fiche["commune_insee"] == "60175"
    assert fiche["fiche_etat"]["commune"]["sure"] is True


@pytest.mark.asyncio
async def test_T3_2_rue_cherchee_dans_la_commune_deja_tranchee():
    fiche, _ = await _appel(
        "j'habite à Pont-Sainte-Maxence 60700", "c'est au six rue danton"
    )
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "adresse_intervention", "6 rue danton"
    )
    assert verdict.statut == "ecrit" and verdict.suite is None, verdict
    assert fiche["adresse_intervention"] == "6 Rue Danton"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("note", ["M O R E A U", "moreau", "MOREAU"])
async def test_T3_3_epellation_lue_par_le_code(note):
    """La forme écrite est celle du lecteur d'épellation (« Moreau »), jamais la
    recopie du modèle."""
    fiche, _ = await _appel("c'est monsieur moreau, M O R E A U")
    verdict = ecrire_dans_la_fiche(fiche, _reglages(), "nom", note)
    assert verdict.statut == "ecrit"
    assert fiche["nom"] == fiche["epellations_lues"][-1]["epele"] == "Moreau"


@pytest.mark.asyncio
async def test_T3_3_run_796_une_epellation_mal_recopiee_est_refusee():
    fiche, lus = await _appel("c'est monsieur moreau, M O R E A U")
    verdict = ecrire_dans_la_fiche(fiche, _reglages(), "nom", "MORSO", paroles=lus)
    assert (verdict.statut, verdict.raison) == ("refuse", "non_dit")
    assert "nom" not in fiche


# --- T3.4, T3.5, T3.7 : ce que le modèle lit -----------------------------------


PHRASES = [
    "c'est à creil 60100",
    "c'est monsieur moreau, M O R E A U",
    "mon numéro c'est zéro six douze trente-quatre cinquante-six soixante-dix-huit",
]


@pytest.mark.asyncio
async def test_T3_4_allume_aucune_note_dans_le_texte_du_modele():
    fiche, lus = await _appel(*PHRASES)
    for lu in lus:
        assert not any(marque in lu for marque in MARQUES), lu
    # Les modules ont bien travaillé : leurs traces sont là pour l'outil.
    assert fiche["communes_verifiees"] and fiche["epellations_lues"]


@pytest.mark.asyncio
async def test_T3_5_allume_la_reecriture_a_lieu():
    _, lus = await _appel(PHRASES[2])
    assert "06" in lus[0] and "78" in lus[0]
    assert "douze" not in lus[0]


@pytest.mark.asyncio
async def test_T3_7_eteint_notes_et_reecriture_inchangees():
    _, lus = await _appel(*PHRASES, reglages=ETEINT)
    assert MARQUE_EPELLATION in lus[1]
    assert "06 12 34 56 78" in lus[2]
    # Éteint, la commune n'est lue qu'à une étape qui en collecte une (T2.1).
    assert MARQUE_COMMUNE not in lus[0]
    adresse = SimpleNamespace(
        name="adresse", extraction_variables=[SimpleNamespace(name="commune")]
    )
    lu = await lire_message_tape(
        PHRASES[0], ETEINT, STT_FRANCAIS, MAGASIN, adresse, None
    )
    assert MARQUE_COMMUNE in lu


# --- T3.6 et D37 : quand le module hésite, ou n'a rien trouvé ------------------


TRACE_HESITANTE = {
    "communes_verifiees": [
        {
            "etape": "adresse",
            "entendu": "saint martin",
            "statut": "a_confirmer",
            "commune_retenue": None,
            "propositions": [
                {
                    "nom": "Saint-Martin-Longueau",
                    "code_insee": "60587",
                    "departement": "Oise",
                },
                {
                    "nom": "Saint-Martin-le-Nœud",
                    "code_insee": "60586",
                    "departement": "Oise",
                },
            ],
        }
    ]
}


def test_T3_6_commune_ambigue_ecrite_non_sure_avec_options():
    fiche = {**TRACE_HESITANTE}
    verdict = ecrire_dans_la_fiche(fiche, _reglages(), "commune", "saint martin")
    assert verdict.statut == "ecrit" and verdict.suite == "ambigu"
    assert verdict.options == (
        "Saint-Martin-Longueau (Oise)",
        "Saint-Martin-le-Nœud (Oise)",
    )
    assert fiche["fiche_etat"]["commune"]["sure"] is False
    assert "commune_insee" not in fiche


@pytest.mark.asyncio
async def test_T3_6_le_gestionnaire_renvoie_ambigu_et_laisse_relancer():
    fiche = {**TRACE_HESITANTE}
    gestionnaire = creer_gestionnaire(_reglages(), lambda: fiche, lambda: [])
    resultats = []

    async def rappel(resultat, *, properties=None):
        resultats.append((resultat, properties))

    await gestionnaire(
        SimpleNamespace(
            arguments={"commune": "saint martin"},
            tool_call_id="n1",
            result_callback=rappel,
        )
    )
    ((resultat, properties),) = resultats
    assert resultat["statut"] == "ambigu"
    assert resultat["a_confirmer"][0]["options"]
    assert resultat["consigne"] == CONSIGNE_AMBIGU
    # Note seule, hors suivi : aucun `run_llm` fixé, Pipecat relance (D40).
    assert properties is None


def test_D37_commune_sans_trace_ecrite_non_sure_a_confirmer():
    """Runs 791 et 792 : une commune notée sans trace du module n'est pas perdue."""
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(fiche, _reglages(), "commune", "Lyon 5ᵉ")
    assert verdict.statut == "ecrit" and verdict.suite == "a_confirmer"
    assert fiche["commune"] == "Lyon 5ᵉ"
    assert fiche["fiche_etat"]["commune"]["sure"] is False


def test_D6_une_commune_non_sure_n_ecrase_pas_une_commune_sure():
    fiche = {
        "communes_verifiees": [
            {
                "entendu": "creil",
                "statut": "sure",
                "propositions": [],
                "commune_retenue": {"nom": "Creil", "code_insee": "60175"},
            },
        ]
    }
    ecrire_dans_la_fiche(fiche, _reglages(), "commune", "creil")
    verdict = ecrire_dans_la_fiche(fiche, _reglages(), "commune", "Lyon Court")
    assert (verdict.statut, verdict.raison) == ("refuse", "non_sure_sur_sure")
    assert fiche["commune"] == "Creil" and fiche["commune_insee"] == "60175"


def test_rue_hesitante_remplacee_par_la_proposition_nommee():
    fiche = {
        "voies_verifiees": [
            {
                "entendu": "avenue fauche",
                "statut": "a_confirmer",
                "voie_retenue": None,
                "propositions": [{"nom": "Avenue Foch", "score": 88.0}],
            },
        ]
    }
    lecture = lire_rue("7 avenue fauche", fiche)
    assert (lecture.valeur, lecture.sure, lecture.suite) == (
        "7 avenue fauche",
        False,
        "a_confirmer",
    )
    lecture = lire_rue("7 Avenue Foch", fiche)
    assert (lecture.valeur, lecture.sure, lecture.options) == (
        "7 Avenue Foch",
        False,
        ("Avenue Foch",),
    )


@pytest.mark.asyncio
async def test_run_828_le_modele_recoit_l_ecriture_officielle():
    """L'appelant dit « Ponce-Alpes-Maxence », le module tranche Pont-Sainte-Maxence :
    le résultat de l'outil le dit au modèle, qui ne voit plus de note entre crochets."""
    fiche, _ = await _appel("j'habite à Ponce-Alpes-Maxence, soixante mille sept cents")
    resultats = []

    async def rappel(resultat, *, properties=None):
        resultats.append(resultat)

    gestionnaire = creer_gestionnaire(_reglages(), lambda: fiche, lambda: [])
    await gestionnaire(
        SimpleNamespace(
            arguments={"commune": "Ponce-Alpes-Maxence", "code_postal": "60700"},
            tool_call_id="n1",
            result_callback=rappel,
        )
    )
    (resultat,) = resultats
    assert resultat["statut"] == "note"
    assert resultat["ecriture_retenue"] == {"commune": "Pont-Sainte-Maxence"}
    assert "officielle" in resultat["consigne"]
    # A6 : la consigne ne pousse plus à redire ni à faire confirmer.
    assert "Tu ne la redis pas et tu ne la fais pas confirmer" in resultat["consigne"]
    # Une valeur écrite telle que donnée n'est pas répétée au modèle.
    assert "code_postal" not in resultat["ecriture_retenue"]


def test_la_trace_la_plus_recente_gagne():
    fiche = {
        "communes_verifiees": [
            {
                "entendu": "creil",
                "statut": "a_confirmer",
                "commune_retenue": None,
                "propositions": [{"nom": "Creil", "code_insee": "60175"}],
            },
            {
                "entendu": "creil",
                "statut": "sure",
                "propositions": [],
                "commune_retenue": {"nom": "Creil", "code_insee": "60175"},
            },
        ]
    }
    assert lire_commune("creil", fiche).sure is True
