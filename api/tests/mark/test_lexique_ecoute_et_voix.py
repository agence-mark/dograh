"""[.mark] Non-regression test for the two other uses of the trade vocabulary.

The questions this file answers:

    Does the transcription receive the agent's Dictionary first, then the terms
    ticked in the vocabulary, and nothing more than the budget allows? With the
    switch off, does it receive EXACTLY the list of before? Does the voice say
    the names as the vocabulary asks, whatever the case, on whole words only,
    with the agent's own fixes winning -- and are the numbers still said in
    words afterwards? And does the text the model keeps stay the official
    spelling?

Why it exists
-------------
Plan ``lexique-metier``, lot 3 (L7, L8, T11; budget raised by Evan on
2026-09-17, L19). 🔴 A list too long is refused by Deepgram and the call loses
its transcription; a pronunciation applied inside words would turn
"Scandinave" into something nobody said.

⚠️ What this file does NOT prove: that a real call transcribes better (the
measure in volume decides), nor that the screen shows the vocabulary.
"""

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.lexique.ecoute import (
    MAX_CARACTERES_ECOUTES,
    MAX_TERMES_ECOUTES,
    construire_liste_flux,
    regles_de_prononciation,
)
from api.services.lexique.reglages import interrupteur_allume, lire_lexique_de_lappel
from api.services.pipecat.service_factory import construire_remplacements_de_voix

DICTIONARY = "poêle à granulés, insert, ramonage"

LEXIQUE = LexiqueMetier.model_validate(
    {
        "termes": [
            {"terme": "Edilkamin", "variantes": ["Edil Kamin"], "prononciation": "édile kamine",
             "categorie": "marque", "a_ecouter": True},
            {"terme": "Jøtul", "prononciation": "yotoul", "categorie": "marque", "a_ecouter": True},
            {"terme": "Scan", "prononciation": "skann", "categorie": "marque", "a_ecouter": False},
            {"terme": "MCZ", "categorie": "marque", "a_ecouter": True},
            {"terme": "ramonage", "type": "mot", "a_ecouter": True},
        ]
    }
)


# --------------------------------------------------------------------------- #
# 1. The terms the transcription listens for
# --------------------------------------------------------------------------- #


def test_sans_lexique_la_liste_est_celle_daujourdhui():
    termes, depassement = construire_liste_flux(DICTIONARY, None)
    assert termes == ["poêle à granulés", "insert", "ramonage"]
    assert depassement is False
    assert construire_liste_flux(None, None) == ([], False)
    assert construire_liste_flux("", LexiqueMetier()) == ([], False)


def test_le_dictionnaire_passe_devant_puis_les_termes_coches():
    termes, depassement = construire_liste_flux(DICTIONARY, LEXIQUE)
    # "ramonage" is ticked in the vocabulary too: sent once, in the Dictionary's place.
    assert termes == ["poêle à granulés", "insert", "ramonage", "Edilkamin", "Jøtul", "MCZ"]
    assert depassement is False


def test_un_terme_decoche_nest_pas_envoye():
    termes, _ = construire_liste_flux(None, LEXIQUE)
    assert "Scan" not in termes


def test_les_doublons_sont_retires_sans_tenir_compte_des_majuscules():
    termes, _ = construire_liste_flux("EDILKAMIN, insert", LEXIQUE)
    assert termes.count("EDILKAMIN") == 1
    assert "Edilkamin" not in termes


def test_la_liste_sarrete_au_budget_de_termes():
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": f"Marque{i:03d}", "a_ecouter": True} for i in range(200)]}
    )
    termes, depassement = construire_liste_flux(None, lexique)
    assert len(termes) == MAX_TERMES_ECOUTES
    assert depassement is True


def test_la_liste_sarrete_au_budget_de_caracteres():
    long = "x" * 78
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": f"{long}{i:02d}", "a_ecouter": True} for i in range(30)]}
    )
    termes, depassement = construire_liste_flux(None, lexique)
    assert sum(len(t) for t in termes) <= MAX_CARACTERES_ECOUTES
    assert depassement is True


def test_le_dictionnaire_des_agents_daujourdhui_laisse_la_place_aux_marques():
    """Read on 2026-09-17 on agents 6, 12 and 13: 81 terms, 1 142 characters."""
    dictionary = ", ".join(f"terme{i:02d}" for i in range(81))
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": f"Marque{i:02d}", "a_ecouter": True} for i in range(27)]}
    )
    termes, depassement = construire_liste_flux(dictionary, lexique)
    assert depassement is False
    assert len([t for t in termes if t.startswith("Marque")]) == 27


