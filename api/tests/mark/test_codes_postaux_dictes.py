"""[.mark] Non-regression test for postal codes said in words, and the towns they point to.

The questions this file answers:

    When a postal code is said in words and two readings exist, is it decided
    by the town said, the town of the call so far, the department said or a
    single reading, and otherwise left TO CONFIRM? Do amounts and references
    stay out of the town check? And does the bench of 2026-09-16, passed
    through the reader, still give no town announced sure and wrong?

Why it exists
-------------
At the bench of 2026-09-16 no postal code said in words ever reached the town
check, and "le devis faisait 15000 euros" announced Devise (80) as sure. In the
Oise, "soixante deux cents" is Compiègne (60200) OR Calais (62100): a rule that
picks one without a clue announces a wrong town to the caller as certain.
🔴 "0 town announced sure and wrong" is the rule this file keeps.
"""

import json
from pathlib import Path

import pytest

from api.services.communes.analyse import A_CONFIRMER, SURE
from api.services.communes.base import charger_base
from api.services.communes.mention import mentionner
from api.services.nombres.lecture import (
    PAR_COMMUNE_DITE,
    PAR_DEPARTEMENT,
    PAR_LECTURE_UNIQUE,
    PAR_PROXIMITE,
    PAR_TRACE,
    analyser_message,
    reecrire,
)

