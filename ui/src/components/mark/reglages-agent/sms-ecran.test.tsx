/**
 * [.mark] The SMS of an agent on screen (chantier l-agent-travaille, L6), rendered.
 *
 *   - the button shows only once the module « SMS » is ticked; off by default, and an agent that
 *     never touched it sends no « sms » key (a frozen payload does not change);
 *   - in the modal: a switch on asks its text, the preview is the server's (filled by a real
 *     call: length, billed parts), the counter is read for THIS agent;
 *   - what the server would refuse is said before (no text, no number, a landline, a sender name).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { erreursSms, SMS_ETEINT } from "./ModaleSms";
import { APRES_APPEL_ETEINT, type EtatApresAppel, lireApresAppel, pourEnvoyer, SectionApresAppelAgent } from "./SectionApresAppelAgent";

const m = vi.hoisted(() => ({ compteur: vi.fn(), apercu: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getCompteurSmsApiV1WorkflowWorkflowIdSmsGet: m.compteur,
    postApercuSmsApiV1WorkflowWorkflowIdSmsApercuPost: m.apercu,
}));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const Section = ({ depart, recu }: { depart: EtatApresAppel; recu: (v: EtatApresAppel) => void }) => {
    const [valeur, setValeur] = useState(depart);
    return (
        <FournisseurLangue>
            <SectionApresAppelAgent
                valeur={valeur}
                workflowId={12}
                champsFiche={["nom", "motif"]}
                onChange={(v) => {
                    setValeur(v);
                    recu(v);
                }}
            />
        </FournisseurLangue>
    );
};

describe("[.mark] the SMS of an agent", () => {
    it("is off by default and never adds a key to an agent that did not touch it", () => {
        expect(pourEnvoyer(lireApresAppel({ actif: true }))).not.toHaveProperty("sms");
        expect(SMS_ETEINT.appelant.actif || SMS_ETEINT.equipe.actif).toBe(false);
    });

    it("opens from the module, previews with a real call and reads this agent's counter", async () => {
        m.compteur.mockResolvedValue({ data: { envoyes: 7 } });
        m.apercu.mockResolvedValue({ data: { texte: "Dupont, demande notée.", longueur: 22, coupe: false, parties: 1, encodage: "gsm7", run_id: 41 } });
        const recu = vi.fn();
        render(<Section depart={{ ...APRES_APPEL_ETEINT, actif: true }} recu={recu} />);
        expect(screen.queryByText("Réglages des SMS")).toBeNull();
        fireEvent.click(screen.getByLabelText(/SMS à l'appelant et à l'équipe/));
        fireEvent.click(screen.getByText("Réglages des SMS"));
        expect(await screen.findByText("SMS envoyés par cet agent : 7")).toBeTruthy();
        expect(m.compteur).toHaveBeenCalledWith({ path: { workflow_id: 12 } });
        fireEvent.click(screen.getByRole("switch", { name: /récapitulatif à l'appelant/i }));
        fireEvent.change(document.getElementById("sms-appelant-texte")!, { target: { value: "{{nom}}, demande notée." } });
        await waitFor(() => expect(m.apercu).toHaveBeenCalledWith({ path: { workflow_id: 12 }, body: { texte: "{{nom}}, demande notée." } }), { timeout: 2000 });
        expect(await screen.findByText("Dupont, demande notée.")).toBeTruthy();
        expect(screen.getByText(/rempli avec l'appel n° 41/)).toBeTruthy();
        expect(recu.mock.calls.at(-1)?.[0]).toMatchObject({ modules: ["sms"], sms: { appelant: { actif: true, texte: "{{nom}}, demande notée." } } });
    });

    it("says before what the server refuses", () => {
        const fr = (v: Parameters<typeof erreursSms>[0]) => erreursSms(v).map((e) => e.fr);
        expect(fr({ ...SMS_ETEINT, appelant: { actif: true, texte: null } })).toEqual(["Le SMS à l'appelant demande son texte."]);
        expect(fr({ ...SMS_ETEINT, equipe: { actif: true, texte: "x", numeros: [] } })).toEqual(["Le SMS à l'équipe demande au moins un numéro."]);
        expect(fr({ ...SMS_ETEINT, equipe: { actif: true, texte: "x", numeros: ["01 44 55 66 77"] } })).toHaveLength(1);
        expect(fr({ ...SMS_ETEINT, equipe: { actif: true, texte: "x", numeros: ["07 11 22 33 44"] } })).toEqual([]);
        expect(fr({ ...SMS_ETEINT, expediteur: "NUANCES DE FEU" })).toHaveLength(1);
    });
});
