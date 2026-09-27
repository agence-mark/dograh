"""[.mark] The cues before a name come from the vocabulary, never from the code (question 249).

The questions this file answers:

    Does « les poêles sont chers » stay free of any brand (« sont » is not
    « Sohn »)? Does « c'est un poêle Royal » read Royal because the vocabulary
    carries « poêle » ticked « announces a brand », and read nothing once the
    box is unticked? Do the words of a job (« ramonage », « sortie de toit »)
    announce no brand? Does a vocabulary of ANOTHER trade (a restaurant:
    « vin », « champagne ») work with no line of code added? And is no word of a
    trade vocabulary written in the code of ``api/services`` and ``api/schemas``?

Why it exists
-------------
Plan ``2026-09-27-plan-amorces-du-lexique.md`` (question 249, decisions D1 to
D7 of Evan, 2026-09-27, option A: the box « announces a brand »). Until then, ``AMORCES_FORTES`` listed stove words in
``analyse.py``: at a restaurant the mechanism stopped working, unless the fork
was patched. Evan's rule: zero trade word in the code.

The route is the real one: ``corriger_texte`` of the pipeline, on an index
built by ``construire_index``, as a call runs it.

⚠️ What this file does NOT prove: what the transcription writes on a real call
(the phone bench decides), nor that the production vocabulary has its boxes
ticked (to do on the screen after deploying).
"""

import ast
import json
import re
from pathlib import Path

import pytest

from api.schemas.lexique_metier import LexiqueMetier, normaliser_terme
from api.services.communes.base import charger_base
from api.services.lexique.analyse import MOTS_OUTILS, singulier_et_pluriel
from api.services.pipecat.reconnaissance_lexique import construire_index, corriger_texte

DONNEES = Path(__file__).parent / "donnees"
API = Path(__file__).resolve().parents[2]
RACINES_GARDEES = (API / "services", API / "schemas")


@pytest.fixture(scope="module", autouse=True)
def _base_communes():
    """The list of communes, loaded once: without it the vocabulary reads nothing (T16)."""
    charger_base()


def _lexique(*termes: dict) -> LexiqueMetier:
    return LexiqueMetier.model_validate({"termes": list(termes)})


async def _corrige(texte: str, lexique: LexiqueMetier) -> str:
    return await corriger_texte(texte, construire_index(lexique))


POELE = {"terme": "poêle", "type": "mot", "annonce_marque": True}
ROYAL = {"terme": "Royal", "categorie": "marque"}
HAAS_SOHN = {"terme": "Haas+Sohn", "categorie": "marque"}


# --------------------------------------------------------------------------- #
# 1. A very frequent word alone is never a brand heard badly
# --------------------------------------------------------------------------- #


async def test_les_poeles_sont_chers_ne_donne_aucune_marque():
    # Run 400: « sont », after the trade word « poêles », was read as « Sohn », sure.
    assert await _corrige("les poêles sont chers", _lexique(POELE, HAAS_SOHN)) == "les poêles sont chers"


async def test_une_marque_peu_courante_apres_un_mot_du_metier_reste_lue():
    assert await _corrige("un poêle Sohn", _lexique(POELE, HAAS_SOHN)) == "un poêle Haas+Sohn"


# --------------------------------------------------------------------------- #
# 2. The cue comes from the vocabulary's trade words
# --------------------------------------------------------------------------- #


async def test_le_mot_du_metier_du_lexique_fait_lire_la_marque():
    assert await _corrige("c'est un poêle royal", _lexique(POELE, ROYAL)) == "c'est un poêle Royal"


async def test_sans_le_mot_du_metier_dans_le_lexique_rien_nest_lu():
    # The proof that the cue is data: the same sentence, the trade word removed.
    assert await _corrige("c'est un poêle royal", _lexique(ROYAL)) == "c'est un poêle royal"


async def test_un_mot_du_lexique_sans_la_case_nannonce_aucune_marque():
    # Option A: listed is not enough, the box decides.
    poele_decoche = {**POELE, "annonce_marque": False}
    assert await _corrige("c'est un poêle royal", _lexique(poele_decoche, ROYAL)) == "c'est un poêle royal"


