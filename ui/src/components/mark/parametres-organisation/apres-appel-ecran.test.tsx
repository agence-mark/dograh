/**
 * [.mark] The after-call on screen (chantier l-agent-travaille, L4), rendered.
 *
 *   - « After the call » (Platform Settings): the settings read are shown; what is typed is
 *     exactly what « Save » sends (keys by reference to « Keys », never a password field);
 *     hours that are not hours block the theme and name the setting (E7);
 *   - the test mail, the recap now and the purge now act at once, with what they need;
 *   - the run window's section: each step with its status, a failed one in red with
 *     « Retry », which asks the server for THAT step; nothing at all when the agent does not
 *     use the after-call (X2);
 *   - the agent's switch: off by default, its steps and modules shown only when on (E8).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SectionApresAppel } from "../fenetre-du-run/SectionApresAppel";
import { FournisseurLangue } from "../langue/langue";
import { APRES_APPEL_ETEINT, pourEnvoyer, SectionApresAppelAgent } from "../reglages-agent/SectionApresAppelAgent";
import { lireHeures, ThemeApresAppel, useApresAppel } from "./ThemeApresAppel";

const m = vi.hoisted(() => ({
    get: vi.fn(),
    put: vi.fn(),
    essai: vi.fn(),
    nuit: vi.fn(),
    recap: vi.fn(),
    run: vi.fn(),
    relancer: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
    getApresAppelApiV1OrganizationsApresAppelGet: m.get,
    putApresAppelApiV1OrganizationsApresAppelPut: m.put,
    postEssaiMailApiV1OrganizationsApresAppelEssaiMailPost: m.essai,
    postNuitApiV1OrganizationsApresAppelNuitPost: m.nuit,
    postRecapitulatifApiV1OrganizationsApresAppelRecapitulatifPost: m.recap,
    getApresAppelDuRunApiV1WorkflowWorkflowIdRunsRunIdApresAppelGet: m.run,
    postRelancerEtapeApiV1WorkflowWorkflowIdRunsRunIdApresAppelEtapeRelancerPost: m.relancer,
    listerLesClesApiV1ClesGet: () =>
        Promise.resolve({ data: [{ uuid: "u-mistral", nom: "Mistral du client", fournisseur: "mistral" }, { uuid: "u-smtp", nom: "Boîte mail", fournisseur: "smtp" }] }),
    fournisseursDesClesApiV1ClesFournisseursGet: () => Promise.resolve({ data: ["mistral", "smtp", "webhook"] }),
    identifiantDesigneApiV1ClesDesigneeUuidGet: () => Promise.resolve({ data: { etat: "bibliotheque", nom: "x" } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

const ECRAN = {
    reglages: {
        format: "apres-appel-mark",
        version: 1,
        synthese: { modele: "mistral-small-latest", cle: "mark-cle:u-mistral", nom_assistant: null, nom_entreprise: null, consigne: null },
        smtp: { hote: "smtp.example.org", port: 587, securite: "starttls", utilisateur: "agent", mot_de_passe: "mark-cle:u-smtp", expediteur: "agent@example.org", nom_expediteur: null },
        recapitulatif: { actif: false, heures: [8] },
        webhook: { url: null, secret: null },
    },
    adresses: { organisation: [], installation: ["mark@example.org"] },
    smtp_installation: false,
    base_rattachee: true,
    derniere_nuit: { debut: "2026-10-07T03:17:00Z", statut: "faite", resultat: { purge: { verbatim: 2, appel: 1 } } },
};

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const rendre = (noeud: React.ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);

const Apres = ({ signaler = vi.fn() }: { signaler?: (id: string, modifie: boolean, enErreur: boolean) => void }) => {
    const apresAppel = useApresAppel();
    return <ThemeApresAppel ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={signaler} apresAppel={apresAppel} />;
};

describe("After the call (organization)", () => {
    it("shows what is saved, and saves exactly what is typed", async () => {
        m.get.mockResolvedValue({ data: structuredClone(ECRAN) });
        m.put.mockImplementation(async ({ body }) => ({ data: { ...ECRAN, reglages: body } }));
        rendre(<Apres />);
        const hote = (await screen.findByLabelText(/^(Server|Serveur)$/)) as HTMLInputElement;
        expect(hote.value).toBe("smtp.example.org");
        expect(document.querySelector('input[type="password"]')).toBeNull();
        expect(screen.getByTestId("derniere-nuit").textContent).toContain("verbatim 2");
        fireEvent.change(screen.getByLabelText(/Assistant's name|Nom de l'assistant/), { target: { value: "Léa" } });
        fireEvent.click(screen.getByRole("switch", { name: /Send the recap|Envoyer le récapitulatif/ }));
        fireEvent.change(await screen.findByLabelText(/^(Hours|Heures)$/), { target: { value: "8, 17" } });
        fireEvent.change(screen.getByLabelText(/Custom webhook: address|Webhook sur mesure : adresse/), {
            target: { value: "https://n8n.example.org/webhook/fin" },
        });
        fireEvent.click(screen.getByRole("button", { name: /^(Save|Enregistrer)/ }));
        await waitFor(() => expect(m.put).toHaveBeenCalledTimes(1));
        const corps = m.put.mock.calls[0][0].body;
        expect(corps.synthese).toEqual({ ...ECRAN.reglages.synthese, nom_assistant: "Léa" });
        expect(corps.smtp).toEqual(ECRAN.reglages.smtp);
        expect(corps.recapitulatif).toEqual({ actif: true, heures: [8, 17] });
        expect(corps.webhook).toEqual({ url: "https://n8n.example.org/webhook/fin", secret: null });
    });

    it("blocks the theme on hours that are not hours, and names the setting (E7)", async () => {
        m.get.mockResolvedValue({ data: { ...structuredClone(ECRAN), reglages: { ...ECRAN.reglages, recapitulatif: { actif: true, heures: [8] } } } });
        const signaler = vi.fn();
        rendre(<Apres signaler={signaler} />);
        fireEvent.change(await screen.findByLabelText(/^(Hours|Heures)$/), { target: { value: "8, 25" } });
        await waitFor(() => expect(signaler).toHaveBeenLastCalledWith("apres-appel", true, true));
        expect(screen.getAllByText(/Recap hours|Heures du récapitulatif/).length).toBeGreaterThan(0);
        expect(lireHeures("8h, 17")).toEqual([8, 17]);
        expect(lireHeures("24")).toBeNull();
    });

    it("sends a test mail to the address typed, runs the purge now", async () => {
        m.get.mockResolvedValue({ data: structuredClone(ECRAN) });
        m.essai.mockResolvedValue({ data: { statut: "envoye" } });
        m.nuit.mockResolvedValue({ data: { statut: "faite" } });
        rendre(<Apres />);
        fireEvent.change(await screen.findByLabelText(/Test recipient|Destinataire de l'essai/), { target: { value: "moi@example.org" } });
        fireEvent.click(screen.getByTestId("essai-mail"));
        await waitFor(() => expect(m.essai).toHaveBeenCalledWith({ body: { destinataire: "moi@example.org" } }));
        fireEvent.click(screen.getByTestId("purge-maintenant"));
        await waitFor(() => expect(m.nuit).toHaveBeenCalledTimes(1));
    });
});

describe("After the call (run window)", () => {
    it("shows each step, a failure in red with Retry, which asks for THAT step", async () => {
        const vue = {
            actif: true,
            etapes: [
                { nom: "ecriture", statut: "ok", tentatives: 1, definitive: true, detail: "call 3, request 2", envois: [] },
                { nom: "synthese", statut: "ok", tentatives: 1, definitive: true, detail: "mistral-small-latest", envois: [] },
                { nom: "mail", statut: "echec", tentatives: 3, definitive: true, detail: "The mail server refused the user or the password.", envois: [] },
            ],
            appel_id: 3,
            demande_id: 2,
            synthese: "La personne a demandé un rappel.",
        };
        m.run.mockResolvedValue({ data: vue });
        m.relancer.mockResolvedValue({ data: { ...vue, etapes: [vue.etapes[0], vue.etapes[1], { ...vue.etapes[2], statut: "en_attente" }] } });
        rendre(<SectionApresAppel workflowId={7} runId={42} />);
        const etapes = await screen.findAllByTestId("etape-apres-appel");
        expect(etapes.map((e) => e.getAttribute("data-statut"))).toEqual(["ok", "ok", "echec"]);
        expect(etapes[2].className).toContain("destructive");
        expect(screen.getByTestId("synthese-du-run").textContent).toContain("rappel");
        fireEvent.click(screen.getByTestId("relancer-mail"));
        await waitFor(() =>
            expect(m.relancer).toHaveBeenCalledWith({ path: { workflow_id: 7, run_id: 42, etape: "mail" } }),
        );
    });

    it("says a test call was kept out of the after-call (decision of 07/10)", async () => {
        m.run.mockResolvedValue({ data: { actif: false, essai: true, etapes: [] } });
        rendre(<SectionApresAppel workflowId={7} runId={42} />);
        expect((await screen.findByTestId("bloc-apres-appel-essai")).textContent).toMatch(/après-appel non exécuté|after-call not run/);
    });

    it("shows nothing when the agent does not use the after-call (X2)", async () => {
        m.run.mockResolvedValue({ data: { actif: false, etapes: [] } });
        const { container } = rendre(<SectionApresAppel workflowId={7} runId={42} />);
        await waitFor(() => expect(m.run).toHaveBeenCalled());
        expect(container.querySelector('[data-testid="bloc-apres-appel"]')).toBeNull();
    });
});

describe("After the call (agent)", () => {
    const Agent = ({ onValeur }: { onValeur: (v: unknown) => void }) => {
        const [valeur, setValeur] = useState(APRES_APPEL_ETEINT);
        return (
            <SectionApresAppelAgent
                valeur={valeur}
                onChange={(v) => {
                    setValeur(v);
                    onValeur(pourEnvoyer(v));
                }}
            />
        );
    };

    it("is off by default; on, shows its steps, its modules and its fields (E8)", async () => {
        const onValeur = vi.fn();
        rendre(<Agent onValeur={onValeur} />);
        expect(screen.queryByLabelText(/Summarise the call|Résumer l'appel/)).toBeNull();
        fireEvent.click(screen.getByRole("switch", { name: /Work after the call|Travailler après l'appel/ }));
        expect(await screen.findByLabelText(/Summarise the call|Résumer l'appel/)).toBeTruthy();
        fireEvent.click(screen.getByLabelText(/Custom webhook|Webhook sur mesure/));
        fireEvent.change(document.getElementById("apres_appel_champ_nom")!, { target: { value: "nom_client" } });
        expect(onValeur).toHaveBeenLastCalledWith({ actif: true, essais: false, synthese: true, mail: true, modules: ["webhook"], champs: { nom: "nom_client" } });
    });
});
