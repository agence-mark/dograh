"""[.mark] SA-18, lot C (C10) : un nom d'outil écrit en texte est lu même suivi d'un reste de jeton ou du texte de son argument.

Aux essais du 17/11 : « passer_a_l_agent_commandeLa » (nom collé au début du texte de l'argument), « passer_a_l_agent_commande "La personne veut… » (argument
positionnel entre guillemets), « passer_a_l_agent_service dj{…} » (reste de jeton de Mistral devant l'accolade) étaient dits à voix haute.
"""

import pytest

from api.services.pipecat.texte_du_cerveau import _outil_ecrit_possible, lire_un_outil_ecrit

OUTILS = ["passer_a_l_agent_commande", "passer_a_l_agent_service", "fin"]
PARAMETRES = {"passer_a_l_agent_commande": "demande", "passer_a_l_agent_service": "demande"}


def test_un_argument_positionnel_entre_guillemets_est_lu():
    texte = 'passer_a_l_agent_commande "La personne veut commander une Regina à emporter."'
    assert lire_un_outil_ecrit(texte, OUTILS, PARAMETRES) == (
        "passer_a_l_agent_commande", '{"demande": "La personne veut commander une Regina à emporter"}'
    )


def test_le_nom_colle_au_texte_de_l_argument_est_lu():
    nom, arguments = lire_un_outil_ecrit("passer_a_l_agent_commandeLa personne veut une Regina", OUTILS, PARAMETRES)
    assert nom == "passer_a_l_agent_commande" and "personne veut une Regina" in arguments


def test_un_reste_de_jeton_devant_l_accolade_est_ignore():
    texte = 'passer_a_l_agent_service dj{"demande": "réclamation"}'
    assert lire_un_outil_ecrit(texte, OUTILS, PARAMETRES) == ("passer_a_l_agent_service", '{"demande": "réclamation"}')


def test_sans_parametre_connu_le_texte_derriere_le_nom_n_est_pas_lu():
    assert lire_un_outil_ecrit('passer_a_l_agent_commande "La personne veut"', OUTILS) is None
    assert lire_un_outil_ecrit("Fin de la conversation", OUTILS, PARAMETRES) is None  # « fin » n'a pas de paramètre, et le mot est suivi d'une lettre


def test_le_flux_reste_retenu_tant_que_le_texte_peut_etre_l_argument():
    assert _outil_ecrit_possible('passer_a_l_agent_commande "La personne', OUTILS, PARAMETRES)
    assert not _outil_ecrit_possible('passer_a_l_agent_commande "La personne', OUTILS)  # sans paramètre connu : comme avant


@pytest.mark.parametrize("parole", ["Finalement je préfère une Regina.", "Je passe à l'agent de commande."])
def test_une_parole_normale_n_est_jamais_retenue(parole):
    assert not _outil_ecrit_possible(parole, OUTILS, PARAMETRES)
    assert lire_un_outil_ecrit(parole, OUTILS, PARAMETRES) is None
