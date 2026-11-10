"""[.mark] Builder, lot 5 : les règles du contrôle du prompt (pures, sans base, sans appel).

⛔ Zéro vocabulaire métier : chaque règle ne regarde que la FORME du texte et du graphe (répétition, nom d'outil, valeur
d'exemple, sortie du graphe, longueur, variable inconnue...), jamais un mot du métier d'un client.

Bloquants (Q12, B34, B49) : règle écrite deux fois, règles qui se contredisent, nom d'outil dans le texte, exemple de
valeur, outil sans consigne d'échec, étape sans sortie vers la fin, longueur au-delà du plafond (avertissement depuis T3), persona qui porte une règle
de conduite, phrase dite par le code écrite aussi dans un prompt, ``{{nom}}`` inconnu.
Avertissements : outil d'écriture sans relecture en deux temps (R0-3), genre du persona différent de celui de la voix (B31),
fait écrit en dur alors qu'un objet de même contenu existe (B49), base du client injoignable (B49).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from api.services.etiquettes_prompt.familles import est_une_etiquette, sans_etiquettes
from api.utils.template_renderer import TEMPLATE_VAR_PATTERN, is_builtin_variable

BLOQUANT = "bloquant"
AVERTISSEMENT = "avertissement"

LONGUEUR_MIN_D_UNE_REGLE = 25
LONGUEUR_MIN_D_UNE_PHRASE = 12
LONGUEUR_MIN_D_UN_FAIT = 8

TYPES_A_PROMPT = ("startCall", "agentNode", "endCall", "globalNode")
PREFIXES_DU_CONTEXTE = ("initial_context.", "gathered_context.")


@dataclass
class Defaut:
    code: str
    gravite: str
    message: str
    etape: str | None = None
    extrait: str | None = None
    # [.mark] Clôture, SA-3 : ce que le message dit de variable (nombre de caractères, genre de valeur, nom d'un objet), pour que l'écran
    # le traduise PAR IDENTIFIANT (``code``) dans les deux langues. ``message`` reste la phrase anglaise (API, MCP, journaux).
    parametres: dict[str, Any] = field(default_factory=dict)

    def en_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "gravite": self.gravite,
            "message": self.message,
            "etape": self.etape,
            "extrait": self.extrait,
            "parametres": self.parametres,
        }


@dataclass
class OutilConnu:
    uuid: str
    nom: str
    categorie: str = "http_api"
    methode: str | None = None  # HTTP seulement


@dataclass
class ObjetConnu:
    nom: str
    texte: str


@dataclass
class Entree:
    graphe: dict[str, Any]
    outils: dict[str, OutilConnu] = field(default_factory=dict)  # uuid -> outil
    noms_d_outils_du_moteur: tuple[str, ...] = ()
    phrases_du_code: list[str] = field(default_factory=list)
    # ``None`` : la base du client n'a pas répondu (on ne bloque pas sur les objets, on le dit).
    objets: list[ObjetConnu] | None = field(default_factory=list)
    variables_posees_par_le_code: frozenset[str] = frozenset()
    variables_de_l_agent: frozenset[str] = frozenset()  # contexte de l'agent, extractions, fiche, phrases du client
    genre_de_la_voix: str | None = None  # "f" | "m" | None (non relevé : on ne devine pas)
    # [.mark] Lot « façon Tala par motif » (T3) : le plafond d'un prompt lit le réglage « Taille supportée par le cerveau »
    # (``cerveau_plafond_prompt``) ; vide = aucun seuil, la règle ``longueur`` est muette. Même principe pour le poids d'une réplique.
    plafond: int | None = None
    poids_max: int | None = None
    # La position (« eteint » | « previent » | « bloque ») de chaque contrôle de rédaction, lue dans ``publication.controles`` :
    # le MÊME réglage que les autres contrôles de publication. Absent = « previent ».
    redaction: dict[str, str] = field(default_factory=dict)


# --- outils de texte ----------------------------------------------------------------------------------------------


def normaliser(texte: Any) -> str:
    s = unicodedata.normalize("NFKD", str(texte or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip()


def _unites(prompt: str) -> list[str]:
    """Les règles d'un prompt : une par ligne, puis par phrase. Les titres et lignes courtes ne comptent pas."""
    sortie: list[str] = []
    for ligne in prompt.splitlines():
        ligne = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ligne).strip()
        for phrase in re.split(r"(?<=[.!?;])\s+", ligne):
            if len(normaliser(phrase)) >= LONGUEUR_MIN_D_UNE_REGLE:
                sortie.append(phrase.strip())
    return sortie


