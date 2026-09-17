"""[.mark] Non-regression test for reading the names of the trade vocabulary.

The questions this file answers:

    On the bench of the 2026-09-16 trial (272 sentences carrying a brand, said
    by a synthetic voice at 8 kHz and transcribed by Whisper), does the module
    read at least as many names right as the trial measured, and never more
    than one name sure and wrong? Does it stay useful WITHOUT the pronunciation
    library? Does it read no brand at all in the 81 sentences that carry none?
    Are the real cases of the benches (« Edilcamin », « édile camembert »,
    « poil », « amener ») read as decided? Does a town's name (« Chazelles »,
    « Deville ») never become a brand? And does the correction write the exact
    words the plan fixed?

Why it exists
-------------
Plan ``lexique-metier``, lots 2 and 4 (2026-09-16, thresholds revised by Evan
on 2026-09-17, L20). 🔴 A brand announced sure and wrong is worse than no
vocabulary at all: the agent would write another maker's name on the job.

⚠️ What this file does NOT prove: what the transcription writes on a real call
(the measure in volume decides), nor that the vocabulary is branched into the
pipeline (``test_reconnaissance_lexique_branchement.py``).
"""

import json
from pathlib import Path

import pytest

from api.schemas.lexique_metier import LexiqueMetier, normaliser_terme
from api.services.communes.base import charger_base
from api.services.lexique import analyse as module_analyse
from api.services.lexique.analyse import (
    A_CONFIRMER,
    HOMONYME_COMMUNE,
    SURE,
    Index,
    analyser,
    cle_sonore,
    sons_sans_drapeaux,
)
from api.services.lexique.correction import (
    corriger,
    deja_mentionne,
    partie_de_lappelant,
)

DONNEES = Path(__file__).parent / "donnees"
# Measured on the port, 2026-09-17 (L20): the trial's figures minus what the two
# rules the plan adds cost (language marks removed, towns never rewritten).
SEUILS = {
    ("large-v3", True): 157,
    ("small", True): 129,
    ("large-v3", False): 156,
    ("small", False): 127,
}


@pytest.fixture(scope="module")
def lexique() -> LexiqueMetier:
    return LexiqueMetier.model_validate(json.loads((DONNEES / "lexique_poeles_2026-09-16.json").read_text("utf-8")))


