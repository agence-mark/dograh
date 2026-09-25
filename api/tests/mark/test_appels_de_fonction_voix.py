"""[.mark] C14 (patch du banc, PB14) : la voix ne dit jamais un appel de fonction écrit.

Plan : `Labo-agent-vocal/plans/patch-fiche-banc/2026-09-25-plan-patch-fiche-banc.md`.

Run 852 : le modèle a écrit sa porte au lieu de l'appeler, et la voix a dit
« demande_entretien » trois fois. Les phrases ci-dessous sont celles du run.

| Test | Ce qu'il prouve |
|---|---|
| retrait | L'appel écrit est retiré, puce comprise ; le reste de la phrase est intact |
| autre sens | Une parenthèse ordinaire, un texte sans parenthèses : intacts |
| filtre | Une phrase qui n'est qu'un appel est sautée, jamais envoyée à la voix |
| branchement | Toute voix construite par l'usine les reçoit, phrase par phrase seulement |
| Pipecat | Par le vrai service de voix : dit sans l'appel, historique avec |
"""

from types import SimpleNamespace

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSTextFrame,
)
from pipecat.tests.utils import run_test
from pipecat.utils.text.xml_function_tag_filter import XMLFunctionTagFilter

from api.services.pipecat.appels_de_fonction_voix import (
    PhraseQuiNEstQuUnAppel,
    retirer_appels_de_fonction,
    retirer_les_appels,
)
from api.services.pipecat.service_factory import (
    construire_filtres_de_texte_voix,
    create_tts_service,
    reglages_de_voix_communs,
)
from api.tests.mark.test_nombres_pour_la_voix import (
    FOURNISSEURS,
    STT_FRANCAIS,
    _audio_config,
    _VoixQuiEcoute,
)

PHRASES_852 = [
    (
        (
            "D'accord. Je vais vous mettre en relation avec un conseiller pour fixer "
            "la date de l'intervention. •demande_entretien()"
        ),
        (
            "D'accord. Je vais vous mettre en relation avec un conseiller pour fixer "
            "la date de l'intervention."
        ),
    ),
    (
        (
            "C'est noté. Un conseiller va vous rappeler pour fixer ce rendez-vous "
            "d'entretien. • demande_entretien()"
        ),
        (
            "C'est noté. Un conseiller va vous rappeler pour fixer ce rendez-vous "
            "d'entretien."
        ),
    ),
]


@pytest.mark.parametrize("ecrit, dit", PHRASES_852)
def test_run_852_l_appel_ecrit_n_est_pas_dit(ecrit, dit):
    assert retirer_les_appels(ecrit) == dit


@pytest.mark.parametrize(
    "ecrit, dit",
    [
        ("Très bien. *demande_sav() Je note.", "Très bien. Je note."),
        ("Parfait - fin_appel_standard()", "Parfait"),
        ("D'accord transfert() je vous passe", "D'accord je vous passe"),
        ('Noté. noter_information({"nom": "Lefebvre"})', "Noté."),
    ],
)
def test_puce_et_arguments(ecrit, dit):
    assert retirer_les_appels(ecrit) == dit


@pytest.mark.parametrize(
    "texte",
    [
        "Le magasin ouvre à 10 h (10 h 30 le samedi).",
        "Votre poêle (à bois) sera vu par un technicien.",
        "Un conseiller vous rappelle dans la journée.",
        "Voir la notice (page 12).",
    ],
)
def test_une_parenthese_ordinaire_reste_dite(texte):
    assert retirer_les_appels(texte) is texte or retirer_les_appels(texte) == texte


@pytest.mark.asyncio
async def test_la_transformation_ne_leve_jamais():
    assert await retirer_appels_de_fonction(None) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase, attendu",
    [
        ("•demande_entretien()", ""),
        (" • demande_entretien(). ", ""),
        ("demande_entretien() Je note.", "demande_entretien() Je note."),
        ("…", "…"),
        ("(10 h)", "(10 h)"),
    ],
)
async def test_le_filtre_saute_une_phrase_qui_n_est_qu_un_appel(phrase, attendu):
    assert await PhraseQuiNEstQuUnAppel().filter(phrase) == attendu