def _noeuds(graphe: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in graphe.get("nodes") or [] if isinstance(n, dict)]


def _donnees(noeud: dict[str, Any]) -> dict[str, Any]:
    return noeud.get("data") if isinstance(noeud.get("data"), dict) else {}


def _nom(noeud: dict[str, Any]) -> str:
    return str(_donnees(noeud).get("name") or noeud.get("id") or "?")


def _prompt(noeud: dict[str, Any]) -> str:
    p = _donnees(noeud).get("prompt")
    return p if isinstance(p, str) else ""


def _global(graphe: dict[str, Any]) -> dict[str, Any] | None:
    return next((n for n in _noeuds(graphe) if n.get("type") == "globalNode"), None)


def _prompts_de_parole(graphe: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    return [(n, _prompt(n)) for n in _noeuds(graphe) if n.get("type") in TYPES_A_PROMPT and _prompt(n)]


# --- 1. règle écrite deux fois ------------------------------------------------------------------------------------


def regle_en_double(e: Entree) -> list[Defaut]:
    defauts: list[Defaut] = []
    glob = _global(e.graphe)
    globales = {normaliser(u) for u in _unites(_prompt(glob))} if glob else set()
    for n, prompt in _prompts_de_parole(e.graphe):
        vues: set[str] = set()
        for u in _unites(prompt):
            cle = normaliser(u)
            if cle in vues:
                defauts.append(Defaut("regle_en_double", BLOQUANT, "A rule is written twice in the same prompt.", _nom(n), u[:120], {"portee": "meme_prompt"}))
            vues.add(cle)
            if n.get("type") != "globalNode" and _donnees(n).get("add_global_prompt", True) and cle in globales:
                defauts.append(Defaut("regle_en_double", BLOQUANT, "A rule of the step is already in the global prompt.", _nom(n), u[:120], {"portee": "prompt_general"}))
    return defauts


# --- 2. règles qui se contredisent ---------------------------------------------------------------------------------

_NEGATION = re.compile(r"\b(jamais|never|ne\s+\w+\s+pas|ne\s+pas|do\s+not|don't|must\s+not|interdit|forbidden)\b")
_AFFIRMATION = re.compile(r"\b(toujours|always|tu\s+dois|dois|must|il\s+faut|obligatoire)\b")
_MOTS_DE_LIAISON = frozenset(
    "toujours jamais always never ne pas do not don't must tu dois il faut interdit forbidden obligatoire le la les un une des de du "
    "d' l' et ou to the an you your tes ton ta votre vous".split()
)


def _noyau(phrase: str) -> frozenset[str]:
    jetons = re.findall(r"[a-z0-9']+", normaliser(phrase))
    return frozenset(j for j in jetons if j not in _MOTS_DE_LIAISON and len(j) > 2)


def regles_contradictoires(e: Entree) -> list[Defaut]:
    defauts: list[Defaut] = []
    for n, prompt in _prompts_de_parole(e.graphe):
        unites = [(u, _noyau(u), normaliser(u)) for u in _unites(prompt)]
        for i, (a, noyau_a, norm_a) in enumerate(unites):
            for b, noyau_b, norm_b in unites[i + 1 :]:
                if len(noyau_a) < 3 or len(noyau_b) < 3:
                    continue
                if len(noyau_a & noyau_b) / len(noyau_a | noyau_b) < 0.75:
                    continue
                a_nie, b_nie = bool(_NEGATION.search(norm_a)), bool(_NEGATION.search(norm_b))
                a_affirme, b_affirme = bool(_AFFIRMATION.search(norm_a)), bool(_AFFIRMATION.search(norm_b))
                if (a_nie and b_affirme and not b_nie) or (b_nie and a_affirme and not a_nie):
                    defauts.append(Defaut("regles_contradictoires", BLOQUANT, "Two rules say the opposite.", _nom(n), f"{a[:60]} / {b[:60]}"))
    return defauts


# --- 3. nom d'outil dans le texte ----------------------------------------------------------------------------------


def nom_d_outil_dans_le_texte(e: Entree) -> list[Defaut]:
    noms = {o.nom for o in e.outils.values() if o.nom} | set(e.noms_d_outils_du_moteur)
    defauts: list[Defaut] = []
    for n, prompt in _prompts_de_parole(e.graphe):
        # [.mark] Lot 8 (décision du 04/11) : une étiquette {{outil:…}} n'est pas un nom écrit en clair ; le nom brut reste refusé.
        prompt = sans_etiquettes(prompt)
        for nom in sorted(noms):
            if re.search(rf"(?<![\w]){re.escape(nom)}(?![\w])", prompt, flags=re.IGNORECASE):
                defauts.append(
                    Defaut("nom_d_outil_dans_le_texte", BLOQUANT, "A tool name is written in the prompt: the model may say it aloud.", _nom(n), nom)
                )
    return defauts


# --- 4. exemple de valeur ------------------------------------------------------------------------------------------

_VALEURS = (
    ("an e-mail address", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("a phone number or a long number", re.compile(r"(?<![\w.])(?:\+?\d[\d .-]{6,}\d)(?![\w])")),
    ("a date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("a quoted example", re.compile(r"(?:par exemple|ex\.|e\.g\.|for example|for instance)\s*:?\s*[«\"“'][^»\"”']{2,}[»\"”']", re.IGNORECASE)),
)


def exemple_de_valeur(e: Entree) -> list[Defaut]:
    defauts: list[Defaut] = []
    for n, prompt in _prompts_de_parole(e.graphe):
        sans_variables = re.sub(r"\{\{[^}]*\}\}", " ", prompt)
        for genre, motif in _VALEURS:
            m = motif.search(sans_variables)
            if m:
                defauts.append(
                    Defaut(
                        "exemple_de_valeur", BLOQUANT, f"The prompt gives {genre} as an example: the model copies it.", _nom(n), m.group(0)[:60], {"genre": genre}
                    )
                )
    return defauts


# --- 5. outil sans consigne d'échec --------------------------------------------------------------------------------

_ECHEC = re.compile(
    r"(echou|erreur|indisponible|ne repond pas|pas de reponse|impossible|incident|panne|\bfail|\berror|unavailable|not respond|doesn't respond|"
    r"si l'outil|if the tool|en cas de|repli|rappel|call back|callback)"
)


def _outils_de(noeud: dict[str, Any]) -> list[str]:
    uuids = _donnees(noeud).get("tool_uuids")
    return [u for u in uuids if isinstance(u, str)] if isinstance(uuids, list) else []


def outil_sans_consigne_d_echec(e: Entree) -> list[Defaut]:
    return [
        Defaut("outil_sans_consigne_d_echec", BLOQUANT, "The step has tools but no instruction for when a tool fails or does not answer.", _nom(n))
        for n in _noeuds(e.graphe)
        if _outils_de(n) and not _ECHEC.search(normaliser(_prompt(n)))
    ]


# --- 6. étape sans sortie vers la fin ------------------------------------------------------------------------------


def etape_sans_sortie(e: Entree) -> list[Defaut]:
    noeuds = {str(n.get("id")): n for n in _noeuds(e.graphe) if n.get("type") in ("startCall", "agentNode", "endCall")}
    if not noeuds:
        return []
    sortants: dict[str, list[str]] = {i: [] for i in noeuds}
    for liaison in e.graphe.get("edges") or []:
        if isinstance(liaison, dict) and str(liaison.get("source")) in noeuds:
            sortants[str(liaison["source"])].append(str(liaison.get("target")))
    fins = {i for i, n in noeuds.items() if n.get("type") == "endCall" or _donnees(n).get("is_end")}
    if not fins:
        return [Defaut("etape_sans_sortie", BLOQUANT, "The graph has no end step.", parametres={"cas": "pas_de_fin"})]
    atteint = set(fins)
    change = True
    while change:
        change = False
        for i, cibles in sortants.items():
            if i not in atteint and any(c in atteint for c in cibles):
                atteint.add(i)
                change = True
    defauts = []
    for i, n in noeuds.items():
        donnees = _donnees(n)
        if i in atteint or donnees.get("retour_au_principal") or donnees.get("travail_de_fond"):
            continue
        defauts.append(Defaut("etape_sans_sortie", BLOQUANT, "No path leads from this step to the end of the call.", _nom(n), parametres={"cas": "pas_de_chemin"}))
    return defauts


# --- 7. longueur -----------------------------------------------------------------------------------------------------


def longueur(e: Entree) -> list[Defaut]:
    """Un avertissement (jamais un blocage) : le plafond est celui du cerveau (Réglages › Briques), vide = aucun seuil = muette."""
    if not e.plafond:
        return []
    return [
        Defaut(
            "longueur",
            AVERTISSEMENT,
            f"The prompt is {len(p)} characters long, above the ceiling of {e.plafond}.",
            _nom(n),
            parametres={"longueur": len(p), "plafond": e.plafond},
        )
        for n, p in _prompts_de_parole(e.graphe)
        if len(p) > e.plafond
    ]


# --- 8. persona qui contient une règle de conduite ---------------------------------------------------------------------

_CONDUITE = re.compile(
    r"\b(ne\s+(?:\w+\s+)?jamais|jamais|toujours|tu\s+dois|vous\s+devez|il\s+faut|interdit|obligatoire|never|always|you\s+must|must|do\s+not|don't)\b"
)
_TITRE = re.compile(r"^\s*(?:#{1,6}\s*|\[|\*\*)\s*([^\n\]*#:]{1,40}?)\s*(?:\]|\*\*|:)?\s*$|^\s*([^\n\]*#:.]{1,40}?)\s*:\s*$")


def _titre_de(ligne: str) -> str | None:
    m = _TITRE.match(ligne)
    return normaliser(m.group(1) or m.group(2)) if m else None


def sections_persona(graphe: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Les passages « persona » : un titre « persona » jusqu'au titre suivant, ou tout le nœud global nommé « persona »."""
    sortie: list[tuple[dict[str, Any], str]] = []
    for n in _noeuds(graphe):
        prompt = _prompt(n)
        if not prompt:
            continue
        if n.get("type") == "globalNode" and normaliser(_nom(n)) == "persona":
            sortie.append((n, prompt))
            continue
        courant: list[str] | None = None
        for ligne in prompt.splitlines():
            titre = _titre_de(ligne)
            if titre is not None:
                if courant:
                    sortie.append((n, "\n".join(courant)))
                courant = [] if titre == "persona" else None
            elif courant is not None:
                courant.append(ligne)
        if courant:
            sortie.append((n, "\n".join(courant)))
    return sortie


def persona_avec_regle_de_conduite(e: Entree) -> list[Defaut]:
    defauts = []
    for n, texte in sections_persona(e.graphe):
        for ligne in texte.splitlines():
            if _CONDUITE.search(normaliser(ligne)):
                defauts.append(Defaut("persona_avec_regle", BLOQUANT, "The persona holds a rule of conduct: a persona is style only.", _nom(n), ligne.strip()[:120]))
                break
    return defauts


# --- 9. phrase dite par le code écrite aussi dans un prompt (B34) --------------------------------------------------------


def phrase_du_code_dans_un_prompt(e: Entree) -> list[Defaut]:
    phrases = {normaliser(p).rstrip(" .!?;:"): p for p in e.phrases_du_code if len(normaliser(p)) >= LONGUEUR_MIN_D_UNE_PHRASE}
    defauts = []
    for n, prompt in _prompts_de_parole(e.graphe):
        texte = normaliser(prompt)
        for cle, phrase in phrases.items():
            if cle in texte:
                defauts.append(Defaut("phrase_du_code_dans_un_prompt", BLOQUANT, "A sentence the code says is also written in a prompt.", _nom(n), phrase[:120]))
    return defauts


# --- 10. avertissements : outil d'écriture sans relecture, genre de la voix ------------------------------------------------

_RELECTURE = re.compile(
    r"(relis|relire|relecture|reformul|recapitul|confirm|valide|verifi|read back|read it back|recap|double-check|"
    r"avant d'(?:agir|envoyer|enregistrer|valider)|before (?:acting|sending|saving))"
)
_METHODES_D_ECRITURE = ("POST", "PUT", "PATCH", "DELETE")


def outil_d_ecriture_sans_relecture(e: Entree) -> list[Defaut]:
    defauts = []
    for n in _noeuds(e.graphe):
        ecrivains = [e.outils[u].nom for u in _outils_de(n) if u in e.outils and (e.outils[u].methode or "").upper() in _METHODES_D_ECRITURE]
        if ecrivains and not _RELECTURE.search(normaliser(_prompt(n))):
            defauts.append(
                Defaut(
                    "outil_d_ecriture_sans_relecture",
                    AVERTISSEMENT,
                    "A tool that writes is offered without a read-back in two steps (read what is about to be done, act only on a yes).",
                    _nom(n),
                    ", ".join(ecrivains),
                )
            )
    return defauts


_FEMININ = re.compile(r"\b(ravie|enchantee|prete|contente|desolee|heureuse|certaine|sure|attentive|une assistante|une conseillere|une secretaire)\b")
_MASCULIN = re.compile(r"\b(ravi|enchante|pret|content|desole|heureux|certain|attentif|un assistant|un conseiller|un secretaire)\b")


def genre_du_persona(texte: str) -> str | None:
    n = normaliser(texte)
    f, m = len(_FEMININ.findall(n)), len(_MASCULIN.findall(n))
    if f > m:
        return "f"
    if m > f:
        return "m"
    return None


def genre_persona_contre_voix(e: Entree) -> list[Defaut]:
    if e.genre_de_la_voix not in ("f", "m"):
        return []
    return [
        Defaut("genre_persona_voix", AVERTISSEMENT, "The persona's agreements are not in the gender of the chosen voice.", _nom(n))
        for n, texte in sections_persona(e.graphe)
        if genre_du_persona(texte) not in (None, e.genre_de_la_voix)
    ]


# --- 11. {{nom}} inconnu (B49) ----------------------------------------------------------------------------------------------


def variables_ecrites(prompt: str) -> list[str]:
    # [.mark] Lot 8 : une étiquette d'objet n'est pas une variable (contrôle « Étiquettes des prompts » de la publication).
    return [m.group(1) for m in re.finditer(TEMPLATE_VAR_PATTERN, prompt) if not est_une_etiquette(m.group(1))]


def variable_connue(nom: str, e: Entree, noms_des_objets: set[str]) -> bool:
    if is_builtin_variable(nom) or nom.startswith(PREFIXES_DU_CONTEXTE):
        return True
    return nom in noms_des_objets or nom.split(".")[0] in noms_des_objets or nom in e.variables_posees_par_le_code or nom in e.variables_de_l_agent


def variable_inconnue(e: Entree) -> list[Defaut]:
    noms_objets = {o.nom for o in e.objets or []}
    defauts: list[Defaut] = []
    for n, prompt in _prompts_de_parole(e.graphe):
        vus: set[str] = set()
        for nom in variables_ecrites(prompt):
            if nom in vus or variable_connue(nom, e, noms_objets):
                continue
            vus.add(nom)
            if e.objets is None:
                # La base du client ne répond pas : le moteur laisse le {{nom}} écrit tel quel et l'appel continue.
                defauts.append(
                    Defaut(
                        "variable_non_verifiee",
                        AVERTISSEMENT,
                        "The client's database did not answer: this variable could not be checked against the objects.",
                        _nom(n),
                        "{{" + nom + "}}",
                    )
                )
            else:
                defauts.append(
                    Defaut("variable_inconnue", BLOQUANT, "This variable is neither an object of the agent nor a variable the code sets.", _nom(n), "{{" + nom + "}}")
                )
    return defauts


# --- 12. fait en dur doublé d'un objet (B49) ----------------------------------------------------------------------------------


def fait_en_dur(e: Entree) -> list[Defaut]:
    defauts = []
    for objet in e.objets or []:
        morceaux = {normaliser(objet.texte)}
        for ligne in objet.texte.splitlines():
            morceaux.add(normaliser(ligne))
            morceaux |= {normaliser(c) for c in ligne.split(" | ")}
        morceaux = {m for m in morceaux if len(m) >= LONGUEUR_MIN_D_UN_FAIT}
        for n, prompt in _prompts_de_parole(e.graphe):
            texte = normaliser(re.sub(r"\{\{[^}]*\}\}", " ", prompt))
            trouve = next((m for m in sorted(morceaux, key=len, reverse=True) if m in texte), None)
            if trouve:
                defauts.append(
                    Defaut(
                        "fait_en_dur",
                        AVERTISSEMENT,
                        f"A fact is written in the prompt while the object « {objet.nom} » holds it: use {{{{{objet.nom}}}}}.",
                        _nom(n),
                        trouve[:80],
                        {"objet": objet.nom},
                    )
                )
    return defauts


# --- 13. contrôles de rédaction K1 à K5 (lot « façon Tala par motif ») -------------------------------------------------------
# Une bonne pratique ne bloque jamais seule (décision du 04/11) : AVERTISSEMENT par défaut. Chaque contrôle a sa position dans
# ``publication.controles`` (Éteint · Prévient · Bloque), lue dans ``Entree.redaction`` : « Éteint » = aucun défaut, « Bloque » =
# BLOQUANT. K5 (le poids) n'a que Éteint et Prévient.

K1, K2, K3, K4, K5 = "valeur_en_dur", "verbe_ecran", "action_sans_outil", "sortie_non_citee", "poids_agent"
CODES_DE_REDACTION = (K1, K2, K3, K4, K5)


def _gravite_de(e: Entree, code: str) -> str | None:
    """``None`` : le contrôle est éteint (aucun défaut). Sinon la gravité que sa position donne."""
    position = e.redaction.get(code, "previent")
    if position == "eteint":
        return None
    return BLOQUANT if position == "bloque" and code != K5 else AVERTISSEMENT


_MONTANT = re.compile(r"(?<![\w{])\d[\d  .,]*\s?(?:€|euros?\b|eur\b|\$|dollars?\b)", re.IGNORECASE)
_DELAI = re.compile(r"(?<![\w{.])\d+\s?(?:jours?|heures?|minutes?|semaines?|mois|secondes?|hours?|days?|weeks?|months?)\b", re.IGNORECASE)
_PRENOM_EN_EXEMPLE = re.compile(r"(?:par exemple|ex\.|e\.g\.|for example|for instance)\s*:?\s*(?:de\s+|comme\s+)?([A-ZÉÈÀ][a-zéèêàïîô-]{2,})")


def valeur_en_dur(e: Entree) -> list[Defaut]:
    """K1 : un montant, un délai chiffré ou un prénom donné « par exemple » dans un prompt. Complète ``exemple_de_valeur`` (adresse,
    numéro, date, exemple entre guillemets) et ``fait_en_dur`` (texte d'un objet), sans les remplacer."""
    gravite = _gravite_de(e, K1)
    if gravite is None:
        return []
    defauts = []
    for n, prompt in _prompts_de_parole(e.graphe):
        sans_variables = re.sub(r"\{\{[^}]*\}\}", " ", prompt)
        for genre, motif in (("an amount", _MONTANT), ("a figure delay", _DELAI), ("a first name given as an example", _PRENOM_EN_EXEMPLE)):
            m = motif.search(sans_variables)
            if m:
                defauts.append(
                    Defaut(
                        K1,
                        gravite,
                        f"The prompt writes {genre} in the text: a value that changes belongs in a variable or an object.",
                        _nom(n),
                        m.group(0).strip()[:60],
                        {"genre": genre},
                    )
                )
    return defauts


_VERBE_ECRAN = re.compile(
    r"(?<![\w])(affich\w*|s'affich\w*|clique\w*|cliqu\w*|clic|a l'ecran|sur l'ecran|l'ecran|ecran|display\w*|click\w*|on screen|on the screen|on-screen)(?![\w])"
)


def verbe_ecran(e: Entree) -> list[Defaut]:
    """K2 : un verbe d'écran (afficher, cliquer, à l'écran) dans le prompt d'un agent vocal : la personne n'a pas d'écran."""
    gravite = _gravite_de(e, K2)
    if gravite is None:
        return []
    defauts = []
    for n, prompt in _prompts_de_parole(e.graphe):
        m = _VERBE_ECRAN.search(normaliser(sans_etiquettes(prompt)))
        if m:
            defauts.append(Defaut(K2, gravite, "A screen verb is written in a voice prompt: the caller has no screen.", _nom(n), m.group(0)[:60]))
    return defauts


_ACTION = re.compile(
    r"(?<![\w])(enregistr\w*|reserv\w*|annul\w*|envoi\w*|envoy\w*|notez? dans|noter dans|inscri\w*|supprim\w*|deplac\w*|"
    r"book\w*|cancel\w*|save\w*|send\w*|schedule\w*)(?![\w])"
)


def _outil_qui_ecrit(e: Entree, uuid: str) -> bool:
    outil = e.outils.get(uuid)
    if outil is None:
        return False
    if (outil.categorie or "http_api") == "http_api":
        return (outil.methode or "").upper() in _METHODES_D_ECRITURE
    return True  # transfert, outil natif ou serveur d'outils : on ne devine pas qu'il se contente de lire


def action_sans_outil(e: Entree) -> list[Defaut]:
    """K3 : « enregistrer, réserver, annuler, envoyer, noter dans » dans une étape sans aucun outil qui écrit. Étend
    ``outil_d_ecriture_sans_relecture`` (un outil qui écrit sans relecture) au cas inverse : l'action est promise, aucun outil ne la fait."""
    gravite = _gravite_de(e, K3)
    if gravite is None:
        return []
    defauts = []
    for n in _noeuds(e.graphe):
        if n.get("type") not in ("startCall", "agentNode"):
            continue
        m = _ACTION.search(normaliser(sans_etiquettes(_prompt(n))))
        if m and not any(_outil_qui_ecrit(e, u) for u in _outils_de(n)):
            defauts.append(
                Defaut(K3, gravite, "The step promises an action but has no tool that writes: the model would say it did it.", _nom(n), m.group(0)[:60])
            )
    return defauts


def sortie_non_citee(e: Entree) -> list[Defaut]:
    """K4 : une étape à deux sorties de travail ou plus dont le texte ne cite aucune étape visée (ni son nom, ni le libellé de la liaison)."""
    gravite = _gravite_de(e, K4)
    if gravite is None:
        return []
    noeuds = {str(n.get("id")): n for n in _noeuds(e.graphe)}
    sortantes: dict[str, list[dict[str, Any]]] = {}
    for liaison in e.graphe.get("edges") or []:
        if isinstance(liaison, dict):
            cible = noeuds.get(str(liaison.get("target")))
            if cible is not None and cible.get("type") == "agentNode" and not _donnees(cible).get("is_end"):
                sortantes.setdefault(str(liaison.get("source")), []).append(liaison)
    defauts = []
    for identifiant, liaisons in sortantes.items():
        origine = noeuds.get(identifiant)
        if origine is None or len(liaisons) < 2:
            continue
        texte = normaliser(sans_etiquettes(_prompt(origine)))
        citees = []
        for liaison in liaisons:
            cibles = [_nom(noeuds[str(liaison.get("target"))]), str((liaison.get("data") or {}).get("label") or "")]
            citees.append(any(len(normaliser(c)) >= 3 and normaliser(c) in texte for c in cibles))
        if not any(citees):
            visees = ", ".join(_nom(noeuds[str(item.get("target"))]) for item in liaisons)
            defauts.append(Defaut(K4, gravite, "The step has several work exits but its text names none of them.", _nom(origine), visees[:80]))
    return defauts


@dataclass
class PoidsDUneEtape:
    """Ce que le cerveau lit à chaque réplique dans une étape : le prompt général, celui de l'étape, les conditions de ses sorties."""

    etape: str
    noeud_id: str
    general: int
    texte: int
    conditions: int
    nb_conditions: int

    @property
    def total(self) -> int:
        return self.general + self.texte + self.conditions

    def en_json(self) -> dict[str, Any]:
        return {
            "etape": self.etape,
            "noeud_id": self.noeud_id,
            "general": self.general,
            "texte": self.texte,
            "conditions": self.conditions,
            "nb_conditions": self.nb_conditions,
            "total": self.total,
        }


def poids_par_etape(graphe: dict[str, Any]) -> list[PoidsDUneEtape]:
    """K5 : le poids de chaque étape, calculé sur les VRAIS textes (caractères), du plus lourd au plus léger. L'historique de l'appel,
    qui vient en plus, n'est pas compté. Le prompt général n'entre que dans une étape qui le lit (``add_global_prompt`` non faux)."""
    general = _global(graphe)
    longueur_generale = len(_prompt(general)) if general else 0
    sortantes: dict[str, list[dict[str, Any]]] = {}
    for liaison in graphe.get("edges") or []:
        if isinstance(liaison, dict):
            sortantes.setdefault(str(liaison.get("source")), []).append(liaison.get("data") if isinstance(liaison.get("data"), dict) else {})
    lignes = []
    for n in _noeuds(graphe):
        if n.get("type") not in ("startCall", "agentNode", "endCall"):
            continue
        liees = sortantes.get(str(n.get("id")), [])
        lit_le_general = _donnees(n).get("add_global_prompt") is not False
        lignes.append(
            PoidsDUneEtape(
                etape=_nom(n),
                noeud_id=str(n.get("id")),
                general=longueur_generale if lit_le_general else 0,
                texte=len(_prompt(n)),
                conditions=sum(len(str(d.get("condition") or "")) + len(str(d.get("label") or "")) for d in liees),
                nb_conditions=len(liees),
            )
        )
    return sorted(lignes, key=lambda p: p.total, reverse=True)


def poids_agent(e: Entree) -> list[Defaut]:
    """K5 : informe, ne contraint jamais. Sans seuil (``cerveau_poids_max`` vide) aucun défaut : l'écran montre les nombres seuls."""
    if _gravite_de(e, K5) is None or not e.poids_max:
        return []
    return [
        Defaut(
            K5,
            AVERTISSEMENT,
            f"The brain reads {p.total} characters at each reply in this step, above the threshold of {e.poids_max}.",
            p.etape,
            str(p.total),
            {"total": p.total, "seuil": e.poids_max},
        )
        for p in poids_par_etape(e.graphe)
        if p.total > e.poids_max
    ]


REGLES = (
    regle_en_double,
    regles_contradictoires,
    nom_d_outil_dans_le_texte,
    exemple_de_valeur,
    outil_sans_consigne_d_echec,
    etape_sans_sortie,
    longueur,
    persona_avec_regle_de_conduite,
    phrase_du_code_dans_un_prompt,
    variable_inconnue,
    outil_d_ecriture_sans_relecture,
    genre_persona_contre_voix,
    fait_en_dur,
    valeur_en_dur,
    verbe_ecran,
    action_sans_outil,
    sortie_non_citee,
    poids_agent,
)


def controler(e: Entree) -> list[Defaut]:
    defauts: list[Defaut] = []
    for regle in REGLES:
        defauts.extend(regle(e))
    return defauts
