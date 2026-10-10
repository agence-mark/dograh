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
"""

from api.services.workflow.dto import AgentNodeData, sanitize_workflow_definition
from api.services.workflow.fiche_au_fil_de_leau import (
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


def test_les_deux_prochains_manquants_dans_l_ordre_de_l_etape():
    souffle = souffle_de_l_etape(_reglages(), {"motif": "vidange"}, ETAPE)
    assert "immatriculation, puis kilometrage" in souffle
    assert "commune garage" not in souffle and "suggestion" in souffle


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


def test_rien_case_eteinte_sans_etiquettes_ou_rien_qui_manque():
    assert souffle_de_l_etape(_reglages(allume=False), {}, ETAPE) is None
    assert souffle_de_l_etape(_reglages(), {}, ()) is None
    plein = {"immatriculation": "x", "kilometrage": "1", "commune_garage": "y"}
    assert souffle_de_l_etape(_reglages(), plein, ETAPE) is None
    # Un nom qui n'est pas un champ de la fiche est ignoré, jamais soufflé.
    assert souffle_de_l_etape(_reglages(), plein, ("inconnu",)) is None


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
        "immatriculation, puis kilometrage" in m["content"] for m in params["messages"]
    )
    etape["champs"] = ()
    params = executer_sans_toucher_la_boucle_courante(
        llm.get_chat_completions([{"role": "user", "content": "bonjour"}])
    )
    assert not any("Il manque encore" in m["content"] for m in params["messages"])
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
