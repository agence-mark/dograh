"""[.mark] Les portes du Post-scriptum après la mesure au clavier (chantier postscriptum-et-communes, lot 3).

La question de ce fichier :

    Les trois défauts de portes vus sur Qwen3 235B et Mistral Large (runs 1089 à 1104) sont-ils
    fermés par le code, sans rien changer hors du Post-scriptum ?

| Test | Constat | Correctif |
|---|---|---|
| la liste des portes n'a plus de flèche | les modèles recopiaient « → <étape> » (8 runs sur 16) | Q1 |
| une porte inconnue sans phrase fait reparler le modèle, une fois | run 1089 : deux tours muets | Q3 |
| une porte écrite en fin de phrase n'est pas dite et est prise | run 1089 : « … enregistrés. → panne_decrite » lu | Q4 |
| une flèche suivie d'autre chose qu'un nom reste dite | revue du 05/10 (« Du salon → à la cuisine ? ») | Q4 |
| une flèche dans la note n'est jamais une porte | une valeur JSON peut porter une flèche | Q4 |

Le moteur est le témoin de ``test_porte_parlee_processeur.py`` ; aucun mot de métier (preuve : un garage).
"""

from types import SimpleNamespace

import pytest

from api.services.workflow.porte_parlee import consigne_des_portes
from api.tests.mark.test_porte_parlee_processeur import PORTES, _MontagePortes, _Moteur


class _MoteurQuiRelance(_Moteur):
    def __init__(self):
        super().__init__()
        self.relances = 0

    def est_une_porte_de_l_etape(self, nom):
        return nom in PORTES

    async def relancer_une_reponse_muette(self):
        self.relances += 1
        return self.relances == 1


def _montage_qui_relance() -> _MontagePortes:
    montage = _MontagePortes()
    moteur = _MoteurQuiRelance()
    montage.moteur = moteur
    montage.processeur._portes = moteur
    montage.processeur._moteur = moteur
    return montage


# --- Q1 ----------------------------------------------------------------------


def test_la_liste_des_portes_n_a_plus_de_fleche():
    """Un garage : la porte « vehicule_decrit » mène à l'étape « coordonnees »."""
    arete = SimpleNamespace(
        get_function_name=lambda: "vehicule_decrit", target="2", condition="Quand la plaque est notée."
    )
    noeud = SimpleNamespace(out_edges=[arete])
    graphe = SimpleNamespace(nodes={"2": SimpleNamespace(name="coordonnees", premiere_replique="Votre nom ?")})
    bloc = consigne_des_portes(noeud, graphe, lambda texte: texte)
    assert "- vehicule_decrit (vers l'étape coordonnees) : Quand la plaque est notée." in bloc
    liste = bloc.split("# Les portes de cette étape", 1)[1].split("# La première réplique", 1)[0]
    lignes = [l for l in liste.splitlines() if l.startswith("- ")]
    assert lignes and all("→" not in l for l in lignes), lignes


# --- Q3 ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_une_porte_inconnue_sans_phrase_fait_reparler_le_modele_une_fois():
    montage = _montage_qui_relance()
    ordre = await montage.reponse("→ coordonnees\n|||\n{}")
    assert ordre.dit.strip() == ""
    assert montage.traces[-1]["porte_etat"] == "inconnue"
    assert montage.traces[-1].get("relance_muette") is True
    assert montage.moteur.relances == 1


@pytest.mark.asyncio
async def test_une_porte_inconnue_avec_phrase_ne_relance_pas():
    montage = _montage_qui_relance()
    ordre = await montage.reponse("→ coordonnees\nVotre nom ?|||{}")
    assert ordre.dit.strip() == "Votre nom ?"
    assert montage.moteur.relances == 0


# --- Q4 ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["C'est noté. → vers_panne"],
        ["C'est noté. → vers_", "panne"],
        ["C'est noté. → « vers_panne »|||", '{"motif": "panne"}'],
    ],
    ids=["entiere", "coupee", "avant-le-separateur"],
)
async def test_une_porte_en_fin_de_phrase_n_est_pas_dite_et_est_prise(morceaux):
    montage = _MontagePortes()
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "C'est noté."
    assert "→" not in ordre.dit and "vers_panne" not in ordre.dit
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]


@pytest.mark.asyncio
async def test_une_fleche_suivie_d_une_phrase_reste_dite():
    montage = _MontagePortes()
    ordre = await montage.reponse("Du salon → à la cuisine ?|||", '{"motif": "pose"}')
    assert ordre.dit == "Du salon → à la cuisine ?"
    assert montage.moteur.prises == []
    assert montage.traces[-1]["champs"] == ["motif"]


@pytest.mark.asyncio
async def test_une_fleche_dans_la_note_n_est_jamais_une_porte():
    montage = _MontagePortes()
    ordre = await montage.reponse("Quelle plaque ?|||", '{"autre": "garage → atelier"}')
    assert ordre.dit.strip() == "Quelle plaque ?"
    assert montage.moteur.prises == []
    # La note est lue entière, flèche comprise (la fiche de ce banc refuse ensuite le champ).
    assert montage.traces[-1]["champs"] == ["autre"]
    assert montage.fiche["fiche_journal"][-1]["valeur"] == "garage → atelier"


# --- Revue du 11/10 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_une_fleche_suivie_d_un_mot_qui_n_est_pas_une_porte_reste_dite():
    """« lundi → mardi. » : « mardi » n'est pas une porte de l'étape, il est dit."""
    montage = _montage_qui_relance()
    ordre = await montage.reponse("Plutôt lundi → mardi|||{}")
    assert ordre.dit == "Plutôt lundi → mardi"
    assert montage.moteur.prises == []


@pytest.mark.asyncio
async def test_prose_et_porte_dans_la_meme_reponse_une_seule_relance():
    """Revue du 11/10 : B6 ne relance pas quand une porte est écrite ; la porte fait reparler."""
    montage = _montage_qui_relance()
    ordre = await montage.reponse("→ vers_panne\nJe note votre nom.")
    assert ordre.dit.strip() == ""
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.moteur.prises[0]["relancer"] is True
    assert montage.moteur.relances == 0


@pytest.mark.asyncio
async def test_une_prose_qui_part_faute_de_relance_ne_dit_jamais_de_json():
    """Revue du 11/10 : relance déjà faite à ce tour, la prose part, son JSON jamais."""
    montage = _montage_qui_relance()
    montage.moteur.relances = 1  # la garde de C3 est déjà prise à ce tour
    ordre = await montage.reponse('Je note : {"nom": "Dupont"}')
    assert "{" not in ordre.dit and "Dupont\"" not in ordre.dit, ordre.dit


@pytest.mark.asyncio
async def test_une_fleche_dans_la_note_du_meme_morceau_n_est_jamais_une_porte():
    """Revue du 11/10 (point 5) : séparateur et note dans le même morceau que la flèche."""
    montage = _montage_qui_relance()
    ordre = await montage.reponse('Quelle plaque ?|||{"autre": "a → vers_panne"}')
    assert ordre.dit.strip() == "Quelle plaque ?"
    assert montage.moteur.prises == []
    assert montage.traces[-1]["champs"] == ["autre"]
