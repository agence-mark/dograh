"""[.mark] Chantier agents-specialises, lot 17 : la fiche à plusieurs demandes.

Plan `Labo-agent-vocal/plans/agents-specialises/` (lot 17). Un appel peut porter deux demandes sur
deux objets différents : chaque champ a une portée (``appel`` = commun à tout l'appel, ``demande`` =
propre à une demande), et la demande en cours se clôt quand l'appel passe à un spécialisé qui n'est
pas le premier à travailler.

⛔ Aucun nom de champ, de motif ni de métier dans le code : les tests utilisent des noms neutres
(``objet``, ``detail``, ``nom``, ``telephone``).

| Test | Ce qu'il prouve |
|---|---|
| portée par défaut | calculée par les réglages génériques (lecteurs, nom, reconnaissance des champs), jamais par une liste de noms |
| portée à l'écran | la vraie route d'enregistrement garde la portée posée et laisse la vide vide |
| ouverture | passation vers un spécialisé = demande close, champs « demande » retirés, « appel » gardés ; retour et premier spécialisé : rien |
| deux demandes | par la vraie route du clavier : deux demandes sur deux objets, deux blocs justes, aucun écrasement |
| le modèle voit | l'état de la fiche montre la demande close en lecture, rien sans demande close |
| filet de fin d'appel | ne relit pas les champs des demandes closes |
| envoi | deux demandes = deux blocs ; une demande, ou un seul spécialisé = l'envoi d'avant, à l'octet |
| base et mail | l'après-appel écrit une demande par bloc et le mail les sépare |
| agent seul | aucune passation, aucune clé nouvelle |
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.db.bases_clients import connexion as schema
from api.schemas.apres_appel import ApresAppelAgent
from api.schemas.fiche_agent import NOMS_RESERVES, ChampFiche
from api.services.apres_appel.envoi import construire_envoi
from api.services.fiche.demandes import (
    CLE_DEMANDES,
    champs_hors_demandes_closes,
    ouvrir_une_demande,
    portee_effective,
    portee_par_defaut,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    ReglagesFiche,
    balayer_la_fiche,
    ecrire_dans_la_fiche,
    etat_de_la_fiche,
)
from api.tests.mark.test_apres_appel import (  # noqa: F401  (fixtures)
    _equipe,
    _executer_tout_de_suite,
    _organisation,
    _regler,
    base_v4,
    modele,
    smtp,
)
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_base_portail_chaine import _run_perso
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_passation_clavier import (
    _agent_de_l_organisation,
    _appel,
    _dit,
    _outil_de_passation,
    _principal,
    _republier,
    _session,
    _specialise,
    _texte,
    _vide,
)
from pipecat.tests import MockLLMService

PRINCIPAL = 100
S1 = 101
S2 = 102

CONFIG = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de la personne"},
        {"nom": "telephone", "origine": "dicte", "description": "Numéro de la personne"},
        {"nom": "objet", "origine": "dicte", "description": "Objet de la demande"},
        {"nom": "detail", "origine": "dicte", "description": "Détail de la demande"},
        {"nom": "motif", "origine": "dicte", "description": "Ce que la personne demande"},
    ],
}


def _reglages(config: dict | None = None) -> ReglagesFiche:
    reglages = ReglagesFiche.depuis(copy.deepcopy(config or CONFIG))
    assert reglages is not None
    return reglages


def _ecrire(fiche: dict, reglages: ReglagesFiche, **valeurs) -> None:
    for nom, valeur in valeurs.items():
        verdict = ecrire_dans_la_fiche(fiche, reglages, nom, valeur, paroles=[str(valeur)])
        assert verdict.statut == "ecrit", (nom, verdict)


def _passation(vers: int, *, de: int = PRINCIPAL, raison: str = "raison") -> dict:
    return {"de": de, "vers": vers, "raison": raison, "refusee": False, "issue": "completed"}


def _fiche_avec_un_specialiste() -> tuple[dict, ReglagesFiche]:
    """Un appel déjà passé par un premier spécialisé : nom, objet et détail notés."""
    reglages = _reglages()
    fiche: dict = {}
    _ecrire(fiche, reglages, nom="Lemaire", objet="premier", detail="a)")
    fiche["passations"] = [_passation(S1), _passation(PRINCIPAL, de=S1, raison="retour")]
    return fiche, reglages


# --------------------------------------------------------------------------- #
# 1. La portée
# --------------------------------------------------------------------------- #


def test_la_portee_par_defaut_vient_des_reglages_generiques_jamais_d_une_liste_de_noms():
    reglages = _reglages(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [
                {"nom": "nom"},
                {"nom": "telephone"},
                {"nom": "objet"},
                {"nom": "lieu", "lecteur": "commune"},
                {"nom": "voie", "lecteur": "rue"},
                # Les noms réglés pour l'agent (« Field recognition ») : un nom propre au client.
                {"nom": "joignable"},
                {"nom": "contact_courriel"},
                {"nom": "zone"},
            ],
            "variables_telephone": "telephone*, joignable",
            "variables_courriel": "contact_courriel",
            "variables_code_postal": "zone",
        }
    )
    par_nom = {c.nom: c for c in reglages.champs}
    motifs = reglages.motifs_des_types
    attendu = {
        "nom": "appel",
        "telephone": "appel",
        "lieu": "appel",
        "voie": "appel",
        "joignable": "appel",
        "contact_courriel": "appel",
        "zone": "appel",
        "objet": "demande",
    }
    assert {n: portee_par_defaut(c, motifs) for n, c in par_nom.items()} == attendu
    # Sans le réglage, « joignable » n'est rien de particulier : propre à la demande.
    sans = _reglages({"fiche_au_fil_de_leau": True, "fiche_champs": [{"nom": "joignable"}]})
    assert portee_par_defaut(sans.champs[0], sans.motifs_des_types) == "demande"


def test_une_portee_choisie_a_l_ecran_prime_dans_les_deux_sens():
    reglages = _reglages()
    motifs = reglages.motifs_des_types
    assert portee_effective(ChampFiche(nom="objet", portee="appel"), motifs) == "appel"
    assert portee_effective(ChampFiche(nom="telephone", portee="demande"), motifs) == "demande"
    assert portee_effective(ChampFiche(nom="telephone"), motifs) == "appel"
    assert ChampFiche(nom="objet").portee is None
    with pytest.raises(ValueError):
        ChampFiche(nom="objet", portee="autre")


def test_demandes_est_un_nom_reserve_de_la_fiche():
    assert "demandes" in NOMS_RESERVES


@pytest.mark.asyncio
async def test_la_route_d_enregistrement_garde_la_portee_posee_et_laisse_la_vide_vide(
    db_session, async_session, test_client_factory
):
    base = copy.deepcopy(FICHE)
    user, agent = await _monter(db_session, async_session, base, _principal())
    champs = [
        {"nom": "nom", "origine": "dicte"},
        {"nom": "objet", "origine": "dicte", "portee": "demande"},
        {"nom": "telephone", "origine": "dicte", "portee": "demande"},
        {"nom": "detail", "origine": "dicte"},
    ]
    async with test_client_factory(user) as client:
        reponse = await client.put(
            f"/api/v1/workflow/{agent.id}",
            json={
                "name": "Fiche",
                "workflow_definition": _principal(),
                "workflow_configurations": {
                    "fiche_au_fil_de_leau": True,
                    "fiche_champs": champs,
                },
            },
        )
        assert reponse.status_code == 200, reponse.text
    brouillon = await db_session.get_draft_version(agent.id)
    enregistres = {
        c["nom"]: c for c in brouillon.workflow_configurations["fiche_champs"]
    }
    # Posée à l'écran : gardée telle quelle, relue telle quelle.
    assert enregistres["objet"]["portee"] == "demande"
    assert enregistres["telephone"]["portee"] == "demande"
    # Vide : jamais remplacée par sa valeur calculée (même règle que ``lecteur``).
    assert enregistres["nom"].get("portee") is None
    assert enregistres["detail"].get("portee") is None
    # Et le moteur la lit : « telephone » posé « demande » est propre à la demande.
    reglages = ReglagesFiche.depuis(brouillon.workflow_configurations)
    portees = {c.nom: portee_effective(c, reglages.motifs_des_types) for c in reglages.champs}
    assert portees["telephone"] == "demande" and portees["nom"] == "appel", portees


# --------------------------------------------------------------------------- #
# 2. L'ouverture d'une demande
# --------------------------------------------------------------------------- #


def test_une_passation_vers_un_second_specialise_clot_la_demande_et_garde_l_appel():
    fiche, reglages = _fiche_avec_un_specialiste()
    _ecrire(fiche, reglages, telephone="0612345678")
    bloc = ouvrir_une_demande(
        fiche,
        reglages,
        vers_un_specialise=True,
        principal_id=PRINCIPAL,
        noms_des_agents={S1: "Premier"},
        champ_motif="motif",
    )
    assert bloc is not None
    assert fiche[CLE_DEMANDES] == [bloc]
    assert bloc["ordre"] == 1 and bloc["agent_id"] == S1 and bloc["agent"] == "Premier"
    assert bloc["champs"] == {"objet": "premier", "detail": "a)"}
    # Les champs « demande » quittent la vue à plat (valeur, variables extraites, état) ;
    # ceux de l'appel restent.
    for cle in ("objet", "detail"):
        assert cle not in fiche and cle not in fiche["extracted_variables"]
        assert cle not in fiche[CLE_ETAT]
    assert fiche["nom"] == "Lemaire" and fiche["telephone"] == "0612345678"
    assert fiche[CLE_ETAT]["nom"]["sure"] is True
    # La provenance suit le champ dans le bloc.
    assert bloc["etat"]["objet"]["source"] == "outil"


def test_ce_que_le_principal_note_apres_le_retour_va_a_la_nouvelle_demande():
    """Revue du 16/10 : la demande du spécialisé est photographiée au retour ; le principal qui
    qualifie la demande suivante (il réécrit ``objet``) n'écrase jamais la demande close."""
    from api.services.fiche.demandes import CLE_PHOTO, photographier_la_demande

    fiche, reglages = _fiche_avec_un_specialiste()
    photographier_la_demande(fiche, reglages)
    assert fiche[CLE_PHOTO] == {"objet": "premier", "detail": "a)"}
    fiche["objet"] = "second"  # le principal qualifie la demande suivante
    bloc = ouvrir_une_demande(fiche, reglages, vers_un_specialise=True, principal_id=PRINCIPAL)
    assert bloc["champs"] == {"objet": "premier", "detail": "a)"}
    assert fiche["objet"] == "second", "la valeur réécrite reste à la nouvelle demande"
    assert "detail" not in fiche and CLE_PHOTO not in fiche
    assert fiche["nom"] == "Lemaire"


