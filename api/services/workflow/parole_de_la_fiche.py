"""[.mark] Chantier Partie 1, lot 6 : la phrase libre du modèle sur une étape qui porte la fiche (B8 « A et B », B9 point 3, B11 points 4 et 5,
B12 décision 1, repli A seul d'après B13, D62).

Branché à la place du contrôle des répliques (``reponse_avalee.RepliqueVerifiee``) quand l'étape montre la fiche au modèle : la phrase dite sans
appel d'outil est retenue selon ``actions_communes.parole.phrase_libre_retenue`` (critères structurels, D1 : aucune lecture des mots en dehors de
la barrière des chiffres), et le modèle repasse avec la ligne d'état du rappel ; la relance encore retenue est remplacée par une relance du modèle avec le fait (``consigne_de_relance``, une par tour), puis par la suite réglée déjà posée (motifs de ``PHRASES_DU_CODE``) ou la phrase réglée « pas compris » de l'agent (P3) : le code ne compose aucune phrase (C5, reprise R1 de C6). Sur une autre étape, le contrôle d'avant est rendu tel quel. ⛔ Ne lève jamais : dans le doute, la réplique passe.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from typing import Any

from loguru import logger

from api.services.actions_communes import du as DU
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.barriere_des_chiffres import porte_les_chiffres
from api.services.actions_communes.repli import consigne_de_ce_que_le_code_dit, consigne_des_chiffres_exiges, consigne_de_relance
from api.services.commande import panier as P
from api.services.phrases.catalogue import REPONSE_PERDUE
from api.services.workflow.verite_des_actions import Retenue, tracer_une_retenue

CLE_DES_PAROLES = "paroles_de_la_personne"


def porte_la_fiche(fiche_de_l_appel: Any) -> bool:
    """L'étape de cette requête montre-t-elle la fiche au modèle (les cases montrées du tour, D52) ?"""
    from api.services.integrations.connectors.outil import nom_vu
    from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

    if not isinstance(fiche_de_l_appel, dict):
        return False
    montrees = fiche_de_l_appel.get(CLE_DES_CASES_MONTREES) or {}
    return isinstance(montrees, dict) and any(n in montrees for n in ("fiche", nom_vu(fiche_de_l_appel, "fiche")))


def _objet_en_cours(p: dict) -> bool:
    return bool(p.get("lignes") or p.get("mode") or p.get("enregistree"))


def _connecteur_de_l_etape(moteur: Any):
    """Le connecteur dont la ``fiche`` est montrée à cette étape (la commande, la réservation), ou ``None``."""
    from api.services.workflow.cases_selon_l_etat import _connecteur_de

    try:
        return _connecteur_de(moteur, "fiche")
    except Exception:  # noqa: BLE001
        logger.exception("[parole] connecteur de l'étape non lu : aucun connecteur, la parole retombe sur le panier")
        return None


def dossier_de_la_parole(fiche_de_l_appel: Any, connecteur: Any = None) -> dict:
    """Le dossier que la parole lit : celui que le connecteur déclare (``dossier_de_la_parole``), sinon le panier de la commande (lot 7)."""
    lire = getattr(connecteur, "dossier_de_la_parole", None)
    return lire(fiche_de_l_appel) if callable(lire) else P.du_dossier(fiche_de_l_appel)


def objet_en_cours(p: dict, connecteur: Any = None) -> bool:
    lire = getattr(connecteur, "objet_en_cours", None)
    return lire(p) if callable(lire) else _objet_en_cours(p)


def _suite_reglee(fiche: Any, p: dict, etat: PAROLE.EtatDuTour) -> str | None:
    """Reprise R1 de l'audit de C6 : la relance a échoué, la suite réglée déjà posée part seule (``PAROLE.la_suite_reglee``) ; la phrase du total qui part ainsi rend la relecture entendue.
    ``None`` : rien de réglé, P3."""
    a_dire = PAROLE.la_suite_reglee(etat)
    PAROLE.noter_le_total_dit(p, etat, a_dire)
    PAROLE.garder(fiche, etat)
    return a_dire


