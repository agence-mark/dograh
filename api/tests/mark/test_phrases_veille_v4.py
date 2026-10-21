"""[.mark] Chantier correctifs-apres-banc-v4, lot 4 (4.3 à 4.5, 4.10) : la veille générique, les incidents et les
sorties du diseur, sur un faux moteur qui parle vraiment (``queue_speech``), garde sa fiche et raccroche.

| Test | La garantie |
|---|---|
| dans l'ordre | trois phrases « dans l'ordre » : la 1re, puis la 2e, puis la 3e, jamais une 4e ; arrêt net au plafond par attente |
| tournées | « tournées » : jamais deux fois la même d'affilée tant qu'une autre reste |
| arrêt net | le résultat arrive : plus aucune redite, la sortie ne part pas |
| intervalle | la redite se compte depuis la FIN de la phrase précédente |
| dès le lancement | délai 0 : la phrase part tout de suite ; l'annonce de l'agent passe en première, les redites restent les phrases fixes |
| plafond par appel | « au plus M fois dans l'appel » vaut pour toutes les attentes de l'appel, pas pour une seule |
| sortie d'attente | après la dernière redite, attente toujours là : phrase de sortie, note dans la fiche (par le point d'écriture unique), raccrocher |
| sans sortie posée | une règle qui ne pose pas de sortie ne fait rien de plus (comportement d'avant) |
| incident | l'échec : la phrase tant que le compteur est sous le plafond, la sortie à l'incident M (noter, transférer, raccrocher) |
| ordre d'incident | « dans l'ordre » compte les incidents : la n-ième phrase au n-ième échec |
| règle éteinte ou défaut | éteinte : rien ; ``seulement_si_posee`` : le défaut du catalogue ne parle pas |
| transfert refusé | la destination hors de la liste ne part pas : le modèle reprend, l'interdit est dit |
| compte rendu | le compte rendu standard en français, chaque ligne seulement si elle a un contenu |
| pause commune | la pause minimale entre deux phrases d'attente se règle sur le principal |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.schemas.phrases_du_code import NoteDeSortie, Sortie
from api.services.phrases.catalogue import (
    APPELANT_SE_TAIT,
    MOTIFS,
    OUTIL_ECHOUE,
    OUTIL_TARDE,
    TRAVAIL_DURE,
    TRAVAIL_ECHOUE,
)
from api.services.phrases.compte_rendu import compte_rendu
from api.services.phrases.diseur import CLE_TRACE, DiseurDePhrases
from api.services.phrases.regles import PhraseResolue
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.tests.mark.test_attente_parlee import _FauxMoteur

PAS = 0.002


class _Moteur(_FauxMoteur):
    """Un moteur qui dit ses phrases (avec leur texte), garde une fiche et raccroche."""

    def __init__(self):
        super().__init__(lambda: 0.0)
        self.sans_sortie_audio = False
        self.end_call_with_reason = AsyncMock()
        self.drain_call_pipeline = AsyncMock()
        self._fiche = ReglagesFiche(
            champs=(
                ChampFiche(
                    nom="rendez_vous",
                    origine="deduit",
                    valeurs=["confirme", "a_rappeler"],
                    rempli_par_outil="poser_rendez_vous",
                ),
            )
        )
        self.longueur_de_phrase = 0.0

    async def queue_speech(self, texte, **_):
        self.dites.append(texte)
        fin = asyncio.Event()
        if self.longueur_de_phrase <= 0:
            fin.set()
        else:
            asyncio.get_running_loop().call_later(self.longueur_de_phrase, fin.set)
        return SimpleNamespace(wait=fin.wait, text=texte)


def _diseur(moteur=None):
    moteur = moteur or _Moteur()
    diseur = DiseurDePhrases(moteur)
    diseur.repos_s = lambda: 0.0  # le repos a son propre test
    moteur.phrases = diseur
    return moteur, diseur


def _phrase(motif=TRAVAIL_DURE, variantes=("P1", "P2", "P3"), **champs):
    base = dict(
        motif=MOTIFS[motif],
        variantes=tuple(variantes),
        delai_s=0.0,
        active=True,
        niveau="agent",
        redite_s=0.02,
        max_par_attente=3,
        max_pose=True,
        cle=("agent", motif),
    )
    base.update(champs)
    return PhraseResolue(**base)


@pytest.mark.asyncio
async def test_trois_phrases_dans_l_ordre_puis_rien_au_plafond_par_attente():
    moteur, diseur = _diseur()
    phrase = _phrase(ordre="dans_l_ordre", max_par_attente=3)
    resultat = await diseur.veiller(TRAVAIL_DURE, lambda: True, phrase=phrase, pas_s=PAS)
    assert moteur.dites == ["P1", "P2", "P3"]
    assert resultat.dites == 3 and resultat.sortie is None
    # La trace dit la fois dans l'attente (0 = la première phrase, 1 et 2 = ses redites).
    trace = moteur._gathered_context[CLE_TRACE]
    assert [t["texte"] for t in trace] == ["P1", "P2", "P3"]
    assert [t.get("redite") for t in trace] == [None, 1, 2]


@pytest.mark.asyncio
async def test_en_tournees_jamais_deux_fois_la_meme_d_affilee():
    moteur, diseur = _diseur()
    phrase = _phrase(variantes=("A", "B"), ordre="tournees", max_par_attente=5)
    await diseur.veiller(TRAVAIL_DURE, lambda: True, phrase=phrase, pas_s=PAS)
    assert len(moteur.dites) == 5
    assert all(a != b for a, b in zip(moteur.dites, moteur.dites[1:]))


@pytest.mark.asyncio
async def test_le_resultat_arrive_plus_aucune_redite():
    moteur, diseur = _diseur()
    encore = {"oui": True}
    phrase = _phrase(
        ordre="dans_l_ordre",
        redite_s=0.05,
        ensuite=Sortie(phrases=["Au revoir."], action="raccrocher"),
    )

    def au_depart():
        # Le résultat arrive pendant l'intervalle qui suit la première phrase.
        asyncio.get_running_loop().call_later(0.01, encore.update, {"oui": False})

    await diseur.veiller(
        TRAVAIL_DURE, lambda: encore["oui"], phrase=phrase, pas_s=PAS, au_depart=au_depart
    )
    assert moteur.dites == ["P1"]
    moteur.end_call_with_reason.assert_not_awaited()


@pytest.mark.asyncio
async def test_la_redite_se_compte_depuis_la_fin_de_la_phrase_precedente():
    moteur, diseur = _diseur()
    moteur.longueur_de_phrase = 0.06
    instants = []
    d = moteur.queue_speech

    async def horodatee(texte, **kw):
        instants.append(asyncio.get_running_loop().time())
        return await d(texte, **kw)

    moteur.queue_speech = horodatee
    phrase = _phrase(ordre="dans_l_ordre", redite_s=0.05, max_par_attente=2)
    await diseur.veiller(TRAVAIL_DURE, lambda: True, phrase=phrase, pas_s=PAS)
    assert len(instants) == 2
    # 0,06 s de phrase PUIS 0,05 s d'intervalle : au moins 0,11 s entre les deux départs.
    assert instants[1] - instants[0] >= 0.105


@pytest.mark.asyncio
async def test_des_le_lancement_et_l_annonce_de_l_agent_passe_en_premiere():
    moteur, diseur = _diseur()
    phrase = _phrase(variantes=("Fixe 1", "Fixe 2"), ordre="dans_l_ordre", texte_de_l_agent=True)
    await diseur.veiller(
        TRAVAIL_DURE,
        lambda: True,
        phrase=phrase,
        premiere="Je regarde les dates.",
        pas_s=PAS,
    )
    # L'annonce d'abord (dès le lancement, délai 0), puis les redites : phrases fixes, la 2e de la règle.
    assert moteur.dites[0] == "Je regarde les dates."
    assert moteur.dites[1:] == ["Fixe 2", "Fixe 2"]


@pytest.mark.asyncio
async def test_le_plafond_dans_l_appel_vaut_pour_toutes_les_attentes():
    moteur, diseur = _diseur()
    phrase = _phrase(max_par_attente=1, redite_s=None, max_par_appel=2)
    for _ in range(4):
        await diseur.veiller(TRAVAIL_DURE, lambda: True, phrase=phrase, pas_s=PAS)
    # Quatre attentes, deux phrases au plus dans l'appel (tournées : la 1re puis la 2e).
    assert moteur.dites == ["P1", "P2"]


@pytest.mark.asyncio
async def test_sortie_d_attente_dit_note_dans_la_fiche_puis_raccroche():
    moteur, diseur = _diseur()
    phrase = _phrase(
        variantes=("Un instant.",),
        max_par_attente=2,
        ensuite=Sortie(
            phrases=["Je vous laisse, au revoir."],
            noter=NoteDeSortie(champ="rendez_vous", valeur="a_rappeler"),
            action="raccrocher",
        ),
    )
    resultat = await diseur.veiller(TRAVAIL_DURE, lambda: True, phrase=phrase, pas_s=PAS)
    assert moteur.dites == ["Un instant.", "Un instant.", "Je vous laisse, au revoir."]
    # La note passe par le point d'écriture unique de la fiche, même pour un champ rempli par un outil.
    assert moteur._gathered_context["rendez_vous"] == "a_rappeler"
    moteur.end_call_with_reason.assert_awaited_once()
    assert resultat.sortie.prise_en_main is True and resultat.sortie.notes == ["rendez_vous = a_rappeler"]
    assert moteur._gathered_context[CLE_TRACE][-1].get("sortie") is True


@pytest.mark.asyncio
async def test_une_regle_sans_sortie_posee_ne_fait_rien_de_plus():
    moteur, diseur = _diseur()
    phrase = _phrase(variantes=("Un instant.",), max_par_attente=2)
    resultat = await diseur.veiller(TRAVAIL_DURE, lambda: True, phrase=phrase, pas_s=PAS)
    assert moteur.dites == ["Un instant.", "Un instant."] and resultat.sortie is None
    moteur.end_call_with_reason.assert_not_awaited()


@pytest.mark.asyncio
async def test_un_incident_la_phrase_puis_la_sortie_au_plafond():
    moteur, diseur = _diseur()
    reglages = {
        "phrases_regles": [
            {
                "motif": OUTIL_ECHOUE,
                "variantes": ["Je n'arrive pas à finaliser."],
                "max_par_appel": 2,
                "ensuite": {
                    "phrases": ["Un conseiller vous rappelle."],
                    "noter": {"champ": "rendez_vous", "valeur": "a_rappeler"},
                    "action": "raccrocher",
                },
            }
        ]
    }
    moteur.active_agent.reglages = reglages
    premier = await diseur.signaler_un_probleme(OUTIL_ECHOUE, outil="poser_rendez_vous")
    assert premier.incident == 1 and premier.dit == "Je n'arrive pas à finaliser."
    assert premier.issue is None and premier.le_modele_reprend is True
    assert "rendez_vous" not in moteur._gathered_context
    second = await diseur.signaler_un_probleme(OUTIL_ECHOUE, outil="poser_rendez_vous")
    assert second.incident == 2 and second.dit == "Je n'arrive pas à finaliser."
    assert second.issue is not None and second.issue.prise_en_main is True
    assert second.le_modele_reprend is False
    assert second.notes == ["rendez_vous = a_rappeler"]
    assert moteur.dites == [
        "Je n'arrive pas à finaliser.",
        "Je n'arrive pas à finaliser.",
        "Un conseiller vous rappelle.",
    ]
    assert moteur._gathered_context["rendez_vous"] == "a_rappeler"
    moteur.end_call_with_reason.assert_awaited_once()


@pytest.mark.asyncio
async def test_sans_plafond_la_sortie_part_au_premier_incident():
    moteur, diseur = _diseur()
    moteur.active_agent.reglages = {
        "phrases_regles": [
            {
                "motif": TRAVAIL_ECHOUE,
                "variantes": ["Je n'y arrive pas."],
                "ensuite": {"noter": {"champ": "rendez_vous", "valeur": "a_rappeler"}},
            }
        ]
    }
    probleme = await diseur.signaler_un_probleme(TRAVAIL_ECHOUE)
    assert probleme.dit == "Je n'y arrive pas." and probleme.notes == ["rendez_vous = a_rappeler"]
    # Sortie « noter » seule : l'action reste celle du motif, le modèle reprend.
    assert probleme.le_modele_reprend is True
    moteur.end_call_with_reason.assert_not_awaited()


@pytest.mark.asyncio
async def test_dans_l_ordre_compte_les_incidents():
    moteur, diseur = _diseur()
    moteur.active_agent.reglages = {
        "phrases_regles": [
            {
                "motif": OUTIL_ECHOUE,
                "variantes": ["Premier échec.", "Deuxième échec.", "Troisième échec."],
                "ordre": "dans_l_ordre",
            }
        ]
    }
    for _ in range(3):
        await diseur.signaler_un_probleme(OUTIL_ECHOUE)
    assert moteur.dites == ["Premier échec.", "Deuxième échec.", "Troisième échec."]


@pytest.mark.asyncio
async def test_eteinte_ou_defaut_un_echec_de_http_ne_parle_pas():
    moteur, diseur = _diseur()
    # Le défaut du catalogue (allumé pour un connecteur, comme avant) ne parle pas pour un autre outil.
    rien = await diseur.signaler_un_probleme(OUTIL_ECHOUE, outil="x", seulement_si_posee=True)
    assert rien.dit is None and moteur.dites == []
    # Pour un connecteur (sans cette réserve), le défaut parle comme avant.
    connecteur = await diseur.signaler_un_probleme(OUTIL_ECHOUE, outil="x")
    assert connecteur.dit == MOTIFS[OUTIL_ECHOUE].variantes_defaut[0]
    moteur.active_agent.reglages = {
        "phrases_regles": [{"motif": OUTIL_ECHOUE, "variantes": [], "active": False}]
    }
    eteinte = await diseur.signaler_un_probleme(OUTIL_ECHOUE, outil="x")
    assert eteinte.dit is None and eteinte.phrase is None


@pytest.mark.asyncio
async def test_un_transfert_vers_une_destination_hors_de_l_equipe_ne_part_pas():
    moteur, diseur = _diseur()
    moteur.active_agent.reglages = {
        "phrases_regles": [
            {
                "motif": OUTIL_ECHOUE,
                "variantes": ["Souci."],
                "ensuite": {"action": "transferer", "destination": "inconnue"},
            }
        ]
    }
    moteur._call_context_vars = {}
    moteur._custom_tool_manager = SimpleNamespace(get_organization_id=AsyncMock(return_value=1))
    probleme = await diseur.signaler_un_probleme(OUTIL_ECHOUE)
    assert probleme.issue.prise_en_main is False
    assert probleme.le_modele_reprend is True
    assert "transférer" in probleme.issue.interdit and probleme.issue.erreurs
    moteur.end_call_with_reason.assert_not_awaited()


def test_le_compte_rendu_standard_en_francais():
    plein = compte_rendu(
        "le transfert n'a pas abouti",
        detail="pas de réponse",
        dit="Je n'ai pas pu vous mettre en relation.",
        notes=["rendez_vous = a_rappeler"],
        interdits=["transférer"],
    )
    assert plein == (
        "[Ce qui vient de se passer : le transfert n'a pas abouti, pas de réponse.\n"
        "L'appelant a entendu : « Je n'ai pas pu vous mettre en relation. ». Ne la répète pas.\n"
        "Noté dans la fiche : rendez_vous = a_rappeler.\n"
        "Plus possible dans cet appel : transférer.]"
    )
    # Chaque ligne n'apparaît que si elle a un contenu.
    assert compte_rendu("l'outil n'a pas abouti") == "[Ce qui vient de se passer : l'outil n'a pas abouti.]"
    assert compte_rendu("") == ""
    assert "do not repeat" not in plein.lower()


@pytest.mark.asyncio
async def test_la_pause_minimale_se_regle_sur_le_principal():
    moteur = _Moteur()
    diseur = DiseurDePhrases(moteur)
    assert diseur.repos_s() == 3.0  # la valeur d'avant
    moteur.reglages_appel = {"phrases_repos_s": 7}
    assert diseur.repos_s() == 7.0
    moteur.reglages_appel = {"phrases_repos_s": 99}
    assert diseur.repos_s() == 10.0
    moteur.reglages_appel = {"phrases_repos_s": 0.1}
    assert diseur.repos_s() == 1.0


@pytest.mark.asyncio
async def test_le_silence_garde_son_motif_et_ses_cases():
    # Le silence est tenu par le moniteur de l'appel (nombre de relances) : son motif porte la redite.
    assert MOTIFS[APPELANT_SE_TAIT].peut_redire
    moteur, diseur = _diseur()
    phrase = diseur.phrase(APPELANT_SE_TAIT)
    assert phrase.action_de_sortie == "raccrocher" and phrase.sortie_posee is False
    assert phrase.max_pose is False and phrase.max_par_attente == 1


@pytest.mark.asyncio
async def test_une_redite_retenue_par_la_pause_attend_au_lieu_de_finir_l_attente():
    moteur = _Moteur()
    diseur = DiseurDePhrases(moteur)
    moteur.phrases = diseur
    diseur.repos_s = lambda: 0.15
    phrase = _phrase(ordre="dans_l_ordre", redite_s=0.02, max_par_attente=2)
    resultat = await diseur.veiller(TRAVAIL_DURE, lambda: True, phrase=phrase, pas_s=PAS)
    # La redite (0,02 s) est plus courte que la pause (0,15 s) : elle part quand même, plus tard.
    assert moteur.dites == ["P1", "P2"] and resultat.dites == 2


@pytest.mark.asyncio
async def test_un_outil_vise_par_son_nom_dans_la_veille():
    moteur, diseur = _diseur()
    moteur.active_agent.reglages = {
        "phrases_regles": [
            {"motif": OUTIL_TARDE, "variantes": ["Pour tous."], "delai_s": 0},
            {"motif": OUTIL_TARDE, "outils": ["chercher_dates"], "variantes": ["Je regarde les dates."], "delai_s": 0},
        ]
    }
    await diseur.veiller(OUTIL_TARDE, lambda: True, outil="chercher_dates", pas_s=PAS)
    await diseur.veiller(OUTIL_TARDE, lambda: True, outil="reserver", pas_s=PAS)
    assert moteur.dites == ["Je regarde les dates.", "Pour tous."]
