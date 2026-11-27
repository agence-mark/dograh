"""[.mark] Agent fiable (Evan, 17/11) : à chaque requête, le modèle reçoit l'ÉTAT de la commande calculé par le code, pour poser lui-même la
bonne question au bon moment sans appeler un outil pour la découvrir (un passage du modèle par tour au lieu de deux).

| Test | Ce qu'il prouve |
|---|---|
| E1 | début de commande, rien de posé, établissement fermé au décroché : le mode manque ensuite, la fermeture et la réouverture sont dites |
| E2 | vraie carte, fermé : après le premier geste, les modes offerts et la reprise retenus par la source (aucune requête ajoutée à l'état) |
| E3 | vraie carte, en livraison, « une reine » sans taille : la ligne prise, et ce qui manque ensuite est la taille avec ses options |
| E4 | vraie carte, « c'est tout » : ``finaliser`` attend le prénom, l'état le dit ; rien n'est encore à demander à la fin avant |
| E5 | minimum de la zone : dit sur un panier vide, « pas atteint » avec ce qui manque sous le minimum, rien quand il est atteint |
| E6 | une commande enregistrée : l'état le dit, rien ne manque |
| E7 | par le vrai gestionnaire de l'outil (``executer``) et le connecteur déclaré : la source retient les modes, l'état de l'étape les dit |
| R1 | mécanisme : un outil du connecteur dans la requête range l'état en fin d'instruction système, remplacé (jamais empilé) à la requête suivante |
| R2 | mécanisme : sans outil d'un connecteur à état, l'instruction système n'est pas touchée (agent sans commande : comportement d'avant) ; un bloc d'avant est retiré |
| R3 | inscription : le connecteur d'un outil est retenu par son nom de fonction ; un outil sans connecteur est oublié |
| R4 | par le vrai circuit autour du cerveau : la requête construite porte l'état dans le message système, l'historique n'est pas touché |
| M1 | aucun mot de métier dans le mécanisme commun ni dans l'état de la commande |
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.tests import MockLLMService

from api.db.bases_clients import horloge
from api.services.commande import etat_pour_le_modele as etat, moteur, panier
from api.services.workflow import etat_des_connecteurs as mecanisme
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_naturelle_casa import Appel, casa  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import PARIS
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401

ADRESSE_SENLIS = "12 rue de Beauvais, 60300 Senlis"
JEUDI_APRES_MIDI = datetime(2026, 11, 12, 15, 30, tzinfo=PARIS)  # entre le service de midi et celui du soir : fermé


def _etat(p: dict, appel: dict | None = None, fiche: dict | None = None) -> str:
    t = etat.texte({**(fiche or {}), panier.CLE: p}, appel or {})
    assert t is not None
    print(f"\n{t}\n({len(t)} caractères)")
    return t


# --------------------------------------------------------------------------- #
# L'état de la commande
# --------------------------------------------------------------------------- #


def test_e1_debut_rien_de_pose():
    t = etat.texte({}, {"etat_ouverture": "FERME", "reouverture": "à dix-huit heures"})
    print(f"\n{t}\n({len(t)} caractères)")
    assert t.startswith(etat.ENTETE)
    # Lot 6 (D49) : l'état dit le mode, les lignes et ce qui manque ; la fermeture n'y est plus (lue au décroché, ``lire_l_ouverture`` du lot 4 ;
    # sens repris par partie_1/test_l04_cuisine.py::test_pause_de_la_caisse_au_decroche)
    assert "Mode de retrait : pas encore dit." in t and "Lignes : aucune." in t
    assert "Ce qui manque ensuite : le mode de retrait" in t
    assert "fermé" not in t










def test_e6_commande_enregistree():
    """C7 B10 (T8) : depuis le lot 2 de P1F (``fc038c7b``), l'étape est stockée et ne se déduit plus de ``p["enregistree"]`` : la commande s'enregistre par sa transition."""
    from api.services.commande import etape as ETAPE

    p = panier.nouveau()
    p["lignes"] = [{"n": 1, "nom": "X", "code": "x", "quantite": 1, "choix": [], "retires": []}]
    ETAPE.transition(p, ETAPE.ENREGISTREE_EN_BASE, faits={"numero_court": "C12"}, empreinte=panier.empreinte(p))
    t = _etat(p)
    assert "Commande de cet appel enregistrée (numéro C12)" in t and "Ce qui manque" not in t


# test_e7_par_le_vrai_gestionnaire_et_le_connecteur_declare : supprimé au lot 6 (D49), il jouait ``choisir_mode`` (outil retiré) ; sens repris par partie_1/test_l06_parole.py::test_fiche_dans_le_systeme


# --------------------------------------------------------------------------- #
# Le mécanisme commun
# --------------------------------------------------------------------------- #


def _outils(*noms: str) -> ToolsSchema:
    return ToolsSchema(standard_tools=[FunctionSchema(name=n, description="x", properties={}, required=[]) for n in noms])


def _moteur(fiche: dict | None = None) -> SimpleNamespace:
    m = SimpleNamespace(_gathered_context=fiche if fiche is not None else {}, _call_context_vars={})
    mecanisme.inscrire_l_outil(m, "ajouter", SimpleNamespace(definition={"config": {"connecteur": "commande", "action": "ajouter"}}))
    mecanisme.inscrire_l_outil(m, "chercher", SimpleNamespace(definition={"config": {}}))
    return m


def _cerveau() -> MockLLMService:
    cerveau = MockLLMService(mock_steps=[], chunk_delay=0)
    cerveau._base_system_instruction = "Tu prends la demande."
    cerveau._compose_system_instruction()
    return cerveau


def test_r1_l_etat_finit_l_instruction_systeme_remplace_jamais_empile():
    p = panier.nouveau()
    m, cerveau = _moteur({panier.CLE: p}), _cerveau()
    assert mecanisme.placer_l_etat(m, cerveau, _outils("chercher", "ajouter")) is True
    instruction = cerveau._settings.system_instruction
    assert instruction.startswith("Tu prends la demande.") and instruction.split("\n\n", 1)[1].startswith(etat.ENTETE)
    assert "Mode de retrait : pas encore dit." in instruction
    p["mode"] = "emporter"
    mecanisme.placer_l_etat(m, cerveau, _outils("ajouter"))
    apres = cerveau._settings.system_instruction
    assert apres.count(etat.ENTETE) == 1 and "Mode de retrait : à emporter." in apres and "pas encore dit" not in apres


def test_r2_sans_outil_d_un_connecteur_a_etat_rien_n_est_touche():
    cerveau = _cerveau()
    avant = cerveau._settings.system_instruction
    assert mecanisme.placer_l_etat(SimpleNamespace(_gathered_context={}), cerveau, _outils("ajouter")) is False  # aucun outil inscrit
    assert mecanisme.placer_l_etat(_moteur(), cerveau, _outils("chercher")) is False
    assert cerveau._settings.system_instruction == avant and cerveau._appended_system_instructions == []
    # l'étape suivante n'a plus l'outil : le bloc d'avant est retiré
    m = _moteur()
    mecanisme.placer_l_etat(m, cerveau, _outils("ajouter"))
    assert etat.ENTETE in cerveau._settings.system_instruction
    mecanisme.placer_l_etat(m, cerveau, _outils("chercher"))
    assert cerveau._settings.system_instruction == avant and cerveau._appended_system_instructions == []


def test_r3_inscription_par_nom_de_fonction():
    m = _moteur()
    assert mecanisme.connecteurs_de_la_requete(m, _outils("chercher", "ajouter")) == ["commande"]
    assert mecanisme.connecteurs_de_la_requete(m, [{"type": "function", "function": {"name": "ajouter"}}]) == ["commande"]
    mecanisme.inscrire_l_outil(m, "ajouter", SimpleNamespace(definition={"config": {}}))
    assert mecanisme.connecteurs_de_la_requete(m, _outils("ajouter")) == []


@pytest.mark.asyncio
async def test_r4_par_le_vrai_circuit_la_requete_porte_l_etat_dans_le_message_systeme():
    from pipecat.frames.frames import LLMContextFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.tests.utils import run_test

    from api.services.pipecat.avant_la_requete import autour_du_cerveau
    from api.tests.mark.test_figeage_v12_lot_a2 import CerveauRequetes, _monter_avec_la_case

    harness, engine, cerveau = await _monter_avec_la_case(CerveauRequetes, case=False, cerveau=CerveauRequetes())
    try:
        mecanisme.inscrire_l_outil(engine, "ajouter", SimpleNamespace(definition={"config": {"connecteur": "commande"}}))
        engine._gathered_context[panier.CLE] = panier.nouveau()
        messages = [{"role": "assistant", "content": "Je vous écoute."}, {"role": "user", "content": "je voudrais commander"}]
        avant, apres = autour_du_cerveau(engine, engine.active_agent)
        contexte = LLMContext(messages=[dict(m) for m in messages], tools=_outils("ajouter"))
        await run_test(Pipeline([avant, cerveau, apres]), frames_to_send=[LLMContextFrame(contexte)], start_timeout=10.0)
        requete = cerveau.vues[-1]
        systemes = [m for m in requete["messages"] if m.get("role") == "system"]
        assert len(systemes) == 1 and etat.ENTETE in systemes[0]["content"] and "le mode" in systemes[0]["content"]
        assert [m["content"] for m in requete["messages"] if m.get("role") == "user"] == ["je voudrais commander"]
        assert contexte.get_messages() == messages
    finally:
        await harness.stop()


@pytest.mark.xfail(strict=True, reason="Défaut possible du lot 6 : etat_pour_le_modele.py porte des mots de métier (allergie, livraison), voir a-trancher.md")
def test_m1_aucun_mot_de_metier():
    from api.tests.mark.test_restauration_commande_outils import MOTS_DU_METIER

    racine = Path(etat.__file__).parent.parent
    for chemin in (racine / "commande" / "etat_pour_le_modele.py", racine / "workflow" / "etat_des_connecteurs.py"):
        corps = chemin.read_text(encoding="utf-8")
        assert [x.group(0) for x in MOTS_DU_METIER.finditer(corps)] == [], chemin.name
    commun = (racine / "workflow" / "etat_des_connecteurs.py").read_text(encoding="utf-8").casefold()
    for mot in ("pizza", "restaurant", "commande", "panier", "réservation", "reservation", "caisse", "hubrise", "devis", "rendez-vous"):
        assert mot not in commun, mot
