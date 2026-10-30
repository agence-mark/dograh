"""[.mark] Ce que le cerveau écrit en texte et qui n'est pas une parole.

Rejeu du 16/10 après D1 (run 1410, Mistral Small chez Scaleway), deux répliques dites à voix
haute :

- « [TOOL_CALLS]fin » suivi de la phrase d'au revoir : le modèle a écrit dans son format natif
  d'appel d'outil ce qui était une porte de l'étape (« → fin ») ; le fournisseur l'a laissé en
  texte (même famille que la réponse avalée, ``reponse_avalee.py``) ;
- une indication de scène entre crochets avant la phrase (le modèle imite les notes entre
  crochets que le code lui montre, comme l'état de la fiche).

Ce module transforme le flux du cerveau, avant la trace, le lecteur de portes, la voix et
l'historique (téléphone et clavier) :

- un appel écrit dans un format natif (Mistral ``[TOOL_CALLS]``, Qwen ``<tool_call>``) qui
  nomme un **outil déclaré** de la requête devient un vrai appel d'outil (le texte d'avant
  reste dit, rien n'est dit après) ;
- s'il nomme autre chose et que l'agent prend ses portes dans la réponse (la consigne porte
  la flèche ``→``), il devient la ligne de porte ``→ nom`` suivie du reste : le lecteur de
  portes la lit comme toute porte écrite (porte inconnue comprise : relancée une fois) ;
- sinon le jeton et le nom sont retirés ;
- un texte entre crochets n'est jamais dit ni gardé (journalisé), SAUF une balise d'expression de la liste
  permise de la voix Soniox (lot 5 ter de voix-soniox, D29 : ``FluxNettoye(..., balises_permises)``, liste posée
  par ``poser_les_balises_du_cerveau``) ; sans liste, comme avant ; un crochet jamais fermé
  dans les 160 caractères qui suivent est rendu tel quel ;
- C2 (tri du 17/10, Large 3) : une didascalie en italique entre parenthèses, ``*(…)*``, suit la
  même règle que les crochets (« *(Je le relis une fois noté.)* » était dite à voix haute). Sauf
  si elle porte une flèche ``→`` : c'est alors une porte habillée (« *(→ retour)* »), laissée au
  lecteur de portes (C1) ;
- C6 (tri du 17/10, Small 3.2) : l'en-tête de la fiche, ``[Fiche de l'appel : pour toi seulement…]``,
  est lu à voix haute quand le modèle le recopie, parce qu'il dépasse les 160 caractères des
  crochets ordinaires. Il est retiré **quelle que soit sa longueur** ; resté ouvert jusqu'à la fin
  du flux, tout ce qui suit son ouverture est retiré (c'est la fiche, jamais une parole).

- agent-facon-tala (C1, case ``reconnaitre_un_outil_ecrit``, éteinte par défaut) : une réplique qui n'est **que**
  le nom d'un outil déclaré à ce tour (nu ou habillé : tirets bas, italiques, ponctuation, arguments
  ``nom,{...}`` ou ``nom_demande="…"``) devient l'appel de cet outil : jamais dite, jamais gardée dans
  l'historique (casque 2469 : le mot gardé était imité six fois). Une réplique qui contient du vrai texte en plus
  n'est pas touchée. Voir ``lire_un_outil_ecrit`` et ``FluxOutilEcrit``.

⚠️ Latence, cas rares seulement : un « [ » ouvert retient la voix jusqu'à sa fermeture (au plus
160 caractères) ; après un jeton d'appel, le reste de la réponse part à la fin du flux.

⛔ Ne lève jamais à la place du service : une erreur rend le flux d'origine. Un flux sans
crochet ni jeton passe tel quel, morceau par morceau, sans retard.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Iterable

from loguru import logger

from api.services.pipecat.balises_expression import nom_de_balise
from api.services.workflow.porte_parlee import FLECHE

# C1 : posé sur le service de l'agent (vrai/faux) à chaque requête par ``avant_la_requete``, selon la case de l'agent.
ATTRIBUT_OUTIL_ECRIT = "_mark_outil_ecrit_reconnu"
CLE_OUTIL_ECRIT = "reconnaitre_un_outil_ecrit"
ATTRIBUT_DERNIERS_OUTILS = "_mark_derniers_outils"
JETONS_D_APPEL = ("[TOOL_CALLS]", "<tool_call>")
_LONGUEUR_MAX_CROCHETS = 160
_NOM = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*")
# C6 : le début de l'en-tête de la fiche que le code montre au modèle (``fiche_au_fil_de_leau.ENTETE_ETAT*``,
# gardé identique par un test).
DEBUT_ENTETE_FICHE = "[Fiche de l'appel"
_ENTETE_FICHE = re.compile(re.escape(DEBUT_ENTETE_FICHE) + r"[^\]]*\]\s*")
# C2 : une didascalie « *(…)* » (jamais une porte : pas de flèche dedans).
_DIDASCALIE = re.compile(
    r"\*\((?:(?!%s)[^()\n]){1,%d}\)\*\s*" % (re.escape(FLECHE), _LONGUEUR_MAX_CROCHETS)
)
_DIDASCALIE_OUVERTE = re.compile(
    r"\*\((?:(?!%s)[^()\n]){0,%d}\)?$" % (re.escape(FLECHE), _LONGUEUR_MAX_CROCHETS)
)


def _delta(morceau: Any) -> Any:
    choix = getattr(morceau, "choices", None) or []
    return getattr(choix[0], "delta", None) if choix else None


def _texte(morceau: Any) -> str | None:
    delta = _delta(morceau)
    contenu = getattr(delta, "content", None) if delta is not None else None
    return contenu if isinstance(contenu, str) else None


def _avec_texte(morceau: Any, texte: str) -> Any:
    """Le même morceau, son texte remplacé (copie : le morceau d'origine n'est pas touché)."""
    choix = morceau.choices[0]
    delta = choix.delta.model_copy(update={"content": texte})
    return morceau.model_copy(update={"choices": [choix.model_copy(update={"delta": delta})]})


def _morceau_d_appel(modele: Any, nom: str, arguments: str, index: int = 0) -> Any:
    from openai.types.chat.chat_completion_chunk import (
        ChatCompletionChunk,
        Choice,
        ChoiceDelta,
        ChoiceDeltaToolCall,
        ChoiceDeltaToolCallFunction,
    )

    return ChatCompletionChunk(
        id=getattr(modele, "id", None) or "appel-ecrit",
        created=int(getattr(modele, "created", None) or time.time()),
        model=getattr(modele, "model", None) or "",
        object="chat.completion.chunk",
        choices=[
            Choice(
                index=0,
                delta=ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=index,
                            id=f"ecrit-{int(time.time() * 1000)}-{index}",
                            type="function",
                            function=ChoiceDeltaToolCallFunction(name=nom, arguments=arguments),
                        )
                    ]
                ),
                finish_reason=None,
            )
        ],
    )


def _arguments(brut: str) -> str:
    """Les arguments JSON en tête de ``brut`` (``{}`` s'il n'y en a pas de lisibles)."""
    brut = brut.strip()
    if brut.startswith("{"):
        try:
            valeur, _ = json.JSONDecoder().raw_decode(brut)
            if isinstance(valeur, dict):
                return json.dumps(valeur, ensure_ascii=False)
        except ValueError:
            pass
    return "{}"


def _arguments_et_reste(texte: str) -> tuple[str, str]:
    """Un objet JSON en tête de ``texte`` (sinon ``{}``), et ce qui le suit."""
    brut = texte.lstrip()
    if brut.startswith("{"):
        try:
            valeur, fin = json.JSONDecoder().raw_decode(brut)
            if isinstance(valeur, dict):
                return json.dumps(valeur, ensure_ascii=False), brut[fin:]
        except ValueError:
            pass
    return "{}", texte


def lire_l_appel(apres_le_jeton: str, jeton: str) -> tuple[str | None, str, str]:
    """Ce qui suit un jeton d'appel : (nom, arguments JSON, reste du texte).

    Formes lues : ``nom[ARGS]{…}``, ``nom{…}``, ``[{"name": …, "arguments": …}]`` (Mistral) ;
    ``{"name": …, "arguments": …}</tool_call>`` (Qwen). ``nom`` à ``None`` : illisible."""
    texte = apres_le_jeton
    if jeton == "<tool_call>":
        corps, _, reste = texte.partition("</tool_call>")
        try:
            valeur = json.loads(corps.strip())
            nom = valeur.get("name")
            args = valeur.get("arguments") or {}
            if isinstance(args, str):
                return (nom if isinstance(nom, str) else None), _arguments(args), reste
            return (nom if isinstance(nom, str) else None), json.dumps(args, ensure_ascii=False), reste
        except (ValueError, AttributeError):
            return None, "{}", reste
    texte = texte.lstrip()
    if texte.startswith("["):
        try:
            valeur, fin = json.JSONDecoder().raw_decode(texte)
            premier = valeur[0] if isinstance(valeur, list) and valeur else {}
            nom = premier.get("name")
            args = premier.get("arguments") or {}
            args = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
            return (nom if isinstance(nom, str) else None), _arguments(args), texte[fin:]
        except (ValueError, AttributeError, IndexError):
            return None, "{}", texte
    correspondance = _NOM.match(texte)
    if correspondance is None:
        return None, "{}", texte
    nom = correspondance.group(0)
    reste = texte[correspondance.end():]
    if reste.startswith("[ARGS]"):
        reste = reste[len("[ARGS]"):]
    arguments, reste = _arguments_et_reste(reste)
    return nom, arguments, reste


def _debut_de_jeton(texte: str) -> bool:
    """Le texte finit-il par le début d'un jeton d'appel (« <tool », « [TOOL_C »…) ?"""
    return any(
        texte.endswith(jeton[:k]) for jeton in JETONS_D_APPEL for k in range(1, len(jeton))
    )


def _appels_en_liste(apres_le_jeton: str) -> list[tuple[str, str]] | None:
    """La forme liste de Mistral, ``[{"name": …, "arguments": …}, …]`` : tous ses appels."""
    texte = apres_le_jeton.lstrip()
    if not texte.startswith("["):
        return None
    try:
        valeur, _ = json.JSONDecoder().raw_decode(texte)
    except ValueError:
        return None
    appels = []
    for element in valeur if isinstance(valeur, list) else []:
        if isinstance(element, dict) and isinstance(element.get("name"), str):
            args = element.get("arguments") or {}
            appels.append(
                (element["name"], args if isinstance(args, str) else json.dumps(args, ensure_ascii=False))
            )
    return appels or None


def sans_didascalies(texte: str) -> str:
    """C2 : ``texte`` sans ses didascalies ``*(…)*`` fermées (et l'espace qui les suit)."""
    return _DIDASCALIE.sub("", texte)


_CROCHETS_FERMES = re.compile(r"\[([^\[\]\n]{0,%d})\]\s*" % _LONGUEUR_MAX_CROCHETS)


def sans_crochets(texte: str, permises: Iterable[str] = ()) -> str:
    """``texte`` sans ses passages entre crochets fermés (et l'espace qui les suit), puis
    sans ses didascalies en italique (C2).

    Lot 5 ter (voix-soniox, D29) : une balise d'expression de ``permises`` (noms comparés sans
    crochets, casse ignorée) est GARDÉE telle qu'écrite, espace compris ; tout autre crochet est
    retiré comme avant. ``permises`` vide : exactement le comportement d'avant."""
    gardees = frozenset(permises)

    def _retirer(m: re.Match) -> str:
        return m.group(0) if gardees and nom_de_balise(m.group(1)) in gardees else ""

    return sans_didascalies(_CROCHETS_FERMES.sub(_retirer, _ENTETE_FICHE.sub("", texte)))


def _crochet_ouvert(texte: str, permises: frozenset) -> int:
    """Position du dernier « [ » qui n'est pas une balise permise complète (-1 sinon). Sans balise
    permise : ``texte.rfind("[")``, comme avant."""
    position = texte.rfind("[")
    while position >= 0 and permises:
        m = _CROCHETS_FERMES.match(texte, position)
        if m is None or nom_de_balise(m.group(1)) not in permises:
            break
        position = texte.rfind("[", 0, position)
    return position


def sans_entete_ouvert(texte: str) -> str:
    """C6 : l'en-tête de la fiche resté ouvert à la fin du flux : tout ce qui suit son
    ouverture est retiré."""
    debut = texte.find(DEBUT_ENTETE_FICHE)
    if debut < 0:
        return texte
    logger.warning(f"[cerveau] en-tête de la fiche jamais fermé, retiré : {texte[debut:debut + 80]!r}")
    return texte[:debut]


def _didascalie_en_attente(texte: str) -> bool:
    """C2 : le texte finit-il sur une didascalie encore ouverte (« *( … » sans « )* »), ou sur
    une étoile seule, début possible de « *( » dans le morceau suivant ?"""
    return texte.endswith("*") or _DIDASCALIE_OUVERTE.search(texte) is not None


# --- correctifs-apres-banc-v4, lot 2 (6.5) : les lignes internes lues à voix haute -------------
#
# Run 1479 : le modèle imite le format du bloc de fiche (« Noté : … », « Encore attendu : … ») et la
# voix le lit. Une ligne de réplique qui COMMENCE par une étiquette du bloc est retirée avant la voix,
# la trace et l'historique. Les étiquettes sont lues dans le code qui écrit le bloc
# (``fiche_au_fil_de_leau.etiquettes_du_bloc``). Une phrase normale qui contient « noté » reste : seule
# l'étiquette en début de ligne, suivie de son deux-points, est coupée.

_INTERNE, _PEUT_ETRE, _NORMAL = "interne", "peut_etre", "normal"


def _classer_le_debut_de_ligne(ligne: str, etiquettes: tuple[str, ...]) -> str:
    """Le début de ligne ``ligne`` est-il une étiquette interne (suivie de « : »), peut-il encore le
    devenir (un début d'étiquette), ou est-il une parole ?"""
    debut = ligne.lstrip(" \t")
    if not debut:
        return _PEUT_ETRE
    for nom in etiquettes:
        if debut.startswith(nom):
            reste = debut[len(nom):].lstrip(" \t")
            if reste.startswith(":"):
                return _INTERNE
            if not reste:
                return _PEUT_ETRE
        elif nom.startswith(debut):
            return _PEUT_ETRE
    return _NORMAL


def sans_lignes_internes(texte: str, etiquettes: tuple[str, ...] | None = None) -> str:
    """``texte`` sans ses lignes qui commencent par une étiquette du bloc de fiche (6.5)."""
    if etiquettes is None:
        from api.services.workflow.fiche_au_fil_de_leau import etiquettes_du_bloc

        etiquettes = etiquettes_du_bloc()
    return "".join(
        ligne
        for ligne in texte.splitlines(keepends=True)
        if _classer_le_debut_de_ligne(ligne.split("\n", 1)[0], etiquettes) != _INTERNE
    )


def _porte_une_fin(morceau: Any) -> bool:
    """Le morceau de texte porte-t-il aussi une fin de réponse ou un compte de jetons à ne pas perdre ?"""
    choix = getattr(morceau, "choices", None) or []
    return bool(
        (choix and getattr(choix[0], "finish_reason", None)) or getattr(morceau, "usage", None)
    )


class FluxSansLignesInternes:
    """Le flux du cerveau sans les lignes qui commencent par une étiquette du bloc de fiche (6.5).

    Un début de ligne qui pourrait encore devenir une étiquette (« No », « Encore att ») est retenu le
    temps de savoir ; une parole normale passe aussitôt, morceau par morceau. Une ligne interne est
    retirée jusqu'à son saut de ligne compris. Au bout du flux, un début de ligne resté ambigu est
    rendu tel quel. Sans étiquettes lisibles : flux d'origine."""

    def __init__(self, flux: Any):
        self._flux = flux

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        try:
            from api.services.workflow.fiche_au_fil_de_leau import etiquettes_du_bloc

            etiquettes = etiquettes_du_bloc()
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[cerveau] étiquettes du bloc illisibles, lignes internes non filtrées : {erreur!r}")
            etiquettes = ()
        if not etiquettes:
            async for morceau in self._flux:
                yield morceau
            return
        debut_de_ligne, supprime, tenu = True, False, ""
        en_attente: list[Any] = []  # morceaux sans texte (fin, jetons) arrivés pendant une retenue
        dernier: Any = None
        async for morceau in self._flux:
            texte = _texte(morceau)
            if texte is None:
                if tenu or supprime:
                    en_attente.append(morceau)
                else:
                    yield morceau
                continue
            dernier = morceau
            sortie, reste = "", texte
            while reste:
                if supprime:
                    i = reste.find("\n")
                    if i < 0:
                        reste = ""
                        break
                    reste, supprime, debut_de_ligne = reste[i + 1:], False, True
                    continue
                i = reste.find("\n")
                ligne, fin = (reste, len(reste)) if i < 0 else (reste[:i], i + 1)
                if not debut_de_ligne:
                    sortie += reste[:fin]
                    reste = reste[fin:]
                    debut_de_ligne = i >= 0
                    continue
                classe = _classer_le_debut_de_ligne(tenu + ligne, etiquettes)
                if classe == _INTERNE:
                    logger.warning(f"[cerveau] ligne interne jamais dite : {(tenu + ligne)[:80]!r}")
                    supprime, tenu = True, ""
                    continue  # le reste de la ligne est retiré par la branche ci-dessus
                if classe == _PEUT_ETRE and i < 0:
                    tenu += ligne
                    reste = ""
                    break
                sortie += tenu + reste[:fin]
                tenu, reste = "", reste[fin:]
                debut_de_ligne = i >= 0
            if sortie:
                yield _avec_texte(morceau, sortie)
            elif _porte_une_fin(morceau):
                en_attente.append(_avec_texte(morceau, ""))
            if not tenu and not supprime:
                for m in en_attente:
                    yield m
                en_attente = []
        if tenu and dernier is not None:
            yield _avec_texte(dernier, tenu)  # un début de ligne resté ambigu : une parole
        for m in en_attente:
            yield m

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


# --- agent-facon-tala, C1 : la réplique qui n'est que le nom d'un outil -----------------------
#
# Casque 2447/2449/2469 et banc local S2, S4, S5, S6, S12 : le cerveau écrit « _coordonnees_ », « *retour* » ou
# « coordonnees,{"nom": …} » AU LIEU d'appeler l'outil ; la voix le lit, et le mot resté dans l'historique est imité
# au tour suivant. Ce n'est pas un jeton d'appel natif (``JETONS_D_APPEL``) : rien ne l'annonce, seule la réplique
# entière, réduite à son noyau, porte le nom d'un outil déclaré à ce tour.

# La flèche « → » n'en fait PAS partie : une porte écrite (« → retour ») reste une porte, lue par le lecteur de portes.
_DECOR = " \t\r\n_*`'\"“”«»‘’.,;:!?()[]<>-–—…"
# Le décor entre le nom et ses arguments (le tiret bas et le guillemet en sont exclus : ils appartiennent au nom ou à la valeur).
_DECOR_APRES_LE_NOM = _DECOR.replace("_", "").replace('"', "")
_VALEUR = re.compile(r'\s*[,;]?\s*_?(\w+)\s*=\s*"([^"]*)"')
# Une suite d'arguments encore possible quand le flux n'est pas fini : paires ``clé="valeur"`` dont la dernière peut être ouverte.
_SUITE_POSSIBLE = re.compile(
    r'(?:\s*[,;]?\s*_?\w+\s*=\s*"[^"]*")*\s*[,;]?\s*(?:_?\w*(?:\s*=\s*(?:"[^"]*)?)?)?[\s_*`\'"“”.,;:!?()\]>]*'
)
_LONGUEUR_MAX_OUTIL_ECRIT = 400


def _cle_de_nom(nom: str) -> str:
    return nom.strip().lower().replace("-", "_")


def _nom_en_tete(coeur: str, outils: Iterable[str]) -> tuple[str, str] | None:
    """(outil déclaré, reste) quand ``coeur`` COMMENCE par le nom d'un outil (le plus long d'abord), sinon ``None``.
    Un nom suivi d'une lettre ou d'un chiffre n'est pas ce nom (« finalement » n'est pas « fin »)."""
    bas = coeur.lower().replace("-", "_")
    for nom in sorted(outils, key=len, reverse=True):
        cle = _cle_de_nom(nom)
        if not cle or not bas.startswith(cle):
            continue
        reste = coeur[len(cle):]
        if reste[:1].isalnum():
            continue
        return nom, reste
    return None


def _arguments_apres_le_nom(reste: str) -> str:
    return reste.lstrip(_DECOR_APRES_LE_NOM).lstrip("_").lstrip(" ,;:(")


def lire_un_outil_ecrit(texte: str, outils: Iterable[str]) -> tuple[str, str] | None:
    """(nom de l'outil, arguments JSON) quand ``texte`` n'est QUE le nom d'un outil déclaré, nu ou habillé ; sinon ``None``.

    Formes lues, entourées de tout décor (tirets bas, étoiles, guillemets, ponctuation, flèche) : ``nom`` ;
    ``nom,{"clé": "valeur"}`` ou ``nom{…}`` ; ``nom_demande="…"`` / ``nom(demande="…")`` (une clé ou plusieurs).
    Toute autre suite (du vrai texte) : ``None``, la réplique n'est pas touchée."""
    outils = list(outils)
    coeur = texte.lstrip(_DECOR)
    trouve = _nom_en_tete(coeur, outils) if coeur else None
    if trouve is None:
        return None
    nom, reste = trouve
    reste = _arguments_apres_le_nom(reste)
    if not reste.strip(_DECOR):
        return nom, "{}"
    if reste.startswith("{"):
        try:
            valeur, fin = json.JSONDecoder().raw_decode(reste)
        except ValueError:
            return None
        if isinstance(valeur, dict) and not reste[fin:].strip(_DECOR):
            return nom, json.dumps(valeur, ensure_ascii=False)
        return None
    arguments: dict[str, str] = {}
    position = 0
    while True:
        m = _VALEUR.match(reste, position)
        if m is None:
            break
        arguments[m.group(1)] = m.group(2)
        position = m.end()
    if arguments and not reste[position:].strip(_DECOR):
        return nom, json.dumps(arguments, ensure_ascii=False)
    return None


def _outil_ecrit_possible(texte: str, outils: list[str]) -> bool:
    """Le texte lu jusqu'ici peut-il encore devenir une réplique qui n'est que le nom d'un outil (le flux continue) ?"""
    if len(texte) > _LONGUEUR_MAX_OUTIL_ECRIT:
        return False
    coeur = texte.lstrip(_DECOR)
    if not coeur:
        return True  # que du décor pour l'instant
    bas = coeur.lower().replace("-", "_")
    if any(_cle_de_nom(n).startswith(bas) for n in outils):
        return True  # un début de nom
    trouve = _nom_en_tete(coeur, outils)
    if trouve is None:
        return False
    reste = _arguments_apres_le_nom(trouve[1])
    if reste.startswith("{"):
        try:
            _, fin = json.JSONDecoder().raw_decode(reste)
        except ValueError:
            return True  # JSON pas encore fermé
        return not reste[fin:].strip(_DECOR)
    return _SUITE_POSSIBLE.fullmatch(reste) is not None


def _a_un_appel(morceau: Any) -> bool:
    choix = getattr(morceau, "choices", None) or []
    delta = getattr(choix[0], "delta", None) if choix else None
    return bool(getattr(delta, "tool_calls", None))


class FluxOutilEcrit:
    """C1 : le flux (déjà nettoyé) dont la réplique, si elle n'est QUE le nom d'un outil déclaré, devient l'appel de cet outil.

    Une parole normale passe aussitôt, morceau par morceau : seul un début qui pourrait encore être un nom d'outil (ou du
    décor seul) est retenu, au plus ``_LONGUEUR_MAX_OUTIL_ECRIT`` caractères. À la fin du flux : le texte retenu est un
    outil écrit → appel d'outil à sa place, texte jamais rendu ; sinon il est rendu tel quel. Un vrai appel d'outil déjà
    présent dans le flux l'emporte (le texte est alors retiré, jamais doublé)."""

    def __init__(self, flux: Any, outils: Iterable[str]):
        self._flux = flux
        self._outils = list(outils)

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        tenus: list[Any] = []
        texte = ""
        retenu = False
        parole = False  # une parole est partie : la suite passe sans retenue
        async for morceau in self._flux:
            contenu = _texte(morceau)
            if parole:
                yield morceau
                continue
            if not retenu:
                if not contenu or not _outil_ecrit_possible(contenu, self._outils):
                    parole = parole or bool(contenu)
                    yield morceau
                    continue
                retenu = True
                texte, tenus = contenu, [morceau]
                continue
            tenus.append(morceau)
            if contenu:
                texte += contenu
                if not _outil_ecrit_possible(texte, self._outils):
                    # une parole a commencé : le texte retenu part tel quel, la suite passe sans retenue
                    for m in FluxNettoye._rendre_texte(tenus, texte):
                        yield m
                    tenus, texte, retenu, parole = [], "", False, True
        if retenu:
            for m in self._a_la_fin(tenus, texte):
                yield m

    def _a_la_fin(self, tenus: list[Any], texte: str) -> list[Any]:
        lu = lire_un_outil_ecrit(texte, self._outils)
        if lu is None:
            return FluxNettoye._rendre_texte(tenus, texte)
        nom, arguments = lu
        sans_texte = [m for m in tenus if _texte(m) is None]
        if any(_a_un_appel(m) for m in sans_texte):
            logger.warning(f"[cerveau] nom d'outil écrit « {nom} » retiré : un vrai appel est déjà là")
            return sans_texte
        premier = next((m for m in tenus if _texte(m) is not None), None)
        logger.warning(f"[cerveau] réplique qui n'est que le nom d'un outil ({texte!r}) : rendue en appel de « {nom} »")
        return [_morceau_d_appel(premier, nom, arguments)] + FluxNettoye._fin_d_appel(sans_texte)

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


class FluxNettoye:
    """Le flux du cerveau, sans appel écrit en texte ni passage entre crochets."""

    def __init__(
        self,
        flux: Any,
        outils: Iterable[str],
        portes_dans_la_reponse: bool,
        balises_permises: Iterable[str] = (),
        outil_ecrit: bool = False,
    ):
        self._flux = FluxSansLignesInternes(flux)
        # C1 : la case « reconnaître un outil écrit en texte » (éteinte : flux d'avant, à l'octet).
        self._outil_ecrit = bool(outil_ecrit)
        self._outils = set(outils)
        self._portes = portes_dans_la_reponse
        # Lot 5 ter (D29) : les balises d'expression que la voix de l'appel accepte (vide = aucune).
        self._balises = frozenset(nom_de_balise(b) for b in balises_permises if nom_de_balise(b))

    def __aiter__(self):
        if self._outil_ecrit and self._outils:
            return FluxOutilEcrit(self._parcourir(), self._outils).__aiter__()
        return self._parcourir()

    async def _parcourir(self):
        tenus: list[Any] = []  # morceaux de texte retenus (crochet ouvert ou appel écrit)
        texte_tenu = ""
        appel: str | None = None  # le jeton d'appel vu : on garde tout jusqu'à la fin
        noms_coupes: list[str] = []  # morceaux du nom après un jeton Mistral (frontières)
        fin_du_nom = False
        async for morceau in self._flux:
            texte = _texte(morceau)
            if texte is None:
                if appel is not None or tenus:
                    if appel is not None and noms_coupes and not fin_du_nom:
                        fin_du_nom = True  # un morceau sans texte ferme le nom (run 1410)
                    tenus.append(morceau)
                    continue
                yield morceau
                continue
            if appel is not None:
                if appel == "[TOOL_CALLS]" and not fin_du_nom and "".join(noms_coupes) in self._outils:
                    fin_du_nom = True  # un nom d'outil déclaré, complet : rien ne s'y colle
                if appel == "[TOOL_CALLS]" and not fin_du_nom:
                    if _NOM.fullmatch(texte) and not (noms_coupes and texte[:1].isupper()):
                        noms_coupes.append(texte)
                    else:
                        fin_du_nom = True
                texte_tenu += texte
                tenus.append(morceau)
                continue
            jeton = next((j for j in JETONS_D_APPEL if j in texte_tenu + texte), None)
            if jeton is not None:
                appel = jeton
                texte_tenu += texte
                tenus.append(morceau)
                apres = texte_tenu.split(jeton, 1)[1]
                if apres and _NOM.fullmatch(apres):
                    noms_coupes.append(apres)
                continue
            if tenus or "[" in texte or "*" in texte or _debut_de_jeton(texte):
                texte_tenu += texte
                tenus.append(morceau)
                nettoye = sans_crochets(texte_tenu, self._balises)
                if nettoye != texte_tenu:
                    logger.warning(f"[cerveau] texte entre crochets jamais dit : {texte_tenu!r}")
                    texte_tenu = nettoye
                ouvert = _crochet_ouvert(texte_tenu, self._balises)
                if ouvert >= 0 and len(texte_tenu) - ouvert <= _LONGUEUR_MAX_CROCHETS:
                    continue  # un crochet encore ouvert : on attend sa fermeture
                if DEBUT_ENTETE_FICHE in texte_tenu:
                    continue  # C6 : l'en-tête de la fiche, retenu quelle que soit sa longueur
                if _didascalie_en_attente(texte_tenu):
                    continue  # C2 : une didascalie encore ouverte : on attend sa fermeture
                if _debut_de_jeton(texte_tenu):
                    continue  # peut-être un jeton d'appel coupé en deux morceaux
                for sortie in self._rendre_texte(tenus, texte_tenu):
                    yield sortie
                tenus, texte_tenu = [], ""
                continue
            yield morceau
        if appel is not None:
            for sortie in self._rendre_l_appel(
                tenus, sans_entete_ouvert(texte_tenu), appel, noms_coupes
            ):
                yield sortie
        elif tenus:
            for sortie in self._rendre_texte(
                tenus, sans_entete_ouvert(sans_crochets(texte_tenu, self._balises))
            ):
                yield sortie

    @staticmethod
    def _rendre_texte(tenus: list[Any], texte: str) -> list[Any]:
        """Le texte retenu en un morceau (le premier morceau de texte), puis les autres
        morceaux retenus sans texte (fin, compte de jetons)."""
        sorties = []
        place = False
        for morceau in tenus:
            if _texte(morceau) is None:
                sorties.append(morceau)
            elif not place:
                place = True
                if texte:
                    sorties.append(_avec_texte(morceau, texte))
        return sorties

    def _rendre_l_appel(
        self, tenus: list[Any], texte: str, jeton: str, noms_coupes: list[str]
    ) -> list[Any]:
        avant, _, apres = texte.partition(jeton)
        appels = _appels_en_liste(apres) if jeton == "[TOOL_CALLS]" else None
        declares = [(n, a) for n, a in appels or [] if n in self._outils]
        if declares:
            if len(declares) < len(appels):
                logger.warning(
                    f"[cerveau] appels écrits en texte : {len(appels) - len(declares)} hors des outils, ignorés"
                )
            logger.warning(f"[cerveau] appels écrits en texte rendus : {[n for n, _ in declares]}")
            avant = sans_crochets(avant, self._balises)
            sorties = [_avec_texte(tenus[0], avant)] if avant.strip() else []
            sorties += [
                _morceau_d_appel(tenus[0], n, a, index=i) for i, (n, a) in enumerate(declares)
            ]
            return sorties + self._fin_d_appel([m for m in tenus if _texte(m) is None])
        coupe = "".join(noms_coupes)
        if jeton == "[TOOL_CALLS]" and coupe and apres.startswith(coupe):
            # Le nom tel que le fournisseur l'a découpé : « fin », puis un morceau vide, puis
            # « Je vous souhaite… » (run 1410) ; collé, « finJe » ne se distinguerait pas.
            nom, reste = coupe, apres[len(coupe):]
            if reste.startswith("[ARGS]"):
                reste = reste[len("[ARGS]"):]
            arguments, reste = _arguments_et_reste(reste)
        else:
            nom, arguments, reste = lire_l_appel(apres, jeton)
        avant = sans_crochets(avant, self._balises)
        sans_texte = [m for m in tenus if _texte(m) is None]
        modele = tenus[0] if tenus else None
        if nom and nom in self._outils:
            logger.warning(f"[cerveau] appel écrit en texte ({jeton}) : rendu en appel de « {nom} »")
            sorties = []
            if avant.strip():
                sorties.append(_avec_texte(tenus[0], avant))
            sorties.append(_morceau_d_appel(modele, nom, arguments))
            return sorties + self._fin_d_appel(sans_texte)
        reste = sans_crochets(reste.lstrip(), self._balises)
        if nom and self._portes:
            logger.warning(f"[cerveau] appel écrit en texte ({jeton}) : lu comme la porte « {nom} »")
            nouveau = f"{avant.rstrip()}\n{FLECHE} {nom}\n{reste}" if avant.strip() else f"{FLECHE} {nom}\n{reste}"
        else:
            logger.warning(f"[cerveau] appel écrit en texte ({jeton}) retiré : {texte!r}")
            nouveau = f"{avant}{reste}"
        return self._rendre_texte(tenus, nouveau)

    @staticmethod
    def _fin_d_appel(sans_texte: list[Any]) -> list[Any]:
        """Les morceaux sans texte retenus, la fin marquée « appel d'outil »."""
        sorties = []
        for morceau in sans_texte:
            choix = getattr(morceau, "choices", None) or []
            if choix and getattr(choix[0], "finish_reason", None):
                morceau = morceau.model_copy(
                    update={"choices": [choix[0].model_copy(update={"finish_reason": "tool_calls"})]}
                )
            elif choix and _delta(morceau) is not None and not getattr(choix[0], "finish_reason", None):
                continue  # un morceau vide du milieu : sans objet après l'appel
            sorties.append(morceau)
        return sorties

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


def case_outil_ecrit(agent: Any, moteur: Any) -> bool:
    """C1 : la case « reconnaître un outil écrit en texte » de l'agent, posée à ``True`` seulement. ⛔ Ne lève jamais."""
    try:
        reglages = getattr(agent, "reglages", None) or getattr(moteur, "reglages_appel", None) or {}
        return reglages.get(CLE_OUTIL_ECRIT) is True
    except Exception:  # noqa: BLE001
        return False


def poser_la_case_outil_ecrit(moteur: Any, llm: Any) -> None:
    """C1 : pose sur le service de l'agent actif la valeur de sa case (lue par ``TexteDuCerveauMixin`` à chaque requête).
    Téléphone et clavier passent tous deux par ``preparer_la_requete``. ⛔ Ne lève jamais."""
    try:
        setattr(llm, ATTRIBUT_OUTIL_ECRIT, case_outil_ecrit(getattr(moteur, "active_agent", None), moteur))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[cerveau] case « outil écrit » non posée : {erreur!r}")


def _noms_des_outils(context: Any) -> list[str]:
    try:
        outils = getattr(context, "tools", None)
        return [t.name for t in (getattr(outils, "standard_tools", None) or [])]
    except Exception:  # noqa: BLE001
        return []


class TexteDuCerveauMixin:
    """Mêlé au cerveau compatible OpenAI, sous la trace, au-dessus de la relance sans flux :
    la relance rendue en morceaux est nettoyée comme le flux d'origine."""

    async def get_chat_completions(self, context):  # type: ignore[override]
        flux = await super().get_chat_completions(context)  # type: ignore[misc]
        try:
            consigne = str(getattr(getattr(self, "_settings", None), "system_instruction", "") or "")
            portes = FLECHE in consigne or any(
                isinstance(m, dict) and m.get("role") == "system" and FLECHE in str(m.get("content") or "")
                for m in (getattr(context, "messages", None) or [])
            )
            outils = _noms_des_outils(context)
            # C9 : les outils déclarés à cette requête, lus par le détecteur d'impasse (une réplique qui n'est que leur nom).
            setattr(self, ATTRIBUT_DERNIERS_OUTILS, tuple(outils))
            return FluxNettoye(
                flux,
                outils,
                portes,
                getattr(self, "balises_du_cerveau", ()) or (),
                outil_ecrit=getattr(self, ATTRIBUT_OUTIL_ECRIT, False) is True,
            )
        except Exception as erreur:  # noqa: BLE001 -- jamais à la place du service
            logger.warning(f"[cerveau] nettoyage du texte non posé : {erreur!r}")
            return flux
