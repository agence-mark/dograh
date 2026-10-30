"""[.mark] builder-agent-vocal, lot 5 : le contrôle du prompt par le code (Q12, B31, B34, B49).

Chaque défaut est détecté ET n'est pas détecté à tort ; chaque test rougit si la règle qu'il protège disparaît.
Règles génériques : aucun mot de métier dans ces textes d'essai.
"""

from __future__ import annotations

import pytest

from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.controle import regles, service
from api.services.builder.controle.regles import AVERTISSEMENT, BLOQUANT, Entree, ObjetConnu, OutilConnu
from api.tests.mark.builder_commun import AGENT, utilisateur


def noeud(identifiant, type_, nom, prompt="", **donnees):
    return {"id": identifiant, "type": type_, "position": {"x": 0, "y": 0}, "data": {"name": nom, "prompt": prompt, **donnees}}


def lien(a, b):
    return {"id": f"{a}-{b}", "source": a, "target": b, "data": {"label": "x", "condition": "y"}}


def graphe(*noeuds_, liens=None):
    return {"nodes": list(noeuds_), "edges": liens if liens is not None else [lien("1", "2")]}


def sain(prompt="Accueille la personne et demande ce dont elle a besoin."):
    return graphe(noeud("1", "startCall", "Départ", prompt), noeud("2", "endCall", "Fin", "Dis au revoir poliment."))


def codes(defauts, gravite=None):
    return {d.code for d in defauts if gravite is None or d.gravite == gravite}


def controle(g, **plus):
    return regles.controler(Entree(graphe=g, **plus))


def test_un_agent_sain_ne_donne_aucun_defaut():
    assert controle(sain()) == []


# --- règle écrite deux fois / contradictoire -------------------------------------------------------------------------


def test_une_regle_ecrite_deux_fois_dans_un_prompt_est_bloquante():
    p = "Parle toujours avec des phrases courtes et simples.\nPose une seule question à la fois.\nParle toujours avec des phrases courtes et simples."
    assert "regle_en_double" in codes(controle(sain(p)), BLOQUANT)


def test_une_regle_du_global_reprise_dans_une_etape_est_bloquante_sauf_si_l_etape_ne_le_lit_pas():
    regle = "Ne coupe jamais la parole de la personne qui te parle."
    g = graphe(noeud("0", "globalNode", "Global", regle), noeud("1", "startCall", "Départ", regle), noeud("2", "endCall", "Fin", "Au revoir."))
    assert "regle_en_double" in codes(controle(g), BLOQUANT)
    g["nodes"][1]["data"]["add_global_prompt"] = False
    assert "regle_en_double" not in codes(controle(g))


def test_deux_regles_differentes_ne_sont_pas_un_doublon():
    p = "Parle avec des phrases courtes et simples.\nPose une seule question à la fois, jamais deux."
    assert "regle_en_double" not in codes(controle(sain(p)))


def test_deux_regles_qui_se_contredisent_sont_bloquantes():
    p = "Reformule toujours la demande avant de répondre à la personne.\nReformule jamais la demande avant de répondre à la personne."
    assert "regles_contradictoires" in codes(controle(sain(p)), BLOQUANT)


def test_deux_regles_sur_des_sujets_differents_ne_se_contredisent_pas():
    p = "Reformule toujours la demande avant de répondre à la personne.\nN'interromps jamais la personne pendant qu'elle explique son besoin."
    assert "regles_contradictoires" not in codes(controle(sain(p)))


# --- nom d'outil, exemple de valeur -----------------------------------------------------------------------------------


OUTIL = OutilConnu(uuid="u1", nom="chercher_un_creneau", methode="POST")


def test_un_nom_d_outil_dans_le_texte_est_bloquant_et_un_mot_proche_ne_l_est_pas():
    entree = {"outils": {"u1": OUTIL}}
    assert "nom_d_outil_dans_le_texte" in codes(controle(sain("Appelle chercher_un_creneau pour proposer une heure."), **entree), BLOQUANT)
    assert "nom_d_outil_dans_le_texte" not in codes(controle(sain("Cherche un créneau pour la personne."), **entree))


