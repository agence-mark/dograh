"""[.mark] Non-regression test for the names of the team found in a text (l-agent-collegue, L3).

The questions this file answers (C12, C13, R7):

    On a corpus whose truth is posed BY HAND -- names deformed like the transcription
    deforms them (« Kamil » for Camille, « Sasha » for Sacha, « Tiery », « Maël Roux »),
    full names, composed first names, two people sharing a first name -- does the finder
    give exactly the expected people with the expected certainty, and NOTHING else? On
    sentences without any name of the team, but full of words that ARE names elsewhere
    (« rose », « claire », « petit », « blanc », « le matin »), does it find NOTHING?

Both directions are asserted, and counted: a finder that answers nothing would pass the
negative half, a finder that answers everything the positive half.

🔴 The known red case (R7): « Le rendez-vous est fixé demain matin. » -- « matin » is
« Martin » to the spelling score (91). Without the rule « a single word counts only with a
capital », it is a mention of Camille Martin. Proved red by switching the rule off (journal
of the chantier, L3).

⚠️ Known limit, kept out of the truth on purpose: « Inesse » for « Inès » is not found
(both sound keys drop the final s of « Inès »). Not a false positive: a miss.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.noms_personnes import reperer
from api.services.noms_personnes import reperage as module

# Neutral people from several trades (X5).
EQUIPE = [
    SimpleNamespace(cle="camille", prenom="Camille", nom="Martin"),
    SimpleNamespace(cle="sacha", prenom="Sacha", nom="Bernard"),
    SimpleNamespace(cle="julien-p", prenom="Julien", nom="Petit"),
    SimpleNamespace(cle="julien-m", prenom="Julien", nom="Moreau"),
    SimpleNamespace(cle="rose", prenom="Rose", nom="Lefèvre"),
    SimpleNamespace(cle="jean-marc", prenom="Jean-Marc", nom="Dubois"),
    SimpleNamespace(cle="ines", prenom="Inès", nom="Garcia"),
    SimpleNamespace(cle="thierry", prenom="Thierry", nom="Laurent"),
    SimpleNamespace(cle="maelle", prenom="Maëlle", nom="Roux"),
    SimpleNamespace(cle="kevin", prenom="Kevin", nom="Blanc"),
    SimpleNamespace(cle="claire", prenom="Claire", nom="Fontaine"),
]

# The truth, posed by hand: text → {key: certainty}.
AVEC_NOMS = [
    ("La personne a demandé à parler à Kamil pour sa facture.", {"camille": "a_confirmer"}),
    ("Elle voulait joindre Julien.", {"julien-p": "a_confirmer", "julien-m": "a_confirmer"}),
    ("Julien Petit doit la rappeler.", {"julien-p": "detectee"}),
    ("Sasha Bernard a été prévenu.", {"sacha": "detectee"}),
    ("Jean Marc a pris le dossier.", {"jean-marc": "detectee"}),
    ("Le dossier ira à Jean-Marc.", {"jean-marc": "detectee"}),
    ("L'assistant a transmis à Mme Martin.", {"camille": "detectee"}),
    ("La personne souhaite que Thierry la rappelle.", {"thierry": "detectee"}),
    ("Elle a été orientée vers Tiery pour le devis.", {"thierry": "a_confirmer"}),
    ("Le dossier est suivi par Maël Roux.", {"maelle": "detectee"}),
    ("Claire Fontaine rappellera la personne demain.", {"claire": "detectee"}),
    ("Elle a parlé avec Monsieur Blanc.", {"kevin": "detectee"}),
    ("Rose Lefèvre", {"rose": "detectee"}),
    ("Inès Garcia et Sacha ont reçu la demande.", {"ines": "detectee", "sacha": "detectee"}),
]

SANS_NOM = [
    "La personne a demandé un devis pour une extension de garage.",
    "Le rendez-vous est fixé demain matin.",
    "Petit souci sur la facture du mois dernier.",
    "La façade sera peinte en rose et blanc.",
    "Elle trouve la notice peu claire.",
    "Le mur en pierre s'est fissuré près de la fontaine.",
    "La personne attend un colis de Martinique.",
    "Rose a été choisie comme couleur des volets.",
    "Blanc cassé, la teinte demandée.",
    "Le patient souhaite déplacer sa séance de kinésithérapie.",
    "La commande numéro 4521 n'est pas arrivée.",
    "Elle habite rue Jean Jaurès à Creil.",
    "La personne veut parler au responsable du planning.",
    "Monsieur Dupont a appelé pour son contrat d'assurance.",
    "Elle souhaite une table pour quatre personnes samedi soir.",
    "L'assistant a promis un rappel avant midi.",
    "Claire et nette, la réponse a rassuré la personne.",
    "Le client de Laurentides a confirmé.",
    "La personne a demandé si le magasin de Rouen était ouvert.",
    "Elle appelle pour un abonnement mensuel.",
]


def _trouve(texte: str) -> dict[str, str]:
    return {r.cle: r.certitude for r in reperer(texte, EQUIPE)}


@pytest.mark.parametrize("texte,attendu", AVEC_NOMS)
def test_les_noms_de_lequipe_sont_trouves_exactement(texte, attendu):
    assert _trouve(texte) == attendu


@pytest.mark.parametrize("texte", SANS_NOM)
def test_aucun_faux_positif_sur_une_phrase_sans_nom(texte):
    assert _trouve(texte) == {}


def test_le_compte_dans_les_deux_sens():
    """A mute finder passes the negatives, a greedy one the positives: both counted."""
    trouves = sum(len(_trouve(t)) for t, _ in AVEC_NOMS)
    attendus = sum(len(a) for _, a in AVEC_NOMS)
    faux = sum(len(_trouve(t)) for t in SANS_NOM)
    assert (trouves, faux) == (attendus, 0)
    assert attendus >= 15 and len(SANS_NOM) >= 20


def test_le_cas_rouge_connu_depend_de_la_regle_des_majuscules(monkeypatch):
    """R7: « matin » is a mention of Martin as soon as the capital rule is gone."""
    reel = module._jetons

    def sans_majuscules(texte):
        return [
            module._Jeton(j.norm, True, False, j.debut, j.fin) for j in reel(texte)
        ]

    monkeypatch.setattr(module, "_jetons", sans_majuscules)
    assert "camille" in _trouve("Le rendez-vous est fixé demain matin.")


def test_lextrait_est_court_et_le_texte_intact():
    texte = "x " * 300 + "Julien Petit doit la rappeler." + " y" * 300
    [r] = reperer(texte, EQUIPE)
    assert r.forme == "Julien Petit" and len(r.extrait) <= 200 and "Julien Petit" in r.extrait


def test_jamais_dexception():
    assert reperer(None, EQUIPE) == [] and reperer("Julien", None) == []
    assert reperer("Julien", [SimpleNamespace(cle="x", prenom=None, nom=None)]) == []
