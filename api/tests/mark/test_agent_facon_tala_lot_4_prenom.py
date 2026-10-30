"""[.mark] agent-facon-tala, lot 4 (C6) : le filtre du nom couvre aussi le prénom noté dans la fiche.

Relevé du 30/10 (S5, casque 2447) : après la prise de nom, l'agent redisait « Bertin. » seul (le prénom noté dans la
fiche). Même case que le nom (``interdire_nom_appelant``), pas de nouvelle.

| Test | Ce qu'il prouve |
|---|---|
| prénom | le prénom de la fiche part, y compris coupé en morceaux par le flux du modèle (la vraie chaîne) |
| même case | éteinte (le défaut) : rien ne part, nom et prénom ; la case du nom éteinte mais la civilité allumée : le prénom reste |
| règles du nom | majuscule requise, jamais une adresse, jamais épelé, jamais touché dans la fiche |
| nom et prénom | « Bertin Faucheux » en une phrase part en entier, sans ponctuation orpheline |
| sans prénom | une fiche sans prénom : le comportement d'avant |
| clavier | le filtre du clavier (``creer_filtre_nom_civilite``, même fonction que le téléphone) lit le prénom |
"""

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.tests import run_test
from pipecat.tests.utils import SleepFrame

from api.services.pipecat.filtre_nom_civilite import (
    FiltreNomCiviliteProcessor,
    creer_filtre_nom_civilite,
    retirer_nom_et_civilite,
)
from api.tests.mark.test_filtre_nom_civilite_branchement import DEMARRAGE_S, _Aval


def _filtre(variables, **interrupteurs):
    return FiltreNomCiviliteProcessor(
        retirer_nom=interrupteurs.get("retirer_nom", True),
        retirer_civilite=interrupteurs.get("retirer_civilite", False),
        variables=lambda: dict(variables),
        mode_envoi="sentence",
    )


async def _jouer(processeur, morceaux):
    aval = _Aval()
    await run_test(
        Pipeline([processeur, aval]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            *[LLMTextFrame(m) for m in morceaux],
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )
    return "".join(aval.textes)


@pytest.mark.asyncio
async def test_le_prenom_de_la_fiche_part_meme_coupe_en_morceaux():
    # S5 : « Bertin. » redit seul après la prise de nom.
    sortie = await _jouer(
        _filtre({"nom": "Faucheux", "prenom": "Bertin"}),
        ["D'accord, c'est noté.", " Bert", "in.", " Et votre", " adresse ?"],
    )
    assert "Bertin" not in sortie
    assert sortie.strip() == "D'accord, c'est noté. Et votre adresse ?"


@pytest.mark.asyncio
async def test_nom_et_prenom_dans_la_meme_phrase_partent_sans_ponctuation_orpheline():
    sortie = await _jouer(
        _filtre({"nom": "Faucheux", "prenom": "Bertin"}),
        ["Merci, Bertin", " Faucheux", ", je note", " votre demande."],
    )
    assert "Bertin" not in sortie and "Faucheux" not in sortie
    assert sortie.strip() == "Merci je note votre demande."  # encadré par ses virgules : elles partent avec lui, comme pour le nom seul


@pytest.mark.asyncio
async def test_case_eteinte_le_prenom_reste_dit():
    sortie = await _jouer(
        _filtre({"nom": "Faucheux", "prenom": "Bertin"}, retirer_nom=False, retirer_civilite=True),
        ["Bertin.", " Et votre", " adresse ?"],
    )
    assert "Bertin" in sortie


@pytest.mark.asyncio
async def test_sans_prenom_dans_la_fiche_le_comportement_d_avant():
    sortie = await _jouer(
        _filtre({"nom": "Faucheux"}), ["Merci Faucheux.", " Bertin est", " un prénom, non ?"]
    )
    assert "Faucheux" not in sortie
    assert "Bertin est un prénom" in sortie


def test_les_regles_du_nom_valent_pour_le_prenom():
    # Le mot ordinaire en minuscules reste : « marc » dans une phrase n'est pas la personne.
    assert retirer_nom_et_civilite("Il boit du marc.", "Marc", retirer_nom=True) == "Il boit du marc."
    # Une adresse n'est pas la personne : « rue Bertin » chez un appelant prénommé Bertin.
    assert (
        retirer_nom_et_civilite("Vous êtes rue Bertin ?", "Bertin", retirer_nom=True)
        == "Vous êtes rue Bertin ?"
    )
    # Épelé (une lettre après l'autre), le prénom reste : l'épellation confirme.
    assert "B, E, R, T, I, N" in retirer_nom_et_civilite("B, E, R, T, I, N.", "Bertin", retirer_nom=True)
    # Un prénom à particule ou composé part en entier.
    assert "Marie" not in retirer_nom_et_civilite("Merci Marie-Anne, c'est noté.", "Marie-Anne", retirer_nom=True)


@pytest.mark.asyncio
async def test_la_fiche_n_est_jamais_touchee():
    variables = {"nom": "Faucheux", "prenom": "Bertin"}
    await _jouer(_filtre(variables), ["Merci Bertin Faucheux."])
    assert variables == {"nom": "Faucheux", "prenom": "Bertin"}


def test_le_filtre_du_clavier_lit_le_prenom_comme_le_telephone():
    """``creer_filtre_nom_civilite`` est l'unique fabrique (téléphone : ``run_pipeline`` et
    ``agent_runtime_factory`` ; clavier : ``text_chat_runner``) ; la case est celle du nom."""
    filtre = creer_filtre_nom_civilite(
        {"interdire_nom_appelant": True}, lambda: {"nom": "Faucheux", "prenom": "Bertin"}
    )
    assert filtre is not None
    assert filtre._filtrer("Bertin.") == ""
    assert filtre._filtrer("Merci, Bertin Faucheux, c'est noté.") == "Merci c'est noté."
    # Case éteinte : pas de filtre du tout.
    assert creer_filtre_nom_civilite({}, lambda: {"prenom": "Bertin"}) is None
