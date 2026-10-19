"""[.mark] Le code souffle-t-il au modèle le prochain champ manquant de l'étape, et seulement ça ?

La question de ce fichier, et elle seule :

    Case « Step field labels » allumée, la requête de conversation porte-t-elle, pour
    l'ÉTAPE EN COURS, ses deux prochains champs manquants dans son ordre de priorité, en
    suggestion -- sans ce qu'un module a déjà lu au tour même, sans rien pour une étape
    sans étiquettes ; case éteinte, la requête est celle d'avant ?

Pourquoi il existe
------------------
Chantier ``agent-leger-greffier``, lot E (P1, D7 : construite quoi qu'il arrive, option par
agent, tous modes). Leçon A7 (run 835) : la liste de tout ce qui manque, sous les yeux de
l'accueil, a fait mener l'appel par l'accueil ; ici, seulement l'étape en cours, deux au plus.
Preuve sur une fiche d'un autre métier (un garage), par simple réglage.

🆕 fiabilite-orchestration, lot 2 (F9, C4) : le souffle prend la forme de « Déjà connu » :
``Encore attendu : immatriculation, kilometrage, commune garage.``, sur TOUTE la liste manquante
de l'étape (fin des deux au plus) ; la consigne « suggestion » quitte le souffle et s'écrit une
fois dans le prompt de l'étape.
"""

from api.services.workflow.dto import AgentNodeData, sanitize_workflow_definition
from api.services.workflow.fiche_au_fil_de_leau import (
    SOUFFLE_ETAPE_COMPLETE,
    ReglagesFiche,
    etat_avec_les_indices,
    montrer_la_fiche,
    souffle_de_l_etape,
)
from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante

CHAMPS = [
    {
        "nom": "immatriculation",
        "type": "string",
        "origine": "dicte",
        "description": "Plaque.",
    },
    {"nom": "kilometrage", "type": "string", "origine": "dicte", "description": "Km."},
    {
        "nom": "commune_garage",
        "type": "string",
        "origine": "dicte",
        "description": "Commune.",
    },
    {"nom": "motif", "type": "string", "origine": "deduit", "description": "Motif."},
]
ETAPE = ("immatriculation", "kilometrage", "commune_garage")


def _reglages(allume=True, mode="greffier"):
    return ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": CHAMPS,
            "fiche_mode_de_note": mode,
            "etiquettes_des_etapes": allume,
        }
    )


def test_toute_la_liste_manquante_dans_l_ordre_de_l_etape_au_format_deja_connu():
    souffle = souffle_de_l_etape(_reglages(), {"motif": "vidange"}, ETAPE)
    assert souffle == "Encore attendu : immatriculation, kilometrage, commune garage."
    assert "suggestion" not in souffle


def test_ce_qui_est_note_ou_lu_au_tour_meme_n_est_plus_souffle():
    fiche = {
        "immatriculation": "AB-123-CD",
        "communes_verifiees": [
            {
                "statut": "sure",
                "commune_retenue": {"nom": "Compiègne", "codes_postaux": ["60200"]},
            }
        ],
    }
    souffle = souffle_de_l_etape(_reglages(), fiche, ETAPE)
    assert "kilometrage" in souffle and "immatriculation" not in souffle
    assert "commune" not in souffle


def test_rien_case_eteinte_ou_sans_etiquettes():
    assert souffle_de_l_etape(_reglages(allume=False), {}, ETAPE) is None
    assert souffle_de_l_etape(_reglages(), {}, ()) is None
    plein = {"immatriculation": "x", "kilometrage": "1", "commune_garage": "y"}
    assert souffle_de_l_etape(_reglages(allume=False), plein, ETAPE) is None
    # Un nom qui n'est pas un champ de la fiche est ignoré, jamais soufflé.
    assert souffle_de_l_etape(_reglages(), plein, ("inconnu",)) is None


def test_etape_complete_le_souffle_dit_de_prendre_sa_porte():
    """Chantier greffier-conversation, lot C (C2, runs 1125, 1126, 1131) : tout est obtenu,
    noté ou lu au tour même par un module : l'agent est poussé vers sa porte."""
    plein = {"immatriculation": "x", "kilometrage": "1", "commune_garage": "y"}
    souffle = souffle_de_l_etape(_reglages(), plein, ETAPE)
    assert souffle == SOUFFLE_ETAPE_COMPLETE
    assert "prends ta porte" in souffle and "suggestion" not in souffle
    assert "Encore attendu" not in souffle