def test_le_nom_de_l_outil_du_moteur_est_aussi_protege():
    d = controle(sain("Utilise signaler_un_probleme si tu es perdu."), noms_d_outils_du_moteur=("signaler_un_probleme",))
    assert "nom_d_outil_dans_le_texte" in codes(d, BLOQUANT)


@pytest.mark.parametrize(
    "texte",
    [
        "Par exemple écris contact@client-reel.fr dans la fiche.",
        "Rappelle au 06 12 34 56 78 si besoin.",
        "La date est 2026-03-04 pour le dossier.",
        "Dis par exemple : « bonjour madame » au début.",
    ],
)
def test_un_exemple_de_valeur_est_bloquant(texte):
    assert "exemple_de_valeur" in codes(controle(sain(texte)), BLOQUANT)


def test_une_variable_ou_un_chiffre_court_ne_sont_pas_un_exemple_de_valeur():
    assert "exemple_de_valeur" not in codes(controle(sain("Demande le numéro de téléphone {{initial_context.telephone}} et pose 2 questions.")))


# --- outil sans consigne d'échec, sortie, longueur --------------------------------------------------------------------------


def test_un_outil_sans_consigne_d_echec_est_bloquant_et_avec_consigne_non():
    sans = graphe(noeud("1", "startCall", "Départ", "Cherche ce qu'il faut.", tool_uuids=["u1"]), noeud("2", "endCall", "Fin", "Au revoir."))
    avec = graphe(
        noeud("1", "startCall", "Départ", "Cherche ce qu'il faut. Si l'outil ne répond pas, propose un rappel.", tool_uuids=["u1"]),
        noeud("2", "endCall", "Fin", "Au revoir."),
    )
    assert "outil_sans_consigne_d_echec" in codes(controle(sans), BLOQUANT)
    assert "outil_sans_consigne_d_echec" not in codes(controle(avec))


def test_une_etape_sans_chemin_vers_la_fin_est_bloquante_et_un_chemin_indirect_suffit():
    cul = graphe(noeud("1", "startCall", "Départ", "p"), noeud("3", "agentNode", "Impasse", "p"), noeud("2", "endCall", "Fin", "p"), liens=[lien("1", "2")])
    d = controle(cul)
    assert [x.etape for x in d if x.code == "etape_sans_sortie"] == ["Impasse"]
    indirect = graphe(noeud("1", "startCall", "Départ", "p"), noeud("3", "agentNode", "Milieu", "p"), noeud("2", "endCall", "Fin", "p"), liens=[lien("1", "3"), lien("3", "2")])
    assert "etape_sans_sortie" not in codes(controle(indirect))


def test_un_graphe_sans_etape_de_fin_est_bloquant():
    assert "etape_sans_sortie" in codes(controle(graphe(noeud("1", "startCall", "Départ", "p"), liens=[])), BLOQUANT)


def test_un_prompt_trop_long_est_bloquant_selon_le_plafond():
    long = "Une consigne tout à fait ordinaire. " * 10
    assert "longueur" in codes(controle(sain(long), plafond=100), BLOQUANT)
    assert "longueur" not in codes(controle(sain(long), plafond=5000))


# --- persona ---------------------------------------------------------------------------------------------------------------


PERSONA_PROPRE = "# Persona\nTu t'appelles Camille. Ton ton est chaleureux et posé.\n# Règles\nNe coupe jamais la parole."
PERSONA_AVEC_REGLE = "# Persona\nTu t'appelles Camille. Tu dois toujours vouvoyer la personne.\n# Règles\nPose une question à la fois."


def test_un_persona_avec_une_regle_de_conduite_est_bloquant_et_une_regle_hors_persona_non():
    g = lambda p: graphe(noeud("0", "globalNode", "Global", p), noeud("1", "startCall", "Départ", "Accueille."), noeud("2", "endCall", "Fin", "Au revoir."))
    assert "persona_avec_regle" in codes(controle(g(PERSONA_AVEC_REGLE)), BLOQUANT)
    assert "persona_avec_regle" not in codes(controle(g(PERSONA_PROPRE)))


