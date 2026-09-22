"""[.mark] Garantie : la rue dite par l'appelant est retrouvée, ou déclarée introuvable — jamais inventée.

Question du labo : **l'adresse notée est-elle la bonne rue ?** Sur les runs,
« rue Danton » s'écrivait « rue d'antan », « Rue John-Fitzgerald Kennedy »
devenait « rue Jones-phyrole-Canédie ». Le code cherche la rue dite parmi celles
de la commune retenue, et rend un verdict.

🔴 **La garantie qui prime sur toutes les autres : zéro fausse sûre.** Annoncer
« utilise ce nom » pour une rue que l'appelant n'a pas dite met une mauvaise
adresse dans la fiche, et l'agent la répète sans hésiter. Le reste — combien de
rues trouvées du premier coup — vient après.

| Section | Ce qu'elle tient |
|---|---|
| 1 | L'index de test : vrai contenu, vraies clés, vrai chemin de lecture |
| 2 | 🔴 **Zéro fausse sûre** sur les 438 cas des deux corpus |
| 3 | Ce qui est retrouvé, et ce qui ne l'est pas — chiffré, pas promis |
| 4 | Les règles payées par un défaut mesuré (fenêtres, pluriels, types) |
| 5 | Le numéro (Q5), jamais dit au modèle |
| 6 | La mention : texte exact, épellation UNE fois (Q4), idempotence |
| 7 | Les invariants comptés, dans les deux sens |

⛔ L'index complet (111 Mo, 109 départements) n'est **pas** dans ces tests : ils
tournent sur les communes du corpus, extraites du vrai index avec les mêmes
clés (`api/scripts/mark/extraire_index_de_test.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.services.communes.base import normaliser
from api.services.voies import base as base_voies
from api.services.voies.analyse import (
    A_CONFIRMER,
    INTROUVABLE,
    SURE,
    Detection,
    Proposition,
    analyser,
    est_type,
    sans_type,
)
from api.services.voies.mention import (
    MARQUE,
    deja_mentionne,
    mentionner_voie,
    phrase_de_mention,
)

DONNEES = Path(__file__).parent / "donnees"
CORPUS = json.loads((DONNEES / "voies_corpus_2026-09-22.json").read_text(encoding="utf-8"))
EXPORT_TEST = "test-2026-09-16"


@pytest.fixture(autouse=True)
def index_de_test(monkeypatch, tmp_path):
    """Les tests lisent l'index de test PAR LE CHEMIN RÉEL, décompression comprise."""
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", DONNEES / "voies")
    monkeypatch.setattr(base_voies, "EXPORT", EXPORT_TEST)
    monkeypatch.setattr(base_voies, "DOSSIER_TRAVAIL", tmp_path / "voies")
    base_voies.voies_de.cache_clear()
    yield
    base_voies.voies_de.cache_clear()


def _detecter(cas: dict) -> Detection:
    return analyser(cas["phrase"], base_voies.voies_de(cas["insee"]), cas.get("commune"))


def _meme(a: str, b: str) -> bool:
    return normaliser(a) == normaliser(b)


# --- 1. L'index de test ---------------------------------------------------


def test_lindex_de_test_porte_bien_les_communes_du_corpus():
    attendues = {cas["insee"] for cas in CORPUS}
    vides = [insee for insee in sorted(attendues) if len(base_voies.voies_de(insee)) == 0]
    assert vides == []
    assert len(attendues) == 224


def test_une_commune_se_lit_par_le_chemin_reel_decompression_comprise():
    """⛔ Le test ne lit pas un SQLite posé à côté : il passe par la
    décompression du fichier départemental, comme en appel."""
    voies = base_voies.voies_de("60057")  # Beauvais
    assert len(voies) > 500
    assert any(_meme(nom, "Rue Vincent de Beauvais") for nom in voies.noms)
    # Les clés sont STOCKÉES, pas recalculées à la lecture.
    assert all(cle for cle in voies.cles_sonores)


def test_les_cles_stockees_sont_celles_que_le_code_recalcule():
    """🔑 Le seul mécanisme qui voit une divergence entre l'index et le lecteur.

    Le 22/09, le script de génération et la recherche n'avaient pas la même
    liste de types : « Cour d'Alger » gardait son type dans sa clé, « Rue
    d'Alger » non, et la mauvaise des deux sortait SÛRE. Aucun autre test ne
    pouvait le voir. Même garde que `test_base_communes.py` pour les communes.
    """
    from api.services.communes.base import cle_phonetique, cle_sonore

    voies = base_voies.voies_de("75056")  # Paris, 5 871 voies
    for rang, nom in enumerate(voies.noms):
        coeur = sans_type(normaliser(nom))
        assert voies.cles_sonores[rang] == cle_sonore(coeur), nom
        assert voies.cles_phonetiques[rang] == cle_phonetique(coeur), nom


