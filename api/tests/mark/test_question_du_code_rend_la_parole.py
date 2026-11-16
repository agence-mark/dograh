"""[.mark] SA-40 (M92, appel 2578, « Tester au clavier », Gemma 4) : une question dite par le code rend la parole à la personne.

La cause, prouvée sur le contexte de l'appel 2578 (``checkpoint.messages``) :

- message 25 : ``finaliser`` rend son résultat en « dit par le code » ; message 26 : le code dit « Je note le zéro six, vingt, trente,
  quarante, cinquante. Vous réglez comment ? » ; le résultat part au modèle SANS ``run_llm`` (``enveloppe_des_actions``, ``rendre``),
  donc Pipecat relance le modèle (``llm_response_universal``, ``run_llm = True`` faute de propriété) ; message 27 : le modèle rappelle
  ``finaliser`` ; message 29 : il ajoute « Comment souhaitez-vous régler ? » ;
- messages 32 à 36 : même chaîne après la relecture qui finit par « C'est bon ? » : « C'est bien cela ? ».

Le mécanisme, sans un mot de métier : quand le texte que le code vient de dire pour ce résultat se termine par une question, le résultat
part au modèle avec ``run_llm=False`` : aucune génération n'est demandée, la parole revient à la personne. Le même chemin sert le
clavier et le téléphone (l'enveloppe de toute action).

| Test | Ce qu'il prouve |
|---|---|
| numéro (×1), relecture (×1) | après une question du code, le modèle n'est pas relancé ; les autres propriétés sont gardées |
| texte sans question | le modèle est relancé comme avant |
| outil sans « dit par le code » | les propriétés passent telles quelles |
| voix en échec | le texte reste au modèle, qui est relancé pour le dire |
| texte déjà dit dans le tour | rien n'est redit : la propriété passe telle quelle |
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from api.services.outils_mark.pour_la_voix import avec_restitution, finit_par_une_question
from api.services.workflow.enveloppe_des_actions import envelopper_l_action
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR
from pipecat.frames.frames import FunctionCallResultProperties

NUMERO = "Je note le zéro six, vingt, trente, quarante, cinquante. Vous réglez comment ?"
RELECTURE = (
    "Je vous relis : deux Regina Normale, à emporter, pour mercredi dix-huit novembre à vingt heures trente. Cela fait vingt-cinq "
    "euros quatre-vingts. Vous réglez vingt-cinq euros quatre-vingts par carte. C'est bon ?"
)
ENREGISTREE = "Votre commande est enregistrée pour mercredi dix-huit novembre à vingt heures trente."


class _Lecture:
    def __init__(self, issue: str = "PENDING") -> None:
        self.outcome = SimpleNamespace(name=issue)


class _Moteur:
    def __init__(self, issue: str = "PENDING") -> None:
        self.dites: list[str] = []
        self._issue = issue
        self._gathered_context: dict[str, Any] = {CLE_TOUR: 3}
        self.phrases = SimpleNamespace(coupures=SimpleNamespace(noter=lambda *a, **k: None))

    async def queue_speech(self, text=None, **_options):
        self.dites.append(text)
        return _Lecture(self._issue)


async def _rendu(moteur: _Moteur, resultat: dict, properties: Any = None) -> tuple[Any, Any]:
    """Le résultat et les propriétés que l'enveloppe rend à Pipecat pour ``resultat``."""
    rendus: list[tuple[Any, Any]] = []

    async def rendre(sortie, **kwargs):
        rendus.append((sortie, kwargs.get("properties")))

    async def action(params):
        await params.result_callback(resultat, properties=properties)

    await envelopper_l_action(moteur, "finaliser", action)(SimpleNamespace(result_callback=rendre, arguments={}))
    assert len(rendus) == 1
    return rendus[0]


def _dit_par_le_code(texte: str, **plus: Any) -> dict:
    return avec_restitution({"statut": "INCOMPLETE", "suggestion": texte, **plus}, {"restitution": "dit_par_le_code"})


async def test_appel_2578_apres_la_question_du_numero_le_modele_n_est_pas_relance():
    moteur = _Moteur()
    sortie, proprietes = await _rendu(moteur, _dit_par_le_code(NUMERO, manque="paiement"))
    assert moteur.dites == [NUMERO]
    assert sortie["deja_dit_par_le_code"] is True and "suggestion" not in sortie
    assert proprietes is not None and proprietes.run_llm is False


async def test_appel_2578_apres_le_c_est_bon_de_la_relecture_le_modele_n_est_pas_relance():
    moteur = _Moteur()

    async def apres() -> None:
        return None

    sortie, proprietes = await _rendu(
        moteur, _dit_par_le_code(RELECTURE, manque="relecture"), FunctionCallResultProperties(on_context_updated=apres)
    )
    assert moteur.dites == [RELECTURE]
    assert proprietes.run_llm is False
    assert proprietes.on_context_updated is apres  # le reste des propriétés est gardé


async def test_un_texte_du_code_sans_question_finale_laisse_le_modele_parler():
    moteur = _Moteur()
    _sortie, proprietes = await _rendu(moteur, _dit_par_le_code(ENREGISTREE))
    assert moteur.dites == [ENREGISTREE]
    assert proprietes is None  # Pipecat relance le modèle, comme avant


async def test_un_outil_sans_dit_par_le_code_passe_tel_quel():
    moteur = _Moteur()
    resultat = {"statut": "INCOMPLETE", "suggestion": "Vous réglez comment ?", "manque": "paiement"}
    for proprietes in (None, FunctionCallResultProperties(run_llm=True)):
        sortie, rendues = await _rendu(moteur, resultat, proprietes)
        assert sortie == resultat and rendues is proprietes
    assert moteur.dites == []


async def test_une_voix_en_echec_laisse_le_texte_au_modele_qui_est_relance():
    moteur = _Moteur(issue="FAILED")
    sortie, proprietes = await _rendu(moteur, _dit_par_le_code(NUMERO))
    assert sortie["restitution"] == "mot_pour_mot" and sortie["texte_a_dire"] == NUMERO
    assert proprietes is None


async def test_un_texte_deja_dit_dans_le_tour_n_est_pas_redit_et_ne_change_pas_la_relance():
    moteur = _Moteur()
    await _rendu(moteur, _dit_par_le_code(NUMERO))
    _sortie, proprietes = await _rendu(moteur, _dit_par_le_code(NUMERO))
    assert moteur.dites == [NUMERO]
    assert proprietes is None


def test_la_question_finale_se_lit_sur_le_dernier_signe():
    assert finit_par_une_question("Vous réglez comment ?")
    assert finit_par_une_question("C'est bon ? »  ")
    assert not finit_par_une_question("Une question ? Puis un fait.")
    assert not finit_par_une_question("")
    assert not finit_par_une_question(None)
