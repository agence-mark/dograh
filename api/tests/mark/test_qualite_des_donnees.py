"""[.mark] Non-regression test of the data quality (chantier l-agent-collegue, L7; plan
qualite-des-donnees, lots 2 to 4, QD1 to QD8, Q-1, Q-2).

The questions this file answers:

    With the agent's « Check the data » on, at a step that collects a phone, is a number dictated
    with 9 or 11 digits said to the model, word for word as the plan wrote it -- and is EVERY
    other reading identical to the character (other steps, switch off, amounts, references with
    letters)? At the end of the call, through the REAL after-call, is the record checked, its
    verdict written with the call and said in the mail -- and is no value ever changed?

⚠️ What this file does NOT prove: the bench (a real voice, a real extraction).
"""

from __future__ import annotations

import copy
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.fiche.controle import controler, correspond
from api.services.pipecat.lecture_appelant import lire_message_tape, lire_texte

ETAPE_TEL = SimpleNamespace(name="coordonnees", extraction_variables=[SimpleNamespace(name="telephone")])
ETAPE_MOTIF = SimpleNamespace(name="motif", extraction_variables=[SimpleNamespace(name="motif")])
TEL = ("telephone*", "tel_*", "portable*", "numero_telephone*", "rappel_numero*")

NEUF = "c'est le zéro six douze trente-quatre cinquante-six sept"
DIX = "c'est le zéro six douze trente-quatre cinquante-six soixante-dix-huit"
ONZE = "c'est le zéro six douze trente-quatre cinquante-six soixante-dix-huit neuf"
PLUS_HUIT = "plus trente-trois six douze trente-quatre cinquante-six sept"


async def _lire(texte, noeud, variables_tel, champs_fiche=None):
    return await lire_texte(
        texte, conversion=True, verification=False, langue_francaise=True, adresse=None,
        noeud=noeud, consigner=None, variables_tel=variables_tel, champs_fiche=champs_fiche,
    )


# --------------------------------------------------------------------------- #
# Lot 2: the phone with a digit too many or too few (QD7)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "texte, n",
    [(NEUF, 9), (ONZE, 11), (PLUS_HUIT, 9), ("mon numéro c'est zéro six douze trente-quatre cinquante-six sept", 9)],
)
async def test_un_numero_incomplet_est_dit_a_une_etape_de_telephone(texte, n):
    lu = await _lire(texte, ETAPE_TEL, TEL)
    assert lu.endswith(f"a {n} chiffres au lieu de 10. Fais-le répéter avant de le noter.]")
    assert "[Lecture des nombres : le numéro entendu « " in lu


@pytest.mark.parametrize("texte", [NEUF, DIX, ONZE, PLUS_HUIT,
                                   "la facture fait deux cent mille euros",
                                   "la référence A B zéro douze trente-quatre cinquante-six sept huit"])
async def test_hors_etape_de_telephone_ou_interrupteur_eteint_rien_ne_change_au_caractere_pres(texte):
    avant = await _lire(texte, ETAPE_TEL, None)  # switch off: the reading of before
    assert await _lire(texte, ETAPE_MOTIF, TEL) == avant
    assert await _lire(texte, ETAPE_TEL, ()) == avant


async def test_dix_chiffres_restent_un_telephone_sans_mention():
    assert await _lire(DIX, ETAPE_TEL, TEL) == await _lire(DIX, ETAPE_TEL, None)


async def test_fiche_allumee_aucune_note_la_trace_dit_le_numero_incomplet():
    traces = []

    def consigner(entree, cle):
        traces.append((cle, entree))

    lu = await lire_texte(NEUF, conversion=True, verification=False, langue_francaise=True, adresse=None,
                          noeud=ETAPE_MOTIF, consigner=consigner, variables_tel=TEL, champs_fiche=("telephone",))
    assert "[Lecture des nombres" not in lu
    assert [e["type"] for c, e in traces if c == "nombres_lus"] == ["telephone_incomplet"]


