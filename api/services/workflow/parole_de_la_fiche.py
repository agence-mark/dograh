"""[.mark] Chantier Partie 1, lot 6 : la phrase libre du modèle sur une étape qui porte la fiche (B8 « A et B », B9 point 3, B11 points 4 et 5,
B12 décision 1, repli A seul d'après B13, D62).

Branché à la place du contrôle des répliques (``reponse_avalee.RepliqueVerifiee``) quand l'étape montre la fiche au modèle : la phrase dite sans
appel d'outil est retenue selon ``actions_communes.parole.phrase_libre_retenue`` (critères structurels, D1 : aucune lecture des mots en dehors de
la barrière des chiffres), et le modèle repasse avec la ligne d'état du rappel ; la relance encore retenue est remplacée par la phrase du code
(``repli_dit_par_le_code``). Sur une autre étape, le contrôle d'avant est rendu tel quel. ⛔ Ne lève jamais : dans le doute, la réplique passe.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.repli import repli_dit_par_le_code
from api.services.commande import panier as P
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
        return None


def dossier_de_la_parole(fiche_de_l_appel: Any, connecteur: Any = None) -> dict:
    """Le dossier que la parole lit : celui que le connecteur déclare (``dossier_de_la_parole``), sinon le panier de la commande (lot 7)."""
    lire = getattr(connecteur, "dossier_de_la_parole", None)
    return lire(fiche_de_l_appel) if callable(lire) else P.du_dossier(fiche_de_l_appel)


def objet_en_cours(p: dict, connecteur: Any = None) -> bool:
    lire = getattr(connecteur, "objet_en_cours", None)
    return lire(p) if callable(lire) else _objet_en_cours(p)


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
            texte, etat, objet_en_cours=objet_en_cours(p, connecteur), question_en_attente=isinstance(p.get("question"), dict),
            paroles=[str(x) for x in (fiche or {}).get(CLE_DES_PAROLES) or []],
        )
        if raison is None and annonce_non_fondee(texte, p):
            # Lot 20 : une phrase libre qui annonce un enregistrement ou une annulation que l'état dément : retenue (le modèle repasse)
            from api.services.workflow.verite_des_actions import CONSIGNE_ACTION, RAISON_ACTION_NON_FAITE

            PAROLE.garder(fiche, etat)
            return Retenue(RAISON_ACTION_NON_FAITE, texte[:80], CONSIGNE_ACTION)
        if raison is None:
            # la phrase est dite ; le prix d'une proposition née dans ce tour la suit, dit par le code (D33)
            dit = PAROLE.avec_le_suffixe(texte, etat)
            if not dit:
                # Lot 20 : rien n'a changé dans ce tour et une question attend : après sa phrase (« je n'ai pas compris »), le code repose la question
                reprise = PAROLE.reprise_apres_la_phrase(texte, etat, p, getattr(connecteur, "texte_du_manque", None), fiche)
                if reprise:
                    PAROLE.garder(fiche, etat)
                    return Retenue(PAROLE.REPRISE, texte[:80], "", a_dire=f"{PAROLE.sans_balisage(texte)} {reprise}")
            PAROLE.garder(fiche, etat)
            return Retenue(PAROLE.SUFFIXE, texte[:80], "", a_dire=dit) if dit else None
        PAROLE.garder(fiche, etat)
        if relance or raison == PAROLE.REPLI_A and etat.retenues.count(PAROLE.REPLI_A) > 1:
            # Au bout : la phrase du code (la question en attente, sinon ce qui manque) ; le code redemande, il ne choisit rien.
            repli = repli_dit_par_le_code(p, getattr(connecteur, "texte_du_manque", None), fiche)
            if etat.suffixe:
                # Conversation du lot 12 (PRX5-A) : le prix lu que le code devait dire après la phrase n'est pas perdu quand la phrase (au chiffre) est retenue jusqu'au repli
                repli = " ".join(x for x in (etat.suffixe, repli) if x)
                etat.suffixe = etat.suffixe_lu = None
                PAROLE.garder(fiche, etat)
            return Retenue(raison, texte[:80], PAROLE.RAPPELS[raison], a_dire=repli)
        return Retenue(raison, texte[:80], PAROLE.RAPPELS[raison])

    def controler(self, texte: str, messages: Any = None) -> Retenue | None:
        try:
            if not porte_la_fiche(self._fiche()):
                return self.autre.controler(texte, messages) if self.autre is not None else None
            retenue = self._retenue(texte, relance=False)
            if retenue is not None and retenue.raison not in (PAROLE.SUFFIXE, PAROLE.REPRISE):
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
                tracer_une_retenue(self.moteur, retenue.raison, detail="repli du code")
                return retenue
            return None
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[parole] relance non contrôlée : {erreur!r}")
            return None

    def controler_le_silence(self, messages: Any = None) -> Retenue | None:
        """Point de contrôle du lot 7 (conversation 2, tour muet hors zone) : sur une étape qui porte la fiche, le modèle n'a rendu ni texte ni
        appel au bout de ses passes (le flux, puis sa relance sans flux). Jamais un tour muet : la phrase du code est dite (la question en
        attente, sinon ce qui manque, ``repli_dit_par_le_code``), comme pour une relance retenue. Ailleurs : le contrôle d'avant, s'il en a un."""
        try:
            if not porte_la_fiche(self._fiche()):
                autre = getattr(self.autre, "controler_le_silence", None)
                return autre(messages) if autre is not None else None
            fiche = self._fiche()
            connecteur = _connecteur_de_l_etape(self.moteur)
            p = dossier_de_la_parole(fiche, connecteur)
            a_dire = repli_dit_par_le_code(p, getattr(connecteur, "texte_du_manque", None), fiche)
            if not a_dire:
                return None
            tracer_une_retenue(self.moteur, PAROLE.SILENCE, detail="repli du code")
            return Retenue(PAROLE.SILENCE, "", "", a_dire=a_dire)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[parole] silence non contrôlé : {erreur!r}")
            return None

    def controler_avant_outil(self, texte: str, messages: Any = None) -> Retenue | None:
        if porte_la_fiche(self._fiche()):
            return None  # B12 : sur la fiche, ce que le modèle écrit avec l'appel est sa case ``a_dire``, jugée au retour de la fiche
        autre = getattr(self.autre, "controler_avant_outil", None)
        return autre(texte, messages) if autre is not None else None


ANNONCE_NON_FONDEE = "annonce_non_fondee"


def annonce_non_fondee(texte: Any, p: Any) -> bool:
    """Lot 20 (appels 455, 460) : la phrase annonce-t-elle que la commande est enregistrée (confirmée, validée) ou annulée alors que son ÉTAT dit le
    contraire ? La règle « c'est fait » de la vérité des actions (SA-18), comparée au dossier de la parole ; une question n'annonce rien. Un dossier qui
    ne porte pas « enregistree » (une autre action) n'est pas jugé ici. ⛔ Ne lève jamais (dans le doute : non)."""
    try:
        from api.services.workflow.verite_des_actions import _phrases, regle_de_l_action_faite

        if not isinstance(p, dict) or "enregistree" not in p or not texte:
            return False
        faite = regle_de_l_action_faite(("enregistré", "confirmé", "validé"))
        annulee = regle_de_l_action_faite(("annulé",))
        for phrase in _phrases(str(texte)):
            if phrase.rstrip().endswith("?"):
                continue
            if faite is not None and not p.get("enregistree") and faite.search(phrase):
                return True
            if annulee is not None and not p.get("annulee") and annulee.search(phrase):
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


