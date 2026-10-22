/**
 * [.mark] Les balises d'expression permises (chantier voix-soniox, lot 7, D11 et D21) : la CARTE du thème « Voix » et sa
 * MODALE centrée.
 *
 * Ce que ce fichier prouve, parce qu'un réglage déclaré n'est pas un réglage à l'écran :
 * - la carte dit dans quel état est le réglage (défaut de la voix, liste de l'agent, aucune) et montre les balises ;
 * - la modale est centrée, travaille sur une copie (Annuler ne change rien) et écrit ce que le serveur lit :
 *   `null`/absent = défaut de la voix, `[]` = tous les crochets retirés, sinon la liste sans crochets ;
 * - « défaut » écrit `undefined` quand la clé n'était pas enregistrée (aucun changement envoyé pour un agent qui n'a
 *   rien réglé), `null` sinon ;
 * - la liste par défaut de l'écran est celle du code (`BALISES_PAR_DEFAUT`), jamais une copie qui dérive ;
 * - le thème « Voix » rendu en entier porte la carte et l'enregistre (charge utile : cas `balises-permises`,
 *   `references/charges-utiles-agent.test.tsx`).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { BALISES_MAX, BALISES_PAR_DEFAUT, CarteBalises, modeDesBalises, type ValeurBalises } from "./BalisesPermises";

vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

/** La carte avec un état, comme le thème la tient : la valeur courante est relue à chaque rendu. */
const Banc = ({
    depart,
    // ⛔ Pas de valeur par défaut ici : `undefined` est une valeur qui compte (clé jamais enregistrée), et un
    // paramètre par défaut la changerait en `null` sans prévenir.
    retourAuDefaut,
    sansEffet,
    onChange,
}: {
    depart: ValeurBalises;
    retourAuDefaut?: null | undefined;
    sansEffet?: boolean;
    onChange?: (v: ValeurBalises) => void;
}) => {
    const [valeur, setValeur] = useState<ValeurBalises>(depart);
    return (
        <CarteBalises
            valeur={valeur}
            retourAuDefaut={retourAuDefaut}
            sansEffet={sansEffet}
            onChange={(v) => {
                setValeur(v);
                onChange?.(v);
            }}
        />
    );
};

const carte = () => document.querySelector("[data-carte-balises]") as HTMLElement;
const balises = () => Array.from(carte().querySelectorAll("[data-balise]")).map((b) => b.getAttribute("data-balise"));
const ouvrir = () => fireEvent.click(carte());
const appliquer = () => fireEvent.click(screen.getByRole("button", { name: /^apply$/i }));
const ajouter = (texte: string) => {
    const champ = document.getElementById("tts_balises_permises") as HTMLInputElement;
    fireEvent.change(champ, { target: { value: texte } });
    fireEvent.keyDown(champ, { key: "Enter" });
};