@pytest.fixture(scope="module")
def banc() -> dict:
    return json.loads((DONNEES / "lexique_banc_2026-09-16.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def base_communes() -> dict:
    return charger_base().par_nom


@pytest.fixture(scope="module")
def communes() -> dict:
    return charger_base().par_nom


@pytest.fixture(scope="module")
def index(lexique, communes) -> Index:
    return Index.construire(lexique, communes)


@pytest.fixture(scope="module")
def index_sans_sons(lexique, communes) -> Index:
    return Index.construire(lexique, communes, avec_sons=False)


def _formes_par_terme(index: Index) -> dict[str, set[str]]:
    formes: dict[str, set[str]] = {}
    for forme in index.formes:
        formes.setdefault(forme.terme, set()).add(forme.norm)
    return formes


def _jouer_le_banc(index: Index, phrases: list[dict], avec_sons: bool) -> dict:
    """The trial's own counting: right name sure, right name to confirm, wrong name sure."""
    formes = _formes_par_terme(index)
    compte = {"lues": 0, "sure_juste": 0, "a_confirmer_juste": 0, "fausse_sure": 0, "homonyme": 0}
    for phrase in phrases:
        compte["lues"] += 1
        lectures = analyser(phrase["transcrit"], index, avec_sons=avec_sons)

        def juste(detection, phrase=phrase, formes=formes) -> bool:
            return normaliser_terme(detection.terme) == normaliser_terme(phrase["terme"]) or normaliser_terme(
                phrase["dit"]
            ) in formes.get(detection.terme, set())

        retenues = [d for d in lectures if d.statut != HOMONYME_COMMUNE]
        bonnes = [d for d in retenues if juste(d)]
        if bonnes and bonnes[0].statut == SURE:
            compte["sure_juste"] += 1
        elif bonnes:
            compte["a_confirmer_juste"] += 1
        if any(d.statut == SURE and not juste(d) for d in retenues):
            compte["fausse_sure"] += 1
        compte["homonyme"] += sum(1 for d in lectures if d.statut == HOMONYME_COMMUNE)
    return compte


# --------------------------------------------------------------------------- #
# 1 to 3. The bench, with and without the pronunciation library
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("taille", ["large-v3", "small"])
def test_le_banc_avec_les_sons(index, banc, taille):
    compte = _jouer_le_banc(index, banc["avec_marque"][taille], avec_sons=True)
    assert compte["lues"] == 272
    assert compte["sure_juste"] >= SEUILS[(taille, True)], compte
    assert compte["fausse_sure"] <= 1, compte


@pytest.mark.parametrize("taille", ["large-v3", "small"])
def test_le_banc_sans_la_bibliotheque_de_prononciation(index_sans_sons, banc, taille, monkeypatch):
    """⛔ Fail-open: without espeak-ng the spelling keys alone still read the names."""
    monkeypatch.setattr(module_analyse, "sons", lambda textes: None)
    compte = _jouer_le_banc(index_sans_sons, banc["avec_marque"][taille], avec_sons=True)
    assert compte["lues"] == 272
    assert compte["sure_juste"] >= SEUILS[(taille, False)], compte
    assert compte["fausse_sure"] <= 1, compte


def test_sans_la_bibliotheque_la_construction_ne_leve_pas(lexique, communes, monkeypatch):
    monkeypatch.setattr(module_analyse, "sons", lambda textes: None)
    index = Index.construire(lexique, communes)
    assert index.sons_disponibles is False
    assert [d.terme for d in analyser("c'est un Edilcamin", index)] == ["Edilkamin"]


# --------------------------------------------------------------------------- #
# 4. The 81 sentences without a brand
# --------------------------------------------------------------------------- #


def test_aucune_marque_inventee_sur_les_phrases_sans_marque(index, banc):
    vraies = {"Edilkamin": 0, "MCZ": 0, "Cheminées Godin": 0}
    inventees = []
    lues = 0
    for texte in banc["sans_marque"]:
        lues += 1
        for detection in analyser(texte, index):
            if detection.statut == HOMONYME_COMMUNE:
                continue
            if detection.terme in vraies:
                vraies[detection.terme] += 1
            else:
                inventees.append((texte, detection.entendu, detection.terme, detection.statut))
    assert lues == 81
    # The three real brands of these sentences are read; nothing else is.
    assert inventees == []
    assert all(compte >= 1 for compte in vraies.values()), vraies


@pytest.mark.parametrize("texte", ["la cheminée est bloquée", "le conduit est bouché", "c'est pour un devis"])
def test_des_mots_courants_ne_deviennent_pas_une_marque(index, texte):
    assert analyser(texte, index) == []


# --------------------------------------------------------------------------- #
# 5. The real cases of the benches
# --------------------------------------------------------------------------- #


CAS_REELS = {
    "edilcamin": ("c'est un Edilcamin", [("Edilkamin", SURE)]),
    "edil-camin": ("un Edil camin à granulés", [("Edilkamin", SURE)]),
    "edile-camembert": ("C'est un poêle édile camembert", [("Edilkamin", A_CONFIRMER)]),
    "devis": ("c'est pour un devis, une sortie de toit", []),
    "royal": ("c'est royal, merci beaucoup", []),
    "philippe": ("je suis Philippe Martin", []),
    "scandinave": ("un poêle scandinave", []),
    # Fiches B, C and D of 2026-09-17: the transcription's own limits.
    "medicament": ("c'est un poêle médicament", []),
    "poil": ("c'est un poil à granulés", []),
    "amener": ("je voudrais faire amener le conduit", []),
}


@pytest.mark.parametrize("texte,attendu", list(CAS_REELS.values()), ids=list(CAS_REELS))
def test_cas_reels(index, texte, attendu):
    assert [(d.terme, d.statut) for d in analyser(texte, index)] == attendu


def test_easy_flamme_nest_jamais_rhea_flam_sur(index, index_sans_sons):
    """Guard of T5: a name found by its sound alone never becomes sure."""
    for utilise in (index, index_sans_sons):
        for detection in analyser("Un insert Easy Flamme.", utilise):
            assert not (detection.terme == "Rhea Flam" and detection.statut == SURE)


def test_et_dilcama_est_propose_grace_aux_sons(index, index_sans_sons):
    """Fiche C of 2026-09-17, sentence rebuilt: the sounds find it, the spelling leaves it to confirm."""
    avec = [(d.terme, d.statut) for d in analyser("c'est un poêle et dilcama", index)]
    sans = [(d.terme, d.statut) for d in analyser("c'est un poêle et dilcama", index_sans_sons, avec_sons=False)]
    assert avec == [("Edilkamin", A_CONFIRMER)]
    assert sans == []


def test_les_sons_nont_pas_de_drapeau_de_langue():
    """espeak reads « in » as English: « (en)ɪn(fr)vikta » would compare on the marks."""
    prononces = sons_sans_drapeaux(["in victa", "invicta"])
    if prononces is None:
        pytest.skip("pronunciation library unavailable")
    assert all("(" not in son for son in prononces)


# --------------------------------------------------------------------------- #
# 6. The correction and its wording
# --------------------------------------------------------------------------- #


def test_le_nom_sur_est_remplace_dans_le_texte(index):
    texte = "bonjour, c'est un Edilcamin qui se met en erreur"
    assert corriger(texte, analyser(texte, index)) == "bonjour, c'est un Edilkamin qui se met en erreur"


def test_le_nom_douteux_donne_une_mention_au_texte_exact(index):
    texte = "C'est un poêle édile camembert"
    corrige = corriger(texte, analyser(texte, index))
    assert corrige == (
        "C'est un poêle édile camembert "
        "[Lexique : « édile camembert » peut être Edilkamin (marque). Fais confirmer ce nom avant de le noter.]"
    )


def test_la_mention_enumere_jusqua_trois_noms(index):
    from api.services.lexique.analyse import Detection, Proposition
    from api.services.lexique.correction import phrase_de_mention

    def detection(propositions):
        return Detection(
            entendu="édile camembert", debut=0, fin=16, statut=A_CONFIRMER, terme=propositions[0][0],
            categorie=propositions[0][1], score=80.0,
            propositions=tuple(Proposition(t, c, 80.0) for t, c in propositions), par_son=False, exact=False,
        )

    assert phrase_de_mention(detection([("Edilkamin", "marque")])) == (
        "[Lexique : « édile camembert » peut être Edilkamin (marque). Fais confirmer ce nom avant de le noter.]"
    )
    assert phrase_de_mention(detection([("Edilkamin", "marque"), ("Ecoforest", "marque")])) == (
        "[Lexique : « édile camembert » peut être Edilkamin (marque) ou Ecoforest (marque). "
        "Fais confirmer ce nom avant de le noter.]"
    )
    trois = detection([("Edilkamin", "marque"), ("Ecoforest", "marque"), ("Invicta", None)])
    assert phrase_de_mention(trois) == (
        "[Lexique : « édile camembert » peut être Edilkamin (marque), Ecoforest (marque) ou Invicta. "
        "Fais confirmer ce nom avant de le noter.]"
    )


def test_sans_lecture_le_texte_ne_bouge_pas_et_la_correction_est_idempotente(index):
    assert corriger("bonjour, je voudrais un rendez-vous", []) == "bonjour, je voudrais un rendez-vous"
    texte = "c'est un Edilcamin"
    une_fois = corriger(texte, analyser(texte, index))
    assert corriger(une_fois, analyser(une_fois, index)) == une_fois
    doute = "C'est un poêle édile camembert"
    avec_mention = corriger(doute, analyser(doute, index))
    assert deja_mentionne(avec_mention)
    appelant, notes = partie_de_lappelant(avec_mention)
    assert appelant == doute and notes.startswith("[Lexique :")


def test_deux_noms_dans_un_message_sont_corriges_chacun(index):
    """Two names of different lengths: the second span must not be moved by the first."""
    texte = "c'est un Edil camin et avant j'avais un poêle Piazetta"
    lectures = analyser(texte, index)
    assert [(d.entendu, d.terme, d.statut) for d in lectures] == [
        ("Edil camin", "Edilkamin", SURE),
        ("Piazetta", "Piazzetta", SURE),
    ]
    assert corriger(texte, lectures) == "c'est un Edilkamin et avant j'avais un poêle Piazzetta"


@pytest.mark.parametrize(
    "texte,terme",
    [("Un insert ou coffaine.", "Okofen"), ("C'est un poêle thermatec.", "Termatech")],
    ids=["okofen", "termatech"],
)
def test_un_nom_trouve_par_le_son_seul_reste_a_confirmer(index, texte, terme):
    """Guard of T5: the sounds find the name, the spelling decides whether it is sure."""
    if not index.sons_disponibles:
        pytest.skip("pronunciation library unavailable")
    assert [(d.terme, d.statut) for d in analyser(texte, index)] == [(terme, A_CONFIRMER)]


def test_les_mentions_des_autres_lecteurs_ne_sont_pas_analysees(index):
    texte = "je suis à Deville [Vérification de la commune : « Deville » correspond à Déville-lès-Rouen (76250, Seine-Maritime). Utilise ce nom sans le faire répéter.]"
    appelant, notes = partie_de_lappelant(texte)
    assert appelant == "je suis à Deville"
    assert analyser(notes, index) == []


# --------------------------------------------------------------------------- #
# 7. A trade word is listened for, never corrected
# --------------------------------------------------------------------------- #


def test_un_mot_du_metier_nest_jamais_une_lecture(communes):
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "ramonage", "type": "mot", "a_ecouter": True}, {"terme": "Edilkamin"}]}
    )
    index = Index.construire(lexique, communes)
    assert {f.terme for f in index.formes} == {"Edilkamin"}
    assert analyser("je voudrais un ramonage", index) == []


