"""[.mark] Opening state of the business, computed once when the call is set up.

What it settles
---------------
Measured on 2026-09-15 on five calls: the agent's prompt says "the state of the
shop is GIVEN to you, you do not compute it", and the value was EMPTY. Nothing
computed it; only the keyboard replay tool typed it in by hand. So on a real
call the agent did not know whether the shop was open.

The rule of 2026-09-14 still holds: a state that has to be computed is not left
to a model, it is injected. This module computes it, in code, from opening hours
typed in a readable French format in the agent's settings.

The three functions, in the order the data flows
------------------------------------------------
1. ``vers_expression_osm``  the readable text -> an OpenStreetMap expression.
   Raises ``HorairesInvalides`` with the line number. Also used by the save
   route (``UpdateWorkflowRequest``), so a bad entry is refused when it is
   SAVED -- never by the schema, which is read at call set-up.
2. ``calculer_etat``        expression + instant -> (state, spoken reopening).
3. ``injecter_etat_ouverture``  writes ``etat_ouverture``, ``reouverture``,
   ``horaires_ouverture`` and ``annonce_ouverture`` into the call context.
   ⛔ Never raises. The fourth one (chantier corrections-appels-agent-6,
   2026-09-18) is the sentence the recorded greeting says when the shop is
   closed, so that the announcement no longer depends on the model.

And a fourth, from the latence-modele chantier (D2, 2026-09-15), called right
after the third because it is the same moment of the call:
4. ``injecter_date_heure_appel``  writes ``date_appel`` and ``heure_appel``,
   for every agent. ⛔ Never raises.

Decisions (Evan, 2026-09-15), referenced as D1..D13 in the plan
``_AUTONOMIE/plans/en-cours/etat-ouverture/2026-09-15-plan-etat-ouverture.md``.

⛔ Trap measured on the library: ``next_change()`` is the next CHANGE of state,
not the next OPENING (on 15 August it answered "Monday 00:00", the start of a
commented closing period). The reopening is the start of the first OPEN
interval, read from ``intervals()``.

⚠️ Known limit: Alsace-Moselle public holidays (Good Friday, 26 December) are
not in the ``FR`` calendar.
"""

import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from opening_hours import OpeningHours, State, validate

PARIS = ZoneInfo("Europe/Paris")

OUVERT = "OUVERT"
PAUSE = "PAUSE"
FERME = "FERME"
SUR_RENDEZ_VOUS = "SUR_RENDEZ_VOUS"
ETATS = (OUVERT, PAUSE, FERME, SUR_RENDEZ_VOUS)

CLE_ETAT = "etat_ouverture"
CLE_REOUVERTURE = "reouverture"
CLE_HORAIRES = "horaires_ouverture"
CLE_ANNONCE = "annonce_ouverture"

# D11: no opening found within this horizon -> empty reopening, state FERME.
HORIZON_REOUVERTURE = timedelta(days=60)

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_OSM_JOURS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
]
_OSM_MOIS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RDV = "sur rendez-vous"


class HorairesInvalides(ValueError):
    """A readable-format entry that cannot be translated. Message in French,
    carrying the line number, because it is shown as is on the settings screen."""


def _sans_accents(texte: str) -> str:
    """Rule 1 of D2: case and accents are ignored."""
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


# --------------------------------------------------------------------------- #
# 1. Readable text -> OpenStreetMap expression (grammar D2)
# --------------------------------------------------------------------------- #


def _heure(txt: str, ligne: int) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:h]\s*(\d{2})?)?\s*", txt)
    if not m:
        raise HorairesInvalides(f"ligne {ligne} : heure illisible « {txt.strip()} »")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 24 or mi > 59 or (h == 24 and mi > 0):
        raise HorairesInvalides(f"ligne {ligne} : heure impossible « {txt.strip()} »")
    return f"{h:02d}:{mi:02d}"


