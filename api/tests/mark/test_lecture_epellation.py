"""[.mark] Garantie : les lettres épelées par l'appelant sont lues, telles quelles.

Question du labo : **ce que l'appelant épelle arrive-t-il dans la fiche ?**
Sur les 759 runs, 25 épellations de nom ; la variable extraite n'en portait la
forme épelée que **17 fois**. Le lecteur fait ce travail par le code, la mention
dit au modèle de recopier.

Ce que ce fichier protège, et pourquoi chaque section existe :

| Section | Ce qu'elle tient |
|---|---|
| 1 | Le **corpus complet** (136 cas) : réel, écrit, négatif. Zéro fausse lecture |
| 2 | Les **trois règles anti-faux-positif**, chacune payée par un défaut réel |
| 3 | L'**écriture** : capitale initiale, noms composés |
| 4 | Les **courriels** (Q9), et la limite posée : pas de lettre épelée, rien lu |
| 5 | La **mention** : texte exact, idempotence, plusieurs épellations |
| 6 | Le **comptage dans les deux sens** — sans lui un échec de lecture rendrait
      un faux vert (invariant-dans-les-deux-sens) |

⛔ Prouvé rouge avant d'être écrit vert, défaut par défaut : voir le journal du
chantier (`_AUTONOMIE/plans/en-cours/adresses-et-epellation/journal-de-bord.md`).
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from api.services.epellation.lecture import Epellation, lire
from api.services.epellation.mention import (
    MARQUE,
    deja_mentionne,
    mentionner_epellations,
    phrase_de_mention,
)

CORPUS = json.loads(
    (Path(__file__).parent / "donnees" / "epellation_corpus_2026-09-22.json").read_text(
        encoding="utf-8"
    )
)


def _normaliser(texte: str) -> str:
    return unicodedata.normalize("NFC", texte).strip()


def _lu(phrase: str) -> list[str]:
    return [_normaliser(e.epele) for e in lire(phrase)]


# --- 1. Le corpus complet -------------------------------------------------


def test_le_corpus_est_bien_celui_qui_a_servi_au_reglage():
    """⛔ Un corpus amputé ferait passer n'importe quel lecteur."""
    familles = {}
    for cas in CORPUS:
        familles[cas["famille"]] = familles.get(cas["famille"], 0) + 1
    assert familles == {"reel": 106, "ecrit": 15, "negatif": 15}
    assert len(CORPUS) == 136


@pytest.mark.parametrize("cas", CORPUS, ids=lambda c: f"{c['famille']}-{c['phrase'][:30]}")
def test_chaque_phrase_du_corpus_est_lue_exactement(cas):
    assert _lu(cas["phrase"]) == [_normaliser(x) for x in cas["attendu"]]


def test_aucune_fausse_lecture_sur_tout_le_corpus():
    """🔴 La mesure qui prime : une épellation lue là où il n'y en a pas met un
    mot inventé dans la fiche de l'appelant."""
    fausses = [
        cas["phrase"] for cas in CORPUS if not cas["attendu"] and _lu(cas["phrase"])
    ]
    assert fausses == []


# --- 2. Les trois règles anti-faux-positif --------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "il n'y a pas de problème",           # règle 1 : élision, écrivait « Nya »
        "c'est facile d'accès, dire le code",  # règle 2 : noms de lettres, « ddd »
        "c'est urgent, il y a de la fumée",    # règle 3 : voyelles-outils, « Yad »
    ],
)
def test_une_phrase_ordinaire_ne_porte_aucune_epellation(phrase):
    assert lire(phrase) == []


def test_un_nom_de_lettre_nouvre_jamais_une_suite():
    """« de », « te », « effe » rejoignent une suite, ne la commencent pas."""
    assert lire("de te effe") == []
    assert _lu("l o i s e l e t") == ["Loiselet"]


def test_la_derniere_lettre_dune_phrase_nest_pas_perdue():
    """⛔ `"" in "'’"` vaut VRAI en Python : la dernière lettre tombait."""
    assert _lu("l e r o y") == ["Leroy"]
    assert _lu("c'est f l a m a n t") == ["Flamant"]


def test_lapostrophe_appartient_au_mot_qui_la_porte():
    """🔑 C'est CE motif qui écarte les élisions, et rien d'autre dans le module.

    Une épreuve de mutation l'a montré : la garde écrite plus bas dans le lecteur
    ne changeait rien, parce que ``MOTS`` **colle l'élision au mot qui suit** —
    « n'y » sort en un seul jeton de trois caractères, jamais lu comme une
    lettre. Retirer l'apostrophe du motif fait réapparaître « Nya » sur
    « il n'y a » (mesuré : 8 tests rouges).
    """
    from api.services.epellation.lecture import MOTS

    assert [m.group() for m in MOTS.finditer("il n'y a")] == ["il", "n'y", "a"]
    assert lire("il n'y a pas de problème") == []
    assert lire("c'est facile d'accès") == []


