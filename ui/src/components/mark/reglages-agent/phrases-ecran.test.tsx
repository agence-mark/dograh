/**
 * [.mark] Le thème Phrases refait (correctifs-apres-banc-v4, lot 5), rendu par la vraie page du thème.
 *
 * | Test | La garantie |
 * |---|---|
 * | reprise | la phrase pont et la phrase avant un transfert, réglées avant, se montrent comme règles du groupe |
 * | zéro perte | une règle complète traverse l'extraction et l'enregistrement sans perdre une case ; une règle d'avant prend l'identifiant de son étape |
 * | erreurs | les erreurs qui bloquent (plan 4.7), nommées |
 * | aperçu | seconde par seconde, avec les incohérences en orange |
 * | cartes | une carte par règle et par défaut ; l'interrupteur n'ouvre pas la modale ; la carte l'ouvre |
 * | cases | une case non permise par le motif disparaît, remplacée par une ligne grise ; la case « texte de l'agent » |
 * | ajouter | « Ajouter une phrase » en deux étapes, la règle part dans la charge utile |
 * | groupe | un spécialisé voit la règle du groupe en lecture et la remplace ; le principal voit la vue du groupe |
 * | appel | chaque phrase dite par le code est listée ; aucune : pas de carte |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { client } from "@/client/client.gen";
import { UnsavedChangesProvider } from "@/context/UnsavedChangesContext";
import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { ContexteGroupe } from "../groupe/contexte-groupe";
import { lirePhrasesDites,PhrasesDuCode } from "../groupe/PhrasesDuCode";
import { apercuDeLaRegle, type ContextePhrases, normaliserRegle } from "./phrases/modele";
import { chargePhrases, erreursDesPhrases, extrairePhrases, MOTIFS_DE_PHRASES, ThemePhrases } from "./ThemePhrases";

vi.mock("@/components/ui/select", () => import("./references/select-natif"));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    listToolsApiV1ToolsGet: () =>
        Promise.resolve({
            data: [
                { tool_uuid: "o1", name: "chercher_dates", category: "http_api", definition: { config: { timeout_ms: 5000, essais: 1, attente_entre_essais_s: 1 } } },
                { tool_uuid: "o2", name: "reserver", category: "http_api", definition: { config: { timeout_ms: 4000 } } },
            ],
        }),
    getEquipeApiV1OrganizationsEquipeGet: () => Promise.resolve({ data: { personnes: [{ cle: "accueil", prenom: "Accueil" }, { cle: "marc", prenom: "Marc", nom: "Dupont" }] } }),
}));

const ETAPES = [
    { id: "n1", nom: "Rendez-vous" },
    { id: "n2", nom: "Conclusion" },
];

const configuration = (reste: Record<string, unknown> = {}) => resolveWorkflowConfigurations({ ...reste } as never);

const m = vi.hoisted(() => ({ carte: null as unknown }));

beforeEach(() => {
    m.carte = null;
    vi.spyOn(client, "get").mockImplementation((() => Promise.resolve({ data: m.carte, error: m.carte ? undefined : "x" })) as never);
});
afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
});

const monter = async (reste: Record<string, unknown> = {}, options: { groupe?: { specialiseDe: number | null }; etapes?: typeof ETAPES } = {}) => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const resolue = configuration(reste);
    const theme = (
        <UnsavedChangesProvider>
        <ContexteGroupe.Provider value={{ specialiseDe: options.groupe?.specialiseDe ?? null, principalNom: "Accueil", cerveauPropre: false, membres: [] }}>
            <ThemePhrases
                resolue={resolue}
                workflowName="Agent"
                onSave={onSave}
                ouvert
                onBasculer={() => undefined}
                ouvrir={() => undefined}
                etapes={options.etapes ?? ETAPES}
                outilsUuids={["o1", "o2"]}
                workflowId={7}
            />
        </ContexteGroupe.Provider>
        </UnsavedChangesProvider>
    );
    render(theme);
    await waitFor(() => expect(document.querySelectorAll("[data-carte-phrase]").length).toBeGreaterThan(0));
    return { onSave };
};

const carte = (motif: string) => document.querySelector(`[data-carte-phrase][data-motif="${motif}"]`) as HTMLElement;
const enregistrer = async (onSave: ReturnType<typeof vi.fn>) => {
    fireEvent.click(await screen.findByRole("button", { name: "Save Phrases" }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    return onSave.mock.calls[0][0] as { phrases_regles?: unknown[]; phrases_repos_s?: unknown };
};

const CONTEXTE: ContextePhrases = {
    langue: "fr",
    t: (x) => x.fr,
    reposS: 3,
    abandonS: { outil: 5, travail: 60, garde: 4 },
    rythme: { delaiS: 10, relances: 2 },
    destinations: { accueil: "Accueil" },
};

describe("[.mark] theme Phrases : le modèle", () => {
    it("shows the former bridge phrase and hand-over sentence as group rules", () => {
        const { regles } = extrairePhrases({
            attente: { phrase_pont: "Une seconde.", delai_phrase_pont_s: 3 },
            transfert_humain: { phrase_mise_en_relation: "Je vous passe un collègue." },
        });
        expect(regles.map((r) => [r.motif, r.portee, r.variantes, r.delai_s])).toEqual([
            ["passation_tarde", "groupe", ["Une seconde."], 3],
            ["mise_en_relation", "groupe", ["Je vous passe un collègue."], null],
        ]);
        // Une règle déjà écrite l'emporte : l'ancienne valeur n'est pas ajoutée deux fois.
        const deja = extrairePhrases({
            attente: { phrase_pont: "Une seconde." },
            phrases_regles: [{ motif: "passation_tarde", portee: "groupe", variantes: ["Neuf."] }],
        });
        expect(deja.regles.map((r) => r.variantes?.[0])).toEqual(["Neuf."]);
    });

    it("loses no box of a complete rule between the configuration and the save (zéro perte)", () => {
        const complete = {
            motif: "outil_echoue",
            portee: "etape" as const,
            etape: "Rendez-vous",
            etape_id: "n1",
            outils: ["reserver"],
            variantes: ["Je n'arrive pas à réserver.", "Désolé."],
            ordre: "dans_l_ordre" as const,
            delai_s: null,
            redite_s: null,
            max_par_attente: null,
            max_par_appel: 2,
            ensuite: { phrases: ["Un conseiller vous rappelle."], noter: { champ: "rdv", valeur: "a_rappeler" }, action: "transferer" as const, destination: "accueil" },
            texte_de_l_agent: false,
            active: true,
        };
        const lue = extrairePhrases({ phrases_regles: [complete] }).regles;
        expect(chargePhrases(lue, ETAPES)).toEqual([complete]);
        // Une règle d'avant, repérée par le nom seul, ne perd rien et prend l'identifiant du nœud.
        const ancienne = { motif: "outil_tarde", portee: "etape" as const, etape: "Conclusion", variantes: ["Je vérifie."], delai_s: 3, active: true };
        const [charge] = chargePhrases(extrairePhrases({ phrases_regles: [ancienne] }).regles, ETAPES);
        expect(charge).toMatchObject({ motif: "outil_tarde", portee: "etape", etape: "Conclusion", etape_id: "n2", variantes: ["Je vérifie."], delai_s: 3, active: true });
        // L'ancien motif « un connecteur échoue » est lu comme « un outil échoue ».
        expect(chargePhrases([{ motif: "connecteur_echoue", variantes: ["Je transmets."] }])[0].motif).toBe("outil_echoue");
    });

    it("drops the boxes the cause does not allow (a delay on a failure, an exit that is not permitted)", () => {
        const [charge] = chargePhrases([
            { motif: "outil_echoue", portee: "agent", variantes: ["Non."], delai_s: 9, redite_s: 5, max_par_attente: 3, ensuite: { action: "continuer" } },
            { motif: "appelant_se_tait", portee: "agent", variantes: ["Allô ?"], outils: ["x"], texte_de_l_agent: true },
        ]);
        expect(charge).toMatchObject({ delai_s: null, redite_s: null, max_par_attente: null });
        const silence = chargePhrases([{ motif: "appelant_se_tait", portee: "agent", variantes: ["Allô ?"], outils: ["x"], texte_de_l_agent: true }])[0];
        expect(silence.outils).toEqual([]);
        expect(silence.texte_de_l_agent).toBe(false);
    });

    it("blocks the saves of the plan (4.7) and names them", () => {
        const messages = (regles: Parameters<typeof erreursDesPhrases>[0], repos = "") => erreursDesPhrases(regles, ETAPES, repos).map((e) => e.message.en);
        const ok = { motif: "outil_tarde", portee: "agent" as const, variantes: ["A."], delai_s: 3 };
        expect(messages([ok, { ...ok, variantes: ["B."] }])).toContain("Two rules of this cause at the same place.");
        // Même motif au même endroit mais pour un autre outil : permis.
        expect(messages([ok, { ...ok, outils: ["reserver"] }])).toEqual([]);
        expect(messages([{ ...ok, variantes: [] }])).toContain("An active rule needs a sentence.");
        expect(messages([{ ...ok, active: false, variantes: [] }])).toEqual([]);
        expect(messages([{ ...ok, portee: "etape" as const, etape: null, etape_id: null }])).toContain("Choose the step.");
        expect(messages([{ ...ok, delai_s: 130 }]).some((x) => x.startsWith("Delay between"))).toBe(true);
        expect(messages([{ motif: "passation_tarde", portee: "agent", variantes: ["A."], delai_s: 0.1 }]).some((x) => x.startsWith("Delay between 0.5"))).toBe(true);
        expect(messages([{ ...ok, ensuite: { noter: { champ: "rdv", valeur: "" } } }])).toContain("A note needs a record field and a value.");
        expect(messages([{ motif: "outil_echoue", portee: "agent", variantes: ["A."], ensuite: { action: "transferer" } }])).toContain("A transfer needs its destination.");
        expect(messages([{ ...ok, ensuite: { action: "raccrocher" } }])).toContain("This exit is not allowed for this cause.");
        expect(messages([ok], "12")).toContain("Between 1 and 10 s.");
        expect(messages([ok], "")).toEqual([]);
    });

    it("unrolls what the caller hears, second by second, and flags the incoherences in orange", () => {
        const travail = apercuDeLaRegle(
            normaliserRegle({ motif: "travail_dure", portee: "etape", variantes: ["A.", "B."], ordre: "dans_l_ordre", delai_s: 0, redite_s: 8, max_par_attente: 3, texte_de_l_agent: true }),
            CONTEXTE,
        );
        expect(travail.lignes.map((l) => l.quand)).toEqual(["0 s", "8 s", "16 s", "60 s"]);
        expect(travail.lignes[0].texte).toContain("(ou la phrase écrite par l'agent)");
        expect(travail.lignes[3].sortie).toBe(true);
        // Redite plus courte que la pause : elle partira toutes les 3 s.
        const courte = apercuDeLaRegle(normaliserRegle({ motif: "outil_tarde", variantes: ["A."], delai_s: 1, redite_s: 2, max_par_attente: 3 }), CONTEXTE);
        expect(courte.alertes.join(" ")).toContain("plus court que la pause minimale (3 s)");
        expect(courte.lignes.map((l) => l.quand).slice(0, 3)).toEqual(["1 s", "4 s", "7 s"]);
        // L'outil abandonne à 5 s : la dernière redite ne partira jamais.
        const jamais = apercuDeLaRegle(normaliserRegle({ motif: "outil_tarde", variantes: ["A."], delai_s: 1, redite_s: 3, max_par_attente: 3 }), CONTEXTE);
        expect(jamais.alertes.join(" ")).toContain("n'arrivera jamais");
        expect(jamais.lignes.filter((l) => l.jamais)).toHaveLength(1);
        // Le silence : les relances puis la sortie.
        const silence = apercuDeLaRegle(
            normaliserRegle({ motif: "appelant_se_tait", variantes: ["Toujours là ?", "Allô ?"], delai_s: 10, max_par_attente: 2, ensuite: { phrases: ["Au revoir."], action: "raccrocher" } }),
            CONTEXTE,
        );
        expect(silence.lignes.map((l) => l.quand)).toEqual(["10 s", "20 s", "30 s"]);
        expect(silence.lignes[2].texte).toContain("Au revoir.");
        // Un échec : la phrase puis le modèle reprend, la sortie au plafond.
        const echec = apercuDeLaRegle(
            normaliserRegle({ motif: "outil_echoue", variantes: ["Raté."], max_par_appel: 2, ensuite: { phrases: ["On vous rappelle."], noter: { champ: "rdv", valeur: "a_rappeler" }, action: "transferer", destination: "accueil" } }),
            CONTEXTE,
        );
        expect(echec.lignes).toHaveLength(2);
        expect(echec.lignes[1].texte).toContain("rdv = a_rappeler");
        expect(echec.lignes[1].texte).toContain("transfert vers Accueil");
        expect(echec.alertes.join(" ")).toContain("Entreprise fermée");
    });

    it("knows every cause of the code", () => {
        expect(MOTIFS_DE_PHRASES.map((m) => m.id)).toEqual([
            "outil_tarde",
            "travail_dure",
            "passation_tarde",
            "modele_tarde",
            "appelant_se_tait",
            "reponse_perdue",
            "outil_echoue",
            "travail_echoue",
            "transfert_echoue",
            "mise_en_relation",
        ]);
    });
});

describe("[.mark] theme Phrases : l'écran", () => {
    it("draws the notice, the filters with their counters, the pause and a card per cause", async () => {
        await monter();
        expect(document.querySelector("[data-notice-phrases]")).not.toBeNull();
        expect(screen.getByRole("tab", { name: "All (10)" })).toBeTruthy();
        expect(screen.getByRole("tab", { name: "Waits (5)" })).toBeTruthy();
        expect(screen.getByRole("tab", { name: "Problems (4)" })).toBeTruthy();
        expect(screen.getByRole("tab", { name: "Actions (1)" })).toBeTruthy();
        expect(document.getElementById("phrases_repos_s")).not.toBeNull();
        expect(document.querySelectorAll("[data-carte-phrase]")).toHaveLength(10);
        expect(carte("modele_tarde").getAttribute("data-origine")).toBe("defaut");
        // Une règle éteinte est grisée et dit ce qui se passe à la place.
        expect(carte("outil_tarde").getAttribute("data-active")).toBe("non");
        expect(carte("outil_tarde").textContent).toContain("Nothing is said: the caller waits for the tool's result.");
        fireEvent.mouseDown(screen.getByRole("tab", { name: "Problems (4)" }));
        fireEvent.click(screen.getByRole("tab", { name: "Problems (4)" }));
        await waitFor(() => expect(document.querySelectorAll("[data-carte-phrase]")).toHaveLength(4));
    });

    it("switches a card on without opening its dialog, and the card opens the dialog", async () => {
        const { onSave } = await monter();
        fireEvent.click(within(carte("outil_tarde")).getByRole("switch"));
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(carte("outil_tarde").getAttribute("data-active")).toBe("oui");
        expect(carte("outil_tarde").getAttribute("data-origine")).toBe("agent");
        fireEvent.click(carte("outil_tarde"));
        expect(await screen.findByRole("dialog")).toBeTruthy();
        expect(screen.getByText("Edit the sentence : a tool is working")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        const charge = await enregistrer(onSave);
        expect(charge.phrases_regles).toHaveLength(1);
        expect(charge.phrases_regles?.[0]).toMatchObject({ motif: "outil_tarde", portee: "agent", active: true, delai_s: 3 });
    });

    it("replaces a box the cause does not allow by a grey line, and shows the wait read elsewhere", async () => {
        await monter();
        fireEvent.click(carte("modele_tarde"));
        const dialogue = await screen.findByRole("dialog");
        const delai = dialogue.querySelector('[data-ligne-phrase="delai"]') as HTMLElement;
        expect(delai.querySelector("[data-gris]")).not.toBeNull();
        expect(dialogue.querySelector("#phrase_delai")).toBeNull();
        expect(dialogue.querySelector('[data-ligne-phrase="redite"] [data-gris]')).not.toBeNull();
        expect(dialogue.querySelector('[data-ligne-phrase="ensuite"] [data-gris]')).not.toBeNull();
        expect(dialogue.querySelector('[data-ligne-phrase="outil"] [data-gris]')).not.toBeNull();
        // Un outil échoue : le délai disparaît, pas l'outil ni le plafond.
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        fireEvent.click(carte("outil_echoue"));
        const echec = await screen.findByRole("dialog");
        expect(echec.querySelector('[data-ligne-phrase="delai"] [data-gris]')).not.toBeNull();
        expect(echec.querySelector("#phrase_par_appel")).not.toBeNull();
        expect(echec.querySelector('[data-ligne-phrase="outil"] [data-gris]')).toBeNull();
        expect(within(echec).getByLabelText("For the tool : chercher_dates")).toBeTruthy();
    });

    it("offers the text written by the agent only at After = 0 s, and drops it when the delay moves", async () => {
        const { onSave } = await monter();
        fireEvent.click(carte("travail_dure"));
        const dialogue = await screen.findByRole("dialog");
        expect(dialogue.querySelector("#phrase_texte_de_l_agent")).toBeNull();
        fireEvent.change(dialogue.querySelector("#phrase_delai") as HTMLInputElement, { target: { value: "0" } });
        const choix = dialogue.querySelector("#phrase_texte_de_l_agent") as HTMLSelectElement;
        expect(choix).not.toBeNull();
        fireEvent.change(choix, { target: { value: "agent" } });
        expect(dialogue.querySelector("[data-apercu-phrase]")?.textContent).toContain("(ou la phrase écrite par l'agent)".replace("ou la phrase écrite par l'agent", "or the sentence the agent writes"));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        let charge = await enregistrer(onSave);
        expect(charge.phrases_regles?.[0]).toMatchObject({ motif: "travail_dure", delai_s: 0, texte_de_l_agent: true });
        // Le délai qui bouge retire la case.
        cleanup();
        onSave.mockClear();
        await monter({ phrases_regles: [{ motif: "travail_dure", portee: "agent", variantes: ["A."], delai_s: 0, texte_de_l_agent: true }] });
        fireEvent.click(carte("travail_dure"));
        const d2 = await screen.findByRole("dialog");
        fireEvent.change(d2.querySelector("#phrase_delai") as HTMLInputElement, { target: { value: "4" } });
        expect(d2.querySelector("#phrase_texte_de_l_agent")).toBeNull();
        void charge;
        charge = { phrases_regles: [] };
    });

    it("adds a sentence in two steps and sends the rule", async () => {
        const { onSave } = await monter({}, {});
        fireEvent.click(screen.getByRole("button", { name: "Add a sentence" }));
        const etape1 = await screen.findByRole("dialog");
        expect(within(etape1).getByText("Step 1 of 2", { selector: "span" })).toBeTruthy();
        expect(within(etape1).getAllByRole("button").filter((b) => b.hasAttribute("data-motif-ajout"))).toHaveLength(10);
        fireEvent.click(within(etape1).getByRole("button", { name: "A tool fails" }));
        const etape2 = await screen.findByText(/Step 2 of 2/);
        expect(etape2).toBeTruthy();
        fireEvent.change(document.getElementById("phrase_variante_0") as HTMLInputElement, { target: { value: "Je ne peux pas réserver." } });
        fireEvent.change(document.getElementById("phrase_par_appel") as HTMLInputElement, { target: { value: "2" } });
        fireEvent.change(document.getElementById("phrase_sortie_action") as HTMLSelectElement, { target: { value: "transferer" } });
        // Sans destination : l'ajout est bloqué et la raison est dite.
        expect((screen.getByRole("button", { name: "Add" }) as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByRole("alert").textContent).toContain("A transfer needs its destination.");
        fireEvent.change(document.getElementById("phrase_sortie_destination") as HTMLSelectElement, { target: { value: "accueil" } });
        await waitFor(() => expect((screen.getByRole("button", { name: "Add" }) as HTMLButtonElement).disabled).toBe(false));
        // « Changer de motif » revient à l'étape 1.
        fireEvent.click(screen.getByRole("button", { name: "← Change the cause" }));
        expect(await screen.findByText("Step 1 of 2", { selector: "span" })).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "A tool fails" }));
        fireEvent.change(await waitFor(() => document.getElementById("phrase_variante_0") as HTMLInputElement), { target: { value: "Je ne peux pas réserver." } });
        fireEvent.change(document.getElementById("phrase_par_appel") as HTMLInputElement, { target: { value: "2" } });
        fireEvent.change(document.getElementById("phrase_sortie_action") as HTMLSelectElement, { target: { value: "transferer" } });
        fireEvent.change(document.getElementById("phrase_sortie_destination") as HTMLSelectElement, { target: { value: "accueil" } });
        fireEvent.click(screen.getByRole("button", { name: "Add" }));
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(carte("outil_echoue").getAttribute("data-origine")).toBe("agent");
        const charge = await enregistrer(onSave);
        expect(charge.phrases_regles).toEqual([
            {
                motif: "outil_echoue",
                portee: "agent",
                etape: null,
                etape_id: null,
                outils: [],
                variantes: ["Je ne peux pas réserver."],
                ordre: "tournees",
                delai_s: null,
                redite_s: null,
                max_par_attente: null,
                max_par_appel: 2,
                ensuite: { phrases: [], noter: null, action: "transferer", destination: "accueil" },
                texte_de_l_agent: false,
                active: true,
            },
        ]);
    });

    it("turns a card orange when its step no longer exists", async () => {
        await monter({ phrases_regles: [{ motif: "outil_tarde", portee: "etape", etape: "Ancienne", etape_id: "disparue", variantes: ["A."], delai_s: 3 }] });
        const orange = carte("outil_tarde");
        expect(orange.querySelector('[data-note="etape-supprimee"]')).not.toBeNull();
        const ok = await monter({ phrases_regles: [{ motif: "outil_tarde", portee: "etape", etape: "Renommée", etape_id: "n1", variantes: ["A."], delai_s: 3 }] }).then(() => document.querySelectorAll('[data-note="etape-supprimee"]'));
        // Renommer une étape garde ses règles : l'identifiant de nœud la retrouve, le nom affiché est celui du graphe.
        expect(ok.length).toBe(1);
        expect(document.body.textContent).toContain("Rendez-vous");
    });

    it("a specialised agent reads the group rule, and replaces it in its own agent", async () => {
        m.carte = {
            agents: [
                {
                    id: 7,
                    nom: "Entretien",
                    est_principal: false,
                    motifs: [],
                    regles: [],
                    regles_du_groupe: [{ motif: "appelant_se_tait", portee: "groupe", variantes: ["Toujours là ?"], delai_s: 10, active: true, dernier: null }],
                    lecture: [],
                },
            ],
            actions: [],
        };
        const { onSave } = await monter({ agent_principal_id: 5 }, { groupe: { specialiseDe: 5 } });
        await waitFor(() => expect(document.querySelector('[data-note="regle-heritee"]')).not.toBeNull());
        const heritee = document.querySelector('[data-origine="heritee"]') as HTMLElement;
        expect(heritee.textContent).toContain("Toujours là ?");
        // En lecture : ni interrupteur ni ouverture.
        expect(within(heritee).queryByRole("switch")).toBeNull();
        expect((within(heritee).getByText("Edit on the main agent").closest("a") as HTMLAnchorElement).getAttribute("href")).toBe("/workflow/5/settings");
        fireEvent.click(within(heritee).getByRole("button", { name: "Replace in this agent" }));
        const dialogue = await screen.findByRole("dialog");
        expect((dialogue.querySelector("#phrase_endroit") as HTMLSelectElement).value).toBe("agent");
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        const charge = await enregistrer(onSave);
        expect(charge.phrases_regles?.[0]).toMatchObject({ motif: "appelant_se_tait", portee: "agent", variantes: ["Toujours là ?"], delai_s: 10 });
        // La pause est celle du principal : en lecture ici.
        expect((document.getElementById("phrases_repos_s") as HTMLInputElement).disabled).toBe(true);
    });

    it("shows the group view on the main agent: cause × agent, with where each sentence comes from", async () => {
        const motifs = (niveau: string, variante: string | null) =>
            MOTIFS_DE_PHRASES.map((mo) => ({
                motif: mo.id, famille: mo.famille, libelle: mo.libelle, quand: mo.quand, eteinte: mo.eteinte, a_un_delai: mo.a_un_delai,
                variantes: variante ? [variante] : [], delai_s: null, active: variante !== null, niveau, etapes: [], dernier: null,
            }));
        m.carte = {
            agents: [
                { id: 7, nom: "Accueil", est_principal: true, motifs: motifs("agent", "Un instant."), regles: [], lecture: [] },
                { id: 8, nom: "Entretien", est_principal: false, motifs: motifs("principal", "Un instant."), regles: [], regles_du_groupe: [], lecture: [] },
            ],
            actions: [],
        };
        await monter({ agents_specialises: [8] });
        const vue = await waitFor(() => {
            const v = document.querySelector("[data-vue-du-groupe]");
            expect(v?.querySelector("table")).not.toBeNull();
            return v as HTMLElement;
        });
        expect(vue.querySelectorAll("[data-ligne-groupe]")).toHaveLength(10);
        expect(vue.querySelector('[data-case-groupe="appelant_se_tait-7"]')?.getAttribute("data-niveau")).toBe("agent");
        const cellule = vue.querySelector('[data-case-groupe="appelant_se_tait-8"]') as HTMLElement;
        expect(cellule.getAttribute("data-niveau")).toBe("groupe");
        expect(cellule.textContent).toContain("héritée du principal".replace("héritée du principal", "inherited from the main agent"));
        // La case d'un autre agent mène à ses réglages ; « + propre » ouvre l'ajout du motif chez lui.
        expect((cellule.querySelector("a[href$='/workflow/8/settings']") as HTMLAnchorElement)).not.toBeNull();
        expect((cellule.querySelector("a[href*='phrases_ajout=appelant_se_tait']") as HTMLAnchorElement).getAttribute("href")).toBe("/workflow/8/settings?phrases_ajout=appelant_se_tait");
        // Une case du principal ouvre la règle (ici un défaut : l'ajout du motif).
        fireEvent.click(vue.querySelector('[data-case-groupe="appelant_se_tait-7"] button') as HTMLButtonElement);
        expect(await screen.findByRole("dialog")).toBeTruthy();
    });
});

describe("[.mark] la fenêtre de l'appel liste les phrases dites par le code", () => {
    it("lists each sentence, and draws nothing without one", () => {
        const contexte = {
            phrases_du_code: [
                { motif: "travail_dure", agent: 4, etape: "Créneaux", niveau: "defaut", texte: "C'est presque bon.", moment_s: 12.5 },
                "illisible",
            ],
        };
        expect(lirePhrasesDites(contexte)).toHaveLength(1);
        render(<PhrasesDuCode contexte={contexte} />);
        const ligne = document.querySelector('[data-phrase-dite="travail_dure"]');
        expect(ligne?.textContent).toContain("C'est presque bon.");
        expect(ligne?.textContent).toContain("Créneaux");
        cleanup();
        const { container } = render(<PhrasesDuCode contexte={{}} />);
        expect(container.innerHTML).toBe("");
        expect(screen.queryByText("Sentences said by the code")).toBeNull();
    });
});
