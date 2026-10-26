"""[.mark] Chantier correctifs-apres-banc-v4, lot 4 (4.8, 4.11) : la résolution à huit rangs, la carte et les
sons des phrases de sortie.

| Test | La garantie |
|---|---|
| huit rangs | étape + outil, étape, agent + outil, agent, groupe + outil, groupe, ancien réglage, défaut : chacun gagne quand les précédents manquent |
| outil | « pour l'outil » ne vaut que pour cet outil ; sans outil connu, une règle qui en nomme ne vaut pas |
| motif sans outil | l'outil est ignoré pour un motif qui ne vise pas d'outil |
| spécialisé | il hérite du groupe puis garde la sienne, l'outil compris |
| carte | chaque règle est rendue avec ses cases, l'étape supprimée est signalée, les cases du motif sont lues |
| sons | les phrases de sortie et toutes les variantes « dans l'ordre » sont fabriquées au décroché |
"""

from api.services.phrases.carte import AgentDeLaCarte, construire_la_carte
from api.services.phrases.catalogue import (
    OUTIL_ECHOUE,
    OUTIL_TARDE,
    PASSATION_TARDE,
    TRAVAIL_DURE,
)
from api.services.phrases.regles import (
    NIVEAU_AGENT,
    NIVEAU_DEFAUT,
    NIVEAU_ETAPE,
    NIVEAU_PRINCIPAL,
    resoudre,
)
from api.services.phrases.sons import textes_a_fabriquer


def _r(motif, variantes, portee="agent", **champs):
    return {"motif": motif, "portee": portee, "variantes": variantes, **champs}


def test_les_huit_rangs_dans_l_ordre():
    principal = {
        "phrases_regles": [
            _r(OUTIL_ECHOUE, ["Groupe, outil."], "groupe", outils=["reserver"]),
            _r(OUTIL_ECHOUE, ["Groupe."], "groupe"),
        ]
    }
    agent = {
        "phrases_regles": [
            _r(OUTIL_ECHOUE, ["Étape, outil."], "etape", etape="Rdv", etape_id="n1", outils=["reserver"]),
            _r(OUTIL_ECHOUE, ["Étape."], "etape", etape="Rdv", etape_id="n1"),
            _r(OUTIL_ECHOUE, ["Agent, outil."], outils=["reserver"]),
            _r(OUTIL_ECHOUE, ["Agent."]),
        ]
    }

    def lire(reglages_agent, reglages_principal, etape="Rdv", etape_id="n1", outil="reserver"):
        phrase = resoudre(
            OUTIL_ECHOUE,
            reglages_agent=reglages_agent,
            reglages_principal=reglages_principal,
            etape=etape,
            etape_id=etape_id,
            outil=outil,
        )
        return phrase.variantes[0], phrase.niveau

    assert lire(agent, principal) == ("Étape, outil.", NIVEAU_ETAPE)
    # Un autre outil à la même étape : la règle d'étape pour tous.
    assert lire(agent, principal, outil="chercher") == ("Étape.", NIVEAU_ETAPE)
    # Une autre étape : l'agent, avec l'outil puis sans.
    assert lire(agent, principal, etape="Autre", etape_id="n2") == ("Agent, outil.", NIVEAU_AGENT)
    assert lire(agent, principal, etape="Autre", etape_id="n2", outil="chercher") == ("Agent.", NIVEAU_AGENT)
    # Un spécialisé sans règle propre : le groupe du principal, avec l'outil puis sans.
    assert lire({}, principal) == ("Groupe, outil.", NIVEAU_PRINCIPAL)
    assert lire({}, principal, outil="chercher") == ("Groupe.", NIVEAU_PRINCIPAL)
    # Rien de réglé : le défaut du catalogue.
    phrase = resoudre(OUTIL_ECHOUE, reglages_agent={}, reglages_principal={})
    assert phrase.niveau == NIVEAU_DEFAUT and phrase.posee is False


def test_le_septieme_rang_est_l_ancien_reglage_avant_le_defaut():
    ancien = {"attente": {"phrase_pont": "Une seconde.", "delai_phrase_pont_s": 3}}
    phrase = resoudre(PASSATION_TARDE, reglages_agent={}, reglages_principal=ancien)
    assert (phrase.niveau, phrase.variantes, phrase.delai_s) == (NIVEAU_PRINCIPAL, ("Une seconde.",), 3)
    assert phrase.posee is True
    # Une règle du groupe, plus précise que l'ancien réglage, le remplace.
    avec = {**ancien, "phrases_regles": [_r(PASSATION_TARDE, ["Nouvelle."], "groupe", delai_s=1)]}
    assert resoudre(PASSATION_TARDE, reglages_agent={}, reglages_principal=avec).variantes == ("Nouvelle.",)


