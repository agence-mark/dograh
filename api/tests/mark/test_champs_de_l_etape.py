"""[.mark] Chantier fiabilite-orchestration, lot 2 : la liste des champs de l'étape (F9, F19, C3, C4).

| Test | La garantie |
|---|---|
| deux lignes | « Encore attendu » puis « Déjà connu », même forme, complément exact sur la liste de l'étape |
| une seule case | l'une ou l'autre clé allume les deux lignes (F19) ; aucune : rien |
| rempli par l'outil | un champ qu'un outil remplit n'est jamais « attendu » de l'appelant, ni retenu par la garde |
| garde | un outil de l'étape refuse tant que la liste n'est pas complète, puis s'exécute ; sans liste, case éteinte, agent du fond : rien ne change |
| confier gardé | « confier » rend « incomplet » sans lancer de travail quand la liste manque (run 1468) |
"""

import asyncio
from types import SimpleNamespace

import pytest

from api.services.travail.reglages import NOM_OUTIL
from api.services.workflow.enveloppe_des_actions import (
    envelopper_l_action,
    garde_de_l_etape,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CONSIGNE_DES_SUGGESTIONS,
    ReglagesFiche,
    etat_avec_les_indices,
)
from api.tests.mark.test_travail_de_fond import (
    DEMANDE,
    RESULTAT,
    Appel,
    _appel_d_outil,
    _texte,
)

CHAMPS = [
    {"nom": "nom", "type": "string", "origine": "dicte"},
    {"nom": "numero_dicte", "type": "string", "origine": "dicte"},
    {"nom": "adresse_intervention", "type": "string", "origine": "dicte"},
    {
        "nom": "rendez_vous",
        "type": "string",
        "origine": "deduit",
        "valeurs": ["confirme"],
        "rempli_par_outil": "poser_rendez_vous",
    },
]
ETAPE = ("nom", "numero_dicte", "adresse_intervention", "rendez_vous")


def _reglages(**cles):
    return ReglagesFiche.depuis(
        {"fiche_au_fil_de_leau": True, "fiche_champs": CHAMPS, "fiche_mode_de_note": "greffier", **cles}
    )


def test_encore_attendu_puis_deja_connu_complement_exact():
    reglages = _reglages(fiche_deja_connu=True)
    texte = etat_avec_les_indices(reglages, {"nom": "Durand"}, None, [], ETAPE)
    lignes = texte.splitlines()
    i = next(n for n, ligne in enumerate(lignes) if ligne.startswith("Encore attendu : "))
    assert lignes[i] == "Encore attendu : numero dicte, adresse intervention."
    assert lignes[i + 1] == "Déjà connu : nom."
    assert "Durand" not in lignes[i] + lignes[i + 1]  # jamais la valeur
    assert "suggestion" not in texte  # C4 : écrite une fois dans le prompt de l'étape
    assert "suggestions" in CONSIGNE_DES_SUGGESTIONS


def test_une_seule_case_allume_les_deux_lignes():
    for cles in ({"fiche_deja_connu": True}, {"etiquettes_des_etapes": True}):
        reglages = _reglages(**cles)
        assert reglages.etiquettes is True and reglages.deja_connu is True
    reglages = _reglages()
    assert reglages.etiquettes is False and reglages.deja_connu is False
    assert etat_avec_les_indices(reglages, {"nom": "Durand"}, None, [], ETAPE) is None or (
        "Encore attendu" not in etat_avec_les_indices(reglages, {"nom": "Durand"}, None, [], ETAPE)
    )


def _moteur(fiche, reglages, champs_etape):
    return (
        SimpleNamespace(_fiche=reglages, _gathered_context=fiche),
        SimpleNamespace(current_node=SimpleNamespace(champs_etape=champs_etape)),
    )


def test_la_garde_refuse_puis_accepte_et_ignore_le_champ_de_l_outil():
    reglages = _reglages(fiche_deja_connu=True)
    fiche = {"nom": "Durand"}
    moteur, agent = _moteur(fiche, reglages, ETAPE)
    assert garde_de_l_etape(moteur, agent) == {
        "statut": "incomplet",
        "manque": ["numero dicte", "adresse intervention"],
    }
    fiche.update(numero_dicte="0612345678", adresse_intervention="3 rue Haute")
    # rendez_vous est rempli par l'outil lui-même : jamais attendu.
    assert garde_de_l_etape(moteur, agent) is None


def test_sans_liste_case_eteinte_ou_agent_du_fond_rien_ne_change():
    moteur, agent = _moteur({}, _reglages(fiche_deja_connu=True), ())
    assert garde_de_l_etape(moteur, agent) is None
    moteur, agent = _moteur({}, _reglages(), ETAPE)
    assert garde_de_l_etape(moteur, agent) is None
    moteur, _ = _moteur({}, _reglages(fiche_deja_connu=True), ETAPE)
    assert garde_de_l_etape(moteur, SimpleNamespace(current_node=None)) is None
    assert garde_de_l_etape(SimpleNamespace(_fiche=None, _gathered_context={}), agent) is None


@pytest.mark.asyncio
async def test_l_outil_garde_ne_s_execute_pas_puis_s_execute():
    fiche = {"nom": "Durand"}
    moteur, agent = _moteur(fiche, _reglages(fiche_deja_connu=True), ETAPE)
    executions, rendus = [], []

    async def action(params):
        executions.append(1)
        await params.result_callback({"statut": "confirme"})

    async def rendre(resultat, **_):
        rendus.append(resultat)

    enveloppe = envelopper_l_action(moteur, "poser_rendez_vous", action, agent)
    await enveloppe(SimpleNamespace(result_callback=rendre, arguments={}))
    assert executions == [] and rendus[0]["statut"] == "incomplet"
    assert "rendez_vous" not in fiche
    fiche.update(numero_dicte="0612345678", adresse_intervention="3 rue Haute")
    await enveloppe(SimpleNamespace(result_callback=rendre, arguments={}))
    assert executions == [1] and rendus[1] == {"statut": "confirme"}
    assert fiche["rendez_vous"] == "confirme"
    # Une action qui peut transférer l'appel n'est jamais gardée.
    fiche.pop("numero_dicte")
    sans_garde = envelopper_l_action(moteur, "equipe", action, agent, garde=False)
    await sans_garde(SimpleNamespace(result_callback=rendre, arguments={}))
    assert executions == [1, 1]


@pytest.fixture
async def appel():
    a = Appel()
    try:
        yield a
    finally:
        await a.arreter()


@pytest.mark.asyncio
async def test_confier_est_garde_par_la_liste_de_l_etape(appel):
    """Run 1468 : « confier » lancé avec « nom et adresse à venir ». La liste de l'étape manque :
    l'outil rend « incomplet », aucun travail ne part, le modèle reparle pour demander."""
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte("Quel est votre nom ?"),
        ],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    moteur = appel.engine
    moteur._fiche = _reglages(fiche_deja_connu=True)
    moteur.active_agent.workflow.nodes["start"].champs_etape = ("nom",)
    await appel.ouvrir()
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 2)
    await asyncio.sleep(0.2)
    assert appel.travaux() == []
    outils = [m for m in appel.messages() if m.get("role") == "tool"]
    assert outils and "incomplet" in outils[0]["content"]
