"""[.mark] Chantier voix-soniox, lot 5 bis (D11) : les balises d'expression entre crochets.

Soniox lit des balises d'expression écrites en anglais entre crochets (``[warm]``, ``[calm]``,
``[slowly]``, ``[pause]``). Recherche du 21/10 : **une balise inconnue peut être lue à voix haute**.
Ce module pose les garde-fous, AVANT tout essai de balises (D10) :

- ``retirer_balises(texte, permises)`` : tout crochet hors liste est retiré du texte ;
- ``sans_balises(texte)`` : tous les crochets retirés. Pour ce que les gens lisent (transcription
  affichée, verbatim conservé) et ce que la fiche lit : un crochet n'y est jamais montré ;
- ``retirer_balises_pour_la_voix(permises)`` : la transformation Pipecat posée dans la file du texte
  de la voix, après les nombres en mots, avant la voix.

🔑 Une TRANSFORMATION et non un filtre de texte, pour la raison de ``nombres_pour_la_voix.py`` :
elle ne change que le texte envoyé à la voix. ⚠️ Mais une voix qui horodate les mots (Soniox,
ElevenLabs) fait reconstruire l'historique du modèle depuis ce qui a été DIT : il garde donc les
balises permises (jamais les retirées). Seules la transcription, le verbatim et la fiche n'en
montrent aucune (D-24).

⛔ Ce que ce module ne fait jamais
- **Écrire une balise.** Aucune balise n'est ajoutée par le code ; elles viennent d'une phrase fixe
  ou du prompt, et c'est un essai au banc (D10), pas ce lot.
- Coûter une réplique : Pipecat jette l'audio de la phrase quand une transformation lève. Toute
  erreur rend le texte tel quel, avec un avertissement.
- Toucher un texte sans crochet : il est rendu identique (même objet), c'est le test « zéro perte »
  sur le corpus des phrases réelles.

⚠️ Phrase par phrase seulement. Mot à mot, un crochet arrive en morceaux (« [wa », « rm] ») et ne
peut pas être lu : la transformation n'est pas posée (``construire_remplacements_de_voix``). Le
texte que le cerveau écrit : depuis le lot 5 ter (D29), ``texte_du_cerveau.py`` laisse passer les balises
de la liste permise sous la voix Soniox (phrase par phrase) et retire tout autre crochet.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable

from loguru import logger

# D11 : la liste par défaut (sans les crochets : la liste de l'écran accepte « warm » comme « [warm] »).
BALISES_PAR_DEFAUT: tuple[str, ...] = ("warm", "calm", "slowly", "pause")

# Un passage entre crochets fermé, sur une ligne, au plus 160 caractères (comme ``texte_du_cerveau``),
# avec l'espace avant et après.
_CROCHETS = re.compile(r"([ \t]*)\[([^\[\]\n]{0,160})\]([ \t]*)")


def nom_de_balise(valeur: object) -> str:
    """``« [Warm] »`` -> ``warm`` : la forme sous laquelle une balise est comparée à la liste."""
    texte = str(valeur or "").strip()
    if texte.startswith("[") and texte.endswith("]"):
        texte = texte[1:-1]
    return texte.strip().lower()


def balises_permises(valeurs: Iterable[object] | None) -> frozenset[str]:
    """La liste de l'écran sous sa forme comparable (vides ignorées)."""
    return frozenset(nom for nom in (nom_de_balise(v) for v in valeurs or ()) if nom)


def retirer_balises(texte: str, permises: Iterable[object] | None = ()) -> str:
    """``texte`` sans tout passage entre crochets qui n'est pas dans ``permises``.

    Liste vide ou absente : tous les crochets sont retirés (réglage éteint). Un texte sans crochet
    est rendu tel quel (même objet). L'espace qui entourait une balise retirée est recollé : « Oui
    [x] d'accord » devient « Oui d'accord », « fin [x]. » devient « fin. »."""
    if "[" not in texte:
        return texte
    gardees = balises_permises(permises)

    def _remplacer(m: re.Match) -> str:
        avant, contenu, apres = m.group(1), m.group(2), m.group(3)
        if nom_de_balise(contenu) in gardees:
            return m.group(0)
        if m.start() == 0 or m.end() == len(texte) or not apres:
            return ""
        return avant or apres

    return _CROCHETS.sub(_remplacer, texte)


def sans_balises(texte: str) -> str:
    """``texte`` sans aucun passage entre crochets fermé : ce que la transcription affichée, le
    verbatim conservé et la fiche lisent (D11). Un texte sans crochet est rendu tel quel."""
    return retirer_balises(texte, ())


def retirer_balises_pour_la_voix(
    permises: Iterable[object] | None,
) -> Callable[[str, str], Awaitable[str]]:
    """La transformation Pipecat : le texte envoyé à la voix, sans les balises hors liste.

    Ne lève jamais : une erreur rend le texte tel quel."""
    gardees = tuple(permises or ())

    async def _transformer(texte: str, _type: str = "*") -> str:
        try:
            retire = retirer_balises(texte, gardees)
        except Exception as erreur:  # noqa: BLE001 -- la voix doit continuer
            logger.warning(f"[.mark] Balises d'expression non retirées pour la voix : {erreur!r}")
            return texte
        if retire != texte:
            # ⛔ Jamais le texte (données personnelles) : seulement les balises retirées et leur nombre.
            permises = balises_permises(gardees)
            retirees = [
                m.group(2) for m in _CROCHETS.finditer(texte) if nom_de_balise(m.group(2)) not in permises
            ]
            logger.info(f"[.mark] Balises hors liste retirées pour la voix : {len(retirees)} {retirees!r}")
        return retire

    return _transformer