# --- 2. 🔴 Zéro fausse sûre -----------------------------------------------


def test_aucune_rue_fausse_nest_annoncee_sure():
    """🔴 LA garantie du module, sur les 438 cas des deux corpus."""
    fausses = []
    for cas in CORPUS:
        detection = _detecter(cas)
        if detection.statut != SURE:
            continue
        if not cas["attendu"] or not _meme(detection.retenue, cas["attendu"]):
            fausses.append((cas["phrase"], detection.retenue, cas["attendu"]))
    assert fausses == []


def test_une_rue_inexistante_nest_jamais_annoncee_sure():
    """Les 63 rues inventées : « introuvable » ou « à confirmer », jamais sûre."""
    inventees = [cas for cas in CORPUS if cas["famille"] == "inventee"]
    assert len(inventees) == 63
    assert all(_detecter(cas).statut != SURE for cas in inventees)


def test_une_phrase_sans_adresse_ne_propose_aucune_rue():
    """⛔ « C'est la maison au bout du chemin » ne doit rien faire noter."""
    sans_adresse = [
        cas for cas in CORPUS
        if cas["famille"] == "reel" and not cas["attendu"]
        and "maison au bout" in cas["phrase"]
    ]
    assert sans_adresse, "le corpus doit porter ces phrases"
    assert all(_detecter(cas).statut != SURE for cas in sans_adresse)


# --- 3. Ce qui est retrouvé, chiffré --------------------------------------


def test_toutes_les_rues_reelles_des_runs_sont_retrouvees():
    """27 phrases des runs visent une vraie rue : aucune n'est perdue."""
    attendues = [cas for cas in CORPUS if cas["famille"] == "reel" and cas["attendu"]]
    assert len(attendues) == 27
    perdues = []
    for cas in attendues:
        detection = _detecter(cas)
        tete = detection.propositions[0].nom if detection.propositions else ""
        if not tete or not _meme(tete, cas["attendu"]):
            perdues.append((cas["phrase"], tete, cas["attendu"]))
    assert perdues == []


def test_la_rue_deformee_par_la_transcription_est_rattrapee():
    """Le cas le plus dur du corpus réel : « rue Jones-phyrole-Canédie » à Creil."""
    cas = next(c for c in CORPUS if "Jones-phyrole" in c["phrase"])
    detection = _detecter(cas)
    assert detection.propositions
    assert _meme(detection.propositions[0].nom, "Rue John Kennedy")


def test_le_corpus_sonore_reste_au_niveau_mesure_le_22_09():
    """⛔ Un plancher, pas une promesse. 300 rues réelles dites en 8 kHz puis
    transcrites : un banc PLUS DUR que le casque, qui sert à comparer deux
    versions du lecteur, pas à annoncer un taux au client.

    Mesuré le 22/09 : 234 retrouvées (135 sûres, 99 en tête d'un « à confirmer »).
    Ce test rougit si une modification fait retomber le lecteur.
    """
    sonores = [cas for cas in CORPUS if cas["famille"] == "sonore"]
    assert len(sonores) == 300
    trouvees = 0
    for cas in sonores:
        detection = _detecter(cas)
        tete = detection.propositions[0].nom if detection.propositions else ""
        if tete and _meme(tete, cas["attendu"]):
            trouvees += 1
    assert trouvees >= 225, f"{trouvees} retrouvées, 234 le 22/09"


# --- 4. Les règles payées par un défaut mesuré ----------------------------


def test_une_fenetre_partielle_ne_suffit_pas_a_etre_sure():
    """« allée des Mésanges Dorées » n'existe pas à Bury ; « Rue des Mésanges »
    si. Sans la pénalité sur les mots laissés de côté, la seconde sortait SÛRE
    (15 fausses sûres sur 156 cas tenaient à ce seul défaut)."""
    detection = analyser(
        "j'habite allée des Mésanges Dorées à Bury", base_voies.voies_de("60116"), "Bury"
    )
    assert detection.statut != SURE


@pytest.mark.parametrize("mot", ["rue", "rues", "impasse", "impasses", "places", "chemins"])
def test_les_pluriels_sont_des_types_de_voie(mot):
    """⛔ « 79 rues de la mairie » : la faute la plus fréquente de la
    transcription, et sans elle rien ne s'ancre."""
    assert est_type(mot)


def test_une_voie_dont_le_nom_est_un_type_garde_son_nom():
    """« Grande Rue » est un nom de voie, pas un type suivi d'un nom."""
    assert sans_type(normaliser("Grande Rue")) == "grande rue"
    assert sans_type(normaliser("Rue de la République")) == "republique"


