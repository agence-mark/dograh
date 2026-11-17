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
from api.services.commande import action, etat_pour_le_modele as etat, moteur, panier
from api.services.workflow import etat_des_connecteurs as mecanisme
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_naturelle_casa import Appel, casa  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import PARIS
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401

ADRESSE_SENLIS = "12 rue de Beauvais, 60300 Senlis"
JEUDI_APRES_MIDI = datetime(2026, 11, 12, 15, 30, tzinfo=PARIS)  # entre le service de midi et celui du soir : fermé


def _etat(p: dict, appel: dict | None = None) -> str:
    t = etat.texte({panier.CLE: p}, appel or {})
    assert t is not None
    print(f"\n{t}\n({len(t)} caractères)")
    return t


async def _geste(a: Appel, nom: str, arguments: dict):
    """Un geste comme ``executer`` le joue : la source qui retient, puis ce qu'elle a dit écrit dans le panier."""
    source = etat.SourceQuiRetient(a.source)
    nom, arguments = action.vers_la_question_en_attente(source, a.p, nom, arguments)
    r = await action._geste(source, a.p, a.regles, nom, arguments, SimpleNamespace(run_id=None, appel={}, fiche={}))
    a.p["question_en_attente"] = action.reponse_attendue(nom, r)
    etat.retenir(a.p, source)
    return r


# --------------------------------------------------------------------------- #
# L'état de la commande
# --------------------------------------------------------------------------- #


def test_e1_debut_rien_de_pose_ferme_au_decroche():
    t = etat.texte({}, {"etat_ouverture": "FERME", "reouverture": "à dix-huit heures"})
    print(f"\n{t}\n({len(t)} caractères)")
    assert t.startswith(etat.ENTETE)
    assert "Pris : rien pour l'instant." in t
    assert "Établissement fermé en ce moment, réouverture : à dix-huit heures." in t
    assert "Ce qui manque ensuite : le mode." in t
    # ouvert au décroché : rien n'est dit de l'ouverture
    assert "fermé" not in etat.texte({}, {"etat_ouverture": "OUVERT", "reouverture": ""})


async def test_e2_ferme_apres_le_premier_geste_modes_et_reprise_retenus(casa):
    with horloge.remplacer(casa.base, JEUDI_APRES_MIDI):
        a = Appel(casa)
        await _geste(a, "choisir_mode", {"sens": "autre", "mots": "je voudrais commander"})
        t = _etat(a.p, {"etat_ouverture": "FERME", "reouverture": "à dix-huit heures"})
    assert "Fermé en ce moment, reprise : dix-huit heures" in t, t
    assert "Ce qui manque ensuite : le mode (à emporter, en livraison" in t, t  # les modes que la source offre
    assert "Établissement" not in t  # la source sait mieux que le décroché : son état passe devant


async def test_e3_une_reine_en_livraison_sans_taille(casa):
    a = Appel(casa)
    await _geste(a, "choisir_mode", {"mode": "livraison", "adresse": ADRESSE_SENLIS, "mots": f"en livraison au {ADRESSE_SENLIS}"})
    r = await _geste(a, "ajouter", {"articles": "une reine", "mots": "une reine"})
    assert r.statut == "CHOIX_OBLIGATOIRE", r
    t = _etat(a.p)
    assert "Mode : en livraison." in t and "Adresse : 12 rue de Beauvais" in t and "(zone Senlis)" in t, t
    assert "Pris : 1 × Regina, taille à choisir." in t, t
    assert "Ce qui manque ensuite : taille pour Regina : " in t, t
    assert "Encore à obtenir quand elle aura tout dit : prénom, numéro de téléphone et règlement." in t, t