def test_au_retour_au_principal_et_chez_le_premier_specialise_rien_n_est_clos():
    fiche, reglages = _fiche_avec_un_specialiste()
    avant = copy.deepcopy(fiche)
    # Retour au principal : la destination n'est pas un spécialisé.
    assert ouvrir_une_demande(
        fiche, reglages, vers_un_specialise=False, principal_id=PRINCIPAL
    ) is None
    assert fiche == avant
    # Premier spécialisé de l'appel (aucune passation avant) : la qualification du principal et
    # le travail du spécialisé ne font qu'une demande.
    neuf: dict = {}
    _ecrire(neuf, reglages, nom="Lemaire", objet="premier")
    avant_neuf = copy.deepcopy(neuf)
    assert ouvrir_une_demande(
        neuf, reglages, vers_un_specialise=True, principal_id=PRINCIPAL
    ) is None
    assert neuf == avant_neuf
    assert CLE_DEMANDES not in neuf
    # Rien de rempli côté « demande » : rien à clore.
    vide, _ = _fiche_avec_un_specialiste()
    for cle in ("objet", "detail"):
        vide.pop(cle)
        vide["extracted_variables"].pop(cle)
    assert ouvrir_une_demande(
        vide, reglages, vers_un_specialise=True, principal_id=PRINCIPAL
    ) is None
    assert CLE_DEMANDES not in vide