class VerificateurDeLaFiche:
    """Le contrôle de la phrase libre d'une étape qui porte la fiche ; ``autre`` : le contrôle d'avant, pour toute autre étape."""

    def __init__(self, moteur: Any, autre: Any = None):
        self.moteur = moteur
        self.autre = autre

    def _fiche(self) -> dict | None:
        fiche = getattr(self.moteur, "_gathered_context", None)
        return fiche if isinstance(fiche, dict) else None

    def _retenue(self, texte: str, relance: bool) -> Retenue | None:
        fiche = self._fiche()
        etat = PAROLE.etat_du_tour(fiche)
        connecteur = _connecteur_de_l_etape(self.moteur)
        p = dossier_de_la_parole(fiche, connecteur)
        raison = PAROLE.phrase_libre_retenue(
            texte, etat, objet_en_cours=objet_en_cours(p, connecteur), question_en_attente=CONV.question_de(p) is not None,
            paroles=[str(x) for x in (fiche or {}).get(CLE_DES_PAROLES) or []], p=p,
        )
        if raison is None and annonce_non_fondee(texte, p):
            # Lot 20 : une phrase libre qui annonce un enregistrement ou une annulation que l'état dément : retenue (le modèle repasse)
            from api.services.workflow.verite_des_actions import CONSIGNE_ACTION, RAISON_ACTION_NON_FAITE

            PAROLE.garder(fiche, etat)
            return Retenue(RAISON_ACTION_NON_FAITE, texte[:80], CONSIGNE_ACTION)
        if raison is None and PAROLE.dit_ce_que_le_code_dit(texte, etat):
            # C6 : le code dit la question après la phrase (la relecture) ; une phrase du modèle qui la pose déjà est relancée une fois ; si la relance la pose encore,
            # la phrase du modèle n'est pas dite et seule la phrase réglée du code part (R0 : jamais un tour muet), sans nouvelle requête
            consigne = consigne_de_ce_que_le_code_dit(etat)
            a_dire = None
            if not consigne:
                a_dire = PAROLE.la_suite_reglee(etat)  # la suite réglée seule (PE-2 : précédée de la confirmation réglée de la commande), la question du modèle attend
                PAROLE.noter_le_total_dit(p, etat, a_dire)  # la phrase du total est dite, seule : la relecture est entendue
            PAROLE.garder(fiche, etat)
            return Retenue(PAROLE.CE_QUE_LE_CODE_DIT, texte[:80], consigne or "", a_dire=a_dire)
        due = etat.exiges is not None and PAROLE.question_due_sans_suite(texte, etat.suffixe, CONV.question_de(p) is not None)
        if raison is None and etat.exiges is not None and (due or not porte_les_chiffres(texte, etat.exiges)):
            # C6 n° 5 : la confirmation du modèle ne dit pas l'heure (valeur exigée), ou (R2) la phrase ne pose pas la question qui attend alors que le code ne dit rien après elle :
            # relancée une fois ; ensuite la suite réglée seule, sinon P3 (R1 : jamais le fait accompli)
            consigne = consigne_des_chiffres_exiges(etat, question_due=due)
            a_dire = None if consigne else PAROLE.la_suite_reglee(etat)
            PAROLE.garder(fiche, etat)
            return Retenue(PAROLE.CHIFFRES_EXIGES, texte[:80], consigne or "", a_dire=a_dire)
        if raison is None:
            # la phrase est dite ; la phrase réglée du code la suit (le total de la relecture, ou le rendu et la question après la confirmation : C6)
            etat.exiges = None
            dit = PAROLE.avec_le_suffixe(texte, etat, p)
            if not dit and PAROLE.question_oubliee(texte, etat, p) and (consigne := consigne_de_relance(p, fiche, etat, connecteur)):
                # Lot 20 : rien n'a changé dans ce tour et une question attend, la phrase (« je n'ai pas compris ») ne la pose pas : le modèle repasse avec elle (C5)
                PAROLE.garder(fiche, etat)
                return Retenue(PAROLE.REPRISE, texte[:80], consigne)
            if not dit:
                PAROLE.noter_le_total_dit(p, etat, texte)  # C6 n° 8 : la relecture de la réservation part seule (sans phrase réglée après elle) : entendue si elle dit les valeurs exigées
            PAROLE.garder(fiche, etat)
            return Retenue(PAROLE.SUFFIXE, texte[:80], "", a_dire=dit) if dit else None
        PAROLE.garder(fiche, etat)
        if relance or raison == PAROLE.REPLI_A and etat.retenues.count(PAROLE.REPLI_A) > 1:
            return self._au_bout(raison, texte, relance, p, connecteur)
        return Retenue(raison, texte[:80], PAROLE.RAPPELS[raison])

    def _au_bout(self, raison: str, texte: str, relance: bool, p: dict, connecteur: Any) -> Retenue:
        """Au bout (une relance retenue, ou le repli A redit) : C5, décision d'Evan 25/11 8 h 45, le code ne dit pas la question ni le refus ; il relance le modèle UNE fois
        avec le fait (``consigne_de_relance``). Déjà fait dans ce tour : la suite réglée déjà posée (``_suite_reglee``), sinon rien (``RepliqueVerifiee`` dit la phrase réglée, P3)."""
        fiche = self._fiche()
        etat = PAROLE.etat_du_tour(fiche)
        consigne = consigne_de_relance(p, fiche, etat, connecteur)
        if consigne:
            PAROLE.garder(fiche, etat)
            return Retenue(raison, texte[:80], consigne)
        a_dire = _suite_reglee(fiche, p, etat)
        return Retenue(raison, texte[:80], "" if relance else PAROLE.RAPPELS[raison], a_dire=a_dire)

    def controler(self, texte: str, messages: Any = None) -> Retenue | None:
        try:
            if not porte_la_fiche(self._fiche()):
                return self.autre.controler(texte, messages) if self.autre is not None else None
            retenue = self._retenue(texte, relance=False)
            if retenue is not None and retenue.raison != PAROLE.SUFFIXE:
                tracer_une_retenue(self.moteur, retenue.raison, detail=retenue.detail)
            return retenue
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[parole] réplique non contrôlée : {erreur!r}")
            return None

    def controler_la_relance(self, texte: str, messages: Any = None) -> Retenue | None:
        try:
            if not porte_la_fiche(self._fiche()):
                autre = getattr(self.autre, "controler_la_relance", None)
                return autre(texte, messages) if autre is not None else None
            retenue = self._retenue(texte, relance=True)
            if retenue is not None:
                # P2 (lot 19 bis) : une relance retenue n'est jamais dite, même quand le code n'a pas de phrase de remplacement (``a_dire`` vide : ``RepliqueVerifiee`` dit alors sa phrase neutre)
                tracer_une_retenue(self.moteur, retenue.raison, detail="relance du fait ou suite réglée")
                return retenue
            return None
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[parole] relance non contrôlée : {erreur!r}")
            return None

    def controler_le_silence(self, messages: Any = None, sans_relance: bool = False) -> Retenue | None:
        """Point de contrôle du lot 7 (conversation 2, tour muet hors zone) : sur une étape qui porte la fiche, le modèle n'a rendu ni texte ni
        appel au bout de ses passes (le flux, puis sa relance sans flux). Jamais un tour muet. C5 (décision d'Evan 25/11 8 h 45) : le code ne compose pas
        de phrase, il RELANCE le modèle avec le fait (``consigne_de_relance``) ; sans rien à relancer, la suite réglée déjà posée (R1, ``_suite_reglee``), sinon une retenue vide (sans consigne ni
        texte : ``RepliqueVerifiee`` dit alors la phrase réglée de l'agent, P3) : sur ces étapes elle ne rend jamais ``None``. ``sans_relance`` : la relance du modèle a échoué ou n'est plus permise,
        seule la suite réglée reste. Ailleurs : le contrôle d'avant, s'il en a un (``None`` possible). En cas d'erreur de lecture (T1) : jamais ``None`` sur une étape qui porte la fiche,
        une retenue vide (la phrase réglée, P3, sans requête de plus) et une ligne au journal ; ailleurs ``None`` (le flux rendu tel quel). Jamais une exception."""
        fiche_portee = False
        try:
            fiche_portee = porte_la_fiche(self._fiche())
            if not fiche_portee:
                autre = getattr(self.autre, "controler_le_silence", None)
                return autre(messages) if autre is not None else None
            fiche = self._fiche()
            connecteur = _connecteur_de_l_etape(self.moteur)
            p = dossier_de_la_parole(fiche, connecteur)
            etat = PAROLE.etat_du_tour(fiche)
            consigne = None if sans_relance else consigne_de_relance(p, fiche, etat, connecteur)
            if consigne:
                PAROLE.garder(fiche, etat)
                tracer_une_retenue(self.moteur, PAROLE.SILENCE, detail="relance du fait")
                return Retenue(PAROLE.SILENCE, "", consigne)
            a_dire = _suite_reglee(fiche, p, etat)
            if not a_dire:
                tracer_une_retenue(self.moteur, PAROLE.SILENCE, detail="phrase réglée")
                return Retenue(PAROLE.SILENCE, "", "")
            tracer_une_retenue(self.moteur, PAROLE.SILENCE, detail="suite réglée")
            return Retenue(PAROLE.SILENCE, "", "", a_dire=a_dire)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[parole] silence non contrôlé : {erreur!r}")
            # T1 : sur la fiche, jamais un tour muet : la retenue vide fait dire la phrase réglée (``RepliqueVerifiee._rien_a_relancer``)
            return Retenue(PAROLE.SILENCE, "", "") if fiche_portee else None

    def controler_avant_outil(self, texte: str, messages: Any = None) -> Retenue | None:
        if porte_la_fiche(self._fiche()):
            return None  # B12 : sur la fiche, ce que le modèle écrit avec l'appel est sa case ``a_dire``, jugée au retour de la fiche
        autre = getattr(self.autre, "controler_avant_outil", None)
        return autre(texte, messages) if autre is not None else None


