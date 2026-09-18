"""[.mark] The states of a business and the two sentences said at pick-up.

⛔ This module imports NOTHING. It exists so that the settings schema
(``api/schemas/annonce_ouverture.py``) and the call-time code
(``api/services/pipecat/etat_ouverture.py``) can share these values without the
schema layer depending on the service layer.

Why it was pulled out (independent review of 2026-09-18, S5): the schema used to
import the service module directly. That only worked because the service module
happens to import nothing from ``api.*`` at load time. The day someone adds an
``api.schemas`` import at its top, the application stops starting -- a landmine
nobody would see coming. Four lines in a module of their own remove it.
"""

from __future__ import annotations

OUVERT = "OUVERT"
PAUSE = "PAUSE"
FERME = "FERME"
SUR_RENDEZ_VOUS = "SUR_RENDEZ_VOUS"
ETATS = (OUVERT, PAUSE, FERME, SUR_RENDEZ_VOUS)

# The variable an announcement sentence may carry, and the two sentences an
# organization that never opened the settings screen keeps hearing.
#   « {reouverture} »  the spoken reopening (« demain à 10 heures »).
#   « [ … ] »          said only when that reopening is known.
JETON_REOUVERTURE = "reouverture"
ANNONCE_FERMETURE_DEFAUT = "Nous sommes fermés en ce moment[, nous rouvrons {reouverture}]."
ANNONCE_PAUSE_DEFAUT = "Nous sommes fermés pour le moment[, nous rouvrons {reouverture}]."
