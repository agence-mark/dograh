/**
 * [.mark] M40 : l'envoi de la fiche du portail, sans que personne ne la voie ni ne la recopie.
 *
 * L'écran de l'étape 7 (ou « Relancer l'envoi au portail ») poste la fiche au portail par un FORMULAIRE de premier niveau, dans un nouvel
 * onglet : jamais dans l'adresse, jamais un `fetch` entre origines (le portail n'a pas à autoriser le fork). Le corps du formulaire porte la
 * fiche (clé et accès à la base), le lien d'entrée d'une minute et ce que le fork sait du client (nom, établissements, canaux, métier).
 *
 * L'onglet est ouvert AVANT l'appel au serveur, au clic : après une attente, le navigateur ne tient plus le geste pour celui de la personne et
 * bloquerait la fenêtre. Il est coupé de la page d'origine (`opener` à rien) avant d'aller au portail.
 */
import { ADRESSE_PORTAIL } from "@/components/mark/relation/commun";

export interface CorpsPortail {
    fiche: string;
    lien: string;
    nom: string;
    montage: string;
    canaux: string;
    metier: string;
}

/** Ouvre l'onglet du portail, vide, à appeler dans le gestionnaire du clic. `null` : le navigateur l'a refusé. */
export function ouvrirOngletDuPortail(organisation: number): Window | null {
    if (!ADRESSE_PORTAIL) return null;
    const onglet = window.open("", `portail-client-${organisation}`);
    if (onglet) onglet.opener = null;
    return onglet;
}

/** Poste le formulaire dans l'onglet (ou dans un nouveau si le navigateur avait refusé le premier). Le formulaire est retiré aussitôt. */
export function posterAuPortail(onglet: Window | null, corps: CorpsPortail): void {
    const formulaire = document.createElement("form");
    formulaire.method = "POST";
    formulaire.action = `${ADRESSE_PORTAIL}/relier/auto`;
    formulaire.target = onglet?.name || "_blank";
    formulaire.style.display = "none";
    for (const [nom, valeur] of Object.entries(corps)) {
        const champ = document.createElement("input");
        champ.type = "hidden";
        champ.name = nom;
        champ.value = valeur;
        formulaire.appendChild(champ);
    }
    document.body.appendChild(formulaire);
    try {
        formulaire.submit();
    } finally {
        formulaire.remove();
    }
}
