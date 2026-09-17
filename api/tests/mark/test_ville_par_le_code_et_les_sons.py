"""[.mark] The town decided by the postal code, the sounds and the repetition (plan voix-et-communes, lot 2).

The questions this file answers:

1. A postal code known (said in the message, or at the turn before), is the
   badly transcribed name of the benches of 2026-09-16 and 17 decided among
   the communes of that code, clearly ahead (V4, thresholds 75/30 decided by
   Evan on 2026-09-17)? And is a town said at the turn BEFORE the code left to
   confirm, as on 2026-09-16?
2. Does a name repeated after a request for precision decide the town (V8)?
3. Is the rest of a name opening on "Saint-" never a town of its own (T8)?
4. Do the pronounced sounds (espeak-ng, V5) help, and does the check go on
   without them?
5. Called as the bench's fiche A version 3 (each town with its code, then the
   sentences without a town), is any town announced sure and wrong?

⛔ It does NOT prove the transcription writes these words again: the bench
decides. The names below are what Deepgram really wrote (runs 259 to 265).
"""

import pytest

from api.services.communes import analyse
from api.services.communes import sons as module_sons
from api.services.communes.analyse import SURE
from api.services.communes.base import charger_base
from api.services.nombres.lecture import analyser_message
from api.services.pipecat.lecture_appelant import _trace_nombre
from api.services.pipecat.verification_communes import trace_de


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees("60589")  # Saint-Maximin (60), the bench's reference


def _tours(base, magasin, textes):
    """The messages of a call, each read with the REAL records of the previous ones."""
    communes, nombres, lectures = [], [], []
    for texte in textes:
        r = analyser_message(texte, base, magasin, communes, trace_nombres=nombres)
        communes += [trace_de(d, base, "coordonnees") for d in r.detections]
        nombres += [_trace_nombre(n, r.choix.get(n.debut), "coordonnees") for n in r.nombres]
        lectures.append(r)
    return lectures


def _sures(r):
    return [d.lectures[0].commune.nom for d in r.detections if d.statut == SURE]


# The badly transcribed names, with the code of the town meant, said in words.
RATES = {
    "Bové": ("soixante mille", "Beauvais"),
    "Bouvé": ("soixante mille", "Beauvais"),
    "Bovet": ("soixante mille", "Beauvais"),
    "BOV": ("soixante mille", "Beauvais"),
    "Brel": ("soixante cinq cent dix", "Bresles"),
    "Coil à forêt": ("soixante cinq cent quatre-vingts", "Coye-la-Forêt"),
    "il a foré": ("soixante cinq cent quatre-vingts", "Coye-la-Forêt"),
    "C'est un monte-à-terre": ("soixante cent soixante", "Montataire"),
    "Liladan": ("quatre-vingt-quinze deux cent quatre-vingt-dix", "L'Isle-Adam"),
    "Lyon Court": ("soixante cent quarante", "Liancourt"),
    "L'y en cours": ("soixante cent quarante", "Liancourt"),
}
# Below the thresholds decided by Evan (75/30): to confirm, never wrong.
A_CONFIRMER = {
    "conquérir": ("soixante deux cents", "Compiègne"),
    "Saint-Laurent": ("soixante trois cent quarante", "Saint-Leu-d'Esserent"),
    "moult à terre": ("soixante cent soixante", "Montataire"),
}


# --------------------------------------------------------------------------- #
# 1. V4
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nom", sorted(RATES))
def test_nom_et_code_dans_la_meme_phrase(base, magasin, nom):
    code, ville = RATES[nom]
    (r,) = _tours(base, magasin, [f"{nom}, {code}"])
    assert _sures(r) == [ville]
    (choix,) = r.choix.values()
    assert choix.statut == "sure"


@pytest.mark.parametrize("nom", sorted(RATES))
def test_code_puis_nom_au_tour_suivant(base, magasin, nom):
    code, ville = RATES[nom]
    _, r = _tours(base, magasin, [code, nom])
    assert _sures(r) == [ville]


@pytest.mark.parametrize("nom", sorted(A_CONFIRMER))
def test_sous_les_seuils_a_confirmer_jamais_faux(base, magasin, nom):
    code, ville = A_CONFIRMER[nom]
    (meme,) = _tours(base, magasin, [f"{nom}, {code}"])
    _, apres = _tours(base, magasin, [code, nom])
    for r in (meme, apres):
        assert all(s == ville for s in _sures(r)), _sures(r)


