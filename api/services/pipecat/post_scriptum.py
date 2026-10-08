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
from typing import Any

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
from api.services.workflow.porte_parlee import FLECHE
from api.services.workflow.workflow_graph import transition_tool_name
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
# Un tour coupé par la personne avant la fin de la réponse (avec `separateur` : vu ou non).
INTERROMPU = "interrompu"

# D7 : une ligne qui commence comme du JSON ou comme un bloc de code.
_DEBUT_JSON_EN_LIGNE = re.compile(r"\n[ \t]*[{`]")
_DEBUT_JSON_EN_TETE = re.compile(r"^[ \t]*[{`]")
# Ce qu'on ne peut pas encore envoyer : une fin de ligne dont on ne sait pas
# encore si elle ouvre du JSON, ou un guillemet fermant peut-être final.
_FIN_EN_SUSPENS = re.compile(r"[ \t\n|]*$")
_GUILLEMET_FERMANT = re.compile(r"[\s  ]*»[\s  ]*$")
_GUILLEMET_OUVRANT = re.compile(r"^[\s  ]*«[\s  ]*")
# Plan postscriptum-note-d-abord (C8) : en note d'abord, la phrase attend que la note
# soit écrite dans la fiche (le filtre du nom la lit), au plus ce délai : jamais plus.
DELAI_NOTE_AVANT_LA_VOIX = 0.3
# Plan porte-parlee (D9) : case allumée, « || » vaut séparateur à la lecture.
_SEPARATEUR_TOLERE = re.compile(r"\|{2,}")
# Ce qui entoure parfois le nom écrit après « → » (guillemets, mise en forme).
_AUTOUR_DU_NOM = " \t\r«»\"'`*:.,;"


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


