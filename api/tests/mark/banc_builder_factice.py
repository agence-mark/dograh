"""[.mark] builder-agent-vocal, lots 3-4 : l'API du banc local, avec un CERVEAU FACTICE et un stockage en mémoire.

Pour le parcours de l'écran (créer, déposer, valider la fiche, approuver le document de conception, voir les
changements, refuser, accepter) sur une instance locale : aucun appel à un fournisseur, aucune dépense, pas de MinIO.

* le stockage de fichiers est remplacé AVANT que l'application ne se charge (``MinioFileSystem`` → mémoire) ;
* le cerveau du builder est remplacé par un acteur qui joue des tours écrits d'avance, choisis d'après le dernier
  message de la personne (mots-clés ``lis``, ``concois``, ``construis``, ``base``) ; la clé saisie à l'écran est
  rangée et chiffrée comme en production, simplement jamais envoyée à quelqu'un.

Lancement (depuis la racine du dépôt, ``api/.env.banc`` chargé) ::

    PYTHONPATH=. .venv/Scripts/python.exe -m api.tests.mark.banc_builder_factice --port 8011
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import AsyncIterator
from typing import Any

from api.services import filesystem
from api.services.filesystem.base import BaseFileSystem


class SystemeDeFichiersEnMemoire(BaseFileSystem):
    """Assez de stockage pour le parcours : écrire, relire, effacer."""

    def __init__(self, **_ignores: Any):
        self.fichiers: dict[str, bytes] = {}

    async def acreate_file(self, file_path, content) -> bool:
        self.fichiers[file_path] = await content.read()
        return True

    async def aupload_file(self, local_path, destination_path) -> bool:
        with open(local_path, "rb") as fichier:
            self.fichiers[destination_path] = fichier.read()
        return True

    async def aget_signed_url(self, file_path, expiration=3600, force_inline=False, use_internal_endpoint=False):
        return None

    async def aget_file_metadata(self, file_path):
        donnees = self.fichiers.get(file_path)
        return None if donnees is None else {"size": len(donnees)}

    async def aget_presigned_put_url(self, file_path, expiration=900, content_type="application/octet-stream", max_size=0):
        return None

    async def adownload_file(self, source_path, local_path) -> bool:
        donnees = self.fichiers.get(source_path)
        if donnees is None:
            return False
        with open(local_path, "wb") as fichier:
            fichier.write(donnees)
        return True

    async def acopy_file(self, source_path, destination_path) -> bool:
        if source_path not in self.fichiers:
            return False
        self.fichiers[destination_path] = self.fichiers[source_path]
        return True

    async def adelete_file(self, file_path) -> bool:
        return self.fichiers.pop(file_path, None) is not None


# --- le cerveau factice -------------------------------------------------------------------------------------------------

CONCEPTION = {
    "objectif": "Répondre aux appels et prendre une demande de rappel.",
    "reussite": "Chaque appelant laisse son nom et son numéro.",
    "hypotheses": ["Les horaires de l'audit sont à jour."],
    "donnees": [{"nom": "numero", "si_absente": "Proposer un rappel."}],
    "outils": [{"nom": "noter", "reponses": ["ok", "erreur"], "si_indisponible": "Proposer un rappel."}],
    "exemples_appels": ["Bonjour, je voudrais être rappelé."],
}


def _ecrire_la_fiche() -> dict[str, Any]:
    return {
        "champs": {
            "horaires": {"valeur": "Du lundi au vendredi, de 9h à 18h.", "source": "audit.md, section 1", "classement": "objet"},
            "motifs_d_appel": {"valeur": "Prise de rendez-vous, demande de rappel.", "source": "audit.md, section 1", "classement": "regle"},
        },
        "trous": [{"champ": "zone", "question": "Quelle zone l'entreprise couvre-t-elle ?", "reponse_suggeree": "Le département"}],
    }


def scenario(mot: str) -> list[list[dict[str, Any]]]:
    from api.services.builder.cerveau.factice import appel, texte, tour

    if mot == "lis":
        return [
            tour(texte("Je lis les documents déposés. "), appel("fiche_tirer_des_documents", {})),
            tour(texte("J'écris la fiche. "), appel("fiche_ecrire", _ecrire_la_fiche())),
            tour(texte("La fiche est prête : il reste une question sur la zone.")),
        ]
    if mot == "concois":
        return [
            tour(appel("conception_ecrire", CONCEPTION)),
            tour(texte("Voici le document de conception. Approuve-le ou renvoie-le avec une note.")),
        ]
    if mot == "construis":
        operations = [
            {"op": "ajouter_noeud", "id": "2", "type": "agentNode", "nom": "Prise de demande", "prompt": "Prends le nom et le numéro."},
            {"op": "ajouter_noeud", "id": "3", "type": "endCall", "nom": "Fin", "prompt": "Remercie et raccroche."},
            {"op": "ajouter_liaison", "source": "1", "target": "2", "label": "Demande", "condition": "L'appelant veut être rappelé."},
            {"op": "ajouter_liaison", "source": "2", "target": "3", "label": "Fini", "condition": "Nom et numéro pris."},
            {"op": "modifier_prompt", "id": "1", "prompt": "Accueille l'appelant en une phrase."},
        ]
        return [
            tour(texte("Je construis. "), appel("brouillon_operation", {"operations": operations})),
            tour(appel("brouillon_enregistrer", {})),
            tour(texte("Le brouillon est enregistré : 5 changements, rien n'est publié.")),
        ]
    return [tour(texte("Dis-moi « lis » pour lire les documents, « concois » pour le document de conception, « construis » pour construire."))]


class CerveauDuBanc:
    """Joue le scénario du dernier message de la personne, un tour par résultat d'action reçu."""

    async def tour(self, *, systeme: str, messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        dernier = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=-1)
        demande = str(messages[dernier]["content"]).split("[Message de la personne]")[-1].lower() if dernier >= 0 else ""
        mot = next((m for m in ("lis", "concois", "construis") if m in demande), "")
        etape = sum(1 for m in messages[dernier + 1 :] if m["role"] == "outil")
        tours = scenario(mot)
        for evenement in tours[min(etape, len(tours) - 1)]:
            yield evenement


def main() -> None:
    analyse = argparse.ArgumentParser()
    analyse.add_argument("--port", type=int, default=8011)
    arguments = analyse.parse_args(sys.argv[1:])
    filesystem.MinioFileSystem = SystemeDeFichiersEnMemoire  # avant le chargement de ``api.services.storage``
    import uvicorn

    from api.routes import builder

    builder.fabriquer_le_cerveau = lambda reglages, cle: CerveauDuBanc()
    from api.app import app

    uvicorn.run(app, host="127.0.0.1", port=arguments.port, log_level="warning")


if __name__ == "__main__":
    main()
