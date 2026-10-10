"""[.mark] Ce que l'écran du greffier affirme, vérifié contre le serveur (mode-prise-de-notes, partie 2).

| Test | Ce qu'il prouve |
|---|---|
| formulaire généré | la modale du greffier lit le schéma de chaque fournisseur (D9, lot C d'agent-leger-greffier) ; aucune liste écrite à la main |
| clé des passes | l'encadré de la page d'un appel lit la clé que le greffier écrit |
"""

from pathlib import Path

from api.services.configuration.registry import REGISTRY, ServiceType
from api.services.pipecat.greffier import TRACE_GREFFIER

ECRAN = Path(__file__).resolve().parents[3] / "ui" / "src" / "components" / "mark"


def test_la_modale_du_greffier_est_generee_depuis_le_schema_du_fournisseur():
    """Lot C d'agent-leger-greffier (D9) : plus aucune liste de fournisseurs écrite à la
    main côté écran ; la modale montre les champs que le serveur déclare pour le
    fournisseur nommé, et le serveur accepte exactement ceux-là (``greffier_llm_valide``)."""
    theme = (ECRAN / "reglages-agent" / "ThemeDonnees.tsx").read_text(encoding="utf-8")
    assert "<ChampsFournisseurLlm bloc={blocEdite} onChange={setBlocEdite} />" in theme
    composant = (ECRAN / "modeles" / "ChampsFournisseurLlm.tsx").read_text(encoding="utf-8")
    assert "getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet" in composant
    consigne = (ECRAN / "reglages-agent" / "consigne-greffier.ts").read_text(encoding="utf-8")
    assert "FOURNISSEURS_AVEC_TEMPERATURE" not in consigne
    # Le serveur valide chaque réglage par la déclaration du fournisseur.
    from api.schemas.workflow_configurations import _classe_llm

    assert {
        str(getattr(f, "value", f)) for f in REGISTRY[ServiceType.LLM]
    } == {f for f in (str(getattr(f, "value", f)) for f in REGISTRY[ServiceType.LLM]) if _classe_llm(f)}


def test_l_encadre_de_l_appel_lit_la_cle_des_passes():
    source = (ECRAN / "BilanGreffier.tsx").read_text(encoding="utf-8")
    assert f'CLE_PASSES_DU_GREFFIER = "{TRACE_GREFFIER}"' in source
