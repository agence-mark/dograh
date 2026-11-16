"use client";

/**
 * [.mark] Module Restauration, lot 13 (F6) : l'onglet Salle de la page Entreprise, repris de l'écran partagé de la maquette (`salle-commun.tsx`) et branché sur
 * les routes du fork (``GET …/salle``, ``PUT …/salle/plan``, ``PUT …/salle/creneaux``, ``POST …/reservations/{id}/statut``, lot 8 pour annuler).
 *
 * Trois vues : Jour (la frise de la soirée), Salles (le plan, tables déplacées et assemblées pour CE soir sans toucher au plan enregistré, « Revenir au plan »),
 * Planning (les réservations à venir, « Cette semaine » ou « Tous »). Chaque réservation se dit « Leroy · 2 · 20h30-22h00 ». « Régler » ouvre une grande fenêtre
 * centrale : Plan de salle (salles libres et renommables, palette de tables, grille aimantée, problèmes signalés) et Créneaux et durées (créneaux peints sur la
 * semaine, durée d'un repas par taille de groupe, règles).
 *
 * Le plan du soir (tables déplacées ou assemblées pour ce soir) reste dans l'écran : il n'est pas gardé en base (manque M13 du lot 26).
 */
import { CalendarDays, Check, Link2, Pencil, Plus, RotateCcw, Settings2, Trash2, Unlink, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { ECHECS } from "../notifications/phrases-echec";
import { EtatVide } from "../studio/etat-vide";
import { FenetreOnglets } from "../studio/fenetre-onglets";
import { Confirmer, EcranDonnees, SelecteurEtab, useTexte } from "./commun";
import { useCharge, useModuleRestauration } from "./contexte";
import {
    annulerLaReservation, type DureeDeGroupe, ecrireLePlan, ecrireLesCreneaux, type ElementDuPlan, type Forme, lireLaSalle, poserLeStatut,
    type ReglesDeSalle, type ReservationLue, type SalleDuPlan, type SalleRendue, type ServiceDeSalle, type TableDuPlan,
} from "./donnees-salle";

const GRILLE = { colonnes: 20, lignes: 12 };
const CASE = 38;
const JOURS_COURTS = { fr: ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"], en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] };
const PREMIERE_HEURE = 11; // la grille des créneaux : 24 demi-heures de 11 h à 23 h
const NOM_FORME: Record<Forme, { fr: string; en: string }> = { ronde: { fr: "Ronde", en: "Round" }, carree: { fr: "Carrée", en: "Square" }, rectangle: { fr: "Rectangle", en: "Rectangle" } };

const heure = (m: number) => `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
/** 1230 -> « 20h30 », la forme courte des infos pratiques. */
const hh = (m: number) => `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}`;
const sansCivilite = (n: string) => n.replace(/^(Mme|M\.|Mlle)\s+/, "");
const copie = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const libelleJour = (iso: string, en: boolean) =>
    new Date(`${iso}T12:00:00Z`).toLocaleDateString(en ? "en-GB" : "fr-FR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const ecartDeJours = (iso: string, depuis: string) => Math.round((Date.parse(`${iso}T12:00:00Z`) - Date.parse(`${depuis}T12:00:00Z`)) / 86_400_000);

// --------------------------------------------------------------------------- le modèle de l'écran, tiré de ce que le serveur rend

interface Plan {
    salles: SalleDuPlan[];
}
const planDe = (r: SalleRendue): Plan => ({
    salles: r.salles.map((s) => ({ id: String(s.id), nom: s.nom, elements: s.elements, tables: s.tables.map((t) => ({ ...t, id: String(t.id), assemblable_avec: t.assemblable_avec.map(String) })) })),
});

/** Ce qui cloche dans un plan, dit à l'écran (E-09 : problèmes mis en évidence). */
export function problemesDuPlan(salle: SalleDuPlan): { table: string; fr: string; en: string }[] {
    const out: { table: string; fr: string; en: string }[] = [];
    for (const a of salle.tables) {
        if (a.couverts_min === 0 || a.couverts_max < a.couverts_min) out.push({ table: a.id, fr: `${a.nom} : nombre de couverts à compléter`, en: `${a.nom}: seats to fill in` });
        for (const b of salle.tables) {
            if (a.id < b.id && a.x < b.x + b.l && a.x + a.l > b.x && a.y < b.y + b.h && a.y + a.h > b.y) out.push({ table: a.id, fr: `${a.nom} et ${b.nom} se chevauchent`, en: `${a.nom} and ${b.nom} overlap` });
        }
        if (a.x < 0 || a.y < 0 || a.x + a.l > GRILLE.colonnes || a.y + a.h > GRILLE.lignes) out.push({ table: a.id, fr: `${a.nom} sort du plan`, en: `${a.nom} is outside the plan` });
    }
    return out;
}

/** Les créneaux d'un établissement peints sur la semaine (lundi = 0) : une case est peinte si un créneau recouvre cette demi-heure. */
export function grilleDe(services: ServiceDeSalle[]): boolean[][] {
    return Array.from({ length: 7 }, (_, j) =>
        Array.from({ length: 24 }, (_, c) => {
            const debut = PREMIERE_HEURE * 60 + c * 30;
            return services.some((s) => {
                const [h1, m1] = s.debut.split(":").map(Number);
                const [h2, m2] = s.fin.split(":").map(Number);
                return s.jours.includes(j + 1) && h1 * 60 + m1 < debut + 30 && h2 * 60 + m2 > debut;
            });
        }),
    );
}
const finDeGrille = PREMIERE_HEURE * 60 + 24 * 30;
const dansLaGrille = (s: ServiceDeSalle) => {
    const [h1, m1] = s.debut.split(":").map(Number);
    const [h2, m2] = s.fin.split(":").map(Number);
    return h1 * 60 + m1 >= PREMIERE_HEURE * 60 && h2 * 60 + m2 <= finDeGrille;
};
const hm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
/** La grille peinte devient des créneaux : les séries de demi-heures de chaque jour, regroupées quand elles sont les mêmes d'un jour à l'autre. Un créneau
 * qui sort de la grille (avant 11 h, après 23 h) est gardé tel quel : l'écran ne le perd jamais. Un créneau qui a déjà ces heures garde son nom et son pas. */
export function servicesDe(grille: boolean[][], avant: ServiceDeSalle[]): ServiceDeSalle[] {
    const parSerie = new Map<string, number[]>();
    grille.forEach((ligne, j) => {
        let debut: number | null = null;
        for (let c = 0; c <= 24; c++) {
            if (c < 24 && ligne[c]) debut ??= c;
            else if (debut !== null) {
                const cle = `${debut}-${c}`;
                parSerie.set(cle, [...(parSerie.get(cle) ?? []), j + 1]);
                debut = null;
            }
        }
    });
    const horsGrille = avant.filter((s) => !dansLaGrille(s));
    const faits: ServiceDeSalle[] = [];
    for (const [cle, jours] of parSerie) {
        const [a, b] = cle.split("-").map(Number);
        const d = hm(PREMIERE_HEURE * 60 + a * 30), f = hm(PREMIERE_HEURE * 60 + b * 30);
        const connu = avant.find((s) => s.debut === d && s.fin === f);
        faits.push({ nom: connu?.nom ?? (PREMIERE_HEURE * 60 + a * 30 < 16 * 60 ? "Midi" : "Soir"), jours, debut: d, fin: f, pas_minutes: connu?.pas_minutes ?? avant[0]?.pas_minutes ?? 15 });
    }
    // deux séries au même nom (deux « Soir » à des heures différentes) : le nom porte les heures
    const noms = faits.map((s) => s.nom);
    return [...faits.map((s) => (noms.filter((n) => n === s.nom).length > 1 ? { ...s, nom: `${s.nom} ${s.debut}` } : s)), ...horsGrille.map(({ nom, jours, debut, fin, pas_minutes }) => ({ nom, jours, debut, fin, pas_minutes }))];
}

/** Les minutes depuis minuit « maintenant », tenues à jour depuis l'heure que le serveur a donnée à la lecture. */
function useMaintenantMin(depart: number) {
    const [debut] = useState(() => Date.now());
    const [n, setN] = useState(depart);
    useEffect(() => {
        const id = setInterval(() => setN(depart + (Date.now() - debut) / 60_000), 30_000);
        return () => clearInterval(id);
    }, [depart, debut]);
    return n;
}

// --------------------------------------------------------------------------- pièces communes

function LigneCliquable({ onOuvrir, libelle, children }: { onOuvrir: () => void; libelle?: string; children: React.ReactNode }) {
    return (
        <tr
            tabIndex={0}
            aria-label={libelle}
            onClick={onOuvrir}
            onKeyDown={(e) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onOuvrir();
                }
            }}
            className="cursor-pointer hover:bg-muted/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
        >
            {children}
        </tr>
    );
}

/** La grande fenêtre centrale du bouton « Régler » : les réglages profonds, sans quitter l'écran. */
function GrandeFenetre({
    titre, sous, fermer, onglets, onglet, choisir, children,
}: {
    titre: string;
    sous?: string;
    fermer: () => void;
    onglets: { cle: string; libelle: string }[];
    onglet: string;
    choisir: (cle: string) => void;
    children: React.ReactNode;
}) {
    return (
        <Dialog centree open onOpenChange={(o) => !o && fermer()}>
            <DialogContent className="flex h-[88vh] w-[min(96vw,1120px)] max-w-none flex-col gap-0 p-0 sm:max-w-none" data-fenetre-regler>
                <div className="shrink-0 space-y-3 border-b px-6 pt-5 pb-4">
                    <div>
                        <DialogTitle className="text-xl">{titre}</DialogTitle>
                        <DialogDescription className="text-sm text-muted-foreground">{sous}</DialogDescription>
                    </div>
                    <Tabs value={onglet} onValueChange={choisir}>
                        <TabsList>
                            {onglets.map((o) => (
                                <TabsTrigger key={o.cle} value={o.cle}>{o.libelle}</TabsTrigger>
                            ))}
                        </TabsList>
                    </Tabs>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">{children}</div>
            </DialogContent>
        </Dialog>
    );
}

/** Une table dessinée (forme, couleur d'état, nom et couverts). */
function DessinTable({ tb, classe, epais }: { tb: TableDuPlan; classe: string; epais: boolean }) {
    const cx = (tb.x + tb.l / 2) * CASE, cy = (tb.y + tb.h / 2) * CASE;
    return (
        <>
            {tb.forme === "ronde" ? (
                <ellipse cx={cx} cy={cy} rx={(tb.l * CASE) / 2 - 2} ry={(tb.h * CASE) / 2 - 2} className={classe} strokeWidth={epais ? 3 : 1.5} />
            ) : (
                <rect x={tb.x * CASE + 2} y={tb.y * CASE + 2} width={tb.l * CASE - 4} height={tb.h * CASE - 4} rx={tb.forme === "carree" ? 6 : 10} className={classe} strokeWidth={epais ? 3 : 1.5} />
            )}
            <text x={cx} y={cy - 2} textAnchor="middle" className="pointer-events-none fill-foreground text-[12px] font-semibold">{tb.nom.length > 8 ? tb.nom.slice(0, 7) + "…" : tb.nom}</text>
            <text x={cx} y={cy + 13} textAnchor="middle" className="pointer-events-none fill-muted-foreground text-[10px]">{tb.couverts_min || "?"}-{tb.couverts_max}</text>
        </>
    );
}

function Decor({ salle }: { salle: SalleDuPlan }) {
    const t = useTexte();
    return (
        <>
            <defs>
                <pattern id="grille" width={CASE} height={CASE} patternUnits="userSpaceOnUse">
                    <path d={`M ${CASE} 0 L 0 0 0 ${CASE}`} className="fill-none stroke-border" strokeWidth={1} />
                </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#grille)" />
            {salle.elements.map((el) => (
                <g key={el.id}>
                    <rect x={el.x * CASE} y={el.y * CASE} width={el.l * CASE} height={el.h * CASE} rx={6} className="fill-muted stroke-border" />
                    <text x={(el.x + el.l / 2) * CASE} y={(el.y + el.h / 2) * CASE + 4} textAnchor="middle" className="fill-muted-foreground text-[11px]">{el.type === "bar" ? t("Bar", "Bar") : t("Entrée", "Entrance")}</text>
                </g>
            ))}
        </>
    );
}

/** Glisser une table sur la grille (plan aimanté) : partagé par le configurateur et le mode service. */
function useGlisser(salle: SalleDuPlan, setSalle: (s: SalleDuPlan) => void, actif: boolean) {
    const svg = useRef<SVGSVGElement>(null);
    const glisse = useRef<{ id: string; dx: number; dy: number } | null>(null);
    const position = (ev: React.PointerEvent) => {
        const r = svg.current!.getBoundingClientRect();
        return { x: ((ev.clientX - r.left) / r.width) * GRILLE.colonnes, y: ((ev.clientY - r.top) / r.height) * GRILLE.lignes };
    };
    return {
        svg,
        commencer: (ev: React.PointerEvent, tb: TableDuPlan) => {
            if (!actif) return;
            const p = position(ev);
            glisse.current = { id: tb.id, dx: p.x - tb.x, dy: p.y - tb.y };
        },
        surSvg: {
            onPointerMove: (ev: React.PointerEvent) => {
                const g = glisse.current;
                if (!g || !actif) return;
                const p = position(ev);
                const x = Math.round(p.x - g.dx), y = Math.round(p.y - g.dy);
                const tb = salle.tables.find((o) => o.id === g.id);
                if (tb && (tb.x !== x || tb.y !== y)) setSalle({ ...salle, tables: salle.tables.map((o) => (o.id === g.id ? { ...o, x, y } : o)) });
            },
            onPointerUp: () => { glisse.current = null; },
            onPointerLeave: () => { glisse.current = null; },
        },
        fleches: (ev: React.KeyboardEvent, tb: TableDuPlan) => {
            if (!actif || !ev.key.startsWith("Arrow")) return;
            ev.preventDefault();
            const dx = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0, dy = ev.key === "ArrowDown" ? 1 : ev.key === "ArrowUp" ? -1 : 0;
            setSalle({ ...salle, tables: salle.tables.map((o) => (o.id === tb.id ? { ...o, x: o.x + dx, y: o.y + dy } : o)) });
        },
    };
}

function PlanSalle({ salle, setSalle, selection, setSelection, editable }: { salle: SalleDuPlan; setSalle: (s: SalleDuPlan) => void; selection: string | null; setSelection: (id: string | null) => void; editable: boolean }) {
    const t = useTexte();
    const g = useGlisser(salle, setSalle, editable);
    const enProbleme = new Set(problemesDuPlan(salle).map((p) => p.table));
    return (
        <svg
            ref={g.svg}
            viewBox={`0 0 ${GRILLE.colonnes * CASE} ${GRILLE.lignes * CASE}`}
            className="w-full touch-none rounded-xl border bg-card"
            role="application"
            aria-label={t("Plan de la salle : glissez une table pour la déplacer", "Floor plan: drag a table to move it")}
            {...g.surSvg}
            onClick={(ev) => { if (ev.target === g.svg.current) setSelection(null); }}
        >
            <Decor salle={salle} />
            {salle.tables.map((tb) => {
                const choisi = selection === tb.id, pb = enProbleme.has(tb.id);
                return (
                    <g
                        key={tb.id}
                        role="button"
                        tabIndex={0}
                        aria-label={`${tb.nom}, ${tb.couverts_min}-${tb.couverts_max}`}
                        aria-pressed={choisi}
                        className="cursor-pointer outline-none"
                        onPointerDown={(ev) => { ev.stopPropagation(); setSelection(tb.id); g.commencer(ev, tb); }}
                        onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") setSelection(tb.id); g.fleches(ev, tb); }}
                    >
                        <DessinTable tb={tb} epais={choisi || pb} classe={pb ? "fill-(--marque-danger) stroke-(--pastille-urgente)" : choisi ? "fill-(--acc-soft) stroke-(--acc)" : "fill-card stroke-foreground"} />
                    </g>
                );
            })}
        </svg>
    );
}

// --------------------------------------------------------------------------- Régler › Plan de salle

function Configurateur({ etab, rendu, editable, apres }: { etab: number; rendu: SalleRendue; editable: boolean; apres: (r: SalleRendue) => void }) {
    const t = useTexte();
    const { langue } = useLangue();
    const [salles, setSalles] = useState<SalleDuPlan[]>(() => copie(planDe(rendu).salles));
    const [courante, setCourante] = useState(0);
    const [selection, setSelection] = useState<string | null>(null);
    const [renomme, setRenomme] = useState<number | null>(null);
    const [rapide, setRapide] = useState("");
    const [aSupprimer, setASupprimer] = useState(false);
    const [modifie, setModifie] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const compteur = useRef(0);
    const nouvelId = () => `nouveau-${Date.now().toString(36)}-${compteur.current++}`;
    const salle = salles[courante];
    const maj = (s: SalleDuPlan) => { setSalles(salles.map((x, i) => (i === courante ? s : x))); setModifie(true); };
    if (!salle) {
        return (
            <div className="space-y-4">
                <p className="text-sm text-muted-foreground">{t("Aucune salle pour l'instant.", "No room yet.")}</p>
                {editable && <Button size="sm" onClick={() => { setSalles([{ id: nouvelId(), nom: t("Salle", "Room"), elements: [], tables: [] }]); setModifie(true); }}><Plus className="size-4" aria-hidden /> {t("Salle", "Room")}</Button>}
            </div>
        );
    }
    const table = salle.tables.find((x) => x.id === selection) ?? null;
    const problemes = problemesDuPlan(salle);
    const libre = (tables: TableDuPlan[], l: number, h: number) => {
        const pris: { x: number; y: number; l: number; h: number }[] = [...tables, ...salle.elements];
        for (let y = 0; y <= GRILLE.lignes - h; y++) for (let x = 0; x <= GRILLE.colonnes - l; x++) if (!pris.some((o) => x < o.x + o.l && x + l > o.x && y < o.y + o.h && y + h > o.y)) return { x, y };
        return { x: 0, y: 0 };
    };
    const numero = () => salles.reduce((n, s) => n + s.tables.length, 0) + 1;
    const ajouterTable = (forme: Forme, min: number, max: number): TableDuPlan => {
        const l = forme === "rectangle" ? 3 : 2;
        return { id: nouvelId(), nom: `T${numero()}`, forme, ...libre(salle.tables, l, 2), l, h: 2, couverts_min: min, couverts_max: max, assemblable_avec: [] };
    };
    const poseRapide = () => {
        const m = [...rapide.matchAll(/(\d+)\s*(?:tables?\s*)?de\s*(\d+)/gi)];
        if (!m.length) {
            notifier.echec({ fr: "Écrivez par exemple « 4 tables de 2, 6 de 4 ».", en: "Write for example \"4 tables of 2, 6 of 4\"." });
            return;
        }
        const nouvelles: TableDuPlan[] = [];
        let n = numero();
        for (const [, nb, c] of m) {
            for (let i = 0; i < Math.min(Number(nb), 40); i++) {
                const l = Number(c) > 4 ? 3 : 2;
                nouvelles.push({
                    id: nouvelId(), nom: `T${n++}`, forme: Number(c) > 4 ? "rectangle" : Number(c) <= 2 ? "ronde" : "carree", ...libre([...salle.tables, ...nouvelles], l, 2), l, h: 2,
                    couverts_min: Math.max(1, Number(c) - 1), couverts_max: Math.min(50, Number(c)), assemblable_avec: [],
                });
            }
        }
        maj({ ...salle, tables: [...salle.tables, ...nouvelles] });
        setRapide("");
        notifier.succes({ fr: `${nouvelles.length} tables posées. Rangez-les à la souris.`, en: `${nouvelles.length} tables placed. Arrange them with the mouse.` });
    };
    const enregistrer = async () => {
        if (problemes.length > 0 || salles.some((s) => problemesDuPlan(s).length > 0)) {
            notifier.echec({ fr: "Le plan a des problèmes (tables qui se chevauchent ou qui sortent) : corrigez-les d'abord.", en: "The plan has issues (overlapping or outside tables): fix them first." });
            return;
        }
        setEnCours(true);
        const r = await ecrireLePlan(etab, salles.map((s) => ({ ...s, tables: s.tables.map((x) => ({ ...x, assemblable_avec: x.assemblable_avec })) })));
        setEnCours(false);
        if (r.error || !r.data) {
            notifier.echec(ECHECS.restaurationSalleEnregistrer, { erreur: r.error });
            return;
        }
        setModifie(false);
        apres(r.data);
        setSalles(copie(planDe(r.data).salles));
        setSelection(null);
        notifier.succes({ fr: "Plan de salle enregistré.", en: "Floor plan saved." });
    };
    const majTable = (patch: Partial<TableDuPlan>) => maj({ ...salle, tables: salle.tables.map((x) => (x.id === table!.id ? { ...x, ...patch } : x)) });
    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label={t("Salles", "Rooms")}>
                {salles.map((s, i) => (
                    <div key={s.id} className="flex items-center">
                        {renomme === i ? (
                            <Input
                                autoFocus
                                defaultValue={s.nom}
                                className="h-9 w-40"
                                aria-label={t("Nom de la salle", "Room name")}
                                maxLength={60}
                                onBlur={(ev) => { setSalles(salles.map((x, k) => (k === i ? { ...x, nom: ev.target.value.trim() || x.nom } : x))); setRenomme(null); setModifie(true); }}
                                onKeyDown={(ev) => { if (ev.key === "Enter") (ev.target as HTMLInputElement).blur(); }}
                            />
                        ) : (
                            <Button role="tab" aria-selected={courante === i} size="sm" variant={courante === i ? "default" : "outline"} className="h-9 cursor-pointer" onClick={() => { setCourante(i); setSelection(null); }} onDoubleClick={() => editable && setRenomme(i)}>{s.nom}</Button>
                        )}
                        {courante === i && editable && renomme !== i && (
                            <Button variant="ghost" size="icon" className="size-8 cursor-pointer" aria-label={t("Renommer la salle", "Rename the room")} onClick={() => setRenomme(i)}><Pencil className="size-3.5" aria-hidden /></Button>
                        )}
                    </div>
                ))}
                {editable && salles.length < 12 && (
                    <Button size="sm" variant="ghost" className="h-9 cursor-pointer" onClick={() => { setSalles([...salles, { id: nouvelId(), nom: t("Nouvelle salle", "New room"), tables: [], elements: [] }]); setCourante(salles.length); setModifie(true); }}>
                        <Plus className="size-4" aria-hidden /> {t("Salle", "Room")}
                    </Button>
                )}
                {editable && salles.length > 1 && (
                    <Button size="sm" variant="ghost" className="h-9 cursor-pointer text-destructive" onClick={() => setASupprimer(true)}><Trash2 className="size-4" aria-hidden /> {t("Supprimer la salle", "Delete room")}</Button>
                )}
            </div>

            {editable && (
                <div className="flex flex-wrap items-center gap-2" aria-label={t("Palette", "Palette")}>
                    <span className="text-sm font-medium">{t("Ajouter", "Add")} :</span>
                    {(["ronde", "carree", "rectangle"] as Forme[]).map((f) => (
                        <Button key={f} size="sm" variant="outline" className="h-9 cursor-pointer" onClick={() => { const nt = ajouterTable(f, f === "rectangle" ? 4 : 2, f === "rectangle" ? 6 : f === "ronde" ? 2 : 4); maj({ ...salle, tables: [...salle.tables, nt] }); setSelection(nt.id); }}>
                            {NOM_FORME[f][langue]}
                        </Button>
                    ))}
                    <Button size="sm" variant="outline" className="h-9 cursor-pointer" onClick={() => { const p = libre(salle.tables, 5, 2); const el: ElementDuPlan = { id: `bar${Date.now().toString(36)}`, type: "bar", ...p, l: 5, h: 2 }; maj({ ...salle, elements: [...salle.elements, el] }); }}>{t("Bar", "Bar")}</Button>
                    <span className="mx-2 hidden h-6 w-px bg-border @xl:block" />
                    <Input value={rapide} onChange={(ev) => setRapide(ev.target.value)} onKeyDown={(ev) => { if (ev.key === "Enter") poseRapide(); }} className="h-9 w-64" placeholder={t("4 tables de 2, 6 de 4", "4 tables of 2, 6 of 4")} aria-label={t("Pose rapide", "Quick placement")} />
                    <Button size="sm" className="h-9 cursor-pointer" onClick={poseRapide} disabled={!rapide.trim()}><Zap className="size-4" aria-hidden /> {t("Pose rapide", "Quick placement")}</Button>
                </div>
            )}

            <div className="grid gap-5 @4xl:grid-cols-[minmax(0,1fr)_280px]">
                <PlanSalle salle={salle} setSalle={maj} selection={selection} setSelection={setSelection} editable={editable} />
                <aside className="space-y-5">
                    <div className="rounded-xl border bg-card p-4">
                        <p className="mb-2 text-sm font-semibold">{t("Résumé", "Summary")}</p>
                        <p className="text-sm text-muted-foreground">{salle.tables.length} {t("tables", "tables")} · {salle.tables.reduce((s, x) => s + x.couverts_max, 0)} {t("couverts", "covers")}</p>
                        {problemes.length === 0 ? (
                            <p className="mt-3 flex items-center gap-2 text-sm text-(--point-publie)"><Check className="size-4" aria-hidden /> {t("Aucun problème dans ce plan.", "No issues in this plan.")}</p>
                        ) : (
                            <ul className="mt-3 space-y-1.5" aria-label={t("Problèmes", "Issues")}>
                                {problemes.map((p, i) => (
                                    <li key={i}><button type="button" className="cursor-pointer text-left text-sm text-destructive hover:font-semibold" onClick={() => setSelection(p.table)}>⚠ {langue === "en" ? p.en : p.fr}</button></li>
                                ))}
                            </ul>
                        )}
                    </div>
                    {table && (
                        <div className="space-y-3 rounded-xl border bg-card p-4" aria-label={table.nom}>
                            <div className="space-y-1">
                                <Label htmlFor="nom-table" className="text-xs">{t("Nom", "Name")}</Label>
                                <Input id="nom-table" maxLength={40} disabled={!editable} value={table.nom} onChange={(ev) => majTable({ nom: ev.target.value })} />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-1">
                                    <Label htmlFor="cmin" className="text-xs">{t("Couverts min.", "Min. covers")}</Label>
                                    <Input id="cmin" type="number" min={1} disabled={!editable} value={table.couverts_min} onChange={(ev) => majTable({ couverts_min: Number(ev.target.value) })} />
                                </div>
                                <div className="space-y-1">
                                    <Label htmlFor="cmax" className="text-xs">{t("Couverts max.", "Max. covers")}</Label>
                                    <Input id="cmax" type="number" min={1} disabled={!editable} value={table.couverts_max} onChange={(ev) => majTable({ couverts_max: Number(ev.target.value) })} />
                                </div>
                            </div>
                            {table.assemblable_avec.length > 0 && (
                                <p className="text-xs text-muted-foreground">{t("Assemblable avec", "Can join")} {table.assemblable_avec.map((id) => salle.tables.find((x) => x.id === id)?.nom ?? id).join(", ")}</p>
                            )}
                            {editable && (
                                <Button variant="ghost" size="sm" className="cursor-pointer text-destructive" onClick={() => { maj({ ...salle, tables: salle.tables.filter((x) => x.id !== table.id).map((x) => ({ ...x, assemblable_avec: x.assemblable_avec.filter((a) => a !== table.id) })) }); setSelection(null); notifier.succes({ fr: "Table supprimée.", en: "Table deleted." }); }}>
                                    <Trash2 className="size-4" aria-hidden /> {t("Supprimer la table", "Delete table")}
                                </Button>
                            )}
                        </div>
                    )}
                </aside>
            </div>
            {editable && <div className="flex justify-end"><Button disabled={!modifie || enCours} onClick={() => void enregistrer()}>{t("Enregistrer le plan", "Save the plan")}</Button></div>}
            {aSupprimer && (
                <Confirmer
                    titre={t(`Supprimer « ${salle.nom} » ?`, `Delete "${salle.nom}"?`)}
                    texte={t("Ses tables disparaissent du plan. Une table réservée à venir ne se retire pas : le plan sera refusé à l'enregistrement.", "Its tables leave the plan. A table with a booking to come cannot be removed: the plan is refused on save.")}
                    bouton={t("Supprimer", "Delete")}
                    fermer={() => setASupprimer(false)}
                    valider={() => { setSalles(salles.filter((_, i) => i !== courante)); setCourante(0); setASupprimer(false); setModifie(true); notifier.succes({ fr: "Salle supprimée.", en: "Room deleted." }); }}
                />
            )}
        </div>
    );
}

// --------------------------------------------------------------------------- Régler › Créneaux et durées

type Tranche = { de: number; a: number; minutes: number };

function Creneaux({ etab, rendu, editable, apres }: { etab: number; rendu: SalleRendue; editable: boolean; apres: (r: SalleRendue) => void }) {
    const t = useTexte();
    const { langue } = useLangue();
    const [grille, setGrille] = useState<boolean[][]>(() => grilleDe(rendu.services));
    const [tranches, setTranches] = useState<Tranche[]>(() => rendu.durees.map((d) => ({ de: d.couverts_min, a: d.couverts_max, minutes: d.duree_minutes })));
    const [regles, setRegles] = useState(() => ({ delai: rendu.regles.delai_minimal / 60, jours: rendu.regles.jours_a_l_avance, taille: rendu.regles.couverts_max_groupe ?? 0 }));
    const [modifie, setModifie] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const peinture = useRef<boolean | null>(null);
    const poser = (j: number, c: number, v: boolean) => { setGrille((g) => g.map((l, jj) => (jj === j ? l.map((x, cc) => (cc === c ? v : x)) : l))); setModifie(true); };
    const majTranche = (i: number, champ: keyof Tranche, v: number) => { setTranches(tranches.map((x, k) => (k === i ? { ...x, [champ]: v } : x))); setModifie(true); };
    const majRegles = (r: Partial<typeof regles>) => { setRegles({ ...regles, ...r }); setModifie(true); };
    const enregistrer = async () => {
        if (tranches.some((x) => x.de < 1 || x.a < x.de || x.minutes < 15)) {
            notifier.echec({ fr: "Une tranche de durée est incomplète : de, à et minutes doivent se suivre.", en: "A length range is incomplete: from, to and minutes must be consistent." });
            return;
        }
        setEnCours(true);
        const durees: DureeDeGroupe[] = tranches.map((x) => ({ couverts_min: x.de, couverts_max: x.a, duree_minutes: x.minutes }));
        const r = await ecrireLesCreneaux(etab, {
            services: servicesDe(grille, rendu.services),
            durees,
            regles: { delai_minimal: Math.round(regles.delai * 60), jours_a_l_avance: regles.jours, couverts_max_groupe: regles.taille > 0 ? regles.taille : null } satisfies Partial<ReglesDeSalle>,
        });
        setEnCours(false);
        if (r.error || !r.data) {
            notifier.echec({ fr: "Créneaux et règles non enregistrés. Vérifiez les valeurs, puis réessayez.", en: "Slots and rules not saved. Check the values, then try again." }, { erreur: r.error });
            return;
        }
        setModifie(false);
        apres(r.data);
        notifier.succes({ fr: "Créneaux et règles enregistrés. L'agent les applique dès le prochain appel.", en: "Slots and rules saved. The agent applies them from the next call." });
    };
    return (
        <div className="space-y-5" onPointerUp={() => { peinture.current = null; }} onPointerLeave={() => { peinture.current = null; }}>
            <p className="text-sm text-muted-foreground">{t("Peignez les demi-heures où l'agent peut prendre des réservations. Un clic sur une case, puis glissez.", "Paint the half-hours when the agent can take bookings. Click a cell, then drag.")}</p>
            <div className="overflow-x-auto">
                <div className="grid min-w-[640px] touch-none gap-1 select-none" style={{ gridTemplateColumns: "44px repeat(24, minmax(0,1fr))" }} role="grid" aria-label={t("Créneaux de réservation de la semaine", "Weekly booking slots")}>
                    <span />
                    {Array.from({ length: 24 }, (_, c) => (
                        <span key={c} className="text-center text-[10px] text-muted-foreground">{c % 2 === 0 ? `${PREMIERE_HEURE + c / 2}h` : ""}</span>
                    ))}
                    {grille.map((ligne, j) => (
                        <div key={j} className="contents" role="row">
                            <span className="flex items-center text-xs text-muted-foreground">{JOURS_COURTS[langue][j]}</span>
                            {ligne.map((v, c) => (
                                <button
                                    key={c}
                                    type="button"
                                    role="gridcell"
                                    aria-pressed={v}
                                    aria-label={`${JOURS_COURTS[langue][j]} ${PREMIERE_HEURE + Math.floor(c / 2)} h ${c % 2 ? "30" : "00"}`}
                                    disabled={!editable}
                                    className={`h-8 rounded-sm ${v ? "bg-(--acc)" : "bg-muted"} ${editable ? "cursor-pointer hover:opacity-80" : ""} focus-visible:outline-2 focus-visible:outline-ring`}
                                    onPointerDown={() => { peinture.current = !v; poser(j, c, !v); }}
                                    onPointerEnter={() => { if (peinture.current !== null) poser(j, c, peinture.current); }}
                                    onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); poser(j, c, !v); } }}
                                />
                            ))}
                        </div>
                    ))}
                </div>
            </div>
            {rendu.services.some((s) => !dansLaGrille(s)) && (
                <p className="text-xs text-muted-foreground">{t("Un créneau hors de la grille (avant 11 h ou après 23 h) est gardé tel quel.", "A slot outside the grid (before 11 am or after 11 pm) is kept as it is.")}</p>
            )}
            <div className="grid gap-6 rounded-xl border bg-card p-5 @3xl:grid-cols-2">
                <section aria-label={t("Durée d'un repas", "Meal length")} className="space-y-3">
                    <p className="text-sm font-semibold">{t("Durée d'un repas", "Meal length")}</p>
                    <p className="text-xs text-muted-foreground">{t("La table est bloquée ce temps-là. L'agent s'en sert pour savoir si une table se libère à temps.", "The table is held for this long. The agent uses it to know whether a table frees up in time.")}</p>
                    <div className="grid w-fit grid-cols-[auto_3.5rem_auto_3.5rem_auto_4rem_auto_2rem] items-center gap-x-2 gap-y-2 text-sm">
                        {tranches.map((g, i) => (
                            <div key={i} className="contents">
                                <span className="text-muted-foreground">{t("De", "From")}</span>
                                <Input aria-label={t("De (personnes)", "From (people)")} type="number" min={1} disabled={!editable} value={g.de} onChange={(ev) => majTranche(i, "de", Number(ev.target.value))} className="h-8 w-14 text-right tabular-nums" />
                                <span className="text-muted-foreground">{t("à", "to")}</span>
                                <Input aria-label={t("À (personnes)", "To (people)")} type="number" min={1} disabled={!editable} value={g.a} onChange={(ev) => majTranche(i, "a", Number(ev.target.value))} className="h-8 w-14 text-right tabular-nums" />
                                <span className="text-muted-foreground">{t("pers.", "ppl")}</span>
                                <Input aria-label={t("Durée en minutes", "Length in minutes")} type="number" min={15} step={15} disabled={!editable} value={g.minutes} onChange={(ev) => majTranche(i, "minutes", Number(ev.target.value))} className="h-8 w-16 text-right tabular-nums" />
                                <span className="text-muted-foreground">min</span>
                                {editable ? (
                                    <Button variant="ghost" size="icon" className="size-8 cursor-pointer" aria-label={t("Retirer cette tranche", "Remove this range")} onClick={() => { setTranches(tranches.filter((_, k) => k !== i)); setModifie(true); }}><Trash2 className="size-3.5" aria-hidden /></Button>
                                ) : <span />}
                            </div>
                        ))}
                    </div>
                    {editable && (
                        <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => { const der = tranches[tranches.length - 1]; setTranches([...tranches, { de: der ? der.a + 1 : 1, a: der ? der.a + 4 : 2, minutes: der ? der.minutes + 15 : 75 }]); setModifie(true); }}>
                            <Plus className="size-3.5" aria-hidden /> {t("Tranche", "Range")}
                        </Button>
                    )}
                </section>
                <section aria-label={t("Règles", "Rules")} className="space-y-3">
                    <p className="text-sm font-semibold">{t("Règles", "Rules")}</p>
                    <div className="grid w-fit grid-cols-[auto_4rem_auto] items-center gap-x-3 gap-y-2 text-sm">
                        {([
                            ["delai", t("Réserver au moins", "Book at least"), regles.delai, t("h à l'avance", "h ahead"), (v: number) => majRegles({ delai: v })],
                            ["jours", t("Réserver au plus", "Book at most"), regles.jours, t("jours à l'avance", "days ahead"), (v: number) => majRegles({ jours: v })],
                            ["taille", t("Groupe le plus grand (0 : sans limite)", "Largest group (0: no limit)"), regles.taille, t("pers.", "ppl"), (v: number) => majRegles({ taille: v })],
                        ] as const).map(([id, lib, val, unite, changer]) => (
                            <div key={id} className="contents">
                                <Label htmlFor={`regle-${id}`}>{lib}</Label>
                                <Input id={`regle-${id}`} type="number" min={0} disabled={!editable} value={val} onChange={(ev) => changer(Number(ev.target.value))} className="h-8 w-16 text-right tabular-nums" />
                                <span className="text-sm text-muted-foreground">{unite}</span>
                            </div>
                        ))}
                    </div>
                </section>
                {editable && <div className="flex justify-end @3xl:col-span-2"><Button disabled={!modifie || enCours} onClick={() => void enregistrer()}>{t("Enregistrer", "Save")}</Button></div>}
            </div>
        </div>
    );
}

// --------------------------------------------------------------------------- le service de ce soir

/** Le plan du soir : tables déplacées et assemblées pour ce soir, sans toucher au plan enregistré. */
type Soir = { salles: SalleDuPlan[]; groupes: string[][]; tablesDe: Record<string, string[]> };
type Etat = "libre" | "reservee" | "bientot" | "arrivee";
type Bloc = { id: string; prenom: string; couverts: number; debut: number; fin: number; statut: "reservee" | "arrivee" };

const CLASSE_ETAT: Record<Etat, string> = {
    libre: "fill-card stroke-foreground",
    reservee: "fill-(--acc-soft) stroke-(--acc)",
    bientot: "fill-(--acc-soft) stroke-(--acc) [stroke-dasharray:5_3]",
    arrivee: "fill-(--marque-succes) stroke-(--point-publie)",
};
const CLASSE_BLOC: Record<Etat, string> = {
    libre: "bg-muted",
    reservee: "bg-(--acc-soft) text-foreground border-(--acc)",
    bientot: "bg-(--acc-soft) text-foreground border-(--acc) border-dashed",
    arrivee: "bg-(--marque-succes) text-(--marque-succes-texte) border-(--point-publie)",
};

const blocsDuJour = (r: SalleRendue): Bloc[] =>
    r.reservations
        .filter((x) => x.jour === r.aujourd_hui)
        .map((x) => ({ id: x.numero, prenom: x.prenom ?? "?", couverts: x.couverts, debut: x.debut_min, fin: x.debut_min + x.duree_minutes, statut: x.statut === "honoree" ? "arrivee" : "reservee" }));
const infos = (b: Bloc) => `${sansCivilite(b.prenom)} · ${b.couverts} · ${hh(b.debut)}-${hh(b.fin)}`;
const soirDepart = (r: SalleRendue): Soir => ({ salles: copie(planDe(r).salles), groupes: [], tablesDe: Object.fromEntries(r.reservations.filter((x) => x.jour === r.aujourd_hui).map((x) => [x.numero, x.table_ids.map(String)])) });

function Legende() {
    const t = useTexte();
    return (
        <div className="flex flex-wrap items-center gap-4 text-xs">
            <span className="flex items-center gap-1.5"><span className="size-3 rounded-sm border border-foreground/40 bg-card" /> {t("Libre", "Free")}</span>
            <span className="flex items-center gap-1.5"><span className="size-3 rounded-sm border border-(--acc) bg-(--acc-soft)" /> {t("Réservée", "Booked")}</span>
            <span className="flex items-center gap-1.5"><span className="size-3 rounded-sm border border-dashed border-(--acc) bg-(--acc-soft)" /> {t("Bientôt", "Soon")}</span>
            <span className="flex items-center gap-1.5"><span className="size-3 rounded-sm border border-(--point-publie) bg-(--marque-succes)" /> {t("Arrivée", "Arrived")}</span>
        </div>
    );
}

function Service({ rendu, vue, soir, setSoir, ouvrir }: { rendu: SalleRendue; vue: "plan" | "frise"; soir: Soir; setSoir: (s: Soir | null) => void; ouvrir: (id: string) => void }) {
    const t = useTexte();
    const now = useMaintenantMin(rendu.maintenant_min);
    const [courante, setCourante] = useState(0);
    const [selection, setSelection] = useState<string | null>(null);
    const blocs = useMemo(() => blocsDuJour(rendu), [rendu]);
    const salle = soir.salles[courante] ?? { id: "", nom: "", elements: [], tables: [] };
    const plan = useMemo(() => planDe(rendu).salles, [rendu]);
    const deplacee = JSON.stringify(soir.salles.map((s) => s.tables.map((x) => [x.id, x.x, x.y]))) !== JSON.stringify(plan.map((s) => s.tables.map((x) => [x.id, x.x, x.y])));
    const change = deplacee || soir.groupes.length > 0;
    const g = useGlisser(salle, (s) => setSoir({ ...soir, salles: soir.salles.map((x, i) => (i === courante ? s : x)) }), true);

    const groupeDe = (id: string) => soir.groupes.find((gr) => gr.includes(id)) ?? null;
    const blocsDe = (ids: string[]) => blocs.filter((b) => (soir.tablesDe[b.id] ?? []).some((x) => ids.includes(x))).sort((a, b) => a.debut - b.debut);
    const etatDe = (b: Bloc): Etat => (b.statut === "arrivee" && now < b.fin ? "arrivee" : b.debut - now <= 30 && b.debut - now > -5 ? "bientot" : "reservee");
    /** La réservation qu'on montre sur une table : celle en cours, sinon la prochaine de la soirée. */
    const montree = (ids: string[]) => blocsDe(ids).find((b) => b.fin > now) ?? null;
    const etatTable = (ids: string[]): Etat => { const b = montree(ids); return b ? etatDe(b) : "libre"; };
    const nomsDe = (ids: string[]) => ids.map((id) => soir.salles.flatMap((s) => s.tables).find((x) => x.id === id)?.nom ?? id);

    const assembler = (a: string, b: string) => {
        const ga = groupeDe(a) ?? [a], gb = groupeDe(b) ?? [b];
        const nouveau = [...new Set([...ga, ...gb])];
        setSoir({ ...soir, groupes: [...soir.groupes.filter((gr) => gr !== groupeDe(a) && gr !== groupeDe(b)), nouveau] });
        notifier.succes({ fr: `Tables ${nomsDe(nouveau).join(" + ")} assemblées pour ce soir.`, en: `Tables ${nomsDe(nouveau).join(" + ")} joined for tonight.` });
    };
    const separer = (id: string) => { setSoir({ ...soir, groupes: soir.groupes.filter((gr) => !gr.includes(id)) }); notifier.succes({ fr: "Tables séparées.", en: "Tables split." }); };
    const revenir = () => { setSoir(null); setSelection(null); notifier.information({ fr: "Retour au plan de salle enregistré.", en: "Back to the saved floor plan." }); };

    const choisie = selection ? salle.tables.find((x) => x.id === selection) ?? null : null;
    const unite = choisie ? groupeDe(choisie.id) ?? [choisie.id] : [];
    const tablesUnite = salle.tables.filter((x) => unite.includes(x.id));
    const voisines = choisie ? salle.tables.filter((x) => !unite.includes(x.id)).sort((a, b) => Math.hypot(a.x - choisie.x, a.y - choisie.y) - Math.hypot(b.x - choisie.x, b.y - choisie.y)).slice(0, 6) : [];

    // Lignes de la frise : un groupe assemblé = une ligne ; sinon une ligne par table.
    const lignes = useMemo(() => {
        const vues = new Set<string>();
        const out: { ids: string[]; nom: string; couverts: number }[] = [];
        for (const s of soir.salles) for (const tb of s.tables) {
            if (vues.has(tb.id)) continue;
            const ids = soir.groupes.find((gr) => gr.includes(tb.id)) ?? [tb.id];
            ids.forEach((x) => vues.add(x));
            const tbs = soir.salles.flatMap((x) => x.tables).filter((x) => ids.includes(x.id));
            out.push({ ids, nom: tbs.map((x) => x.nom).join("+"), couverts: tbs.reduce((n, x) => n + x.couverts_max, 0) });
        }
        return out;
    }, [soir]);

    if (soir.salles.every((s) => s.tables.length === 0)) {
        return <EtatVide cas="premier" icone={CalendarDays} titre={t("Aucune table pour l'instant", "No table yet")} info={t("Posez vos salles et vos tables dans « Régler ».", "Place your rooms and tables in “Settings”.")} />;
    }
    const debut = 18 * 60, fin = 23 * 60, total = fin - debut;
    const pct = (m: number) => `${((Math.min(fin, Math.max(debut, m)) - debut) / total) * 100}%`;

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
                <Legende />
                <span className="flex-1" />
                {change && (
                    <>
                        <span className="text-xs text-muted-foreground">{t("Disposition de ce soir : le plan de salle n'est pas modifié.", "Tonight's layout: the saved floor plan is unchanged.")}</span>
                        <Button variant="outline" size="sm" className="cursor-pointer" onClick={revenir}><RotateCcw className="size-3.5" aria-hidden /> {t("Revenir au plan", "Back to the plan")}</Button>
                    </>
                )}
            </div>

            {vue === "plan" ? (
                <>
                    {soir.salles.length > 1 && (
                        <div className="flex flex-wrap gap-2" role="tablist" aria-label={t("Salles", "Rooms")}>
                            {soir.salles.map((s, i) => (
                                <Button key={s.id} role="tab" aria-selected={courante === i} size="sm" variant={courante === i ? "default" : "outline"} className="h-9 cursor-pointer" onClick={() => { setCourante(i); setSelection(null); }}>{s.nom}</Button>
                            ))}
                        </div>
                    )}
                    <div className="grid gap-5 @4xl:grid-cols-[minmax(0,1fr)_280px]">
                        <svg
                            ref={g.svg}
                            viewBox={`0 0 ${GRILLE.colonnes * CASE} ${GRILLE.lignes * CASE}`}
                            className="w-full touch-none rounded-xl border bg-card"
                            role="application"
                            aria-label={t("Plan du service : glissez une table pour la déplacer ce soir", "Service floor plan: drag a table to move it tonight")}
                            {...g.surSvg}
                            onClick={(ev) => { if (ev.target === g.svg.current) setSelection(null); }}
                        >
                            <Decor salle={salle} />
                            {soir.groupes.map((gr) => {
                                const tbs = salle.tables.filter((x) => gr.includes(x.id));
                                if (tbs.length < 2) return null;
                                const x0 = Math.min(...tbs.map((x) => x.x)), y0 = Math.min(...tbs.map((x) => x.y)), x1 = Math.max(...tbs.map((x) => x.x + x.l)), y1 = Math.max(...tbs.map((x) => x.y + x.h));
                                return (
                                    <g key={gr.join("+")} className="pointer-events-none">
                                        <rect x={x0 * CASE - 5} y={y0 * CASE - 5} width={(x1 - x0) * CASE + 10} height={(y1 - y0) * CASE + 10} rx={12} className="fill-none stroke-foreground" strokeWidth={1.25} strokeDasharray="5 4" />
                                        <text x={x0 * CASE} y={y0 * CASE - 9} className="fill-foreground text-[10px] font-semibold">{tbs.map((x) => x.nom).join(" + ")} · {tbs.reduce((n, x) => n + x.couverts_max, 0)} {t("couv.", "cov.")}</text>
                                    </g>
                                );
                            })}
                            {salle.tables.map((tb) => {
                                const ids = groupeDe(tb.id) ?? [tb.id];
                                const b = montree(ids);
                                const choisi = unite.includes(tb.id);
                                const premiere = ids[0] === tb.id;
                                return (
                                    <g
                                        key={tb.id}
                                        role="button"
                                        tabIndex={0}
                                        aria-label={`${tb.nom}${b ? `, ${infos(b)}` : ""}`}
                                        aria-pressed={choisi}
                                        className="cursor-pointer outline-none"
                                        onPointerDown={(ev) => { ev.stopPropagation(); setSelection(tb.id); g.commencer(ev, tb); }}
                                        onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") setSelection(tb.id); g.fleches(ev, tb); }}
                                    >
                                        <DessinTable tb={tb} epais={choisi} classe={CLASSE_ETAT[etatTable(ids)]} />
                                        {b && premiere && (
                                            <foreignObject x={tb.x * CASE - 16} y={(tb.y + tb.h) * CASE + 2} width={tb.l * CASE + 32} height={36} className="pointer-events-none overflow-visible">
                                                <div className="flex justify-center">
                                                    <span className="flex flex-col items-center rounded-md border bg-background px-1.5 py-0.5 text-center text-[10px] leading-tight text-foreground shadow-xs">
                                                        <b className="max-w-full truncate font-semibold">{sansCivilite(b.prenom)}</b>
                                                        <span className="whitespace-nowrap tabular-nums">{b.couverts} · {hh(b.debut)}-{hh(b.fin)}</span>
                                                    </span>
                                                </div>
                                            </foreignObject>
                                        )}
                                    </g>
                                );
                            })}
                        </svg>
                        <aside className="space-y-5">
                            {choisie ? (
                                <div className="space-y-4 rounded-xl border bg-card p-4" aria-label={nomsDe(unite).join(" + ")}>
                                    <div>
                                        <p className="text-sm font-semibold">{unite.length > 1 ? `${t("Tables", "Tables")} ${nomsDe(unite).join(" + ")}` : choisie.nom}</p>
                                        <p className="text-xs text-muted-foreground">{tablesUnite.reduce((n, x) => n + x.couverts_max, 0)} {t("couverts au plus", "covers at most")}</p>
                                    </div>
                                    <div className="space-y-1.5">
                                        <p className="text-xs font-medium text-muted-foreground">{t("Ce soir", "Tonight")}</p>
                                        {blocsDe(unite).length === 0 ? (
                                            <p className="text-sm text-muted-foreground">{t("Aucune réservation.", "No booking.")}</p>
                                        ) : (
                                            <ul className="space-y-1.5">
                                                {blocsDe(unite).map((b) => (
                                                    <li key={b.id}><button type="button" onClick={() => ouvrir(b.id)} className={`w-full cursor-pointer rounded-md border px-2 py-1.5 text-left text-xs font-medium hover:font-bold focus-visible:outline-2 focus-visible:outline-ring ${CLASSE_BLOC[etatDe(b)]}`}>{infos(b)}</button></li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                    <div className="space-y-1.5">
                                        <p className="text-xs font-medium text-muted-foreground">{t("Assembler avec", "Join with")}</p>
                                        <div className="flex flex-wrap gap-1.5">
                                            {voisines.map((v) => (
                                                <Button key={v.id} variant="outline" size="sm" className="h-8 cursor-pointer" onClick={() => assembler(choisie.id, v.id)}><Link2 className="size-3.5" aria-hidden /> {v.nom}</Button>
                                            ))}
                                        </div>
                                    </div>
                                    {unite.length > 1 && <Button variant="ghost" size="sm" className="cursor-pointer" onClick={() => separer(choisie.id)}><Unlink className="size-3.5" aria-hidden /> {t("Séparer", "Split")}</Button>}
                                    <p className="text-xs text-muted-foreground">{t("Glissez une table pour la déplacer ce soir. Demain, la salle reprend son plan.", "Drag a table to move it tonight. Tomorrow the room goes back to its plan.")}</p>
                                </div>
                            ) : (
                                <div className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">{t("Touchez une table pour voir ses réservations, l'assembler avec une autre ou la déplacer pour ce soir.", "Tap a table to see its bookings, join it to another or move it for tonight.")}</div>
                            )}
                        </aside>
                    </div>
                </>
            ) : (
                <div className="overflow-x-auto">
                    <div className="min-w-[720px]" role="table" aria-label={t("Frise du service de ce soir", "Tonight's service timeline")}>
                        <div className="relative ml-24 h-6 text-[11px] text-muted-foreground">
                            {[18, 19, 20, 21, 22, 23].map((h) => <span key={h} className={`absolute whitespace-nowrap ${h === 23 ? "-translate-x-full" : "-translate-x-1/2"}`} style={{ left: pct(h * 60) }}>{h} h</span>)}
                        </div>
                        {lignes.map((l) => (
                            <div key={l.ids.join("+")} className="flex items-center gap-2 py-1" role="row">
                                <span className="w-[88px] shrink-0 truncate text-sm font-medium">{l.nom} <span className="text-xs font-normal text-muted-foreground">({l.couverts})</span></span>
                                <div className="relative h-9 flex-1 rounded-md bg-muted/60">
                                    {blocsDe(l.ids).map((b) => (
                                        <button key={b.id} type="button" onClick={() => ouvrir(b.id)} aria-label={infos(b)} title={infos(b)} className={`absolute inset-y-0.5 cursor-pointer overflow-hidden rounded-md border px-2 text-left text-xs font-medium whitespace-nowrap hover:font-bold focus-visible:outline-2 focus-visible:outline-ring ${CLASSE_BLOC[etatDe(b)]}`} style={{ left: pct(b.debut), width: `calc(${pct(b.fin)} - ${pct(b.debut)})` }}>
                                            {infos(b)}
                                        </button>
                                    ))}
                                    <span className="absolute inset-y-0 w-px bg-foreground" style={{ left: pct(now) }} aria-hidden />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// --------------------------------------------------------------------------- Planning et détail d'une réservation

function Planning({ rendu, ouvrir }: { rendu: SalleRendue; ouvrir: (id: string) => void }) {
    const t = useTexte();
    const { langue } = useLangue();
    const [portee, setPortee] = useState<"semaine" | "tous">("semaine");
    const liste = rendu.reservations
        .filter((r) => portee === "tous" || ecartDeJours(r.jour, rendu.aujourd_hui) <= 6)
        .sort((a, b) => (a.jour < b.jour ? -1 : a.jour > b.jour ? 1 : a.debut_min - b.debut_min));
    const jours = [...new Set(liste.map((r) => r.jour))];
    return (
        <div className="space-y-5">
            <Tabs value={portee} onValueChange={(v) => setPortee(v as typeof portee)}>
                <TabsList aria-label={t("Période", "Period")}>
                    <TabsTrigger value="semaine">{t("Cette semaine", "This week")}</TabsTrigger>
                    <TabsTrigger value="tous">{t("Tous", "All")}</TabsTrigger>
                </TabsList>
            </Tabs>
            {liste.length === 0 ? (
                <EtatVide cas="premier" icone={CalendarDays} titre={t("Aucune réservation à venir", "No upcoming bookings")} info={t("L'agent prend les réservations selon vos créneaux et votre salle.", "The agent takes bookings based on your slots and floor plan.")} />
            ) : (
                jours.map((j) => {
                    const items = liste.filter((r) => r.jour === j);
                    return (
                        <section key={j} className="space-y-2" aria-label={libelleJour(j, langue === "en")}>
                            <h3 className="flex flex-wrap items-baseline gap-x-3 text-sm font-semibold first-letter:uppercase">
                                {libelleJour(j, langue === "en")}
                                <span className="text-xs font-normal text-muted-foreground">{items.length} {items.length > 1 ? t("réservations", "bookings") : t("réservation", "booking")} · {items.reduce((n, r) => n + r.couverts, 0)} {t("couverts", "covers")}</span>
                            </h3>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>{t("Heure", "Time")}</TableHead><TableHead>{t("Nom", "Name")}</TableHead><TableHead>{t("Couverts", "Covers")}</TableHead><TableHead>{t("Tables", "Tables")}</TableHead><TableHead>{t("Note", "Note")}</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {items.map((r) => (
                                        <LigneCliquable key={r.numero} libelle={r.prenom ?? ""} onOuvrir={() => ouvrir(r.numero)}>
                                            <TableCell className="w-20 text-muted-foreground tabular-nums">{heure(r.debut_min)}</TableCell>
                                            <TableCell className="font-medium">{r.prenom ?? "?"}</TableCell>
                                            <TableCell className="tabular-nums">{r.couverts}</TableCell>
                                            <TableCell>{r.tables.join(" + ")}</TableCell>
                                            <TableCell className="text-muted-foreground">{r.note ?? "–"}</TableCell>
                                        </LigneCliquable>
                                    ))}
                                </TableBody>
                            </Table>
                        </section>
                    );
                })
            )}
        </div>
    );
}

function DetailReservation({ r, rendu, etab, soir, setSoir, editable, fermer, apres }: {
    r: ReservationLue;
    rendu: SalleRendue;
    etab: number;
    soir: Soir;
    setSoir: (s: Soir) => void;
    editable: boolean;
    fermer: () => void;
    apres: () => void;
}) {
    const t = useTexte();
    const { langue } = useLangue();
    const [confirmer, setConfirmer] = useState(false);
    const [changer, setChanger] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const ceSoir = r.jour === rendu.aujourd_hui;
    const ids = soir.tablesDe[r.numero] ?? r.table_ids.map(String);
    const toutes = soir.salles.flatMap((s) => s.tables);
    const nomsDe = (liste: string[]) => liste.map((id) => toutes.find((x) => x.id === id)?.nom ?? id);
    const [choix, setChoix] = useState<string[]>(ids);
    const nom = r.prenom ?? "?";
    const bloc: Bloc = { id: r.numero, prenom: nom, couverts: r.couverts, debut: r.debut_min, fin: r.debut_min + r.duree_minutes, statut: r.statut === "honoree" ? "arrivee" : "reservee" };
    const sous = ceSoir ? `${t("Ce soir", "Tonight")} · ${hh(bloc.debut)}-${hh(bloc.fin)}` : `${libelleJour(r.jour, langue === "en")} · ${heure(r.debut_min)}`;
    const geste = async (statut: "honoree" | "confirmee") => {
        setEnCours(true);
        const res = await poserLeStatut(etab, r.numero, statut);
        setEnCours(false);
        if (res.error) return void notifier.echec(ECHECS.restaurationReservationGeste, { erreur: res.error });
        notifier.succes(statut === "honoree" ? { fr: `${nom} est marquée arrivée.`, en: `${nom} is marked as arrived.` } : { fr: `${nom} n'est plus marquée arrivée.`, en: `${nom} is no longer marked as arrived.` });
        apres();
        fermer();
    };
    const annuler = async () => {
        setEnCours(true);
        const res = await annulerLaReservation(etab, r.numero);
        setEnCours(false);
        setConfirmer(false);
        if (res.error) return void notifier.echec(ECHECS.restaurationReservationGeste, { erreur: res.error });
        notifier.succes({ fr: "Réservation annulée.", en: "Booking cancelled." });
        apres();
        fermer();
    };
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={nom}
            sous={sous}
            valider={null}
            pied={editable ? (
                <>
                    <Button variant="outline" className="cursor-pointer text-destructive" disabled={enCours} onClick={() => setConfirmer(true)}>{t("Annuler la réservation", "Cancel booking")}</Button>
                    <Button className="cursor-pointer" disabled={enCours} onClick={() => void geste(r.statut === "honoree" ? "confirmee" : "honoree")}>{r.statut === "honoree" ? t("Retirer « arrivée »", "Remove “arrived”") : t("Marquer arrivée", "Mark arrived")}</Button>
                </>
            ) : undefined}
        >
            <div className="space-y-5 px-6 py-4">
                {ceSoir && <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm font-medium">{infos(bloc)}</p>}
                <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-2 text-sm">
                    <dt className="text-muted-foreground">{t("Couverts", "Covers")}</dt><dd className="font-semibold">{r.couverts}</dd>
                    <dt className="text-muted-foreground">{t("Tables", "Tables")}</dt>
                    <dd className="flex items-center gap-2">
                        <span className="font-semibold">{nomsDe(ids).join(" + ")}</span>
                        {editable && ceSoir && !changer && <Button variant="ghost" size="sm" className="h-7 cursor-pointer" onClick={() => setChanger(true)}>{t("Changer", "Change")}</Button>}
                    </dd>
                    {r.telephone && (<><dt className="text-muted-foreground">{t("Téléphone", "Phone")}</dt><dd>{r.telephone}</dd></>)}
                    {r.note && (<><dt className="text-muted-foreground">{t("Note", "Note")}</dt><dd>{r.note}</dd></>)}
                    <dt className="text-muted-foreground">{t("Prise par", "Taken by")}</dt>
                    <dd>{r.cree_par === "agent" ? t("l'agent, par téléphone", "the agent, by phone") : r.cree_par === "caisse" ? t("la caisse", "the till") : t("le restaurant", "the restaurant")}</dd>
                </dl>
                {changer && ceSoir && (
                    <div className="space-y-3 rounded-md border p-3">
                        <p className="text-xs text-muted-foreground">{t("Choisissez une ou plusieurs tables. Plusieurs tables = assemblées pour ce soir. Le plan de salle enregistré ne change pas.", "Pick one or more tables. Several tables = joined for tonight. The saved floor plan does not change.")}</p>
                        <div className="flex flex-wrap gap-1.5">
                            {toutes.map((x) => {
                                const on = choix.includes(x.id);
                                return (
                                    <Button key={x.id} size="sm" variant={on ? "default" : "outline"} className="h-8 cursor-pointer" aria-pressed={on} onClick={() => setChoix(on ? choix.filter((c) => c !== x.id) : [...choix, x.id])}>
                                        {x.nom} <span className="text-xs opacity-70">({x.couverts_max})</span>
                                    </Button>
                                );
                            })}
                        </div>
                        <div className="flex justify-end gap-2">
                            <Button variant="ghost" size="sm" className="cursor-pointer" onClick={() => { setChoix(ids); setChanger(false); }}>{t("Annuler", "Cancel")}</Button>
                            <Button
                                size="sm"
                                className="cursor-pointer"
                                disabled={choix.length === 0}
                                onClick={() => {
                                    const groupes = soir.groupes.filter((gr) => !gr.some((x) => choix.includes(x)));
                                    setSoir({ ...soir, tablesDe: { ...soir.tablesDe, [r.numero]: choix }, groupes: choix.length > 1 ? [...groupes, choix] : groupes });
                                    setChanger(false);
                                    notifier.succes({ fr: `${sansCivilite(nom)} : tables ${nomsDe(choix).join(" + ")} pour ce soir.`, en: `${sansCivilite(nom)}: tables ${nomsDe(choix).join(" + ")} tonight.` });
                                }}
                            >
                                {t("Valider", "Apply")}
                            </Button>
                        </div>
                    </div>
                )}
            </div>
            {confirmer && (
                <Confirmer
                    titre={t("Annuler cette réservation ?", "Cancel this booking?")}
                    texte={t("La table se libère tout de suite. Le client est prévenu par SMS si l'envoi est allumé (Réglages restaurant › Envois).", "The table is freed at once. The customer is told by text if the message is switched on (Restaurant settings › Messages).")}
                    bouton={t("Annuler la réservation", "Cancel booking")}
                    fermer={() => setConfirmer(false)}
                    valider={() => void annuler()}
                />
            )}
        </FenetreOnglets>
    );
}

