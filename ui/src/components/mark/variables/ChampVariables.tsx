"use client";

/**
 * [.mark] U3 bis (E62, E63) : `ChampVariables`, le champ de texte où les `{{variables}}` sont des étiquettes.
 *
 * - Un champ `contentEditable` : le texte tapé reste du texte, chaque `{{cle}}` devient une pastille ATOMIQUE (on la
 *   supprime d'un bloc), de la couleur de sa source (E63), rouge avec un ⚠ si le catalogue ne la connaît pas.
 * - Insertion : en tapant `{{` ou par double-clic dans le champ, un menu flottant (recherche, groupes par source,
 *   valeur d'exemple, ↑ ↓ Entrée).
 * - Clic sur une étiquette : « si vide, dire » (le `fallback` du moteur), valeur actuelle, changer, retirer.
 * - « Aperçu avec les valeurs » : le texte avec les exemples du catalogue.
 * - Le texte enregistré reste `{{cle}}` / `{{cle | fallback:repli}}` : aucun changement du moteur.
 */
import { AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { useLangue } from "../langue/langue";
import {
    apercu,
    clesInconnues,
    COULEUR_SOURCE,
    decouper,
    motif,
    NOM_SOURCE,
    type Source,
    sourceDe,
    type VariableCatalogue,
} from "./texte-etiquettes";

const SOURCES: Source[] = ["entreprise", "appel", "fiche", "campagne"];

const stylePastille = (couleur: string) =>
    `background:${couleur};color:#fff;border-radius:4px;padding:0 6px;margin:0 1px;font-size:12px;line-height:20px;display:inline-block;user-select:all;cursor:pointer`;

const poserPastille = (span: HTMLElement, cle: string, brut: string, catalogue: VariableCatalogue[], connu: boolean) => {
    const source = connu ? sourceDe(cle, catalogue) : "appel";
    span.contentEditable = "false";
    span.dataset.cle = cle;
    span.dataset.brut = brut;
    span.dataset.source = source;
    span.setAttribute("style", stylePastille(COULEUR_SOURCE[source]));
    const libelle = catalogue.find((v) => v.cle === cle)?.libelle ?? cle;
    span.textContent = source === "inconnue" ? `⚠ ${cle}` : libelle;
};

/** Pose les segments du texte dans le champ : du texte, des `<br>`, des pastilles. */
const construireDom = (el: HTMLElement, texte: string, catalogue: VariableCatalogue[], connu: boolean) => {
    el.textContent = "";
    for (const s of decouper(texte)) {
        if (s.type === "texte") {
            s.texte.split("\n").forEach((ligne, i) => {
                if (i > 0) el.appendChild(document.createElement("br"));
                if (ligne) el.appendChild(document.createTextNode(ligne));
            });
            continue;
        }
        const span = document.createElement("span");
        poserPastille(span, s.cle, s.brut, catalogue, connu);
        el.appendChild(span);
    }
};

/** Relit le texte enregistré depuis le champ : une pastille redonne son motif d'origine. */
export const lireDom = (el: HTMLElement): string => {
    const lire = (noeud: Node): string => {
        let sortie = "";
        noeud.childNodes.forEach((n, i) => {
            if (n.nodeType === Node.TEXT_NODE) sortie += n.textContent ?? "";
            else if (n instanceof HTMLElement) {
                if (n.dataset.cle) sortie += n.dataset.brut ?? "";
                else if (n.tagName === "BR") sortie += "\n";
                else sortie += (i > 0 ? "\n" : "") + lire(n);
            }
        });
        return sortie;
    };
    return lire(el);
};

export interface ChampVariablesProps {
    value: string;
    onChange: (valeur: string) => void;
    catalogue: VariableCatalogue[];
    /** `false` tant que le serveur n'a pas répondu : aucune étiquette n'est déclarée inconnue. */
    catalogueLu?: boolean;
    placeholder?: string;
    ariaLabel?: string;
    /** Une seule ligne (Entrée ne saute pas de ligne). */
    uneLigne?: boolean;
    className?: string;
}

export function ChampVariables({ value, onChange, catalogue, catalogueLu = true, placeholder, ariaLabel, uneLigne = false, className }: ChampVariablesProps) {
    const { t } = useLangue();
    const ref = useRef<HTMLDivElement>(null);
    const dernier = useRef<string | null>(null);
    const empreinteCatalogue = useRef<string>("");
    const plage = useRef<Range | null>(null);
    const [menu, setMenu] = useState<{ retirerAccolades: boolean; remplace: HTMLElement | null } | null>(null);
    const [recherche, setRecherche] = useState("");
    const [actif, setActif] = useState(0);
    const [etiquette, setEtiquette] = useState<HTMLElement | null>(null);
    const [voirApercu, setVoirApercu] = useState(false);

    // Le champ suit le texte venu de dehors (ouverture, annulation) ou le catalogue (les couleurs).
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const empreinte = `${catalogue.length}:${catalogueLu}`;
        if (dernier.current === value && empreinteCatalogue.current === empreinte) return;
        construireDom(el, value, catalogue, catalogueLu);
        empreinteCatalogue.current = empreinte;
        dernier.current = value;
    }, [value, catalogue, catalogueLu]);

    const publier = useCallback(() => {
        const el = ref.current;
        if (!el) return;
        const texte = lireDom(el);
        if (texte !== dernier.current) {
            dernier.current = texte;
            onChange(texte);
        }
    }, [onChange]);

    const garderPlage = () => {
        const sel = window.getSelection();
        plage.current = sel && sel.rangeCount > 0 && ref.current?.contains(sel.anchorNode) ? sel.getRangeAt(0).cloneRange() : null;
    };

    const ouvrir = (retirerAccolades: boolean, remplace: HTMLElement | null = null) => {
        garderPlage();
        setRecherche("");
        setActif(0);
        setEtiquette(null);
        setMenu({ retirerAccolades, remplace });
    };

    const onInput = () => {
        publier();
        const sel = window.getSelection();
        const noeud = sel?.anchorNode;
        if (noeud && noeud.nodeType === Node.TEXT_NODE && (noeud.textContent ?? "").slice(0, sel?.anchorOffset).endsWith("{{")) ouvrir(true);
    };

    const filtrees = useMemo(() => {
        const q = recherche.trim().toLowerCase();
        return SOURCES.flatMap((source) =>
            catalogue.filter(
                (v) => v.source === source && v.cle !== "initial_context" && (!q || v.cle.toLowerCase().includes(q) || v.libelle.toLowerCase().includes(q)),
            ),
        );
    }, [catalogue, recherche]);

    const choisir = (variable: VariableCatalogue) => {
        const el = ref.current;
        if (!el || !menu) return;
        if (menu.remplace) {
            const ancien = decouper(menu.remplace.dataset.brut ?? "").find((s) => s.type === "variable");
            const repli = ancien && ancien.type === "variable" ? ancien.repli : null;
            poserPastille(menu.remplace, variable.cle, motif(variable.cle, repli), catalogue, true);
        } else {
            const pastille = document.createElement("span");
            poserPastille(pastille, variable.cle, motif(variable.cle, null), catalogue, true);
            let range = plage.current;
            if (!range) {
                range = document.createRange();
                range.selectNodeContents(el);
                range.collapse(false);
            }
            if (menu.retirerAccolades && range.startContainer.nodeType === Node.TEXT_NODE) {
                const texte = range.startContainer as Text;
                const fin = range.startOffset;
                if ((texte.textContent ?? "").slice(fin - 2, fin) === "{{") {
                    texte.deleteData(fin - 2, 2);
                    range.setStart(texte, fin - 2);
                    range.collapse(true);
                }
            }
            range.insertNode(pastille);
            range.setStartAfter(pastille);
            range.collapse(true);
            const sel = window.getSelection();
            sel?.removeAllRanges();
            sel?.addRange(range);
        }
        setMenu(null);
        publier();
    };

    const surTouche = (e: React.KeyboardEvent) => {
        if (uneLigne && e.key === "Enter") e.preventDefault();
    };

    const surTocheMenu = (e: React.KeyboardEvent) => {
        if (e.key === "ArrowDown") {
            e.preventDefault();
            setActif((a) => Math.min(filtrees.length - 1, a + 1));
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActif((a) => Math.max(0, a - 1));
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (filtrees[actif]) choisir(filtrees[actif]);
        } else if (e.key === "Escape") {
            setMenu(null);
        }
    };

    const surClic = (e: React.MouseEvent) => {
        const cible = (e.target as HTMLElement).closest?.("[data-cle]") as HTMLElement | null;
        if (cible && ref.current?.contains(cible)) {
            setMenu(null);
            setEtiquette(cible);
        } else setEtiquette(null);
    };

    const inconnues = catalogueLu ? clesInconnues(value, catalogue) : [];
    const segment = etiquette ? decouper(etiquette.dataset.brut ?? "").find((s) => s.type === "variable") : undefined;
    const repliActuel = segment && segment.type === "variable" ? (segment.repli ?? "") : "";
    const exempleActuel = etiquette ? (catalogue.find((v) => v.cle === etiquette.dataset.cle)?.exemple ?? "") : "";

    return (
        <div className={cn("relative grid gap-1", className)} data-champ-variables>
            <div className="relative">
                {value === "" && placeholder && <span className="pointer-events-none absolute left-3 top-2 text-sm text-muted-foreground">{placeholder}</span>}
                <div
                    ref={ref}
                    role="textbox"
                    aria-multiline={!uneLigne}
                    aria-label={ariaLabel}
                    contentEditable
                    suppressContentEditableWarning
                    data-testid="champ-variables"
                    className={cn(
                        "w-full rounded-md border bg-background px-3 py-2 text-sm leading-6 outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        uneLigne ? "overflow-x-auto whitespace-nowrap" : "max-h-[300px] min-h-[100px] overflow-y-auto whitespace-pre-wrap",
                    )}
                    onInput={onInput}
                    onKeyDown={surTouche}
                    onClick={surClic}
                    onDoubleClick={(e) => {
                        if (!(e.target as HTMLElement).closest?.("[data-cle]")) ouvrir(false);
                    }}
                    onBlur={garderPlage}
                />
            </div>
            {menu && (
                <div className="absolute left-0 top-full z-50 mt-1 w-80 rounded-md border bg-popover p-2 shadow-md" data-testid="menu-variables" onKeyDown={surTocheMenu}>
                    <Input
                        autoFocus
                        aria-label={t({ en: "Search a variable", fr: "Chercher une variable" })}
                        value={recherche}
                        onChange={(e) => {
                            setRecherche(e.target.value);
                            setActif(0);
                        }}
                        className="mb-2 h-8"
                    />
                    <div className="max-h-64 overflow-y-auto">
                        {SOURCES.map((source) => {
                            const lignes = filtrees.filter((v) => v.source === source);
                            if (lignes.length === 0) return null;
                            return (
                                <div key={source} data-groupe={source}>
                                    <p className="px-1 pt-1 text-xs font-medium text-muted-foreground">{t(NOM_SOURCE[source])}</p>
                                    {lignes.map((v) => (
                                        <button
                                            key={v.cle}
                                            type="button"
                                            data-variable={v.cle}
                                            data-actif={filtrees[actif]?.cle === v.cle}
                                            onClick={() => choisir(v)}
                                            className={cn("flex w-full cursor-pointer items-center gap-2 rounded px-1 py-1 text-left text-sm hover:font-medium", filtrees[actif]?.cle === v.cle && "bg-muted")}
                                        >
                                            <span className="rounded px-1.5 text-xs text-white" style={{ background: COULEUR_SOURCE[source] }}>
                                                {v.libelle}
                                            </span>
                                            <span className="truncate text-xs text-muted-foreground">{v.exemple}</span>
                                        </button>
                                    ))}
                                </div>
                            );
                        })}
                        {filtrees.length === 0 && <p className="p-2 text-sm text-muted-foreground">{t({ en: "No variable.", fr: "Aucune variable." })}</p>}
                    </div>
                </div>
            )}
            {etiquette && (
                <div className="absolute left-0 top-full z-50 mt-1 w-72 space-y-2 rounded-md border bg-popover p-3 text-sm shadow-md" data-testid="fiche-etiquette">
                    <p className="font-medium">{etiquette.dataset.cle}</p>
                    {exempleActuel && (
                        <p className="text-xs text-muted-foreground">
                            {t({ en: "Current value", fr: "Valeur actuelle" })} : {exempleActuel}
                        </p>
                    )}
                    <label className="grid gap-1 text-xs">
                        {t({ en: "If empty, say", fr: "Si vide, dire" })}
                        <Input
                            aria-label={t({ en: "If empty, say", fr: "Si vide, dire" })}
                            defaultValue={repliActuel}
                            className="h-8"
                            onChange={(e) => {
                                const saisi = e.target.value.trim().replace(/[}|]/g, "");
                                etiquette.dataset.brut = motif(etiquette.dataset.cle ?? "", saisi || null);
                                publier();
                            }}
                        />
                    </label>
                    <div className="flex justify-between">
                        <button type="button" className="cursor-pointer text-xs hover:font-medium" onClick={() => ouvrir(false, etiquette)}>
                            {t({ en: "Change", fr: "Changer" })}
                        </button>
                        <button
                            type="button"
                            className="cursor-pointer text-xs text-destructive hover:font-medium"
                            onClick={() => {
                                etiquette.remove();
                                setEtiquette(null);
                                publier();
                            }}
                        >
                            {t({ en: "Remove", fr: "Retirer" })}
                        </button>
                    </div>
                </div>
            )}
            <div className="flex items-center justify-between text-xs">
                <button type="button" aria-pressed={voirApercu} className="cursor-pointer text-muted-foreground hover:font-medium" onClick={() => setVoirApercu((v) => !v)}>
                    {t({ en: "Preview with values", fr: "Aperçu avec les valeurs" })}
                </button>
                {inconnues.length > 0 && (
                    <span className="flex items-center gap-1 text-destructive" role="alert" data-testid="compteur-inconnues">
                        <AlertTriangle className="h-3 w-3" />
                        {t({ en: `${inconnues.length} unknown variable(s): publishing is refused`, fr: `${inconnues.length} variable(s) inconnue(s) : la publication sera refusée` })}
                    </span>
                )}
            </div>
            {voirApercu && (
                <p className="whitespace-pre-wrap rounded-md bg-muted p-2 text-sm" data-testid="apercu-variables">
                    {apercu(value, catalogue)}
                </p>
            )}
        </div>
    );
}