def _valeur(brute: str, ligne: int) -> tuple[str, str]:
    """« 10:00-12:30 et 14h-18h30 sur rendez-vous » -> ("10:00-12:30,14:00-18:30", "sur rendez-vous").

    Rules 2 to 4 of D2. Returns the OSM time selector (``off`` when closed) and
    the comment. ``sur rendez-vous`` wins over a parenthesised comment: OSM
    carries one comment per rule, and this one decides the state.
    """
    texte = brute.strip()
    commentaire = ""
    m = re.search(r"\(([^)]*)\)\s*$", texte)
    if m:
        commentaire = m.group(1).strip()
        texte = texte[: m.start()].strip()
    normalise = _sans_accents(texte)
    if normalise.endswith(RDV):
        commentaire = RDV
        normalise = normalise[: -len(RDV)].strip(" ,")
    if '"' in commentaire:
        raise HorairesInvalides(f"ligne {ligne} : guillemet interdit dans le commentaire")
    if normalise in ("ferme", "fermee"):
        return "off", commentaire
    sortie = []
    for morceau in re.split(r"\s*(?:,|\bet\b)\s*", normalise):
        if not morceau:
            continue
        bornes = re.split(r"\s*[-–]\s*", morceau)
        if len(bornes) != 2:
            raise HorairesInvalides(f"ligne {ligne} : plage illisible « {morceau} »")
        debut, fin = _heure(bornes[0], ligne), _heure(bornes[1], ligne)
        if fin <= debut:
            # A range past midnight would be cut at midnight in silence: the
            # next day's rule, always present, replaces its overflow in OSM.
            raise HorairesInvalides(
                f"ligne {ligne} : la fin précède le début « {morceau} » "
                "(une plage ne passe pas minuit)"
            )
        sortie.append(f"{debut}-{fin}")
    if not sortie:
        raise HorairesInvalides(f"ligne {ligne} : aucune plage horaire")
    return ",".join(sortie), commentaire


def _date(txt: str, ligne: int) -> str:
    """« 24/12/2026 » -> "2026 Dec 24" ; « 25/12 » -> "Dec 25" (every year)."""
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s*", txt)
    if not m:
        raise HorairesInvalides(
            f"ligne {ligne} : date illisible « {txt.strip()} » (attendu JJ/MM ou JJ/MM/AAAA)"
        )
    jour, mois, annee = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        # A leap year when none is given, so 29/02 is accepted as a yearly date.
        date(int(annee) if annee else 2024, mois, jour)
    except ValueError:
        raise HorairesInvalides(f"ligne {ligne} : date impossible « {txt.strip()} »") from None
    return (f"{annee} " if annee else "") + f"{_OSM_MOIS[mois - 1]} {jour:02d}"


def _regle(selecteur: str, valeur: str, commentaire: str, ligne: int) -> str:
    regle = f"{selecteur} {valeur}" + (f' "{commentaire}"' if commentaire else "")
    # Each rule is checked on its own, so a refusal can name its line.
    if not validate(regle):
        raise HorairesInvalides(f"ligne {ligne} : horaires non reconnus « {regle} »")
    return regle


def vers_expression_osm(texte: str) -> str:
    """Translate the readable format (D2) into an OpenStreetMap expression.

    Order of the rules, which IS the priority (rule 7): the seven days, then
    public holidays, then the exceptions in the order typed -- in OSM a later
    rule replaces an earlier one for the days it covers.
    """
    regles_jours: dict[int, str] = {}
    # Rule 5: no "jours fériés" line means closed on public holidays.
    regle_feries: str | None = "PH off"
    exceptions: list[str] = []
    dans_exceptions = False

    for numero, brute in enumerate(texte.splitlines(), start=1):
        ligne = brute.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, separateur, valeur = ligne.partition(":")
        cle_normalisee = _sans_accents(cle.strip())

        if cle_normalisee == "exceptions" and not valeur.strip():
            dans_exceptions = True
            continue
        if not separateur:
            raise HorairesInvalides(f"ligne {numero} : il manque « : » dans « {ligne} »")

        if cle_normalisee in JOURS:
            index = JOURS.index(cle_normalisee)
            plages, commentaire = _valeur(valeur, numero)
            regles_jours[index] = _regle(_OSM_JOURS[index], plages, commentaire, numero)
            continue

        if cle_normalisee in ("jours feries", "feries"):
            normalisee = _sans_accents(valeur.strip())
            # Strict: « ouvert le matin seulement » must be refused, not read
            # as open all day (rule 8).
            if normalisee in ("ouvert", "ouverte"):
                # Open on public holidays: the weekday rules apply unchanged.
                regle_feries = None
            else:
                plages, commentaire = _valeur(valeur, numero)
                regle_feries = _regle("PH", plages, commentaire, numero)
            continue

        if dans_exceptions or re.match(r"^\s*(du\s+)?\d", cle_normalisee):
            periode = re.fullmatch(r"\s*du\s+(.+?)\s+au\s+(.+?)\s*", cle_normalisee)
            plages, commentaire = _valeur(valeur, numero)
            if periode:
                quand = f"{_date(periode.group(1), numero)}-{_date(periode.group(2), numero)}"
            else:
                quand = _date(cle, numero)
            exceptions.append(_regle(quand, plages, commentaire, numero))
            continue

        raise HorairesInvalides(
            f"ligne {numero} : « {cle.strip()} » n'est ni un jour, ni « jours fériés », ni une date"
        )

    manquants = [JOURS[i] for i in range(7) if i not in regles_jours]
    if manquants:
        raise HorairesInvalides("jours sans ligne : " + ", ".join(manquants))

    regles = [regles_jours[i] for i in range(7)]
    if regle_feries:
        regles.append(regle_feries)
    regles += exceptions
    expression = "; ".join(regles)
    if not validate(expression):
        raise HorairesInvalides(f"horaires non reconnus dans leur ensemble : « {expression} »")
    return expression


