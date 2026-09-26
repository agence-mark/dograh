"""[.mark] The cues before a name come from the vocabulary, never from the code (question 249).

The questions this file answers:

    Does « les poêles sont chers » stay free of any brand (« sont » is not
    « Sohn »)? Does « c'est un poêle Royal » read Royal because the vocabulary
    carries « poêle » as a trade word, and read nothing once that word is
    removed from the vocabulary? Does a vocabulary of ANOTHER trade (a
    restaurant: « vin », « champagne ») work with no line of code added? And is
    no word of a trade vocabulary written in the code of ``api/services``?

Why it exists
-------------
Plan ``2026-09-27-plan-amorces-du-lexique.md`` (question 249, decisions D1 to
D3 of Evan, 2026-09-27). Until then, ``AMORCES_FORTES`` listed stove words in
``analyse.py``: at a restaurant the mechanism stopped working, unless the fork
was patched. Evan's rule: zero trade word in the code.

The route is the real one: ``corriger_texte`` of the pipeline, on an index
built by ``construire_index``, as a call runs it.

⚠️ What this file does NOT prove: what the transcription writes on a real call
(the phone bench decides), nor that the production vocabulary carries its trade
words (to check on the screen before deploying).
"""

import ast
import json
import re
from pathlib import Path

import pytest

from api.schemas.lexique_metier import LexiqueMetier, normaliser_terme
from api.services.communes.base import charger_base
from api.services.pipecat.reconnaissance_lexique import construire_index, corriger_texte

DONNEES = Path(__file__).parent / "donnees"
SERVICES = Path(__file__).resolve().parents[2] / "services"


@pytest.fixture(scope="module", autouse=True)
def _base_communes():
    """The list of communes, loaded once: without it the vocabulary reads nothing (T16)."""
    charger_base()


def _lexique(*termes: dict) -> LexiqueMetier:
    return LexiqueMetier.model_validate({"termes": list(termes)})


async def _corrige(texte: str, lexique: LexiqueMetier) -> str:
    return await corriger_texte(texte, construire_index(lexique))


POELE = {"terme": "poêle", "type": "mot"}
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
    {"terme": "vin", "type": "mot"},
    {"terme": "champagne", "type": "mot"},
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


def _termes_des_lexiques() -> set[str]:
    """The terms of the trade vocabularies known to .mark (recopied from the socle)."""
    termes: set[str] = set()
    for fichier in ("lexique_poeles_2026-09-16.json", "lexique_mots_poeles_2026-09-27.json"):
        for terme in json.loads((DONNEES / fichier).read_text("utf-8"))["termes"]:
            for ecrit in [terme["terme"], *terme.get("variantes", [])]:
                norm = normaliser_terme(ecrit)
                if len(norm) > 2:
                    termes.add(norm)
    return termes


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
    ("workflow/fiche_au_fil_de_leau.py", "godin"),
}


def mots_de_metier_dans_le_code(racine: Path, termes: set[str]) -> list[str]:
    """The trade words found in the string constants of the .mark modules under ``racine``.

    Only the modules of .mark (they carry « [.mark] »): Dograh's own code writes
    English, where « insert » or « wanders » are not trade words.
    """
    trouves = []
    for chemin in sorted(racine.rglob("*.py")):
        if "[.mark]" not in chemin.read_text("utf-8"):
            continue
        relatif = chemin.relative_to(racine).as_posix()
        for ligne, chaine in _chaines_du_code(chemin):
            norm = f" {normaliser_terme(chaine)} "
            for terme in sorted(termes):
                if (relatif, terme) in EXCEPTIONS_CONNUES:
                    continue
                if re.search(rf"(?<![a-z0-9]){re.escape(terme)}(?![a-z0-9])", norm):
                    trouves.append(f"{relatif}:{ligne} « {terme} »")
    return trouves


def test_aucun_mot_de_metier_nest_ecrit_dans_le_code_des_services():
    assert mots_de_metier_dans_le_code(SERVICES, _termes_des_lexiques()) == []


def test_les_exceptions_connues_existent_encore():
    # An exception whose word has left the code must leave this list too.
    for relatif, terme in EXCEPTIONS_CONNUES:
        assert terme in normaliser_terme((SERVICES / relatif).read_text("utf-8")), (relatif, terme)


def test_la_garde_voit_un_mot_de_metier(tmp_path):
    # R7: the guard proven on the known red case, the old list put back.
    (tmp_path / "analyse.py").write_text(
        '"""[.mark] Doc: un poêle."""\nAMORCES_FORTES = frozenset({"marque", "poele", "insert", "chez"})\n', "utf-8"
    )
    trouves = mots_de_metier_dans_le_code(tmp_path, _termes_des_lexiques())
    assert sorted(trouves) == ["analyse.py:2 « insert »", "analyse.py:2 « poele »"]
    # The same file outside .mark (no « [.mark] ») is Dograh's: not read.
    (tmp_path / "analyse.py").write_text('AMORCES_FORTES = frozenset({"poele"})\n', "utf-8")
    assert mots_de_metier_dans_le_code(tmp_path, _termes_des_lexiques()) == []
