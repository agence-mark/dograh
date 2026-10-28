"""[.mark] passages-fiables, correctifs de la clôture (formulaire d'Evan, 29/10).

| Test | La garantie |
|---|---|
| retenues au tri | chaque retenue de la vérité des actions (date inconnue, écriture qui tient, réplique retenue) est écrite dans ``gathered_context["retenues_verite"]``, lue par la file de tri, trouvée par le filtre de la base ; le comportement de la retenue ne change pas |
| textes alignés | le motif de phrase ``attente_accordee`` porte le nom de la case de l'écran, en français et en anglais |
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.services.phrases.catalogue import ATTENTE_ACCORDEE, motif
from api.services.tri import donnees
from api.services.workflow.verite_des_actions import (
    CLE_RETENUES,
    GENRE_DATE_INCONNUE,
    GENRE_ECRITURE_QUI_TIENT,
    MAX_RETENUES_PAR_APPEL,
    RAISON_ACTION,
    RAISON_DATE,
    VerificateurDeReplique,
    tracer_une_retenue,
)
from api.tests.mark.test_annulation_d_un_rendez_vous import CHERCHER, RESERVER, Banc

RACINE = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_une_date_que_la_recherche_n_a_pas_donnee_est_retenue_et_tracee_au_run():
    banc = Banc()
    banc.fiche["tour_appelant"] = 3
    await banc.appeler(CHERCHER, jour="semaine du 3 novembre")
    rendu = await banc.appeler(RESERVER, debut="2026-11-09T10:00:00+01:00", nom="Durand")
    assert rendu["statut"] == "incomplet" and not banc.executions[RESERVER]  # comportement inchangé
    (retenue,) = banc.fiche[CLE_RETENUES]
    assert retenue["genre"] == GENRE_DATE_INCONNUE and retenue["outil"] == RESERVER and retenue["tour"] == 3
    assert "9" in retenue["detail"]
    json.dumps(banc.fiche)  # le run se sauvegarde tel quel


@pytest.mark.asyncio
async def test_une_ecriture_qui_tient_deja_est_retenue_et_tracee_au_run():
    banc = Banc()
    banc.fiche["tour_appelant"] = 4
    await banc.reserver()
    assert CLE_RETENUES not in banc.fiche  # rien d'anormal : rien au tri
    rendu = await banc.appeler(RESERVER, nom="Durand")
    assert rendu["garde"] == "ecriture_qui_tient"
    (retenue,) = banc.fiche[CLE_RETENUES]
    assert retenue["genre"] == GENRE_ECRITURE_QUI_TIENT and retenue["outil"] == RESERVER and retenue["tour"] == 4


def test_une_replique_retenue_est_tracee_au_run_et_une_replique_saine_ne_laisse_rien():
    banc = Banc()
    verificateur = VerificateurDeReplique(banc.moteur, banc.agent)
    assert verificateur.controler("J'ai bien noté votre numéro.", []) is None
    assert CLE_RETENUES not in banc.fiche
    assert verificateur.controler("Le 9 novembre.", []).raison == RAISON_DATE
    assert verificateur.controler("Votre rendez-vous est confirmé.", []).raison == RAISON_ACTION
    assert [r["genre"] for r in banc.fiche[CLE_RETENUES]] == [RAISON_DATE, RAISON_ACTION]


def test_la_trace_est_bornee_et_ne_leve_jamais():
    banc = Banc()
    for _ in range(MAX_RETENUES_PAR_APPEL + 5):
        tracer_une_retenue(banc.moteur, GENRE_DATE_INCONNUE, outil="x")
    assert len(banc.fiche[CLE_RETENUES]) == MAX_RETENUES_PAR_APPEL
    tracer_une_retenue(None, "x")
    tracer_une_retenue(type("M", (), {"_gathered_context": None})(), "x")


def test_la_file_de_tri_lit_les_retenues_et_le_filtre_de_la_base_les_trouve():
    contexte = {
        CLE_RETENUES: [
            {"genre": GENRE_DATE_INCONNUE, "outil": "reserver", "detail": "lundi 9 novembre", "tour": 3},
            {"genre": RAISON_ACTION, "outil": None, "detail": "c'est réservé", "tour": 5},
        ]
    }
    lignes = donnees.lire_les_signalements(contexte)
    assert [ligne["type"] for ligne in lignes] == [donnees.TYPE_RETENUE] * 2
    assert len({ligne["id"] for ligne in lignes}) == 2 and {ligne["source"] for ligne in lignes} == {"code"}
    assert lignes[0]["motif"] == "date_non_trouvee : reserver : lundi 9 novembre"
    assert lignes[1]["motif"] == "action_sans_resultat : c'est réservé" and lignes[1]["tour"] == 5
    assert CLE_RETENUES in donnees.CLES_LUES_POUR_LE_TRI
    assert f"exists(@.{CLE_RETENUES}[*])" in donnees.chemin_des_runs_a_trier()
    assert donnees.lire_les_signalements({CLE_RETENUES: "bizarre"}) == []


def test_le_motif_attente_accordee_porte_le_nom_de_la_case_de_l_ecran():
    m = motif(ATTENTE_ACCORDEE)
    assert "Laisser l'appelant prendre son temps" in m.quand_fr
    assert "Let the caller take their time" in m.quand_en
    assert "Laisser la personne" not in m.quand_fr and m.libelle_fr == "L'appelant prend son temps"
    ecran = (RACINE / "ui/src/components/mark/reglages-agent/catalogue.tsx").read_text(encoding="utf-8")
    assert 'fr: "Laisser l\'appelant prendre son temps"' in ecran and f"« {m.libelle_fr} »" in ecran
