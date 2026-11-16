"""[.mark] Manque M40 : l'étape 7 de « Nouveau client » n'affiche plus la fiche du portail, elle la remet à l'écran pour qu'il l'envoie.

| Test | Ce qu'il prouve |
|---|---|
| profil | les cases de l'étape (type d'entreprise, canaux) et les établissements de l'étape 3 deviennent ce que le portail reçoit (``portail``) ; sans case : standard, téléphone, un seul lieu |
| module | le type « restauration » allume le module de la base du client ; « autre » n'y touche pas ; un module qui ne s'allume pas n'arrête pas l'étape (avertissement) |
| rien de secret rangé | la clé n'est jamais dans ce que l'étape range ; seuls le type et les canaux le sont (pour « Reprendre ») |
| renvoi | « Relancer l'envoi » régénère la clé (une seule active, l'ancienne révoquée), relit type et canaux retenus, ne les redemande pas |
| garde | pas de renvoi avant la clé (étape 7), ni par une clé d'API ; la route est au registre sous ``clients.creer`` |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.installation_client import executants, moteur
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_installation_client import _Faux, _client, _contexte, _installation
from api.tests.mark.test_sous_dossiers_et_groupe import autre_org, org  # noqa: F401


@pytest.fixture
def sans_base(monkeypatch):
    from api.services.base_client import rattachement

    async def aucune(organization_id):
        return None

    monkeypatch.setattr(rattachement, "nom_de_la_base", aucune)


@pytest.fixture
def module(monkeypatch):
    """Le geste « allumer le module » enregistré : ce qu'il a reçu, et s'il s'allume."""
    from api.routes import restauration_ecran as routes

    etat = SimpleNamespace(appels=[], actif=True)

    async def put_module(corps, user):
        etat.appels.append(corps.actif)
        return SimpleNamespace(actif=etat.actif)

    monkeypatch.setattr(routes, "put_module", put_module)
    return etat


def _avec_lieux(installation, lieux):
    """L'installation telle que l'étape 3 l'a laissée."""
    for e in installation["etapes"]:
        if e["numero"] == 3:
            e["etat"], e["resultat"] = "faite", {"etablissements": lieux}
    return installation


async def _jouer_jusqu_a_7(db_session, org, monkeypatch, lieux=("siege",)):
    """Joue les étapes 2 à 6 avec de faux exécutants (l'étape 3 laisse ses établissements)."""
    user = _client(org)
    await _installation(db_session, org)
    for n in range(2, 7):
        resultat = {"workflow_id": org.agent.id} if n == 6 else {"etablissements": list(lieux)} if n == 3 else {"fait": True}
        monkeypatch.setitem(executants.EXECUTANTS, n, _Faux(resultat=resultat))
        await moteur.executer(user, org.organisation.id, n, {})
    return user


def test_les_cases_cochees_deviennent_le_canal_du_portail():
    assert executants._canaux_du_portail(["telephone"]) == "telephone"
    assert executants._canaux_du_portail(["site"]) == "site"
    assert executants._canaux_du_portail(["site", "telephone"]) == "les_deux"
    assert executants._canaux_du_portail([]) == "telephone"
    assert executants._canaux_du_portail(None) == "telephone"
    assert executants._canaux_du_portail(["fax", "site"]) == "site"


async def test_le_portail_recoit_le_type_les_canaux_et_le_montage_de_l_etape_3(org, db_session, sans_base, module):
    installation = _avec_lieux(await _installation(db_session, org, "Casa Italia"), ["centre", "gare"])
    sortie = await executants.cle_portail(
        _contexte(org, installation, {"type_entreprise": "restauration", "canaux": ["telephone", "site"]})
    )
    assert sortie.montre["portail"] == {"nom": "Casa Italia", "montage": "plusieurs", "canaux": "les_deux", "metier": "restauration"}
    assert sortie.montre["fiche_portail"]["nom"] == "Casa Italia"
    assert module.appels == [True]
    assert sortie.resultat["module_restauration"] is True
    assert sortie.resultat["type_entreprise"] == "restauration" and sortie.resultat["canaux"] == "les_deux"
    # Rien de secret n'est rangé : la clé n'est que dans ``montre``.
    assert sortie.montre["fiche_portail"]["cle_api"]["valeur"] not in str(sortie.resultat)


