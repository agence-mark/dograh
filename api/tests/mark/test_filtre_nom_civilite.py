"""[.mark] Non-regression test for the switch that forbids saying the caller's name.

The question this file answers, and it answers only this one:

    With the two switches on, does the agent stop saying the caller's name and
    title -- WITHOUT touching anything else it says?

Why it exists
-------------
Five rewrites of the instructions in two days (runs 749 to 753) did not make
this hold: the name was still spoken in 2 voice runs out of 5, the title in 2
out of 5. A rule holds where the action happens and gives way everywhere else.
So it is code, like the towns, the dictated numbers and the opening
announcement before it.

The hard half is not "does it remove the name". It is **zero loss**: the 84 %
of sentences that carry no name must come out identical to the character. That
is why the corpus is real -- 3 889 sentences actually said over 759 calls
(masked, see `donnees/phrases-agent.jsonl`) -- and not sentences invented for
the occasion, which always resemble the filter one has just written.

⛔ What this file does NOT prove: that the module behaves well TO THE EAR.
That is measured on real calls, in the dedicated bench session.
"""

import json
from pathlib import Path

import pytest

from api.services.pipecat.filtre_nom_civilite import retirer_nom_et_civilite

CORPUS = Path(__file__).parent / "donnees" / "phrases-agent.jsonl"

# Une phrase « concernée » est une phrase où le filtre a quelque chose à faire.
CIVILITES = ("monsieur", "madame", "mademoiselle")


def _corpus() -> list[str]:
    assert CORPUS.exists(), (
        f"corpus absent : {CORPUS}. Il est commité dans le dépôt à dessein -- ce "
        "test ne doit toucher le réseau ni en local ni en CI."
    )
    with CORPUS.open(encoding="utf-8") as fichier:
        return [json.loads(ligne)["texte"] for ligne in fichier if ligne.strip()]


def _porte_une_civilite(texte: str) -> bool:
    minuscules = texte.lower()
    return any(civilite in minuscules for civilite in CIVILITES)


# ─── A. Zéro perte ───────────────────────────────────────────────────────────


def test_A_zero_perte_sur_les_phrases_sans_nom_ni_civilite():
    """🔴 L'assertion qui compte le plus, et la seule que le corpus réel peut
    porter : une phrase qui ne concerne pas le filtre en sort IDENTIQUE au
    caractère près, les deux interrupteurs allumés.

    Un filtre qui retire bien le nom mais mange un espace, une virgule ou un
    point d'interrogation ailleurs est inutilisable : il parlerait mal à 100 %
    des appels pour en corriger 16 %.
    """
    intactes = 0
    for phrase in _corpus():
        if _porte_une_civilite(phrase) or "Dupont" in phrase:
            continue
        sortie = retirer_nom_et_civilite(
            phrase, "Dupont", retirer_nom=True, retirer_civilite=True
        )
        assert sortie == phrase, (
            f"phrase modifiée sans raison : {phrase!r} -> {sortie!r}"
        )
        intactes += 1
    # ⛔ Le comptage, dans l'autre sens : sans lui, un corpus mal lu (zéro ligne)
    # rendrait ce test vert en silence. Invariant dans les deux sens.
    assert intactes > 3000, f"corpus trop maigre : {intactes} phrases sans civilité"


def test_H_le_comptage_des_phrases_concernees():
    """🔴 L'autre sens de l'invariant : combien de phrases le filtre concerne.

    Mesuré le 22/09 sur les 759 runs : 15,6 %. Si ce compte s'effondre, c'est
    le corpus qui a été mal lu, pas le métier qui a changé -- et tous les tests
    ci-dessous deviendraient verts sans rien prouver.
    """
    corpus = _corpus()
    concernees = [phrase for phrase in corpus if _porte_une_civilite(phrase)]

    assert len(corpus) > 3000, f"corpus trop maigre : {len(corpus)} phrases"
    assert 0.10 < len(concernees) / len(corpus) < 0.25, (
        f"{len(concernees)}/{len(corpus)} phrases portent une civilité, "
        "loin des 15,6 % mesurés le 22/09"
    )