ANNONCE_NON_FONDEE = "annonce_non_fondee"


# Pierre 12 : « J'ai bien enregistré votre allergie / votre numéro » a pour objet autre chose que la commande ou la réservation : jamais jugée ; « Votre commande est passée » dit la
# même chose qu'« enregistrée ». Ces mots sont ceux du métier : ils sont donnés à la règle commune des actions, qui n'en porte aucun.
ECART_DE_L_ANNONCE = (("enregistré", "confirmé", "validé"), ("commande", "réservation"))
FORME_PASSEE_DE_LA_COMMANDE = r"\bcommande\b[^.!?]*\b(?:est|a\s+été)\s+(?:bien\s+|déjà\s+)?pass[ée]e?\b"


FAITS_DE_L_ANNULATION = ("annulee", "annulee_en_cours")  # les faits accomplis de l'annulation (``porte.textes_du_code``) : le modèle les dit (C6 n° 7)


def annulation_dite_ce_tour(p: Any) -> bool:
    """T43 R1 : le fait que le modèle dit à ce tour est l'annulation (gardé au journal par la porte, ``J.dire_le_fait``), même quand un mode qui la suit a effacé la marque
    « annulee » du dossier (« Annulez, finalement en livraison » : décision du 27/11 7 h 23, le client entend « C'est annulé »). ⛔ Ne lève jamais."""
    try:
        from api.services.actions_communes import journal_du_dit as J

        faits = J.fait_accompli(p) if isinstance(p, dict) else None
        return bool(faits) and faits.get("fait") in FAITS_DE_L_ANNULATION and not J.dit_a_un_tour_d_avant(p, J.FAIT_ACCOMPLI)
    except Exception:  # noqa: BLE001
        logger.exception("[parole] fait du tour non lu : l'annulation n'est pas tenue pour dite")
        return False