@pytest.mark.parametrize("nom", ["Bouvé", "Brel", "Lyon Court"])
def test_nom_au_tour_davant_le_code_reste_a_confirmer(base, magasin, nom):
    """Decision of Evan, 2026-09-17: applied in this order, « chez mes parents »
    then « soixante cent dix » made Esches sure (third review of 2026-09-16)."""
    code, ville = RATES[nom]
    _, r = _tours(base, magasin, [nom, code])
    assert _sures(r) == []
    assert ville in [l.commune.nom for d in r.detections for l in d.lectures]


def test_un_nom_ecrit_exactement_nest_pas_remplace_par_le_code_du_tour_davant(base, magasin):
    """« Arcueil » said after 60100: another place, named as written."""
    _, r = _tours(base, magasin, ["soixante cent", "Arcueil"])
    assert _sures(r) == ["Arcueil"]
    # Spelled exactly, not in the code: another place, even when close to a commune of it.
    _, r = _tours(base, magasin, ["soixante cent quarante", "Liancourt-Saint-Pierre"])
    assert _sures(r) == ["Liancourt-Saint-Pierre"]
    # « Boves » is a real town, written as said: never replaced by Beauvais, left to confirm.
    _, r = _tours(base, magasin, ["soixante mille", "Boves"])
    assert _sures(r) == []


@pytest.mark.parametrize("texte, ville", [
    ("Chantilly 60230", "Chambly"), ("Goincourt 60129", "Gilocourt"), ("Mouy 60790", "Pouilly"),
])
def test_un_nom_juste_avec_un_code_faux_ne_devient_pas_une_autre_commune(base, magasin, texte, ville):
    """Review of 2026-09-17: the right name with a wrong (or badly heard) code
    made another commune of that code sure. The conflict stays visible."""
    (r,) = _tours(base, magasin, [texte])
    assert ville not in _sures(r)


def test_la_ville_du_code_nest_pas_prise_dans_des_mots_de_conversation(base, magasin):
    for texte in ("il y a soixante mille", "je crois que c'est soixante cinq cents",
                  "ça doit être deux mille cinq cent dix", "d'accord soixante mille"):
        (r,) = _tours(base, magasin, [texte])
        assert [d for d in r.detections if d.statut == SURE and not d.code_postal_entendu] == [], texte


def test_lecture_du_code_a_deux_lectures_tranchee_par_la_ville(base, magasin):
    """« soixante sept cent quarante » is 60740 or 67140: the town decides."""
    (r,) = _tours(base, magasin, ["Sans Maximin, soixante sept cent quarante"])
    assert _sures(r) == ["Saint-Maximin"]
    assert [c.code for c in r.choix.values()] == ["60740"]


# --------------------------------------------------------------------------- #
# 2. V8
# --------------------------------------------------------------------------- #


def test_un_nom_ecrit_comme_la_commune_repete_apres_une_precision_tranche(base, magasin):
    premier, second = _tours(base, magasin, ["Lyon", "Lyon"])
    assert _sures(premier) == []
    assert _sures(second) == ["Lyon"]
    # Longer names open on « Pont » or « Marseille », not on « Lyon »: without
    # the shop, any of them blocks.
    from api.services.nombres.lecture import _debut_dun_nom_plus_proche

    marseille = next(c for c in base.communes if c.nom == "Marseille")
    assert _debut_dun_nom_plus_proche(marseille, base, None)


@pytest.mark.parametrize("nom, code, ville", [
    ("Bouvé", "soixante mille", "Beauvais"), ("Lyon Court", "soixante cent quarante", "Liancourt"),
])
def test_un_nom_mal_transcrit_repete_ne_tranche_pas_le_code_tranche(base, magasin, nom, code, ville):
    """Decision of Evan, 2026-09-17: « Bouvé » twice made Boves sure (run 264's
    error). Repeated, it stays to confirm; said again with the code, V4 decides."""
    _, second = _tours(base, magasin, [nom, nom])
    assert _sures(second) == []
    _, avec_code = _tours(base, magasin, [nom, f"{nom}, {code}"])
    assert _sures(avec_code) == [ville]