# ─── B. Ce qui est retiré, niveau 2 ──────────────────────────────────────────


@pytest.mark.parametrize(
    "entree, attendu",
    [
        # civilité + nom
        ("D'accord, c'est noté, monsieur Dupont.", "D'accord, c'est noté."),
        ("Merci Monsieur Dupont. C'est quel modèle ?", "Merci. C'est quel modèle ?"),
        # le nom seul, À LA MAJUSCULE
        ("Dupont, c'est noté.", "C'est noté."),
        ("Je note Dupont. Et votre numéro ?", "Je note. Et votre numéro ?"),
        # la civilité seule
        ("Bonjour madame, je vous écoute.", "Bonjour, je vous écoute."),
        ("Au revoir, monsieur.", "Au revoir."),
    ],
)
def test_B_le_niveau_2_retire_les_trois_formes(entree, attendu):
    assert (
        retirer_nom_et_civilite(
            entree, "Dupont", retirer_nom=True, retirer_civilite=True
        )
        == attendu
    )


def test_C_le_nom_en_MINUSCULES_nest_pas_touche():
    """⛔ « vous êtes passé chez le boulanger » ne se mutile pas chez un
    appelant nommé Boulanger. C'est la limite assumée du niveau 2 : la
    majuscule discrimine, et elle ne discrimine plus en début de phrase.
    """
    phrase = "Vous êtes passé chez le boulanger la semaine dernière ?"

    assert (
        retirer_nom_et_civilite(
            phrase, "Boulanger", retirer_nom=True, retirer_civilite=True
        )
        == phrase
    )


def test_C_le_nom_du_magasin_est_epargne():
    """Le filtre s'ancre sur la variable extraite `nom`, jamais sur une liste
    de mots : le nom du magasin n'est pas le nom de l'appelant."""
    phrase = "Nuances de Feu bonjour, je suis Marie."

    assert (
        retirer_nom_et_civilite(
            phrase, "Dupont", retirer_nom=True, retirer_civilite=True
        )
        == phrase
    )


def test_C_une_commune_homonyme_nest_pas_touchee():
    """Bury est une commune de l'Oise ET un nom de personne. Tant que
    l'appelant ne s'appelle pas Bury, la commune ne bouge pas."""
    phrase = "Vous êtes bien à Bury, dans l'Oise ?"

    assert (
        retirer_nom_et_civilite(
            phrase, "Dupont", retirer_nom=True, retirer_civilite=True
        )
        == phrase
    )


# ─── D. Les cas réels relevés le 22/09 ───────────────────────────────────────


@pytest.mark.parametrize(
    "entree, attendu",
    [
        # un nom entre deux virgules, suivi d'un deux-points
        (
            "Alors, monsieur Delamotte : je vous mets en relation.",
            "Alors : je vous mets en relation.",
        ),
        # en fin de phrase, devant un point d'interrogation
        (
            "Vous avez autre chose à ajouter, madame Delamotte ?",
            "Vous avez autre chose à ajouter ?",
        ),
        # une civilité seule encadrée de deux virgules : les DEUX partent avec
        # elle. Garder celle d'avant rendrait « votre poêle, est un Godin » sur
        # le cas voisin, ce qui est franchement fautif ; « Très bien et votre
        # numéro ? » ne l'est pas, il perd juste une respiration.
        ("Très bien, madame, et votre numéro ?", "Très bien et votre numéro ?"),
        # deux occurrences dans la même phrase
        (
            "Monsieur Delamotte, je répète : votre poêle, monsieur Delamotte, est un Godin.",
            "Je répète : votre poêle est un Godin.",
        ),
    ],
)
def test_D_les_cas_reels_ne_rendent_pas_la_phrase_bancale(entree, attendu):
    """⛔ « D'accord, c'est noté, monsieur Untel. » doit donner « D'accord,
    c'est noté. », jamais « D'accord, c'est noté, . »"""
    assert (
        retirer_nom_et_civilite(
            entree, "Delamotte", retirer_nom=True, retirer_civilite=True
        )
        == attendu
    )


