"""[.mark] Une adresse mail n'est jamais lue comme commune (chantier actions-sures-et-parite-clavier, lot C).

Plan `Labo-agent-vocal/plans/actions-sures-et-parite-clavier/`. Run 2040 (banc de fin du 27/10) : l'agent demande
« Pourriez-vous me donner votre adresse mail ? », la personne tape « marc.henry@gmail.com ». Deux défauts de lecture :
le mot « adresse » de la question était pris pour un signe de lieu, et une adresse ÉCRITE n'était pas abritée (seule une
adresse dictée l'était). « marc » est devenu la commune sûre Marcq (78770), qui a remplacé Creil dans la recherche et la
réservation. Aucune étape n'est interdite à la lecture des communes : seule la lecture est réparée.

| Test | Ce qu'il prouve |
|---|---|
| signe de lieu | « adresse mail », « adresse e-mail », « adresse électronique » ne sont pas des questions de lieu ; « adresse » seule, si |
| run 2040 | après « votre adresse mail ? », « marc.henry@gmail.com » ne produit aucune commune, et le texte arrive intact |
| la commune reste lue | « c'est à Creil, et mon mail marc.henry@gmail.com » : Creil est lue, rien dans l'adresse |
"""

from types import SimpleNamespace

import pytest

from api.schemas.organization_preferences import AdresseEtablissement
from api.services.communes.force import signe_de_lieu
from api.services.pipecat.lecture_appelant import lire_texte
from api.services.pipecat.verification_communes import CLE_TRACE

QUESTION_MAIL = "Pourriez-vous me donner votre adresse mail, s'il vous plaît ?"


@pytest.mark.parametrize(
    "question",
    [QUESTION_MAIL, "Et votre adresse e-mail ?", "Quelle est votre adresse électronique ?", "Votre adresse courriel ?"],
)
def test_une_question_d_adresse_mail_n_est_pas_un_signe_de_lieu(question):
    assert signe_de_lieu("marc.henry@gmail.com", question) is False


@pytest.mark.parametrize(
    "question, texte",
    [
        ("Quelle est l'adresse de l'intervention ?", "Creil"),
        (QUESTION_MAIL, "j'habite Creil"),
        (None, "mon adresse c'est 8 rue Pasteur"),
    ],
)
def test_une_vraie_question_ou_parole_de_lieu_reste_un_signe(question, texte):
    assert signe_de_lieu(texte, question) is True


class _Registre:
    def __init__(self):
        self.entrees: dict[str, list] = {}

    def __call__(self, entree: dict, cle: str) -> None:
        self.entrees.setdefault(cle, []).append(entree)


async def _lire(texte: str, question: str | None) -> tuple[str, list]:
    registre = _Registre()
    lu = await lire_texte(
        texte,
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin"),
        noeud=SimpleNamespace(
            name="rendez_vous_entretien",
            extraction_variables=[SimpleNamespace(name=n) for n in ("commune", "code_postal", "email")],
        ),
        consigner=registre,
        voies=True,
        epellation=True,
        champs_fiche=("nom", "prenom", "commune", "code_postal", "adresse_intervention", "email"),
        question_avant=question,
    )
    return lu, registre.entrees.get(CLE_TRACE, [])


async def test_run_2040_une_adresse_mail_ecrite_ne_produit_aucune_commune():
    lu, communes = await _lire("marc.henry@gmail.com", QUESTION_MAIL)
    assert lu.startswith("marc.henry@gmail.com")
    assert not any("Marcq" in str(c) for c in communes), communes
    assert communes == [], communes


async def test_la_commune_dite_a_cote_d_une_adresse_mail_reste_lue():
    lu, communes = await _lire("c'est à Creil, et mon mail marc.henry@gmail.com", None)
    assert "marc.henry@gmail.com" in lu
    # Creil est lue (« à confirmer » face à Créteil, comme avant ce chantier) ; rien n'est lu dans l'adresse.
    assert [c.get("entendu") for c in communes] == ["Creil"], communes
    assert "Marcq" not in str(communes), communes