def annonce_non_fondee(texte: Any, p: Any) -> bool:
    """Lot 20 (appels 455, 460) : la phrase annonce-t-elle que la commande est enregistrée (confirmée, validée) ou annulée alors que son ÉTAT dit le
    contraire ? La règle « c'est fait » de la vérité des actions (SA-18), comparée au dossier de la parole ; une question n'annonce rien. Un dossier qui
    ne porte pas « enregistree » (une autre action) n'est pas jugé ici. T43 R1 : « annulé » est fondé quand le dossier est annulé OU quand l'annulation est
    le fait dit de ce tour (``annulation_dite_ce_tour``). ⛔ Ne lève jamais (dans le doute : non)."""
    try:
        from api.services.workflow.verite_des_actions import _phrases, regle_de_l_action_faite

        if not isinstance(p, dict) or "enregistree" not in p or not texte:
            return False
        faite = regle_de_l_action_faite(("enregistré", "confirmé", "validé"), sauf_si_autre_objet=ECART_DE_L_ANNONCE, formes_en_plus=(FORME_PASSEE_DE_LA_COMMANDE,))
        annulee = None if p.get("annulee") or annulation_dite_ce_tour(p) else regle_de_l_action_faite(("annulé",), sauf_si_autre_objet=ECART_DE_L_ANNONCE)

        for phrase in _phrases(str(texte)):
            if phrase.rstrip().endswith("?"):
                continue
            if faite is not None and not p.get("enregistree") and faite.search(phrase):
                return True
            if annulee is not None and annulee.search(phrase):
                return True
        return False
    except Exception:  # noqa: BLE001
        logger.exception("[parole] annonce non jugée : la phrase n est pas jugée infondée")
        return False


CHEMINS_DU_NOM = (("prenom",), ("nom",), ("client", "prenom"), ("client", "nom"))  # Pierre 11 : le prénom et le nom de la PERSONNE, jamais une autre clé « nom »