def sans_json(texte: str) -> str:
    """La parole d'un texte où le modèle a mêlé du JSON (D7) : sans les objets
    ``{…}`` (même imbriqués ou inachevés), sans les clôtures ``` ni les « | »."""
    texte = re.sub(r"```[A-Za-z]*", " ", texte or "")
    sortie: list[str] = []
    profondeur = 0
    for caractere in texte:
        if caractere == "{":
            profondeur += 1
        elif caractere == "}" and profondeur:
            profondeur -= 1
        elif not profondeur:
            sortie.append(caractere)
    return re.sub(r"\s+", " ", "".join(sortie).replace("|", " ")).strip()


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
        portes: Any = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        # Plan porte-parlee : le moteur qui prend les portes écrites, case allumée
        # seulement (``None`` : le processeur d'avant, à l'octet).
        self._portes = portes if reglages.portes_dans_la_reponse else None
        self._portes_en_cours: set[asyncio.Task] = set()
        self._reglages = reglages
        self._fiche = fiche
        self._messages = messages
        self._notices = notices
        # L'étape attend-elle un post-scriptum ? (pas une étape de fin, D12)
        self._attendu = attendu
        self._notes_en_cours = notes_en_cours if notes_en_cours is not None else set()
        # Une seule note à la fois, dans l'ordre des réponses (relecture du 04/10) :
        # une note lente (rues relues) ne doit pas finir après la suivante.
        self._une_note_a_la_fois = asyncio.Lock()
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
        # Plan porte-parlee (case allumée seulement).
        self._a_dit = False  # quelque chose est parti à la voix
        self._reponse: str | None = None  # identifiant de lecture de la réponse
        self._ligne_au_debut = True  # le flux est en début de ligne
        self._blancs = ""  # les blancs d'un début de ligne, en attente
        self._dans_la_porte = False  # une ligne « → » est en cours de lecture
        self._porte_brute = ""
        self._portes_lues: list[str] = []  # les lignes « → » complètes
        self._transition_dite = False
        # Plan postscriptum-note-d-abord (S1, case « Reply order » sur note d'abord).
        self._dans_la_note = self._reglages.note_d_abord  # la note n'est pas finie
        self._note_d_abord = ""  # la note écrite avant la phrase, jamais dite
        self._note_d_abord_lue = False  # elle est lue (et envoyée à ``noter``)
        self._champs_d_abord: dict | None = None
        self._sans_separateur = False  # la note s'est fermée sans séparateur

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
            # Un séparateur mal formé (« || ») ne part pas à la voix (relecture du 04/10).
            texte = texte.rstrip().rstrip("|").rstrip()
        if not texte:
            return
        self._en_debut_de_ligne = texte.endswith("\n")
        porteuse = frame or LLMTextFrame(texte)
        porteuse.text = texte
        self._a_dit = True
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
            # Plan porte-parlee (D7) : la réponse se retrouve à la sortie par cet identifiant.
            self._reponse = frame.metadata.get("dograh_speech_id")
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMFullResponseEndFrame):
            if self._portes is None:
                await self._finir(direction)
            else:
                # D6 : la porte est prise à la fin de la réponse, après la phrase et la note.
                self._clore_la_ligne(complete=True)
                portes = (list(self._portes_lues), self._transition_dite, self._reponse)
                attendu = self._attendu()
                trace = await self._finir(direction)
                if portes[0]:
                    await self._porte_protegee(portes, trace, relancer=not self._dit)
                elif (
                    trace is not None
                    and not self._dit
                    and attendu
                    and self._reglages.note_d_abord
                ):
                    # C3 : ni phrase ni porte (une note seule) : le modèle reparle, une fois.
                    # Formulaire du lot 4 (Evan, 08/10) : en « porte, note, phrase » seulement.
                    relancer = getattr(self._portes, "relancer_une_reponse_muette", None)
                    if relancer is not None and await relancer():
                        trace["relance_muette"] = True
            await self.push_frame(frame, direction)
            return

        detail: dict = {}
        if isinstance(frame, InterruptionFrame) and self._portes is not None:
            # D6 : la décision du modèle portait sur ce que la personne avait dit ;
            # l'étape change même si elle coupe la parole. Une ligne « → » coupée
            # en route n'est jamais prise (un nom tronqué peut en nommer un autre).
            attendu = self._attendu()
            self._clore_la_ligne(complete=False)
            detail = await self._prendre_la_porte(
                list(self._portes_lues),
                self._transition_dite,
                self._reponse,
                relancer=False,
            )
            vu = self._vu_du_texte and attendu
        else:
            vu = (
                isinstance(frame, InterruptionFrame)
                and self._vu_du_texte
                and self._attendu()
            )
        if vu:
            # Relecture du 04/10 : un tour coupé compte dans la mesure D11, avec ce
            # qu'on sait du séparateur ; sa note n'est pas écrite (le tour suivant
            # ou la passe de fin la rattrape).
            self._tracer(INTERROMPU, [], separateur=self._separateur, **detail)
        if isinstance(frame, (InterruptionFrame, EndFrame, CancelFrame)):
            self._oublier()
            await self.push_frame(frame, direction)
            return

        if not isinstance(frame, LLMTextFrame):
            await self.push_frame(frame, direction)
            return

        if self._portes is not None:
            # Plan porte-parlee (lot 4) : une ligne « → » est retenue où qu'elle
            # soit (en tête, après la phrase, après le séparateur), jamais dite.
            frame.text = self._filtrer_les_portes(frame.text)
            await self._annoncer_la_transition(direction)
            if not frame.text:
                self._vu_du_texte = True
                return
        self._vu_du_texte = True
        if self._dans_la_note:
            # Plan postscriptum-note-d-abord (S1) : la note d'abord, jamais dite.
            await self._lire_la_note_d_abord(frame, direction)
            return
        await self._phrase(frame, direction)

    async def _phrase(self, frame: LLMTextFrame, direction: FrameDirection) -> None:
        """La phrase vers la voix, la note retenue (l'ordre d'avant ; en note
        d'abord, ce qui suit le séparateur)."""
        if self._apres:
            self._note += frame.text
            if not self._separateur:
                trouve = self._separateur_dans(self._note)
                if trouve is not None:
                    coupe, apres = trouve
                    # D7 (relecture du 04/10) : le JSON écrit AVANT le séparateur
                    # n'est jamais dit, mais la parole qui l'entoure l'est.
                    await self._dire(
                        sans_json(self._note[:coupe]), None, direction, fin=True
                    )
                    self._separateur = True
                    self._note = self._note[apres:]
            return
        texte, self._attente = self._attente + frame.text, ""
        trouve = self._separateur_dans(texte)
        if trouve is not None:
            coupe, apres = trouve
            avant = texte[:coupe]
            # D7 : du JSON ou une clôture de code arrivés dans le même morceau que
            # le séparateur ne partent pas à la voix non plus.
            json_ = _DEBUT_JSON_EN_LIGNE.search(avant)
            if json_ is None and self._en_debut_de_ligne:
                json_ = _DEBUT_JSON_EN_TETE.search(avant)
            if json_ is not None:
                avant = f"{avant[: json_.start()]} {sans_json(avant[json_.start() :])}"
            await self._dire(avant, frame, direction, fin=True)
            self._apres = self._separateur = True
            self._note = texte[apres:]
            return
        json_ = _DEBUT_JSON_EN_LIGNE.search(texte)
        if json_ is None and self._en_debut_de_ligne:
            json_ = _DEBUT_JSON_EN_TETE.search(texte)
        if json_ is not None:
            # D7 : du JSON sans séparateur ne part jamais à la voix. Ce qui suit
            # est retenu ; la parole qu'il contient part au séparateur, ou à la
            # fin de la réponse (jamais un tour muet).
            await self._dire(texte[: json_.start()], frame, direction, fin=True)
            self._apres = True
            self._note = texte[json_.start() :]
            return
        garde = self._a_retenir(texte)
        await self._dire(texte[: len(texte) - garde], frame, direction)
        self._attente = texte[len(texte) - garde :]

    async def _lire_la_note_d_abord(
        self, frame: LLMTextFrame, direction: FrameDirection
    ) -> None:
        """S1 : tout ce qui précède le séparateur est la note. Dès qu'elle est
        finie, elle part à ``noter`` et la suite va à la voix comme une phrase.

        Replis (D7 tient toujours) : une réponse qui commence par une phrase (le
        modèle a gardé l'ordre d'avant) part à la voix tout de suite ; une note
        fermée (``}``) suivie d'une phrase sans séparateur vaut séparateur."""
        self._note_d_abord += frame.text
        tete = self._note_d_abord
        debut = tete.lstrip(" \t\r\n")
        if not debut:
            return
        trouve = self._separateur_dans(tete)
        if trouve is None and not debut.startswith(("{", "`", "|")):
            # L'ordre d'avant : la phrase d'abord. Elle part sans attendre.
            self._dans_la_note, self._note_d_abord = False, ""
            frame.text = tete
            await self._phrase(frame, direction)
            return
        if trouve is not None:
            coupe, apres = trouve
        else:
            fin = _fin_de_l_objet(tete)
            reste = tete[fin:] if fin is not None else ""
            if fin is None or not reste.strip(" \t\r\n|`"):
                return  # la note continue, ou le séparateur arrive peut-être
            coupe = apres = fin
            self._sans_separateur = True
        self._dans_la_note = False
        self._note_d_abord_lue = True
        self._note_d_abord = tete[:coupe]
        self._champs_d_abord = lire_la_note(self._note_d_abord)
        tache = self._noter_en_tache(
            self._champs_d_abord if self._champs_d_abord else None, self._lus
        )
        if self._champs_d_abord:
            # C8 : la note dans la fiche avant la phrase (le filtre du nom la lit).
            _, en_retard = await asyncio.wait({tache}, timeout=DELAI_NOTE_AVANT_LA_VOIX)
            if en_retard:
                logger.warning("[fiche] note d'abord lente : la phrase part sans l'attendre")
        if tete[apres:]:
            frame.text = tete[apres:]
            await self._phrase(frame, direction)

    def _noter_en_tache(self, champs: dict | None, lus: list[dict]) -> asyncio.Task:
        tache = asyncio.get_running_loop().create_task(self._noter(champs, lus))
        self._notes_en_cours.add(tache)
        tache.add_done_callback(self._notes_en_cours.discard)
        return tache

    async def _finir_note_d_abord(self, direction: FrameDirection) -> dict | None:
        """S1, fin de la réponse : le reste de la phrase à la voix ; la note est
        déjà partie à ``noter`` au séparateur (sinon, elle part maintenant)."""
        self._dit = False
        if self._dans_la_note:
            # Ni séparateur ni phrase après la note : la parole qu'elle contient part.
            tete = self._note_d_abord
            await self._dire(sans_json(tete), None, direction, fin=True)
            champs = lire_la_note(tete) if "{" in tete else None
            if champs:
                self._noter_en_tache(champs, self._lus)
            etat, detail = (PRESENT if champs else ABSENT), {"sans_phrase": True}
        else:
            if not self._apres and self._attente.strip(" \t\n|"):
                await self._dire(self._attente, None, direction, fin=True)
            if self._apres and not self._separateur:
                await self._dire(sans_json(self._note), None, direction, fin=True)
            champs = self._champs_d_abord
            etat = ILLISIBLE if champs is None else (PRESENT if champs else VIDE)
            detail = {"sans_separateur": True} if self._sans_separateur else {}
            # Une seconde note après la phrase (le modèle a écrit les deux ordres).
            apres = lire_la_note(self._note) if "{" in self._note else None
            if apres:
                detail["note_apres_la_phrase"] = True
                self._noter_en_tache(apres, self._lus)
        if not self._vu_du_texte:
            self._oublier()
            return None
        self._dit = self._a_dit
        attendu = self._attendu()
        self._oublier()
        if etat == ABSENT and not attendu:
            return None
        return self._tracer(etat, sorted(champs or {}), ordre="note_d_abord", **detail)

    async def _finir(self, direction: FrameDirection) -> dict | None:
        """Fin de la réponse : le reste à la voix, puis la note. Rend la trace
        écrite pour ce tour (ou ``None``) ; ``self._dit`` : la réponse a parlé."""
        if self._reglages.note_d_abord and (
            self._dans_la_note or self._note_d_abord_lue
        ):
            return await self._finir_note_d_abord(direction)
        self._dit = False
        if not self._apres and self._attente.strip(" \t\n|"):
            await self._dire(self._attente, None, direction, fin=True)
        if self._apres and not self._separateur:
            # D7 : du JSON sans séparateur ; la parole écrite autour part quand même.
            await self._dire(sans_json(self._note), None, direction, fin=True)
        if not self._vu_du_texte:
            # Une réponse qui ne parle pas (une porte, D5) : ni note ni trace.
            self._oublier()
            return None
        champs: dict | None = None
        detail: dict = {}
        if self._separateur:
            champs = lire_la_note(self._note)
            if self._portes is not None and await self._rattraper_la_phrase(
                champs, direction
            ):
                # D10 : une phrase écrite après la note est dite, plus tard.
                detail["phrase_apres_note"] = True
                champs = {} if champs is None else champs
            etat = ILLISIBLE if champs is None else (PRESENT if champs else VIDE)
        else:
            etat = ABSENT
        lus = self._lus
        self._dit = self._a_dit
        self._oublier()
        if etat == ILLISIBLE:
            logger.warning("[fiche] post_scriptum_illisible : rien noté à ce tour")
        elif etat == ABSENT and self._attendu():
            logger.info("[fiche] post_scriptum_absent : rien noté à ce tour")
        if etat == ABSENT and not self._attendu():
            # Une étape de fin n'a pas de consigne : son silence n'est pas un oubli.
            return None
        trace = self._tracer(etat, sorted(champs or {}), **detail)
        # Une réponse sans note efface les notices ; elle passe par la même file
        # que les notes, sinon une note lente les réécrirait après elle.
        a_noter = champs if etat == PRESENT else None
        tache = asyncio.get_running_loop().create_task(self._noter(a_noter, lus))
        self._notes_en_cours.add(tache)
        tache.add_done_callback(self._notes_en_cours.discard)
        return trace

    def _tracer(self, etat: str, champs: list[str], **detail) -> dict | None:
        try:
            fiche = self._fiche()
            trace = {
                "tour": fiche.get(CLE_TOUR),
                "etat": etat,
                "champs": champs,
                **detail,
            }
            fiche.setdefault(TRACE_POST_SCRIPTUM, []).append(trace)
            return trace
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[fiche] trace du post-scriptum non écrite : {erreur!r}")
            return None

    # --- Plan porte-parlee (lot 4) : la porte écrite dans la réponse -------------

    def _separateur_dans(self, texte: str) -> tuple[int, int] | None:
        """Où commence et où finit le séparateur dans ``texte``, ou ``None``.
        Case éteinte : ``|||`` seul, comme avant. Allumée (D9) : ``||`` aussi,
        sauf en toute fin de morceau (peut-être le début de ``|||`` : retenu)."""
        if self._portes is None:
            coupe = texte.find(SEPARATEUR)
            return None if coupe < 0 else (coupe, coupe + len(SEPARATEUR))
        for trouve in _SEPARATEUR_TOLERE.finditer(texte):
            if trouve.end() < len(texte) or len(trouve.group(0)) >= len(SEPARATEUR):
                return trouve.start(), trouve.end()
        return None

    def _filtrer_les_portes(self, texte: str) -> str:
        """Retire du flux les lignes qui commencent par « → » (blancs en tête
        permis) et les garde à part ; le reste passe tel quel. Morceau par
        morceau : une ligne coupée en plusieurs morceaux est recollée."""
        sortie: list[str] = []
        for caractere in texte:
            if self._dans_la_porte:
                if caractere == "\n":
                    self._clore_la_ligne(complete=True)
                    self._ligne_au_debut = True
                else:
                    self._porte_brute += caractere
            elif self._ligne_au_debut:
                if caractere in " \t\r":
                    self._blancs += caractere
                elif caractere == FLECHE:
                    self._dans_la_porte, self._porte_brute, self._blancs = True, "", ""
                    self._ligne_au_debut = False
                else:
                    sortie.append(self._blancs + caractere)
                    self._blancs = ""
                    self._ligne_au_debut = caractere == "\n"
            else:
                sortie.append(caractere)
                self._ligne_au_debut = caractere == "\n"
        return "".join(sortie)

    def _clore_la_ligne(self, *, complete: bool) -> None:
        """Une ligne « → » en cours est finie (``complete``) ou coupée en route."""
        if not self._dans_la_porte:
            return
        self._dans_la_porte = False
        if complete:
            self._portes_lues.append(_nom_de_porte(self._porte_brute))
        else:
            logger.warning("[porte] ligne « → » coupée en route : jamais prise")
            self._portes_lues.append(None)
        self._porte_brute = ""

    async def _annoncer_la_transition(self, direction: FrameDirection) -> None:
        """D16 : la phrase de transition écrite de la porte part avant la phrase du
        modèle, si rien n'est encore parti à la voix. Une fois par réponse."""
        if self._transition_dite or self._a_dit or not self._portes_lues:
            return
        if self._attente.strip():
            # La phrase du modèle a commencé (retenue, pas encore partie) : trop tard.
            return
        nom = self._portes_lues[0]
        if not nom:
            return
        phrase = self._portes.phrase_de_transition_ecrite(nom)
        if phrase:
            await self.push_frame(
                TTSSpeakFrame(phrase, append_to_context=False, persist_to_logs=True),
                direction,
            )
            # Elle ne compte pas comme une parole du modèle (revue du 05/10) : une
            # réponse faite de la seule porte fait encore reparler le modèle.
            self._transition_dite = True

    async def _prendre_la_porte(
        self,
        noms: list[str | None],
        transition_dite: bool,
        reponse: str | None,
        *,
        relancer: bool,
    ) -> dict:
        """La première porte lue est donnée au moteur ; rend ce qu'on trace."""
        if not noms:
            return {}
        detail: dict = {"porte": noms[0]}
        if len(noms) > 1:
            detail["portes_en_trop"] = len(noms) - 1
        if noms[0] is None:
            detail["porte_etat"] = "coupee"
        elif not noms[0]:
            logger.warning("[porte] « → » sans nom : rien")
            detail["porte_etat"] = "sans_nom"
        else:
            detail["porte_etat"] = await self._portes.prendre_porte_ecrite(
                noms[0],
                transition_dite=transition_dite,
                reponse=reponse,
                relancer=relancer,
            )
        return detail

    async def _porte_protegee(
        self, portes: tuple, trace: dict | None, *, relancer: bool
    ) -> None:
        """La porte de fin de réponse, dans une tâche que l'interruption n'annule pas
        (revue du 05/10) : la fin de réponse est une frame interruptible ; annulée
        pendant ``set_node``, l'étape changeait à moitié, ou pas du tout et sans
        trace. On l'attend sans pouvoir l'interrompre : elle finit toujours."""

        async def prendre() -> None:
            detail = await self._prendre_la_porte(*portes, relancer=relancer)
            self._completer_la_trace(trace, detail)

        tache = asyncio.get_running_loop().create_task(prendre())
        self._portes_en_cours.add(tache)
        tache.add_done_callback(self._portes_en_cours.discard)
        await asyncio.shield(tache)

    def _completer_la_trace(self, trace: dict | None, detail: dict) -> None:
        if not detail:
            return
        if trace is not None:
            trace.update(detail)
        else:
            self._tracer(ABSENT, [], **detail)

    async def _rattraper_la_phrase(
        self, champs: dict | None, direction: FrameDirection
    ) -> bool:
        """D10 : une phrase écrite APRÈS la note (un objet JSON lisible) part à la
        voix à la fin de la réponse. Une note sans objet JSON lisible n'est jamais
        dite (« RAS », « rien à noter ») : rien de technique à la voix (revue du 05/10)."""
        note = self._note
        if champs is None or "}" not in note:
            return False
        phrase = sans_json(note[note.rfind("}") + 1 :]).strip(" `")
        if not phrase or phrase.startswith(("//", "#", "(")):
            return False
        await self._dire(
            f" {phrase}" if self._a_dit else phrase, None, direction, fin=True
        )
        return True

    async def _noter(self, champs: dict | None, lus: list[dict]) -> None:
        """La note, par les mêmes contrôles que l'outil ; ses notices au tour suivant (D4).
        ``champs`` à ``None`` : la réponse n'a rien noté, ses notices s'effacent."""
        async with self._une_note_a_la_fois:
            if champs is None:
                if self._notices is not None:
                    self._notices.retenir(None)
                return
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