def test_un_nom_nannonce_jamais_une_marque():
    lexique = _lexique({"terme": "Supra", "annonce_marque": True})
    assert lexique.termes[0].annonce_marque is False


def test_un_terme_enregistre_avant_la_case_la_lit_decochee():
    assert _lexique({"terme": "poêle", "type": "mot"}).termes[0].annonce_marque is False


@pytest.mark.parametrize(
    "texte",
    [
        # Found by the independent review of 2026-09-27: every word of the
        # vocabulary made a cue, and these became brands, SURE.
        "le ramonage c'est juste obligatoire",
        "j'ai une sortie de toit juste au dessus",
        "le crédit d'impôt c'est juste pour les RGE",
        "le joint philippe l'a changé",
        "pour l'entretien royal service",
        "le conduit passe par le toit supra rapide",
    ],
)
async def test_les_mots_dun_travail_nannoncent_aucune_marque(texte):
    assert await _corrige(texte, _lexique_de_la_production()) == texte


async def test_le_pluriel_du_mot_coche_annonce_aussi():
    assert await _corrige("des poêles royal", _lexique(POELE, ROYAL)) == "des poêles Royal"


def _lexique_de_la_production() -> LexiqueMetier:
    brut = json.loads((DONNEES / "lexique_poeles_2026-09-16.json").read_text("utf-8"))
    mots = json.loads((DONNEES / "lexique_mots_poeles_2026-09-27.json").read_text("utf-8"))["termes"]
    return LexiqueMetier.model_validate({**brut, "termes": brut["termes"] + mots})


async def test_une_orthographe_du_mot_du_metier_est_aussi_une_amorce():
    # D2: « poil » typed as a spelling of « poêle » (Whisper writes it on the bench).
    poele_et_poil = {**POELE, "variantes": ["poil"]}
    assert await _corrige("un poil royal", _lexique(poele_et_poil, ROYAL)) == "un poil Royal"
    assert await _corrige("un poil royal", _lexique(POELE, ROYAL)) == "un poil royal"


async def test_les_amorces_de_la_langue_restent_sans_lexique_de_mots():
    assert await _corrige("la marque c'est royal", _lexique(ROYAL)) == "la marque c'est Royal"


# --------------------------------------------------------------------------- #
# 3. Another trade, no line of code added
# --------------------------------------------------------------------------- #


RESTAURANT = (
    {"terme": "vin", "type": "mot", "annonce_marque": True},
    {"terme": "champagne", "type": "mot", "annonce_marque": True},
    {"terme": "Petit Village", "categorie": "marque"},
    {"terme": "Grand Siècle", "categorie": "marque"},
)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("un vin petit village", "un vin Petit Village"),
        ("un champagne grand siècle", "un champagne Grand Siècle"),
    ],
)
async def test_un_lexique_de_restaurant_marche_sans_code(texte, attendu):
    assert await _corrige(texte, _lexique(*RESTAURANT)) == attendu


async def test_sans_ses_mots_le_lexique_de_restaurant_ne_lit_rien():
    marques = [t for t in RESTAURANT if t.get("type") != "mot"]
    assert await _corrige("un vin petit village", _lexique(*marques)) == "un vin petit village"


# --------------------------------------------------------------------------- #
# 4. Guard: no word of a trade vocabulary written in the code
# --------------------------------------------------------------------------- #


# Words of the vocabularies that are also plain words of the language, used by
# the code for what they say there. ⛔ Each one with its reason; never a word
# that only a trade uses.
MOTS_DE_LA_LANGUE = {
    "ferme": "the business is closed (opening state), not the « foyer fermé »",
    "fermes": "same",
    "sortie": "the way out of a step of the workflow, not the « sortie de toit »",
    "sorties": "same",
    "turbo": "the name of a voice model of the provider (eleven_turbo)",
}