def test_les_cles_d_un_champ_de_commune_ou_de_date_suivent_leur_champ():
    reglages = _reglages(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [
                {"nom": "nom"},
                {"nom": "date_a", "lecteur": "aucun", "portee": "demande"},
                {"nom": "lieu_b", "lecteur": "commune", "portee": "demande"},
            ],
        }
    )
    fiche = {
        "nom": "X",
        "date_a": "2026-01-01",
        "date_a_dit": "l'an dernier",
        "lieu_b": "Creil",
        "lieu_b_insee": "60175",
        "extracted_variables": {},
        CLE_ETAT: {},
        "passations": [_passation(S1)],
    }
    bloc = ouvrir_une_demande(fiche, reglages, vers_un_specialise=True, principal_id=PRINCIPAL)
    assert bloc is not None
    assert "lieu_b" not in fiche and "lieu_b_insee" not in fiche
    assert bloc["champs"]["lieu_b_insee"] == "60175"
    assert fiche["nom"] == "X"


def test_un_agent_seul_ne_recoit_aucune_cle_nouvelle():
    reglages = _reglages()
    fiche: dict = {}
    _ecrire(fiche, reglages, nom="Lemaire", objet="premier")
    avant = copy.deepcopy(fiche)
    # Ni passation, ni spécialisé, ni fiche : rien ne bouge, jamais de levée.
    assert ouvrir_une_demande(fiche, reglages, vers_un_specialise=True, principal_id=None) is None
    assert ouvrir_une_demande(fiche, None, vers_un_specialise=True, principal_id=PRINCIPAL) is None
    assert fiche == avant and CLE_DEMANDES not in fiche
    assert champs_hors_demandes_closes(reglages, fiche) is reglages
    assert etat_de_la_fiche(reglages, fiche) == etat_de_la_fiche(reglages, avant)