def noms_de_la_personne(p: Any) -> list[str]:
    """B5 (audit des textes § 2.5) : le prénom et le nom que la personne a donnés, lus dans le dossier à leurs seuls chemins (commande : ``client.prenom`` ;
    réservation : ``prenom`` et ``nom`` à la racine). Pierre 11 : jamais une autre clé « nom » (la zone de livraison, l'article proposé, un dossier d'ailleurs)."""
    noms: list[str] = []
    if isinstance(p, dict):
        for chemin in CHEMINS_DU_NOM:
            valeur: Any = p
            for cle in chemin:
                valeur = valeur.get(cle) if isinstance(valeur, dict) else None
            if isinstance(valeur, str) and len(valeur.strip()) >= 2 and valeur.strip() not in noms:
                noms.append(valeur.strip())
    return noms


def sans_le_nom(phrase: str | None, noms: list[str]) -> str | None:
    """« C'est bien noté, Paul. » → « C'est bien noté. » : la phrase du modèle ne dit jamais le nom de la personne (enfreint au jeu 3 : 533, 482).
    Pierre 11 : le nom (entier, ou chacun de ses mots de deux lettres au moins) ne part qu'en POSITION D'ADRESSE : après une virgule en fin de proposition
    (« …, Paul. »), en tête de phrase suivi d'une virgule (« Paul, c'est noté »), ou derrière « au nom de ». Un mot de la phrase qui est aussi le sien
    (« pour le dîner » pour « Le Goff », « une reine » pour « Reine ») reste. ⛔ Ne lève jamais."""
    import re

    if not phrase or not noms:
        return phrase
    try:
        texte = phrase
        mots = sorted({m for n in noms for m in [n, *n.split()] if len(m) >= 2}, key=len, reverse=True)
        net = re.sub(r"[\W_]+", " ", texte.casefold()).strip()
        if any(net == re.sub(r"[\W_]+", " ", m.casefold()).strip() for m in mots):
            return None  # rien d'autre que le nom : le modèle repasse
        for mot in mots:
            m = re.escape(mot)
            texte = re.sub(rf"\s*,\s*{m}(?![\w-])(?=\s*(?:[.!?,;…]|$))", "", texte, flags=re.IGNORECASE)  # « …, Paul. » « …, Paul, à emporter »
            texte = re.sub(rf"(?:^|(?<=[.!?…]\s)){m}(?![\w-])\s*,\s*", "", texte, flags=re.IGNORECASE)  # « Paul, c'est noté »
            texte = re.sub(rf"\s*au nom de\s+{m}(?![\w-])", "", texte, flags=re.IGNORECASE)
        # l'espace française avant « ? » et « ! » est gardée ; seules celles devant « . » et « , » sont retirées
        texte = re.sub(r"\s+([.,])", r"", re.sub(r"\s{2,}", " ", texte)).strip(" ,;")
        return (texte[:1].upper() + texte[1:]) if texte else None
    except Exception:  # noqa: BLE001
        logger.exception("[parole] nom de la personne non retiré : la phrase est gardée telle quelle")
        return phrase