def _termes_des_lexiques() -> set[str]:
    """The terms of the trade vocabularies known to .mark (recopied from the socle),
    whole, and each of their words of 4 letters or more, singular and plural.

    ⚠️ Its limit: it knows the stove trade only (the two vocabularies of the
    tests). A word of another trade written in the code is not seen.
    """
    termes: set[str] = set()
    for fichier in ("lexique_poeles_2026-09-16.json", "lexique_mots_poeles_2026-09-27.json"):
        for terme in json.loads((DONNEES / fichier).read_text("utf-8"))["termes"]:
            for ecrit in [terme["terme"], *terme.get("variantes", [])]:
                norm = normaliser_terme(ecrit)
                if len(norm) > 2:
                    termes.add(norm)
                for mot in norm.split():
                    if len(mot) > 3 and mot not in MOTS_OUTILS:
                        termes.update(singulier_et_pluriel(mot))
    return termes - set(MOTS_DE_LA_LANGUE)


def _chaines_du_code(chemin: Path) -> list[tuple[int, str]]:
    """Every string constant of a module, docstrings excepted (they are documentation)."""
    arbre = ast.parse(chemin.read_text("utf-8"))
    docstrings = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            corps = noeud.body
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                docstrings.add(id(corps[0].value))
    return [
        (noeud.lineno, noeud.value)
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) and id(noeud) not in docstrings
    ]


# Known and left on purpose, each one a decision of Evan's still open. ⛔ Never add
# an entry here to make the test green: remove the word from the code instead.
EXCEPTIONS_CONNUES = {
    # The example of the tool that fills the job sheet (« un Godin, il fume… »):
    # the description was written word for word and tested on 20 calls, not
    # retouched without a trial. Found by this guard on 2026-09-27.
    ("services/workflow/fiche_au_fil_de_leau.py", "godin"),
}


def mots_de_metier_dans_le_code(racines: tuple[Path, ...], termes: set[str]) -> list[str]:
    """The trade words found in the string constants of the .mark modules under ``racines``.

    Only the modules of .mark (they carry « [.mark] »): Dograh's own code writes
    English, where « insert » or « wanders » are not trade words.
    """
    trouves = []
    for chemin in sorted(c for racine in racines for c in racine.rglob("*.py")):
        if "[.mark]" not in chemin.read_text("utf-8"):
            continue
        relatif = chemin.relative_to(racines[0].parent).as_posix()
        for ligne, chaine in _chaines_du_code(chemin):
            norm = f" {normaliser_terme(chaine)} "
            for terme in sorted(termes):
                if (relatif, terme) in EXCEPTIONS_CONNUES:
                    continue
                if re.search(rf"(?<![a-z0-9]){re.escape(terme)}(?![a-z0-9])", norm):
                    trouves.append(f"{relatif}:{ligne} « {terme} »")
    return trouves


def test_aucun_mot_de_metier_nest_ecrit_dans_le_code_des_services_et_des_schemas():
    assert mots_de_metier_dans_le_code(RACINES_GARDEES, _termes_des_lexiques()) == []


def test_les_exceptions_connues_existent_encore():
    # An exception whose word has left the code must leave this list too.
    for relatif, terme in EXCEPTIONS_CONNUES:
        assert terme in normaliser_terme((API / relatif).read_text("utf-8")), (relatif, terme)




ANCIENNE_LISTE = (
    '"""[.mark] Doc: un poêle."""\n'
    'AMORCES_FORTES = frozenset({"marque", "poele", "poeles", "poil", "insert", "foyer", "chaudiere",\n'
    '    "cuisiniere", "modele", "chez", "granules", "bois", "fabricant"})\n'
)


def test_la_garde_voit_toute_lancienne_liste(tmp_path):
    # R7: the guard proven on the known red case, the old list put back whole.
    # The review of 2026-09-27 found « foyer », « chaudiere », « bois » unseen.
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "analyse.py").write_text(ANCIENNE_LISTE, "utf-8")
    trouves = mots_de_metier_dans_le_code((tmp_path / "services",), _termes_des_lexiques())
    vus = {t.split("« ")[1].rstrip(" »") for t in trouves}
    assert vus == {"poele", "poeles", "poil", "insert", "foyer", "chaudiere", "cuisiniere", "granules", "bois"}


def test_la_garde_ne_lit_pas_le_code_de_dograh(tmp_path):
    # The same file without « [.mark] » is Dograh's, written in English: not read.
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "analyse.py").write_text('AMORCES_FORTES = frozenset({"poele"})\n', "utf-8")
    assert mots_de_metier_dans_le_code((tmp_path / "services",), _termes_des_lexiques()) == []
