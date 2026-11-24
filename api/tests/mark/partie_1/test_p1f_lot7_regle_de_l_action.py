"""[.mark] Lot 7a, ligne 63 : les deux formes de Pierre 12 (« j'ai bien enregistré votre allergie » n'annonce pas la commande ; « votre commande est passée » l'annonce) rejoignent la règle
commune « c'est fait » de ``verite_des_actions``, sans mot du métier dans la règle : l'appelant lui donne ses verbes, ses objets et sa forme. Le verdict est celui de l'ancienne
double expression, phrase par phrase ; la règle par défaut, celle des autres agents, ne bouge pas."""

from __future__ import annotations

import re

import pytest

from api.services.workflow import verite_des_actions as V
from api.services.workflow.parole_de_la_fiche import annonce_non_fondee

PHRASES = [
    "Votre commande est passée.", "Votre commande a été bien passée.", "Votre commande est enregistrée.", "J'ai bien enregistré votre commande.",
    "J'ai bien enregistré votre allergie au lait.", "J'ai noté votre allergie.", "Nous avons confirmé votre numéro.", "On a déjà validé vos informations.",
    "J'ai bien enregistré votre réservation.", "Votre commande est annulée.", "J'ai annulé votre commande.", "J'ai annulé votre rendez-vous.",
    "Votre commande est enregistrée et j'ai bien enregistré votre allergie.", "J'ai bien enregistré votre allergie. Votre commande est passée.",
    "Commande enregistrée, elle sera prête pour dix-neuf heures.", "Votre commande est-elle passée ?", "Votre commande est prise en charge.",
    "C'est validé.", "La pizza est passée au four.", "J'ai bien enregistré votre prénom et votre commande est annulée.",
]


def _ancien(phrase: str, p: dict) -> bool:
    """L'ancienne double expression, recopiée telle quelle, pour comparer."""
    return any(_ancien_phrase(x, p) for x in V._phrases(phrase))


def _ancien_phrase(phrase: str, p: dict) -> bool:
    autre = re.search(r"\b(?:j['’]ai|nous\s+avons|on\s+a)\s+(?:bien\s+|déjà\s+)?(?:enregistré|confirmé|validé)\s+(?:votre|vos|ton|ta|tes)\s+(?!commande|réservation)", phrase, re.IGNORECASE)
    if phrase.rstrip().endswith("?") or autre:
        return False
    faite, annulee = V.regle_de_l_action_faite(("enregistré", "confirmé", "validé")), V.regle_de_l_action_faite(("annulé",))
    if not p.get("enregistree") and re.search(r"\bcommande\b[^.!?]*\b(?:est|a\s+été)\s+(?:bien\s+|déjà\s+)?pass[ée]e?\b", phrase, re.IGNORECASE):
        return True
    return bool((not p.get("enregistree") and faite.search(phrase)) or (not p.get("annulee") and annulee.search(phrase)))


@pytest.mark.parametrize("phrase", PHRASES)
@pytest.mark.parametrize("p", [{"enregistree": None}, {"enregistree": {"numero": 1}}, {"enregistree": None, "annulee": True}, {"enregistree": {"numero": 1}, "annulee": True}])
def test_le_verdict_est_celui_de_l_ancienne_double_expression(phrase, p):
    assert annonce_non_fondee(phrase, p) is _ancien(phrase, p), (phrase, p)


def test_le_cas_de_pierre_12_reste_dit_et_l_allergie_reste_hors_jugement():
    assert annonce_non_fondee("Votre commande est passée.", {"enregistree": None}) is True
    assert annonce_non_fondee("J'ai bien enregistré votre allergie au lait.", {"enregistree": None}) is False


def test_un_agent_temoin_hors_restauration_garde_exactement_sa_regle():
    """La règle par défaut (sans les mots d'un métier) juge « j'ai bien enregistré votre allergie » : rien n'y est écarté, et sa forme n'a pas bougé."""
    regle = V.regle_de_l_action_faite(("enregistré", "confirmé", "validé"))
    assert regle.search("J'ai bien enregistré votre allergie au lait.")
    assert regle.search("Votre commande est passée.") is None
    assert regle is V.regle_de_l_action_faite(("enregistré", "confirmé", "validé"))
    assert "(?!" not in regle.pattern.split("{")[0].replace(V._ETAT_ET_NON_ACTION, "")
    assert V.regle_de_l_action_faite() is V._ACTION_FAITE


def test_aucun_mot_du_metier_dans_la_regle_commune():
    source = open(V.__file__, encoding="utf-8").read()
    debut = source.index("def _regle_de_l_action_faite")
    fin = source.index("_ACTION_FAITE = regle_de_l_action_faite()")
    code = chr(10).join(ligne for ligne in source[debut:fin].splitlines() if not ligne.lstrip().startswith("#"))
    for mot in ("commande", "réservation", "allergie", "pizza"):
        assert mot not in code, mot
