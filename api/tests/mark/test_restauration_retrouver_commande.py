"""[.mark] Module Restauration, lot 7, étape 7 : retrouver une commande déjà passée (outil ``retrouver_commande``).

Vraie base, carte de référence, jeudi 12 h.

| Test | Ce qu'il prouve |
|---|---|
| retrouvée | par le numéro qui s'affiche ou par le numéro de la commande (court ou long) ; dit « enregistrée » et l'heure, jamais une étape de la préparation (E-36) |
| statuts lus | annulée dite annulée ; refusée ou en échec : l'équipe rappelle ; les étapes intermédiaires ne se disent pas |
| plusieurs | on demande laquelle, jamais au hasard |
| cloisonnement | jamais la commande d'un autre établissement ni d'un autre numéro |
| inconnue | introuvable : la phrase, rien d'inventé ; sans numéro ni numéro affiché : on demande le numéro |
"""

from __future__ import annotations

from api.services.commande import moteur
from api.services.commande.moteur import Appelant
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import TEL, Appel


async def _passer(commerce, affiche=TEL):
    a = await Appel(commerce, affiche=affiche, vente_en_plus=False).pret(A("regina", 1, "Normale"))
    await a.jusqu_a_la_relecture()
    fait = await a.confirmer()
    assert fait.statut in ("ENREGISTREE", "TRANSMISE"), fait
    return fait.faits


async def test_retrouvee_par_le_numero_qui_s_affiche_ou_par_son_numero_dit_enregistree_et_l_heure(commerce):  # noqa: F811
    faits = await _passer(commerce)
    a = Appel(commerce)
    r = await moteur.retrouver_commande(a.source, a.p, a.regles, a.appelant)
    assert r.statut == "OK" and r.faits["numero_court"] == faits["numero_court"]
    assert r.suggestion.startswith("Votre commande est enregistrée pour ") and "douze heures vingt" in r.suggestion     # jeudi midi + 20 minutes
    par_court = await moteur.retrouver_commande(a.source, a.p, a.regles, Appelant(None, "x"), faits["numero_court"])
    par_long = await moteur.retrouver_commande(a.source, a.p, a.regles, Appelant(None, "x"), faits["numero"])
    assert par_court.faits["numero_court"] == par_long.faits["numero_court"] == faits["numero_court"]
    # une étape de la préparation ne se dit jamais
    await commerce.c.execute("UPDATE mark.resto_commande SET statut = 'en_preparation' WHERE numero = $1::uuid", faits["numero"])
    dit = await moteur.retrouver_commande(a.source, a.p, a.regles, a.appelant)
    assert dit.faits["statut"] == "en_preparation" and "préparation" not in dit.suggestion and dit.suggestion.startswith("Votre commande est enregistrée")


async def test_les_statuts_perdus_sont_dits_tels_quels(commerce):  # noqa: F811
    faits = await _passer(commerce)
    a = Appel(commerce)
    for statut, debut_de_phrase in (("annulee", "Cette commande est annulée."), ("refusee", "Cette commande n'est pas passée"), ("echec", "Cette commande n'est pas passée")):
        await commerce.c.execute("UPDATE mark.resto_commande SET statut = $2 WHERE numero = $1::uuid", faits["numero"], statut)
        r = await moteur.retrouver_commande(a.source, a.p, a.regles, a.appelant)
        assert r.faits["statut"] == statut and r.suggestion.startswith(debut_de_phrase), (statut, r.suggestion)


async def test_plusieurs_commandes_on_demande_laquelle(commerce):  # noqa: F811
    await _passer(commerce)
    autre = await Appel(commerce, vente_en_plus=False).pret("coca")
    autre.appelant = Appelant(TEL, "appel-2")
    await autre.jusqu_a_la_relecture()
    assert (await autre.confirmer()).statut in ("ENREGISTREE", "TRANSMISE")
    a = Appel(commerce)
    r = await moteur.retrouver_commande(a.source, a.p, a.regles, a.appelant)
    assert (r.statut, r.manque) == ("AMBIGU", "reference") and len(r.faits["candidats"]) == 2 and "Laquelle ?" in r.suggestion


async def test_jamais_la_commande_d_un_autre_lieu_ou_d_un_autre_numero_inconnue_ou_sans_reference(commerce):  # noqa: F811
    faits = await _passer(commerce)
    a = Appel(commerce, affiche="+33699999999")
    assert (await moteur.retrouver_commande(a.source, a.p, a.regles, a.appelant)).statut == "INTROUVABLE"       # un autre numéro
    assert (await moteur.retrouver_commande(a.source, a.p, a.regles, a.appelant, "C99")).statut == "INTROUVABLE"
    # un autre établissement de la même base : la commande n'y est pas
    from api.services.restauration.appel_et_memoire.appel import Lieu
    from api.services.restauration.source_commande import SourceClasseur

    ailleurs = SourceClasseur(commerce.c, Lieu(commerce.base, commerce.b, 1), nom_prise="test")
    assert (await moteur.retrouver_commande(ailleurs, a.p, a.regles, Appelant(TEL, "x"))).statut == "INTROUVABLE"
    assert (await moteur.retrouver_commande(ailleurs, a.p, a.regles, Appelant(None, "x"), faits["numero"])).statut == "INTROUVABLE"
    sans = await moteur.retrouver_commande(a.source, a.p, a.regles, Appelant(None, "x"))
    assert (sans.statut, sans.manque) == ("INCOMPLETE", "reference")
