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
 *
 * [.mark] Partie 3, lots 8 et 22 (§ 3 bis) : avec `objets`, le MÊME champ cite aussi des objets (`{{outil:…}}`, `{{etape:…}}`,
 * `{{agent:…}}`, `{{equipe:…}}`, `{{document:…}}`, `{{phrase:…}}`, `{{bloc:…}}`) : un seul sélecteur (`{{`, `@` ou double-clic),
 * trié par famille avec un filtre ; pastille à la couleur de la famille et au mot de la famille (« Outil › … ») ; rouge si l'objet
 * manque, est archivé ou si l'outil n'est pas rattaché à l'étape, avec sa correction en un clic ; carte au survol avec « Retirer ».
 */
import { AlertTriangle, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";
import {
    affiche,
    estObjet,
    type Famille,
    FAMILLES,
    figerBloc,
    type ObjetCitable,
    resoudre as resoudreObjet,
    STYLE_FAMILLE,
} from "./etiquettes-objets";
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
    `background:${couleur};color:white;border-radius:4px;padding:0 6px;margin:0 1px;font-size:12px;line-height:20px;display:inline-block;user-select:all;cursor:pointer`;

/** Ce qu'un champ sait des objets citables (absent : le champ ne cite que des variables). */
interface ContexteObjets {
    objets: ObjetCitable[];
    lu: boolean;
    outils: string[] | null;
    t: (x: Texte) => string;
}

const poserPastille = (span: HTMLElement, cle: string, brut: string, catalogue: VariableCatalogue[], connu: boolean, obj?: ContexteObjets) => {
    span.contentEditable = "false";
    span.dataset.cle = cle;
    span.dataset.brut = brut;
    if (estObjet(cle)) {
        const r = resoudreObjet(cle, obj?.objets ?? [], obj?.outils ?? null, Boolean(obj?.lu));
        span.dataset.famille = r.famille;
        span.dataset.source = r.motif ? "inconnue" : `objet-${r.famille}`;
        if (r.motif) span.dataset.erreur = r.motif;
        else delete span.dataset.erreur;
        span.setAttribute("style", stylePastille(r.motif ? COULEUR_SOURCE.inconnue : STYLE_FAMILLE[r.famille].couleur));
        span.textContent = `${r.motif ? "⚠ " : ""}${obj ? affiche(r, obj.t) : cle}`;
        return;
    }
    const source = connu ? sourceDe(cle, catalogue) : "appel";
    span.dataset.source = source;
    span.setAttribute("style", stylePastille(COULEUR_SOURCE[source]));
    const libelle = catalogue.find((v) => v.cle === cle)?.libelle ?? cle;
    span.textContent = source === "inconnue" ? `⚠ ${cle}` : libelle;
};

/** Pose les segments du texte dans le champ : du texte, des `<br>`, des pastilles. */
const construireDom = (el: HTMLElement, texte: string, catalogue: VariableCatalogue[], connu: boolean, obj?: ContexteObjets) => {
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
        poserPastille(span, s.cle, s.brut, catalogue, connu, obj);
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
    /** Lots 8 et 22 : les objets citables (absent = variables seulement ; `@` n'ouvre alors rien). */
    objets?: ObjetCitable[];
    objetsLus?: boolean;
    /** Les outils rattachés à l'étape qui porte ce texte (`null` : pas une étape, pas de contrôle « rattaché »). */
    outilsDeLEtape?: string[] | null;
    /** « Rattacher l'outil à l'étape » (correction en un clic) ; absent : la correction n'est pas proposée ici. */
    rattacher?: (toolUuid: string) => void;
    /** Clic sur un objet sans erreur : l'ouvrir à côté. */
    ouvrirObjet?: (cle: string) => void;
}

/** Une ligne du sélecteur : une variable ou un objet. */
interface Entree {
    cle: string;
    libelle: string;
    groupe: string;
    famille: Famille | "variable";
    couleur: string;
    detail: string;
    note?: string;
}

export function ChampVariables({
    value,
    onChange,
    catalogue,
    catalogueLu = true,
    placeholder,
    ariaLabel,
    uneLigne = false,
    className,
    objets,
    objetsLus = false,
    outilsDeLEtape = null,
    rattacher,
    ouvrirObjet,
}: ChampVariablesProps) {
    const { t } = useLangue();
    const ref = useRef<HTMLDivElement>(null);
    const racine = useRef<HTMLDivElement>(null);
    const dernier = useRef<string | null>(null);
    const empreinteCatalogue = useRef<string>("");
    const plage = useRef<Range | null>(null);
    const minuteur = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [menu, setMenu] = useState<{ retirerAccolades: boolean; remplace: HTMLElement | null } | null>(null);
    const [recherche, setRecherche] = useState("");
    const [actif, setActif] = useState(0);
    const [filtre, setFiltre] = useState<Famille | "variable" | null>(null);
    const [etiquette, setEtiquette] = useState<HTMLElement | null>(null);
    const [survol, setSurvol] = useState<HTMLElement | null>(null);
    const [voirApercu, setVoirApercu] = useState(false);
    const avecObjets = objets !== undefined;
    const outilsCle = (outilsDeLEtape ?? []).join(",");
    const obj: ContexteObjets | undefined = useMemo(
        () => (avecObjets ? { objets: objets ?? [], lu: objetsLus, outils: outilsDeLEtape, t } : undefined),
        // eslint-disable-next-line react-hooks/exhaustive-deps -- `outilsCle` porte le contenu de `outilsDeLEtape`
        [avecObjets, objets, objetsLus, outilsCle, t],
    );

    // Le champ suit le texte venu de dehors (ouverture, annulation), le catalogue (les couleurs) ou les outils de l'étape.
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const empreinte = `${catalogue.length}:${catalogueLu}:${objets?.length ?? -1}:${objetsLus}:${outilsCle}`;
        if (dernier.current === value && empreinteCatalogue.current === empreinte) return;
        construireDom(el, value, catalogue, catalogueLu, obj);
        empreinteCatalogue.current = empreinte;
        dernier.current = value;
    }, [value, catalogue, catalogueLu, objets, objetsLus, outilsCle, obj]);

    // Le sélecteur et les cartes se ferment au clic dehors (Échap : sur le menu ou dans le champ).
    useEffect(() => {
        if (!menu && !etiquette) return;
        const dehors = (e: MouseEvent) => {
            if (racine.current && !racine.current.contains(e.target as Node)) {
                setMenu(null);
                setEtiquette(null);
            }
        };
        // Échap ferme le menu ou la carte, jamais la fenêtre qui porte le champ (elle écoute Échap plus haut, en capture).
        const echap = (e: KeyboardEvent) => {
            if (e.key !== "Escape") return;
            e.preventDefault();
            e.stopImmediatePropagation();
            setMenu(null);
            setEtiquette(null);
        };
        document.addEventListener("mousedown", dehors);
        window.addEventListener("keydown", echap, true);
        return () => {
            document.removeEventListener("mousedown", dehors);
            window.removeEventListener("keydown", echap, true);
        };
    }, [menu, etiquette]);

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
        setFiltre(null);
        setEtiquette(null);
        setSurvol(null);
        setMenu({ retirerAccolades, remplace });
    };

    const onInput = () => {
        publier();
        const sel = window.getSelection();
        const noeud = sel?.anchorNode;
        const avant = noeud && noeud.nodeType === Node.TEXT_NODE ? (noeud.textContent ?? "").slice(0, sel?.anchorOffset) : "";
        if (avant.endsWith("{{")) ouvrir(true);
        else if (avecObjets && /(^|\s)@$/.test(avant)) ouvrir(true);
    };

    const filtrees: Entree[] = useMemo(() => {
        const q = recherche.trim().toLowerCase();
        const garde = (e: Entree) => !q || `${e.cle} ${e.libelle} ${e.detail}`.toLowerCase().includes(q);
        const variables: Entree[] =
            filtre === null || filtre === "variable"
                ? SOURCES.flatMap((source) =>
                      catalogue
                          .filter((v) => v.source === source && v.cle !== "initial_context")
                          .map((v) => ({
                              cle: v.cle,
                              libelle: v.libelle,
                              groupe: t(NOM_SOURCE[source]),
                              famille: "variable" as const,
                              couleur: COULEUR_SOURCE[source],
                              detail: v.exemple ?? "",
                          })),
                  )
                : [];
        const lesObjets: Entree[] = avecObjets
            ? FAMILLES.filter((fam) => filtre === null || filtre === fam).flatMap((fam) =>
                  (objets ?? [])
                      .filter((o) => o.famille === fam && o.statut === "actif")
                      .map((o) => ({
                          cle: o.cle,
                          libelle: o.libelle,
                          groupe: t(STYLE_FAMILLE[fam].pluriel),
                          famille: fam,
                          couleur: STYLE_FAMILLE[fam].couleur,
                          detail: fam === "outil" ? (o.rendu ?? "") : (o.resume ?? ""),
                          note:
                              resoudreObjet(o.cle, objets ?? [], outilsDeLEtape, true).motif === "non_rattache"
                                  ? t({ en: "not in the step", fr: "pas dans l'étape" })
                                  : undefined,
                      })),
              )
            : [];
        return [...variables, ...lesObjets].filter(garde);
        // eslint-disable-next-line react-hooks/exhaustive-deps -- `outilsCle` porte le contenu de `outilsDeLEtape`
    }, [catalogue, recherche, filtre, avecObjets, objets, outilsCle, t]);
    const groupes = [...new Set(filtrees.map((e) => e.groupe))];
    const famillesPresentes: (Famille | "variable")[] = avecObjets
        ? ["variable", ...FAMILLES.filter((fam) => (objets ?? []).some((o) => o.famille === fam && o.statut === "actif"))]
        : [];

    const choisir = (choix: Entree) => {
        const el = ref.current;
        if (!el || !menu) return;
        if (menu.remplace) {
            const ancien = decouper(menu.remplace.dataset.brut ?? "").find((s) => s.type === "variable");
            const repli = ancien && ancien.type === "variable" && !estObjet(choix.cle) ? ancien.repli : null;
            poserPastille(menu.remplace, choix.cle, motif(choix.cle, repli), catalogue, true, obj);
        } else {
            const pastille = document.createElement("span");
            poserPastille(pastille, choix.cle, motif(choix.cle, null), catalogue, true, obj);
            let range = plage.current;
            if (!range) {
                range = document.createRange();
                range.selectNodeContents(el);
                range.collapse(false);
            }
            if (menu.retirerAccolades && range.startContainer.nodeType === Node.TEXT_NODE) {
                const texte = range.startContainer as Text;
                const fin = range.startOffset;
                const contenu = texte.textContent ?? "";
                const geste = contenu.slice(fin - 2, fin) === "{{" ? 2 : contenu[fin - 1] === "@" ? 1 : 0;
                if (geste) {
                    texte.deleteData(fin - geste, geste);
                    range.setStart(texte, fin - geste);
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
        if (e.key === "Escape") {
            setEtiquette(null);
            setSurvol(null);
        }
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
            e.preventDefault();
            e.stopPropagation();
            setMenu(null);
        }
    };

    const surClic = (e: React.MouseEvent) => {
        const cible = (e.target as HTMLElement).closest?.("[data-cle]") as HTMLElement | null;
        if (cible && ref.current?.contains(cible)) {
            setMenu(null);
            setSurvol(null);
            // Un objet sans erreur s'ouvre à côté ; un objet en erreur montre sa correction ; une variable, son réglage.
            if (estObjet(cible.dataset.cle ?? "") && !cible.dataset.erreur && ouvrirObjet) {
                ouvrirObjet(cible.dataset.cle ?? "");
                setEtiquette(null);
            } else setEtiquette(cible);
        } else setEtiquette(null);
    };

    // La carte au survol d'un objet : un résumé, quelques lignes, le problème s'il y en a un, et « Retirer ».
    const surSurvol = (e: React.MouseEvent) => {
        const cible = (e.target as HTMLElement).closest?.("[data-cle]") as HTMLElement | null;
        if (!cible || !avecObjets || !estObjet(cible.dataset.cle ?? "") || menu || etiquette) return;
        if (minuteur.current) clearTimeout(minuteur.current);
        minuteur.current = setTimeout(() => setSurvol(cible), 200);
    };
    const quitterSurvol = () => {
        if (minuteur.current) clearTimeout(minuteur.current);
        minuteur.current = setTimeout(() => setSurvol(null), 250);
    };
    const garderSurvol = () => {
        if (minuteur.current) clearTimeout(minuteur.current);
    };
    useEffect(
        () => () => {
            if (minuteur.current) clearTimeout(minuteur.current);
        },
        [],
    );

    const retirerPastille = (el: HTMLElement) => {
        el.remove();
        setEtiquette(null);
        setSurvol(null);
        publier();
    };
    const reecrireBloc = (el: HTMLElement, version: number | null) => {
        const neuf = figerBloc(el.dataset.brut ?? "", el.dataset.cle ?? "", version).replace(/^\{\{\s*|\s*\}\}$/g, "");
        poserPastille(el, neuf, `{{${neuf}}}`, catalogue, true, obj);
        setEtiquette(null);
        publier();
    };

    const enErreur = [
        ...(catalogueLu ? clesInconnues(value, catalogue) : []),
        ...(obj && objetsLus
            ? decouper(value).flatMap((s) => (s.type === "variable" && estObjet(s.cle) && resoudreObjet(s.cle, obj.objets, obj.outils, true).motif ? [s.cle] : []))
            : []),
    ];
    const objetClique = etiquette && estObjet(etiquette.dataset.cle ?? "") ? resoudreObjet(etiquette.dataset.cle ?? "", objets ?? [], outilsDeLEtape, objetsLus) : null;
    const objetSurvole = survol && survol.isConnected ? resoudreObjet(survol.dataset.cle ?? "", objets ?? [], outilsDeLEtape, objetsLus) : null;
    const segment = etiquette && !objetClique ? decouper(etiquette.dataset.brut ?? "").find((s) => s.type === "variable") : undefined;
    const repliActuel = segment && segment.type === "variable" ? (segment.repli ?? "") : "";
    const exempleActuel = etiquette && !objetClique ? (catalogue.find((v) => v.cle === etiquette.dataset.cle)?.exemple ?? "") : "";

    return (
        <div ref={racine} className={cn("relative grid gap-1", className)} data-champ-variables>
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
                    onMouseOver={surSurvol}
                    onMouseLeave={quitterSurvol}
                    onDoubleClick={(e) => {
                        if (!(e.target as HTMLElement).closest?.("[data-cle]")) ouvrir(false);
                    }}
                    onBlur={garderPlage}
                />
            </div>
            {menu && (
                <div
                    className={cn("absolute left-0 top-full z-50 mt-1 rounded-md border bg-popover p-2 shadow-md", avecObjets ? "w-[400px]" : "w-80")}
                    data-testid="menu-variables"
                    onKeyDown={surTocheMenu}
                >
                    <Input
                        autoFocus
                        aria-label={
                            avecObjets
                                ? t({ en: "Search a variable, a tool, a step…", fr: "Chercher une variable, un outil, une étape…" })
                                : t({ en: "Search a variable", fr: "Chercher une variable" })
                        }
                        placeholder={
                            avecObjets
                                ? t({ en: "Search a variable, a tool, a step…", fr: "Chercher une variable, un outil, une étape…" })
                                : t({ en: "Search a variable", fr: "Chercher une variable" })
                        }
                        value={recherche}
                        onChange={(e) => {
                            setRecherche(e.target.value);
                            setActif(0);
                        }}
                        className="mb-2 h-8"
                    />
                    {avecObjets && (
                        <div className="mb-2 flex flex-wrap gap-1" role="group" aria-label={t({ en: "Families", fr: "Familles" })} data-testid="filtre-familles">
                            {([null, ...famillesPresentes] as (Famille | "variable" | null)[]).map((fam) => (
                                <button
                                    key={fam ?? "toutes"}
                                    type="button"
                                    aria-pressed={filtre === fam}
                                    onClick={() => {
                                        setFiltre(fam);
                                        setActif(0);
                                    }}
                                    className={cn(
                                        "h-6 cursor-pointer rounded-full px-2 text-[11px] hover:font-medium",
                                        filtre === fam ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                                    )}
                                >
                                    {fam === null ? t({ en: "All", fr: "Toutes" }) : fam === "variable" ? t({ en: "Variables", fr: "Variables" }) : t(STYLE_FAMILLE[fam].pluriel)}
                                </button>
                            ))}
                        </div>
                    )}
                    <div className="max-h-64 overflow-y-auto">
                        {groupes.map((groupe) => {
                            const lignes = filtrees.filter((e) => e.groupe === groupe);
                            const source = lignes[0]?.famille === "variable" ? SOURCES.find((s) => t(NOM_SOURCE[s]) === groupe) : undefined;
                            return (
                                <div key={groupe} data-groupe={source ?? lignes[0]?.famille}>
                                    <p className="px-1 pt-1 text-xs font-medium text-muted-foreground">{groupe}</p>
                                    {lignes.map((v) => (
                                        <button
                                            key={v.cle}
                                            type="button"
                                            data-variable={v.famille === "variable" ? v.cle : undefined}
                                            data-objet={v.famille === "variable" ? undefined : v.cle}
                                            data-actif={filtrees[actif]?.cle === v.cle}
                                            onClick={() => choisir(v)}
                                            className={cn(
                                                "flex w-full cursor-pointer items-center gap-2 rounded px-1 py-1 text-left text-sm hover:font-medium",
                                                filtrees[actif]?.cle === v.cle && "bg-muted",
                                            )}
                                        >
                                            <span className="max-w-[55%] shrink-0 truncate rounded px-1.5 text-xs text-white" style={{ background: v.couleur }}>
                                                {v.libelle}
                                            </span>
                                            <span className={cn("flex-1 truncate text-right text-xs", v.note ? "text-destructive" : "text-muted-foreground")}>{v.note ?? v.detail}</span>
                                        </button>
                                    ))}
                                </div>
                            );
                        })}
                        {filtrees.length === 0 && (
                            <p className="p-2 text-sm text-muted-foreground">
                                {avecObjets ? t({ en: "Nothing matches.", fr: "Rien ne correspond." }) : t({ en: "No variable.", fr: "Aucune variable." })}
                            </p>
                        )}
                    </div>
                </div>
            )}
            {etiquette && objetClique && (
                <div
                    className="absolute left-0 top-full z-50 mt-1 w-80 space-y-2 rounded-md border bg-popover p-3 text-sm shadow-md"
                    data-testid="probleme-etiquette"
                    role="dialog"
                    aria-label={affiche(objetClique, t)}
                >
                    <p className="font-medium">{affiche(objetClique, t)}</p>
                    {objetClique.message ? (
                        <p className="text-destructive">{t(objetClique.message)}</p>
                    ) : (
                        <p className="text-xs text-muted-foreground">{objetClique.objet?.resume}</p>
                    )}
                    <div className="grid gap-1.5">
                        {objetClique.motif === "non_rattache" && rattacher && (
                            <button
                                type="button"
                                className="cursor-pointer rounded-md bg-primary px-2 py-1.5 text-left text-xs text-primary-foreground hover:font-medium"
                                onClick={() => {
                                    rattacher((etiquette.dataset.cle ?? "").slice("outil:".length).split("/")[0]);
                                    setEtiquette(null);
                                }}
                            >
                                {t({ en: "Attach the tool to the step", fr: "Rattacher l'outil à l'étape" })}
                            </button>
                        )}
                        {objetClique.famille === "bloc" && objetClique.objet?.version && objetClique.epingle !== objetClique.objet.version && (
                            <button
                                type="button"
                                className="cursor-pointer rounded-md border px-2 py-1.5 text-left text-xs hover:font-medium"
                                onClick={() => reecrireBloc(etiquette, objetClique.objet?.version ?? null)}
                            >
                                {t({ en: `Stay on version ${objetClique.objet.version}`, fr: `Rester sur la version ${objetClique.objet.version}` })}
                            </button>
                        )}
                        {objetClique.famille === "bloc" && objetClique.epingle !== null && objetClique.objet?.version && (
                            <button type="button" className="cursor-pointer rounded-md border px-2 py-1.5 text-left text-xs hover:font-medium" onClick={() => reecrireBloc(etiquette, null)}>
                                {t({ en: "Follow the latest version", fr: "Suivre la dernière version" })}
                            </button>
                        )}
                        <button
                            type="button"
                            className="flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1.5 text-left text-xs text-destructive hover:font-medium"
                            onClick={() => retirerPastille(etiquette)}
                        >
                            <Trash2 className="h-3 w-3" />
                            {t({ en: "Remove the label", fr: "Retirer l'étiquette" })}
                        </button>
                    </div>
                </div>
            )}
            {survol && objetSurvole && !menu && !etiquette && (
                <div
                    className="absolute left-0 top-full z-50 mt-1 w-72 space-y-1.5 rounded-md border bg-popover p-3 text-sm shadow-md"
                    data-testid="carte-survol"
                    role="tooltip"
                    onMouseEnter={garderSurvol}
                    onMouseLeave={quitterSurvol}
                >
                    <div className="flex items-center gap-2">
                        <span
                            className="truncate rounded px-1.5 text-xs text-white"
                            style={{ background: objetSurvole.motif ? COULEUR_SOURCE.inconnue : STYLE_FAMILLE[objetSurvole.famille].couleur }}
                        >
                            {objetSurvole.libelle}
                        </span>
                        <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{t(STYLE_FAMILLE[objetSurvole.famille].prefixe)}</span>
                    </div>
                    {objetSurvole.objet?.resume && <p className="line-clamp-3 text-xs text-muted-foreground">{objetSurvole.objet.resume}</p>}
                    {(objetSurvole.objet?.lignes ?? []).slice(0, 3).map(([k, v]) => (
                        <p key={k} className="flex gap-2 text-xs">
                            <span className="shrink-0 text-muted-foreground">{k}</span>
                            <span className="truncate">{v}</span>
                        </p>
                    ))}
                    {objetSurvole.famille === "bloc" && (
                        <p className="text-xs">
                            {objetSurvole.epingle !== null
                                ? t({ en: `Stays on v${objetSurvole.epingle}`, fr: `Reste sur la v${objetSurvole.epingle}` })
                                : t({ en: "Follows the latest version in Recipe", fr: "Suit la dernière version en Recette" })}
                        </p>
                    )}
                    {objetSurvole.message ? (
                        <p className="text-xs text-destructive">
                            {t(objetSurvole.message)} {t({ en: "Click to fix.", fr: "Cliquer pour corriger." })}
                        </p>
                    ) : (
                        ouvrirObjet && <p className="text-xs text-muted-foreground">{t({ en: "Click to open it beside.", fr: "Cliquer pour l'ouvrir à côté." })}</p>
                    )}
                    <button type="button" className="flex cursor-pointer items-center gap-1 text-xs text-destructive hover:font-medium" onClick={() => retirerPastille(survol)}>
                        <Trash2 className="h-3 w-3" />
                        {t({ en: "Remove", fr: "Retirer" })}
                    </button>
                </div>
            )}
            {etiquette && !objetClique && (
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
                        <button type="button" className="cursor-pointer text-xs text-destructive hover:font-medium" onClick={() => retirerPastille(etiquette)}>
                            {t({ en: "Remove", fr: "Retirer" })}
                        </button>
                    </div>
                </div>
            )}
            <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-3">
                    <button type="button" aria-pressed={voirApercu} className="cursor-pointer text-muted-foreground hover:font-medium" onClick={() => setVoirApercu((v) => !v)}>
                        {t({ en: "Preview with values", fr: "Aperçu avec les valeurs" })}
                    </button>
                    {avecObjets && <span className="text-muted-foreground">{t({ en: "Double-click, {{ or @ for a label", fr: "Double-clic, {{ ou @ pour une étiquette" })}</span>}
                </span>
                {enErreur.length > 0 && (
                    <span className="flex items-center gap-1 text-destructive" role="alert" data-testid="compteur-inconnues">
                        <AlertTriangle className="h-3 w-3" />
                        {avecObjets
                            ? t({ en: `${enErreur.length} label(s) in error: publishing is blocked`, fr: `${enErreur.length} étiquette(s) en erreur : la publication est bloquée` })
                            : t({ en: `${enErreur.length} unknown variable(s): publishing is refused`, fr: `${enErreur.length} variable(s) inconnue(s) : la publication sera refusée` })}
                    </span>
                )}
            </div>
            {voirApercu && (
                <p className="whitespace-pre-wrap rounded-md bg-muted p-2 text-sm" data-testid="apercu-variables">
                    {apercu(value, catalogue, objets)}
                </p>
            )}
        </div>
    );
}