# --------------------------------------------------------------------------- #
# 3. Ce que voit le modèle, le filet de fin d'appel
# --------------------------------------------------------------------------- #


def test_le_modele_voit_la_demande_close_en_lecture_et_rien_sans_demande_close():
    fiche, reglages = _fiche_avec_un_specialiste()
    sans_demande = etat_de_la_fiche(reglages, fiche)
    ouvrir_une_demande(
        fiche, reglages, vers_un_specialise=True, principal_id=PRINCIPAL, champ_motif="motif"
    )
    _ecrire(fiche, reglages, objet="second")
    etat = etat_de_la_fiche(reglages, fiche)
    assert "objet = « second »" in etat
    lignes = [ligne for ligne in etat.splitlines() if ligne.startswith("Demande déjà traitée")]
    assert len(lignes) == 1 and "objet = « premier »" in lignes[0] and "detail = « a) »" in lignes[0], etat
    assert "ne la redemande pas" in lignes[0]
    # La demande close n'est plus dans « Noté » : le spécialisé ne la prend pas pour la sienne.
    note = next(ligne for ligne in etat.splitlines() if ligne.startswith("Noté"))
    assert "premier" not in note
    # Sans demande close, l'état est celui d'avant, ligne pour ligne.
    assert "Demande déjà traitée" not in sans_demande


@pytest.mark.asyncio
async def test_le_filet_de_fin_d_appel_ne_relit_pas_les_champs_des_demandes_closes():
    fiche, reglages = _fiche_avec_un_specialiste()
    ouvrir_une_demande(fiche, reglages, vers_un_specialise=True, principal_id=PRINCIPAL)
    demandes_relues: list[list[str]] = []

    async def extraire(variables, consigne):
        demandes_relues.append([v.name for v in variables])
        return {}

    messages = [
        {"role": "user", "content": "premier a)"},
        {"role": "user", "content": "je m'appelle Lemaire"},
    ]
    await balayer_la_fiche(reglages, extraire, fiche, messages)
    relus = {n for liste in demandes_relues for n in liste}
    # Les champs « demande » (objet, détail, motif) ne sont pas relus dans toute la conversation.
    assert relus <= {"nom", "telephone"}, relus
    # Sans demande close : le filet relit tout ce qui est vide, comme avant.
    seule, regl = _fiche_avec_un_specialiste()
    for cle in ("objet", "detail"):
        seule.pop(cle)
        seule["extracted_variables"].pop(cle)
    demandes_relues.clear()
    await balayer_la_fiche(regl, extraire, seule, messages)
    relus = {n for liste in demandes_relues for n in liste}
    assert {"objet", "detail"} <= relus, relus


