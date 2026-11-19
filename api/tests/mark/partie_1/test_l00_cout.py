"""[.mark] Chantier Partie 1, lot 0 : le coût d'un run Gemma 4 est chiffré (L00-13, complément de Pierre 11b).

Le prix est une DONNÉE de l'organisation (décision L5 du chantier de la fenêtre du run : aucun prix dans le code, une table vide dit
« coût non capté », jamais un coût deviné). Le 19/11, la table de l'organisation du chantier était vide (« pas de prix ») ; elle porte
désormais le tarif daté ci-dessous, versé par l'écran (route ``PUT /organizations/fenetre-du-run``) et relu. Ce fichier tient la même
ligne que l'organisation, pour prouver que ce tarif chiffre un run Gemma 4 au montant attendu.
"""

import json
from pathlib import Path

from api.schemas.fenetre_du_run import ReglagesFenetreDuRun
from api.services.analyse_run.cout import cout_du_run

TARIF = ReglagesFenetreDuRun.model_validate(json.loads((Path(__file__).parent / "donnees" / "tarif_gemma_4.json").read_text(encoding="utf-8")))
MODELE = TARIF.lignes[0].modele
RUN = {"usage_info": {"llm": {f"DograhOpenAILLMService#1|||{MODELE}": {"prompt_tokens": 3200, "completion_tokens": 60}}}}


def test_cout_gemma_non_nul():
    c = cout_du_run(RUN, TARIF)
    assert c["status"] == "ok" and not c["partial"], c
    assert c["lines"][0]["cost"] == round((3200 * 0.25 + 60 * 0.50) / 1_000_000, 6), c
    assert c["lines"][0]["cost"] > 0 and c["currency"] == "EUR" and c["rate_dates"] == ["2026-10-09"], c


def test_sans_table_le_cout_reste_non_capte():
    """L5 tient : sans table, rien n'est deviné."""
    assert cout_du_run(RUN, None)["status"] == "not_captured"
    assert cout_du_run(RUN, ReglagesFenetreDuRun())["status"] == "not_captured"
