"""[.mark] Lot 8, 8c-2 (109) : le connecteur « Service » n'importe plus la porte de la commande (``commande/porte.py``) : la fiche du service et les outils
de l'accueil ont leur module (``commande/porte_du_service.py``). Lu par ``ast`` (imports de tête et imports dans les fonctions)."""

from __future__ import annotations

import ast
from pathlib import Path

RACINE_API = Path(__file__).resolve().parents[3]
SERVICE = RACINE_API / "services/integrations/connectors/actions/service.py"


def _modules_importes(fichier: Path) -> set[str]:
    noms: set[str] = set()
    for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
        if isinstance(noeud, ast.ImportFrom) and noeud.module:
            noms.add(noeud.module)
            noms.update(f"{noeud.module}.{alias.name}" for alias in noeud.names)
        elif isinstance(noeud, ast.Import):
            noms.update(alias.name for alias in noeud.names)
    return noms


def test_le_connecteur_service_n_importe_pas_la_porte_de_la_commande():
    assert "api.services.commande.porte" not in _modules_importes(SERVICE)


def test_la_fiche_du_service_et_les_outils_de_l_accueil_ont_leur_module():
    from api.services.commande import porte_du_service

    assert callable(porte_du_service.executer_la_fiche_du_service) and callable(porte_du_service.executer_un_outil_de_l_accueil)
    assert set(porte_du_service.OUTILS_DE_L_ACCUEIL) == {"ouverture_en_ce_moment", "heure_annoncee", "remises_disponibles", "envoyer_un_sms"}
