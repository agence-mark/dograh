"""[.mark] Module Restauration, lot 7 (W20, E-37) : les phrases d'attente par outil, au seuil réglable, en variantes, jamais deux fois la même dans un appel.

| Test | Ce qu'il prouve |
|---|---|
| variantes | la première pas encore dite, puis la suivante ; toutes dites : rien ; un autre appel repart de zéro |
| sans variantes | le comportement d'avant : la phrase seule, redite à chaque fois |
| seuil | un outil rapide ne dit rien ; un outil lent dit une variante, au seuil réglé de CET outil |
| deux familles d'outils | l'attente des outils génériques et la patience des outils du catalogue choisissent pareil |
| schéma | la liste est bornée (6 variantes de 300 signes) |
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from api.services.integrations.connectors.champs_requis import Patience
from api.services.outils_mark import variantes_d_attente
from api.services.outils_mark.comportement import Attente


class Moteur:
    def __init__(self):
        self.dites: list[str] = []

    async def queue_text_message(self, texte, mute_user=False):
        self.dites.append(texte)


VARIANTES = {"phrases_attente": ["Je regarde.", "Un instant.", "Je vérifie."], "seuil_patience_ms": 0}


def test_les_variantes_sortent_une_a_une_puis_plus_rien_et_un_autre_appel_repart_de_zero():
    m = Moteur()
    assert [variantes_d_attente.choisir(m, VARIANTES) for _ in range(5)] == ["Je regarde.", "Un instant.", "Je vérifie.", None, None]
    assert variantes_d_attente.choisir(Moteur(), VARIANTES) == "Je regarde."


def test_sans_variantes_la_phrase_seule_est_redite_comme_avant():
    m = Moteur()
    config = {"phrase_attente": "Un instant."}
    assert [variantes_d_attente.choisir(m, config) for _ in range(3)] == ["Un instant."] * 3
    assert variantes_d_attente.choisir(m, {}) is None and not variantes_d_attente.a_une_attente({})


def test_des_doublons_et_des_vides_sont_ecartes():
    assert variantes_d_attente.les_variantes({"phrases_attente": ["a", "a", " ", None, "b"]}) == ["a", "b"]


async def _lent(classe, config, moteur, duree):
    a = classe(moteur, config)
    a.demarrer()
    await asyncio.sleep(duree)
    a.arreter()


async def test_le_seuil_de_l_outil_decide_et_deux_appels_lents_disent_deux_variantes_differentes():
    m = Moteur()
    config = {**VARIANTES, "seuil_patience_ms": 50}
    await _lent(Attente, config, m, 0.01)                 # outil rapide : le seuil n'est pas atteint
    assert m.dites == []
    await _lent(Attente, config, m, 0.15)
    await _lent(Patience, config, m, 0.15)                # l'autre famille d'outils partage la mémoire de l'appel
    assert m.dites == ["Je regarde.", "Un instant."]


def test_le_schema_borne_les_variantes():
    from api.schemas.tool import IntegrationToolConfig as C

    base = {"connecteur": "commande", "action": "ajouter"}
    assert C(**base, phrases_attente=["a", "b"]).phrases_attente == ["a", "b"]
    with pytest.raises(ValidationError):
        C(**base, phrases_attente=["x"] * 7)
    with pytest.raises(ValidationError):
        C(**base, phrases_attente=["x" * 301])
