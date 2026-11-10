/**
 * [.mark] Correctifs écran 7 à 12 (page d'un appel) : contrôle qualité en clair, phrases du code, titre avec le libellé de l'issue,
 * prix manquants dits en clair, contexte en trois parties. Les jeux d'essai ont la forme que le serveur écrit
 * (`api/services/juge/`, `etat_ouverture.py`, fiche de l'analyse du run).
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AnalyseDuRun } from "../fenetre-du-run/types";
import { PrixManquants } from "../fenetre-du-run/TableauDesCouts";
import { PhrasesDuCode } from "../groupe/PhrasesDuCode";
import { FournisseurLangue } from "../langue/langue";
import { ContexteDeLAppel } from "./ContexteDeLAppel";
import { ControleQualite } from "./ControleQualite";
import { libelleDeLIssue } from "./issue";
import { titreDeLaConversation } from "./titre";

vi.mock("../fenetre-du-run/FenetreDuRun", () => ({
    LigneNue: ({ libelle, children, testId }: { libelle: React.ReactNode; children: React.ReactNode; testId?: string }) => (
        <div data-testid={testId}>
            <span>{libelle}</span> <span>{children}</span>
        </div>
    ),
}));

afterEach(cleanup);
const dans = (ui: React.ReactNode) => render(<FournisseurLangue>{ui}</FournisseurLangue>);
const t = (x: { en: string; fr: string }) => x.fr;

const JUGE = {
    etat: "juge",
    source: "cle_api",
    modele: "mistral-small-2603",
    verdicts: [
        { critere: "Suit le parcours sans erreur", verdict: "reussi", replique: 2, preuve: "Bonjour", confiance: 0.9 },
        { critere: "Sait agir avec les outils", verdict: "rate", replique: 5, preuve: "Je vous réserve le créneau de mardi", confiance: 0.8 },
        { critere: "Extrait des données propres", verdict: "non_verifiable", replique: null, preuve: "Aucune donnée à lire.", confiance: 0.4 },
    ],
};

describe("[.mark] point 7 : contrôle qualité en clair", () => {
    it("dit la note, chaque verdict avec sa réplique, les étiquettes et le rangement dans À améliorer", () => {
        dans(<ControleQualite titre="Résultats" annotations={{ juge: JUGE }} mode="twilio" note={2.9} />);
        const q = screen.getByTestId("controle-qualite");
        expect(within(q).getByTestId("qualite-note").textContent).toContain("2,9 / 5");
        const verdicts = within(q).getAllByTestId("qualite-verdict");
        expect(verdicts).toHaveLength(3);
        expect(verdicts[1].textContent).toContain("Sait agir avec les outils");
        expect(verdicts[1].textContent).toContain("réplique n° 5");
        expect(verdicts[1].textContent).toContain("Je vous réserve le créneau de mardi");
        expect(within(q).getByTestId("qualite-etiquettes").textContent).toContain("Sait agir avec les outils");
        expect(within(q).getByTestId("qualite-a-ameliorer").textContent).toContain("oui, 2 critères");
        expect(q.textContent).not.toContain("{");
        expect(within(q).getByTestId("copier-json-qualite")).toBeTruthy();
    });
    it("un essai au navigateur dit que le juge ne lit que les vrais appels", () => {
        dans(<ControleQualite titre="Résultats" annotations={null} mode="smallwebrtc" note={null} />);
        expect(screen.getByTestId("appel-non-juge").textContent).toContain("ne lit que les vrais appels");
    });
    it("un état connu du juge se dit comme à l'en-tête", () => {
        dans(<ControleQualite titre="Résultats" annotations={{ juge: { etat: "trop_court" } }} mode="twilio" note={null} />);
        expect(screen.getByTestId("appel-non-juge").textContent).toContain("plus court que la durée minimale");
    });
    it("un verdict hors forme ne casse rien", () => {
        dans(<ControleQualite titre="R" annotations={{ juge: { etat: "juge", verdicts: [{ critere: { x: 1 } }, "n", { critere: "A", verdict: "rate" }] } }} mode="twilio" note={null} />);
        expect(screen.getAllByTestId("qualite-verdict")).toHaveLength(1);
    });
});

describe("[.mark] point 8 : phrases du code", () => {
    it("une ligne par phrase : moment, motif, phrase", () => {
        dans(<PhrasesDuCode contexte={{ phrases_du_code: [{ motif: "travail_dure", texte: "Un instant.", moment_s: 31.6 }] }} />);
        const ligne = document.querySelector('[data-phrase-dite="travail_dure"]')!;
        expect(ligne.textContent).toContain("00:31.6");
        expect(ligne.textContent).toContain("« Un instant. »");
    });
    it("sans phrase : un état vide, pas une page blanche", () => {
        dans(<PhrasesDuCode contexte={{}} />);
        expect(screen.getByTestId("phrases-du-code-vide").textContent).toContain("aucune phrase");
    });
});

describe("[.mark] point 9 : le libellé de l'issue dans le titre", () => {
    it("dit l'issue de départ en français et lit un code propre à l'agent", () => {
        expect(libelleDeLIssue("callback_requested", t)).toBe("Rappel demandé");
        expect(libelleDeLIssue("entretien_reserve", t)).toBe("Entretien reserve");
        expect(libelleDeLIssue({ x: 1 }, t)).toBe("");
        expect(titreDeLaConversation({ motif_appel: "Dépannage", mapped_call_disposition: "entretien_reserve" }, "Agent", t)).toBe("Dépannage · Entretien reserve");
    });
});

describe("[.mark] point 10 : coûts partiels dits en clair", () => {
    it("liste les briques sans prix et où les saisir", () => {
        dans(
            <PrixManquants
                sansPrix={[
                    { component: "llm", model: "mistral-small-2603" },
                    { component: "stt", model: "stt-rt-v5" },
                    { component: "tts", model: "sonic-3.6" },
                ]}
            />,
        );
        const m = screen.getByTestId("prix-manquants").textContent!;
        expect(m).toContain("mistral-small-2603 (cerveau)");
        expect(m).toContain("stt-rt-v5 (transcription)");
        expect(m).toContain("sonic-3.6 (voix)");
        expect(m).toContain("Fenêtre d'appel");
    });
});

const ANALYSE = {
    summary: { version: { commit: "ead374200000" } },
    record: {
        status: "ok",
        fields: [
            { name: "commune", value: { nom: "Verneuil-en-Halatte", code_insee: "60684", codes_postaux: ["60550"] }, empty: false },
            { name: "nom_appelant", value: "Durand", empty: false },
            { name: "urgence", value: null, empty: true },
        ],
    },
} as unknown as AnalyseDuRun;

describe("[.mark] points 11 et 12 : le contexte en trois parties", () => {
    const monter = (analyse: AnalyseDuRun | null = ANALYSE) =>
        dans(
            <ContexteDeLAppel
                initial={{
                    etablissement: "Atelier des Tilleuls",
                    etat_ouverture: "OUVERT",
                    horaires_ouverture: "lundi : 9h-12h\nmardi : 9h-12h",
                    date_appel: "mardi 10 novembre 2026",
                    call_id: "abc",
                    provider: "twilio",
                    annonce_ouverture: "Bonjour",
                }}
                recueilli={{ commune: { nom: "X" }, motif_appel: "RDV", call_status: "done" }}
                analyse={analyse}
                idAgent="4"
                idAppel="60"
                versionAgent={3}
            />,
        );
    it("contexte initial : libellés en français, horaires avec retours à la ligne, clés techniques écartées", () => {
        monter();
        const initial = screen.getByTestId("contexte-initial");
        expect(initial.textContent).toContain("Atelier des Tilleuls");
        expect(initial.textContent).toContain("Ouvert");
        expect(initial.textContent).not.toContain("twilio");
        expect(initial.textContent).not.toContain("abc");
        expect(initial.textContent).not.toContain("Bonjour");
        const horaires = within(initial).getByText(/lundi : 9h-12h/);
        expect(horaires.className).toContain("whitespace-pre-line");
    });
    it("contexte recueilli : champs de la fiche dans l'ordre, commune en clair, vides signalés", () => {
        monter();
        const r = screen.getByTestId("contexte-recueilli");
        const lignes = within(r).getAllByTestId("ligne-de-contexte").map((l) => l.textContent);
        expect(lignes[0]).toContain("Commune");
        expect(lignes[0]).toContain("Verneuil-en-Halatte (60550)");
        expect(lignes[1]).toContain("Nom appelant");
        expect(within(r).getByTestId("champs-non-renseignes").textContent).toContain("Urgence");
        expect(r.textContent).not.toContain("code_insee");
    });
    it("sans fiche lue : le contexte filtré, objets en clair", () => {
        monter(null);
        const r = screen.getByTestId("contexte-recueilli");
        expect(r.textContent).toContain("Motif appel");
        expect(r.textContent).not.toContain("done");
        expect(r.textContent).toContain("X");
    });
    it("identifiants : agent, version, appel, commit", () => {
        monter();
        const i = screen.getByTestId("contexte-identifiants").textContent!;
        expect(i).toContain("4");
        expect(i).toContain("v3");
        expect(i).toContain("60");
        expect(i).toContain("ead37420");
    });
    it("le JSON reste accessible derrière Copier", () => {
        monter();
        expect(screen.getAllByTestId("copier-json-contexte")).toHaveLength(2);
    });
});