# --------------------------------------------------------------------------- #
# 4. Deux demandes sur deux objets, par la vraie route du clavier
# --------------------------------------------------------------------------- #

CHAMPS_GROUPE = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {"nom": "objet", "origine": "dicte", "description": "L'objet de la demande"},
        {"nom": "detail", "origine": "dicte", "description": "Le détail de la demande"},
        {"nom": "motif", "origine": "dicte", "description": "Ce que la personne demande"},
    ],
}


def _noter(arguments, identifiant):
    return MockLLMService.create_function_call_chunks(
        "noter_information", arguments, tool_call_id=identifiant
    )


async def _groupe_a_deux_specialises(db_session, async_session):
    base = copy.deepcopy(CHAMPS_GROUPE)
    user, principal = await _monter(db_session, async_session, base, _principal())
    organisation = principal.organization_id
    specialises = []
    outils = []
    for nom in ("S1", "S2"):
        specialise = await _agent_de_l_organisation(
            db_session,
            user,
            organisation,
            nom,
            _specialise(),
            {**base, "agent_principal_id": principal.id},
        )
        specialises.append(specialise)
        outils.append(
            await _outil_de_passation(
                db_session, user, organisation, f"Passer a {nom}", specialise.id
            )
        )
    await _republier(
        db_session,
        principal,
        _principal([o.tool_uuid for o in outils]),
        {**base, "agents_specialises": [s.id for s in specialises]},
    )
    return user, principal, specialises


@pytest.mark.asyncio
async def test_deux_demandes_sur_deux_objets_font_deux_blocs_sans_aucun_ecrasement(
    db_session, async_session, test_client_factory
):
    user, principal, (s1, s2) = await _groupe_a_deux_specialises(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            # Tour 1 : le principal note le nom et passe la main au premier spécialisé.
            _dit(_noter({"nom": "Lemaire"}, "n1"), [*_appel("passer_a_s1", "p1")]),
            _vide(),  # la fabrique
            _dit(_texte("De quel objet s'agit-il ?")),  # S1 ouvre
            # Tour 2 : S1 note SA demande, dit « autre chose ? » et rend la main.
            _vide(),
            _dit(
                _noter({"objet": "objet un", "detail": "premier détail", "motif": "motif un"}, "n2"),
                [*_texte("Autre chose ?"), *_appel("retour", "r1")],
            ),
            _vide(),  # la fabrique construit le principal
            # Tour 3 : le principal passe la main au second spécialisé (autre demande).
            _dit([*_appel("passer_a_s2", "p2")]),
            _vide(),  # la fabrique
            _dit(_texte("Quel est cet autre objet ?")),  # S2 ouvre
            # Tour 4 : S2 note SA demande.
            _vide(),
            _dit(
                _noter({"objet": "objet deux", "detail": "second détail", "motif": "motif deux"}, "n3"),
                _texte("C'est noté."),
            ),
        ],
        [
            "bonjour, je m'appelle Lemaire, j'ai une demande",
            "c'est pour l'objet un, premier détail, motif un",
            "oui, j'ai une autre demande",
            "c'est pour l'objet deux, second détail, motif deux",
        ],
    )
    apres_passation = reponses[2]["checkpoint"]["gathered_context"]
    # À la passation vers S2 : la demande de S1 est close, la fiche à plat repart vide côté demande.
    assert len(apres_passation[CLE_DEMANDES]) == 1, apres_passation
    assert apres_passation["nom"] == "Lemaire"
    assert "objet" not in apres_passation and "detail" not in apres_passation
    final = reponses[3]["checkpoint"]["gathered_context"]
    closes = final[CLE_DEMANDES]
    assert len(closes) == 1, closes
    assert closes[0]["agent_id"] == s1.id and closes[0]["ordre"] == 1
    assert closes[0]["champs"]["objet"] == "objet un", closes
    assert closes[0]["champs"]["detail"] == "premier détail"
    assert closes[0]["motif"] == "motif un"
    # La demande en cours (S2) n'a rien écrasé : sa valeur est la sienne, celle de S1 est intacte.
    assert final["objet"] == "objet deux" and final["detail"] == "second détail", final
    assert final["nom"] == "Lemaire"
    assert [e.get("vers") for e in final["passations"]] == [s1.id, principal.id, s2.id]


