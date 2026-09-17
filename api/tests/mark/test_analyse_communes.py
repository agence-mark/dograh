"""[.mark] Non-regression test for recognising the town a caller names.

The questions this file answers:

    Replayed on the bench of the 2026-09-16 trial, does the fork's analysis
    still give what the prototype gave: no town announced sure and wrong, at
    least 48 of 56 sure and right with the shop nearby? And does the note the
    model reads say, word for word, what the plan fixed?

Why it exists
-------------
"Beauvais" was transcribed "Beauvet" then "Bovet". The analysis was tuned on
that bench; a threshold moved, a rule lost in a rewrite, and the model would
be told a wrong town is certain. 🔴 That is the one failure that costs a
customer a wasted trip, and only a replay of the whole bench sees it.

The bench (``donnees/communes_banc_2026-09-16.json``) holds texts only: the
reference shop is "Saint-Maximin (60)", with no company name.
"""

import json
from pathlib import Path

import pytest

from api.services.communes.analyse import A_CONFIRMER, SURE, analyser
from api.services.communes.base import charger_base
from api.services.communes.mention import MARQUE, deja_mentionne, mentionner

BANC = json.loads(
    (Path(__file__).parent / "donnees" / "communes_banc_2026-09-16.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees(BANC["magasin_de_reference"]["insee"])


def _verdicts(base, magasin):
    """Each sentence of the bench, classified like the trial's banc4.py."""
    verdicts = []
    for element in BANC["avec_commune"]:
        attendu = (element["commune"], element["departement"])
        verdict = "manquee"
        for detection in analyser(element["phrase"], base, magasin):
            noms = [(l.commune.nom, l.commune.dep) for l in detection.lectures]
            if detection.statut == SURE:
                verdict = "sure_juste" if noms[0] == attendu else "sure_fausse"
            elif noms and noms[0] == attendu:
                verdict = "a_confirmer_juste_en_tete"
            elif attendu in noms:
                verdict = "a_confirmer_juste_dedans"
            if verdict != "manquee":
                break
        verdicts.append((element["phrase"], verdict))
    return verdicts


def _sures(base, magasin, phrases):
    return sorted(
        (phrase, detection.lectures[0].commune.nom)
        for phrase in phrases
        for detection in analyser(phrase, base, magasin)
        if detection.statut == SURE
    )


# --------------------------------------------------------------------------- #
# 1. The trial's bench, replayed
# --------------------------------------------------------------------------- #


def test_banc_avec_le_magasin_aucune_sure_fausse(base, magasin):
    verdicts = _verdicts(base, magasin)
    # Counted: a bench that stopped reading its sentences would pass empty.
    assert len(verdicts) == 56
    compte = {v: sum(1 for _, x in verdicts if x == v) for _, v in verdicts}
    assert compte.get("sure_fausse", 0) == 0, verdicts
    assert compte.get("sure_juste", 0) >= 48
    # Reference result of the prototype, for the record: 48 sure and right,
    # 6 + 1 to confirm with the right town proposed, 1 missed.
    assert [p for p, v in verdicts if v == "manquee"] == ["Crêpe il en Valois"]


def test_banc_sans_magasin_pas_plus_de_sures_fausses_que_le_prototype(base):
    verdicts = _verdicts(base, None)
    assert len(verdicts) == 56
    fausses = sorted(p for p, v in verdicts if v == "sure_fausse")
    # The prototype's two, named: without a location clue, "Crêpe il" lands
    # on Crépey (54) and "Brêle" on Brélès (29). Known limit, not a target.
    assert fausses == ["Crêpe il en Valois", "à Brêle"]


def test_phrases_sans_commune_fausses_sures_connues(base, magasin):
    """Known limits, named one by one. ⛔ Not a target: never add to this list
    to make the test pass; a new false "sure" is a regression."""
    assert len(BANC["adresses_sans_commune"]) == 25
    assert len(BANC["phrases_du_labo"]) == 64

    # Real towns the callers of the lab did say: these are right.
    vraies = {"Beauvais", "Creil", "Compiègne", "Senlis", "Chantilly"}

    adresses_avec = _sures(base, magasin, BANC["adresses_sans_commune"])
    adresses_sans = _sures(base, None, BANC["adresses_sans_commune"])
    assert adresses_avec == [("à la campagne", "Campagne")]
    assert adresses_sans == []

    labo_avec = [s for s in _sures(base, magasin, BANC["phrases_du_labo"]) if s[1] not in vraies]
    labo_sans = [s for s in _sures(base, None, BANC["phrases_du_labo"]) if s[1] not in vraies]
    assert labo_avec == [("Depuis avant-hier", "Deuillet")]
    assert labo_sans == [
        (
            "Bonjour, je voulais savoir où en est ma commande, j'ai vu quelqu'un "
            "il y a trois semaines",
            "Troyes",
        ),
        ("C'est un poêle à bois, un Godin", "Bois"),
    ]


# --------------------------------------------------------------------------- #
# 2. The cases that motivated the patch
# --------------------------------------------------------------------------- #


def test_les_transcriptions_du_labo_menent_a_beauvais(base, magasin):
    (beauvet,) = analyser("c'est à Beauvet", base, magasin)
    assert beauvet.statut == SURE
    assert (beauvet.lectures[0].commune.nom, beauvet.lectures[0].commune.dep) == ("Beauvais", "60")

    # "Bovet" IS another real town's sound (Boves, 80): even with the shop
    # nearby it stays to be confirmed, with Beauvais proposed. That is the
    # prototype's result too, and the right one: never announced sure.
    (bovet,) = analyser("j'habite à Bovet", base, magasin)
    assert bovet.statut == A_CONFIRMER
    assert ("Beauvais", "60") in [(l.commune.nom, l.commune.dep) for l in bovet.lectures]


def test_chercher_dans_toute_la_phrase_est_exclu(base, magasin):
    """⛔ v2 of the trial read "avec" as Hanvec and "deux" as Dreux."""
    assert analyser(
        "je voudrais passer avec deux personnes pour voir un poêle", base, magasin
    ) == []


def test_un_nom_apres_un_type_de_voie_est_une_rue(base, magasin):
    detections = analyser("au 12 rue de la gare à Sanlis", base, magasin)
    assert [d.lectures[0].commune.nom for d in detections] == ["Senlis"]


# --------------------------------------------------------------------------- #
# 3. The note, word for word
# --------------------------------------------------------------------------- #


def test_mention_sure_au_mot_pres(base, magasin):
    texte = "c'est à Beauvet"
    assert mentionner(texte, analyser(texte, base, magasin), base) == (
        "c'est à Beauvet [Vérification de la commune : « Beauvet » correspond à "
        "Beauvais (60000, Oise). Utilise ce nom sans le faire répéter.]"
    )


def test_mention_incertaine_au_mot_pres(base):
    texte = "à Sanlis"
    detections = analyser(texte, base, None)
    assert [d.statut for d in detections] == [A_CONFIRMER]
    assert mentionner(texte, detections, base) == (
        "à Sanlis [Vérification de la commune : « Sanlis » peut être Senlis (60300, Oise), "
        "Senlis (62310, Pas-de-Calais) ou Saint-Lys (31470, Haute-Garonne). "
        "Demande d'abord si c'est Senlis (Oise) ; si ce n'est pas elle, propose Senlis (Pas-de-Calais), "
        "puis Saint-Lys (Haute-Garonne). "
        "Nomme chaque commune avec son département. "
        "Si aucune ne convient, fais préciser la commune ou son code postal avant de la noter.]"
    )


def test_mention_garde_le_code_postal_dit(base):
    """The postal code shown is the one the caller said, when it is the town's."""
    texte = "Beaumont 95260"
    assert mentionner(texte, analyser(texte, base, None), base) == (
        "Beaumont 95260 [Vérification de la commune : « Beaumont » correspond à "
        "Beaumont-sur-Oise (95260, Val-d'Oise). Utilise ce nom sans le faire répéter.]"
    )


def test_mention_garde_ce_qui_a_ete_ecrit(base, magasin):
    """« entendu » is the transcription's own spelling, hyphens included."""
    texte = "c'est à Pont-Saint-Maxence"
    (detection,) = analyser(texte, base, magasin)
    assert detection.entendu == "Pont-Saint-Maxence"


def test_aucune_detection_texte_inchange(base, magasin):
    texte = "c'est pour un entretien annuel"
    assert analyser(texte, base, magasin) == []
    assert mentionner(texte, [], base) == texte


def test_la_marque_ouvre_chaque_mention(base, magasin):
    texte = "à Beauvet"
    mentionne = mentionner(texte, analyser(texte, base, magasin), base)
    assert MARQUE == "[Vérification de la commune"
    assert mentionne.count(MARQUE) == 1
    assert deja_mentionne(mentionne)
    assert not deja_mentionne(texte)


# --------------------------------------------------------------------------- #
# 4. Plan nombres-dictes: billing words, departments, postal codes read in words
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase", ["le devis faisait 15000 euros", "c'est la commande 60300"]
)
def test_n6_un_mot_de_facturation_nest_pas_une_commune(base, magasin, phrase):
    """N6, even without the reader: Devise (80) and Lacommande (64) were sure."""
    assert [d for d in analyser(phrase, base, magasin) if d.statut == SURE] == []


def test_le_departement_dit_departage(base):
    """"Sanlis" hesitates between Senlis (60) and Senlis (62): the Oise said decides."""
    sans = analyser("à Sanlis", base, None)
    avec = analyser("à Sanlis", base, None, departements={"60"})
    assert sans[0].statut == A_CONFIRMER
    assert (avec[0].statut, avec[0].lectures[0].commune.dep) == (SURE, "60")


def test_les_mots_dun_code_postal_lu_ne_sont_pas_une_commune(base, magasin):
    """With the reader's spans, the words of a postal code anchor the town next
    to them and are never read as a town themselves."""
    texte = "Saint-Maximin soixante sept cent quarante"
    spans = {"60740": [(2, 6)], "67140": [(2, 6)]}
    (d,) = analyser(texte, base, magasin, codes_postaux=spans)
    assert (d.statut, d.lectures[0].commune.nom, d.fin) == (SURE, "Saint-Maximin", 2)
