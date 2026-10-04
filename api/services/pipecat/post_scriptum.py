"""[.mark] Le post-scriptum : le modèle parle, puis écrit sa note dans la même réponse.

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`, lot 4. En mode post-scriptum, la consigne
ajoutée par le code (``consigne_du_mode``) demande au modèle de répondre en deux parties :

    Et votre rue ?
    |||
    {"commune": "Creil"}

Ce processeur, placé dans l'étape de génération juste avant le filtre du nom (donc avant la
voix), laisse partir la phrase vers la voix au fil des morceaux et **retient tout ce qui suit le
séparateur** : la note n'est jamais dite, et comme la mémoire du modèle est faite de ce que la voix
a dit (agrégateur placé après elle), elle n'entre jamais dans l'historique. À la fin de la réponse,
la note passe par ``noter`` (les mêmes contrôles que l'outil) dans une tâche à part : la voix est
déjà partie, rien n'attend.

🔑 Une passe du modèle par tour au lieu de deux : c'est tout l'objet du mode (≈ 1,6 s de silence au
lieu de ≈ 3,1 s, `reference/08-performance.md` VI.8).

Ce que le processeur garantit (patron de ``filtre_nom_civilite.py``) :

- un morceau qui pourrait être le début du séparateur (``|``, ``||``) est retenu jusqu'à savoir ;
- D7 : sans séparateur, tout part à la voix, la note du tour est absente et c'est tracé ; une ligne
  qui commence comme du JSON ou un bloc de code n'est **jamais** envoyée à la voix ;
- les guillemets « » qui encadrent toute la phrase sont retirés (runs 889 et 893 du rejeu) ;
- les phrases figées (``TTSSpeakFrame`` : accueil, portes) et les frames ``skip_tts`` passent intactes ;
- le tampon est oublié à chaque début de réponse, à l'interruption, à la fin et à l'annulation ;
- ⛔ il ne lève jamais : une note illisible ou un module en panne ne coûte pas l'appel.

Chaque réponse qui parle laisse une trace dans la fiche (``post_scriptums``) : présent, vide,
absent ou illisible, avec le tour et les champs notés. C'est la mesure du seuil D11.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Iterable

from loguru import logger

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_TOUR,
    MODE_POST_SCRIPTUM,
    SEPARATEUR,
    Notices,
    ReglagesFiche,
    derniere_question,
    noter,
    paroles_de_l_appelant,
)
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# La trace de chaque réponse qui parle, dans la fiche de l'appel.
TRACE_POST_SCRIPTUM = "post_scriptums"
PRESENT, VIDE, ABSENT, ILLISIBLE = "present", "vide", "absent", "illisible"

# D7 : une ligne qui commence comme du JSON ou comme un bloc de code.
_DEBUT_JSON_EN_LIGNE = re.compile(r"\n[ \t]*[{`]")
_DEBUT_JSON_EN_TETE = re.compile(r"^[ \t]*[{`]")
# Ce qu'on ne peut pas encore envoyer : une fin de ligne dont on ne sait pas
# encore si elle ouvre du JSON, ou un guillemet fermant peut-être final.
_FIN_EN_SUSPENS = re.compile(r"[ \t\n|]*$")
_GUILLEMET_FERMANT = re.compile(r"[\s  ]*»[\s  ]*$")
_GUILLEMET_OUVRANT = re.compile(r"^[\s  ]*«[\s  ]*")
# Une note « tout ou rien » : le délai laissé aux notes en cours avant la passe de fin.
DELAI_DES_NOTES_EN_COURS = 3.0


def lire_la_note(brut: str) -> dict | None:
    """La note écrite après le séparateur. ``{}`` : rien à noter (y compris rien
    du tout après le séparateur). ``None`` : illisible. Tolère les clôtures
    ``` et un texte autour de l'objet."""
    texte = re.sub(r"^\s*```[A-Za-z]*", "", brut or "")
    texte = re.sub(r"```\s*$", "", texte).strip()
    if not texte:
        return {}
    try:
        valeur = json.loads(texte)
    except ValueError:
        trouve = re.search(r"\{.*\}", texte, re.DOTALL)
        if not trouve:
            return None
        try:
            valeur = json.loads(trouve.group(0))
        except ValueError:
            return None
    return valeur if isinstance(valeur, dict) else None


