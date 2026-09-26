"""[.mark] The budget of the vocabulary as the screen shows it (plan « le lexique », Q2).

« 212 / 450 tokens (Deepgram) », and the ticked terms that would not be sent:
computed HERE with the very functions a call uses (``plafond_du_lexique``,
``construire_liste_ecoutee``), for the organization's transcription provider.
The screen never counts on its own: two counts would drift apart.

⚠️ The organization's vocabulary only. Each agent's own Dictionary is sent
FIRST and takes from the same ceiling; the screen says so in words.
"""

from __future__ import annotations

from loguru import logger

from api.schemas.lexique_metier import BudgetLexique, LexiqueMetier
from api.services.configuration.ai_model_configuration import (
    get_resolved_ai_model_configuration,
)
from api.services.configuration.plafond_lexique import plafond_du_lexique
from api.services.lexique.ecoute import construire_liste_ecoutee


async def budget_du_lexique(organization_id: int | None, lexique: LexiqueMetier) -> BudgetLexique:
    fournisseur = modele = None
    try:
        resolue = await get_resolved_ai_model_configuration(organization_id=organization_id)
        stt = getattr(resolue.effective, "stt", None)
        fournisseur = getattr(stt, "provider", None)
        fournisseur = str(getattr(fournisseur, "value", fournisseur)) if fournisseur else None
        modele = getattr(stt, "model", None)
    except Exception as erreur:  # noqa: BLE001 -- shown as « no provider », never a 500
        logger.warning(f"[.mark] Transcription provider unreadable for the vocabulary budget: {erreur!r}")
    plafond = plafond_du_lexique(fournisseur, modele)
    liste = construire_liste_ecoutee(None, lexique, plafond)
    return BudgetLexique(
        fournisseur=fournisseur,
        nom_du_plafond=plafond.fournisseur if plafond else None,
        plafond_jetons=plafond.jetons if plafond else None,
        jetons=liste.jetons,
        envoyes=liste.termes,
        non_envoyes=liste.non_envoyes,
    )
