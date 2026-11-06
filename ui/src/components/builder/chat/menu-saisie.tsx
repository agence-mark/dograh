"use client";

/**
 * [.mark] Partie 3, sous-lot 11 (SE-17, E-7) : les menus « @ » et « / » du composeur du fil, comme la maquette (`useMenuSaisie`).
 *
 * « @ » n'importe où dans le message cite un objet (un agent, une recette de la bibliothèque) : le nom est écrit dans le message, le
 * builder le lit comme du texte. « / » au tout début du message propose une demande type : choisie, elle est écrite en phrase
 * (le builder répond à une phrase, pas à un code). Les entrées viennent des données réelles (agents de l'organisation, recettes
 * de la bibliothèque) ; rien n'est inventé. Clavier : flèches, Entrée ou Tab choisit, Échap ferme.
 */
import { Bot, BookOpen, FlaskConical, ListChecks } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useEffect, useMemo, useState } from "react";

import { getWorkflowsSummaryApiV1WorkflowSummaryGet, listerLesRecettesApiV1BuilderRecettesGet } from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { useAuth } from "@/lib/auth";

type Icone = typeof Bot;
export type EntreeDeSaisie = { groupe: Texte; nom: string; dit?: string; icone: Icone; /** Ce qui est écrit dans le message quand on la choisit. */ texte: string };

const GROUPES = {
    agents: { en: "Agents", fr: "Agents" },
    recettes: { en: "Library recipes", fr: "Recettes de la bibliothèque" },
    tests: { en: "Tests", fr: "Tests" },
    conduite: { en: "Driving the chat", fr: "Conduite du chat" },
} satisfies Record<string, Texte>;

/** Les demandes types du « / » : des phrases que le builder sait traiter avec ses actions (jouer les tests, contrôler, plan, rapport). */
const COMMANDES: { nom: string; groupe: Texte; dit: Texte; phrase: Texte; icone: Icone }[] = [
    { nom: "tester", groupe: GROUPES.tests, icone: FlaskConical, dit: { en: "Play the test suite on the draft", fr: "Jouer la suite de tests sur le brouillon" }, phrase: { en: "Play the whole test suite on the draft and tell me what fails.", fr: "Joue toute la suite de tests sur le brouillon et dis-moi ce qui échoue." } },
    { nom: "analyser", groupe: GROUPES.tests, icone: FlaskConical, dit: { en: "Analyze the real calls of the week", fr: "Analyser les vrais appels de la semaine" }, phrase: { en: "Analyze the real calls of the last week and tell me the causes that come back.", fr: "Analyse les vrais appels de la dernière semaine et dis-moi les causes qui reviennent." } },
    { nom: "controler", groupe: GROUPES.tests, icone: ListChecks, dit: { en: "Check the agent before publishing", fr: "Contrôler l'agent avant de publier" }, phrase: { en: "Check the agent step by step before publishing and list what to fix.", fr: "Contrôle l'agent étape par étape avant publication et liste ce qu'il faut corriger." } },
    { nom: "plan", groupe: GROUPES.conduite, icone: ListChecks, dit: { en: "Give the plan and where we are", fr: "Redonner le plan et où on en est" }, phrase: { en: "Give me the plan again and tell me where we are.", fr: "Redonne-moi le plan et dis-moi où on en est." } },
    { nom: "rapport", groupe: GROUPES.conduite, icone: ListChecks, dit: { en: "Write the report now", fr: "Faire le rapport maintenant" }, phrase: { en: "Write the end report now.", fr: "Fais le rapport de fin maintenant." } },
];

/** Le mot en cours : « @… » n'importe où, « /… » seulement en tout début de message. */
export const motEnCours = (texte: string): { signe: "@" | "/"; q: string; debut: number } | null => {
    const a = texte.match(/(^|\s)@([^\s@]*)$/);
    if (a) return { signe: "@", q: a[2], debut: texte.length - a[2].length - 1 };
    const c = texte.match(/^\/([^\s]*)$/);
    if (c) return { signe: "/", q: c[1], debut: 0 };
    return null;
};

