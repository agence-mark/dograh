"""[.mark] Chantier correctifs-apres-banc-commun, lot 3 : fiche et greffier (K2, K10, K6a, K6b, K6c, V3).

| Test | La garantie |
|---|---|
| K2 garde après les passes | la garde de l'étape attend les passes en cours (1,5 s au plus) avant de rendre « incomplet » ; aucun coût quand rien ne manque ni quand rien ne tourne ; le gestionnaire enveloppé et l'outil « confier » s'en servent |
| K10 numéro non dit | un numéro dont les chiffres ne sont pas dans la parole n'est pas écrit (champ vide, consigne « il manque des chiffres ») ; complet, dicté en deux fois, zéro de tête absent, correction par paires : écrits |
| K6a date | « l'année dernière, en octobre » se lit « octobre l'an dernier » |
| K6b consigne | le greffier lit « ne sait pas » ≠ « refuse » |
| K6c accent | nom épelé sans type d'accent, forme accentuée dite dans l'appel : la forme accentuée est écrite |
| V3 nom épelé | à la question du nom, les lettres épelées remplissent le nom, un prénom qui recopiait le nom est corrigé ; la règle de recopie du balayage ne bloque jamais un nom épelé |
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from api.services.groupe.notes import nom_lisible  # noqa: F401 -- la garde l'importe
from api.services.pipecat.greffier import REGLES_D_ECRITURE, consigne_du_greffier
from api.services.workflow.dates_relatives import lire_expression
from api.services.workflow.enveloppe_des_actions import (
    garde_de_l_etape,
    garde_de_l_etape_apres_les_notes,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CLE_MODE,
    CLE_TOUR,
    MODE_GREFFIER,
    TRACE_EPELLATIONS,
    ReglagesFiche,
    chiffres_dits,
    ecrire_dans_la_fiche,
    forme_accentuee_dite,
    reponse_de_l_outil,
)
from api.tests.mark.test_correctifs_fiche_et_fond import CHAMPS, ETAPE, _config
from api.tests.mark.test_greffier import _Modele, _Montage

# --------------------------------------------------------------------------- #
# K2 : la garde attend les passes en cours
# --------------------------------------------------------------------------- #


def _moteur_et_agent(montage, notes=()):
    moteur = SimpleNamespace(
        _fiche=montage.reglages, _gathered_context=montage.fiche, notes_en_cours=set(notes)
    )
    agent = SimpleNamespace(current_node=SimpleNamespace(champs_etape=ETAPE))
    return moteur, agent


def _montage_presque_complet():
    montage = _Montage(_Modele(), _config())
    montage.fiche.update(
        {"prenom": "Marc", "nom": "Petit", "email": "m@exemple.fr", "numero_dicte": "0655443322"}
    )
    return montage


async def test_k2_la_garde_attend_la_passe_en_cours_et_relit_la_fiche():
    """Run 1510 : « manque … » juste après les avoir dits, la passe du greffier du même tour finit juste après."""
    montage = _montage_presque_complet()

    async def la_passe_du_greffier():
        await asyncio.sleep(0.2)
        montage.fiche["urgence"] = "normal"

    tache = asyncio.ensure_future(la_passe_du_greffier())
    moteur, agent = _moteur_et_agent(montage, [tache])
    # Le verdict immédiat est « incomplet » (c'est le défaut) ; avec l'attente, plus rien ne manque.
    assert garde_de_l_etape(moteur, agent) == {"statut": "incomplet", "manque": ["urgence"]}
    assert await garde_de_l_etape_apres_les_notes(moteur, agent) is None


async def test_k2_une_passe_trop_lente_ne_bloque_pas_plus_que_le_delai(monkeypatch):
    import api.services.workflow.enveloppe_des_actions as enveloppe

    monkeypatch.setattr(enveloppe, "DELAI_DES_NOTES_DE_LA_GARDE", 0.05)
    montage = _montage_presque_complet()
    tache = asyncio.ensure_future(asyncio.sleep(5))
    moteur, agent = _moteur_et_agent(montage, [tache])
    try:
        debut = asyncio.get_running_loop().time()
        refus = await garde_de_l_etape_apres_les_notes(moteur, agent)
        assert asyncio.get_running_loop().time() - debut < 1
        assert refus == {"statut": "incomplet", "manque": ["urgence"]}
    finally:
        tache.cancel()


async def test_k2_aucun_cout_quand_rien_ne_manque_ou_que_rien_ne_tourne():
    montage = _montage_presque_complet()
    montage.fiche["urgence"] = "normal"
    tache = asyncio.ensure_future(asyncio.sleep(5))
    moteur, agent = _moteur_et_agent(montage, [tache])
    try:
        debut = asyncio.get_running_loop().time()
        assert await garde_de_l_etape_apres_les_notes(moteur, agent) is None
        assert asyncio.get_running_loop().time() - debut < 0.5  # rien manquait : pas d'attente
    finally:
        tache.cancel()
    # Rien ne tourne : le verdict est celui d'avant.
    montage.fiche.pop("urgence")
    moteur, agent = _moteur_et_agent(montage)
    assert await garde_de_l_etape_apres_les_notes(moteur, agent) == garde_de_l_etape(moteur, agent)


async def test_k2_le_gestionnaire_enveloppe_attend_la_passe():
    from api.services.workflow.enveloppe_des_actions import envelopper_l_action

    montage = _montage_presque_complet()

    async def la_passe_du_greffier():
        await asyncio.sleep(0.1)
        montage.fiche["urgence"] = "normal"

    tache = asyncio.ensure_future(la_passe_du_greffier())
    moteur, agent = _moteur_et_agent(montage, [tache])
    rendus, appels = [], []

    async def gestionnaire(params):
        appels.append(1)
        await params.result_callback({"statut": "fait"})

    async def rendre(resultat, *a, **k):
        rendus.append(resultat)

    params = SimpleNamespace(result_callback=rendre, llm=None, tool_call_id="x")
    await envelopper_l_action(moteur, "reserver", gestionnaire, agent)(params)
    assert appels == [1]
    assert rendus and rendus[-1].get("statut") != "incomplet"


# --------------------------------------------------------------------------- #
# K10 : un numéro n'est écrit que si ses chiffres sont dans la parole
# --------------------------------------------------------------------------- #


async def _numero_note(parole, ecrit, **suite):
    montage = _Montage(_Modele({"numero_dicte": ecrit}), _config())
    montage.messages = [{"role": "user", "content": parole}]
    await montage.passe()
    return montage


async def test_k10_huit_chiffres_dits_dix_ecrits_le_champ_reste_vide():
    """Run 1507 : « 0612345656 » écrit et noté sûr pour huit chiffres dictés."""
    montage = await _numero_note("zéro six douze trente-quatre cinquante-six", "0612345656")
    assert "numero_dicte" not in montage.fiche
    journal = montage.fiche[CLE_JOURNAL]
    assert (journal[-1]["champ"], journal[-1]["statut"], journal[-1]["raison"]) == (
        "numero_dicte",
        "refuse",
        "chiffres_non_dits",
    )
    # Le refus est redit au greffier à la passe suivante.
    assert any(r["raison"] == "chiffres_non_dits" for r in montage.greffier._refus)


async def test_k10_la_consigne_dit_qu_il_manque_des_chiffres():
    montage = await _numero_note("06 12 34 56", "0612345656")
    note = SimpleNamespace(
        ecrits=[],
        retenus={},
        refuses=[{"champ": "numero_dicte", "raison": "chiffres_non_dits"}],
        a_confirmer=[],
        a_proposer=[],
    )
    resultat = reponse_de_l_outil(note)
    assert "il manque des chiffres" in resultat["consigne"]
    assert "numero_dicte" not in montage.fiche


@pytest.mark.parametrize(
    "paroles, ecrit",
    [
        (["06 12 34 56 78"], "0612345678"),
        (["zéro six douze trente-quatre cinquante-six soixante-dix-huit"], "0612345678"),
        (["c'est le 06 12 34", "56 78"], "0612345678"),  # dicté en deux fois
    ],
)
async def test_k10_un_numero_complet_est_ecrit(paroles, ecrit):
    montage = _Montage(_Modele({"numero_dicte": ecrit}), _config())
    montage.messages = [{"role": "user", "content": p} for p in paroles]
    await montage.passe()
    assert montage.fiche.get("numero_dicte") == ecrit


def test_k10_chiffres_dits_ne_leve_jamais_et_doute_vaut_vrai():
    assert chiffres_dits("", ["rien"]) is True
    assert chiffres_dits("0612345678", ["06 12 34"]) is False
    assert chiffres_dits("0612345678", [object()]) is not None


async def test_k10_une_correction_par_paires_passe_toujours():
    """Lot C d'avant : « c'est pas 47, c'est 74 » corrige une paire d'un numéro déjà noté."""
    montage = _Montage(_Modele({"numero_dicte": "0674455566"}), _config())
    montage.fiche.update({"numero_dicte": "0647455566"})
    montage.messages = [
        {"role": "user", "content": "06 47 45 55 66"},
        {"role": "user", "content": "non, pas quarante-sept, soixante-quatorze"},
    ]
    await montage.passe()
    assert montage.fiche["numero_dicte"] == "0674455566"


# --------------------------------------------------------------------------- #
# K6a, K6b
# --------------------------------------------------------------------------- #

JOUR = datetime(2026, 10, 23)


@pytest.mark.parametrize(
    "texte, dit, attendu",
    [
        ("L'année dernière, en octobre", "L'année dernière, en octobre", "10/2025"),
        ("l'an dernier au mois de mars", "l'an dernier au mois de mars", "03/2025"),
        ("cette année en juin", "cette année en juin", "06/2026"),
        ("c'était l'année dernière", "l'année dernière", "2025"),  # sans mois : inchangé
        ("octobre l'an dernier", "octobre l'an dernier", "10/2025"),  # le sens d'avant : inchangé
    ],
)
def test_k6a_le_mois_apres_l_annee_relative_est_garde(texte, dit, attendu):
    assert lire_expression(texte, JOUR) == (dit, attendu)


def test_k6b_le_greffier_sait_que_ne_pas_savoir_n_est_pas_refuser():
    montage = _Montage(_Modele(), _config())
    consigne = consigne_du_greffier(montage.reglages, None)
    assert "Ne pas savoir n'est pas refuser" in consigne
    assert "Ne pas savoir n'est pas refuser" in REGLES_D_ECRITURE
    assert "jamais « refusé »" in consigne


# --------------------------------------------------------------------------- #
# K6c : l'accent
# --------------------------------------------------------------------------- #


def test_k6c_forme_accentuee_dite():
    assert forme_accentuee_dite("Lefevre", ["Je m'appelle Lefèvre"]) == "Lefèvre"
    assert forme_accentuee_dite("LEFEVRE", ["Lefèvre"]) == "LEFÈVRE"
    assert forme_accentuee_dite("Lefevre", ["Lefevre"]) is None  # rien d'accentué dit
    assert forme_accentuee_dite("Lefevre", ["Lemaire"]) is None  # autres lettres


def _fiche_epelee(epele, tour=3):
    return {CLE_TOUR: tour, TRACE_EPELLATIONS: [{"tour": tour, "epele": epele, "entendu": "e f"}]}


def _reglages_noms():
    return ReglagesFiche.depuis(_config())


def test_k6c_le_nom_epele_sans_accent_garde_la_forme_accentuee_dite():
    """Run 1496 : « Lefèvre, avec un accent sur le premier E » donnait Lefevre."""
    reglages, fiche = _reglages_noms(), _fiche_epelee("Lefevre")
    paroles = ["Mon nom c'est Lefèvre", "L E F E V R E, avec un accent sur le premier E"]
    verdict = ecrire_dans_la_fiche(
        fiche, reglages, "nom", "Lefevre", source=MODE_GREFFIER, paroles=paroles
    )
    assert verdict.statut == "ecrit" and fiche["nom"] == "Lefèvre"


def test_k6c_sans_forme_accentuee_dite_l_epellation_reste_telle_quelle():
    reglages, fiche = _reglages_noms(), _fiche_epelee("Lefevre")
    ecrire_dans_la_fiche(
        fiche, reglages, "nom", "Lefevre", source=MODE_GREFFIER, paroles=["L E F E V R E"]
    )
    assert fiche["nom"] == "Lefevre"


# --------------------------------------------------------------------------- #
# V3 : le nom épelé
# --------------------------------------------------------------------------- #

QUESTION_DU_NOM = "Quel est votre nom ?"


def test_v3_les_lettres_epelees_remplissent_le_nom_et_corrigent_le_prenom_recopie():
    """Run 1515 : « Marc Henry » transcrit « Henri » ; H-E-N-R-Y n'y changeait rien."""
    reglages, fiche = _reglages_noms(), _fiche_epelee("Henry")
    fiche["prenom"] = "Henri"
    fiche["fiche_etat"] = {"prenom": {"sure": True, "source": MODE_GREFFIER}}
    paroles = ["Marc Henri", "H E N R Y"]
    verdict = ecrire_dans_la_fiche(
        fiche, reglages, "prenom", "Henri", source=MODE_GREFFIER, paroles=paroles, question=QUESTION_DU_NOM
    )
    assert (verdict.statut, verdict.raison) == ("refuse", "epele_pour_nom")
    assert fiche["nom"] == "Henry"
    assert "prenom" not in fiche  # recopié du nom : vidé, la passe suivante l'écrit (« Marc »)
    verdict = ecrire_dans_la_fiche(
        fiche, reglages, "prenom", "Marc", source=MODE_GREFFIER, paroles=paroles, question=QUESTION_DU_NOM
    )
    assert verdict.statut == "ecrit" and fiche["prenom"] == "Marc"