async def test_au_clavier_le_reglage_de_l_agent_decide():
    stt = SimpleNamespace(language="fr")
    allume = {"conversion_nombres_transcription": True, "controle_donnees": True}
    lu = await lire_message_tape(NEUF, allume, stt, None, ETAPE_TEL, None)
    assert "a 9 chiffres au lieu de 10" in lu
    eteint = {"conversion_nombres_transcription": True}
    assert await lire_message_tape(NEUF, eteint, stt, None, ETAPE_TEL, None) == await _lire(NEUF, ETAPE_TEL, None)
    # A custom list replaces the default.
    perso = {**allume, "variables_telephone": "joignable"}
    assert "chiffres au lieu de 10" not in await lire_message_tape(NEUF, perso, stt, None, ETAPE_TEL, None)


# --------------------------------------------------------------------------- #
# Lot 3: the record checked, never changed (QD2, QD3, QD8)
# --------------------------------------------------------------------------- #

NOMS = {"telephone": TEL, "code_postal": ("code_postal*", "cp_*"), "courriel": ("email*", "courriel*", "mail*"),
        "date": ("date*",), "commune": ("commune", "commune_*", "adresse*")}
JOUR = date(2026, 10, 7)


class Communes:
    def __init__(self):
        self.par_cp = {"60100": ["Creil"], "60000": ["Beauvais"]}
        self.par_nom = {"creil": [0], "beauvais": [1]}

    def communes_du_code_postal(self, cp):
        return [SimpleNamespace(nom=n) for n in self.par_cp.get(cp, [])]


def _verdict(fiche, attendus=()):
    from api.services.communes.base import normaliser

    return controler(fiche, noms=NOMS, champs_attendus=attendus, jour_appel=JOUR, base_communes=Communes(), normaliser=normaliser)


@pytest.mark.parametrize(
    "fiche, code, voisin",
    [
        ({"telephone": "06 12 34 56 7"}, "telephone_invalide", {"telephone": "+33 6 12 34 56 78"}),
        ({"code_postal": "60999"}, "code_postal_inconnu", {"code_postal": "60100"}),
        ({"code_postal": "60100", "commune": "Beauvais"}, "commune_code_postal_incoherents", {"code_postal": "60100", "commune": "Creil"}),
        ({"email": "jean.dupont@@exemple"}, "courriel_invalide", {"email": "jean.dupont@exemple.fr"}),
        ({"email": "jean@gmial.com"}, "courriel_domaine_douteux", {"email": "jean@gmail.com"}),
        ({"date_intervention": "bientôt"}, "date_invalide", {"date_intervention": "2026-10-09"}),
        ({"date_intervention": "1950-01-01"}, "date_improbable", {"date_intervention": "octobre 2025"}),
    ],
)
def test_chaque_code_et_un_voisin_qui_ne_le_declenche_pas(fiche, code, voisin):
    assert [p["code"] for p in _verdict(fiche)["problemes"]] == [code]
    assert _verdict(voisin) == {"statut": "complete", "problemes": []}


def test_domaine_douteux_propose_sans_corriger_et_adresse_jamais_comparee_a_la_commune():
    fiche = {"email": "jean@gmial.com", "code_postal": "60100", "adresse_chantier": "3 rue des Lilas Beauvais"}
    avant = copy.deepcopy(fiche)
    verdict = _verdict(fiche)
    assert verdict["problemes"] == [{"champ": "email", "code": "courriel_domaine_douteux", "valeur": "jean@gmial.com",
                                     "detail": "gmial.com, peut-être gmail.com"}]
    assert fiche == avant  # QD8: nothing changed


def test_champ_vide_seulement_pour_les_etapes_traversees():
    verdict = _verdict({"nom": "Dupont"}, attendus=["nom", "telephone"])
    assert verdict["statut"] == "a_reprendre" and verdict["problemes"] == [
        {"champ": "telephone", "code": "champ_vide", "valeur": None, "detail": None}]
    assert _verdict({"nom": "Dupont"}, attendus=["nom"])["statut"] == "complete"


