"""[.mark] Partie 1, lot 8a (T1) : l'ouverture lue au décroché (``injecter_l_ouverture_de_la_caisse``) : ouverte, en pause, fermée ; caisse illisible : le contexte reste, rien ne lève.

Écrit avant de brancher les crochets (8a) : la même lecture sert la voix et le clavier, par le crochet ``au_decroche`` du module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from api.services.pipecat.etat_ouverture import CLE_ANNONCE, CLE_ETAT, CLE_REOUVERTURE
from api.services.restauration.appel_et_memoire import etiquettes as E

ALLUMEE = {"commande_sur_catalogue": True}
REPRISE = datetime(2030, 1, 15, 19, 0, tzinfo=UTC)


class _Connexion:
    def __init__(self):
        self.fermee = False

    async def close(self):
        self.fermee = True


class _Source:
    def __init__(self, connexion, lieu):
        pass

    async def charger_les_modes(self):
        return None


@pytest.fixture
def decroche(monkeypatch):
    """Tout ce qui touche la base est remplacé ; ``ouverture`` est ce que la caisse répond."""
    reponse = {"ouverture": {"ouvert": True}, "module_allume": True, "nom_base": "base_essai"}
    connexions: list[_Connexion] = []

    async def nom_de_la_base(_organisation):
        return reponse["nom_base"]

    async def etablissement_de_lappel(*_a, **_k):
        return None

    async def connecter(_nom):
        connexions.append(_Connexion())
        return connexions[-1]

    async def module_allume(_connexion):
        return reponse["module_allume"]

    async def identifiant(_connexion, _cle):
        return 1

    async def fuseau(_connexion, _etablissement):
        return "Europe/Paris"

    async def lire_l_ouverture(_source):
        if isinstance(reponse["ouverture"], Exception):
            raise reponse["ouverture"]
        return reponse["ouverture"]

    import api.services.base_client.rattachement as rattachement
    import api.services.commande.moteur as moteur
    import api.services.etablissements.appel as etablissements

    monkeypatch.setattr(rattachement, "nom_de_la_base", nom_de_la_base)
    monkeypatch.setattr(etablissements, "etablissement_de_lappel", etablissement_de_lappel)
    monkeypatch.setattr(moteur, "lire_l_ouverture", lire_l_ouverture)
    monkeypatch.setattr(E, "connecter", connecter)
    monkeypatch.setattr(E, "module_allume", module_allume)
    monkeypatch.setattr(E, "identifiant_de_l_etablissement", identifiant)
    monkeypatch.setattr(E, "fuseau_de", fuseau)
    monkeypatch.setattr(E, "SourceClasseur", _Source)
    monkeypatch.setattr(E, "horloge", lambda _organisation: SimpleNamespace(maintenant=lambda: datetime(2030, 1, 15, 10, 0, tzinfo=UTC)))
    reponse["connexions"] = connexions
    return reponse


async def _lire(contexte=None, configurations=ALLUMEE):
    return await E.injecter_l_ouverture_de_la_caisse(dict(contexte or {}), configurations, 7, 3)


async def test_une_caisse_ouverte_ne_change_rien(decroche):
    assert await _lire({"a": 1}) == {"a": 1}
    assert decroche["connexions"][0].fermee


async def test_une_caisse_en_pause_le_dit_des_le_decroche(decroche):
    decroche["ouverture"] = {"ouvert": False, "etat": "PAUSE", "reprise": REPRISE}
    contexte = await _lire({"a": 1})
    assert contexte["a"] == 1 and contexte[CLE_ETAT] == "PAUSE" and contexte[CLE_REOUVERTURE] and contexte[CLE_ANNONCE]


async def test_une_caisse_fermee_sans_reprise_le_dit_sans_reouverture(decroche):
    decroche["ouverture"] = {"ouvert": False, "etat": "FERME"}
    contexte = await _lire()
    assert contexte[CLE_ETAT] == "FERME" and contexte[CLE_REOUVERTURE] == ""


async def test_une_caisse_illisible_laisse_le_contexte_et_ne_leve_pas(decroche):
    decroche["ouverture"] = RuntimeError("la caisse ne répond pas")
    assert await _lire({"a": 1}) == {"a": 1}
    assert decroche["connexions"][0].fermee  # la connexion est rendue même sur l'erreur


@pytest.mark.parametrize("cas", ["module_eteint", "pas_de_base", "module_du_lieu_eteint"])
async def test_sans_module_ni_base_rien_ne_change(decroche, cas):
    decroche["ouverture"] = {"ouvert": False, "etat": "PAUSE", "reprise": REPRISE}  # fermée : on verrait la différence
    if cas == "module_eteint":
        assert await _lire({"a": 1}, configurations={"commande_sur_catalogue": False}) == {"a": 1}
    elif cas == "pas_de_base":
        decroche["nom_base"] = None
        assert await _lire({"a": 1}) == {"a": 1}
    else:
        decroche["module_allume"] = False
        assert await _lire({"a": 1}) == {"a": 1}