# --------------------------------------------------------------------------- #
# 2. Expression + instant -> state and spoken reopening (D3, D4)
# --------------------------------------------------------------------------- #


def _a_paris(instant: datetime) -> datetime:
    return instant.replace(tzinfo=PARIS) if instant.tzinfo is None else instant.astimezone(PARIS)


def heure_parlee(instant: datetime) -> str:
    """« 14 heures », « 10 heures 30 », « 9 heures 05 », « minuit », « minuit 30 »."""
    if instant.hour == 0:
        # Evan, 2026-09-15: « minuit 30 », not « 0 heure 30 ».
        return "minuit" + (f" {instant.minute:02d}" if instant.minute else "")
    unite = "heure" if instant.hour <= 1 else "heures"
    return f"{instant.hour} {unite}" + (f" {instant.minute:02d}" if instant.minute else "")


def _phrase_reouverture(maintenant: datetime, reouverture: datetime, commentaire: str) -> str:
    ecart = (reouverture.date() - maintenant.date()).days
    heure = heure_parlee(reouverture)
    if ecart == 0:
        phrase = f"aujourd'hui à {heure}"
    elif ecart == 1:
        phrase = f"demain à {heure}"
    elif ecart < 7:
        phrase = f"{JOURS[reouverture.weekday()]} à {heure}"
    else:
        quantieme = "1er" if reouverture.day == 1 else str(reouverture.day)
        phrase = (
            f"{JOURS[reouverture.weekday()]} {quantieme} "
            f"{MOIS[reouverture.month - 1]} à {heure}"
        )
    if commentaire == RDV:
        phrase += ", sur rendez-vous"
    return phrase


def calculer_etat(expression: str, maintenant: datetime) -> tuple[str, str]:
    """D3 and D4, evaluated at ``maintenant`` in Paris time."""
    t = _a_paris(maintenant)
    horaires = OpeningHours(expression, timezone=PARIS, country="FR")
    etat, commentaire = horaires.state(t)

    if etat == State.OPEN:
        return (SUR_RENDEZ_VOUS if commentaire == RDV else OUVERT), ""

    if etat == State.UNKNOWN:
        # D3.5: our grammar produces no ambiguous rule, so this should not
        # happen; if it does, the agent is told closed rather than open.
        logger.error(f"[etat_ouverture] ambiguous state at {t.isoformat()} for « {expression} »")

    reouverture, commentaire_reouverture = None, ""
    # ⛔ The horizon is added in UTC. Added in local time, 28 January 02:30 +
    # 60 days lands on 29 March 02:30, an hour that does not exist in Paris,
    # and the library raises (review of 2026-09-15).
    horizon = (t.astimezone(UTC) + HORIZON_REOUVERTURE).astimezone(PARIS)
    for debut, _fin, etat_intervalle, commentaire_intervalle in horaires.intervals(
        t, horizon
    ):
        if etat_intervalle == State.OPEN:
            reouverture, commentaire_reouverture = _a_paris(debut), commentaire_intervalle
            break
    if reouverture is None:
        return FERME, ""

    debut_du_jour = t.replace(hour=0, minute=0, second=0, microsecond=0)
    deja_ouvert_aujourdhui = t > debut_du_jour and any(
        etat_intervalle == State.OPEN and fin is not None and _a_paris(fin) <= t
        for (_debut, fin, etat_intervalle, _c) in horaires.intervals(debut_du_jour, t)
    )
    meme_jour = reouverture.date() == t.date()
    code = PAUSE if (etat == State.CLOSED and deja_ouvert_aujourdhui and meme_jour) else FERME
    return code, _phrase_reouverture(t, reouverture, commentaire_reouverture)