# --------------------------------------------------------------------------- #
# 2. The switch
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "run_configs,attendu",
    [({}, True), (None, True), ({"lexique_metier": None}, True), ({"lexique_metier": False}, False),
     ({"lexique_metier": True}, True)],
    ids=["absent", "aucune-config", "nul", "eteint", "allume"],
)
def test_linterrupteur_est_allume_par_defaut(run_configs, attendu):
    assert interrupteur_allume(run_configs) is attendu


@pytest.mark.asyncio
async def test_interrupteur_eteint_le_lexique_nest_meme_pas_lu(monkeypatch):
    lectures = []

    async def _lire(organization_id):
        lectures.append(organization_id)
        return LEXIQUE

    monkeypatch.setattr("api.services.lexique.reglages.lire_lexique", _lire)
    assert (await lire_lexique_de_lappel({"lexique_metier": False}, 11)).termes == []
    assert lectures == []
    assert (await lire_lexique_de_lappel({}, 11)).termes
    assert lectures == [11]


# --------------------------------------------------------------------------- #
# 3. The pronunciations
# --------------------------------------------------------------------------- #


async def _dire(texte: str, run_configs: dict | None, lexique, langue_francaise: bool = False) -> str:
    for _, transformation in construire_remplacements_de_voix(run_configs, langue_francaise, lexique):
        texte = await transformation(texte, "*")
    return texte


@pytest.mark.asyncio
async def test_le_nom_est_prononce_comme_le_lexique_le_demande():
    assert await _dire("votre EDILKAMIN est en erreur", None, LEXIQUE) == "votre édile kamine est en erreur"
    assert await _dire("un poêle Edil Kamin", None, LEXIQUE) == "un poêle édile kamine"
    assert await _dire("un Jøtul et un MCZ", None, LEXIQUE) == "un yotoul et un MCZ"


@pytest.mark.asyncio
async def test_seuls_les_mots_entiers_sont_remplaces():
    """⛔ "Scan" must not eat the "Scan" of "Scandinave"."""
    assert await _dire("un poêle scandinave, pas un Scan", None, LEXIQUE) == (
        "un poêle scandinave, pas un skann"
    )


@pytest.mark.asyncio
async def test_lentree_de_lagent_lemporte_sur_le_lexique():
    dit = await _dire("un Jøtul", {"tts_replacements": ["Jøtul:iotoul de Norvège"]}, LEXIQUE)
    assert dit == "un iotoul de Norvège"


@pytest.mark.asyncio
async def test_lentree_de_lagent_seule_se_comporte_comme_avant():
    assert await _dire("Appelez le SAV demain", {"tts_replacements": ["SAV:S. A. V."]}, None) == (
        "Appelez le S. A. V. demain"
    )


@pytest.mark.asyncio
async def test_la_prononciation_passe_avant_les_nombres_en_mots():
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Edilkamin", "prononciation": "édile kamine"}]}
    )
    dit = await _dire("votre Edilkamin, code postal 60550", None, lexique, langue_francaise=True)
    assert dit.startswith("votre édile kamine")
    assert "60550" not in dit and "soixante" in dit


@pytest.mark.asyncio
async def test_agent_non_francais_les_nombres_restent_en_chiffres():
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Edilkamin", "prononciation": "édile kamine"}]}
    )
    dit = await _dire("your Edilkamin, code 60550", None, lexique, langue_francaise=False)
    assert dit == "your édile kamine, code 60550"


def test_sans_prononciation_aucune_transformation_nest_posee():
    sans = LexiqueMetier.model_validate({"termes": [{"terme": "Edilkamin", "a_ecouter": True}]})
    assert construire_remplacements_de_voix(None, False, sans) == []
    assert construire_remplacements_de_voix(None, False, None) == []


@pytest.mark.asyncio
async def test_chaque_orthographe_dun_nom_est_prononcee():
    """🔴 Relecture du 17/09 : la table indexée sur la forme normalisée gardait
    UNE seule orthographe -- la variante -- et l'orthographe officielle, la seule
    que la correction écrit, n'était plus prononcée."""
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Jotul", "variantes": ["Jøtul"], "prononciation": "yotoul"}]}
    )
    assert await _dire("Vous avez un Jotul, et aussi un Jøtul.", None, lexique) == (
        "Vous avez un yotoul, et aussi un yotoul."
    )
    motifs = [motif for motif, _ in regles_de_prononciation(None, lexique)]
    assert len(motifs) == 2


