"""[.mark] C3, C3 bis, C5 : ce que la fiche accepte, décidé le 29/09 (formulaire d'Evan).

Chantier correctifs-banc-34, plan `Labo-agent-vocal/plans/correctifs-banc-34/`, décisions
D-C3 (remplacée), D-C3bis, D-C5. Chaque cas vient d'un appel réel du banc (runs 861 à 895).

| Test | Décision | Run |
|---|---|---|
| une phrase recollée de deux répliques est refusée | D-C5 | 883 |
| la même phrase dite en une réplique est acceptée | D-C5 (témoin) | 883 |
| moins de 4 mots : règle d'avant (mots dits à des moments différents) | D-C5 (témoin) | — |
| la passe de fin n'écrit jamais un champ DICTÉ à liste | D-C3 | 881, 893 |
| l'outil, lui, l'écrit au moment de la réponse | D-C3 (témoin) | 884 |
| un DÉDUIT à liste (l'urgence) reste écrit par la passe | D-C3 (témoin, zéro perte) | 882, 889… |
| une phrase déduite, morceau d'un seul tenant d'un champ dicté, est une recopie | D-C3bis | 883, 892 |
| entre deux déduits, entre deux dictés : deux vraies valeurs | D-C3bis (témoins, resserrée au rejeu) | 875, 884 |
| 3 mots contenus ailleurs : pas une recopie (« poêle à granulés » dans le motif) | D-C3bis (témoin, PB1 du 25/09) | — |
"""

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    ReglagesFiche,
    balayer_la_fiche,
)
from api.tests.mark.test_fiche_correctifs_modules import Appel, _reglages

VERBATIM = {"nom": "verbatim_demande", "origine": "dicte", "description": "La demande, mot pour mot."}
APPELANT = {"nom": "appelant", "origine": "dicte", "description": "Qui appelle."}
CONDUIT = {"nom": "conduit_existant", "origine": "dicte", "valeurs": ["oui", "non"]}
URGENCE = {"nom": "degre_urgence", "origine": "deduit", "valeurs": ["danger", "panne", "normal"]}
SYMPTOME = {"nom": "symptome", "origine": "deduit", "cumulatif": True}
APPAREIL = {"nom": "appareil", "origine": "deduit"}
MOTIF = {"nom": "motif", "origine": "deduit", "cumulatif": True}


class Extracteur:
    def __init__(self, reponse: dict):
        self.reponse = reponse

    async def __call__(self, variables, consigne):
        return dict(self.reponse)


def _messages(*paroles: str) -> list[dict]:
    return [{"role": "user", "content": p} for p in paroles]


def _refus(fiche: dict, champ: str) -> str | None:
    return next(
        (e["raison"] for e in fiche.get(CLE_JOURNAL) or [] if e["champ"] == champ and e["statut"] == "refuse"),
        None,
    )


def _fiche(*champs: dict) -> ReglagesFiche:
    return ReglagesFiche.depuis({"fiche_au_fil_de_leau": True, "fiche_champs": list(champs)})


# --- D-C5 : une phrase se dit dans UNE réplique --------------------------------------


@pytest.mark.asyncio
async def test_C5_run_883_une_phrase_recollee_de_deux_repliques_est_refusee():
    appel = Appel(_reglages(VERBATIM))
    appel.dit("Oui bonjour, j'aimerais faire entretenir mon pour la brosse s'il vous plaît.")
    appel.dit("C'est un poêle à bois de la marque Jotule.")
    resultat = await appel.note(
        verbatim_demande="j'aimerais faire entretenir mon poêle pour la brosse s'il vous plaît"
    )
    assert "verbatim_demande" not in appel.fiche, resultat
    assert resultat["refuses"] == [{"champ": "verbatim_demande", "raison": "non_dit"}]


@pytest.mark.asyncio
async def test_C5_la_meme_phrase_dite_en_une_replique_est_acceptee():
    appel = Appel(_reglages(VERBATIM))
    appel.dit("bonjour")
    appel.dit("j'aimerais faire entretenir mon poêle pour la brosse s'il vous plaît")
    await appel.note(verbatim_demande="J'aimerais faire entretenir mon poêle, pour la brosse")
    assert appel.fiche["verbatim_demande"] == "J'aimerais faire entretenir mon poêle, pour la brosse"