@pytest.mark.asyncio
async def test_un_appel_a_un_seul_specialise_ne_clot_rien_par_la_vraie_route(
    db_session, async_session, test_client_factory
):
    user, principal, _ = await _groupe_a_deux_specialises(db_session, async_session)
    reponses = await _session(
        test_client_factory,
        user,
        principal,
        [
            _vide(),
            _dit(
                _noter({"nom": "Lemaire", "motif": "motif un"}, "n1"),
                [*_appel("passer_a_s1", "p1")],
            ),
            _vide(),
            _dit(_texte("De quel objet s'agit-il ?")),
            _vide(),
            _dit(_noter({"objet": "objet un"}, "n2"), _texte("C'est noté.")),
        ],
        ["je m'appelle Lemaire, motif un", "c'est l'objet un"],
    )
    fiche = reponses[1]["checkpoint"]["gathered_context"]
    assert CLE_DEMANDES not in fiche, fiche
    assert fiche["objet"] == "objet un" and fiche["motif"] == "motif un" and fiche["nom"] == "Lemaire"


# --------------------------------------------------------------------------- #
# 5. L'envoi après l'appel
# --------------------------------------------------------------------------- #

DEBUT = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _run(gathered: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=900,
        workflow_id=PRINCIPAL,
        workflow=SimpleNamespace(name="Accueil"),
        definition_id=5,
        definition=SimpleNamespace(
            version_number=1,
            workflow_configurations={"fiche_champs": CONFIG["fiche_champs"]},
        ),
        initial_context={"caller_number": "+33612345678", "called_number": "+33100000000"},
        gathered_context=gathered,
        usage_info={"call_duration_seconds": 90.0},
        created_at=DEBUT,
        call_type="inbound",
        mode="twilio",
    )


def _fiche_a_deux_demandes() -> dict:
    reglages = _reglages()
    fiche: dict = {}
    _ecrire(fiche, reglages, nom="Lemaire", telephone="0612345678", objet="un", detail="d1", motif="m1")
    fiche["passations"] = [_passation(S1), _passation(PRINCIPAL, de=S1, raison="retour")]
    ouvrir_une_demande(
        fiche,
        reglages,
        vers_un_specialise=True,
        principal_id=PRINCIPAL,
        noms_des_agents={S1: "Premier"},
        champ_motif="motif",
    )
    fiche["passations"].append(_passation(S2))
    _ecrire(fiche, reglages, objet="deux", detail="d2", motif="m2")
    return fiche


def _envoi(gathered: dict) -> dict:
    return construire_envoi(
        _run(gathered), {"summary": {}, "latency": {}, "conversation": {}}, ApresAppelAgent(actif=True)
    )


