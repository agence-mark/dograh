"""[.mark] Clôture D2 (É11, É68) : la liste des configurations de téléphonie dit QUELLE étape bloque, par son identifiant.

L'écran traduit l'étape (deux langues) d'après cette clé ; le texte anglais du fournisseur n'est plus que le repli d'une clé inconnue.
"""

from api.services.telephony.registry import ProviderSetupChecklist, SetupStep


def _etape(cle: str, fait: bool, bloque: bool = True) -> SetupStep:
    return SetupStep(key=cle, title=f"t-{cle}", description=f"d-{cle}", complete=fait, blocks_outbound=bloque)


def test_la_premiere_etape_bloquante_donne_sa_cle():
    liste = ProviderSetupChecklist.from_steps([_etape("sip_domain", True), _etape("outbound_trunk", False), _etape("caller_id", False)])
    assert liste.ready_for_outbound is False
    assert liste.outbound_blocked_step == "outbound_trunk"
    assert liste.outbound_blocked_reason == "d-outbound_trunk"


def test_rien_ne_bloque_pas_de_cle():
    liste = ProviderSetupChecklist.from_steps([_etape("sip_domain", True), _etape("inbound_routing", False, bloque=False)])
    assert liste.ready_for_outbound is True
    assert liste.outbound_blocked_step is None


def test_la_cle_part_dans_la_liste_des_configurations():
    from api.schemas.telephony_config import TelephonyConfigurationListItem

    assert "outbound_blocked_step" in TelephonyConfigurationListItem.model_fields