def decider_apres_la_fiche(fiche_de_l_appel: Any, retour: Any, arguments: Any, connecteur: str | None = None) -> PAROLE.Decision:
    """Le retour de la fiche de ce tour : ``a_dire`` dite seule (un passage, ``run_llm`` faux), ou second passage avec le retour (lot 6, étape 1).
    ⛔ Ne lève jamais : dans le doute, second passage (le modèle reformule avec le retour, comme avant)."""
    try:
        etat = PAROLE.etat_du_tour(fiche_de_l_appel)
        from api.services.integrations.connectors.catalogue import connecteur as connecteur_nomme

        nomme = connecteur_nomme(connecteur) if connecteur else None
        p = dossier_de_la_parole(fiche_de_l_appel, nomme)
        arguments = arguments if isinstance(arguments, dict) else {}
        CLE_TEXTES_DU_CODE = PAROLE.CLE_TEXTES_DU_CODE

        textes = fiche_de_l_appel.pop(CLE_TEXTES_DU_CODE, None) if isinstance(fiche_de_l_appel, dict) else None
        decision = PAROLE.parole_du_tour(
            retour if isinstance(retour, dict) else {}, arguments.get("a_dire"), etat,
            [str(x) for x in (fiche_de_l_appel or {}).get(CLE_DES_PAROLES) or []] if isinstance(fiche_de_l_appel, dict) else [], p, arguments,
            textes, objet_en_cours(p, nomme),
        )
        if decision.mode == PAROLE.A_DIRE_SEUL and decision.motif != "texte_du_code" and annonce_non_fondee(decision.a_dire, p):
            # Lot 20 : « votre commande est bien enregistrée » sur un panier vide : jamais dit ; le modèle repasse avec le retour
            decision = PAROLE.Decision(PAROLE.SECOND_PASSAGE, motif=ANNONCE_NON_FONDEE)
        if decision.mode == PAROLE.A_DIRE_SEUL and decision.motif != "texte_du_code" and decision.a_dire:
            # B5 : « Tu ne dis jamais son nom ni son prénom » est contrôlé par le code avant de dire la phrase (plus par le texte)
            propre = sans_le_nom(decision.a_dire, noms_de_la_personne(p))
            if propre != decision.a_dire:
                from dataclasses import replace

                decision = replace(decision, a_dire=propre) if propre else PAROLE.Decision(PAROLE.SECOND_PASSAGE, motif="nom_retire")
        if decision.mode != PAROLE.A_DIRE_SEUL and isinstance(retour, dict) and retour.get(DU.CLE_FAITS_A_DIRE):
            # Pierre A3 : des faits à dire (l'allergie) ne sont notés « donnés » que lorsque la parole laisse le modèle les recevoir (le code qui dit sa phrase seule ne les donne pas)
            from api.services.commande.moteur import noter_les_faits_donnes

            noter_les_faits_donnes(p)
        if decision.mode == PAROLE.A_DIRE_SEUL:
            PAROLE.noter_le_total_dit(p, etat, decision.a_dire)  # C6 : la phrase du total part avec celle du modèle (question déjà donnée) : la relecture est entendue
        PAROLE.garder(fiche_de_l_appel, etat)
        return decision
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[parole] retour de la fiche non jugé : {erreur!r}")
        return PAROLE.Decision(PAROLE.SECOND_PASSAGE, motif="erreur")


async def dire_le_retour(engine: Any, fiche: Any, donnees: Any, params: Any, connecteur: str | None, workflow_id: Any) -> bool:
    """Lot 7a (ligne 110) : ce que l'outil d'un connecteur qui porte la fiche (``Connecteur.porte_la_fiche``) fait du retour de sa fiche, après qu'elle est jouée : l'agent qui l'écrit tient l'action
    (M8, porteur noté sous la conversation de l'appel, ligne 122), la parole décide (``decider_apres_la_fiche``), puis la phrase dite seule (lot 6, B12, D5) ; sinon le modèle repasse.
    Vrai : la phrase est dite seule, le résultat est rendu à Pipecat, l'outil n'a plus rien à rendre ; faux : l'outil rend le retour au modèle."""
    from pipecat.frames.frames import FunctionCallResultProperties

    from api.services.actions_communes.enveloppe_legere import pour_le_modele
    from api.services.groupe.passations import noter_le_porteur

    noter_le_porteur(fiche, connecteur, workflow_id)
    decision = decider_apres_la_fiche(fiche, donnees, params.arguments, connecteur)
    if decision.mode == PAROLE.A_DIRE_SEUL and not decision.a_dire and decision.motif == REPONSE_PERDUE:
        # T12 : relance ratée sans suite réglée : la phrase réglée « pas compris » de l'agent (P3), jamais un tour muet
        from dataclasses import replace

        from api.services.pipecat.reponse_avalee import phrase_de_repli_reglee

        decision = replace(decision, a_dire=phrase_de_repli_reglee(getattr(getattr(engine, "active_agent", None), "llm", None)))
    if decision.mode == PAROLE.A_DIRE_SEUL and decision.a_dire:
        # Clôture, lot B2 (IC5, inventaire C5 : 390 retours sur 718 sans elle) : ce qui est dit entre dans l'historique du modèle comme
        # réplique de l'agent ; sans elle, le modèle ne sait pas ce que la personne a entendu (le récapitulatif, la question du code)
        await engine.queue_text_message(decision.a_dire, mute_user=True, append_to_context=True)
        # P3 : une lecture du même tour attend le modèle (Pipecat ne relance qu'au dernier résultat du groupe) : sa phrase est dite et le modèle repasse pour répondre à la lecture
        await params.result_callback(pour_le_modele(donnees), properties=None if PAROLE.la_fiche_laisse_la_relance(fiche) else FunctionCallResultProperties(run_llm=False))
        return True
    return False