async def test_e4_c_est_tout_le_prenom_manque(casa):
    a = await Appel(casa).a_emporter()
    await _geste(a, "ajouter", {"articles": "une reine", "choix": "normale", "mots": "une reine normale"})
    assert not panier.a_completer(a.p), a.p["lignes"]
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "c'est tout"})
    assert a.p["question_en_attente"] == "finaliser.prenom", r
    t = _etat(a.p)
    assert "Ce qui manque ensuite : le prénom." in t, t
    assert "Encore à obtenir" not in t  # la fin est en cours : ce qui manque ensuite suffit


async def test_e5_le_minimum_de_la_zone(casa):
    await casa.c.execute("UPDATE mark.resto_zone SET minimum = 2500 WHERE id = $1", casa.zone)
    a = Appel(casa)
    await _geste(a, "choisir_mode", {"mode": "livraison", "adresse": ADRESSE_SENLIS, "mots": ADRESSE_SENLIS})
    assert "Minimum de commande pour cette adresse : vingt-cinq euros." in _etat(a.p)
    await _geste(a, "ajouter", {"articles": "une reine", "choix": "normale", "mots": "une reine normale"})
    t = _etat(a.p)
    assert "vingt-cinq euros, pas atteint (il manque " in t, t
    await _geste(a, "ajouter", {"articles": "trois reines", "choix": "normale", "mots": "trois reines normales"})
    assert "Minimum" not in _etat(a.p)
    # une ligne changée sans nouveau chiffrage : on ne dit plus « atteint » ni « pas atteint », seulement le minimum
    a.p["lignes"][0]["quantite"] = 9
    assert "Minimum de commande pour cette adresse : vingt-cinq euros." in _etat(a.p)


def test_e6_commande_enregistree():
    p = panier.nouveau()
    p["lignes"] = [{"n": 1, "nom": "X", "code": "x", "quantite": 1, "choix": [], "retires": []}]
    p["enregistree"] = {"numero_court": "C12"}
    t = _etat(p)
    assert "Commande enregistrée (numéro C12)." in t and "manque" not in t


async def test_e7_par_le_vrai_gestionnaire_et_le_connecteur_declare(appel_de_test):
    await appel_de_test.jouer("choisir_mode", sens="autre", mots="je voudrais commander")
    assert (appel_de_test.fiche[panier.CLE].get(etat.CLE_CONNU) or {}).get("modes"), appel_de_test.fiche[panier.CLE]
    m = appel_de_test.moteur
    mecanisme.inscrire_l_outil(m, "ajouter", SimpleNamespace(definition={"config": {"connecteur": "commande", "action": "ajouter"}}))
    t = mecanisme.texte_de_l_etat(m, _outils("ajouter"))
    print(t)
    assert t and t.startswith(etat.ENTETE) and "Ce qui manque ensuite : le mode (à emporter" in t, t
    await appel_de_test.jouer("choisir_mode", mode="à emporter")
    assert "Mode : à emporter." in mecanisme.texte_de_l_etat(m, _outils("ajouter"))


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
    assert "le mode" in instruction
    p["mode"] = "emporter"
    mecanisme.placer_l_etat(m, cerveau, _outils("ajouter"))
    apres = cerveau._settings.system_instruction
    assert apres.count(etat.ENTETE) == 1 and "Mode : emporter." in apres and "le mode" not in apres


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


def test_m1_aucun_mot_de_metier():
    from api.tests.mark.test_restauration_commande_outils import MOTS_DU_METIER

    racine = Path(etat.__file__).parent.parent
    for chemin in (racine / "commande" / "etat_pour_le_modele.py", racine / "workflow" / "etat_des_connecteurs.py"):
        corps = chemin.read_text(encoding="utf-8")
        assert [x.group(0) for x in MOTS_DU_METIER.finditer(corps)] == [], chemin.name
    commun = (racine / "workflow" / "etat_des_connecteurs.py").read_text(encoding="utf-8").casefold()
    for mot in ("pizza", "restaurant", "commande", "panier", "réservation", "reservation", "caisse", "hubrise", "devis", "rendez-vous"):
        assert mot not in commun, mot
