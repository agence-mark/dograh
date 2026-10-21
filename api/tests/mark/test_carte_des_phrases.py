"""[.mark] Chantier fiabilite-orchestration, lot 4 ter (F16, F24) : la carte des phrases dites par le code.

| Test | La garantie |
|---|---|
| inventaire | chaque endroit du code qui fait parler la voix sans le modèle est dans ``INVENTAIRE_DU_CODE`` : une phrase ajoutée sans la carte fait échouer ce test |
| carte | chaque motif, son texte en vigueur, d'où il vient, son délai, son état, ses règles d'étape |
| groupe | vue du principal : tout le groupe ; un spécialisé reprend la phrase du principal |
| dernier | le dernier déclenchement lu dans la trace des appels, par motif et par agent |
| lecture | accueil, phrases des portes et fins figées du graphe, en lecture |
"""

import re
from collections import Counter
from pathlib import Path

from api.services.phrases.carte import (
    INVENTAIRE_DU_CODE,
    AgentDeLaCarte,
    construire_la_carte,
    derniers_declenchements,
    lecture_du_graphe,
)
from api.services.phrases.catalogue import OUTIL_ECHOUE, MOTIFS, OUTIL_TARDE, PASSATION_TARDE

SERVICES = Path(__file__).resolve().parents[2] / "services"
PAROLE = re.compile(r"TTSSpeakFrame\(|queue_speech\(|\.speak\(|queue_text_message\(|_speak\(")


def test_chaque_phrase_du_code_est_dans_l_inventaire():
    trouves: Counter[str] = Counter()
    for fichier in SERVICES.rglob("*.py"):
        relatif = fichier.relative_to(SERVICES).as_posix()
        if relatif.startswith("phrases/"):
            continue  # le diseur : un endroit par motif, la carte les montre tous
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            if PAROLE.search(ligne) and not re.search(r"\bdef\s", ligne):
                trouves[relatif] += 1
    attendus = Counter({f: len(e) for f, e in INVENTAIRE_DU_CODE.items()})
    assert trouves == attendus, (
        "Un endroit du code fait parler la voix sans être dans la carte "
        "(services/phrases/carte.py, INVENTAIRE_DU_CODE) : passez-le par une règle du thème "
        "Phrases, ou inventoriez-le."
    )


def _agent(id_, reglages, **options):
    return AgentDeLaCarte(id=id_, nom=f"agent {id_}", reglages=reglages, **options)


def test_la_carte_donne_chaque_motif_en_vigueur_et_ses_etapes():
    reglages = {
        "phrases_regles": [
            {"motif": OUTIL_TARDE, "variantes": ["Je vérifie."], "delai_s": 4},
            {"motif": OUTIL_TARDE, "portee": "etape", "etape": "B", "variantes": ["Étape B."]},
        ]
    }
    carte = construire_la_carte([_agent(1, reglages)], reglages)
    (agent,) = carte["agents"]
    assert [m["motif"] for m in agent["motifs"]] == list(MOTIFS)
    outil = next(m for m in agent["motifs"] if m["motif"] == OUTIL_TARDE)
    assert (outil["variantes"], outil["delai_s"], outil["active"], outil["niveau"]) == (
        ["Je vérifie."],
        4,
        True,
        "agent",
    )
    assert outil["etapes"][0]["etape"] == "B" and outil["etapes"][0]["variantes"] == ["Étape B."]
    pont = next(m for m in agent["motifs"] if m["motif"] == PASSATION_TARDE)
    assert pont["active"] is False and pont["niveau"] == "defaut" and pont["eteinte"]["fr"]
    assert carte["actions"] and all(a["description"] for a in carte["actions"])


def test_vue_du_principal_tout_le_groupe_et_le_specialise_herite():
    principal = {
        "agents_specialises": [2],
        "phrases_regles": [
            {"motif": OUTIL_ECHOUE, "portee": "groupe", "variantes": ["Pour le groupe."]}
        ],
    }
    carte = construire_la_carte(
        [_agent(1, principal, est_principal=True), _agent(2, {})], principal
    )
    assert [a["id"] for a in carte["agents"]] == [1, 2]
    specialise = next(m for m in carte["agents"][1]["motifs"] if m["motif"] == OUTIL_ECHOUE)
    assert specialise["variantes"] == ["Pour le groupe."] and specialise["niveau"] == "principal"


def test_le_dernier_declenchement_vient_de_la_trace_des_appels():
    traces = [
        (12, "2026-10-19 10:00", [{"motif": OUTIL_ECHOUE, "agent": 1, "etape": "A", "texte": "Récent."}]),
        (11, "2026-10-18 10:00", [{"motif": OUTIL_ECHOUE, "agent": 1, "etape": "A", "texte": "Ancien."}]),
    ]
    derniers = derniers_declenchements(traces)
    carte = construire_la_carte([_agent(1, {})], {}, derniers)
    motif = next(m for m in carte["agents"][0]["motifs"] if m["motif"] == OUTIL_ECHOUE)
    assert motif["dernier"]["run"] == 12 and motif["dernier"]["texte"] == "Récent."
    jamais = next(m for m in carte["agents"][0]["motifs"] if m["motif"] == OUTIL_TARDE)
    assert jamais["dernier"] is None


def test_les_phrases_du_graphe_en_lecture():
    graphe = {
        "nodes": [
            {"id": "a", "data": {"name": "Accueil", "greeting": "Bonjour."}},
            {"id": "f", "data": {"name": "Fin", "fins": [{"phrase": "Au revoir."}]}},
        ],
        "edges": [{"source": "a", "target": "f", "data": {"transition_speech": "Je note."}}],
    }
    lignes = lecture_du_graphe(graphe)
    assert {"nature": "accueil", "endroit": "Accueil", "texte": "Bonjour."} in lignes
    assert {"nature": "fin_figee", "endroit": "Fin", "texte": "Au revoir."} in lignes
    assert {"nature": "porte", "endroit": "Accueil → Fin", "texte": "Je note."} in lignes
    assert lecture_du_graphe(None) == []


def test_la_carte_rend_au_specialise_les_regles_du_groupe_heritees():
    """Lot 5 : l'écran d'un spécialisé montre en lecture les règles « groupe » du principal."""
    principal = {
        "agents_specialises": [2],
        "phrases_regles": [
            {"motif": OUTIL_ECHOUE, "portee": "groupe", "variantes": ["Pour le groupe."]},
            {"motif": OUTIL_ECHOUE, "portee": "agent", "variantes": ["Pour le principal seul."]},
        ],
    }
    carte = construire_la_carte(
        [_agent(1, principal, est_principal=True), _agent(2, {})], principal
    )
    assert carte["agents"][0]["regles_du_groupe"] == []
    heritees = carte["agents"][1]["regles_du_groupe"]
    assert [r["variantes"] for r in heritees] == [["Pour le groupe."]]
    assert heritees[0]["portee"] == "groupe" and heritees[0]["etape_supprimee"] is False