class PostScriptumProcessor(FrameProcessor):
    """Sépare ce que le modèle dit de ce qu'il note, puis écrit la note."""

    def __init__(
        self,
        *,
        reglages: ReglagesFiche,
        fiche: Callable[[], dict],
        messages: Callable[[], Iterable[dict]],
        notices: Notices | None,
        attendu: Callable[[], bool] = lambda: True,
        notes_en_cours: set[asyncio.Task] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._reglages = reglages
        self._fiche = fiche
        self._messages = messages
        self._notices = notices
        # L'étape attend-elle un post-scriptum ? (pas une étape de fin, D12)
        self._attendu = attendu
        self._notes_en_cours = notes_en_cours if notes_en_cours is not None else set()
        self._lus: list[dict] = []
        self._oublier()

    # --- L'état d'une réponse ------------------------------------------------

    def _oublier(self) -> None:
        """Une réponse commence toujours à vide (patron du filtre du nom)."""
        self._attente = ""  # retenu, peut-être encore pour la voix
        self._note = ""  # retenu, jamais pour la voix
        self._apres = False  # tout ce qui arrive va à la note
        self._separateur = False  # le séparateur a été vu
        self._vu_du_texte = False  # la réponse a parlé (une porte seule ne parle pas)
        self._en_tete = True  # rien n'a encore été dit dans cette réponse
        self._en_debut_de_ligne = True
        self._guillemet = False  # la phrase s'ouvrait sur « : le » final part

    # --- Vers la voix ----------------------------------------------------------

    async def _dire(
        self,
        texte: str,
        frame: LLMTextFrame | None,
        direction: FrameDirection,
        *,
        fin: bool = False,
    ) -> None:
        """Pousse ``texte`` à la voix, en réutilisant la frame reçue (ses drapeaux)."""
        if self._en_tete and texte.strip():
            ouvrant = _GUILLEMET_OUVRANT.match(texte)
            if ouvrant:
                self._guillemet = True
                texte = texte[ouvrant.end() :]
            texte = texte.lstrip()
            self._en_tete = not texte
        elif self._en_tete:
            texte = ""
        if fin:
            if self._guillemet:
                texte = _GUILLEMET_FERMANT.sub("", texte)
            texte = texte.rstrip()
        if not texte:
            return
        self._en_debut_de_ligne = texte.endswith("\n")
        porteuse = frame or LLMTextFrame(texte)
        porteuse.text = texte
        await self.push_frame(porteuse, direction)

    def _a_retenir(self, texte: str) -> int:
        """Combien de caractères de la fin ne peuvent pas encore partir."""
        debuts = [len(texte)]
        # Une fin faite d'espaces, de retours à la ligne et de « | » : peut-être
        # le début du séparateur (« \n|| ») ou d'une ligne de JSON (« \n »).
        fin = _FIN_EN_SUSPENS.search(texte)
        if fin and ("|" in fin.group(0) or "\n" in fin.group(0)):
            debuts.append(fin.start())
        if self._en_debut_de_ligne and not texte.strip():
            debuts.append(0)
        if self._guillemet or (self._en_tete and texte.lstrip().startswith("«")):
            fermant = _GUILLEMET_FERMANT.search(texte)
            if fermant:
                debuts.append(fermant.start())
        return len(texte) - min(debuts)

    # --- Les frames ------------------------------------------------------------

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        try:
            await self._traiter(frame, direction)
        except Exception as erreur:  # noqa: BLE001 -- le post-scriptum ne coûte jamais l'appel
            logger.error(
                f"[fiche] post-scriptum en échec, frame transmise : {erreur!r}"
            )
            self._oublier()
            await self.push_frame(frame, direction)

    async def _traiter(self, frame: Frame, direction: FrameDirection) -> None:
        # Les phrases figées (accueil, portes) et le texte marqué « ne pas dire »
        # ne viennent pas d'une réponse à deux parties : intacts.
        if isinstance(frame, TTSSpeakFrame) or (
            isinstance(frame, LLMTextFrame) and getattr(frame, "skip_tts", False)
        ):
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMFullResponseStartFrame):
            self._oublier()
            # Ce que le modèle a lu pour écrire cette réponse : les paroles et la
            # question à laquelle la personne répondait (comme l'outil).
            try:
                self._lus = list(self._messages())
            except Exception as erreur:  # noqa: BLE001
                logger.warning(
                    f"[fiche] post-scriptum : conversation illisible ({erreur!r})"
                )
                self._lus = []
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMFullResponseEndFrame):
            await self._finir(direction)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, (InterruptionFrame, EndFrame, CancelFrame)):
            self._oublier()
            await self.push_frame(frame, direction)
            return

        if not isinstance(frame, LLMTextFrame):
            await self.push_frame(frame, direction)
            return

        self._vu_du_texte = True
        if self._apres:
            self._note += frame.text
            return
        texte, self._attente = self._attente + frame.text, ""
        coupe = texte.find(SEPARATEUR)
        if coupe >= 0:
            await self._dire(texte[:coupe], frame, direction, fin=True)
            self._apres = self._separateur = True
            self._note = texte[coupe + len(SEPARATEUR) :]
            return
        json_ = _DEBUT_JSON_EN_LIGNE.search(texte)
        if json_ is None and self._en_debut_de_ligne:
            json_ = _DEBUT_JSON_EN_TETE.search(texte)
        if json_ is not None:
            # D7 : du JSON sans séparateur ne part jamais à la voix.
            await self._dire(texte[: json_.start()], frame, direction, fin=True)
            self._apres = True
            self._note = texte[json_.start() :]
            return
        garde = self._a_retenir(texte)
        await self._dire(texte[: len(texte) - garde], frame, direction)
        self._attente = texte[len(texte) - garde :]

    async def _finir(self, direction: FrameDirection) -> None:
        """Fin de la réponse : le reste à la voix, puis la note."""
        if not self._apres and self._attente.strip(" \t\n|"):
            await self._dire(self._attente, None, direction, fin=True)
        if not self._vu_du_texte:
            # Une réponse qui ne parle pas (une porte, D5) : ni note ni trace.
            self._oublier()
            return
        champs: dict | None = None
        if self._separateur:
            champs = lire_la_note(self._note)
            etat = ILLISIBLE if champs is None else (PRESENT if champs else VIDE)
        else:
            etat = ABSENT
        lus = self._lus
        self._oublier()
        if etat == ILLISIBLE:
            logger.warning("[fiche] post_scriptum_illisible : rien noté à ce tour")
        elif etat == ABSENT and self._attendu():
            logger.info("[fiche] post_scriptum_absent : rien noté à ce tour")
        if etat == ABSENT and not self._attendu():
            # Une étape de fin n'a pas de consigne : son silence n'est pas un oubli.
            return
        self._tracer(etat, sorted(champs or {}))
        if etat != PRESENT:
            if self._notices is not None:
                self._notices.retenir(None)
            return
        tache = asyncio.get_running_loop().create_task(self._noter(champs, lus))
        self._notes_en_cours.add(tache)
        tache.add_done_callback(self._notes_en_cours.discard)

    def _tracer(self, etat: str, champs: list[str]) -> None:
        try:
            fiche = self._fiche()
            fiche.setdefault(TRACE_POST_SCRIPTUM, []).append(
                {"tour": fiche.get(CLE_TOUR), "etat": etat, "champs": champs}
            )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[fiche] trace du post-scriptum non écrite : {erreur!r}")

    async def _noter(self, champs: dict, lus: list[dict]) -> None:
        """La note, par les mêmes contrôles que l'outil ; ses notices au tour suivant (D4)."""
        try:
            note = await noter(
                self._fiche,
                self._reglages,
                champs,
                paroles=paroles_de_l_appelant(lus),
                question=derniere_question(lus),
                source=MODE_POST_SCRIPTUM,
            )
        except Exception as erreur:  # noqa: BLE001 -- une note ne coûte jamais l'appel
            logger.error(f"[fiche] note du post-scriptum en échec : {erreur!r}")
            note = None
        if self._notices is not None:
            self._notices.retenir(note)


async def attendre_les_notes(notes_en_cours: set[asyncio.Task]) -> None:
    """Avant la passe de fin : laisser finir une note encore en cours (bornée)."""
    en_cours = [t for t in notes_en_cours if not t.done()]
    if not en_cours:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*en_cours, return_exceptions=True), DELAI_DES_NOTES_EN_COURS
        )
    except TimeoutError:
        logger.warning(
            "[fiche] note du post-scriptum trop lente, passe de fin lancée sans elle"
        )


def creer_post_scriptum(
    reglages: ReglagesFiche | None,
    fiche: Callable[[], dict],
    messages: Callable[[], Iterable[dict]],
    notices: Notices | None,
    *,
    attendu: Callable[[], bool] = lambda: True,
    notes_en_cours: set[asyncio.Task] | None = None,
) -> PostScriptumProcessor | None:
    """Le processeur, ou ``None`` hors mode post-scriptum (le défaut : outil)."""
    if reglages is None or reglages.mode != MODE_POST_SCRIPTUM:
        return None
    return PostScriptumProcessor(
        reglages=reglages,
        fiche=fiche,
        messages=messages,
        notices=notices,
        attendu=attendu,
        notes_en_cours=notes_en_cours,
    )