@pytest.mark.parametrize("seq", [
    ["Villers", "Villers"], ["Saint-Just", "Saint-Just"], ["Beaumont", "Beaumont"],
    ["Pont", "Pont"], ["Saint-Martin", "Saint-Martin"], ["Angecourt", "non, Angecourt"],
    ["Bressolles", "Bressolles"], ["Morvilliers", "Morvilliers"], ["Collongues", "Collongues"],
    ["Balan", "Balan"], ["Cerdon", "Cerdon"],
    # A longer town nearer the shop opens on the name (counter-review of 2026-09-17).
    ["Marseille", "Marseille"], ["Mory", "Mory"], ["Vendeuil", "Vendeuil"],
])
def test_une_repetition_qui_napporte_rien_ne_tranche_pas(base, magasin, seq):
    """Review of 2026-09-17: a name several communes carry, or open (« Pont »),
    said twice, names none of them; « non » is not a confirmation."""
    _, r = _tours(base, magasin, seq)
    assert _sures(r) == []


def test_la_repetition_ne_tranche_que_la_commune_proposee_en_tete(base, magasin):
    _, r = _tours(base, magasin, ["Lyon", "Senlis"])
    assert _sures(r) == ["Senlis"]  # sure on its own
    _, r = _tours(base, magasin, ["Lyon", "Lognes"])
    assert "Lyon" not in _sures(r)


# --------------------------------------------------------------------------- #
# 3. T8
# --------------------------------------------------------------------------- #


def test_le_reste_dun_nom_a_prefixe_generique_nest_pas_lu_seul():
    """The motif, not the case: no reading starts right after "saint", "pont",
    "val"…, nor right after an article glued to the next word; an article that is
    not glued still opens a reading ("c'est la maison")."""
    from api.services.communes.analyse import _segments
    from api.services.communes.base import normaliser

    def debuts(texte, spans=()):
        mots = normaliser(texte).split()
        return {" ".join(mots[i:i + n]) for i, n, _, _ in _segments(texte, mots, list(spans), set(), True)}

    # Run 265: the words next to the postal code are anchored, the rest of the name was read alone.
    code = (3, 7)  # « soixante trois cent quarante »
    lus = debuts("Saint-Le-Destran, soixante trois cent quarante", [code])
    assert "saint le destran" in lus
    assert "le destran" not in lus and "destran" not in lus
    lus = debuts("Pont-Sainte-Maxence, soixante sept cents", [(3, 6)])
    assert "pont sainte maxence" in lus
    assert "sainte maxence" not in lus and "maxence" not in lus
    assert "maison" in debuts("c'est la maison")


def test_le_reste_dun_nom_en_saint_nest_pas_une_commune(base, magasin):
    """Run 265: « Saint-Le-Destran » gave Lestrem (62) sure."""
    (r,) = _tours(base, magasin, ["Saint-Le-Destran, soixante trois cent quarante"])
    noms = [l.commune.nom for d in r.detections for l in d.lectures]
    assert "Lestrem" not in noms
    assert _sures(r) == ["Saint-Leu-d'Esserent"]
    (seul,) = _tours(base, magasin, ["Saint-Le-Destran"])
    assert "Lestrem" not in [l.commune.nom for d in seul.detections for l in d.lectures]


# --------------------------------------------------------------------------- #
# 4. V5
# --------------------------------------------------------------------------- #


def test_les_sons_rapprochent_ce_que_la_transcription_ecrit(base, magasin):
    assert module_sons.sons(["monte a terre"]) == module_sons.sons(["montataire"])
    (r,) = _tours(base, magasin, ["Clairement Ferrand"])
    assert _sures(r) == ["Clermont-Ferrand"]


def test_les_sons_restent_justes_quand_plusieurs_appels_les_demandent_en_meme_temps():
    """🔒 Review of 2026-09-17: without a lock, 747 results out of 750 were wrong
    with 8 threads (one temporary file per engine, shared C state)."""
    from concurrent.futures import ThreadPoolExecutor

    lots = [["beauvais", "monte a terre", "liancourt"], ["senlis", "coye la foret"], ["l isle adam", "creil"]] * 40
    attendus = [module_sons.sons(l) for l in lots]
    with ThreadPoolExecutor(max_workers=8) as pool:
        obtenus = list(pool.map(module_sons.sons, lots))
    assert obtenus == attendus


