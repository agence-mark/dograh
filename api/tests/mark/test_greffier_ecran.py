"""[.mark] Ce que l'écran du greffier affirme, vérifié contre le serveur (mode-prise-de-notes, partie 2).

| Test | Ce qu'il prouve |
|---|---|
| température | les fournisseurs pour lesquels l'écran laisse la température ouverte sont exactement ceux dont la configuration en déclare une : ailleurs, le serveur l'ignore |
| clé des passes | l'encadré de la page d'un appel lit la clé que le greffier écrit |
"""

import re
from pathlib import Path

from api.services.configuration.registry import REGISTRY, ServiceType
from api.services.pipecat.greffier import TRACE_GREFFIER

ECRAN = Path(__file__).resolve().parents[3] / "ui" / "src" / "components" / "mark"


def test_l_ecran_laisse_la_temperature_ouverte_la_ou_elle_joue():
    source = (ECRAN / "reglages-agent" / "consigne-greffier.ts").read_text(encoding="utf-8")
    bloc = re.search(r"FOURNISSEURS_AVEC_TEMPERATURE[^=]*=\s*\[([^\]]*)\]", source)
    assert bloc, "FOURNISSEURS_AVEC_TEMPERATURE introuvable : l'écran a bougé"
    ecran = set(re.findall(r'"([a-z_]+)"', bloc.group(1)))
    serveur = {
        str(getattr(fournisseur, "value", fournisseur))
        for fournisseur, configuration in REGISTRY[ServiceType.LLM].items()
        if "temperature" in configuration.model_fields
    }
    assert ecran == serveur


def test_l_encadre_de_l_appel_lit_la_cle_des_passes():
    source = (ECRAN / "BilanGreffier.tsx").read_text(encoding="utf-8")
    assert f'CLE_PASSES_DU_GREFFIER = "{TRACE_GREFFIER}"' in source