def test_sans_outil_connu_une_regle_qui_en_nomme_ne_vaut_pas_et_un_motif_sans_outil_l_ignore():
    reglages = {"phrases_regles": [_r(OUTIL_TARDE, ["Pour reserver."], outils=["reserver"])]}
    assert resoudre(OUTIL_TARDE, reglages_agent=reglages).niveau == NIVEAU_DEFAUT
    assert resoudre(OUTIL_TARDE, reglages_agent=reglages, outil="reserver").variantes == ("Pour reserver.",)
    # Le travail de fond ne vise pas d'outil : l'outil donné est ignoré.
    fond = {"phrases_regles": [_r(TRAVAIL_DURE, ["Fond."], outils=["reserver"])]}
    assert resoudre(TRAVAIL_DURE, reglages_agent=fond, outil="reserver").variantes == ("Fond.",)


def test_la_carte_rend_chaque_regle_avec_ses_cases_et_signale_l_etape_supprimee():
    reglages = {
        "phrases_regles": [
            _r(OUTIL_ECHOUE, ["Souci."], max_par_appel=2,
               ensuite={"phrases": ["On vous rappelle."], "action": "raccrocher"}),
            _r(OUTIL_ECHOUE, ["Souci de réservation."], outils=["reserver"]),
            _r(OUTIL_TARDE, ["Un instant."], "etape", etape="Rdv", etape_id="n1", delai_s=0, redite_s=5,
               max_par_attente=3, ordre="dans_l_ordre"),
            _r(OUTIL_TARDE, ["Fantôme."], "etape", etape="Supprimée", etape_id="nX", delai_s=1),
        ]
    }
    graphe = {"nodes": [{"id": "n1", "data": {"name": "Rendez-vous renommé"}}]}
    carte = construire_la_carte(
        [AgentDeLaCarte(id=1, nom="Accueil", reglages=reglages, graphe=graphe, est_principal=True)],
        reglages,
    )
    agent = carte["agents"][0]
    assert len(agent["motifs"]) == 12
    echoue = next(m for m in agent["motifs"] if m["motif"] == OUTIL_ECHOUE)
    assert echoue["moment"] == "probleme" and echoue["max_par_appel"] == 2
    assert echoue["ensuite"]["action"] == "raccrocher" and echoue["ensuite"]["phrases"] == ["On vous rappelle."]
    regles = {(r["motif"], r["etape_id"], tuple(r["outils"])): r for r in agent["regles"]}
    assert regles[(OUTIL_ECHOUE, None, ("reserver",))]["variantes"] == ["Souci de réservation."]
    vivante = regles[(OUTIL_TARDE, "n1", ())]
    assert vivante["redite_s"] == 5 and vivante["ordre"] == "dans_l_ordre" and vivante["etape_supprimee"] is False
    # L'étape n'existe plus dans le graphe : la carte le dit (la règle est sans effet).
    assert regles[(OUTIL_TARDE, "nX", ())]["etape_supprimee"] is True


def test_les_sons_couvrent_les_phrases_de_sortie_et_chaque_variante_dans_l_ordre():
    reglages = {
        "phrases_regles": [
            _r(OUTIL_TARDE, ["Un.", "Deux.", "Trois."], ordre="dans_l_ordre", delai_s=0, redite_s=3,
               max_par_attente=3, outils=["chercher"]),
            _r(OUTIL_ECHOUE, ["Souci."], ensuite={"phrases": ["Au revoir, pour de bon."], "action": "raccrocher"}),
            _r(OUTIL_ECHOUE, ["Avec {{prenom}}."], "etape", etape="Rdv", etape_id="n1"),
        ]
    }
    textes = textes_a_fabriquer([reglages], reglages)
    for attendu in ("Un.", "Deux.", "Trois.", "Souci.", "Au revoir, pour de bon."):
        assert attendu in textes
    # Une phrase à variable se fabrique à la volée, jamais au décroché.
    assert all("{{" not in t for t in textes)


def test_un_agent_qui_n_allume_rien_se_comporte_comme_avant():
    """Zéro perte : sans aucune règle, chaque motif rend le défaut du catalogue, une fois par attente,
    sans redite, sans plafond, sans sortie réglée (les nouveautés sont éteintes par défaut)."""
    from api.services.phrases.catalogue import MOTIFS

    for identifiant, motif in MOTIFS.items():
        phrase = resoudre(identifiant, reglages_agent={}, reglages_principal={})
        assert phrase.niveau == NIVEAU_DEFAUT, identifiant
        assert phrase.variantes == motif.variantes_defaut and phrase.active is motif.actif_par_defaut
        assert phrase.delai_s == motif.delai_defaut_s
        assert (phrase.redite_s, phrase.max_par_attente, phrase.max_par_appel) == (None, 1, None)
        assert phrase.ordre == "tournees" and phrase.sortie_posee is False
        assert phrase.texte_de_l_agent is False and phrase.max_pose is False
        assert phrase.action_de_sortie == motif.sortie_defaut