def _fin_de_l_objet(texte: str) -> int | None:
    """Où finit le premier objet JSON de ``texte`` (après son ``}``), ou ``None``
    s'il n'est pas encore fermé. Les accolades dans les chaînes ne comptent pas."""
    profondeur, dans_chaine, echappe, vu = 0, False, False, False
    for i, caractere in enumerate(texte):
        if dans_chaine:
            if echappe:
                echappe = False
            elif caractere == "\\":
                echappe = True
            elif caractere == '"':
                dans_chaine = False
        elif caractere == '"':
            dans_chaine = True
        elif caractere == "{":
            profondeur, vu = profondeur + 1, True
        elif caractere == "}" and profondeur:
            profondeur -= 1
            if not profondeur and vu:
                # Une clôture de bloc de code collée à l'objet reste dans la note.
                fin = i + 1
                suite = re.match(r"\s*```", texte[fin:])
                return fin + suite.end() if suite else fin
    return None


def _nom_de_porte(brut: str) -> str:
    """La ligne écrite après « → », TOUTE la ligne, écrite comme le nom d'une porte
    (D4) ; ``""`` : rien d'écrit. Une seconde flèche sur la même ligne est ignorée
    (une porte). ⛔ Jamais le premier mot seul (revue du 05/10) : « → Fin
    renseignement » donnait « fin », une AUTRE porte ; ici « fin_renseignement »,
    et tout ce qui n'est pas exactement un nom de porte est « inconnue »."""
    ligne = brut.split(FLECHE)[0].strip(_AUTOUR_DU_NOM)
    return transition_tool_name(ligne) if ligne else ""


def creer_post_scriptum(
    reglages: ReglagesFiche | None,
    *,
    fiche: Callable[[], dict],
    messages: Callable[[], Iterable[dict]],
    notices: Notices | None,
    attendu: Callable[[], bool] = lambda: True,
    notes_en_cours: set[asyncio.Task] | None = None,
    portes: Any = None,
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
        portes=portes,
    )


def post_scriptum_du_moteur(engine: Any) -> PostScriptumProcessor | None:
    """Le processeur de l'agent qui porte la fiche, branché sur le moteur de
    l'appel : sa fiche, sa conversation, ses notices, ses notes en cours.
    Une seule fabrique pour le téléphone et le clavier (relecture du 04/10 :
    ces lectures sont jouées par les tests, pas seulement lues au source)."""
    return creer_post_scriptum(
        engine.fiche,
        fiche=lambda: engine._gathered_context,
        messages=lambda: engine.context.get_messages() if engine.context else [],
        notices=engine.notices_fiche,
        attendu=engine.post_scriptum_attendu,
        notes_en_cours=engine.notes_en_cours,
        portes=engine,
    )
