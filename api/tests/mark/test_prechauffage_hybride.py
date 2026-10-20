"""[.mark] Chantier fiabilite-orchestration, lot 3 : le préchauffage hybride (F5, F6, R17).

La route complète (réserve construite au décroché, prise par la passation sans construction, refaite
en fond) est tenue par ``test_passation_rapide_groupe.py::test_le_prechauffage_charge_les_cibles_puis_
les_construit_a_l_avance``. Ici : le poste partagé et la passation découpée.

| Test | La garantie |
|---|---|
| même fournisseur | deux services à la même adresse et la même clé gardent le même client (connexion ouverte) |
| autre fournisseur | une autre adresse ou une autre clé garde son propre client |
| isolés | deux agents au même poste gardent chacun leurs outils et leurs réglages |
| fond | le service du cerveau de fond reprend la connexion de l'appel (F6) |
| clé | la clé n'est jamais gardée en clair dans la clé du poste |
| mesure | la passation découpée (installation, origine, premier mot, mémoire) entre dans l'enregistrement |
"""

from types import SimpleNamespace

import pytest
from pipecat.services.openai.llm import OpenAILLMService

from api.services.groupe.mesure_passation import MesureDePassation
from api.services.groupe.postes import Postes, cle_du_poste, memoire_du_processus_mo


def _service(adresse="https://api.exemple.test/v1", cle="cle-a", modele="petit"):
    return OpenAILLMService(api_key=cle, base_url=adresse, model=modele)


def test_meme_fournisseur_meme_connexion_et_autre_fournisseur_la_sienne():
    postes = Postes()
    accueil = _service(modele="grand")
    postes.enregistrer(accueil)
    collegue = _service(modele="petit")  # autre modèle, même adresse, même clé
    assert postes.partager(collegue) is True
    assert collegue._client is accueil._client
    ailleurs = _service(adresse="https://autre.exemple.test/v1")
    autre_cle = _service(cle="cle-b")
    assert postes.partager(ailleurs) is False and ailleurs._client is not accueil._client
    assert postes.partager(autre_cle) is False and autre_cle._client is not accueil._client
    assert postes.partages == 1


def test_deux_agents_au_meme_poste_gardent_leurs_outils():
    postes = Postes()
    accueil, collegue = _service(), _service()
    postes.enregistrer(accueil)
    postes.partager(collegue)

    async def outil(_params):
        return None

    collegue.register_function("propre_au_collegue", outil)
    assert collegue.has_function("propre_au_collegue")
    assert not accueil.has_function("propre_au_collegue")
    assert accueil is not collegue


def test_la_cle_n_est_jamais_gardee_en_clair():
    cle = cle_du_poste(_service(cle="secret-tres-long"))
    assert cle is not None and "secret-tres-long" not in "".join(cle)


def test_sans_client_rien_n_est_partage():
    assert Postes().partager(SimpleNamespace()) is False


def test_la_memoire_se_lit_ou_rend_rien():
    memoire = memoire_du_processus_mo()
    assert memoire is None or memoire > 0


@pytest.mark.asyncio
async def test_la_reserve_prepare_le_cerveau_de_fond_avant_la_passation():
    """F6 : le collègue construit à l'avance arrive avec son cerveau de fond déjà prêt ; un échec
    de construction ne range rien (la passation construira comme avant)."""
    from api.services.groupe.prechauffage import Precharge
    from api.services.workflow.pipecat_engine import PipecatEngine

    runtime = SimpleNamespace(preconstruit=False, travail=None)
    ordre: list[str] = []

    async def construire(*, workflow_id, visit_id):
        ordre.append("construit")
        return runtime

    async def preparer(rt):
        ordre.append("fond")
        rt.travail = "fond prêt"

    class Moteur:
        pass

    moteur = Moteur()
    moteur._agent_factory = SimpleNamespace(precharge=Precharge(organization_id=1), build=construire)
    moteur.preparer_le_travail = preparer
    moteur.is_call_disposed = lambda: False
    await PipecatEngine._mettre_en_reserve(moteur, 42)
    assert ordre == ["construit", "fond"]
    assert moteur._agent_factory.precharge.prets[42] is runtime
    assert runtime.preconstruit is True and runtime.travail == "fond prêt"

    async def echoue(**_):
        raise RuntimeError("cible absente")

    moteur._agent_factory.build = echoue
    await PipecatEngine._mettre_en_reserve(moteur, 43)
    assert 43 not in moteur._agent_factory.precharge.prets
    assert 43 in moteur._agent_factory.precharge.echecs


def test_la_passation_decoupee_entre_dans_l_enregistrement():
    temps = [10.0]
    mesure = MesureDePassation(horloge=lambda: temps[0])
    mesure.demandee("xfer-1")
    temps[0] = 10.2
    mesure.installee(0.05, "reserve", 512.0, "visite-b")
    temps[0] = 10.3
    mesure.commise()
    mesure.premier_mot("visite-a")  # un autre agent : ignoré
    temps[0] = 10.9
    mesure.premier_mot("visite-b")
    mesure.premier_mot("visite-b")  # une seule fois
    temps[0] = 11.4
    mesure.premier_octet()
    enregistrement = mesure.completer({"request_id": "xfer-1", "to_visit_id": "visite-b"})
    assert enregistrement["installation"] == "reserve"
    assert enregistrement["installation_s"] == 0.05
    assert enregistrement["memoire_mo"] == 512.0
    assert enregistrement["premier_mot_s"] == 0.9
    assert enregistrement["voix_premier_octet_s"] == 1.4
    # Une autre passation n'est jamais complétée par celle-ci.
    assert "installation" not in mesure.completer({"request_id": "xfer-2", "to_visit_id": "x"})