# --------------------------------------------------------------------------- #
# 3. Injection into the call context (D5 to D9)
# --------------------------------------------------------------------------- #


def _est_vide(valeur: object) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def phrase_annonce(etat: str, reouverture: str) -> str:
    """The closing sentence the recorded greeting says, or an empty string.

    Why it is computed here, and not left to the agent's prompt: measured on the
    21 calls of 2026-09-17, the announcement was MISSING 12 times and late 4
    times. The prompt said « say it in your FIRST SENTENCE », but the greeting is
    a fixed text (``greeting_type: text``), so the model's first sentence is
    already the second turn. A state that has to be announced on every call is
    injected, like the state itself (rule of 2026-09-14).

    ⚠️ The trailing space belongs to the value: the greeting is written
    ``... bonjour. {{initial_context.annonce_ouverture}}Qu'est-ce que je peux faire
    pour vous ?`` so that an open business says the greeting it has always said,
    unchanged. An unknown variable renders as an empty string
    (``render_template``), so an agent without opening hours is never at risk of
    speaking the placeholder.

    ⛔ Write the variable as a DOTTED path in the greeting
    (``initial_context.annonce_ouverture``). A bare ``{{annonce_ouverture}}``
    is collected by ``get_required_template_variables`` and then demanded as a
    column of every outbound campaign's contact file, which rejects the file
    with HTTP 400 (review of 2026-09-18). Dotted paths are skipped there, and
    the renderer falls back to the bare key anyway.

    ⚠️ Wording stays generic, because this fork carries nothing specific to one
    client: neither "magasin" (a building trade PME has no shop) nor "pause
    déjeuner" (PAUSE means "already open today and reopening today", which at
    14:30 is not lunch).
    """
    if etat == FERME:
        debut = "Nous sommes fermés en ce moment"
    elif etat == PAUSE:
        debut = "Nous sommes fermés pour le moment"
    elif etat in ETATS:  # OUVERT, SUR_RENDEZ_VOUS: nothing to announce.
        return ""
    else:
        # A state written by hand, by a keyboard replay or by a pre-call fetch
        # ("ferme", "FERME ") reads as closed in the prompt while the greeting
        # announces nothing. Silent until now; said out loud from here on.
        logger.warning(f"[etat_ouverture] unknown state « {etat} », nothing announced")
        return ""
    return f"{debut}, nous rouvrons {reouverture}. " if reouverture else f"{debut}. "


def rafraichir_annonce(contexte: dict) -> dict:
    """Re-derive ``annonce_ouverture`` after something overwrote the state.

    Why: a pre-call fetch is merged AFTER the injection, on both paths
    (``event_handlers`` for the phone, ``text_chat_runner`` for the keyboard),
    and it may overwrite ``etat_ouverture`` and ``reouverture``. Without this,
    the greeting would announce a closed business while the model is told it is
    open -- or, worse for the defect this chantier fixes, announce NOTHING while
    the business is closed. Found by the independent review of 2026-09-18.

    ⛔ Never raises, like the injection it completes: a context this cannot read
    is returned untouched, and the call goes on.
    """
    try:
        if CLE_ANNONCE not in contexte:
            return contexte  # no hours on this agent: nothing was ever injected
        etat = contexte.get(CLE_ETAT)
        reouverture = contexte.get(CLE_REOUVERTURE)
        a_jour = phrase_annonce(
            etat if isinstance(etat, str) else "",
            reouverture if isinstance(reouverture, str) else "",
        )
        if a_jour == contexte[CLE_ANNONCE]:
            return contexte
        enrichi = dict(contexte)
        enrichi[CLE_ANNONCE] = a_jour
        return enrichi
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.error(f"[etat_ouverture] announcement not refreshed, call goes on: {erreur}")
        return contexte