CLES_DU_NOM = ("prenom", "nom")
CLES_QUI_PORTENT_UN_ARTICLE = ("proposition_en_plus",)  # son « nom » est celui de l'article proposé (« Coca-Cola »), jamais celui de la personne


def noms_de_la_personne(p: Any, profondeur: int = 3) -> list[str]:
    """B5 (audit des textes § 2.5) : le prénom et le nom que la personne a donnés, lus dans le dossier (commande : ``client.prenom`` ; réservation :
    ``nom``). Les listes (les lignes et leurs noms d'articles) ne sont jamais lues."""
    noms: list[str] = []
    if isinstance(p, dict) and profondeur > 0:
        for cle, valeur in p.items():
            if cle in CLES_DU_NOM and isinstance(valeur, str) and len(valeur.strip()) >= 2:
                noms.append(valeur.strip())
            elif isinstance(valeur, dict) and cle not in CLES_QUI_PORTENT_UN_ARTICLE:
                noms.extend(noms_de_la_personne(valeur, profondeur - 1))
    return noms


def sans_le_nom(phrase: str | None, noms: list[str]) -> str | None:
    """« C'est bien noté, Paul. » → « C'est bien noté. » : la phrase du modèle ne dit jamais le nom de la personne (enfreint au jeu 3 : 533, 482).
    Le nom entier puis chacun de ses mots (deux lettres au moins), avec la virgule et « au nom de » qui l'entourent. ⛔ Ne lève jamais."""
    import re

    if not phrase or not noms:
        return phrase
    try:
        texte = phrase
        mots = sorted({m for n in noms for m in [n, *n.split()] if len(m) >= 2}, key=len, reverse=True)
        for mot in mots:
            texte = re.sub(rf"(?:\s*,)?\s*(?:au nom de\s+)?(?<![\w-]){re.escape(mot)}(?![\w-])", " ", texte, flags=re.IGNORECASE)
        # l'espace française avant « ? » et « ! » est gardée ; seules celles devant « . » et « , » sont retirées
        texte = re.sub(r"\s+([.,])", r"\1", re.sub(r"\s{2,}", " ", texte)).strip(" ,;")
        return (texte[:1].upper() + texte[1:]) if texte else None
    except Exception:  # noqa: BLE001
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
            decision = PAROLE.Decision(PAROLE.SECOND_PASSAGE, motif=ANNONCE_NON_FONDEE, prefixe=decision.prefixe)
        if decision.mode == PAROLE.A_DIRE_SEUL and decision.motif != "texte_du_code" and decision.a_dire:
            # B5 : « Tu ne dis jamais son nom ni son prénom » est contrôlé par le code avant de dire la phrase (plus par le texte)
            propre = sans_le_nom(decision.a_dire, noms_de_la_personne(p))
            if propre != decision.a_dire:
                from dataclasses import replace

                decision = replace(decision, a_dire=propre) if propre else PAROLE.Decision(PAROLE.SECOND_PASSAGE, motif="nom_retire", prefixe=decision.prefixe)
        PAROLE.garder(fiche_de_l_appel, etat)
        return decision
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[parole] retour de la fiche non jugé : {erreur!r}")
        return PAROLE.Decision(PAROLE.SECOND_PASSAGE, motif="erreur")