def test_la_commune_est_retiree_du_passage_compare():
    """« rue des Tilleuls à Beauvais » se comparait « tilleuls a beauvais »."""
    voies = base_voies.voies_de("60057")
    avec = analyser("12 rue Vincent de Beauvais à Beauvais", voies, "Beauvais")
    assert avec.propositions
    assert _meme(avec.propositions[0].nom, "Rue Vincent de Beauvais")


# --- 5. Le numéro (Q5) ----------------------------------------------------


def test_le_numero_dit_est_verifie_sur_la_voie_retenue():
    voies = base_voies.voies_de("60057")
    rang = next(r for r, nom in enumerate(voies.noms) if voies.numeros[r])
    numero = sorted(voies.numeros[rang])[0]
    detection = analyser(f"{numero} {voies.noms[rang]}", voies, None)
    assert detection.propositions
    assert detection.propositions[0].numero_present is True


def test_sans_numero_dit_le_champ_reste_vide():
    voies = base_voies.voies_de("60057")
    detection = analyser("rue Vincent de Beauvais", voies, None)
    assert detection.propositions
    assert detection.propositions[0].numero_present is None


def test_la_mention_ne_parle_jamais_du_numero():
    """Q5 : une base incomplète ne doit pas faire répéter l'appelant."""
    detection = Detection(SURE, "rue machin", (Proposition("Rue Danton", 99.0, False),))
    phrase = phrase_de_mention(detection)
    assert "numéro" not in phrase.lower()
    assert "numero" not in phrase.lower()


# --- 6. La mention --------------------------------------------------------


def test_le_texte_de_la_mention_sure():
    detection = Detection(SURE, "rue d'antan", (Proposition("Rue Danton", 95.0),))
    assert phrase_de_mention(detection) == (
        "[Vérification de la rue : « rue d'antan » correspond à Rue Danton. "
        "Utilise ce nom sans le faire répéter.]"
    )


def test_le_texte_de_la_mention_introuvable_fait_epeler_une_fois():
    """Q4 : une seule épellation, jamais de boucle — une base n'est jamais
    complète, et faire répéter son adresse à un appelant est pire que de noter
    une rue que la base ignore."""
    detection = Detection(INTROUVABLE, "rue du Lavoira")
    phrase = phrase_de_mention(detection)
    assert "ne correspond à aucune rue de la commune" in phrase
    assert "une seule fois" in phrase
    assert phrase.count("épeler") == 1


def test_le_texte_de_la_mention_a_confirmer_propose_puis_fait_epeler():
    detection = Detection(
        A_CONFIRMER, "rue de bray",
        (Proposition("Rue de Bray", 88.0), Proposition("Rue du Bray", 86.0)),
    )
    phrase = phrase_de_mention(detection)
    assert "Demande d'abord si c'est Rue de Bray" in phrase
    assert "propose Rue du Bray" in phrase
    assert "une seule fois" in phrase


def test_la_mention_ne_touche_pas_au_texte_de_lappelant():
    texte = "c'est au 6 rue d'antan"
    detection = Detection(SURE, "rue d'antan", (Proposition("Rue Danton", 95.0),))
    annote = mentionner_voie(texte, detection)
    assert annote.startswith(texte)
    assert deja_mentionne(annote)
    assert not deja_mentionne(texte)


def test_sans_rien_entendu_le_texte_est_rendu_intact():
    texte = "bonjour, je voudrais un rendez-vous"
    assert mentionner_voie(texte, Detection(INTROUVABLE, "")) is texte
    assert mentionner_voie(texte, None) is texte


# --- 7. Les invariants, dans les deux sens --------------------------------


def test_une_voie_sure_est_toujours_une_voie_de_la_commune():
    """Sens direct : ce qui est annoncé sûr existe dans la commune de l'appel."""
    for cas in CORPUS:
        detection = _detecter(cas)
        if detection.statut != SURE:
            continue
        noms = base_voies.voies_de(cas["insee"]).noms
        assert detection.retenue in noms


def test_une_mention_suppose_toujours_une_detection_et_reciproquement():
    """Sens inverse ET comptage : sans le compte, un lecteur qui rendrait
    « introuvable » partout passerait toutes les gardes ci-dessus."""
    avec_mention = sures = 0
    for cas in CORPUS:
        detection = _detecter(cas)
        annote = mentionner_voie(cas["phrase"], detection)
        porte_mention = deja_mentionne(annote)
        # Une mention est écrite si et seulement si quelque chose a été entendu.
        assert porte_mention == bool(detection.entendu)
        avec_mention += porte_mention
        sures += detection.statut == SURE
    # Et ces totaux ne sont pas zéro.
    assert avec_mention >= 400
    assert sures >= 150
