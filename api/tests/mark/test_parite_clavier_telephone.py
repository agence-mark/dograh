"""[.mark] Parité clavier / téléphone (chantier actions-sures-et-parite-clavier, lot A).

Plan `Labo-agent-vocal/plans/actions-sures-et-parite-clavier/`. Banc de fin du 27/10 : le garde-fou d'impasse, branché
dans `run_pipeline.py` (téléphone) mais pas dans `text_chat_runner.py` (clavier), était inerte au clavier ; un banc entier
perdu à le découvrir. Règle d'Evan : tout ce qui existe au téléphone existe au clavier, sauf ce qui est audio par nature.

| Test | Ce qu'il prouve |
|---|---|
| inventaire | chaque branchement du téléphone (`brancher_*`, `creer_*`, `armer_*`, `poser_*`) existe au clavier, ou figure dans les exceptions avec sa raison |
| exceptions | la liste des exceptions ne garde que des branchements qui existent encore au téléphone et manquent au clavier |
| garde-fou | une session clavier où l'agent redit la même réplique pose le temps 1 puis le temps 2 |
| civilité | une session clavier, interrupteur allumé : la civilité n'est ni montrée ni gardée en mémoire |
| journal | une entrée du journal des requêtes devient un événement du tour |
"""

import re
from pathlib import Path

import pytest

from api.services.workflow.sortie_d_impasse import CLE_IMPASSE
from api.services.workflow.text_chat_runner import _JournalDuClavier
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

RACINE = Path(__file__).resolve().parents[2] / "services"
TELEPHONE = RACINE / "pipecat" / "run_pipeline.py"
CLAVIER = RACINE / "workflow" / "text_chat_runner.py"

# Les branchements du téléphone qui n'ont pas lieu d'être au clavier, chacun avec sa raison. Un équivalent au clavier
# sous un autre nom compte aussi : il est nommé dans la raison.
EXCEPTIONS = {
    "armer_filet_lexique": "audio : la liste de mots envoyée à la transcription ; au clavier rien n'est transcrit",
    "brancher_les_coupures": "audio : une phrase du code coupée pendant que le son joue ; au clavier rien ne joue",
    "brancher_les_connexions": "audio : les connexions des services de transcription et de voix",
    "poser_les_balises_du_cerveau": "audio : les balises que la voix Soniox prononce ; au clavier il n'y a pas de voix",
    "creer_lecture_appelant": "équivalent au clavier : lire_message_tape (même lecture, avant le modèle)",
    "creer_reconnaissance_lexique": "équivalent au clavier : annoter_message_tape (même reconnaissance, avant le modèle)",
}

_BRANCHEMENT = re.compile(r"\b((?:brancher|creer|armer|poser)_[a-z_]+)\(")


def _branchements(fichier: Path) -> set[str]:
    texte = fichier.read_text(encoding="utf-8")
    sans_definitions = re.sub(r"\bdef\s+\w+\(", "", texte)
    return set(_BRANCHEMENT.findall(sans_definitions))


def test_inventaire_tout_branchement_du_telephone_existe_au_clavier():
    manquants = _branchements(TELEPHONE) - _branchements(CLAVIER) - set(EXCEPTIONS)
    assert not manquants, (
        f"branchés au téléphone, absents du clavier : {sorted(manquants)}. Brancher au clavier, ou écrire l'exception "
        "avec sa raison dans EXCEPTIONS."
    )


def test_exceptions_seulement_des_branchements_reels_et_absents_du_clavier():
    telephone, clavier = _branchements(TELEPHONE), _branchements(CLAVIER)
    perimees = {nom for nom in EXCEPTIONS if nom not in telephone or nom in clavier}
    assert not perimees, f"exceptions à retirer (plus au téléphone, ou déjà au clavier) : {sorted(perimees)}"
    assert all(raison.strip() for raison in EXCEPTIONS.values())


REDITE = "Je cherche les disponibilités pour vous."