// --------------------------------------------------------------------------- l'onglet

/** L'écran entier : posé tel quel par l'onglet Salle du fork. ``editable`` : le compte peut régler le plan et gérer les réservations. */
function ContenuSalle({ etab, rendu, editable, relire, poser }: { etab: number; rendu: SalleRendue; editable: boolean; relire: () => void; poser: (r: SalleRendue) => void }) {
    const t = useTexte();
    const [vue, setVue] = useState<"jour" | "salles" | "planning">("jour");
    const [ouvert, setOuvert] = useState<string | null>(null);
    const [regler, setRegler] = useState<null | "plan" | "creneaux">(null);
    const [soir, setSoirLocal] = useState<Soir | null>(null);
    const effectif = useMemo(() => soir ?? soirDepart(rendu), [soir, rendu]);
    const resa = ouvert ? rendu.reservations.find((x) => x.numero === ouvert) ?? null : null;
    return (
        <div className="@container space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <Tabs value={vue} onValueChange={(v) => setVue(v as typeof vue)}>
                    <TabsList aria-label={t("Vue", "View")}>
                        <TabsTrigger value="jour">{t("Jour", "Day")}</TabsTrigger>
                        <TabsTrigger value="salles">{t("Salles", "Rooms")}</TabsTrigger>
                        <TabsTrigger value="planning">{t("Planning", "Schedule")}</TabsTrigger>
                    </TabsList>
                </Tabs>
                {editable && (
                    <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setRegler("plan")} data-regler>
                        <Settings2 className="size-4" aria-hidden /> {t("Régler", "Settings")}
                    </Button>
                )}
            </div>
            {vue === "jour" && <Service key="frise" rendu={rendu} vue="frise" soir={effectif} setSoir={setSoirLocal} ouvrir={setOuvert} />}
            {vue === "salles" && <Service key="plan" rendu={rendu} vue="plan" soir={effectif} setSoir={setSoirLocal} ouvrir={setOuvert} />}
            {vue === "planning" && <Planning rendu={rendu} ouvrir={setOuvert} />}
            {resa && <DetailReservation key={resa.numero} r={resa} rendu={rendu} etab={etab} soir={effectif} setSoir={setSoirLocal} editable={editable} fermer={() => setOuvert(null)} apres={relire} />}
            {regler && (
                <GrandeFenetre
                    titre={t("Régler les réservations", "Booking settings")}
                    sous={t("Le plan de la salle, les créneaux réservables, la durée d'un repas et les règles.", "The floor plan, bookable slots, meal length and rules.")}
                    fermer={() => setRegler(null)}
                    onglets={[{ cle: "plan", libelle: t("Plan de salle", "Floor plan") }, { cle: "creneaux", libelle: t("Créneaux et durées", "Slots and lengths") }]}
                    onglet={regler}
                    choisir={(c) => setRegler(c as "plan" | "creneaux")}
                >
                    <div className="@container">
                        {regler === "plan" && <Configurateur key={`plan-${etab}`} etab={etab} rendu={rendu} editable={editable} apres={(r) => { poser(r); setSoirLocal(null); }} />}
                        {regler === "creneaux" && <Creneaux key={`creneaux-${etab}`} etab={etab} rendu={rendu} editable={editable} apres={poser} />}
                    </div>
                </GrandeFenetre>
            )}
        </div>
    );
}

export function OngletSalle() {
    const t = useTexte();
    const { etab } = useModuleRestauration();
    const { donnee, etat, relire, poser } = useCharge(etab === null ? null : () => lireLaSalle(etab), String(etab), ECHECS.restaurationSalle);
    return (
        <EcranDonnees etat={etab === null ? "pret" : etat} relire={() => void relire()} vide={etab === null} titreVide={t("Aucun établissement", "No site")}>
            <div className="flex flex-wrap items-center gap-3 pt-2"><SelecteurEtab /></div>
            {etab !== null && donnee && <ContenuSalle etab={etab} rendu={donnee} editable relire={() => void relire()} poser={poser} />}
        </EcranDonnees>
    );
}
