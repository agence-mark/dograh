"""[.mark] The SMS after the call (chantier l-agent-travaille, L6; plan sms-recapitulatif D1 to D11).

A module of the after-call chain (``modules.py``), switched on agent by agent, off by default:

- D1, D2: sent by the fork, through the client's Twilio (its account of « Telephony »);
- D3: after the call only, never during it (no latency);
- D4: to the caller only on a French mobile: the number presented, else the call-back number of
  the record; to the team on the numbers set;
- D5: nothing for a call without a reason, or classed voicemail / wrong number / hung up;
- D6: one SMS per call and per recipient: what was sent is kept on the run, a retry never resends;
- D7: the chain retries (3 tries), then the step is red on screen and notified;
- D8: the text is never the model's: blanks filled by the record, cut to 160 characters.
"""

from __future__ import annotations

import os
import re

import httpx
from loguru import logger

from api.schemas.apres_appel import LONGUEUR_SMS, est_un_mobile, numero_e164
from api.utils.template_renderer import render_template

ETAPE = "module:sms"
DELAI_TWILIO_S = 15.0
VARIABLE_API = "MARK_TWILIO_API_URL"  # a local stand-in for the demonstration; never set in production

# D5: dispositions of a call where nobody asked anything (lower case, compared by inclusion).
ISSUES_SANS_SMS = (
    "voicemail",
    "repondeur",
    "répondeur",
    "wrong_number",
    "faux_numero",
    "no_answer",
    "busy",
    "failed",
    "canceled",
    "cancelled",
    "machine",
)

# The GSM 03.38 alphabet: a text outside it is sent in UCS-2 (70 characters a part).
_GSM7 = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_ETENDU = set("^{}\\[~]|€")


def api_twilio() -> str:
    return (os.environ.get(VARIABLE_API) or "https://api.twilio.com").rstrip("/")


def nouveau_client(**options) -> httpx.AsyncClient:
    """The HTTP client of the SMS (a test gives its stand-in Twilio here)."""
    return httpx.AsyncClient(**options)


def parties(texte: str) -> tuple[int, str]:
    """How many SMS the operator bills for this text, and the encoding (D8, D9)."""
    if all(c in _GSM7 or c in _GSM7_ETENDU for c in texte):
        longueur = len(texte) + sum(1 for c in texte if c in _GSM7_ETENDU)
        return (1 if longueur <= 160 else -(-longueur // 153)), "gsm7"
    return (1 if len(texte) <= 70 else -(-len(texte) // 67)), "ucs2"


def remplir(texte: str, fiche: dict) -> tuple[str, bool]:
    """The text with its blanks filled by the record, on one line, cut to 160 characters at a
    word (``…``). Returns (text, cut)."""
    rendu = str(
        render_template(texte, {k: ("" if v is None else v) for k, v in fiche.items()})
        or ""
    )
    rendu = re.sub(r"\s+", " ", rendu).strip()
    if len(rendu) <= LONGUEUR_SMS:
        return rendu, False
    coupe = rendu[: LONGUEUR_SMS - 1]
    if " " in coupe:
        coupe = coupe[: coupe.rfind(" ")]
    return coupe.rstrip(" ,;:.-") + "…", True


def fiche_de_l_envoi(envoi: dict) -> dict:
    return {c["nom"]: c["valeur"] for c in envoi.get("champs") or [] if c.get("nom")}


def sans_objet(envoi: dict) -> str | None:
    """D5: the reason no SMS goes out for this call, or None."""
    if not (envoi.get("motif") or "").strip():
        return "No reason in the record: nobody asked anything, no SMS."
    issue = (envoi.get("issue") or "").lower()
    if any(mot in issue for mot in ISSUES_SANS_SMS):
        return f"Call classed « {envoi.get('issue')} »: no SMS."
    return None


def numero_de_l_appelant(run, envoi: dict, champ_rappel: str) -> str | None:
    """D4: the number presented if it is a French mobile, else the call-back number of the
    record if it is one, else None (no SMS to the caller)."""
    initial = getattr(run, "initial_context", None) or {}
    presente = (
        initial.get("caller_number")
        if envoi.get("sens") == "entrant"
        else initial.get("called_number")
    )
    for brut in (presente, fiche_de_l_envoi(envoi).get(champ_rappel)):
        numero = numero_e164(brut)
        if est_un_mobile(numero):
            return numero
    return None


class EchecTwilio(RuntimeError):
    def __init__(self, message: str, definitif: bool):
        super().__init__(message)
        self.definitif = definitif


async def envoyer(
    account_sid: str, auth_token: str, expediteur: str, destinataire: str, texte: str
) -> str:
    """One SMS through the client's Twilio. Returns its id. The token never in an error."""
    url = f"{api_twilio()}/2010-04-01/Accounts/{account_sid}/Messages.json"
    try:
        async with nouveau_client(timeout=DELAI_TWILIO_S) as client:
            reponse = await client.post(
                url,
                data={"To": destinataire, "From": expediteur, "Body": texte},
                auth=(account_sid, auth_token),
            )
    except httpx.HTTPError as erreur:
        raise EchecTwilio(
            f"Twilio does not answer ({type(erreur).__name__}).", definitif=False
        ) from None
    if reponse.status_code >= 400:
        try:
            corps = reponse.json()
            raison = f"{corps.get('code')}: {corps.get('message')}"
        except ValueError:
            raison = f"HTTP {reponse.status_code}"
        logger.warning(f"[.mark] SMS refused by Twilio: {raison}")
        raise EchecTwilio(
            f"Twilio refused the SMS ({raison}).",
            definitif=400 <= reponse.status_code < 500 and reponse.status_code != 429,
        )
    try:
        return str(reponse.json().get("sid") or "")
    except ValueError:
        return ""