async def test_sans_case_cochee_le_client_est_standard_au_telephone_dans_un_seul_lieu(org, db_session, sans_base, module):
    installation = await _installation(db_session, org, "Plomberie Garnier")
    sortie = await executants.cle_portail(_contexte(org, installation, {}))
    assert sortie.montre["portail"] == {"nom": "Plomberie Garnier", "montage": "un", "canaux": "telephone", "metier": "standard"}
    assert module.appels == []  # « autre » n'allume rien
    assert "module_restauration" not in sortie.resultat


async def test_un_module_qui_ne_s_allume_pas_n_arrete_pas_l_etape(org, db_session, sans_base, module):
    module.actif = False
    installation = await _installation(db_session, org)
    sortie = await executants.cle_portail(_contexte(org, installation, {"type_entreprise": "restauration"}))
    assert sortie.resultat["module_restauration"] is False and sortie.resultat["avertissement"] == "module_refuse"
    assert sortie.montre["portail"]["metier"] == "restauration"  # la fiche part quand même : la clé existe


async def test_une_etape_reprise_relit_ce_qu_elle_avait_retenu(org, db_session, sans_base, module):
    installation = await _installation(db_session, org)
    sortie = await executants.cle_portail(
        _contexte(org, installation, {}, resultat_precedent={"type_entreprise": "restauration", "canaux": "site"})
    )
    assert sortie.montre["portail"]["metier"] == "restauration" and sortie.montre["portail"]["canaux"] == "site"


async def test_relancer_l_envoi_regenere_la_cle_et_relit_le_profil_retenu(org, db_session, sans_base, module, monkeypatch):
    user = await _jouer_jusqu_a_7(db_session, org, monkeypatch, ("a", "b"))
    etape = await moteur.executer(user, org.organisation.id, 7, {"type_entreprise": "restauration", "canaux": ["site"]})
    premiere = etape["montre"]["fiche_portail"]["cle_api"]["valeur"]
    rendu = await moteur.renvoyer_au_portail(user, org.organisation.id)
    fiche = rendu["montre"]["fiche_portail"]
    assert fiche["format"] == "client-portail-mark" and fiche["organisation_id"] == org.organisation.id
    assert fiche["cle_api"]["valeur"] != premiere
    assert rendu["montre"]["portail"]["montage"] == "plusieurs"
    assert rendu["montre"]["portail"]["canaux"] == "site" and rendu["montre"]["portail"]["metier"] == "restauration"
    actives = [c for c in await db_session.get_api_keys_by_organization(org.organisation.id) if c.name == executants.NOM_CLE_PORTAIL and c.is_active]
    assert len(actives) == 1 and actives[0].key_prefix == fiche["cle_api"]["prefixe"]  # l'ancienne est révoquée


async def test_pas_de_renvoi_avant_la_cle_ni_par_une_cle_d_api(org, db_session, sans_base, module, monkeypatch):
    user = await _jouer_jusqu_a_7(db_session, org, monkeypatch)
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.renvoyer_au_portail(user, org.organisation.id)
    assert refus.value.statut == 409 and refus.value.code == "cle_non_creee"
    await moteur.executer(user, org.organisation.id, 7, {})
    machine = SimpleNamespace(id=org.utilisateur.id, selected_organization_id=org.organisation.id, par_cle_api=True)
    with pytest.raises(moteur.RefusInstallation) as refus:
        await moteur.renvoyer_au_portail(machine, org.organisation.id)
    assert refus.value.statut == 403 and refus.value.code == "par_une_personne"


def test_la_route_du_renvoi_est_au_registre_sous_clients_creer():
    from api.services.equipe_mark.registre_routes import Permission, decision_de

    decision, _ = decision_de("POST", "/installations-client/courante/portail")
    assert decision == Permission("clients.creer")