describe("[.mark] la liste par défaut de l'écran est celle du code", () => {
    it("lit BALISES_PAR_DEFAUT dans balises_expression.py", () => {
        const source = readFileSync(join(process.cwd(), "..", "api/services/pipecat/balises_expression.py"), "utf8");
        const m = /^BALISES_PAR_DEFAUT[^=]*=\s*\(([^)]*)\)/m.exec(source);
        expect(m, "BALISES_PAR_DEFAUT introuvable : le fichier a bougé, ce test est à mettre à jour").not.toBeNull();
        const code = [...(m as RegExpExecArray)[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
        expect([...BALISES_PAR_DEFAUT]).toEqual(code);
    });

    it("la limite de l'écran est celle du serveur (max_length)", () => {
        const source = readFileSync(join(process.cwd(), "..", "api/schemas/workflow_configurations.py"), "utf8");
        const debut = source.indexOf("tts_balises_permises: list[str] | None");
        expect(debut).toBeGreaterThan(0);
        const m = /max_length=(\d+)/.exec(source.slice(debut, debut + 200));
        expect(Number(m?.[1])).toBe(BALISES_MAX);
    });
});

describe("[.mark] l'état du réglage", () => {
    it.each([
        [undefined, "defaut"],
        [null, "defaut"],
        [[], "aucune"],
        [["warm"], "liste"],
    ] as const)("%j est lu comme « %s »", (valeur, mode) => {
        expect(modeDesBalises(valeur as ValeurBalises)).toBe(mode);
    });
});

describe("[.mark] la carte", () => {
    it("par défaut, montre les quatre balises de la voix Soniox et le nom technique en gris", () => {
        render(<Banc depart={undefined} />);
        expect(carte().getAttribute("data-carte-balises")).toBe("defaut");
        expect(balises()).toEqual([...BALISES_PAR_DEFAUT]);
        expect(carte().textContent).toMatch(/tts_balises_permises/);
        expect(carte().textContent).toMatch(/any other voice: the text is sent as written/i);
        expect(carte().getAttribute("role")).toBe("button");
    });

    it("montre la liste de l'agent", () => {
        render(<Banc depart={["warm", "chuckle"]} />);
        expect(carte().getAttribute("data-carte-balises")).toBe("liste");
        expect(balises()).toEqual(["warm", "chuckle"]);
    });

    it("dit que tous les crochets sont retirés quand la liste est vide", () => {
        render(<Banc depart={[]} />);
        expect(carte().getAttribute("data-carte-balises")).toBe("aucune");
        expect(balises()).toEqual([]);
        expect(carte().textContent).toMatch(/every bracket is removed/i);
    });

    it("dit « sans effet » quand le texte part mot à mot", () => {
        render(<Banc depart={undefined} sansEffet />);
        expect(carte().querySelector('[data-note="balises-sans-effet"]')).not.toBeNull();
        cleanup();
        render(<Banc depart={undefined} />);
        expect(carte().querySelector('[data-note="balises-sans-effet"]')).toBeNull();
    });

    it("est écrite dans les deux langues", () => {
        render(
            <FournisseurLangue>
                <Banc depart={undefined} />
            </FournisseurLangue>,
        );
        expect(carte().textContent).toMatch(/Balises d'expression permises/);
        expect(carte().textContent).toMatch(/Défaut de la voix/);
        expect(carte().textContent).toMatch(/Autre voix : le texte part tel qu'écrit/);
    });
});

describe("[.mark] la modale", () => {
    it("s'ouvre au clic sur la carte, centrée, avec sa notice", () => {
        render(<Banc depart={undefined} />);
        ouvrir();
        const modale = screen.getByRole("dialog");
        expect(modale.getAttribute("data-modale-phrase")).toBe("balises");
        expect(document.querySelector("[data-notice-balises]")?.textContent).toMatch(/cannot write one/i);
        expect(screen.getByRole("radio", { name: "The voice's default" }).getAttribute("aria-checked")).toBe("true");
    });

    it("s'ouvre aussi au clavier", () => {
        render(<Banc depart={undefined} />);
        fireEvent.keyDown(carte(), { key: "Enter" });
        expect(screen.getByRole("dialog")).toBeTruthy();
    });

    it("Annuler ne change rien", () => {
        const onChange = vi.fn();
        render(<Banc depart={["warm"]} onChange={onChange} />);
        ouvrir();
        ajouter("calm");
        fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
        expect(onChange).not.toHaveBeenCalled();
        expect(balises()).toEqual(["warm"]);
    });

    it("écrit la liste de l'agent sans crochets, en minuscules, sans doublon", async () => {
        const onChange = vi.fn();
        render(<Banc depart={undefined} onChange={onChange} />);
        ouvrir();
        ajouter("[Warm], PAUSE, warm");
        expect(screen.getByRole("radio", { name: "The agent's list" }).getAttribute("aria-checked")).toBe("true");
        appliquer();
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(onChange).toHaveBeenCalledWith(["warm", "pause"]);
        expect(balises()).toEqual(["warm", "pause"]);
    });

    it("« Aucune » écrit une liste vide", async () => {
        const onChange = vi.fn();
        render(<Banc depart={undefined} onChange={onChange} />);
        ouvrir();
        fireEvent.click(screen.getByRole("radio", { name: "None" }));
        appliquer();
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(onChange).toHaveBeenCalledWith([]);
        expect(carte().getAttribute("data-carte-balises")).toBe("aucune");
    });

    it("« Défaut » écrit undefined quand la clé n'était pas enregistrée, null sinon", async () => {
        const absente = vi.fn();
        render(<Banc depart={["warm"]} retourAuDefaut={undefined} onChange={absente} />);
        ouvrir();
        fireEvent.click(screen.getByRole("radio", { name: "The voice's default" }));
        appliquer();
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(absente).toHaveBeenCalledWith(undefined);
        cleanup();

        const enregistree = vi.fn();
        render(<Banc depart={["warm"]} retourAuDefaut={null} onChange={enregistree} />);
        ouvrir();
        fireEvent.click(screen.getByRole("radio", { name: "The voice's default" }));
        appliquer();
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(enregistree).toHaveBeenCalledWith(null);
    });

    it("rouvre sur la liste enregistrée", () => {
        render(<Banc depart={["warm", "calm"]} />);
        ouvrir();
        expect(screen.getByRole("radio", { name: "The agent's list" }).getAttribute("aria-checked")).toBe("true");
        expect(document.querySelector('[data-etiquette="warm"]')).not.toBeNull();
        expect(document.querySelector('[data-etiquette="calm"]')).not.toBeNull();
    });
});