def test_D_la_recouture_nagit_QUE_si_un_retrait_a_eu_lieu():
    """🔴 Le défaut du prototype, et la raison de cette garde : sans elle, la
    recouture mangeait l'espace avant le « ? » de phrases où RIEN n'avait été
    retiré."""
    phrase = "Est-ce que le poêle est allumé , là ?"

    assert (
        retirer_nom_et_civilite(
            phrase, "Dupont", retirer_nom=True, retirer_civilite=True
        )
        == phrase
    )


# ─── E. Le nom épelé survit, et c'est voulu ──────────────────────────────────


def test_E_le_nom_epele_nest_JAMAIS_filtre():
    """🔑 Décision d'Evan du 22/09, et elle n'est pas un oubli : l'épellation
    confirme l'information dans les deux sens, alimente la fiche et évite la
    boucle sans fin quand un appelant corrige son nom.

    ⚠️ Sa conséquence est dans la notice de l'écran : quand l'interrupteur est
    allumé, l'agent confirme le nom EN ÉPELANT, jamais en le disant, sinon la
    confirmation perd son objet (« C'est bien ? »).
    """
    phrase = "Donc D - U - P - O - N - T, c'est bien ça ?"

    assert (
        retirer_nom_et_civilite(
            phrase, "Dupont", retirer_nom=True, retirer_civilite=True
        )
        == phrase
    )


def test_E_lepellation_collee_survit_aussi():
    phrase = "Alors D-U-P-O-N-T, j'ai bien noté."

    assert (
        retirer_nom_et_civilite(
            phrase, "Dupont", retirer_nom=True, retirer_civilite=True
        )
        == phrase
    )


# ─── G. Les deux interrupteurs, séparément ───────────────────────────────────


def test_G_les_deux_interrupteurs_eteints_ne_font_RIEN():
    phrase = "D'accord, c'est noté, monsieur Dupont."

    assert retirer_nom_et_civilite(phrase, "Dupont") == phrase


def test_G_le_nom_seul_laisse_la_civilite():
    assert (
        retirer_nom_et_civilite(
            "D'accord, monsieur Dupont, c'est noté.", "Dupont", retirer_nom=True
        )
        == "D'accord, monsieur, c'est noté."
    )


def test_G_la_civilite_seule_laisse_le_nom():
    assert (
        retirer_nom_et_civilite(
            "D'accord, monsieur Dupont, c'est noté.", "Dupont", retirer_civilite=True
        )
        == "D'accord, Dupont, c'est noté."
    )


def test_G_sans_nom_connu_seule_la_civilite_peut_partir():
    """Le filtre ne connaît le nom qu'une fois extrait : avant, il n'a rien à
    retirer, et c'est une limite écrite dans la notice."""
    phrase = "D'accord, monsieur Dupont, c'est noté."

    assert (
        retirer_nom_et_civilite(phrase, None, retirer_nom=True, retirer_civilite=True)
        == "D'accord, Dupont, c'est noté."
    )


def test_le_filtre_ne_leve_JAMAIS():
    """⛔ Une erreur du filtre ne doit pas emporter l'appel : même règle que
    l'adresse et le lexique. Un nom qui est un motif d'expression régulière
    (« M. (Dupont) ») ne doit pas faire mourir le tour de parole."""
    phrase = "D'accord, c'est noté."

    for nom_tordu in ["(", "[a-z", "*", "\\", ""]:
        assert (
            retirer_nom_et_civilite(
                phrase, nom_tordu, retirer_nom=True, retirer_civilite=True
            )
            == phrase
        )