BANC = json.loads(
    (Path(__file__).parent / "donnees" / "communes_banc_2026-09-16.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees(BANC["magasin_de_reference"]["insee"])


def _trace(lecture):
    """The entries the call records for a message (as ``trace_de`` writes them)."""
    return [
        {
            "statut": d.statut,
            "commune_retenue": {"code_insee": d.lectures[0].commune.insee} if d.statut == SURE else None,
            "propositions": [{"code_insee": l.commune.insee} for l in d.lectures[:3]],
        }
        for d in lecture.detections
    ]


def _lu(texte, base, magasin, trace=None):
    """(what the model reads, the message's reading)."""
    r = analyser_message(texte, base, magasin, trace)
    return mentionner(reecrire(texte, r.nombres, r.choix_cp), r.detections, base), r


def _code(r):
    (choix,) = r.choix.values()
    return choix


# --------------------------------------------------------------------------- #
# 1. The bench of 2026-09-16, passed through the reader
# --------------------------------------------------------------------------- #


def test_banc_passe_par_le_lecteur_aucune_sure_fausse(base, magasin):
    verdicts = []
    for element in BANC["avec_commune"]:
        attendu = (element["commune"], element["departement"])
        verdict = "manquee"
        for d in analyser_message(element["phrase"], base, magasin).detections:
            noms = [(l.commune.nom, l.commune.dep) for l in d.lectures]
            if d.statut == SURE:
                verdict = "sure_juste" if noms[0] == attendu else "sure_fausse"
            elif attendu in noms:
                verdict = "a_confirmer_juste"
            if verdict != "manquee":
                break
        verdicts.append((element["phrase"], verdict))
    assert len(verdicts) == 56
    assert [p for p, v in verdicts if v == "sure_fausse"] == []
    assert sum(1 for _, v in verdicts if v == "sure_juste") >= 48


def test_phrases_sans_commune_pas_plus_de_fausses_sures_quavant(base, magasin):
    """The known false "sure" of ``test_analyse_communes.py``, not one more."""
    vraies = {"Beauvais", "Creil", "Compiègne", "Senlis", "Chantilly"}

    def sures(phrases):
        return sorted(
            (p, d.lectures[0].commune.nom)
            for p in phrases
            for d in analyser_message(p, base, magasin).detections
            if d.statut == SURE and d.lectures[0].commune.nom not in vraies
        )

    assert len(BANC["adresses_sans_commune"]) == 25
    assert len(BANC["phrases_du_labo"]) == 64
    assert sures(BANC["adresses_sans_commune"]) == [("à la campagne", "Campagne")]
    assert sures(BANC["phrases_du_labo"]) == [("Depuis avant-hier", "Deuillet")]


# --------------------------------------------------------------------------- #
# 2. N2, one case per branch
# --------------------------------------------------------------------------- #


def test_n2_commune_dite_dans_le_message(base, magasin):
    lu, r = _lu("Saint-Maximin soixante sept cent quarante", base, magasin)
    assert (_code(r).code, _code(r).statut, _code(r).par) == ("60740", "sure", PAR_COMMUNE_DITE)
    assert lu == (
        "Saint-Maximin 60740 [Vérification de la commune : « Saint-Maximin » correspond à "
        "Saint-Maximin (60740, Oise). Utilise ce nom sans le faire répéter.]"
    )


def test_n2_commune_retenue_au_tour_precedent(base, magasin):
    _, avant = _lu("Saint-Maximin", base, magasin)
    lu, r = _lu("soixante sept cent quarante", base, magasin, _trace(avant))
    assert (_code(r).code, _code(r).statut, _code(r).par) == ("60740", "sure", PAR_TRACE)
    assert lu.startswith("60740 [Vérification de la commune : « soixante sept cent quarante » correspond à Saint-Maximin (60740, Oise).")


def test_n2_commune_a_confirmer_puis_code_postal(base, magasin):
    _, avant = _lu("j'habite à Bovet", base, magasin)
    (bovet,) = avant.detections
    assert bovet.statut == A_CONFIRMER
    lu, r = _lu("soixante mille", base, magasin, _trace(avant))
    assert (_code(r).code, _code(r).statut, _code(r).par) == ("60000", "sure", PAR_TRACE)
    # Decision of Evan, 2026-09-16: the code is sure, but 60000 also carries
    # Allonne and Goincourt and « Bovet » was not heard exactly: Beauvais is
    # proposed first, to confirm.
    (beauvais,) = r.detections
    assert (beauvais.statut, beauvais.lectures[0].commune.nom) == (A_CONFIRMER, "Beauvais")
    assert "correspond à" not in lu


def test_n2_departement_dit(base, magasin):
    lu, r = _lu("soixante deux cents, dans l'Oise", base, magasin)
    assert (_code(r).code, _code(r).statut, _code(r).par) == ("60200", "sure", PAR_DEPARTEMENT)
    assert lu.startswith("60200, dans l'Oise")


def test_n2_rien_pour_trancher_a_confirmer_au_plus_proche(base, magasin):
    lu, r = _lu("soixante deux cents", base, magasin)
    assert (_code(r).code, _code(r).statut, _code(r).par) == ("60200", "a_confirmer", PAR_PROXIMITE)
    # ⛔ Never sure on proximity alone.
    assert lu == (
        "60200 [Vérification de la commune : « soixante deux cents » peut être "
        "Compiègne (60200, Oise) ou Calais (62100, Pas-de-Calais). "
        "Fais préciser la commune avant de la noter.]"
    )


def test_n2_une_seule_lecture(base, magasin):
    lu, r = _lu("quatre-vingt-quinze huit cent vingt", base, magasin)
    assert (_code(r).code, _code(r).statut, _code(r).par) == ("95820", "sure", PAR_LECTURE_UNIQUE)
    assert lu.startswith("95820 [Vérification de la commune : « quatre-vingt-quinze huit cent vingt » correspond à Bruyères-sur-Oise")


def test_un_code_postal_sur_de_plusieurs_communes_fait_preciser_la_commune(base, magasin):
    lu, r = _lu("code postal soixante mille", base, magasin)
    assert (_code(r).code, _code(r).statut) == ("60000", "sure")
    (d,) = r.detections
    assert d.statut == A_CONFIRMER and d.code_postal_entendu
    assert lu.endswith("Fais préciser la commune avant de la noter.]")
    assert lu.startswith("code postal 60000 [Vérification de la commune : « soixante mille » peut être Beauvais (60000, Oise)")


def test_la_variante_ne_touche_pas_une_commune_entendue(base):
    """A name heard keeps « la commune ou son code postal »."""
    lu, _ = _lu("à Sanlis", base, None)
    assert lu.endswith("Fais préciser la commune ou son code postal avant de la noter.]")


# --------------------------------------------------------------------------- #
# 3. N6: amounts and references stay out of the town check
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase",
    [
        "le devis faisait quinze mille euros",
        "ma facture numéro douze mille",
        "c'est la commande 60300",
        "commande numéro soixante mille trois cents",
        "le devis faisait 15000 euros",
        "ma facture numéro 12000",
    ],
)
def test_n6_aucune_commune_aucun_code_postal(base, magasin, phrase):
    lu, r = _lu(phrase, base, magasin)
    assert r.detections == []
    assert r.choix == {}
    assert "[Vérification de la commune" not in lu


# --------------------------------------------------------------------------- #
# 4. The case missed at the bench
# --------------------------------------------------------------------------- #


def test_verneuil_en_halatte_dit_en_mots(base, magasin):
    lu, r = _lu("Verneuil-en-Halatte soixante mille cinq cent cinquante", base, magasin)
    (d,) = r.detections
    assert (d.statut, d.lectures[0].commune.nom) == (SURE, "Verneuil-en-Halatte")
    assert (_code(r).code, _code(r).par) == ("60550", PAR_COMMUNE_DITE)
    assert lu.startswith("Verneuil-en-Halatte 60550 [")


@pytest.mark.parametrize(
    "phrase,commune,code",
    [
        ("Compiègne, soixante deux cents", "Compiègne", "60200"),
        ("Chantilly, soixante cinq cents", "Chantilly", "60500"),
        ("Saint-Leu-d'Esserent, soixante trois cent quarante", "Saint-Leu-d'Esserent", "60340"),
        ("c'est à Senlis soixante trois cents", "Senlis", "60300"),
        ("Beaumont-sur-Oise quatre-vingt-quinze deux cent soixante", "Beaumont-sur-Oise", "95260"),
        ("c'est à Breteuil soixante cent vingt", "Breteuil", "60120"),
    ],
)
def test_fiches_commune_et_code_postal_dits(base, magasin, phrase, commune, code):
    _, r = _lu(phrase, base, magasin)
    (d,) = r.detections
    assert (d.statut, d.lectures[0].commune.nom) == (SURE, commune)
    assert (_code(r).code, _code(r).statut) == (code, "sure")


# --------------------------------------------------------------------------- #
# 5. The whole set of dictated sentences: no number becomes a town
# --------------------------------------------------------------------------- #


def test_aucun_telephone_montant_reference_ni_expression_figee_ne_devient_une_commune(base, magasin):
    """Found at lot 3: a phone dictated in words at the address step proposed
    "zéro six" as Clairoix, "plus" as Plou, and "mille mercis" read Millay as sure.
    Both ways and counted over the 39 sentences of ``nombres_dictes.json``."""
    jeu = json.loads(
        (Path(__file__).parent / "donnees" / "nombres_dictes.json").read_text(encoding="utf-8")
    )["phrases"]
    communes = {}
    for element in jeu:
        r = analyser_message(element["phrase"], base, magasin)
        communes[element["phrase"]] = [(d.lectures[0].commune.nom, d.statut) for d in r.detections]
    assert len(communes) == 39

    # Where a town is expected: the postal codes of sheet B, and Bresles.
    avec = {p: c for p, c in communes.items() if c}
    assert avec == {
        "Compiègne, soixante deux cents": [("Compiègne", SURE)],
        "soixante deux cents": [("Compiègne", A_CONFIRMER)],
        "soixante mille deux cents": [("Compiègne", SURE)],
        "Chantilly, soixante cinq cents": [("Chantilly", SURE)],
        "quatre-vingt-quinze mille huit cent vingt": [("Bruyères-sur-Oise", SURE)],
        "six zéro sept quatre zéro": [("Saint-Maximin", SURE)],
        "Saint-Leu-d'Esserent, soixante trois cent quarante": [("Saint-Leu-d'Esserent", SURE)],
        "code postal soixante mille": [("Beauvais", A_CONFIRMER)],
        "à Bresles, dans l'Oise": [("Bresles", SURE)],
        # "vingt ans" proposed Vinantes until 2026-09-16: the words of any
        # number are no longer a town (Six-Fours-les-Plages is recovered when
        # spelled out, see test_balayages_nombres_dictes).
    }


# --------------------------------------------------------------------------- #
# 6. Review of 2026-09-16: a postal code must never confirm itself
# --------------------------------------------------------------------------- #


def _trace_comme_lappel(lecture):
    """The entries the call REALLY records (``trace_de``): a hand-made record
    left the production half of the B2 fix untested (counter-review of 16/09)."""
    from api.services.pipecat.verification_communes import trace_de

    return [trace_de(d, charger_base(), "coordonnees") for d in lecture.detections]


def test_un_code_repete_dans_le_message_reste_a_confirmer(base, magasin):
    """B1: the note born of the first "soixante deux cents" made the second one
    announce Compiègne as sure."""
    lu, r = _lu("soixante deux cents, soixante deux cents", base, magasin)
    assert [c.statut for c in r.choix.values()] == ["a_confirmer", "a_confirmer"]
    assert [d.statut for d in r.detections] == [A_CONFIRMER]
    assert lu.count("[Vérification de la commune") == 1
    assert "correspond à" not in lu


@pytest.mark.parametrize(
    "premier,second,communes_du_code",
    [
        ("soixante cent vingt", "soixante mille cent vingt", ["Breteuil", "Ansauvillers", "Bonneuil-les-Eaux"]),
        ("soixante trois cents", "soixante mille trois cents", ["Senlis", "Chamant"]),
        ("soixante deux cents", "soixante deux cents", ["Compiègne", "Calais"]),
    ],
)
def test_un_code_redit_au_tour_suivant_ne_se_confirme_pas_lui_meme(base, magasin, premier, second, communes_du_code):
    """B2: the proposals made from a code are not towns the caller said."""
    _, avant = _lu(premier, base, magasin)
    lu, r = _lu(second, base, magasin, _trace_comme_lappel(avant))
    assert [d.statut for d in r.detections] == [A_CONFIRMER], lu
    assert "correspond à" not in lu
    propositions = [l.commune.nom for l in r.detections[0].lectures]
    assert set(communes_du_code) & set(propositions)


def test_une_commune_nommee_puis_le_code_reste_sure(base, magasin):
    """The fix does not undo N2 ②: « Bovet » heard, then « soixante mille »: the
    code is sure, Beauvais proposed first (decision of Evan, 2026-09-16: named
    sure only if heard exactly or alone in its code). Kept by the decision of
    2026-09-17: V4 does not apply to a town said at the turn BEFORE the code."""
    _, avant = _lu("j'habite à Bovet", base, magasin)
    _, r = _lu("soixante mille", base, magasin, _trace_comme_lappel(avant))
    (d,) = r.detections
    assert (_code(r).statut, d.statut, d.lectures[0].commune.nom) == ("sure", A_CONFIRMER, "Beauvais")


def test_un_code_incertain_a_cote_dune_commune_qui_ne_le_porte_pas_est_signale(base, magasin):
    lu, r = _lu("Beauvais soixante deux cents", base, magasin)
    assert [(d.statut, d.lectures[0].commune.nom) for d in r.detections] == [
        (SURE, "Beauvais"), (A_CONFIRMER, "Compiègne")
    ]
    assert lu.endswith(
        "[Vérification de la commune : « soixante deux cents » peut être Compiègne (60200, Oise) "
        "ou Calais (62100, Pas-de-Calais). Fais préciser la commune avant de la noter.]"
    )


def test_deux_communes_proposees_du_meme_code_ne_rendent_pas_la_premiere_sure(base, magasin):
    """B2, uniqueness alone: two towns proposed for a NAME (not a code) that
    share a postal code do not make the first of them the caller's."""
    breteuil, ansauvillers = (
        next(c for c in base.communes_du_code_postal("60120") if c.nom == nom)
        for nom in ("Breteuil", "Ansauvillers")
    )
    trace = [{
        "statut": "a_confirmer",
        "commune_retenue": None,
        "propositions": [{"code_insee": breteuil.insee}, {"code_insee": ansauvillers.insee}],
    }]
    lu, r = _lu("soixante cent vingt", base, magasin, trace)
    assert _code(r).par != PAR_TRACE
    (d,) = r.detections
    assert d.statut == A_CONFIRMER
    assert "correspond à" not in lu
