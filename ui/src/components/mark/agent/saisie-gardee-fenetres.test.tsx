/**
 * [.mark] K7 : la saisie gardée dans TOUTES les fenêtres d'un agent. Une fenêtre ouverte (Dialog, AlertDialog, Sheet, et les cadres de
 * fenêtres de l'écran qui les emploient : phrases, champs, large, libre, onglets) est une saisie présumée : quand l'agent est modifié
 * ailleurs, l'onglet ne se relit pas par-dessus elle, il prévient (bandeau « modifié ailleurs ») ; fermée, la fenêtre ne bloque rien.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

import { CadreModale } from "../reglages-agent/phrases/cadre";
import { FenetreChamps } from "../studio/fenetre-champs";
import { FenetreLarge } from "../studio/fenetre-large";
import { FenetreLibre } from "../studio/fenetre-libre";
import { FenetreOnglets } from "../studio/fenetre-onglets";
import { EntetePageAgent } from "./EntetePageAgent";

const m = vi.hoisted(() => ({ declencher: null as null | (() => void) }));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/client/sdk.gen", () => ({
    lireLesTestsApiV1BuilderTestsWorkflowIdGet: vi.fn(async () => ({ data: { tests: [] } })),
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: async () => ({ data: { name: "Agent", workflow_uuid: "u", version_number: 1, version_status: "draft" } }),
}));
vi.mock("./ActionsAgent", () => ({ ActionsAgent: () => null }));
vi.mock("./EnteteAgent", () => ({ EnteteAgent: () => null }));
vi.mock("@/components/mark/sources/useModifications", () => ({
    LigneLive: ({ quand }: { quand?: () => void }) => {
        m.declencher = () => quand?.();
        return null;
    },
}));

afterEach(cleanup);

const dansUnAgent = (enfant: ReactNode) =>
    render(
        <EntetePageAgent agentId={1} onglet="reglages">
            {enfant}
        </EntetePageAgent>,
    );

const PREVENU = /modified elsewhere|modifié ailleurs/; // le reste de la page est masqué aux lecteurs d'écran tant qu'une fenêtre est ouverte : on cherche le texte
const ecrireAilleurs = () => act(() => m.declencher?.());

const FENETRES: [string, ReactNode][] = [
    [
        "Dialog",
        <Dialog key="d" open>
            <DialogContent>
                <DialogTitle>t</DialogTitle>
                <DialogDescription>d</DialogDescription>
            </DialogContent>
        </Dialog>,
    ],
    [
        "AlertDialog",
        <AlertDialog key="a" open>
            <AlertDialogContent>
                <AlertDialogTitle>t</AlertDialogTitle>
                <AlertDialogDescription>d</AlertDialogDescription>
            </AlertDialogContent>
        </AlertDialog>,
    ],
    [
        "Sheet",
        <Sheet key="s" open>
            <SheetContent>
                <SheetTitle>t</SheetTitle>
                <SheetDescription>d</SheetDescription>
            </SheetContent>
        </Sheet>,
    ],
    ["fenêtre des phrases (CadreModale)", <CadreModale key="c" titre="t" description="d" onFermer={() => {}} pied={null}>x</CadreModale>],
    ["FenetreChamps", <FenetreChamps key="fc" ouverte fermer={() => {}} titre="t" sections={[{ champs: [{ id: "n", t: "texte", l: "Nom", v: "" }] }]} valider="Enregistrer" />],
    ["FenetreLarge", <FenetreLarge key="fl" fermer={() => {}} titre="t" pied={null}>x</FenetreLarge>],
    ["FenetreLibre", <FenetreLibre key="fli" ouverte fermer={() => {}} titre="t" corps={<p>x</p>} actions={null} />],
    ["FenetreOnglets", <FenetreOnglets key="fo" fermer={() => {}} titre="t" valider={null}>x</FenetreOnglets>],
];

describe("une fenêtre ouverte dans l'onglet d'un agent garde sa saisie", () => {
    it.each(FENETRES)("%s : l'écriture ailleurs prévient au lieu de relire", async (_nom, fenetre) => {
        dansUnAgent(fenetre);
        ecrireAilleurs();
        expect(await screen.findByText(PREVENU)).toBeTruthy();
    });

    it("fermée, une fenêtre ne bloque rien : l'onglet se relit seul", () => {
        dansUnAgent(
            <Dialog open={false}>
                <DialogContent>
                    <DialogTitle>t</DialogTitle>
                    <DialogDescription>d</DialogDescription>
                </DialogContent>
            </Dialog>,
        );
        ecrireAilleurs();
        expect(screen.queryByText(PREVENU)).toBeNull();
    });

    it("à la fermeture de la fenêtre, le bandeau part et l'onglet se relit", async () => {
        const { rerender } = dansUnAgent(
            <Dialog open>
                <DialogContent>
                    <DialogTitle>t</DialogTitle>
                    <DialogDescription>d</DialogDescription>
                </DialogContent>
            </Dialog>,
        );
        ecrireAilleurs();
        expect(await screen.findByText(PREVENU)).toBeTruthy();
        rerender(
            <EntetePageAgent agentId={1} onglet="reglages">
                <Dialog open={false}>
                    <DialogContent>
                        <DialogTitle>t</DialogTitle>
                        <DialogDescription>d</DialogDescription>
                    </DialogContent>
                </Dialog>
            </EntetePageAgent>,
        );
        expect(screen.queryByText(PREVENU)).toBeNull();
    });

    it("le bouton Recharger relit même avec la fenêtre ouverte", async () => {
        dansUnAgent(
            <Dialog open>
                <DialogContent>
                    <DialogTitle>t</DialogTitle>
                    <DialogDescription>d</DialogDescription>
                </DialogContent>
            </Dialog>,
        );
        ecrireAilleurs();
        fireEvent.click(await screen.findByText(/Recharger|Reload/));
        expect(screen.queryByText(PREVENU)).toBeNull();
    });
});