def injecter_etat_ouverture(
    contexte: dict,
    run_configs: dict,
    maintenant: datetime | None = None,
) -> dict:
    """Return the call context with the opening state added.

    - D6: no opening hours on the agent -> the context is returned unchanged.
    - D7: a key already present and non-empty is NOT overwritten (a keyboard
      replay that injects a state keeps it; a pre-call fetch, merged later,
      wins too). An empty key is computed.
    - ⚠️ D7 does NOT apply to ``annonce_ouverture``: it is DERIVED from the
      state finally kept, so it is always rewritten. A keyboard replay cannot
      force an announcement of its own; it forces the STATE, and the sentence
      follows. A pre-call fetch merged after this call is handled by
      ``rafraichir_annonce``.
    - D9: ⛔ never raises. Invalid hours that reached a call anyway (written by
      hand, through MCP) are logged and nothing is injected: the call goes on.
    """
    try:
        # Imported here to keep this module free of ``api.*`` imports at load
        # time: the save route imports it, and it stays importable on its own.
        from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

        horaires = WorkflowConfigurationDefaults.model_validate(
            {CLE_HORAIRES: (run_configs or {}).get(CLE_HORAIRES)}
        ).horaires_ouverture
        if not horaires:
            return contexte

        instant = maintenant or datetime.now(PARIS)
        etat, reouverture = calculer_etat(vers_expression_osm(horaires), instant)
        calcule = {CLE_ETAT: etat, CLE_REOUVERTURE: reouverture, CLE_HORAIRES: horaires}

        enrichi = dict(contexte)
        for cle, valeur in calcule.items():
            if _est_vide(enrichi.get(cle)):
                enrichi[cle] = valeur
        # Computed from the state FINALLY kept, never from the computed one: a
        # keyboard replay that forces FERME on a Tuesday at 11 must announce a
        # closed shop (D7 applies to the state, the sentence follows it).
        etat_retenu, reouverture_retenue = enrichi[CLE_ETAT], enrichi[CLE_REOUVERTURE]
        enrichi[CLE_ANNONCE] = phrase_annonce(
            etat_retenu if isinstance(etat_retenu, str) else "",
            reouverture_retenue if isinstance(reouverture_retenue, str) else "",
        )
        return enrichi
    except Exception as erreur:  # noqa: BLE001 -- D9: the call must go on
        logger.error(
            f"[etat_ouverture] opening state not injected, the call goes on without it: {erreur}"
        )
        return contexte


# --------------------------------------------------------------------------- #
# 4. Date and time of the call, frozen when it is picked up (latence-modele D2)
# --------------------------------------------------------------------------- #

CLE_DATE_APPEL = "date_appel"
CLE_HEURE_APPEL = "heure_appel"


def date_parlee(instant: datetime) -> str:
    """« mardi 15 septembre 2026 », « vendredi 1er janvier 2027 »."""
    quantieme = "1er" if instant.day == 1 else str(instant.day)
    return f"{JOURS[instant.weekday()]} {quantieme} {MOIS[instant.month - 1]} {instant.year}"


def injecter_date_heure_appel(contexte: dict, maintenant: datetime | None = None) -> dict:
    """Return the call context with the date and time of the call, Paris time.

    Why frozen: the global prompt read ``{{current_time_Europe/Paris}}``, to the
    second, re-rendered at every node. Everything after it changed on every
    request, so Mistral's prompt cache stopped around 120 tokens (measured
    2026-09-15). A prompt that reads these two variables keeps its start.

    - Every agent, hours or not: two variables no prompt reads have no effect.
    - A value already present and non-empty is kept (a replay that injects a
      date keeps it; on the keyboard the first turn's values stay).
    - ⛔ Never raises: logged, context returned unchanged.
    """
    try:
        instant = _a_paris(maintenant or datetime.now(PARIS))
        calcule = {CLE_DATE_APPEL: date_parlee(instant), CLE_HEURE_APPEL: heure_parlee(instant)}
        enrichi = dict(contexte)
        for cle, valeur in calcule.items():
            if _est_vide(enrichi.get(cle)):
                enrichi[cle] = valeur
        return enrichi
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.error(
            f"[etat_ouverture] date and time of the call not injected, the call goes on without them: {erreur}"
        )
        return contexte
