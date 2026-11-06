/**
 * [.mark] R3 M5 : `echecAffiche` rend une phrase fixe dans la langue de l'écran et passe le motif à la notification ; la faute
 * d'un champ (422) reste lisible sous son champ, sans notification.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { lireNotifications, viderNotifications } from "./magasin";
import { ECHEC_GENERIQUE, echecAffiche } from "./echec-affiche";

beforeEach(() => viderNotifications());

describe("echecAffiche", () => {
    it("une erreur interne du serveur ne s'affiche pas : phrase fixe, motif dans la notification", () => {
        const phrase = echecAffiche({ detail: 'relation "x" does not exist (SELECT * FROM x)' });
        expect(phrase).toBe(ECHEC_GENERIQUE.en); // hors fournisseur, l'écran est en anglais
        expect(phrase).not.toMatch(/SELECT|relation/);
        const [notif] = lireNotifications();
        expect(notif.sorte).toBe("echec");
        expect(notif.detail).toMatch(/SELECT/);
        expect(notif.texte).toEqual(ECHEC_GENERIQUE);
    });

    it("une phrase propre au geste remplace la phrase générique", () => {
        const texte = { fr: "Clé non enregistrée.", en: "Key not saved." };
        expect(echecAffiche("boom", texte)).toBe("Key not saved.");
        expect(lireNotifications()[0].texte).toEqual(texte);
    });

    it("la faute d'un champ (422) reste lisible, sans notification", () => {
        const phrase = echecAffiche({ detail: [{ msg: "Field required", loc: ["body", "nom"] }] });
        expect(phrase).toBe("Field required");
        expect(lireNotifications()).toHaveLength(0);
    });
});