def test_branchement_dans_la_collecte_des_filtres_et_des_transformations():
    filtres = construire_filtres_de_texte_voix(None)
    assert type(filtres[0]) is XMLFunctionTagFilter
    # En dernier, après le markdown (revue du 25/09).
    assert type(filtres[-1]) is PhraseQuiNEstQuUnAppel
    filtres = construire_filtres_de_texte_voix({"tts_markdown_filter_enabled": True})
    assert type(filtres[-1]) is PhraseQuiNEstQuUnAppel
    transformations = reglages_de_voix_communs(None)["text_transforms"]
    assert transformations == [("*", retirer_appels_de_fonction)]
    transformations = reglages_de_voix_communs(
        {"tts_replacements": ["SAV:S. A. V."]}, True
    )["text_transforms"]
    assert transformations[0] == ("*", retirer_appels_de_fonction)
    assert len(transformations) == 3  # puis les remplacements, puis les nombres
    # Mot à mot, l'appel arrive en morceaux : rien n'est posé.
    assert (
        reglages_de_voix_communs({"tts_text_aggregation_mode": "token"})[
            "text_transforms"
        ]
        == []
    )


@pytest.mark.parametrize("nom", sorted(FOURNISSEURS))
def test_chaque_voix_construite_par_l_usine_les_recoit(nom):
    user_config = SimpleNamespace(tts=FOURNISSEURS[nom](), stt=STT_FRANCAIS)
    service = create_tts_service(user_config, _audio_config(), run_configs={})
    assert any(isinstance(f, PhraseQuiNEstQuUnAppel) for f in service._text_filters)
    assert service._text_transforms[0] == ("*", retirer_appels_de_fonction)


@pytest.mark.asyncio
async def test_par_pipecat_la_voix_ne_le_dit_pas_et_l_historique_le_garde():
    """Dans une phrase : retiré de ce qui est dit, gardé dans ce qui retourne à
    l'historique et à la transcription (une transformation, pas un filtre)."""
    voix = _VoixQuiEcoute(
        text_filters=construire_filtres_de_texte_voix(None),
        text_transforms=reglages_de_voix_communs(None)["text_transforms"],
    )
    descendus, _ = await run_test(
        voix,
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("C'est noté, •demande_sav() un conseiller vous rappelle."),
            LLMFullResponseEndFrame(),
        ],
        start_timeout=15,
    )
    dit = " ".join(voix.dits)
    assert "demande_sav" not in dit and "conseiller vous rappelle" in dit
    historique = " ".join(f.text for f in descendus if isinstance(f, TTSTextFrame))
    assert "demande_sav()" in historique


@pytest.mark.asyncio
async def test_par_pipecat_une_phrase_qui_n_est_qu_un_appel_n_atteint_pas_la_voix():
    voix = _VoixQuiEcoute(
        text_filters=construire_filtres_de_texte_voix(None),
        text_transforms=reglages_de_voix_communs(None)["text_transforms"],
    )
    await run_test(
        voix,
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame(PHRASES_852[0][0]),
            LLMFullResponseEndFrame(),
        ],
        start_timeout=15,
    )
    assert voix.dits and not any("demande_entretien" in d for d in voix.dits)
    assert not any(not d.strip() for d in voix.dits)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase, attendu",
    [
        ("D'accord.•demande_entretien()", "D'accord."),
        ("D'accord. **demande_entretien()**", "D'accord."),
        ("D'accord. `demande_entretien()`", "D'accord."),
        ("Je note. demande_entretien(motif=(x))", "Je note."),
        ("le poêle (à bois) fume", "le poêle (à bois) fume"),
        ("à 10h (matin)", "à 10h (matin)"),
    ],
)
async def test_revue_un_appel_colle_ou_balise_est_retire(phrase, attendu):
    assert await retirer_appels_de_fonction(phrase) == attendu


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase", ["**demande_entretien()**", "`demande_entretien()`"])
async def test_revue_une_phrase_qui_n_est_qu_un_appel_balise_est_sautee(phrase):
    assert await PhraseQuiNEstQuUnAppel().filter(phrase) == ""


@pytest.mark.asyncio
async def test_revue_un_retrait_n_est_journalise_qu_une_fois():
    from loguru import logger

    lignes: list[str] = []
    ident = logger.add(lignes.append, format="{message}", level="WARNING")
    try:
        phrase = "D'accord. •demande_entretien()"
        filtree = await PhraseQuiNEstQuUnAppel().filter(phrase)
        await retirer_appels_de_fonction(filtree)
        await PhraseQuiNEstQuUnAppel().filter("•demande_entretien()")
    finally:
        logger.remove(ident)
    retraits = [ligne for ligne in lignes if "retiré de la voix" in ligne]
    assert len(retraits) == 2
