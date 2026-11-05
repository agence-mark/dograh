"""[.mark] Builder partie 3, SA-L3a : « Prêt à publier » (une seule liste) et les contrôles « sans effet ».

| Groupe | Ce qu'il prouve |
|---|---|
| sans effet (pur) | chaque cas est vu quand il existe, disparaît quand il n'existe pas, et sa correction en un clic le fait disparaître |
| impasse | la sortie d'impasse sans issue : agent seul sans étape de retour = constat ; une issue (retour rédigé, étape choisie, raccrocher,
  transférer, spécialisé) ou un interrupteur éteint = aucun |
| liste | quatre états, ligne éteinte cachée, « hérité du principal », fiche « sans objet » en temps réel, obligatoires en tête |
| garde | la publication est refusée par les nouvelles lignes quand leur contrôle est sur « bloque », jamais sur « prévient » ou « éteint » |
| route | la correction en un clic écrit le BROUILLON, ne joue que ce que le brouillon propose, est cloisonnée par organisation |
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from api.services import preparation
from api.services.preparation import liste
from api.services.publication import controles, sans_effet
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, monde, sans_les_lignes_de_pret  # noqa: F401
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.mark.test_builder_tests_agent import banc  # noqa: F401


def _noeud(identifiant, nom, type_="agentNode", **donnees):
    return {"id": identifiant, "type": type_, "position": {"x": 0, "y": 0}, "data": {"name": nom, "prompt": f"Prompt {nom}", **donnees}}


def _liaison(identifiant, source, cible, **donnees):
    return {"id": identifiant, "source": source, "target": cible, "data": {"label": f"vers {cible}", "condition": "toujours", **donnees}}


def _graphe(noeuds=None, liaisons=None):
    return {
        "nodes": noeuds
        or [
            _noeud("1", "Accueil", "startCall", is_start=True, greeting="Bonjour."),
            _noeud("2", "Suite"),
            _noeud("3", "Fin", "endCall"),
        ],
        "edges": liaisons or [_liaison("e1", "1", "2"), _liaison("e2", "2", "3")],
    }


def _cles(constats):
    return [c.cle for c in constats]


def _evaluer(definition=None, configurations=None, **options):
    return sans_effet.evaluer(definition or _graphe(), configurations or {}, **options)


def _apres(constat, indice, definition, configurations=None):
    return sans_effet.appliquer(constat.corrections[indice], definition, configurations or {})


# --- condition sur une étape où le modèle décide ----------------------------------------------------------------------------------


def test_une_condition_sur_la_fiche_d_une_etape_ou_le_modele_decide_est_sans_effet():
    graphe = _graphe()
    graphe["edges"][0]["data"]["condition_sur_la_fiche"] = {"etape_complete": True}
    sans_impasse = {"moteur_sortie_d_impasse": False}
    constats = _evaluer(graphe, sans_impasse)
    assert _cles(constats) == ["condition_sur_le_modele"] and constats[0].noeud_id == "1" and constats[0].liaison_id == "e1"
    # la fiche décide sur cette étape : la condition joue, plus de constat
    graphe["nodes"][0]["data"]["qui_decide_du_passage"] = "choix"
    assert "condition_sur_le_modele" not in _cles(_evaluer(graphe, sans_impasse))


def test_les_deux_corrections_d_une_condition_sans_effet_la_font_disparaitre():
    graphe = _graphe()
    graphe["edges"][0]["data"]["condition_sur_la_fiche"] = {"champ": "motif", "vaut": "urgence"}
    config = {"moteur_sortie_d_impasse": False}
    constat = _evaluer(graphe, config)[0]
    for indice in (0, 1):
        nouvelle, _ = _apres(constat, indice, graphe, config)
        assert "condition_sur_le_modele" not in _cles(_evaluer(nouvelle, config)), constat.corrections[indice].id
    # la définition d'origine n'est jamais modifiée (copie)
    assert graphe["edges"][0]["data"]["condition_sur_la_fiche"] == {"champ": "motif", "vaut": "urgence"}


# --- collecte et portes écrites sans fiche ---------------------------------------------------------------------------------------


def test_une_etape_qui_passe_par_la_fiche_sans_fiche_active_est_sans_effet_et_se_corrige():
    graphe = _graphe()
    graphe["nodes"][1]["data"]["qui_decide_du_passage"] = "collecte"
    sans_champs = {"moteur_sortie_d_impasse": False}
    constat = _evaluer(graphe, sans_champs)[0]
    assert constat.cle == "collecte_sans_fiche" and [c.id for c in constat.corrections] == ["faire_decider_le_modele"]  # pas de champ : rien à allumer
    avec_champs = {"fiche_champs": [{"nom": "motif"}], "moteur_sortie_d_impasse": False}
    constat = _evaluer(graphe, avec_champs)[0]
    assert [c.id for c in constat.corrections] == ["allumer_la_fiche", "faire_decider_le_modele"]
    _, ecrits = _apres(constat, 0, graphe, avec_champs)
    assert ecrits == {"fiche_au_fil_de_leau": True}
    allumee = {**avec_champs, "fiche_au_fil_de_leau": True}
    assert _evaluer(graphe, allumee) == []
    nouvelle, _ = _apres(constat, 1, graphe, avec_champs)
    assert _evaluer(nouvelle, avec_champs) == []


def test_des_portes_dans_la_reponse_sans_fiche_sont_sans_effet():
    config = {"portes_dans_la_reponse": True, "moteur_sortie_d_impasse": False}
    constat = _evaluer(configurations=config)[0]
    assert constat.cle == "portes_sans_fiche" and [c.id for c in constat.corrections] == ["rappeler_la_porte"]
    _, ecrits = _apres(constat, 0, _graphe(), config)
    assert ecrits == {"portes_dans_la_reponse": False}
    config_fiche = {**config, "fiche_au_fil_de_leau": True, "fiche_champs": [{"nom": "x"}]}
    assert _evaluer(configurations=config_fiche) == []


# --- temps réel ------------------------------------------------------------------------------------------------------------------


def test_le_temps_reel_avec_des_fonctions_de_la_chaine_est_sans_effet():
    graphe = _graphe()
    graphe["nodes"][1]["data"]["qui_decide_du_passage"] = "collecte"
    config = {"fiche_au_fil_de_leau": True, "portes_dans_la_reponse": True, "fiche_mode_de_note": "greffier", "moteur_sortie_d_impasse": False}
    constats = _evaluer(graphe, config, temps_reel=True)
    assert _cles(constats) == ["temps_reel_chaine"]  # le cas de la collecte sans fiche n'est pas doublé
    assert constats[0].noms == ["fiche_au_fil_de_leau", "portes_dans_la_reponse", "greffier", "passages"]
    nouvelle, ecrits = _apres(constats[0], 0, graphe, config)
    assert _evaluer(nouvelle, {**config, **ecrits}, temps_reel=True) == []
    # en chaîne, les mêmes réglages sont légitimes
    assert "temps_reel_chaine" not in _cles(_evaluer(graphe, {**config, "fiche_champs": [{"nom": "x"}]}))
    # le temps réel sans rien d'allumé : rien à dire
    assert _evaluer(configurations={"moteur_sortie_d_impasse": False}, temps_reel=True) == []


# --- étapes de retour ------------------------------------------------------------------------------------------------------------


def test_deux_etapes_de_retour_se_corrigent_en_gardant_l_une():
    graphe = _graphe()
    graphe["nodes"][0]["data"]["etape_de_retour"] = True
    graphe["nodes"][1]["data"]["etape_de_retour"] = True
    config = {"moteur_sortie_d_impasse": False}
    constats = [c for c in _evaluer(graphe, config) if c.cle == "retour_double"]
    assert len(constats) == 1 and [c.id for c in constats[0].corrections] == ["garder_le_retour", "garder_le_retour"]
    nouvelle, _ = _apres(constats[0], 1, graphe, config)
    restes = [n["id"] for n in nouvelle["nodes"] if n["data"].get("etape_de_retour")]
    assert restes == ["2"] and "retour_double" not in _cles(_evaluer(nouvelle, config))


def test_une_etape_de_retour_non_redigee_est_sans_effet():
    graphe = _graphe()
    graphe["nodes"][1]["data"]["etape_de_retour"] = True
    graphe["nodes"][1]["data"]["prompt"] = ""
    config = {"moteur_sortie_d_impasse": False}
    constat = next(c for c in _evaluer(graphe, config) if c.cle == "retour_non_redige")
    assert constat.noeud_id == "2"
    graphe["nodes"][1]["data"]["prompt"] = "Tu reprends l'appel après un collègue."
    assert "retour_non_redige" not in _cles(_evaluer(graphe, config))


# --- annonce d'ouverture ---------------------------------------------------------------------------------------------------------


def test_une_annonce_d_ouverture_jamais_dite_se_corrige_dans_l_accueil():
    graphe = _graphe()
    config = {"horaires_ouverture": {"lundi": [["09:00", "18:00"]]}, "moteur_sortie_d_impasse": False}
    constat = _evaluer(graphe, config)[0]
    assert constat.cle == "annonce_jamais_dite" and constat.noeud_id == "1"
    nouvelle, _ = _apres(constat, 0, graphe, config)
    assert nouvelle["nodes"][0]["data"]["greeting"] == "{{initial_context.annonce_ouverture}}Bonjour."
    assert _evaluer(nouvelle, config) == []
    # sans horaires : rien à annoncer
    assert _evaluer(graphe, {"moteur_sortie_d_impasse": False}) == []
    # accueil enregistré (audio) : le constat reste, sans correction possible
    audio = copy.deepcopy(graphe)
    audio["nodes"][0]["data"]["greeting_type"] = "audio"
    assert _evaluer(audio, config)[0].corrections == []


# --- cumul de phrases ------------------------------------------------------------------------------------------------------------


def test_une_phrase_de_transition_et_une_premiere_replique_a_la_suite_se_corrigent():
    graphe = _graphe()
    graphe["edges"][0]["data"]["transition_speech"] = "Je regarde ça."
    graphe["edges"][0]["data"]["transition_speech_type"] = "text"
    config = {"moteur_sortie_d_impasse": False}
    assert _evaluer(graphe, config) == []  # sans première réplique, une seule phrase
    graphe["nodes"][1]["data"]["premiere_replique"] = "Alors, voyons."
    constat = _evaluer(graphe, config)[0]
    assert constat.cle == "cumul_de_phrases" and constat.liaison_id == "e1"
    nouvelle, _ = _apres(constat, 0, graphe, config)
    assert "transition_speech" not in nouvelle["edges"][0]["data"] and _evaluer(nouvelle, config) == []


# --- deux webhooks ---------------------------------------------------------------------------------------------------------------


def test_deux_webhooks_actifs_se_disent_et_se_corrigent():
    graphe = _graphe()
    graphe["nodes"].append(_noeud("w", "Notifier", "webhook", enabled=True))
    config = {"apres_appel": {"modules": ["webhook"]}, "moteur_sortie_d_impasse": False}
    assert _evaluer(graphe, config) == []  # le module .mark n'a pas d'adresse : un seul webhook
    constat = _evaluer(graphe, config, webhook_mark_pret=True)[0]
    assert constat.cle == "deux_webhooks" and constat.controle == "deux_webhooks"
    nouvelle, _ = _apres(constat, 0, graphe, config)
    assert nouvelle["nodes"][-1]["data"]["enabled"] is False and _evaluer(nouvelle, config, webhook_mark_pret=True) == []
    _, ecrits = _apres(constat, 1, graphe, config)
    assert ecrits == {"apres_appel": {"modules": []}} and _evaluer(graphe, {**config, **ecrits}, webhook_mark_pret=True) == []
    # un webhook de Dograh déjà désactivé ne compte pas
    graphe["nodes"][-1]["data"]["enabled"] = False
    assert _evaluer(graphe, config, webhook_mark_pret=True) == []


# --- sortie d'impasse sans issue --------------------------------------------------------------------------------------------------


def test_la_sortie_d_impasse_d_un_agent_seul_sans_etape_de_retour_ne_mene_nulle_part():
    constat = _evaluer()[0]
    assert constat.cle == "impasse_sans_issue" and constat.controle == "sortie_d_impasse"
    assert [c.id for c in constat.corrections] == ["renvoyer_a_l_accueil", "eteindre_la_sortie_d_impasse"]


def test_une_issue_ou_un_interrupteur_eteint_ou_un_specialise_levent_le_constat():
    retour = _graphe()
    retour["nodes"][1]["data"]["etape_de_retour"] = True
    assert _evaluer(retour) == []  # une étape de retour rédigée : « rendre la main » mène quelque part
    assert _evaluer(configurations={"moteur_sortie_d_impasse": False}) == []
    assert _evaluer(specialiste=True) == []  # un collègue rend la main à son principal
    for action, destination in (("raccrocher", None), ("transferer", "astreinte")):
        regle = {"motif": "impasse", "portee": "agent", "variantes": ["Je vous passe quelqu'un."], "ensuite": {"action": action, "destination": destination}}
        assert _evaluer(configurations={"phrases_regles": [regle]}) == [], action
    choisie = {"motif": "impasse", "portee": "agent", "variantes": ["Reprenons."], "ensuite": {"action": "aller_a_une_etape", "destination": "2"}}
    assert _evaluer(configurations={"phrases_regles": [choisie]}) == []
    # une étape choisie qui n'existe pas, ou qui est une fin : nulle part
    for cible in ("99", "3"):
        mauvaise = {**choisie, "ensuite": {"action": "aller_a_une_etape", "destination": cible}}
        assert _cles(_evaluer(configurations={"phrases_regles": [mauvaise]})) == ["impasse_sans_issue"], cible
    # « le modèle garde la main » : nulle part
    modele = {"motif": "impasse", "portee": "agent", "variantes": ["Reprenons."], "ensuite": {"action": "modele"}}
    assert _cles(_evaluer(configurations={"phrases_regles": [modele]})) == ["impasse_sans_issue"]
    # le motif éteint : le code ne change pas d'étape, c'est un choix, pas une impasse sans issue
    eteint = {"motif": "impasse", "portee": "agent", "variantes": [], "active": False}
    assert _evaluer(configurations={"phrases_regles": [eteint]}) == []


def test_eteindre_la_sortie_d_impasse_leve_le_constat():
    constat = _evaluer()[0]
    _, ecrits = _apres(constat, 1, _graphe())
    assert ecrits == {"moteur_sortie_d_impasse": False} and _evaluer(configurations=ecrits) == []


def test_un_identifiant_libre_n_est_pas_une_correction():
    with pytest.raises(sans_effet.CorrectionRefusee):
        sans_effet.appliquer(sans_effet.Correction("supprimer_tout"), _graphe(), {})
    with pytest.raises(sans_effet.CorrectionRefusee):
        sans_effet.appliquer(sans_effet.Correction("retirer_le_retour", noeud_id="absent"), _graphe(), {})


def test_un_graphe_illisible_ne_fait_tomber_aucun_cas():
    assert sans_effet.evaluer({"nodes": "x", "edges": None}, {"phrases_regles": "?"}) is not None
    assert sans_effet.evaluer(None, None) is not None


# --- la liste assemblée ----------------------------------------------------------------------------------------------------------


GRAPHE_PREP = {
    "nodes": [_noeud("1", "Accueil", "startCall", is_start=True, tool_uuids=["outil-1"], prompt="Bonjour {{ville}}")],
    "edges": [],
}


def _etapes(**remplacements):
    base = dict(
        definition=GRAPHE_PREP,
        variables_du_modele={},
        configurations={},
        effective=SimpleNamespace(llm=1, stt=1, tts=1, realtime=None, is_realtime=False),
        outils_actifs={"outil-1"},
        fiche=None,
        tests=[],
        problemes_tests_obligatoires=[],
    )
    base.update(remplacements)
    return preparation.calculer(**base)


def _bloc(cle, position, statut="ok", problemes=None):
    return {"cle": cle, "position": position, "statut": statut, "problemes": problemes or []}


POSITIONS_PAR_DEFAUT = [_bloc(c, "bloque") for c in ("variables", "briques", "outils")] + [_bloc("bilan_du_prompt", "bloque")]


def _lignes(etapes, constats=(), controles=POSITIONS_PAR_DEFAUT):
    return {l["id"]: l for l in liste.assembler(etapes, list(constats), list(controles))}


def test_une_ligne_obligatoire_non_faite_est_bloquante_par_le_reglage_du_controle():
    etapes = _etapes()
    assert _lignes(etapes)["variables"]["etat"] == "bloquant"
    prevenu = [_bloc("variables", "previent")] + POSITIONS_PAR_DEFAUT[1:]
    assert _lignes(etapes, controles=prevenu)["variables"]["etat"] == "a_faire"
    eteint = [_bloc("variables", "eteint")] + POSITIONS_PAR_DEFAUT[1:]
    assert "variables" not in _lignes(etapes, controles=eteint)  # un contrôle éteint n'est pas joué : la ligne ne se montre pas
    assert _lignes(_etapes(variables_du_modele={"ville": "Lille"}))["variables"]["etat"] == "fait"


def test_une_ligne_dit_l_etape_exacte_ou_ca_se_regle():
    lignes = _lignes(_etapes(outils_actifs=set()))
    assert lignes["variables"]["noeud_id"] == "1" and lignes["variables"]["manquants"] == ["ville"]
    assert lignes["outils"]["noeud_id"] == "1" and lignes["outils"]["manquants"] == ["outil-1"]


def test_la_fiche_est_sans_objet_en_temps_reel_et_les_outils_sans_outil():
    temps_reel = SimpleNamespace(llm=None, stt=None, tts=None, realtime=object(), is_realtime=True)
    lignes = _lignes(_etapes(effective=temps_reel, definition={"nodes": [_noeud("1", "A", "startCall")], "edges": []}))
    assert "fiche" not in lignes and "outils" not in lignes and lignes["briques"]["etat"] == "fait"


def test_un_reglage_recu_du_principal_est_dit_herite():
    etapes = _etapes(configurations={"fiche_champs": [{"nom": "x"}], "panne": {"x": 1}}, suivies_du_principal=frozenset({"fiche_champs", "panne"}))
    lignes = _lignes(etapes)
    assert lignes["fiche"]["etat"] == "herite" and lignes["panne"]["etat"] == "herite"
    # ce que le principal ne règle pas encore reste à faire
    assert _lignes(_etapes(suivies_du_principal=frozenset({"fiche_champs"})))["fiche"]["etat"] == "a_faire"
    # une ligne propre à l'agent n'est jamais dite héritée
    assert _lignes(_etapes(configurations={"phrases_regles": [{}]}, suivies_du_principal=frozenset()))["phrases"]["etat"] == "fait"


def test_les_obligatoires_sont_en_tete_les_faites_en_fin_et_les_constats_gardent_leur_controle():
    constat = _evaluer()[0]  # impasse sans issue
    blocs = POSITIONS_PAR_DEFAUT + [_bloc("sortie_d_impasse", "bloque"), _bloc("sans_effet", "previent"), _bloc("deux_webhooks", "previent")]
    lignes = liste.assembler(_etapes(variables_du_modele={"ville": "x"}), [constat], blocs)
    rangs = [(l["niveau"], l["etat"]) for l in lignes]
    assert rangs == sorted(rangs, key=lambda r: (0 if r[0] == "requis" else 1, {"bloquant": 0, "a_faire": 1}.get(r[1], 2)))
    impasse = next(l for l in lignes if l["id"] == "impasse_sans_issue")
    assert impasse["etat"] == "bloquant" and impasse["controle"] == "sortie_d_impasse" and impasse["corrections"][0]["id"] == "renvoyer_a_l_accueil"
    # prévient : la même ligne reste à faire, ne bloque pas
    prevenu = [b if b["cle"] != "sortie_d_impasse" else _bloc("sortie_d_impasse", "previent") for b in blocs]
    assert next(l for l in liste.assembler(_etapes(), [constat], prevenu) if l["id"] == "impasse_sans_issue")["etat"] == "a_faire"
    # éteint : la ligne n'existe pas
    eteint = [b if b["cle"] != "sortie_d_impasse" else _bloc("sortie_d_impasse", "eteint") for b in blocs]
    assert "impasse_sans_issue" not in {l["id"] for l in liste.assembler(_etapes(), [constat], eteint)}


def test_les_controles_de_la_fenetre_publier_deviennent_des_lignes():
    blocs = POSITIONS_PAR_DEFAUT + [
        _bloc("attaques", "bloque", "echec", ["2 attack(s) got through."]),
        _bloc("garde_fous", "eteint", "eteint"),
        _bloc("liste_vocale", "previent", "alerte", ["Un point"]),
    ]
    lignes = _lignes(_etapes(variables_du_modele={"ville": "x"}), controles=blocs)
    assert lignes["attaques"]["etat"] == "bloquant" and lignes["attaques"]["onglet"] == "tests"
    assert lignes["attaques"]["manquants"] == ["2 attack(s) got through."]
    assert lignes["liste_vocale"]["etat"] == "a_faire" and "garde_fous" not in lignes
    assert lignes["bilan_du_prompt"]["etat"] == "fait"


# --- la garde de publication -----------------------------------------------------------------------------------------------------


def _brouillon(configurations=None, graphe=None):
    return SimpleNamespace(
        workflow_json=graphe or _graphe(),
        version_number=2,
        workflow_configurations=configurations if configurations is not None else {},
    )


async def test_la_publication_est_refusee_par_la_sortie_d_impasse_sans_issue_et_se_leve_par_la_correction(banc):  # noqa: F811
    from api.services.builder.tests_agent import publication

    wf = banc.workflows[AGENT]
    seul_l_impasse = sans_les_lignes_de_pret({"publication": {"controles": {"sortie_d_impasse": "bloque"}}})
    refus = await publication.verifier_avant_publication(wf, _brouillon(seul_l_impasse), ORG_CLIENT)
    assert refus is not None and [c["cle"] for c in refus["controles_publication"]] == ["sortie_d_impasse"]
    # la même chose qui prévient, ou éteinte, ne bloque pas
    for position in ("previent", "eteint"):
        souple = sans_les_lignes_de_pret({"publication": {"controles": {"sortie_d_impasse": position}}})
        assert await publication.verifier_avant_publication(wf, _brouillon(souple), ORG_CLIENT) is None, position
    # une issue réglée : la publication passe
    corrigee = {**seul_l_impasse, "moteur_sortie_d_impasse": False}
    assert await publication.verifier_avant_publication(wf, _brouillon(corrigee), ORG_CLIENT) is None


async def test_les_lignes_obligatoires_par_defaut_bloquent_la_publication(banc):  # noqa: F811
    from api.services.builder.tests_agent import publication

    wf = banc.workflows[AGENT]
    refus = await publication.verifier_avant_publication(wf, _brouillon({}), ORG_CLIENT)
    assert refus is not None
    bloquants = {c["cle"] for c in refus["controles_publication"]}
    assert {"briques", "sortie_d_impasse"} <= bloquants  # les défauts : variables, briques, outils et l'impasse bloquent


async def test_les_reglages_sans_effet_previennent_par_defaut_et_ne_bloquent_qu_au_choix(banc):  # noqa: F811
    from api.services.builder.tests_agent import publication

    wf = banc.workflows[AGENT]
    graphe = _graphe()
    graphe["edges"][0]["data"]["condition_sur_la_fiche"] = {"etape_complete": True}
    base = sans_les_lignes_de_pret({"moteur_sortie_d_impasse": False, "publication": {"controles": {"sans_effet": "previent"}}})
    assert await publication.verifier_avant_publication(wf, _brouillon(base, graphe), ORG_CLIENT) is None
    vue = await controles.evaluer(wf, _brouillon(base, graphe), ORG_CLIENT)
    bloc = next(c for c in vue["controles"] if c["cle"] == "sans_effet")
    assert bloc["statut"] == "alerte" and vue["bloque"] is False
    assert any(l["constat"] == "condition_sur_le_modele" and l["etat"] == "a_faire" for l in vue["lignes"])
    dur = sans_les_lignes_de_pret({"moteur_sortie_d_impasse": False, "publication": {"controles": {"sans_effet": "bloque"}}})
    refus = await publication.verifier_avant_publication(wf, _brouillon(dur, graphe), ORG_CLIENT)
    assert refus is not None and [c["cle"] for c in refus["controles_publication"]] == ["sans_effet"]


async def test_la_fenetre_et_le_builder_lisent_la_meme_liste(banc, monde, monkeypatch):  # noqa: F811
    from api.services.builder.actions import publication as actions_publication
    from api.services.builder.actions.registre import Contexte, executer

    monkeypatch.setattr(actions_publication, "db_client", monde)
    monkeypatch.setattr("api.services.builder.actions.registre.db_client", monde, raising=False)
    from api.tests.mark.builder_commun import utilisateur

    wf = banc.workflows[AGENT]
    banc.brouillons[AGENT].workflow_configurations = sans_les_lignes_de_pret({"publication": {"controles": {"sortie_d_impasse": "bloque"}}})
    direct = await controles.evaluer(wf, banc.brouillons[AGENT], ORG_CLIENT)
    par_le_builder = await executer("publication_controler", {}, Contexte(user=utilisateur(1), workflow_id=AGENT))
    assert par_le_builder.get("ok") is True, par_le_builder
    assert par_le_builder["lignes"] == direct["lignes"] and any(l["id"] == "impasse_sans_issue" for l in direct["lignes"])


# --- la route de correction (vraie base) -------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("sans_preparation_des_organisations")
async def test_la_correction_en_un_clic_ecrit_le_brouillon_et_rend_la_liste_recalculee(db_session):
    org = await creer_organisation(db_session, "pret-a")
    autre = await creer_organisation(db_session, "pret-b")
    user, jeton = await creer_compte(db_session, "pret-a@example.com", role="Administrateur", organisations=[org])
    _, jeton_autre = await creer_compte(db_session, "pret-b@example.com", role="Administrateur", organisations=[autre])
    agent = await db_session.create_workflow(name="A", workflow_definition=_graphe(), user_id=user.id, organization_id=org)
    await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe())
    base = f"/api/v1/builder/publication/{agent.id}"
    async with client_http() as c:
        avant = (await c.get(base, headers=entetes(jeton, org))).json()
        assert any(l["id"] == "impasse_sans_issue" and l["etat"] == "bloquant" for l in avant["lignes"])
        # une correction que le brouillon ne propose pas : refusée, rien n'est écrit
        refus = await c.post(f"{base}/corriger-un-reglage", json={"correction": "retirer_le_retour", "noeud_id": "2"}, headers=entetes(jeton, org))
        assert refus.status_code == 409
        # un autre client ne corrige pas cet agent
        chez_l_autre = await c.post(f"{base}/corriger-un-reglage", json={"correction": "renvoyer_a_l_accueil", "noeud_id": "1"}, headers=entetes(jeton_autre, autre))
        assert chez_l_autre.status_code == 404
        ok = await c.post(f"{base}/corriger-un-reglage", json={"correction": "renvoyer_a_l_accueil", "noeud_id": "1"}, headers=entetes(jeton, org))
        assert ok.status_code == 200, ok.text
        apres = ok.json()
        assert not any(l["id"] == "impasse_sans_issue" for l in apres["lignes"])
        brouillon = await db_session.get_draft_version(agent.id)
        regles = brouillon.workflow_configurations["phrases_regles"]
        assert regles[0]["motif"] == "impasse" and regles[0]["ensuite"] == {"phrases": [], "noter": None, "action": "aller_a_une_etape", "destination": "1"}
        # la lecture de la page de l'agent voit la même chose
        page = (await c.get(f"/api/v1/workflow/{agent.id}/preparation", headers=entetes(jeton, org))).json()["etapes"]
        assert not any(l["id"] == "impasse_sans_issue" for l in page)
