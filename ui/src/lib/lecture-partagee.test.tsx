/**
 * [.mark] C4 : une lecture pour tous les composants montés ; la valeur est oubliée au démontage ; une écriture met tout le monde
 * à jour sans relire ; une erreur ne boucle pas.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { creerLecturePartagee } from "./lecture-partagee";

afterEach(() => cleanup());

const montrer = (lecture: ReturnType<typeof creerLecturePartagee<string>>, nom: string, actif = true) =>
    function Lecteur() {
        const { valeur, erreur } = lecture.useLecture(actif);
        return <span data-testid={nom}>{erreur ? "erreur" : (valeur ?? "…")}</span>;
    };

describe("[.mark] C4 : lecture partagée", () => {
    it("trois composants montés à des instants différents = une seule lecture", async () => {
        const lire = vi.fn().mockResolvedValue({ data: "v1" });
        const lecture = creerLecturePartagee<string>(lire);
        const A = montrer(lecture, "a");
        const B = montrer(lecture, "b");
        const C = montrer(lecture, "c");
        const { rerender } = render(<A />);
        await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("v1"));
        rerender(<><A /><B /></>);
        rerender(<><A /><B /><C /></>);
        expect(screen.getByTestId("c").textContent).toBe("v1");
        expect(lire).toHaveBeenCalledTimes(1);
    });

    it("une écriture (poser) met tout le monde à jour sans relire", async () => {
        const lire = vi.fn().mockResolvedValue({ data: "v1" });
        const lecture = creerLecturePartagee<string>(lire);
        const A = montrer(lecture, "a");
        const B = montrer(lecture, "b");
        render(<><A /><B /></>);
        await waitFor(() => expect(screen.getByTestId("b").textContent).toBe("v1"));
        act(() => lecture.poser("v2"));
        expect(screen.getByTestId("a").textContent).toBe("v2");
        expect(screen.getByTestId("b").textContent).toBe("v2");
        expect(lire).toHaveBeenCalledTimes(1);
    });

    it("démonté, il ne garde rien : la page suivante relit", async () => {
        const lire = vi.fn().mockResolvedValueOnce({ data: "v1" }).mockResolvedValueOnce({ data: "v2" });
        const lecture = creerLecturePartagee<string>(lire);
        const A = montrer(lecture, "a");
        const premier = render(<A />);
        await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("v1"));
        premier.unmount();
        render(<A />);
        await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("v2"));
        expect(lire).toHaveBeenCalledTimes(2);
    });

    it("pas de lecture tant que le composant n'est pas actif (authentification)", async () => {
        const lire = vi.fn().mockResolvedValue({ data: "v1" });
        const lecture = creerLecturePartagee<string>(lire);
        const Inactif = montrer(lecture, "a", false);
        render(<Inactif />);
        await new Promise((r) => setTimeout(r, 50));
        expect(lire).not.toHaveBeenCalled();
    });

    it("une erreur se dit et ne relance pas la lecture toute seule ; relire réessaie", async () => {
        const lire = vi.fn().mockResolvedValueOnce({ error: { detail: "x" } }).mockResolvedValueOnce({ data: "v1" });
        const lecture = creerLecturePartagee<string>(lire);
        const A = montrer(lecture, "a");
        render(<A />);
        await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("erreur"));
        await new Promise((r) => setTimeout(r, 50));
        expect(lire).toHaveBeenCalledTimes(1);
        await act(async () => { await lecture.relire(); });
        expect(screen.getByTestId("a").textContent).toBe("v1");
    });
});