def test_un_noeud_global_nomme_persona_est_lu_en_entier():
    g = graphe(noeud("0", "globalNode", "Persona", "Tu es Camille. Jamais de familiarité."), noeud("1", "startCall", "Départ", "Accueille."), noeud("2", "endCall", "Fin", "Fin."))
    assert "persona_avec_regle" in codes(controle(g), BLOQUANT)


def test_le_genre_du_persona_contre_la_voix_est_un_avertissement_seulement():
    g = graphe(noeud("0", "globalNode", "Persona", "Tu es Camille, ravie de t'occuper des appels et prête à aider."), noeud("1", "startCall", "Départ", "Accueille."), noeud("2", "endCall", "Fin", "Fin."))
    d = controle(g, genre_de_la_voix="m")
    assert "genre_persona_voix" in codes(d, AVERTISSEMENT) and "genre_persona_voix" not in codes(d, BLOQUANT)
    assert "genre_persona_voix" not in codes(controle(g, genre_de_la_voix="f"))
    # Genre de la voix non relevé : on ne devine pas.
    assert "genre_persona_voix" not in codes(controle(g, genre_de_la_voix=None))


# --- B34 : phrase dite par le code ------------------------------------------------------------------------------------------


def test_une_phrase_dite_par_le_code_ecrite_dans_un_prompt_est_bloquante():
    entree = {"phrases_du_code": ["Je regarde cela tout de suite pour vous."]}
    assert "phrase_du_code_dans_un_prompt" in codes(controle(sain("Dis : je regarde cela tout de suite pour vous, puis cherche."), **entree), BLOQUANT)
    assert "phrase_du_code_dans_un_prompt" not in codes(controle(sain("Cherche ce qu'il faut."), **entree))


def test_une_phrase_trop_courte_du_code_n_est_pas_cherchee():
    assert "phrase_du_code_dans_un_prompt" not in codes(controle(sain("Dis oui."), phrases_du_code=["Oui."]))


# --- R0-3 : écriture sans relecture ----------------------------------------------------------------------------------------


def test_un_outil_d_ecriture_sans_relecture_est_un_avertissement_et_avec_relecture_non():
    entree = {"outils": {"u1": OUTIL}}
    sans = graphe(noeud("1", "startCall", "Départ", "Enregistre la demande. Si l'outil échoue, propose un rappel.", tool_uuids=["u1"]), noeud("2", "endCall", "Fin", "Fin."))
    avec = graphe(
        noeud("1", "startCall", "Départ", "Relis ce que tu vas enregistrer et attends un oui avant d'agir. Si l'outil échoue, propose un rappel.", tool_uuids=["u1"]),
        noeud("2", "endCall", "Fin", "Fin."),
    )
    d = controle(sans, **entree)
    assert "outil_d_ecriture_sans_relecture" in codes(d, AVERTISSEMENT) and not codes(d, BLOQUANT)
    assert "outil_d_ecriture_sans_relecture" not in codes(controle(avec, **entree))
    lecture = OutilConnu(uuid="u1", nom="chercher_un_creneau", methode="GET")
    assert "outil_d_ecriture_sans_relecture" not in codes(controle(sans, outils={"u1": lecture}))


# --- B49 : {{nom}} et faits en dur --------------------------------------------------------------------------------------------


HORAIRES = ObjetConnu(nom="horaires", texte="Du lundi au vendredi de 9h à 18h")


def test_un_nom_inconnu_est_refuse():
    d = controle(sain("Les horaires sont {{horairs}}."), objets=[HORAIRES])
    assert [x.extrait for x in d if x.code == "variable_inconnue"] == ["{{horairs}}"]
    assert all(x.gravite == BLOQUANT for x in d if x.code == "variable_inconnue")


def test_le_nom_d_un_objet_existant_est_accepte_avec_ou_sans_repli():
    d = controle(sain("Les horaires sont {{horaires}} et {{ horaires | à voir }}."), objets=[HORAIRES])
    assert "variable_inconnue" not in codes(d)