def test_tous_les_modes():
    for mode in ("outil", "post_scriptum", "greffier"):
        assert souffle_de_l_etape(_reglages(mode=mode), {}, ETAPE)


def test_la_requete_de_conversation_porte_le_souffle_de_l_etape_en_cours():
    class Faux:
        def __init__(self):
            self.vus = []

        async def get_chat_completions(self, context):
            return self.build_chat_completion_params({"messages": context})

        def build_chat_completion_params(self, p):
            return {"messages": list(p["messages"])}

    llm = Faux()
    etape = {"champs": ETAPE}
    montrer_la_fiche(llm, _reglages(), lambda: {}, None, lambda: etape["champs"])
    params = executer_sans_toucher_la_boucle_courante(
        llm.get_chat_completions([{"role": "user", "content": "bonjour"}])
    )
    assert any(
        "Encore attendu : immatriculation, kilometrage, commune garage." in m["content"]
        for m in params["messages"]
    )
    etape["champs"] = ()
    params = executer_sans_toucher_la_boucle_courante(
        llm.get_chat_completions([{"role": "user", "content": "bonjour"}])
    )
    assert not any("Encore attendu" in m["content"] for m in params["messages"])
    # Sans étiquettes ni fiche remplie, rien n'est ajouté : la requête d'avant.
    assert etat_avec_les_indices(_reglages(), {}, None, [], ()) is None


def test_le_noeud_porte_ses_etiquettes_et_le_vide_disparait():
    from api.services.workflow.workflow_graph import Node

    data = AgentNodeData(
        name="Rendez-vous", prompt="p", champs_etape=" immatriculation , kilometrage ,"
    )
    assert Node(id="1", node_type="agentNode", data=data).champs_etape == (
        "immatriculation",
        "kilometrage",
    )
    definition = sanitize_workflow_definition(
        {
            "nodes": [
                {
                    "id": "1",
                    "type": "agentNode",
                    "data": {"name": "a", "prompt": "p", "champs_etape": "  "},
                }
            ],
            "edges": [],
        }
    )
    assert "champs_etape" not in definition["nodes"][0]["data"]


def test_etape_complete_par_les_traces_du_tour_et_portee_par_la_requete():
    """Lot C de greffier-conversation : ce qu'un module a lu au tour même compte aussi, et la
    requête de conversation porte le souffle « étape complète » (avec l'état de la fiche)."""
    fiche = {
        "immatriculation": "AB-123-CD",
        "kilometrage": "120000",
        "communes_verifiees": [
            {
                "statut": "sure",
                "commune_retenue": {"nom": "Compiègne", "codes_postaux": ["60200"]},
            }
        ],
    }
    assert souffle_de_l_etape(_reglages(), fiche, ETAPE) == SOUFFLE_ETAPE_COMPLETE

    class Faux:
        async def get_chat_completions(self, context):
            return self.build_chat_completion_params({"messages": context})

        def build_chat_completion_params(self, p):
            return {"messages": list(p["messages"])}

    llm = Faux()
    montrer_la_fiche(llm, _reglages(), lambda: fiche, None, lambda: ETAPE)
    params = executer_sans_toucher_la_boucle_courante(
        llm.get_chat_completions([{"role": "user", "content": "voilà"}])
    )
    assert any("prends ta porte" in m["content"] for m in params["messages"])


def test_etape_complete_sans_porte_rien_n_est_souffle():
    """Revue du 13/10 : jamais « prends ta porte » dans une étape qui n'a pas de porte."""
    plein = {"immatriculation": "x", "kilometrage": "1", "commune_garage": "y"}
    assert souffle_de_l_etape(_reglages(), plein, ETAPE, a_des_portes=False) is None
    # Il manque encore quelque chose : « Encore attendu », porte ou non.
    assert "Encore attendu" in souffle_de_l_etape(_reglages(), {}, ETAPE, a_des_portes=False)
