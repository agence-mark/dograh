"""[.mark] M93 : l'agent dit le prénom de l'appelant (« Merci Thomas », Casa et l'Étoile d'Or). Le filtre du nom est coupé (M77 : il cassait
« C'est noté pour Julien. » en « C'est noté pour. »). Le retrait du SEUL vocatif (réglage ``retirer_vocatif_appelant``, éteint par défaut) :
en tête après une formule de politesse, en tête suivi d'une virgule, en fin après une virgule ; jamais au milieu, jamais après une préposition.
"""

import pytest
from pipecat.frames.frames import LLMTextFrame

from api.services.pipecat.filtre_nom_civilite import FiltreNomCiviliteProcessor, creer_filtre_nom_civilite, retirer_vocatif
from api.tests.mark.test_replique_abimee_apres_un_outil import _contexte, _jouer


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("Merci Thomas.", "Merci."),
        ("Merci Thomas, c'est noté.", "Merci, c'est noté."),
        ("Merci beaucoup, Thomas !", "Merci beaucoup !"),
        ("Parfait Thomas, quel est votre numéro ?", "Parfait, quel est votre numéro ?"),
        ("Très bien Thomas.", "Très bien."),
        ("D'accord Thomas, je regarde.", "D'accord, je regarde."),
        ("Thomas, c'est noté.", "C'est noté."),
        ("C'est noté, Thomas.", "C'est noté."),
        ("C'est enregistré. Merci Thomas, autre chose ?", "C'est enregistré. Merci, autre chose ?"),
        # M77 : les phrases que l'ancien filtre cassait restent intactes
        ("C'est noté pour Thomas.", "C'est noté pour Thomas."),
        ("C'est noté pour Thomas, à quelle heure ?", "C'est noté pour Thomas, à quelle heure ?"),
        ("Je mets la commande au nom de Thomas.", "Je mets la commande au nom de Thomas."),
        ("Une pizza pour Thomas et une pour Claire.", "Une pizza pour Thomas et une pour Claire."),
        ("Merci Thomas pour votre appel.", "Merci Thomas pour votre appel."),  # au milieu : jamais
        ("Je livre au 8 rue Thomas.", "Je livre au 8 rue Thomas."),
        ("Thomas ?", "Thomas ?"),  # une phrase qui n'est que le nom : jamais vidée
        ("Merci thomas.", "Merci thomas."),  # sans majuscule, ce n'est pas la personne
    ],
)
def test_seul_le_vocatif_part(texte, attendu):
    assert retirer_vocatif(texte, ["Thomas"]) == attendu


def test_eteint_par_defaut():
    assert creer_filtre_nom_civilite({}, lambda: {}) is None
    assert creer_filtre_nom_civilite({"retirer_vocatif_appelant": True}, lambda: {}) is not None


@pytest.mark.asyncio
async def test_le_processeur_retire_le_vocatif_du_prenom_de_la_fiche_et_de_l_outil():
    def filtre(variables, contexte=None):
        return FiltreNomCiviliteProcessor(
            retirer_nom=False, retirer_civilite=False, retirer_vocatif=True, variables=lambda: variables, contexte=lambda: contexte or {}, mode_envoi="sentence",
        )

    frames = await _jouer(filtre({"prenom": "Thomas"}), [LLMTextFrame("Merci Thomas, c'est noté pour Thomas. Autre chose ?")])
    assert "".join(f.text for f in frames) == "Merci, c'est noté pour Thomas. Autre chose ?"
    frames = await _jouer(filtre({}, _contexte({"prenom": "Julien"})), [LLMTextFrame("Parfait Julien. Quel est votre numéro ?")])
    assert "".join(f.text for f in frames) == "Parfait. Quel est votre numéro ?"