const sans = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Les agents et les recettes réels, lus une fois (en parallèle) quand l'écran est connecté. */
export function useEntreesDeSaisie(): { mentions: EntreeDeSaisie[]; commandes: EntreeDeSaisie[] } {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [agents, setAgents] = useState<{ id: number; name: string }[]>([]);
    const [recettes, setRecettes] = useState<{ slug: string; nom: string }[]>([]);
    useEffect(() => {
        if (loading || !user) return;
        let vivant = true;
        void Promise.all([getWorkflowsSummaryApiV1WorkflowSummaryGet(), listerLesRecettesApiV1BuilderRecettesGet()]).then(([a, r]) => {
            if (!vivant) return;
            if (Array.isArray(a?.data)) setAgents(a.data as { id: number; name: string }[]);
            const lues = (r?.data as { recettes?: { slug: string; nom: string }[] } | undefined)?.recettes;
            if (lues) setRecettes(lues);
        });
        return () => {
            vivant = false;
        };
    }, [loading, user]);
    const mentions = useMemo<EntreeDeSaisie[]>(
        () => [
            ...agents.map((a) => ({ groupe: GROUPES.agents, nom: a.name, icone: Bot, texte: `@${a.name} ` })),
            ...recettes.map((r) => ({ groupe: GROUPES.recettes, nom: r.nom, icone: BookOpen, texte: `@${r.nom} ` })),
        ],
        [agents, recettes],
    );
    const commandes = useMemo<EntreeDeSaisie[]>(
        () => COMMANDES.map((c) => ({ groupe: c.groupe, nom: c.nom, dit: t(c.dit), icone: c.icone, texte: t(c.phrase) })),
        [t],
    );
    return { mentions, commandes };
}

/**
 * Le menu et la prise en charge du clavier. ``clavier(e)`` rend vrai quand la touche a servi au menu (le composeur n'envoie pas).
 * ``poser`` remplace le texte du message. ``sous`` : le menu s'ouvre SOUS la saisie (accueil du builder, décision 18), sinon au-dessus (fil).
 */
export function useMenuSaisie(texte: string, poser: (t: string) => void, entrees: { mentions: EntreeDeSaisie[]; commandes: EntreeDeSaisie[] }, sous = false) {
    const { t } = useLangue();
    const [actif, setActif] = useState(0);
    const [ferme, setFerme] = useState("");
    const mot = motEnCours(texte);
    const ouvert = !!mot && ferme !== texte;
    const liste = !mot
        ? []
        : (mot.signe === "@" ? entrees.mentions : entrees.commandes)
              .filter((e) => sans(`${e.nom} ${e.dit ?? ""}`).includes(sans(mot.q)))
              .slice(0, 12);
    const choisir = (e: EntreeDeSaisie) => {
        if (!mot) return;
        poser(texte.slice(0, mot.debut) + e.texte);
        setActif(0);
    };
    const clavier = (ev: KeyboardEvent): boolean => {
        if (!ouvert || liste.length === 0) return false;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            setActif((actif + 1) % liste.length);
            return true;
        }
        if (ev.key === "ArrowUp") {
            ev.preventDefault();
            setActif((actif - 1 + liste.length) % liste.length);
            return true;
        }
        if (ev.key === "Enter" || ev.key === "Tab") {
            ev.preventDefault();
            choisir(liste[Math.min(actif, liste.length - 1)]);
            return true;
        }
        if (ev.key === "Escape") {
            ev.preventDefault();
            setFerme(texte);
            return true;
        }
        return false;
    };
    const menu: ReactNode =
        ouvert && liste.length > 0 ? (
            <div role="listbox" data-menu-saisie={mot?.signe} className={`absolute left-0 z-20 max-h-80 w-[30rem] max-w-full overflow-auto rounded-xl border bg-popover p-1 shadow-lg ${sous ? "top-full mt-2" : "bottom-full mb-2"}`}>
                {liste.map((e, i) => {
                    const I = e.icone;
                    const titre = i === 0 || liste[i - 1].groupe !== e.groupe;
                    return (
                        <div key={`${e.groupe.en}-${e.nom}`}>
                            {titre && <p className="px-2 pt-2 pb-1 text-[11px] font-medium text-muted-foreground">{t(e.groupe)}</p>}
                            <button
                                type="button"
                                role="option"
                                aria-selected={i === actif}
                                onMouseDown={(ev) => {
                                    ev.preventDefault();
                                    choisir(e);
                                }}
                                onMouseEnter={() => setActif(i)}
                                className={`flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm ${i === actif ? "bg-muted font-medium" : ""}`}
                            >
                                <I className="size-4 shrink-0 text-muted-foreground" />
                                <span className={mot?.signe === "/" ? "font-mono text-[13px]" : ""}>{mot?.signe === "/" ? `/${e.nom}` : e.nom}</span>
                                {e.dit && <span className="ml-auto truncate pl-3 text-xs text-muted-foreground">{e.dit}</span>}
                            </button>
                        </div>
                    );
                })}
            </div>
        ) : null;
    return { menu, clavier };
}