def test_sans_la_bibliotheque_la_verification_continue(base, magasin, monkeypatch):
    """⛔ Fail-open: without espeak-ng, the spelling keys alone, as before."""
    monkeypatch.setattr(analyse, "sons", lambda textes: None)
    (r,) = _tours(base, magasin, ["c'est à Beauvais"])
    assert _sures(r) == ["Beauvais"]
    (r,) = _tours(base, magasin, ["Bouvé, soixante mille"])
    assert _sures(r) == ["Beauvais"]


# --------------------------------------------------------------------------- #
# 5. The fiche A version 3, as a call, on exact text
# --------------------------------------------------------------------------- #

FICHE_A_V3 = [
    ("c'est à Beauvais, soixante mille", "Beauvais"),
    ("c'est au 12 rue de la gare", None),
    ("j'habite à Chambly, soixante deux cent trente", "Chambly"),
    ("c'est sur Bresles, soixante cinq cent dix", "Bresles"),
    ("Grandvilliers, soixante deux cent dix", "Grandvilliers"),
    ("à Clermont-Ferrand, soixante-trois mille", "Clermont-Ferrand"),
    ("Senlis, soixante trois cents", "Senlis"),
    ("à Crépy-en-Valois, soixante huit cents", "Crépy-en-Valois"),
    ("c'est la maison au bout du chemin", None),
    ("on est à Pont-Sainte-Maxence, soixante sept cents", "Pont-Sainte-Maxence"),
    ("à Lamorlaye, soixante deux cent soixante", "Lamorlaye"),
    ("j'habite à Lyon, soixante-neuf mille trois", "Lyon"),
    ("c'est à Liancourt, soixante cent quarante", "Liancourt"),
    ("au 4 allée des lilas", None),
    ("Senlis, soixante mille trois cents", "Senlis"),
    ("Beaumont-sur-Oise, quatre-vingt-quinze deux cent soixante", "Beaumont-sur-Oise"),
    ("j'habite à Clermont, soixante six cents", "Clermont"),
    ("à Creil, soixante cent", "Creil"),
    ("c'est à Bordeaux, trente-trois mille", "Bordeaux"),
    ("c'est à côté de la boulangerie", None),
    ("c'est à Compiègne, soixante deux cents", "Compiègne"),
    ("à Saint-Leu-d'Esserent, soixante trois cent quarante", "Saint-Leu-d'Esserent"),
    ("c'est à Breteuil, soixante cent vingt", "Breteuil"),
    ("Coye-la-Forêt, soixante cinq cent quatre-vingts", "Coye-la-Forêt"),
    ("c'est la résidence les charmilles", None),
    ("c'est à Montataire, soixante cent soixante", "Montataire"),
    ("à Aix-en-Provence, treize mille cent", "Aix-en-Provence"),
    ("j'habite à L'Isle-Adam, quatre-vingt-quinze deux cent quatre-vingt-dix", "L'Isle-Adam"),
    ("Verneuil-en-Halatte, soixante mille cinq cent cinquante", "Verneuil-en-Halatte"),
    ("à Persan, quatre-vingt-quinze trois cent quarante", "Persan"),
    ("au fond de l'impasse des roses", None),
    ("c'est à Gisors, vingt-sept cent quarante", "Gisors"),
    ("c'est à Saint-Malo, trente-cinq quatre cents", "Saint-Malo"),
    ("à Soissons, deux mille deux cents", "Soissons"),
    ("c'est le bâtiment B au deuxième étage", None),
    ("Saint-Maximin, soixante sept cent quarante", "Saint-Maximin"),
    ("j'habite à Amiens, quatre-vingt mille", "Amiens"),
    ("c'est derrière l'église, la maison avec le portail vert", None),
]


def test_fiche_a_version_3_jouee_comme_un_appel(base, magasin):
    lectures = _tours(base, magasin, [texte for texte, _ in FICHE_A_V3])
    assert len(lectures) == 38 and sum(1 for _, v in FICHE_A_V3 if v) == 30
    fausses, sures_justes = [], 0
    for (texte, ville), r in zip(FICHE_A_V3, lectures):
        for nom in _sures(r):
            if nom != ville:
                fausses.append((texte, nom))
            else:
                sures_justes += 1
    assert fausses == []
    # Measured on 2026-09-17 on exact text; the bench criterion is ≥ 28 of 30.
    assert sures_justes >= 28
