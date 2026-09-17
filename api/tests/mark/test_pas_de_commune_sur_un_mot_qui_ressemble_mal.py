"""[.mark] Non-regression test: no commune proposed on words that resemble it badly.

The question this file answers:

    Since the agent names the first commune to confirm aloud (decision of Evan,
    2026-09-17), is a commune still proposed on words of the conversation that
    resemble it badly (« Un poêle à granulés » -> Grandrû)? And does a name
    badly transcribed but meant as a town (« Brel » for Bresles) still propose it?

Why it exists
-------------
Fiche D, runs 269 to 272 (2026-09-17): « Un poêle à granulés » made the agent ask
« Est-ce que vous êtes à Grandrû, dans l'Oise ? », then « Grans, dans les
Bouches-du-Rhône ? ». « L'année dernière » proposed Anet, « Passe à la suite »
Pacé and Lassy. Decision of Evan: no commune on a word that resembles it badly,
« Brel » still proposes Bresles. The motif is fixed by the rules of
``analyse.propositions_fondees``, measured on the calls of 15 to 17/09; the
texts below are what the transcription really wrote.

⛔ A fix that goes too far is worse than the defect: the communes meant by the
caller, badly transcribed, are asserted too (section 3).
"""

import pytest

from api.schemas.organization_preferences import AdresseEtablissement
from api.services.communes import analyse
from api.services.communes.analyse import A_CONFIRMER, SURE
from api.services.communes.base import charger_base
from api.services.communes.mention import MARQUE, mentionner
from api.services.nombres.lecture import analyser_message, reecrire


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees("60589")  # Saint-Maximin (60), the benches' reference


def _noms(r):
    """The communes proposed from words heard (not from a postal code heard)."""
    return [[l.commune.nom for l in d.lectures] for d in r.detections if not d.code_postal_entendu]


# --------------------------------------------------------------------------- #
# 1. The parasites of 2026-09-17: nothing proposed
# --------------------------------------------------------------------------- #

PARASITES_DU_17_09 = [
    # Resemblance under SEUIL_PROPOSITION, and farther than RAYON_PROPOSITION_FAIBLE
    # from the shop (⚠️ radius pending Evan's decision).
    "Un poêle à granulés",  # run 271: Grandrû, Grans, Grane
    "Bonjour, je voudrais faire amener mon poêle à granulés s'il vous plaît.",  # run 269
    "Non, je voudrais faire ramoner mon poêle à granulé.",  # run 269
    "c'est un poêle à granulés et dilcama.",  # run 272
    "Révérance FA quatre cent douze.",  # run 267: Recouvrance, Préveranges
    # Words that go on with a complement name no place: « Passe » is Pacé at 100.
    "Passe à l'élément dix.",  # run 266: Pacé, Allemant
    "Passe aux choses.",  # run 266: Pacé
    # An article right before the words belongs to the commune's name.
    "C'est la maison au bout du chemin.",  # run 266: Maisons, Lormaison
    "C'est le bâtiment b au deuxième étage.",  # run 266: Athis-Mons
    # « côté » followed by « de » is a preposition.
    "c'est à côté de la boulangerie.",  # run 266: Contay, Corte
]
# ⚠️ Known limits, kept knowingly (rule of Evan: zero loss first, counter-review
# of 2026-09-17): « L'année dernière… » (Lanne, the article glued is allowed),
# « Passe à la suite. » (Lassy), « il y a marqué… » (Marques: the « il y a »
# rule depended on capitals, removed), « Flammo. », « crée ». The full list, per
# shop, is ``parasites_restants_connus`` in ``donnees/communes_corpus_reel_2026-09-17.json``.


@pytest.mark.parametrize("texte", PARASITES_DU_17_09)
def test_aucune_commune_proposee_sur_un_parasite_du_17_09(base, magasin, texte):
    r = analyser_message(texte, base, magasin)
    assert _noms(r) == []
    assert MARQUE not in mentionner(reecrire(texte, r.nombres, r.choix_cp), r.detections, base)


def test_une_commune_sure_dans_la_meme_phrase_reste(base, magasin):
    """Only the proposals to confirm are touched."""
    r = analyser_message("C'est la maison au bout du chemin, à Saint-Maximin.", base, magasin)
    assert [(d.statut, d.lectures[0].commune.nom) for d in r.detections] == [(SURE, "Saint-Maximin")]


def test_la_verification_hors_du_francais_applique_la_meme_regle():
    """The check of 2026-09-16, used as is when the agent is not French."""
    from api.services.pipecat.verification_communes import _analyser_et_mentionner

    adresse = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")
    texte, detections, _ = _analyser_et_mentionner("Passe aux choses.", adresse)
    assert (texte, detections) == ("Passe aux choses.", [])


# --------------------------------------------------------------------------- #
# 2. « Brel » proposes Bresles, first (the criterion fixed by Evan)
# --------------------------------------------------------------------------- #