def test_v3_le_nom_ecrit_directement_passe_comme_avant():
    reglages, fiche = _reglages_noms(), _fiche_epelee("Henry")
    verdict = ecrire_dans_la_fiche(
        fiche, reglages, "nom", "Henri", source=MODE_GREFFIER, paroles=["Marc Henri", "H E N R Y"],
        question=QUESTION_DU_NOM,
    )
    assert verdict.statut == "ecrit" and fiche["nom"] == "Henry"


def test_v3_a_la_question_du_prenom_rien_n_est_redirige():
    reglages, fiche = _reglages_noms(), _fiche_epelee("Marc")
    verdict = ecrire_dans_la_fiche(
        fiche, reglages, "prenom", "Mark", source=MODE_GREFFIER, paroles=["M A R C"],
        question="Quel est votre prénom ?",
    )
    assert verdict.statut == "ecrit" and fiche["prenom"] == "Marc"
    assert "nom" not in fiche


def test_v3_un_prenom_sans_rapport_avec_les_lettres_n_est_pas_touche():
    reglages, fiche = _reglages_noms(), _fiche_epelee("Henry")
    fiche["prenom"] = "Marc"
    verdict = ecrire_dans_la_fiche(
        fiche, reglages, "prenom", "Marc", source=MODE_GREFFIER,
        paroles=["Marc Henri", "H E N R Y"], question=QUESTION_DU_NOM,
    )
    assert verdict.statut == "ecrit" and fiche["prenom"] == "Marc"


async def test_v3_la_recopie_du_balayage_ne_bloque_pas_un_nom_epele():
    from api.services.workflow.fiche_au_fil_de_leau import _recopie_d_un_autre_champ

    reglages, fiche = _reglages_noms(), _fiche_epelee("Henry")
    fiche["prenom"] = "Henry"
    assert _recopie_d_un_autre_champ(reglages, fiche, "nom", "Henry") is None
    # Sans épellation, la règle d'avant joue.
    sans = {"prenom": "Henry"}
    assert _recopie_d_un_autre_champ(reglages, sans, "nom", "Henry") == "prenom"