def test_deux_lettres_ne_font_pas_une_epellation():
    assert lire("a b") == []


# --- 3. L'écriture --------------------------------------------------------


@pytest.mark.parametrize(
    "phrase,attendu",
    [
        ("f l a m a n t", "Flamant"),
        ("W A T T E B L E D", "Wattebled"),
        ("g a r n i e r tiret d u m o n t", "Garnier-Dumont"),
        ("v a n espace h e c k e", "Van Hecke"),
        ("b a r b e accent aigu", "Barbé"),
        ("f r a n c cédille o i s", "François"),
        ("n o e tréma l", "Noël"),
        ("double vé a t t", "Watt"),
        ("d u p o n avec deux t", "Dupontt"),
        ("F comme François, L comme Louis, A comme Anatole", "Fla"),
    ],
)
def test_lecriture_de_ce_qui_est_epele(phrase, attendu):
    assert _lu(phrase) == [_normaliser(attendu)]


# --- 4. Les courriels (Q9) ------------------------------------------------


def test_un_courriel_epele_est_ecrit_en_entier():
    assert _lu("Oui, c'est Marc point v d k arobase example point f r.") == [
        "marc.vdk@example.fr"
    ]


def test_le_tiret_bas_dun_courriel_est_lu():
    assert _lu("m a r i e tiret bas d u p o n t arobase example point com") == [
        "marie_dupont@example.com"
    ]


def test_un_courriel_est_lu_une_seule_fois():
    """« v d k » est à la fois une suite épelée et un morceau de l'adresse."""
    assert len(lire("m a r c point v d k arobase example point f r")) == 1


def test_un_courriel_sans_aucune_lettre_epelee_nest_pas_lu():
    """La limite posée en attendant la réponse d'Evan (IDEE-20260922-1) : ce
    module lit des LETTRES épelées. Le jour où la réponse arrive, ce test change
    avec elle — il dit l'état actuel, pas une vérité éternelle."""
    assert lire("Oui, c'est Marc point ferrand arobase example point com.") == []


# --- 5. La mention --------------------------------------------------------


def test_le_texte_de_la_mention_est_celui_du_plan():
    epellation = Epellation(0, 1, "Flamant", "f l a m a n t")
    assert phrase_de_mention(epellation) == (
        "[Épellation : la personne a épelé « Flamant ». "
        "Note exactement ces lettres, sans les corriger et sans les faire répéter.]"
    )


def test_la_mention_ne_touche_pas_au_texte_de_lappelant():
    texte = "c'est monsieur Flamand, f l a m a n t"
    annote = mentionner_epellations(texte, lire(texte))
    assert annote.startswith(texte)
    assert MARQUE in annote


def test_sans_epellation_le_texte_est_rendu_intact():
    texte = "bonjour, je voudrais faire ramoner mon poêle"
    assert mentionner_epellations(texte, lire(texte)) is texte


def test_deux_epellations_donnent_deux_mentions_dans_lordre():
    texte = "d a n t o n puis l o i s e l e t"
    annote = mentionner_epellations(texte, lire(texte))
    assert annote.count(MARQUE) == 2
    assert annote.index("Danton") < annote.index("Loiselet")


def test_la_mention_est_idempotente():
    texte = "c'est f l a m a n t"
    annote = mentionner_epellations(texte, lire(texte))
    assert deja_mentionne(annote)
    assert not deja_mentionne(texte)


# --- 6. Le comptage, dans les deux sens -----------------------------------


def test_autant_de_mentions_que_depellations_lues_sur_tout_le_corpus():
    """🔑 L'invariant compté : sans lui, un lecteur qui rendrait zéro partout
    passerait les tests négatifs et rendrait le reste vert par accident."""
    attendues = sum(len(cas["attendu"]) for cas in CORPUS)
    lues = sum(len(lire(cas["phrase"])) for cas in CORPUS)
    mentions = sum(
        mentionner_epellations(cas["phrase"], lire(cas["phrase"])).count(MARQUE)
        for cas in CORPUS
    )
    assert lues == attendues == mentions
    # Et ce total n'est pas zéro : le corpus porte bien des épellations.
    assert attendues == 73


def test_chaque_epellation_pointe_sur_le_passage_quelle_a_lu():
    """Le sens inverse : les bornes rendues encadrent bien ce qui a été entendu."""
    for cas in CORPUS:
        for epellation in lire(cas["phrase"]):
            assert cas["phrase"][epellation.debut:epellation.fin] == epellation.entendu
            assert epellation.debut < epellation.fin
