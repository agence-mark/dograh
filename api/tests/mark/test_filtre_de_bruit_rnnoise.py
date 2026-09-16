"""[.mark] Non-regression test for the incoming-noise filter.

The questions this file answers:

    Does an agent that asks for RNNoise actually get it on its transport --
    the browser one AND the eight telephony ones -- does an agent that asks
    for nothing get exactly today's transport, and does the optional extra
    stay OUT of the import path until someone turns it on?

⛔ Read that scope literally. Nothing here says RNNoise improves anything. A
noise filter can get in the transcription's way as easily as it helps, and
that is judged on a real phone line.

Why the lazy import is tested, and not just written
---------------------------------------------------
🚨 An extra missing from the image stops the API from STARTING -- not the
call, the whole service -- because the import runs at module load. Paid for on
the Mistral patch (question n° 77). ``rnnoise`` is in the Dockerfile now, but
the day someone trims the extras, or builds the image from a cache that
predates the change, an eager import takes the service down for every client
including those who never asked for a filter. Lazily imported, it breaks one
agent's call and nothing else.
"""

import ast
import inspect
from pathlib import Path

import pytest

from api.schemas.workflow_configurations import (
    DEFAULT_AUDIO_IN_NOISE_FILTER,
    WorkflowConfigurationDefaults,
)
from api.services.pipecat import transport_params
from api.services.pipecat.transport_params import filtre_de_bruit_overrides

RACINE = Path(__file__).resolve().parents[2]

# The browser transport plus the eight telephony ones: the full list of places
# audio comes in. ⛔ Listed here so that a provider added without the filter is
# a red test, not a silent gap.
TRANSPORTS = [
    RACINE / "services" / "pipecat" / "transport_setup.py",
    *sorted((RACINE / "services" / "telephony" / "providers").glob("*/transport.py")),
]


# --------------------------------------------------------------------------- #
# 1. Today's behaviour, unchanged
# --------------------------------------------------------------------------- #


def test_sans_reglage_aucun_filtre_nest_pose():
    assert filtre_de_bruit_overrides(None) == {}
    assert filtre_de_bruit_overrides({}) == {}


def test_le_defaut_declare_est_aucun_filtre():
    assert WorkflowConfigurationDefaults().audio_in_noise_filter == "none"
    assert DEFAULT_AUDIO_IN_NOISE_FILTER == "none"


def test_un_null_enregistre_vaut_aucun_filtre():
    assert filtre_de_bruit_overrides({"audio_in_noise_filter": None}) == {}


def test_un_choix_inconnu_ne_pose_aucun_filtre():
    """⛔ Unknown means no filter, never a crash mid-call.

    The schema refuses anything but the two known values at save time; this is
    the second net, for a value written straight into the database or left
    over from an older name.
    """
    assert filtre_de_bruit_overrides({"audio_in_noise_filter": "krisp"}) == {}


def test_le_schema_refuse_un_filtre_inconnu():
    with pytest.raises(ValueError):
        WorkflowConfigurationDefaults(audio_in_noise_filter="krisp")


# --------------------------------------------------------------------------- #
# 2. Turned on, the filter is built
# --------------------------------------------------------------------------- #


def test_rnnoise_allume_donne_un_filtre_au_transport():
    from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

    overrides = filtre_de_bruit_overrides({"audio_in_noise_filter": "rnnoise"})
    assert isinstance(overrides["audio_in_filter"], RNNoiseFilter)


# --------------------------------------------------------------------------- #
# 3. Every transport goes through the collection point
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fichier", TRANSPORTS, ids=lambda p: p.parent.name)
def test_chaque_transport_passe_par_le_point_de_collecte(fichier):
    source = fichier.read_text(encoding="utf-8")
    assert "filtre_de_bruit_overrides(run_configs)" in source, (
        f"{fichier.parent.name} does not pass through the noise-filter "
        f"collection point. Audio would come in unfiltered on that transport "
        f"alone, and nothing would say so."
    )


def test_il_y_a_bien_neuf_transports():
    """The browser one and the eight telephony ones.

    ⛔ Goes red when a provider is added: that is the moment to decide whether
    it carries the filter, rather than discovering months later that it never
    did.

    🔑 [.mark] Il a fait exactement son travail le 2026-09-16 : la montee vers
    l'amont `23d22b95` a apporte un NEUVIEME transport (exotel), et ce test est
    ce qui l'a signale. La decision prise a ce moment-la, et c'est la seule
    coherente : il porte le filtre comme les huit autres. Passe de 8 a 9.
    """
    assert len(TRANSPORTS) == 9


# --------------------------------------------------------------------------- #
# 4. The optional extra stays out of the import path
# --------------------------------------------------------------------------- #


def test_limport_de_pyrnnoise_est_paresseux():
    """🚨 An extra missing from the image stops the API from starting.

    ⛔ Asserted on the module's syntax tree, not by trying an import: the
    package IS installed here, so an eager import would pass unnoticed and
    only fail on an image built without the extra.
    """
    arbre = ast.parse(inspect.getsource(transport_params))
    imports_au_sommet = [
        noeud
        for noeud in arbre.body
        if isinstance(noeud, (ast.Import, ast.ImportFrom))
    ]
    noms = [
        alias.name
        for noeud in imports_au_sommet
        for alias in getattr(noeud, "names", [])
    ] + [getattr(noeud, "module", "") or "" for noeud in imports_au_sommet]
    assert not any("rnnoise" in nom for nom in noms), (
        "pyrnnoise is imported at module level. An extra missing from the "
        "image would then stop the whole API from starting, for every client, "
        "including those who never turned the filter on."
    )


def test_lextra_rnnoise_est_dans_limage():
    """The other half: lazy import plus an extra that is genuinely installed.

    ⛔ Without the extra in the image, the lazy import turns a service-wide
    outage into a broken call -- better, but still broken. Both halves have to
    hold.
    """
    dockerfile = (RACINE / "Dockerfile").read_text(encoding="utf-8")
    assert "rnnoise]" in dockerfile or ",rnnoise," in dockerfile, (
        "The rnnoise extra left the Dockerfile. Any agent that turns the "
        "filter on would fail at the first call, with an ImportError nothing "
        "on screen predicts."
    )