def test_deux_demandes_donnent_deux_blocs_avec_les_champs_de_l_appel_dans_chacun():
    envoi = _envoi(_fiche_a_deux_demandes())
    blocs = envoi["demandes"]
    assert [b["ordre"] for b in blocs] == [1, 2]
    assert blocs[0]["agent_id"] == S1 and blocs[0]["agent"] == "Premier"
    assert blocs[1]["agent_id"] == S2 and blocs[1].get("courante") is True
    assert [b["motif"] for b in blocs] == ["m1", "m2"]

    def par_portee(bloc, portee):
        return {c["nom"]: c["valeur"] for c in bloc["champs"] if c["portee"] == portee}

    for bloc in blocs:
        assert par_portee(bloc, "appel") == {"nom": "Lemaire", "telephone": "0612345678"}
    assert par_portee(blocs[0], "demande") == {"objet": "un", "detail": "d1", "motif": "m1"}
    assert par_portee(blocs[1], "demande") == {"objet": "deux", "detail": "d2", "motif": "m2"}
    # Les motifs de l'appel : ceux de toutes les demandes, dans l'ordre ; le premier est « le motif ».
    assert envoi["motifs"] == ["m1", "m2"] and envoi["motif"] == "m1"
    # La vue à plat (lue par la synthèse, le SMS…) est celle de la fiche : appel + demande en cours.
    assert {c["nom"]: c["valeur"] for c in envoi["champs"]} == {
        "nom": "Lemaire",
        "telephone": "0612345678",
        "objet": "deux",
        "detail": "d2",
        "motif": "m2",
    }


def test_un_appel_a_une_demande_produit_l_envoi_d_avant_a_l_octet():
    reglages = _reglages()
    # L'appel d'avant : une fiche à plat, aucune clé de groupe.
    d_avant: dict = {}
    _ecrire(d_avant, reglages, nom="Lemaire", telephone="0612345678", objet="un", detail="d1", motif="m1")
    # Le même appel passé par UN spécialisé (et son retour) : aucune demande close.
    groupe = copy.deepcopy(d_avant)
    # À la passation vers S1 la trace est encore vide (le moteur l'écrit une fois la passation faite).
    assert ouvrir_une_demande(
        groupe, reglages, vers_un_specialise=True, principal_id=PRINCIPAL
    ) is None
    groupe["passations"] = [_passation(S1), _passation(PRINCIPAL, de=S1, raison="retour")]
    envoi_avant = _envoi(d_avant)
    envoi_groupe = _envoi(groupe)
    assert "demandes" not in envoi_avant and "demandes" not in envoi_groupe
    assert envoi_groupe == envoi_avant


def test_une_demande_close_sans_demande_en_cours_est_reversee_a_plat():
    """Un seul bloc : la demande unique de l'appel, ses champs reviennent à plat (rien perdu)."""
    reglages = _reglages()
    fiche: dict = {}
    _ecrire(fiche, reglages, nom="Lemaire", objet="un", detail="d1", motif="m1")
    attendu = _envoi(copy.deepcopy(fiche))
    fiche["passations"] = [_passation(S1), _passation(PRINCIPAL, de=S1, raison="retour")]
    ouvrir_une_demande(
        fiche, reglages, vers_un_specialise=True, principal_id=PRINCIPAL, champ_motif="motif"
    )
    envoi = _envoi(fiche)
    assert "demandes" not in envoi
    assert {c["nom"]: c["valeur"] for c in envoi["champs"]} == {
        c["nom"]: c["valeur"] for c in attendu["champs"]
    }
    assert envoi["motifs"] == ["m1"] and envoi["motif"] == "m1"


# --------------------------------------------------------------------------- #
# 6. La base du client, le mail : une demande par bloc
# --------------------------------------------------------------------------- #