@pytest.mark.asyncio
async def test_une_surcharge_de_lagent_ne_sapplique_quune_fois():
    """🔴 Contre-relecture du 17/09 : « jotul » de l'agent et « Jotul » du lexique
    faisaient deux motifs équivalents, et le remplacement était appliqué deux fois."""
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Jotul", "prononciation": "yotoul"}]}
    )
    run_configs = {"tts_replacements": ["jotul:Jotul de Norvège"]}
    assert len(regles_de_prononciation(run_configs, lexique)) == 1
    assert await _dire("un Jotul.", run_configs, lexique) == "un Jotul de Norvège."


@pytest.mark.asyncio
async def test_lentree_de_lagent_ecarte_toutes_les_orthographes_du_meme_mot():
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Jotul", "variantes": ["Jøtul"], "prononciation": "yotoul"}]}
    )
    dit = await _dire(
        "un Jotul et un Jøtul", {"tts_replacements": ["jotul:iotoul de Norvège"]}, lexique
    )
    assert "yotoul" not in dit
    assert dit == "un iotoul de Norvège et un iotoul de Norvège"


def test_les_formes_longues_sont_remplacees_dabord():
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Cheminées Godin", "variantes": ["Godin"], "prononciation": "godin"}]}
    )
    motifs = [motif for motif, _ in regles_de_prononciation(None, lexique)]
    assert motifs[0].endswith("Godin(?!\\w)") and "Chemin" in motifs[0]


# --------------------------------------------------------------------------- #
# 4. At the level of the feature: what the voice receives, what the model keeps
# --------------------------------------------------------------------------- #


class _VoixDeTest:
    """A voice without word timestamps (like Voxtral): it speaks the text it is given."""

    def __init__(self, transformations):
        self._transformations = transformations
        self.dit: list[str] = []

    async def parler(self, texte: str) -> None:
        for _, transformation in self._transformations:
            texte = await transformation(texte, "*")
        self.dit.append(texte)


@pytest.mark.asyncio
async def test_la_voix_recoit_le_texte_transforme_et_lhistorique_garde_lorthographe():
    historique = []
    reponse = "Votre Edilkamin est bien noté."
    historique.append({"role": "assistant", "content": reponse})
    voix = _VoixDeTest(construire_remplacements_de_voix({}, True, LEXIQUE))
    await voix.parler(reponse)
    assert voix.dit == ["Votre édile kamine est bien noté."]
    assert historique == [{"role": "assistant", "content": "Votre Edilkamin est bien noté."}]


@pytest.mark.asyncio
async def test_une_prononciation_hors_normes_ne_casse_pas_la_voix():
    """A spelling typed by hand: parentheses, dots, a backslash."""
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "M.C.Z (granulés)", "prononciation": "aime cé zède"},
                    {"terme": "Backslash", "prononciation": "anti \\ slash"}]}
    )
    assert await _dire("un M.C.Z (granulés) neuf", None, lexique) == "un aime cé zède neuf"
    assert await _dire("le Backslash", None, lexique) == "le anti \\ slash"


def test_le_reglage_est_declare_dans_la_spec_publiee():
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

    champ = WorkflowConfigurationDefaults.model_json_schema()["properties"]["lexique_metier"]
    assert champ["default"] is True
    assert "trade vocabulary" in champ["description"]
    assert WorkflowConfigurationDefaults.model_validate({}).lexique_metier is True


def test_la_transcription_recoit_la_liste_construite():
    """The call hands ``create_stt_service`` what the builder returned, and nothing else."""
    import inspect

    source = inspect.getsource(
        __import__("api.services.pipecat.run_pipeline", fromlist=["x"])
    )
    assert "termes_ecoutes, ecoute_tronquee = construire_liste_flux(" in source
    assert "keyterms = termes_ecoutes or None" in source
    assert "lexique=lexique_metier," in source


def test_la_fabrique_de_voix_recoit_le_lexique():
    from api.services.pipecat.service_factory import create_tts_service

    parametres = inspect_signature(create_tts_service)
    assert "lexique" in parametres


def inspect_signature(fonction) -> list[str]:
    import inspect

    return list(inspect.signature(fonction).parameters)