# --------------------------------------------------------------------------- #
# 8. The keys
# --------------------------------------------------------------------------- #


def test_les_cles_rapprochent_les_orthographes_dune_meme_marque():
    assert cle_sonore(normaliser_terme("Jøtul")) == cle_sonore(normaliser_terme("Jotul"))
    assert normaliser_terme("Haas+Sohn") == "haas sohn"
    assert cle_sonore(normaliser_terme("Piazzetta")) == cle_sonore(normaliser_terme("Piatsetta"))


# --------------------------------------------------------------------------- #
# 9. T16: a town's name is never rewritten as a brand
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def index_homonymes(communes) -> Index:
    lexique = LexiqueMetier.model_validate(
        {
            "termes": [
                {"terme": "Cheminées de Chazelles", "variantes": ["Chazelles"], "categorie": "marque"},
                {"terme": "Barbas", "categorie": "marque"},
                {"terme": "Deville", "categorie": "marque"},
            ]
        }
    )
    return Index.construire(lexique, communes)


@pytest.mark.parametrize(
    "texte",
    ["j'habite à Chazelles", "c'est à Deville", "je suis sur Barbas"],
    ids=["chazelles", "deville", "barbas"],
)
def test_une_commune_nest_jamais_reecrite_en_marque(index_homonymes, texte):
    lectures = analyser(texte, index_homonymes)
    assert all(d.statut == HOMONYME_COMMUNE for d in lectures)
    assert corriger(texte, lectures) == texte


def test_la_marque_reste_reconnue_quand_le_passage_nest_pas_une_commune(index_homonymes):
    texte = "c'est un poêle Cheminées de Chazelle"
    lectures = analyser(texte, index_homonymes)
    assert [(d.terme, d.statut) for d in lectures] == [("Cheminées de Chazelles", SURE)]


def test_les_trois_marques_de_ce_test_sont_bien_des_communes(base_communes):
    """La donnée du test, vérifiée : sans ça, les cas ci-dessus ne prouveraient rien."""
    from api.schemas.lexique_metier import normaliser_terme as forme

    assert {forme("Chazelles"), forme("Barbas"), forme("Deville")} <= set(base_communes)


def test_sans_la_base_des_communes_rien_nest_lu(lexique, monkeypatch):
    """The list of communes unreadable: the vocabulary reads nothing rather than risk a town."""
    index = Index.construire(lexique, None)
    assert analyser("c'est un Edilcamin", index) == []
    assert corriger("c'est un Edilcamin", []) == "c'est un Edilcamin"