def test_une_variable_posee_par_le_code_est_acceptee():
    from api.services.objets_agent.noms_poses_par_le_code import variables_posees_par_le_code

    posee = sorted(variables_posees_par_le_code())[0]
    d = controle(sain("Lis {{" + posee + "}} et {{initial_context.numero}} et {{current_time_Europe/Paris}}."), objets=[], variables_posees_par_le_code=variables_posees_par_le_code())
    assert "variable_inconnue" not in codes(d)
    # Sans la liste du code, la même variable serait inconnue : la liste vient bien du code.
    assert "variable_inconnue" in codes(controle(sain("Lis {{" + posee + "}}."), objets=[]))


def test_une_variable_de_l_agent_est_acceptee():
    assert "variable_inconnue" not in codes(controle(sain("Bonjour {{nom_client}}."), objets=[], variables_de_l_agent=frozenset({"nom_client"})))


def test_un_fait_en_dur_doublant_un_objet_est_un_avertissement():
    d = controle(sain("Nous sommes ouverts du lundi au vendredi de 9h à 18h, dis-le."), objets=[HORAIRES])
    assert "fait_en_dur" in codes(d, AVERTISSEMENT) and "fait_en_dur" not in codes(d, BLOQUANT)
    assert "fait_en_dur" not in codes(controle(sain("Dis les horaires : {{horaires}}."), objets=[HORAIRES]))


def test_une_base_injoignable_ne_bloque_pas_et_avertit():
    d = controle(sain("Les horaires sont {{horaires}}."), objets=None)
    assert not codes(d, BLOQUANT)
    assert [x.code for x in d if x.gravite == AVERTISSEMENT] == ["variable_non_verifiee"]


# --- le service et l'action ---------------------------------------------------------------------------------------------------------


EQUIPE = Contexte(user=utilisateur(1), workflow_id=AGENT)


async def test_l_action_prompt_controler_rend_ok_les_bloquants_et_les_elements_pour_la_carte(monde, monkeypatch):
    async def objets(_):
        return [HORAIRES]

    monkeypatch.setattr(service, "objets_du_client", objets)
    monde.workflows[AGENT].released_definition.workflow_json = sain("Les horaires sont {{inconnu}}. Écris le 06 12 34 56 78.")
    resultat = await executer("prompt_controler", {}, EQUIPE)
    assert resultat["ok"] is False
    assert {b["code"] for b in resultat["bloquants"]} >= {"variable_inconnue", "exemple_de_valeur"}
    assert all({"statut", "message"} <= set(e) for e in resultat["elements"])
    assert resultat["carte"]["type"] == "controle"


async def test_l_action_prompt_controler_est_ok_sur_un_agent_sain_et_refuse_un_autre_client(monde, monkeypatch):
    async def objets(_):
        return []

    monkeypatch.setattr(service, "objets_du_client", objets)
    monde.workflows[AGENT].released_definition.workflow_json = sain()
    assert (await executer("prompt_controler", {}, EQUIPE))["ok"] is True
    autre = Contexte(user=utilisateur(3, organisation=99), workflow_id=AGENT)
    assert (await executer("prompt_controler", {}, autre))["ok"] is False


def test_les_phrases_du_code_comptent_les_defauts_actifs_les_regles_reglees_et_les_fins():
    from api.services.phrases.catalogue import MOTIFS

    actifs = [m for m in MOTIFS.values() if m.actif_par_defaut and m.variantes_defaut]
    assert actifs, "le catalogue doit avoir au moins un motif actif par défaut"
    phrases = service.phrases_du_code({}, {"nodes": [{"data": {"fins": [{"phrase": "Merci, à bientôt."}]}}]})
    assert actifs[0].variantes_defaut[0] in phrases and "Merci, à bientôt." in phrases
    # Un motif réglé éteint ne dit plus son défaut.
    eteint = service.phrases_du_code({"phrases_regles": [{"motif": actifs[0].id, "active": False, "variantes": ["Autre phrase fixe."]}]}, {})
    assert actifs[0].variantes_defaut[0] not in eteint and "Autre phrase fixe." not in eteint