def test_brel_avec_le_departement_60_propose_bresles(base, magasin):
    """Run 268: as in production, Bresles named first (Bornel and Creil, weak but
    near the shop, stay after it: zero loss)."""
    texte = "À Brel dans l'Oise."
    r = analyser_message(texte, base, magasin)
    (d,) = r.detections
    assert (d.statut, [l.commune.nom for l in d.lectures]) == (A_CONFIRMER, ["Bresles", "Bornel", "Creil"])
    assert "Demande d'abord si c'est Bresles (Oise)" in mentionner(texte, r.detections, base)


@pytest.mark.parametrize("texte", [
    "Brel dans le soixante", "C'est Brel dans l'Oise.", "Brel.", "C'est sur Brel.",  # runs 259 to 268
    "Brell soixante.", "C'est Brell Danloise.",
])
def test_brel_propose_toujours_bresles_en_premier(base, magasin, texte):
    (noms,) = _noms(analyser_message(texte, base, magasin))
    assert noms[0] == "Bresles"


# --------------------------------------------------------------------------- #
# 3. The communes meant by the caller, badly transcribed, are still proposed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("texte, commune", [
    ("C'est à Bovet.", "Beauvais"),  # run 261 (Boves first, Beauvais proposed)
    ("Bouvé.", "Beauvais"),  # run 264
    ("Bové d'enloises", "Beauvais"),  # run 259, « dans l'Oise » garbled: not a complement
    ("C'est à Lyon Court.", "Liancourt"),  # run 264
    ("Grand Villiers.", "Grandvilliers"),  # run 264
    ("C'est à Compiagnes.", "Compiègne"),  # run 262
    ("À Saint-Laurent.", "Saint-Laurent"),  # run 261: written exactly, homonyms kept
    # Run 245: the caller goes on after the town, without a complement of it.
    ("Non, c'est à Bovet et oui, il a été entretenu l'année dernière en octobre.", "Beauvais"),
    # An address after the town is not a complement of it.
    ("c'est à Bovet, au 12 rue des Lilas", "Beauvais"),
])
def test_une_commune_mal_transcrite_reste_proposee(base, magasin, texte, commune):
    r = analyser_message(texte, base, magasin)
    assert any(commune in noms for noms in _noms(r)), _noms(r)


@pytest.mark.parametrize("texte, commune, magasin_insee", [
    ("à La signy", "Lassigny", "78168"),  # the article glued in the name (counter-review)
    ("la Morley", "Lamorlaye", None),
    ("J'habite à Vers, dans le Lot.", "Vers", None),  # a name written exactly before « vers »
    ("il y a bovet", "Beauvais", "60589"),  # typed in lower case: no « il y a » rule
])
def test_contre_relecture_la_commune_reste_proposee(base, texte, commune, magasin_insee):
    magasin = base.coordonnees(magasin_insee) if magasin_insee else None
    r = analyser_message(texte, base, magasin)
    assert any(commune in [l.commune.nom for l in d.lectures] for d in r.detections), r.detections


def test_sans_adresse_du_magasin_rien_nest_retire_par_la_ressemblance(base):
    """Nothing locates a weak reading without the shop: kept, as in production."""
    assert any("Grans" in n for n in _noms(analyser_message("Un poêle à granulés", base, None)))


# --------------------------------------------------------------------------- #
# 4. Review of 2026-09-17: a place located next to the town is not a complement
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("texte, commune", [
    ("C'est à Bouvé, à côté de la gare.", "Beauvais"),
    ("C'est à Bovet au bord de l'eau.", "Beauvais"),
    ("C'est à Bovet à la sortie du village.", "Beauvais"),
    ("Champly à côté de Persan.", "Chambly"),
    ("Brel à côté de Beauvais.", "Bresles"),
    ("C'est vers Bovet à côté de Beauvais", "Beauvais"),
    # A place marker introduces the name: what follows never removes it.
    ("C'est à Bovet à la campagne", "Beauvais"),
])
def test_un_repere_de_lieu_apres_la_commune_ne_lefface_pas(base, magasin, texte, commune):
    """Measured by the review: the complement rule dropped the commune meant, and
    « côté » still proposed Contay and Corte, « vers » Vert."""
    noms = _noms(analyser_message(texte, base, magasin))
    assert any(commune in n for n in noms), noms
    assert not any({"Contay", "Corte", "Vert", "Vers"} & set(n) for n in noms), noms


@pytest.mark.parametrize("texte", ["C'est la maison au bout du chemin, soixante mille."])
def test_un_parasite_retire_ne_fait_pas_taire_le_code_postal_dit(base, magasin, texte):
    """Review of 2026-09-17: the parasite counted as a town said, so the postal
    code said alone got no note. Alone, « Soixante mille. » proposes Beauvais."""
    r = analyser_message(texte, base, magasin)
    codes = [[l.commune.nom for l in d.lectures] for d in r.detections if d.code_postal_entendu]
    assert codes and codes[0][:3] == ["Beauvais", "Allonne", "Goincourt"], r.detections
    assert _noms(r) == []


def test_les_mots_sans_contenu_sont_calcules_une_fois_par_liste(base):
    assert analyse._mots_sans_contenu(base) is analyse._mots_sans_contenu(base)
