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
2026-09-17, L19; ceiling declared with the provider, plan « le lexique » of
2026-09-26, Q1). 🔴 A list too long is refused by Deepgram and the call loses
its transcription; a pronunciation applied inside words would turn
"Scandinave" into something nobody said.

⚠️ What this file does NOT prove: that a real call transcribes better (the
measure in volume decides), nor that the screen shows the vocabulary.
"""

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.configuration.plafond_lexique import (
    PlafondLexique,
    jetons_du_terme,
    plafond_du_lexique,
)
from api.services.lexique.ecoute import (
    construire_liste_ecoutee,
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
# 1. The terms the transcription listens for, within the provider's ceiling
# --------------------------------------------------------------------------- #

DEEPGRAM = plafond_du_lexique("deepgram", "flux-general-multi")  # the model in production
NOVA = plafond_du_lexique("deepgram", "nova-3")


def liste(dictionary, lexique, plafond=DEEPGRAM):
    return construire_liste_ecoutee(dictionary, lexique, plafond)


def _lexique_coche(n: int, longueur: int = 9) -> LexiqueMetier:
    return LexiqueMetier.model_validate(
        {"termes": [{"terme": f"M{i:03d}".ljust(longueur, "x"), "a_ecouter": True} for i in range(n)]}
    )


def test_sans_lexique_la_liste_est_celle_daujourdhui():
    resultat = liste(DICTIONARY, None)
    assert resultat.termes == ["poêle à granulés", "insert", "ramonage"]
    assert resultat.tronquee is False
    assert liste(None, None).termes == []
    assert liste("", LexiqueMetier()).termes == []


def test_le_dictionnaire_passe_devant_puis_les_termes_coches():
    resultat = liste(DICTIONARY, LEXIQUE)
    # "ramonage" is ticked in the vocabulary too: sent once, in the Dictionary's place.
    assert resultat.termes == ["poêle à granulés", "insert", "ramonage", "Edilkamin", "Jøtul", "MCZ"]
    assert resultat.tronquee is False


def test_un_terme_decoche_nest_pas_envoye():
    assert "Scan" not in liste(None, LEXIQUE).termes


def test_les_doublons_sont_retires_sans_tenir_compte_des_majuscules():
    termes = liste("EDILKAMIN, insert", LEXIQUE).termes
    assert termes.count("EDILKAMIN") == 1
    assert "Edilkamin" not in termes


def test_flux_sarrete_a_100_termes_quelle_que_soit_leur_longueur():
    """Probe of 2026-09-26: Flux refuses the 101st term (« more than the limit of 100 »)."""
    for longueur in (5, 40):
        resultat = liste(None, _lexique_coche(150, longueur))
        assert len(resultat.termes) == 100
        assert resultat.tronquee is True
        # The order is kept: the START is sent, the end is named.
        assert resultat.non_envoyes[0].startswith("M100")


def test_le_dictionnaire_des_agents_daujourdhui_passe_entier_sur_flux():
    """81 terms, 1 142 characters: accepted by Deepgram on 2026-09-17; 19 terms of the vocabulary fit behind."""
    dictionary = ", ".join(f"t{i:02d}".ljust(14, "x") for i in range(81))
    resultat = liste(dictionary, _lexique_coche(40))
    assert resultat.termes[:81] == [f"t{i:02d}".ljust(14, "x") for i in range(81)]
    assert len(resultat.termes) == 100


def test_nova_sarrete_au_plafond_en_jetons():
    resultat = liste(None, _lexique_coche(200), NOVA)
    assert resultat.tronquee is True
    assert resultat.jetons <= NOVA.jetons
    assert resultat.jetons == sum(jetons_du_terme(t, NOVA) for t in resultat.termes)
    assert resultat.termes == [f"M{i:03d}".ljust(9, "x") for i in range(len(resultat.termes))]


def test_un_terme_long_qui_ne_tient_pas_ne_coute_pas_les_courts_derriere():
    petit = PlafondLexique(fournisseur='Essai', jetons=10, termes=None, octets_par_jeton=3.0, jetons_par_terme=1, source='test')
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "Aaa", "a_ecouter": True}, {"terme": "B" * 60, "a_ecouter": True},
                    {"terme": "Ccc", "a_ecouter": True}]}
    )
    resultat = liste(None, lexique, petit)
    assert resultat.termes == ["Aaa", "Ccc"]
    assert resultat.non_envoyes == ["B" * 60]


def test_le_meme_lexique_suit_le_plafond_de_son_fournisseur():
    """Never one number for every provider: the same list, two ceilings, two cuts."""
    large = PlafondLexique(fournisseur='Essai', jetons=100000, termes=None, octets_par_jeton=3.0, jetons_par_terme=1, source='test')
    assert liste(None, _lexique_coche(150), large).tronquee is False
    assert liste(None, _lexique_coche(150), DEEPGRAM).tronquee is True
    # Long terms: nova-3 cuts on tokens well before Flux cuts on the count.
    assert len(liste(None, _lexique_coche(150, 20), NOVA).termes) < len(liste(None, _lexique_coche(150, 20)).termes) == 100


def test_un_fournisseur_sans_plafond_declare_ne_recoit_aucune_liste():
    """Q1: an unknown limit is a risk of refusal; nothing is sent, and it is said."""
    assert plafond_du_lexique("speechmatics", "enhanced") is None
    assert plafond_du_lexique(None, None) is None
    resultat = liste(DICTIONARY, LEXIQUE, None)
    assert resultat.termes == []
    assert resultat.plafond is None
    assert resultat.non_envoyes[:3] == ["poêle à granulés", "insert", "ramonage"]


def test_les_plafonds_de_deepgram_sont_ceux_de_la_sonde():
    for modele in ("flux-general-multi", "flux-general-en"):
        assert (plafond_du_lexique("deepgram", modele).termes, plafond_du_lexique("deepgram", modele).jetons) == (100, None)
    for modele in ("nova-3", "nova-3-general", "nova-2"):
        assert (plafond_du_lexique("deepgram", modele).termes, plafond_du_lexique("deepgram", modele).jetons) == (None, 500)
    from api.services.configuration.registry import ServiceProviders

    assert plafond_du_lexique(ServiceProviders.DEEPGRAM, "nova-3") is not None


def test_le_compte_des_jetons_ne_sous_estime_pas_les_frontieres_mesurees():
    """The probe measured nova-3's frontier in two orders. The estimate must put
    the FIRST list refused above 500: otherwise it would send a list Deepgram refuses."""
    assert jetons_du_terme("abc", NOVA) == 3  # ceil(3 / 3.5) + 2
    assert jetons_du_terme("Jøtul", NOVA) == 4  # 6 bytes: ceil(6 / 3.5) + 2
    # 111 terms / 965 characters were refused; 89 terms / 1 123 characters too.
    refusee_courte = [f"{i:03d}".ljust(9, "a") for i in range(111)]  # ≈ 965 characters
    assert sum(jetons_du_terme(t, NOVA) for t in refusee_courte) > NOVA.jetons
    refusee_longue = [f"{i:03d}".ljust(13, "a") for i in range(89)]  # ≈ 1 123 characters
    assert sum(jetons_du_terme(t, NOVA) for t in refusee_longue) > NOVA.jetons


def test_aucun_plafond_nest_ecrit_hors_de_la_declaration_du_fournisseur():
    """Q1 / cadre: the ceiling lives in ONE place. A second one, anywhere in the code, is the 2026-09-18 defect back."""
    import re
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    declaration = racine / "services" / "configuration" / "plafond_lexique.py"
    motifs = re.compile(r"MAX_TERMES_ECOUTES|MAX_CARACTERES_ECOUTES|PlafondLexique\(")
    trouves = [
        str(fichier.relative_to(racine))
        for fichier in racine.rglob("*.py")
        if "tests" not in fichier.parts
        and ".venv" not in fichier.parts
        and fichier != declaration
        and motifs.search(fichier.read_text("utf-8", errors="replace"))
    ]
    assert trouves == []


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
    assert "liste_ecoutee = construire_liste_ecoutee(" in source
    assert "keyterms = liste_ecoutee.termes or None" in source
    # Built once the provider is known: the ceiling is the provider's.
    assert source.index("user_config = resolved_user_config") < source.index("liste_ecoutee = construire_liste_ecoutee(")
    assert "lexique=lexique_metier," in source


def test_la_fabrique_de_voix_recoit_le_lexique():
    from api.services.pipecat.service_factory import create_tts_service

    parametres = inspect_signature(create_tts_service)
    assert "lexique" in parametres


def inspect_signature(fonction) -> list[str]:
    import inspect

    return list(inspect.signature(fonction).parameters)
