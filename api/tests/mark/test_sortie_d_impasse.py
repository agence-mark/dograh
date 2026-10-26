"""[.mark] fiabilite-de-la-conversation, lot A : le garde-fou de sortie d'impasse (point 14).

Le code compte quatre signes d'impasse, avertit deux fois le modèle, puis dit la phrase du catalogue et change l'étape.
Chaque test passe par le vrai diseur de phrases et la vraie sortie (``executer``) ; le moteur est un banc léger qui note la
main rendue ; les tests ``moteur_*`` jouent la vraie méthode du moteur de l'appel (``sortir_de_l_impasse``).

| Test | La garantie |
|---|---|
| signe 1 | une réplique redite à l'une des deux précédentes compte ; une phrase du code, une phrase entre guillemets de l'étape, une réplique de moins de trois mots, une phrase d'attente : non |
| signe 2 | une demande au fond identique (règle B1 du lot B) compte, même si le travail est en cours (D-3) ; une autre demande, non ; par la vraie route d'un appel, même quand B2 la refuse |
| signe 3 | trois tours sans champ nouveau dans une étape qui attend des champs : un signe, une fois ; un champ noté ou lu au tour même remet à zéro ; une étape sans champs attendus : jamais (D11) |
| signe 4 | la troisième entrée dans une même étape compte (D15) ; la rejouer au clavier ne compte pas ; un seul changement d'avis ne déclenche rien |
| attente | trois tours d'attente du fond (« j'attends ») ne comptent pas (D2), ni le tour qui suit un appel d'outil |
| riposte | 2e signe : notice 1 ; 3e : notice 2 ; 4e : la phrase du motif « impasse » dite, puis la main rendue, fiche intacte ; la notice n'est montrée qu'au tour qui la suit |
| impasse répétée | la deuxième impasse de l'appel dit « impasse répétée » puis passe à l'étape choisie ; sans étape choisie, comme « impasse » |
| temps 3 et travail en cours | le temps 3 attend la fin du travail de fond (compté sans attendre, dit après le résultat) |
| motif éteint | rien n'est dit, la main n'est pas rendue, le modèle garde l'appel (ses deux notices restent) |
| moteur | un collègue rend la main à l'accueil (étape choisie comprise) ; l'accueil passe de force à son étape de retour ; sans étape de retour : le modèle garde la main |
| schéma | « aller à une étape » garde l'étape choisie, « rendre la main » non ; les deux suites ne sont permises qu'aux deux motifs |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.schemas.phrases_du_code import ReglePhrase
from api.services.phrases.catalogue import IMPASSE, IMPASSE_REPETEE, MOTIFS
from api.services.phrases.diseur import CLE_TRACE, DiseurDePhrases
from api.services.workflow import sortie_d_impasse as impasse
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR
from api.services.workflow.sortie_d_impasse import (
    CLE_IMPASSE,
    NOTICE_TEMPS_1,
    NOTICE_TEMPS_2,
    compter_la_demande,
    entrer_dans_l_etape,
    fin_de_la_replique,
    notice_a_montrer,
)
from api.tests.mark.test_attente_parlee import _FauxMoteur
from api.tests.mark.test_declenchement_de_l_action import _reglages
from api.tests.mark.test_travail_de_fond import _texte, appel  # noqa: F401 -- fixture

REPLIQUE = "Pouvez-vous me redonner votre adresse complète, s'il vous plaît ?"
AUTRE = "Très bien, et à quel numéro peut-on vous joindre aujourd'hui ?"
RECHERCHE = "Cherche deux dates de passage pour un entretien, sur deux jours différents."


def _noeud(identifiant="n1", prompt="Tu aides la personne.", champs=()):
    return SimpleNamespace(
        id=identifiant, name=f"Étape {identifiant}", prompt=prompt, champs_etape=tuple(champs),
        conditions_de_champs=(), is_end=False,
    )


class Banc(_FauxMoteur):
    """Un moteur léger : le vrai diseur, la vraie sortie ; la main rendue est notée, pas jouée."""

    def __init__(self, noeud=None, reglages_agent=None, fiche=None):
        super().__init__(lambda: 0.0)
        self.noeud = noeud or _noeud()
        self._fiche = fiche
        self._gathered_context = {CLE_TOUR: 0}
        self.active_agent = SimpleNamespace(
            reglages=reglages_agent or {}, current_node=self.noeud, workflow_id=1, visit_id="v1"
        )
        self.phrases = DiseurDePhrases(self, horloge=lambda: 0.0)
        self.transfer_coordinator = SimpleNamespace(in_progress=False)
        self.travaux: list = []
        self.mains: list = []
        self.sortir_ok = True

    def etat_pour_le_filet(self):
        return ("v1", self.active_agent.current_node.id)

    async def sortir_de_l_impasse(self, agent, *, etape_cible=None):
        self.mains.append(etape_cible)
        return self.sortir_ok

    def un_tour(self):
        self._gathered_context[CLE_TOUR] += 1

    def dit(self):
        return [e["texte"] for e in self._gathered_context.get(CLE_TRACE, [])]

    def etat(self):
        return self._gathered_context[CLE_IMPASSE]


async def _repliques(banc, *textes):
    """Chaque réplique de l'agent suit une parole de l'appelant."""
    for texte in textes:
        banc.un_tour()
        await fin_de_la_replique(banc, texte, None)
        await asyncio.sleep(0)
    for _ in range(5):
        await asyncio.sleep(0)


def _entrer(banc):
    entrer_dans_l_etape(banc, banc.active_agent, banc.noeud)


def _signes(banc):
    return banc.etat()["signes"]


# --------------------------------------------------------------------------- #
# Signe 1 : la réplique redite
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_signe_1_une_replique_redite_a_l_une_des_deux_precedentes_compte():
    banc = Banc()
    _entrer(banc)
    await _repliques(banc, REPLIQUE, AUTRE)
    assert _signes(banc) == 0
    await _repliques(banc, REPLIQUE)  # identique à l'avant-dernière
    assert _signes(banc) == 1
    await _repliques(banc, "  " + REPLIQUE.upper().replace(",", ""))  # casse et ponctuation ne comptent pas
    assert _signes(banc) == 2


@pytest.mark.asyncio
async def test_signe_1_une_replique_a_trois_repliques_de_distance_ne_compte_pas():
    banc = Banc()
    _entrer(banc)
    await _repliques(banc, REPLIQUE, AUTRE, "Bien noté, je regarde cela avec vous maintenant.", REPLIQUE)
    assert _signes(banc) == 0


@pytest.mark.asyncio
async def test_signe_1_ni_une_phrase_du_code_ni_une_phrase_entre_guillemets_ni_une_attente_ni_une_replique_courte():
    banc = Banc(noeud=_noeud(prompt='Dis « Je vous remercie de votre patience, un instant » avant de chercher.'))
    _entrer(banc)
    banc._gathered_context[CLE_TRACE] = [
        {"motif": "reponse_perdue", "texte": "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"},
        {"motif": "travail_dure", "texte": "C'est presque bon, merci de patienter."},
    ]
    await _repliques(
        banc,
        "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?",
        "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?",
        "C'est presque bon, merci de patienter.",
        "C'est presque bon, merci de patienter.",
        "Je vous remercie de votre patience, un instant.",
        "Je vous remercie de votre patience, un instant.",
        "D'accord.",
        "D'accord.",
        "D'accord.",
    )
    assert _signes(banc) == 0


@pytest.mark.asyncio
async def test_signe_1_une_replique_ne_compte_qu_une_fois_par_tour_de_l_appelant():
    banc = Banc()
    _entrer(banc)
    await _repliques(banc, REPLIQUE)
    banc.un_tour()
    await fin_de_la_replique(banc, REPLIQUE, None)
    await fin_de_la_replique(banc, REPLIQUE, None)  # deux répliques dans le même tour
    assert _signes(banc) == 1


@pytest.mark.asyncio
async def test_signe_1_une_replique_finie_apres_un_changement_d_etape_ne_compte_pas():
    banc = Banc()
    _entrer(banc)
    await _repliques(banc, REPLIQUE)
    banc.un_tour()
    await fin_de_la_replique(banc, REPLIQUE, ("v1", "autre-etape"))
    assert _signes(banc) == 0


# --------------------------------------------------------------------------- #
# Signe 2 : la demande identique (règle B1)
# --------------------------------------------------------------------------- #


def _trace(demande, etape="n1", statut="fait"):
    return {"demande": demande, "etape": etape, "statut": statut, "resultat": "Résultat : x"}


def test_signe_2_une_demande_identique_dans_l_etape_compte_une_autre_non():
    banc = Banc()
    _entrer(banc)
    banc._gathered_context["travaux"] = [_trace(RECHERCHE)]
    compter_la_demande(banc, banc.active_agent, "Cherche autre chose pour un autre jour.")
    assert _signes(banc) == 0
    compter_la_demande(banc, banc.active_agent, "  cherche DEUX dates de passage pour un entretien,\nsur deux jours différents ")
    assert _signes(banc) == 1
    # l'étape compte : la même demande dans une autre étape est nouvelle
    banc._gathered_context["travaux"] = [_trace(RECHERCHE, etape="ailleurs")]
    compter_la_demande(banc, banc.active_agent, RECHERCHE)
    assert _signes(banc) == 1


def test_signe_2_compte_meme_pendant_une_attente_du_systeme():
    """D-3 : chaque demande ouvre une attente ; l'exclusion de D2 rendrait le signe aveugle à la boucle qu'il vise."""
    banc = Banc()
    _entrer(banc)
    banc.travaux = [SimpleNamespace(occupe=True)]
    banc._gathered_context["travaux"] = [_trace(RECHERCHE, statut="en_cours")]
    compter_la_demande(banc, banc.active_agent, RECHERCHE)
    assert _signes(banc) == 1


@pytest.mark.asyncio
async def test_signe_2_par_la_vraie_route_meme_quand_b2_refuse_la_redemande(appel):  # noqa: F811
    from pipecat.tests import MockLLMService

    from api.services.travail.reglages import NOM_OUTIL

    def confier(identifiant):
        return MockLLMService.create_function_call_chunks(
            function_name=NOM_OUTIL, arguments={"demande": RECHERCHE}, tool_call_id=identifiant
        )

    await appel.monter(
        source_etapes=[confier("c1"), confier("c2"), confier("c3"), _texte("Je regarde.")],
        fond_etapes=[_texte("Résultat : mardi ou jeudi.")],
        outils_du_fond=False,
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 4)
    etat = appel.engine._gathered_context[CLE_IMPASSE]
    # trois ffois la même demande : la 1re part, les 2 autres sont refusées par B2 ; chacune des 2 redemandes est un signe
    assert etat["signes"] == 2, etat
    assert [e["signe"] for e in etat["journal"] if "signe" in e] == ["demande_identique", "demande_identique"]
    assert etat["temps"] == 1 and etat["notice"] == NOTICE_TEMPS_1


# --------------------------------------------------------------------------- #
# Signe 3 : rien de nouveau dans une étape qui attend des champs
# --------------------------------------------------------------------------- #


def _banc_a_champs():
    banc = Banc(noeud=_noeud(champs=("nom", "adresse")), fiche=_reglages())
    banc._gathered_context.update({"contrat_entretien": "aucun"})
    return banc


@pytest.mark.asyncio
async def test_signe_3_trois_tours_sans_champ_nouveau_un_signe_une_fois():
    banc = _banc_a_champs()
    _entrer(banc)
    await _repliques(banc, "Quel est votre nom, s'il vous plaît ?", "Je n'ai pas compris, votre nom complet ?")
    assert _signes(banc) == 0
    await _repliques(banc, "Pardon encore une fois, quel est votre nom ?")  # 3e tour
    assert _signes(banc) == 1
    await _repliques(banc, "Dites-moi votre nom, je le note tout de suite.")  # le signe ne tombe qu'une fois
    assert _signes(banc) == 1


@pytest.mark.asyncio
async def test_signe_3_un_champ_note_remet_le_compteur_a_zero_et_six_questions_de_suite_ne_declenchent_rien():
    banc = Banc(noeud=_noeud(champs=("nom", "adresse", "mail")), fiche=_reglages())
    banc._gathered_context.update({"contrat_entretien": "souscrit"})
    _entrer(banc)
    await _repliques(banc, "Quel est votre nom, s'il vous plaît ?", "Merci, et votre adresse complète ?")
    banc._gathered_context["nom"] = "Durand"  # le champ est noté entre deux tours
    await _repliques(banc, "Merci Durand, et votre adresse complète ?")
    banc._gathered_context["adresse"] = "8 rue Pasteur"
    await _repliques(banc, "Parfait, et votre adresse mail pour la confirmation ?")
    assert _signes(banc) == 0
    # une valeur corrigée est aussi quelque chose de nouveau (l'appelant change d'avis)
    banc._gathered_context["adresse"] = "12 rue Pasteur"
    await _repliques(banc, "Bien noté, et votre adresse mail alors ?", "Je note le douze, et votre mail ?")
    assert _signes(banc) == 0


@pytest.mark.asyncio
async def test_signe_3_ne_compte_pas_dans_une_etape_sans_champ_attendu():
    banc = Banc(noeud=_noeud(champs=()), fiche=_reglages())
    _entrer(banc)
    await _repliques(banc, "Que puis-je faire pour vous ?", "Je vous écoute, dites-moi tout.", "Dites-moi ce dont vous avez besoin.", "Je suis là pour vous aider.")
    assert _signes(banc) == 0
    # et une étape dont tout est connu non plus
    banc = Banc(noeud=_noeud(champs=("nom",)), fiche=_reglages())
    banc._gathered_context["nom"] = "Durand"
    _entrer(banc)
    await _repliques(banc, "Que puis-je faire pour vous ?", "Je vous écoute, dites-moi tout.", "Dites-moi ce dont vous avez besoin.", "Je suis là pour vous aider.")
    assert _signes(banc) == 0


# --------------------------------------------------------------------------- #
# Signe 4 : une troisième entrée dans une même étape
# --------------------------------------------------------------------------- #


def _aller(banc, identifiant):
    banc.noeud = _noeud(identifiant)
    banc.active_agent.current_node = banc.noeud
    _entrer(banc)


def test_signe_4_la_troisieme_entree_dans_la_meme_etape_compte_pas_la_deuxieme():
    banc = Banc()
    _entrer(banc)
    for suivante in ("n2", "n1"):  # n1 : 2e entrée, l'appelant a changé d'avis une fois
        _aller(banc, suivante)
    assert _signes(banc) == 0
    _aller(banc, "n2")
    _aller(banc, "n1")  # 3e entrée dans n1
    assert _signes(banc) == 1
    assert banc.etat()["visites"]["1:n1"] == 3
    # le compteur de visites n'est jamais remis à zéro, ceux des signes 1 à 3 oui
    _aller(banc, "n3")
    assert banc.etat()["visites"]["1:n1"] == 3 and _signes(banc) == 0


def test_signe_4_rejouer_la_meme_entree_au_clavier_ne_compte_pas():
    banc = Banc()
    for _ in range(5):
        _entrer(banc)
    assert banc.etat()["visites"] == {"1:n1": 1} and _signes(banc) == 0


# --------------------------------------------------------------------------- #
# Aucun signe pendant une attente du système (D2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trois_tours_d_attente_du_fond_ne_declenchent_rien_ni_le_tour_qui_suit():
    banc = _banc_a_champs()
    _entrer(banc)
    banc.travaux = [SimpleNamespace(occupe=True)]
    await _repliques(banc, "Je cherche encore, merci de patienter un peu.", "Je cherche encore, merci de patienter un peu.",
                     "Je cherche encore, merci de patienter un peu.", "Je cherche encore, merci de patienter un peu.")
    assert _signes(banc) == 0
    banc.travaux = []  # le résultat vient d'arriver : le tour qui suit est encore une attente
    await _repliques(banc, "Voici ce que j'ai trouvé pour vous, mardi ou jeudi.")
    assert _signes(banc) == 0 and banc.etat()["tours_sans_champ"] == 0


# --------------------------------------------------------------------------- #
# La riposte graduée
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_les_trois_temps_dans_l_ordre_la_fiche_intacte_et_la_notice_au_tour_qui_suit():
    banc = Banc()
    banc._gathered_context.update({"nom": "Durand", "adresse": "8 rue Pasteur"})
    avant = {k: v for k, v in banc._gathered_context.items() if k in ("nom", "adresse")}
    _entrer(banc)
    await _repliques(banc, REPLIQUE)
    assert banc.etat()["temps"] == 0
    await _repliques(banc, REPLIQUE)  # 1 signe
    assert banc.etat()["temps"] == 0 and notice_a_montrer(banc) is None
    await _repliques(banc, REPLIQUE)  # 2e signe : temps 1
    assert banc.etat()["temps"] == 1 and notice_a_montrer(banc) == NOTICE_TEMPS_1
    banc.un_tour()
    assert notice_a_montrer(banc) == NOTICE_TEMPS_1  # le tour qui suit
    banc.un_tour()
    assert notice_a_montrer(banc) is None  # puis plus
    await _repliques(banc, REPLIQUE)  # 3e signe : temps 2
    assert banc.etat()["temps"] == 2 and notice_a_montrer(banc) == NOTICE_TEMPS_2
    assert banc.mains == [] and banc.dit() == []
    await _repliques(banc, REPLIQUE)  # 4e signe : temps 3
    assert banc.dit() == [MOTIFS[IMPASSE].variantes_defaut[0]]
    assert banc.mains == [None]  # la main revient à l'accueil, sans étape choisie
    assert {k: banc._gathered_context[k] for k in avant} == avant  # la fiche est intacte
    # après le temps 3, les compteurs des signes 1 à 3 repartent de zéro
    assert banc.etat()["signes"] == 0 and banc.etat()["temps"] == 0 and banc.etat()["impasses"] == 1
    assert notice_a_montrer(banc) is None


@pytest.mark.asyncio
async def test_la_deuxieme_impasse_dit_impasse_repetee_et_passe_a_l_etape_choisie():
    regle = {
        "motif": IMPASSE_REPETEE, "portee": "agent", "variantes": ["On vous rappelle."],
        "ensuite": {"action": "aller_a_une_etape", "destination": "etape-b"},
    }
    banc = Banc(reglages_agent={"phrases_regles": [regle]})
    _entrer(banc)
    for _ in range(2):  # deux impasses, chacune après 4 signes
        await _repliques(banc, *([REPLIQUE] * 5))
        _aller(banc, "n9")  # l'étape change : les compteurs repartent
        _aller(banc, "n1")
        banc._gathered_context[CLE_TRACE] = []
    assert banc.etat()["impasses"] == 2
    assert banc.mains == [None, "etape-b"]


@pytest.mark.asyncio
async def test_impasse_repetee_sans_etape_choisie_se_comporte_comme_impasse():
    banc = Banc()
    _entrer(banc)
    for _ in range(2):
        await _repliques(banc, *([REPLIQUE] * 5))
        _aller(banc, "n9")
        _aller(banc, "n1")
    assert banc.mains == [None, None]
    assert banc.dit()[-1] == MOTIFS[IMPASSE_REPETEE].variantes_defaut[0]


@pytest.mark.asyncio
async def test_un_motif_eteint_ne_dit_rien_ne_rend_pas_la_main_et_laisse_le_modele():
    regle = {"motif": IMPASSE, "portee": "agent", "variantes": [], "active": False}
    banc = Banc(reglages_agent={"phrases_regles": [regle]})
    _entrer(banc)
    await _repliques(banc, *([REPLIQUE] * 5))
    assert banc.dit() == [] and banc.mains == []
    assert banc.etat()["impasses"] == 0  # rien n'a été fait : la prochaine impasse est encore la première


@pytest.mark.asyncio
async def test_la_sortie_reglee_a_l_ecran_est_celle_qui_part():
    regle = {
        "motif": IMPASSE, "portee": "agent", "variantes": ["Reprenons."],
        "ensuite": {"phrases": ["Une seconde."], "action": "modele"},
    }
    banc = Banc(reglages_agent={"phrases_regles": [regle]})
    _entrer(banc)
    await _repliques(banc, *([REPLIQUE] * 5))
    assert banc.dit() == ["Reprenons.", "Une seconde."] and banc.mains == []


@pytest.mark.asyncio
async def test_un_changement_d_avis_de_l_appelant_ne_declenche_rien():
    banc = _banc_a_champs()
    _entrer(banc)
    await _repliques(banc, "Quel jour vous conviendrait le mieux, s'il vous plaît ?")
    banc._gathered_context["nom"] = "Durand"
    await _repliques(banc, "Très bien, mardi prochain à dix heures, c'est noté.")
    banc._gathered_context["nom"] = "Durand-Martin"  # il corrige
    await _repliques(banc, "D'accord, je corrige le nom, mardi prochain à dix heures.")
    _aller(banc, "n2")
    _aller(banc, "n1")  # il revient une fois en arrière
    assert _signes(banc) == 0 and banc.dit() == [] and banc.mains == []


@pytest.mark.asyncio
async def test_pas_de_sortie_pendant_une_passation_la_riposte_attend():
    banc = Banc()
    _entrer(banc)
    banc.transfer_coordinator.in_progress = True
    await _repliques(banc, *([REPLIQUE] * 5))
    assert banc.mains == [] and banc.etat()["a_declencher"] is True
    banc.transfer_coordinator.in_progress = False
    await _repliques(banc, AUTRE)
    assert banc.mains == [None]


# --------------------------------------------------------------------------- #
# La vraie méthode du moteur
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_moteur_un_collegue_rend_la_main_a_l_accueil_avec_l_etape_choisie(appel, monkeypatch):  # noqa: F811
    await appel.monter(source_etapes=[_texte("rien")], fond_etapes=[_texte("rien")], outils_du_fond=False)
    moteur = appel.engine
    agent = moteur.active_agent
    agent.reglages = {**dict(agent.reglages or {}), "agent_principal_id": 77}
    appels = []
    monkeypatch.setattr(moteur, "_rendre_au_principal", lambda a, p, **kw: appels.append((p, kw)) or True)
    monkeypatch.setattr(type(moteur), "agent_transfer_enabled", True, raising=False)
    monkeypatch.setattr(moteur, "agent_can_act", lambda a: True)
    assert await moteur.sortir_de_l_impasse(agent, etape_cible="etape-b") is True
    assert appels == [(77, {"etape_cible": "etape-b"})]


@pytest.mark.asyncio
async def test_moteur_l_accueil_passe_de_force_a_son_etape_de_retour_et_sans_retour_le_modele_garde_la_main(appel, monkeypatch):  # noqa: F811
    from api.services.workflow import pipecat_engine

    await appel.monter(source_etapes=[_texte("rien")], fond_etapes=[_texte("rien")], outils_du_fond=False)
    moteur = appel.engine
    agent = moteur.active_agent
    agent.reglages = {k: v for k, v in dict(agent.reglages or {}).items() if k != "agent_principal_id"}
    monkeypatch.setattr(moteur, "agent_can_act", lambda a: True)
    pris = []

    async def set_node(identifiant, **kw):
        pris.append(identifiant)

    monkeypatch.setattr(moteur, "set_node", set_node)
    retour = SimpleNamespace(id="retour", name="Retour", is_end=False)
    monkeypatch.setattr(pipecat_engine, "etape_de_retour_du_graphe", lambda graphe: None)
    assert await moteur.sortir_de_l_impasse(agent) is False and pris == []
    monkeypatch.setattr(pipecat_engine, "etape_de_retour_du_graphe", lambda graphe: retour)
    assert await moteur.sortir_de_l_impasse(agent) is True and pris == ["retour"]
    # l'étape choisie, quand elle existe dans le graphe de l'accueil, passe avant l'étape de retour
    choisie = next(n for n in agent.workflow.nodes.values() if not n.is_end and n is not agent.current_node)
    assert await moteur.sortir_de_l_impasse(agent, etape_cible=choisie.id) is True
    assert pris[-1] == choisie.id


@pytest.mark.asyncio
async def test_moteur_l_etape_cible_d_une_passation_choisit_l_etape_d_arrivee(appel):  # noqa: F811
    await appel.monter(source_etapes=[_texte("rien")], fond_etapes=[_texte("rien")], outils_du_fond=False)
    moteur = appel.engine
    assert moteur._etape_cible_demandee() is None
    moteur.transfer_coordinator._request = SimpleNamespace(etape_cible="etape-b")
    assert moteur._etape_cible_demandee() == "etape-b"


# --------------------------------------------------------------------------- #
# Le schéma des suites
# --------------------------------------------------------------------------- #


def test_schema_aller_a_une_etape_garde_l_etape_rendre_la_main_non():
    garde = ReglePhrase.model_validate(
        {"motif": IMPASSE_REPETEE, "variantes": ["a"], "ensuite": {"action": "aller_a_une_etape", "destination": " etape-b "}}
    )
    assert garde.ensuite.action == "aller_a_une_etape" and garde.ensuite.destination == "etape-b"
    sans = ReglePhrase.model_validate({"motif": IMPASSE, "variantes": ["a"], "ensuite": {"action": "aller_a_une_etape"}})
    assert sans.ensuite.destination is None
    rendre = ReglePhrase.model_validate(
        {"motif": IMPASSE, "variantes": ["a"], "ensuite": {"action": "rendre_la_main", "destination": "etape-b"}}
    )
    assert rendre.ensuite.destination is None


def test_schema_les_deux_suites_ne_sont_permises_qu_aux_deux_motifs_de_l_impasse():
    for motif in MOTIFS.values():
        permises = {"rendre_la_main", "aller_a_une_etape"} <= set(motif.sorties_permises)
        assert permises == (motif.id in (IMPASSE, IMPASSE_REPETEE)), motif.id
    with pytest.raises(ValueError):
        ReglePhrase.model_validate({"motif": "outil_echoue", "variantes": ["a"], "ensuite": {"action": "rendre_la_main"}})
    for id_ in (IMPASSE, IMPASSE_REPETEE):
        motif = MOTIFS[id_]
        assert motif.actif_par_defaut and motif.moment == "probleme" and motif.famille == "annonce" and motif.sortie_par_le_code


def test_les_notices_au_modele_ne_disent_aucun_mot_de_metier():
    for notice in (NOTICE_TEMPS_1, NOTICE_TEMPS_2):
        assert notice and "poêle" not in notice.lower() and impasse.CLE_IMPASSE == "impasse"


@pytest.mark.asyncio
async def test_le_temps_3_attend_la_fin_du_travail_de_fond_en_cours():
    banc = Banc()
    _entrer(banc)
    banc.travaux = [SimpleNamespace(occupe=True)]
    banc._gathered_context["travaux"] = [_trace(RECHERCHE, statut="en_cours")]
    for _ in range(4):  # quatre redemandes identiques : le signe 2 compte même pendant l'attente (D-3)
        compter_la_demande(banc, banc.active_agent, RECHERCHE)
    assert banc.etat()["temps"] == 3 and banc.etat()["a_declencher"] is True
    await _repliques(banc, "Je cherche toujours, merci de patienter un instant.")
    assert banc.mains == [] and banc.dit() == []  # rendre la main avec un résultat en route le perdrait
    banc.travaux = []
    await _repliques(banc, "Voici le résultat de ma recherche pour vous.")
    assert banc.mains == [None] and banc.dit() == [MOTIFS[IMPASSE].variantes_defaut[0]]