@pytest.mark.asyncio
async def test_garde_fou_au_clavier_la_replique_redite_pose_les_temps(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE)
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), *(_dit(_texte(REDITE)) for _ in range(4))],
        ["bonjour", "alors ?", "toujours rien ?", "vous êtes là ?"],
    )
    etat = reponses[-1]["checkpoint"]["gathered_context"].get(CLE_IMPASSE) or {}
    assert etat.get("temps", 0) >= 2, etat
    assert any(e.get("signe") == "replique_redite" for e in etat.get("journal") or []), etat


@pytest.mark.asyncio
async def test_civilite_au_clavier_ni_montree_ni_gardee_en_memoire(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(
        db_session, async_session, {**FICHE, "interdire_civilite_appelant": True}
    )
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), _dit(_texte("Bonjour madame, je vous écoute."))],
        ["bonjour"],
    )
    charge = reponses[-1]
    memoire = [
        str(m.get("content") or "")
        for m in charge["checkpoint"]["messages"]
        if m.get("role") == "assistant"
    ]
    assert any("je vous écoute" in m for m in memoire), memoire
    assert not any("madame" in m.lower() for m in memoire), memoire
    assert "madame" not in str(charge.get("turns") or charge.get("session") or "").lower()


@pytest.mark.asyncio
async def test_journal_du_clavier_une_entree_devient_un_evenement():
    class Capture:
        def __init__(self):
            self.events = []

        def _append_event(self, nature, charge):
            self.events.append((nature, charge))

    capture = Capture()
    await _JournalDuClavier(capture).append({"type": "mark-model-request", "payload": {"status": 429, "attempt": 1}})
    assert capture.events == [("mark-model-request", {"status": 429, "attempt": 1})]


def test_journal_branche_deux_fois_sur_le_meme_client_ne_s_empile_pas():
    """Revue du 27/10 : passation A → B → A dans un tour du clavier, le même service est rebranché ; le journal est
    remplacé, les crochets ne s'empilent pas (un refus serait noté deux fois)."""
    from types import SimpleNamespace

    from api.services.analyse_run.requetes_modele import brancher_le_journal_des_requetes

    http = SimpleNamespace(event_hooks={"request": [], "response": []})
    llm = SimpleNamespace(_client=SimpleNamespace(_client=http))
    premier, second = object(), object()
    assert brancher_le_journal_des_requetes(llm, premier) is True
    assert brancher_le_journal_des_requetes(llm, second) is True
    assert len(http.event_hooks["response"]) == 1 and len(http.event_hooks["request"]) == 1
    assert http._mark_journal_des_requetes["journal"] is second


# passages-fiables (lot E) : un effet qui n'a pas d'équivalent au clavier, avec sa raison. L'outil « laisser la parole » est
# branché dans le moteur (`set_node`), donc offert au clavier comme au téléphone ; seule la relance de silence manque.
ECARTS_DE_COMPORTEMENT = {
    "laisser_la_parole (relance douce)": "audio : le clavier n'a pas de silence à surveiller (aucun agrégateur de parole n'est lié au moniteur), l'attente n'a donc rien à retenir",
    "alertes (mail regroupé de l'appel)": "pas de fin d'appel au clavier : une session d'essai n'a pas de fin du pipeline qui envoie le mail ; les alertes elles-mêmes sont écrites dans le run au clavier comme au téléphone (même moteur) et lues par la page « Alertes »",
}


def test_e_au_clavier_le_moniteur_ne_relance_jamais_donc_l_attente_n_a_pas_d_effet():
    from api.services.pipecat.call_monitor_processor import CallMonitorProcessor

    assert all(raison.strip() for raison in ECARTS_DE_COMPORTEMENT.values())
    moniteur = CallMonitorProcessor(
        response_source=lambda: None, on_response_timeout=lambda _s: None, on_user_idle=None,
        conversation_enabled=lambda: True,
    )
    moniteur.activate()  # comme `text_chat_runner.py` : activé, mais sans `bind_user`
    moniteur.accorder_l_attente()
    assert moniteur.user_aggregator is None and moniteur._idle_eligible() is False and moniteur._deadline is None