def test_un_nom_personnalise_est_reconnu_et_une_panne_ne_coute_rien():
    assert correspond("portable_pro", ("portable*",)) and not correspond("tel", ("telephone*",))
    perso = {**NOMS, "telephone": ("joignable",)}
    from api.services.communes.base import normaliser

    assert controler({"joignable": "12"}, noms=perso, jour_appel=JOUR, normaliser=normaliser)["statut"] == "a_reprendre"

    class EnPanne(Communes):
        def communes_du_code_postal(self, cp):
            raise RuntimeError("panne")

    assert controler({"code_postal": "60100"}, noms=NOMS, jour_appel=JOUR, base_communes=EnPanne(),
                     normaliser=normaliser) == {"statut": "non_controle", "problemes": []}


# --------------------------------------------------------------------------- #
# Lot 4: the settings (QD1)
# --------------------------------------------------------------------------- #


def test_les_reglages_refusent_un_nom_illisible_et_vide_vaut_defaut():
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults.model_validate({"variables_telephone": "t*"})
    vide = WorkflowConfigurationDefaults.model_validate({"variables_courriel": "  "})
    assert vide.variables_courriel == "email*, courriel*, mail*"
    assert WorkflowConfigurationDefaults().controle_donnees is False


# --------------------------------------------------------------------------- #
# Through the REAL after-call (Q-2): written with the call, said in the mail
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("allume", [True, False])
async def test_apres_lappel_le_verdict_est_ecrit_avec_l_appel_et_dit_dans_le_mail(
    allume, base_v4, smtp, modele, db_session, async_session
):
    from api.db.bases_clients import connexion as schema
    from api.tasks.workflow_completion import process_workflow_completion
    from api.tests.mark import test_apres_appel as t

    org = await t._organisation(async_session, db_session)
    org.definition.workflow_configurations = {**org.definition.workflow_configurations, "controle_donnees": allume}
    org.definition.workflow_json = {"nodes": [
        {"id": "1", "data": {"name": "coordonnees", "extraction_enabled": True,
                             "extraction_variables": [{"name": "telephone"}, {"name": "email"}, {"name": "nom"}]}},
        {"id": "2", "data": {"name": "jamais_atteinte", "extraction_enabled": True,
                             "extraction_variables": [{"name": "date_rdv"}]}},
    ], "edges": []}
    await async_session.flush()
    await t._regler(db_session, org, base_v4, smtp)
    await t._equipe(base_v4)
    run = await t._run(db_session, org)
    fiche = {**run.gathered_context["extracted_variables"], "email": "jean@gmial.com"}
    await db_session.update_workflow_run(run.id, gathered_context={
        **run.gathered_context, "extracted_variables": fiche, "nodes_visited": ["coordonnees"]})
    with patch("api.tasks.arq.enqueue_job", await t._executer_tout_de_suite([])):
        await process_workflow_completion(None, run.id)

    connexion = await schema.connecter(base_v4)
    try:
        brut = await connexion.fetchval("SELECT qualite_fiche FROM mark.appel WHERE dograh_run_id = $1", run.id)
        champs = {r["nom"]: r["valeur"] for r in await connexion.fetch("SELECT nom, valeur FROM mark.champ_appel")}
    finally:
        await connexion.close()
    assert champs["email"] == "jean@gmial.com"  # QD8: written as the extraction left it
    [texte] = smtp.textes()
    bloc = await db_session.lire_apres_appel(run.id)
    if not allume:
        assert brut is None and "Fiche à reprendre" not in texte and "qualite_fiche" not in bloc
        return
    verdict = json.loads(brut) if isinstance(brut, str) else brut
    assert verdict["statut"] == "a_reprendre"
    assert sorted(p["code"] for p in verdict["problemes"]) == ["champ_vide", "courriel_domaine_douteux"]
    # QD2: the field of the step never reached is not expected.
    assert [p["champ"] for p in verdict["problemes"] if p["code"] == "champ_vide"] == ["telephone"]
    assert "⚠ Fiche à reprendre :" in texte and "gmial.com, peut-être gmail.com" in texte
    assert bloc["qualite_fiche"]["statut"] == "a_reprendre"


# Fixtures of the after-call's tests (a real client database, an SMTP stand-in, a model stand-in).
from api.tests.mark.test_apres_appel import base_v4, modele, smtp  # noqa: E402, F401
from api.tests.mark.test_base_client import base_essai  # noqa: E402, F401