async def test_l_apres_appel_ecrit_une_demande_par_bloc_et_le_mail_les_separe(
    base_v4, smtp, modele, db_session, async_session
):
    from api.tasks.workflow_completion import process_workflow_completion

    org = await _organisation(async_session, db_session)
    await _regler(db_session, org, base_v4, smtp)
    await _equipe(base_v4)
    fiche = _fiche_a_deux_demandes()
    run = await _run_perso(
        db_session,
        org,
        gathered={
            **fiche,
            "call_disposition": "rappel_demande",
        },
    )
    with patch("api.tasks.arq.enqueue_job", await _executer_tout_de_suite([])):
        await process_workflow_completion(None, run.id)
    bloc = await db_session.lire_apres_appel(run.id)
    assert bloc["etapes"]["ecriture"]["statut"] == "ok", bloc

    connexion = await schema.connecter(base_v4)
    try:
        appel = await connexion.fetchrow(
            "SELECT id, motif, demande_id FROM mark.appel WHERE dograh_run_id = $1", run.id
        )
        assert appel["motif"] == "m1"
        assert [
            r["motif"]
            for r in await connexion.fetch(
                "SELECT motif FROM mark.appel_motif WHERE appel_id = $1 ORDER BY ordre", appel["id"]
            )
        ] == ["m1", "m2"]
        demandes = await connexion.fetch(
            "SELECT ordre, demande_id, motif FROM mark.appel_demande WHERE appel_id = $1 ORDER BY ordre",
            appel["id"],
        )
        assert [(r["ordre"], r["motif"]) for r in demandes] == [(1, "m1"), (2, "m2")]
        # La demande en cours est celle de l'appel ; la demande close a sa propre ligne.
        assert demandes[1]["demande_id"] == appel["demande_id"]
        assert demandes[0]["demande_id"] != appel["demande_id"]
        propres = await connexion.fetch(
            "SELECT nom, valeur FROM mark.champ_demande WHERE demande_id = $1 ORDER BY nom",
            demandes[0]["demande_id"],
        )
        # Seulement les champs de la demande close ; ceux de l'appel restent dans champ_appel.
        assert [(r["nom"], r["valeur"]) for r in propres] == [
            ("detail", "d1"),
            ("motif", "m1"),
            ("objet", "un"),
        ]
        du_plat = {
            r["nom"]: r["valeur"]
            for r in await connexion.fetch(
                "SELECT nom, valeur FROM mark.champ_appel WHERE appel_id = $1", appel["id"]
            )
        }
        assert du_plat == {
            "nom": "Lemaire",
            "telephone": "0612345678",
            "objet": "deux",
            "detail": "d2",
            "motif": "m2",
        }
        assert await connexion.fetchval(
            "SELECT count(*) FROM mark.demande WHERE contact_id = (SELECT contact_id FROM mark.appel WHERE id = $1)",
            appel["id"],
        ) == 2
    finally:
        await connexion.close()
    # Un seul mail, avec un bloc par demande : les champs de l'appel une fois, puis chaque demande.
    assert len(smtp.messages) == 1
    assert smtp.sujets() == ["Nouvelles demandes : m1 ; m2"]
    texte = smtp.textes()[0]
    assert "Demande 1 (Premier) : m1" in texte and "Demande 2 : m2" in texte, texte
    fiche_du_mail = texte.split("Fiche :", 1)[1]
    assert fiche_du_mail.count("- nom : Lemaire") == 1
    assert fiche_du_mail.index("- objet : un") < fiche_du_mail.index("Demande 2")
    assert fiche_du_mail.index("- objet : deux") > fiche_du_mail.index("Demande 2")


async def test_un_envoi_sans_demandes_n_ecrit_rien_de_plus_dans_la_base(base_v4):
    from api.db.bases_clients import apres_appel as sql
    from api.tests.mark.test_apres_appel import _envoi as envoi_simple

    connexion = await schema.connecter(base_v4)
    try:
        await sql.recevoir_appel(connexion, envoi_simple(77))
        assert await connexion.fetchval("SELECT count(*) FROM mark.appel_demande") == 0
        assert await connexion.fetchval("SELECT count(*) FROM mark.champ_demande") == 0
        assert await connexion.fetchval("SELECT count(*) FROM mark.demande") == 1
    finally:
        await connexion.close()


def test_aucun_nom_de_champ_ni_de_metier_dans_le_code_du_lot():
    """Evan : standard pour tout client, tout secteur, tout métier."""
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    interdits = ("appareil", "marque", "panne", "entretien", "poêle", "poele", "chaudière", "devis")
    for chemin in (
        racine / "services" / "fiche" / "demandes.py",
        racine / "db" / "bases_clients" / "migrations" / "016-fiche-a-plusieurs-demandes.sql",
    ):
        texte = chemin.read_text(encoding="utf-8").lower()
        trouves = [mot for mot in interdits if mot in texte]
        assert not trouves, (chemin.name, trouves)

