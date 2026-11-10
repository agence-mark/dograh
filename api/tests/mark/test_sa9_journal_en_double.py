"""[.mark] Clôture, SA-9 (mineur 9) : une route qui écrit sa propre ligne au journal n'en écrit pas une seconde par le registre.

| Test | Ce qu'il prouve |
|---|---|
| inventaire | chaque route d'écriture de l'application qui appelle elle-même ``journaliser`` / ``ecrire_journal`` est dans ``ROUTES_QUI_JOURNALISENT_ELLES_MEMES`` (préfixe) ou ``..._EXACTES`` (méthode et gabarit) ; la liste ne contient aucune route disparue |
| une seule ligne | ``PUT /builder/branches/{id}/principale/protection`` n'écrit que sa ligne (``agents.principale_protegee``), plus ``agents.publier`` en double ; une écriture ordinaire garde sa ligne du registre |
"""

from __future__ import annotations

import inspect
import re

from api.services.equipe_mark.acces import ROUTES_QUI_JOURNALISENT_ELLES_MEMES, ROUTES_QUI_JOURNALISENT_ELLES_MEMES_EXACTES
from api.services.equipe_mark.registre_routes import ECRITURE, Permission, decision_de, ecrit_quelque_chose
from api.tests.mark.test_journal_sans_fausses_ecritures import _decider
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401
from api.tests.mark.test_principale_protegee import AUTRE, GRAPHE, _agent, _branche_fermee, labo_est  # noqa: F401
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401

APPEL_AU_JOURNAL = re.compile(r"\b(journaliser|ecrire_journal|differer_le_journal)\(")


def _routes_d_ecriture():
    from api.app import app

    for route in app.routes:
        chemin = getattr(route, "path", "")
        if not chemin.startswith("/api/v1"):
            continue
        for methode in (getattr(route, "methods", None) or set()) & ECRITURE:
            yield methode, chemin[len("/api/v1") :], route


def test_toute_route_qui_ecrit_sa_propre_ligne_est_dans_la_liste_des_routes_qui_journalisent_elles_memes():
    en_double = []
    for methode, chemin, route in _routes_d_ecriture():
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            continue
        if not APPEL_AU_JOURNAL.search(source):
            continue
        trouvee = decision_de(methode, chemin)
        if trouvee is None or not isinstance(trouvee[0], Permission) or not ecrit_quelque_chose(methode, chemin):
            continue  # le registre n'écrit aucune ligne pour cette route : rien en double
        if chemin.startswith(ROUTES_QUI_JOURNALISENT_ELLES_MEMES) or (methode, chemin) in ROUTES_QUI_JOURNALISENT_ELLES_MEMES_EXACTES:
            continue
        en_double.append(f"{methode} {chemin}")
    assert not en_double, "ces routes écrivent leur ligne ET celle du registre : à ajouter à ROUTES_QUI_JOURNALISENT_ELLES_MEMES_EXACTES\n" + "\n".join(sorted(en_double))


def test_la_liste_exacte_ne_garde_aucune_route_disparue():
    existantes = {(methode, chemin) for methode, chemin, _ in _routes_d_ecriture()}
    disparues = sorted(ROUTES_QUI_JOURNALISENT_ELLES_MEMES_EXACTES - existantes)
    assert not disparues, disparues


async def test_une_route_qui_journalise_elle_meme_n_ecrit_pas_une_seconde_ligne_et_une_ecriture_ordinaire_garde_la_sienne():
    gabarit = "/api/v1/builder/branches/{workflow_id}/principale/protection"
    assert await _decider("PUT", gabarit, {"workflow_id": 4}) == []
    assert len(await _decider("PUT", "/api/v1/workflow/{workflow_id}", {"workflow_id": 4})) == 1
