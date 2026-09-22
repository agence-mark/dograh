"""[.mark] Interdire à l'agent de PRONONCER le nom de l'appelant et sa civilité.

Pourquoi ce module existe, et pourquoi ce n'est pas une consigne de prompt
--------------------------------------------------------------------------
Cinq réécritures des consignes en deux jours (runs 749 à 753, agent n° 16) :
le nom est resté prononcé dans 2 runs vocaux sur 5, la civilité dans 2 sur 5.
**Une règle tient à l'endroit de l'action, elle cède partout ailleurs.** C'est
déjà vrai des communes, des nombres dictés et de l'annonce d'ouverture.

Où ça agit, et pourquoi PAS là où le plan le disait
---------------------------------------------------
🔴 Mesuré le 22/09 par une sonde exécutée, pas par une lecture : entre le
modèle et la voix, **il n'y a pas de phrases**. Le modèle pousse sa réponse par
morceaux de flux -- 8 frames pour « Bonjour, monsieur Dupont. », avec
``, monsieur`` et `` Dupont`` **séparément**. Un filtre posé là ne reconnaîtrait
jamais un nom, et aucun test ne le verrait : il serait vert et inopérant.

Les deux autres endroits possibles échouent chacun sur une moitié :

- un filtre de texte de la voix voit bien la phrase entière, mais ce qu'il
  retire **ne redescend pas dans la mémoire du modèle** (l'amont l'écrit :
  *« This changes only the text sent to the voice »*). L'agent croirait avoir
  dit le nom, et son tour suivant partirait de faux ;
- un processeur posé avant la voix corrige bien la mémoire du modèle, mais il
  ne voit que des morceaux.

⇒ **Décision d'Evan du 22/09 (voie C)** : un processeur placé juste avant la
voix, qui **recompose la phrase lui-même** avant de la transmettre. Il tient
les deux exigences. Il ne retarde aucun son : en envoi phrase par phrase, la
voix attend déjà la phrase complète avant de synthétiser quoi que ce soit.

Ce que le module NE fait pas
----------------------------
- ⛔ il ne touche **jamais** la fiche d'appel, le verbatim ni les variables
  extraites : on filtre ce qui se dit, jamais ce qui se note ;
- ⛔ il ne filtre **pas le prénom** (hors périmètre, décision du 22/09) ;
- ⛔ il ne filtre **pas le nom épelé**, et c'est **voulu** : l'épellation
  confirme l'information dans les deux sens et évite la boucle sans fin quand
  un appelant corrige son nom ;
- ⛔ en envoi **mot à mot**, il reste **inerte** et le journalise : un agent qui
  hache ses phrases est pire qu'un agent qui prononce un nom.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from loguru import logger

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# Les civilités que l'agent peut dire. ⛔ Pas « docteur » ni « maître » : ils
# désignent un métier autant qu'une personne, et rien ne les a jamais fait dire
# à l'agent.
CIVILITES = ("monsieur", "madame", "mademoiselle")

# Une frontière de phrase : ce qui déclenche la synthèse côté voix.
FIN_DE_PHRASE = re.compile(r"[.!?…](?:[\"'»\)]|\s|$)")


def _motif_du_nom(nom: str) -> str:
    """Le nom, échappé, avec ses variantes d'apostrophe.

    ⛔ Échappé, parce qu'un nom est une donnée saisie : « M. (Dupont) » ferait
    lever une expression régulière construite naïvement, et emporterait le tour
    de parole.
    """
    echappe = re.escape(nom.strip())
    return echappe.replace(r"\'", "['’]").replace("’", "['’]")


def retirer_nom_et_civilite(
    texte: str,
    nom: str | None,
    *,
    retirer_nom: bool = False,
    retirer_civilite: bool = False,
) -> str:
    """Retire le nom et la civilité d'une phrase, sans abîmer le reste.

    **Niveau 2** (décision du 22/09) : la civilité accolée au nom, la civilité
    seule, et le nom seul **quand il porte une majuscule**.

    ⛔ Pas le nom en minuscules : « vous êtes passé chez le boulanger » ne se
    mutile pas chez un appelant nommé Boulanger. La majuscule discrimine, et
    elle ne discrimine plus en début de phrase : limite connue, écrite dans la
    notice de l'écran.

    🔑 La recouture n'agit **que si un retrait a eu lieu**. Sans cette garde, le
    prototype mangeait l'espace avant le point d'interrogation de phrases où
    rien n'avait été retiré -- il aurait parlé mal sur 100 % des appels pour en
    corriger 16 %.

    Ne lève jamais : le texte d'origine est rendu tel quel en cas de pépin.
    """
    if not texte or (not retirer_nom and not retirer_civilite):
        return texte
    try:
        nom_utilisable = (nom or "").strip() if retirer_nom else ""
        civilites = "|".join(CIVILITES) if retirer_civilite else ""

        morceaux = []
        if nom_utilisable:
            motif_nom = _motif_du_nom(nom_utilisable)
            if civilites:
                # La civilité accolée au nom part d'un bloc : « monsieur Dupont ».
                morceaux.append(rf"(?:{civilites})\s+{motif_nom}")
            # ⛔ Le nom épelé n'est pas touché, et c'est voulu : un tiret ou une
            # espace entre deux lettres le sort de ce motif de lui-même. La
            # garde ci-dessous l'écrit quand même, pour qu'un futur lecteur ne
            # croie pas à un oubli.
            morceaux.append(rf"(?<![-\w]){motif_nom}(?![-\w])")
        if civilites:
            morceaux.append(rf"(?:{civilites})")

        if not morceaux:
            return texte

        # 🔑 La ponctuation de liaison part AVEC le groupe, elle n'est pas
        # nettoyée après coup. Nettoyer après coup, c'est réécrire des phrases
        # auxquelles on n'a rien retiré : le prototype mangeait ainsi l'espace
        # typographique avant « ? » -- l'agent aurait mal parlé sur 100 % des
        # appels pour en corriger 16 %.
        noyau = "|".join(f"(?:{m})" for m in morceaux)
        motif = re.compile(
            rf"(?P<avant>\s*,)?\s*(?P<noyau>{noyau})(?P<apres>\s*,)?",
            re.IGNORECASE,
        )

        retraits = 0

        def _remplacer(trouve: re.Match) -> str:
            nonlocal retraits
            valeur = trouve.group("noyau")
            commence_par_civilite = valeur.lower().startswith(CIVILITES)
            if not commence_par_civilite and not valeur[:1].isupper():
                # Le nom en minuscules reste : c'est le mot ordinaire, pas la
                # personne (« passé chez le boulanger » chez M. Boulanger).
                return trouve.group(0)
            retraits += 1
            en_tete = trouve.start() == 0
            encadre = bool(trouve.group("avant")) and bool(trouve.group("apres"))
            # « votre poêle, monsieur Untel, est un Godin » -> les DEUX virgules
            # partent, sinon il reste « votre poêle, est un Godin ».
            # « Monsieur Untel, je répète » -> celle d'après part avec lui.
            if encadre or en_tete:
                return ""
            # ⚠️ La virgule d'avant ne part QUE si la phrase s'arrête ou change
            # de registre derrière le groupe. Sinon elle sépare deux morceaux
            # qui restent tous les deux : « D'accord, monsieur Untel, c'est
            # noté » avec la seule civilité coupée doit rendre « D'accord,
            # Untel, c'est noté », pas « D'accord Untel, c'est noté ».
            suite = texte[trouve.end() :].lstrip()
            if suite and not suite[0] in ".,;:!?…»\"')":
                return (trouve.group("avant") or "") + (trouve.group("apres") or "")
            return trouve.group("apres") or ""

        sortie = motif.sub(_remplacer, texte)
        if not retraits:
            return texte
        return _recoudre(sortie)
    except Exception as erreur:  # noqa: BLE001 -- l'appel doit continuer
        logger.warning(f"[.mark] Name filter failed, sentence kept as is: {erreur!r}")
        return texte


def _recoudre(texte: str) -> str:
    """Refait une phrase lisible après un retrait, et seulement après.

    « D'accord, c'est noté, monsieur Untel. » doit donner « D'accord, c'est
    noté. », jamais « D'accord, c'est noté, . »

    ⚠️ Volontairement MINIMALE : la ponctuation de liaison est déjà partie avec
    le groupe retiré. Il ne reste ici que ce qu'un retrait peut laisser derrière
    lui. ⛔ Surtout pas de normalisation typographique générale : l'espace
    devant « ? » et « : » est correct en français, et le corpus le porte.
    """
    sortie = texte
    # Deux espaces pour un, là où le groupe se tenait.
    sortie = re.sub(r"[ \t]{2,}", " ", sortie)
    # Un espace ou une virgule laissés devant la ponctuation de fin.
    sortie = re.sub(r"\s*,\s*(?=[.!?…])", "", sortie)
    # Un début de phrase qui commence désormais par une espace ou une virgule.
    sortie = re.sub(r"(^|(?<=[.!?…])\s)[\s,]+", r"\1", sortie)
    # Et qui commence par une minuscule après un retrait en tête :
    # « Dupont, c'est noté. » -> « C'est noté. »
    sortie = re.sub(
        r"(^|[.!?…]\s+)([a-zà-ÿ])",
        lambda m: m.group(1) + m.group(2).upper(),
        sortie,
    )
    return sortie.strip()


class FiltreNomCiviliteProcessor(FrameProcessor):
    """Recompose la phrase, la filtre, puis la transmet à la voix.

    🔑 L'état est vivant : le nom est lu **pendant** l'appel, par un rappel de
    fonction vers les variables extraites, parce qu'il n'est pas connu au
    montage du pipeline (patron de ``LectureAppelantProcessor``).

    ⛔ En mode d'envoi ``token``, le processeur laisse passer chaque morceau
    sans y toucher : recomposer les phrases y annulerait le réglage que
    quelqu'un est allé chercher, et un agent qui hache ses phrases est pire
    qu'un agent qui prononce un nom.
    """

    def __init__(
        self,
        *,
        retirer_nom: bool,
        retirer_civilite: bool,
        variables: Callable[[], dict],
        mode_envoi: str = "sentence",
        champ_du_nom: str = "nom",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._retirer_nom = retirer_nom
        self._retirer_civilite = retirer_civilite
        self._variables = variables
        self._champ_du_nom = champ_du_nom
        self._par_phrase = str(mode_envoi) == "sentence"
        self._tampon = ""
        if not self._par_phrase:
            logger.info(
                "[.mark] Name/title filter inert: the text is sent to the voice "
                "word by word, where a name is split across frames."
            )

    def _nom_de_lappelant(self) -> str | None:
        try:
            variables = self._variables() or {}
            valeur = variables.get(self._champ_du_nom)
            return str(valeur).strip() if valeur else None
        except Exception as erreur:  # noqa: BLE001 -- l'appel doit continuer
            logger.warning(f"[.mark] Caller name unreadable: {erreur!r}")
            return None

    def _filtrer(self, texte: str) -> str:
        return retirer_nom_et_civilite(
            texte,
            self._nom_de_lappelant(),
            retirer_nom=self._retirer_nom,
            retirer_civilite=self._retirer_civilite,
        )

    async def _vider(self, direction: FrameDirection):
        """Transmet ce qui reste en tampon, filtré."""
        if not self._tampon:
            return
        reste, self._tampon = self._tampon, ""
        await self.push_frame(LLMTextFrame(self._filtrer(reste)), direction)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if not self._par_phrase or not isinstance(frame, LLMTextFrame):
            # ⚠️ La fin de réponse et l'interruption passent AUSSI par ici, et
            # c'est ce qui garantit qu'aucun morceau ne reste coincé en tampon.
            if isinstance(frame, LLMFullResponseEndFrame):
                await self._vider(direction)
            elif isinstance(frame, InterruptionFrame):
                self._tampon = ""
            await self.push_frame(frame, direction)
            return

        self._tampon += frame.text
        # On ne retient que le morceau de phrase en cours : tout ce qui est
        # terminé part immédiatement, pour ne pas retarder la voix.
        while True:
            fin = FIN_DE_PHRASE.search(self._tampon)
            if not fin:
                break
            coupe = fin.end()
            phrase, self._tampon = self._tampon[:coupe], self._tampon[coupe:]
            await self.push_frame(LLMTextFrame(self._filtrer(phrase)), direction)


def creer_filtre_nom_civilite(
    run_configs: dict | None,
    variables: Callable[[], dict],
) -> FiltreNomCiviliteProcessor | None:
    """Le filtre pour cet agent, ou ``None`` quand les deux interrupteurs sont
    éteints -- ce qui est le défaut, et ce qui vaut pour tout agent existant."""
    run_configs = run_configs or {}
    retirer_nom = bool(run_configs.get("interdire_nom_appelant"))
    retirer_civilite = bool(run_configs.get("interdire_civilite_appelant"))
    if not retirer_nom and not retirer_civilite:
        return None
    from api.schemas.workflow_configurations import DEFAULT_TTS_TEXT_AGGREGATION_MODE

    return FiltreNomCiviliteProcessor(
        retirer_nom=retirer_nom,
        retirer_civilite=retirer_civilite,
        variables=variables,
        mode_envoi=run_configs.get("tts_text_aggregation_mode")
        or DEFAULT_TTS_TEXT_AGGREGATION_MODE,
    )