@pytest.mark.asyncio
async def test_C5_moins_de_quatre_mots_regle_d_avant():
    appel = Appel(_reglages(APPELANT))
    appel.dit("j'appelle pour mon père")
    appel.dit("il s'appelle Duchesne, c'est son fils qui parle")
    await appel.note(appelant="père fils Duchesne")
    assert appel.fiche["appelant"] == "père fils Duchesne"


# --- D-C3 : la passe de fin et les champs à liste ------------------------------------


@pytest.mark.asyncio
async def test_C3_runs_881_893_la_passe_n_ecrit_jamais_un_dicte_a_liste():
    fiche: dict = {}
    ecrits = await balayer_la_fiche(
        _fiche(CONDUIT, URGENCE),
        Extracteur({"conduit_existant": "oui", "degre_urgence": "panne"}),
        fiche,
        _messages("je voudrais parler à quelqu'un", "oui", "mon poêle fait un claquement au démarrage"),
    )
    assert "conduit_existant" not in fiche and "conduit_existant" not in ecrits
    assert _refus(fiche, "conduit_existant") == "dicte_a_liste_hors_outil"
    # Zéro perte : l'urgence, déduite, reste écrite (runs 882, 889, 891, 893…).
    assert fiche["degre_urgence"] == "panne"


@pytest.mark.asyncio
async def test_C3_l_outil_ecrit_toujours_un_dicte_a_liste_au_moment_de_la_reponse():
    appel = Appel(_reglages(CONDUIT))
    appel.dit("non", agent_avant="Avez-vous déjà un conduit de cheminée ?")
    await appel.note(conduit_existant="non")
    assert appel.fiche["conduit_existant"] == "non"


# --- D-C3bis : la recopie d'une phrase déjà notée ailleurs ----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verbatim, symptome",
    [
        (  # run 883
            "j'aimerais faire entretenir mon poêle pour la brosse s'il vous plaît",
            "j'aimerais faire entretenir mon poêle pour la brosse",
        ),
        (  # run 892
            "j'aimerais faire ramoner mon poêle à brousse et je ne comprends pas le montant de la TVA",
            "j'aimerais faire ramoner mon poêle à brousse",
        ),
    ],
)
async def test_C3bis_une_phrase_deja_dans_un_autre_champ_est_une_recopie(verbatim, symptome):
    fiche = {"verbatim_demande": verbatim}
    ecrits = await balayer_la_fiche(
        _fiche(VERBATIM, SYMPTOME), Extracteur({"symptome": symptome}), fiche, _messages(verbatim)
    )
    assert "symptome" not in fiche and ecrits == {}
    assert _refus(fiche, "symptome") == "recopie_de_verbatim_demande"


@pytest.mark.asyncio
async def test_C3bis_trois_mots_contenus_ailleurs_ne_sont_pas_une_recopie():
    fiche = {"motif": "Panne sur un poêle à granulés"}
    await balayer_la_fiche(
        _fiche(MOTIF, APPAREIL),
        Extracteur({"appareil": "poêle à granulés"}),
        fiche,
        _messages("mon poêle à granulés est en panne"),
    )
    assert fiche["appareil"] == "poêle à granulés"


@pytest.mark.asyncio
async def test_C3bis_run_875_un_deduit_contenu_dans_un_autre_deduit_reste():
    """Resserrée au rejeu : le motif, contenu dans le symptôme, est une vraie valeur."""
    fiche = {"symptome": "de la fumée qui sort du poêle à l'allumage depuis trois jours, puis ça va"}
    await balayer_la_fiche(
        _fiche(SYMPTOME, MOTIF),
        Extracteur({"motif": "de la fumée qui sort du poêle à l'allumage depuis trois jours"}),
        fiche,
        _messages("j'ai de la fumée qui sort de mon poêle quand je l'allume", "depuis trois jours"),
    )
    assert fiche["motif"] == "de la fumée qui sort du poêle à l'allumage depuis trois jours"


@pytest.mark.asyncio
async def test_C3bis_run_884_un_dicte_contenu_dans_un_autre_dicte_reste():
    """Resserrée au rejeu : qui appelle, contenu dans la demande, est une vraie valeur."""
    verbatim = "j'appelle pour mon père. Il voudrait installer un poêle à granulés"
    fiche = {"verbatim_demande": verbatim}
    await balayer_la_fiche(
        _fiche(VERBATIM, APPELANT),
        Extracteur({"appelant": "j'appelle pour mon père"}),
        fiche,
        _messages(verbatim),
    )
    assert fiche["appelant"] == "j'appelle pour mon père"
