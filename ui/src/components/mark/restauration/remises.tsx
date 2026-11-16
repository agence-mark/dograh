"use client";

/**
 * [.mark] Module Restauration, lot 13 (F7) : l'onglet Remises de la page Entreprise, repris de la maquette (`remises.tsx`) et branché sur les routes du fork
 * (``GET/POST …/remises``, ``PUT/DELETE …/remises/{id}``, ``POST …/remises/{id}/etat``).
 *
 * Douze mécanismes (E-52). La personne règle des nombres et choisit une cible dans la carte ; l'écran écrit la forme que le comptoir sait lire (``declencheur``,
 * ``effet``, ``perimetre``, ``moment``, ``limite``), jamais un JSON libre. Le calcul exact est celui du comptoir ; l'aperçu du total ci-dessous n'est qu'un
 * panier d'exemple. Création en trois étapes dans le panneau de droite : Quoi, Quand, Comment l'agent le dit. Liste ou frise ; résultats d'après les commandes
 * gardées. Une remise que la caisse porte se lit seulement.
 */
import { ArrowUpFromLine, Check, Clock, Gift, Heart, Layers, Pause, Percent, Play, Plus, ShoppingBasket, Sparkles, Tag, Trash2, Users, UtensilsCrossed } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { ECHECS } from "../notifications/phrases-echec";
import { Champs, FenetreOnglets, LigneChamp as Ligne, Section } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Info, PointEtat } from "../studio/marques";
import { Cellule, Ligne as LigneT, Tableau } from "../studio/tableau";
import { Confirmer, EcranDonnees, euros, LigneSource, Segment3, SelecteurEtab, useTexte } from "./commun";
import { useCharge, useModuleRestauration } from "./contexte";
import { lireLaCarte } from "./donnees";
import {
    changerLEtatDUneRemise, creerUneRemise, type EtatRemise, lireLesRemises, type Mecanisme, MECANISMES, modifierUneRemise, type RemiseEcrite, type RemiseLue,
    type RemisesRendues, supprimerUneRemise,
} from "./donnees-salle";

const ICONES: Record<Mecanisme, typeof Gift> = {
    pourcentage: Percent, montant: Tag, x_achetes_y_offert: Gift, deuxieme_moitie_prix: Percent, prix_du_jour: Tag, seuil_panier: ShoppingBasket, passage_en_menu: UtensilsCrossed,
    taille_superieure: ArrowUpFromLine, offre_famille: Users, creneau: Clock, nouveaute: Sparkles, fidelite: Heart,
};
const NOM: Record<Mecanisme, { fr: string; en: string; exemple: { fr: string; en: string } }> = {
    pourcentage: { fr: "Pourcentage", en: "Percentage", exemple: { fr: "-10 % sur toute la commande", en: "10% off the whole order" } },
    montant: { fr: "Montant", en: "Amount off", exemple: { fr: "-3 € sur la commande", en: "€3 off the order" } },
    x_achetes_y_offert: { fr: "X achetés, Y offert", en: "Buy X, get Y free", exemple: { fr: "3 pizzas achetées, la 4e offerte", en: "Buy 3 pizzas, the 4th is free" } },
    deuxieme_moitie_prix: { fr: "Le deuxième à moitié prix", en: "Second at half price", exemple: { fr: "La 2e pizza à moitié prix", en: "The 2nd pizza at half price" } },
    prix_du_jour: { fr: "Prix du jour", en: "Price of the day", exemple: { fr: "La Regina à 9 € aujourd'hui", en: "The Regina at €9 today" } },
    seuil_panier: { fr: "Seuil de panier", en: "Basket threshold", exemple: { fr: "-10 % dès 30 € de commande", en: "10% off from €30" } },
    passage_en_menu: { fr: "Passage en menu", en: "Meal deal", exemple: { fr: "Une pizza et une boisson à 12 €", en: "A pizza and a drink for €12" } },
    taille_superieure: { fr: "Taille supérieure", en: "Size upgrade", exemple: { fr: "La grande au prix de la moyenne", en: "The large at the medium's price" } },
    offre_famille: { fr: "Offre famille", en: "Family offer", exemple: { fr: "Deux pizzas, une salade et deux boissons à 35 €", en: "Two pizzas, a salad and two drinks for €35" } },
    creneau: { fr: "Créneau", en: "Time slot", exemple: { fr: "-15 % de 18 h à 19 h", en: "15% off from 6 pm to 7 pm" } },
    nouveaute: { fr: "Nouveauté", en: "New item", exemple: { fr: "La nouvelle pizza à prix de lancement", en: "The new pizza at a launch price" } },
    fidelite: { fr: "Fidélité", en: "Loyalty", exemple: { fr: "La 10e commande, un dessert offert", en: "On the 10th order, a free dessert" } },
};
const ETATS: Record<EtatRemise | "programmee", { fr: string; en: string; point: "publie" | "brouillon" | "attente" | "fini" }> = {
    active: { fr: "Active", en: "Active", point: "publie" }, programmee: { fr: "Programmée", en: "Scheduled", point: "brouillon" }, brouillon: { fr: "Brouillon", en: "Draft", point: "brouillon" },
    suspendue: { fr: "En pause", en: "Paused", point: "attente" }, terminee: { fr: "Terminée", en: "Ended", point: "fini" },
};
const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

// --------------------------------------------------------------------------- les réglages d'une remise, vers et depuis ce que la base garde

interface Cible {
    categories: string[];
    codes: string[];
}
interface Case {
    categorie: string;
    quantite: number;
}
/** Ce que l'écran règle, par mécanisme. Les nombres restent des textes tapés ; l'enregistrement les convertit (euros en centimes). */
interface Reglage {
    mecanisme: Mecanisme;
    a: string;
    b: string;
    cible: Cible;
    cases: Case[];
    effetSeuil: "pourcentage" | "montant";
}
const CIBLE_VIDE: Cible = { categories: [], codes: [] };
const DEFAUT: Record<Mecanisme, { a: string; b: string }> = {
    pourcentage: { a: "10", b: "" }, montant: { a: "3", b: "" }, x_achetes_y_offert: { a: "3", b: "1" }, deuxieme_moitie_prix: { a: "50", b: "2" }, prix_du_jour: { a: "9", b: "" },
    seuil_panier: { a: "30", b: "10" }, passage_en_menu: { a: "12", b: "" }, taille_superieure: { a: "", b: "" }, offre_famille: { a: "35", b: "" }, creneau: { a: "15", b: "" },
    nouveaute: { a: "9", b: "" }, fidelite: { a: "10", b: "100" },
};
const nombre = (s: string) => Number(s.replace(",", "."));
const enCentimes = (s: string) => Math.round(nombre(s) * 100);
const aCible = (c: Cible) => c.categories.length + c.codes.length > 0;
const perimetreDe = (c: Cible, modes?: string[]) => ({ ...(c.codes.length ? { codes: c.codes } : {}), ...(c.categories.length ? { categories: c.categories } : {}), ...(modes?.length ? { modes } : {}) });

/** Les réglages vers la forme de la base (colonnes JSON de ``resto_remise``). Lève un texte clair quand il manque quelque chose : jamais une remise annoncée et non appliquée. */
export function versLaBase(r: Reglage, modes: string[], t: (fr: string, en: string) => string): Pick<RemiseEcrite, "declencheur" | "effet" | "perimetre"> {
    const exiger = (ok: boolean, fr: string, en: string) => { if (!ok) throw new Error(t(fr, en)); };
    const a = nombre(r.a), b = nombre(r.b);
    const p = (ok: boolean) => exiger(ok, "Le pourcentage doit être entre 0,5 et 100.", "The percentage must be between 0.5 and 100.");
    switch (r.mecanisme) {
        case "pourcentage": case "creneau": p(a >= 0.5 && a <= 100); return { declencheur: {}, effet: { pourcentage: a }, perimetre: perimetreDe(r.cible, modes) };
        case "montant": exiger(a > 0, "Le montant doit être positif.", "The amount must be positive."); return { declencheur: {}, effet: { montant: enCentimes(r.a) }, perimetre: perimetreDe(r.cible, modes) };
        case "x_achetes_y_offert":
            exiger(Number.isInteger(a) && a >= 1 && Number.isInteger(b) && b >= 1, "Les nombres d'articles doivent être entiers, au moins 1.", "Item counts must be whole numbers, at least 1.");
            return { declencheur: { achetes: a }, effet: { offerts: b }, perimetre: perimetreDe(r.cible, modes) };
        case "deuxieme_moitie_prix":
            p(a >= 0.5 && a <= 100); exiger(Number.isInteger(b) && b >= 2, "Le rang doit être un entier, au moins 2.", "The rank must be a whole number, at least 2.");
            return { declencheur: { rang: b }, effet: { pourcentage: a }, perimetre: perimetreDe(r.cible, modes) };
        case "prix_du_jour": case "nouveaute":
            exiger(a > 0 && aCible(r.cible), "Choisissez l'article et son prix.", "Choose the item and its price."); return { declencheur: {}, effet: { prix: enCentimes(r.a) }, perimetre: perimetreDe(r.cible, modes) };
        case "seuil_panier":
            exiger(a > 0 && b > 0, "Le seuil et l'avantage doivent être positifs.", "The threshold and the benefit must be positive.");
            if (r.effetSeuil === "pourcentage") p(b >= 0.5 && b <= 100);
            return { declencheur: { minimum: enCentimes(r.a) }, effet: r.effetSeuil === "pourcentage" ? { pourcentage: b } : { montant: enCentimes(r.b) }, perimetre: perimetreDe(CIBLE_VIDE, modes) };
        case "passage_en_menu": case "offre_famille":
            exiger(r.cases.length >= 1 && r.cases.every((c) => c.categorie && c.quantite >= 1) && a > 0, "Composez l'offre (une catégorie par case) et fixez son prix.", "Build the offer (one category per slot) and set its price.");
            return { declencheur: { composition: r.cases.map((c) => ({ quantite: c.quantite, perimetre: { categories: [c.categorie] } })) }, effet: { prix: enCentimes(r.a) }, perimetre: perimetreDe(CIBLE_VIDE, modes) };
        case "taille_superieure":
            exiger(r.cible.codes.length >= 1 && !!r.a.trim(), "Choisissez l'article offert en taille supérieure et l'article dont il prend le prix.", "Choose the upgraded item and the item whose price it takes.");
            return { declencheur: {}, effet: { prix_de: r.a.trim() }, perimetre: perimetreDe(r.cible, modes) };
        case "fidelite":
            exiger(Number.isInteger(a) && a >= 2, "Le nombre de commandes doit être un entier, au moins 2.", "The number of orders must be a whole number, at least 2.");
            exiger(b >= 0.5 && b <= 100, "Le pourcentage doit être entre 0,5 et 100.", "The percentage must be between 0.5 and 100.");
            return { declencheur: { tous_les: a }, effet: { pourcentage: b }, perimetre: perimetreDe(CIBLE_VIDE, modes) };
    }
}

const liste = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);
const objet = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
/** Les réglages que la ligne dit, ou ``null`` : une forme que cet écran n'écrit pas (la caisse, .mark) reste en lecture seule. */
export function depuisLaBase(l: RemiseLue): { reglage: Reglage; modes: string[] } | null {
    const d = objet(l.declencheur), e = objet(l.effet), per = objet(l.perimetre);
    const cible: Cible = { categories: liste(per.categories), codes: liste(per.codes) };
    const modes = liste(per.modes);
    const m = l.mecanisme as Mecanisme;
    const base = { mecanisme: m, cible, cases: [] as Case[], effetSeuil: "pourcentage" as const };
    const n = (v: unknown) => (typeof v === "number" ? String(v).replace(".", ",") : "");
    const eu = (v: unknown) => (typeof v === "number" ? String(v / 100).replace(".", ",") : "");
    switch (m) {
        case "pourcentage": case "creneau": return typeof e.pourcentage === "number" ? { reglage: { ...base, a: n(e.pourcentage), b: "" }, modes } : null;
        case "montant": return typeof e.montant === "number" ? { reglage: { ...base, a: eu(e.montant), b: "" }, modes } : null;
        case "x_achetes_y_offert": return typeof d.achetes === "number" && typeof e.offerts === "number" ? { reglage: { ...base, a: n(d.achetes), b: n(e.offerts) }, modes } : null;
        case "deuxieme_moitie_prix": return typeof e.pourcentage === "number" && typeof d.rang === "number" ? { reglage: { ...base, a: n(e.pourcentage), b: n(d.rang) }, modes } : null;
        case "prix_du_jour": case "nouveaute": return typeof e.prix === "number" ? { reglage: { ...base, a: eu(e.prix), b: "" }, modes } : null;
        case "seuil_panier":
            if (typeof d.minimum !== "number") return null;
            if (typeof e.pourcentage === "number") return { reglage: { ...base, a: eu(d.minimum), b: n(e.pourcentage), effetSeuil: "pourcentage" }, modes };
            return typeof e.montant === "number" ? { reglage: { ...base, a: eu(d.minimum), b: eu(e.montant), effetSeuil: "montant" }, modes } : null;
        case "passage_en_menu": case "offre_famille": {
            const cases = Array.isArray(d.composition) ? d.composition.map((c) => ({ categorie: liste(objet(objet(c).perimetre).categories)[0] ?? "", quantite: Number(objet(c).quantite) || 1 })) : [];
            return typeof e.prix === "number" && cases.length ? { reglage: { ...base, a: eu(e.prix), b: "", cases }, modes } : null;
        }
        case "taille_superieure": return typeof e.prix_de === "string" ? { reglage: { ...base, a: e.prix_de, b: "" }, modes } : null;
        case "fidelite": return typeof d.tous_les === "number" && typeof e.pourcentage === "number" ? { reglage: { ...base, a: n(d.tous_les), b: n(e.pourcentage) }, modes } : null;
        default: return null;
    }
}

// --------------------------------------------------------------------------- l'aperçu du total (un panier d'exemple, jamais une commande)

const PANIER = [{ n: "Pizza", c: 1250 }, { n: "Pizza", c: 1250 }, { n: "Boisson", c: 250 }];
const TOTAL = PANIER.reduce((s, l) => s + l.c, 0);
function apercu(r: Reglage): number {
    const a = nombre(r.a) || 0, b = nombre(r.b) || 0;
    const moins = (x: number) => Math.max(0, Math.min(TOTAL, Math.round(x)));
    switch (r.mecanisme) {
        case "pourcentage": case "creneau": return moins((TOTAL * a) / 100);
        case "montant": return moins(a * 100);
        case "x_achetes_y_offert": return a <= 2 ? moins(1250 * b) : 0;
        case "deuxieme_moitie_prix": return b <= 2 ? moins((1250 * a) / 100) : 0;
        case "prix_du_jour": case "nouveaute": return moins(1250 - a * 100);
        case "seuil_panier": return TOTAL >= a * 100 ? moins(r.effetSeuil === "pourcentage" ? (TOTAL * b) / 100 : b * 100) : 0;
        case "passage_en_menu": case "offre_famille": return moins(TOTAL - a * 100);
        default: return 0;
    }
}

// --------------------------------------------------------------------------- l'écran

const nomMec = (id: string, langue: "fr" | "en") => (NOM[id as Mecanisme] ? NOM[id as Mecanisme][langue] : id);
const jourLocal = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("sv-SE") : null);
const aujourdhui = () => new Date().toLocaleDateString("sv-SE");
const etatAffiche = (r: RemiseLue): EtatRemise | "programmee" => (r.etat === "active" && r.debut && jourLocal(r.debut)! > aujourdhui() ? "programmee" : r.etat);

export function OngletRemises() {
    const t = useTexte();
    const { langue } = useLangue();
    const { etab } = useModuleRestauration();
    const { donnee, etat, relire, poser } = useCharge(etab === null ? null : () => lireLesRemises(etab), String(etab), ECHECS.restaurationRemises);
    const carte = useCharge(etab === null ? null : () => lireLaCarte(etab), `carte-${etab}`, ECHECS.restaurationCarte);
    const [vue, setVue] = useState<"liste" | "frise">("liste");
    const [detail, setDetail] = useState<number | null>(null);
    const [creer, setCreer] = useState<null | { depart?: RemiseLue }>(null);
    const choisie = donnee?.remises.find((r) => r.id === detail) ?? null;
    const choix = useMemo(
        () => ({
            categories: (carte.donnee?.categories ?? []).map((c) => ({ ref: c.id, nom: c.nom })),
            produits: (carte.donnee?.produits ?? []).map((p) => ({ code: p.declinaisons[0]?.code_caisse ?? p.id, nom: p.nom })),
        }),
        [carte.donnee],
    );
    const resume = (r: RemiseLue) => {
        const lu = depuisLaBase(r);
        return lu ? resumeDe(lu.reglage, choix, langue) : t("Réglée dans la caisse", "Set in the till");
    };
    return (
        <EcranDonnees etat={etab === null ? "pret" : etat} relire={() => void relire()} iconeVide={Percent} vide={etab === null} titreVide={t("Aucun établissement", "No site")}>
            <div className="flex flex-wrap items-center gap-3 pt-2">
                <SelecteurEtab />
                <span className="flex-1" />
                <Segment3 valeur={vue} changer={setVue} options={[{ v: "liste", l: t("Liste", "List") }, { v: "frise", l: t("Frise", "Timeline") }]} />
                <Button size="sm" className="cursor-pointer" disabled={!donnee || donnee.lecture_seule} onClick={() => setCreer({})}><Plus className="size-3.5" /> {t("Remise", "Discount")}</Button>
            </div>
            {donnee && (
                <LigneSource
                    caisse={donnee.lecture_seule}
                    prise={donnee.prise === "hubrise" ? "HubRise" : donnee.prise}
                    objet={t("Remises gérées", "Discounts managed")}
                />
            )}
            {donnee && donnee.remises.length === 0 ? (
                <p className="py-10 text-center text-sm text-muted-foreground">{t("Aucune remise pour l'instant. Une remise programmée s'allume et s'éteint toute seule aux dates choisies.", "No discount yet. A scheduled discount switches on and off by itself on the chosen dates.")}</p>
            ) : donnee && vue === "liste" ? (
                <Tableau colonnes={[{ titre: t("Remise", "Discount") }, { titre: t("Quand", "When"), secondaire: 3 }, { titre: t("État", "Status") }, { titre: t("Dite", "Mentioned"), droite: true, secondaire: 2 }, { titre: t("Acceptée", "Accepted"), droite: true, secondaire: 1 }, { titre: t("CA", "Revenue"), droite: true }]}>
                    {donnee.remises.map((r) => {
                        const ea = etatAffiche(r);
                        return (
                            <LigneT key={r.id} onClick={() => setDetail(r.id)}>
                                <Cellule principale sous={`${nomMec(r.mecanisme, langue)} · ${resume(r)}`}>{r.nom}</Cellule>
                                <Cellule>{quand(r, t)}</Cellule>
                                <Cellule><PointEtat etat={ETATS[ea].point}>{ETATS[ea][langue]}</PointEtat></Cellule>
                                <Cellule droite>{r.dite}</Cellule>
                                <Cellule droite>{r.acceptee}</Cellule>
                                <Cellule droite className="whitespace-nowrap">{euros(r.ca_centimes)}</Cellule>
                            </LigneT>
                        );
                    })}
                </Tableau>
            ) : donnee ? (
                <Frise liste={donnee.remises} ouvrir={setDetail} />
            ) : null}
            {choisie && donnee && (
                <PanneauDetail
                    key={choisie.id}
                    r={choisie}
                    etab={etab!}
                    lectureSeule={donnee.lecture_seule}
                    resume={resume(choisie)}
                    fermer={() => setDetail(null)}
                    poser={poser}
                    modifier={() => { setCreer({ depart: choisie }); setDetail(null); }}
                />
            )}
            {creer && etab !== null && <CreationRemise key={creer.depart?.id ?? "nouvelle"} etab={etab} depart={creer.depart} choix={choix} fermer={() => setCreer(null)} poser={poser} />}
        </EcranDonnees>
    );
}

const quand = (r: RemiseLue, t: (fr: string, en: string) => string) => {
    const m = objet(r.moment);
    const jours = Array.isArray(m.jours) ? (m.jours as number[]).map((j) => JOURS[j - 1]).filter(Boolean).join(", ") : t("tous les jours", "every day");
    const d = jourLocal(r.debut), f = jourLocal(r.fin);
    return `${jours}${d || f ? ` · ${d ?? "…"} › ${f ?? "…"}` : ""}`;
};

function resumeDe(r: Reglage, choix: { categories: { ref: string; nom: string }[]; produits: { code: string; nom: string }[] }, langue: "fr" | "en"): string {
    const t = (fr: string, en: string) => (langue === "fr" ? fr : en);
    const cible = r.cible.codes[0] ? choix.produits.find((p) => p.code === r.cible.codes[0])?.nom ?? r.cible.codes[0] : r.cible.categories[0] ? choix.categories.find((c) => c.ref === r.cible.categories[0])?.nom ?? r.cible.categories[0] : t("tout le panier", "the whole basket");
    const a = r.a, b = r.b;
    switch (r.mecanisme) {
        case "pourcentage": case "creneau": return `-${a} % · ${cible}`;
        case "montant": return `-${a} € · ${cible}`;
        case "x_achetes_y_offert": return t(`${a} achetés = ${b} offert(s) · ${cible}`, `buy ${a}, get ${b} free · ${cible}`);
        case "deuxieme_moitie_prix": return t(`-${a} % sur le ${b}e · ${cible}`, `${a}% off the ${b}th · ${cible}`);
        case "prix_du_jour": case "nouveaute": return t(`${cible} à ${a} €`, `${cible} at €${a}`);
        case "seuil_panier": return t(`dès ${a} € : ${r.effetSeuil === "pourcentage" ? `-${b} %` : `-${b} €`}`, `from €${a}: ${r.effetSeuil === "pourcentage" ? `-${b}%` : `-€${b}`}`);
        case "passage_en_menu": case "offre_famille": return t(`${r.cases.map((c) => `${c.quantite} ${choix.categories.find((x) => x.ref === c.categorie)?.nom ?? c.categorie}`).join(" + ")} pour ${a} €`, `${r.cases.map((c) => `${c.quantite} ${choix.categories.find((x) => x.ref === c.categorie)?.nom ?? c.categorie}`).join(" + ")} for €${a}`);
        case "taille_superieure": return t(`${cible} au prix de ${choix.produits.find((p) => p.code === a)?.nom ?? a}`, `${cible} at the price of ${choix.produits.find((p) => p.code === a)?.nom ?? a}`);
        case "fidelite": return t(`-${b} % à chaque ${a}e commande`, `${b}% off every ${a}th order`);
    }
}

// Frise : 90 jours autour d'aujourd'hui, une barre par remise, trait noir pour aujourd'hui.
function Frise({ liste, ouvrir }: { liste: RemiseLue[]; ouvrir: (id: number) => void }) {
    const t = useTexte();
    const { langue } = useLangue();
    const D = -50, F = 40, pct = (j: number) => ((Math.max(D, Math.min(F, j)) - D) / (F - D)) * 100;
    const ecart = (iso: string | null, defaut: number) => (iso ? Math.round((Date.parse(`${jourLocal(iso)}T12:00:00Z`) - Date.parse(`${aujourdhui()}T12:00:00Z`)) / 86_400_000) : defaut);
    const couleur = (e: string) => (e === "active" ? ["var(--marque-succes)", "var(--point-publie)"] : e === "programmee" ? ["var(--acc-soft)", "var(--acc)"] : ["var(--muted)", "var(--muted-foreground)"]);
    return (
        <div className="space-y-2">
            <div className="grid grid-cols-[200px_1fr] text-xs text-muted-foreground">
                <span />
                <div className="relative h-5">{[-42, -28, -14, 0, 14, 28].map((j) => <span key={j} className="absolute -translate-x-1/2" style={{ left: `${pct(j)}%` }}>{j === 0 ? t("aujourd'hui", "today") : `${j > 0 ? "+" : ""}${j} j`}</span>)}</div>
            </div>
            <div className="divide-y border-y">
                {liste.map((r) => {
                    const ea = etatAffiche(r);
                    const [fond, trait] = couleur(ea);
                    const d = ecart(r.debut, D), f = ecart(r.fin, F);
                    return (
                        <div key={r.id} className="grid grid-cols-[200px_1fr] items-center">
                            <button type="button" onClick={() => ouvrir(r.id)} className="cursor-pointer truncate py-2.5 pr-3 text-left text-sm font-medium hover:font-semibold">
                                {r.nom}
                                <span className="block text-xs font-normal text-muted-foreground">{nomMec(r.mecanisme, langue)}</span>
                            </button>
                            <div className="relative h-8">
                                <span className="absolute inset-y-0 border-l-2 border-foreground" style={{ left: `${pct(0)}%` }} />
                                <button type="button" onClick={() => ouvrir(r.id)} aria-label={r.nom} className="absolute top-1.5 h-5 cursor-pointer rounded-full border" style={{ left: `${pct(d)}%`, width: `${Math.max(1.5, pct(f) - pct(d))}%`, background: fond, borderColor: trait, borderStyle: r.etat === "suspendue" ? "dashed" : "solid" }} />
                            </div>
                        </div>
                    );
                })}
            </div>
            <p className="text-xs text-muted-foreground">{t("Vert : active ; bleu : programmée ; tireté : en pause ; gris : terminée ou brouillon.", "Green: active; blue: scheduled; dashed: paused; grey: ended or draft.")}</p>
        </div>
    );
}

function PanneauDetail({ r, etab, lectureSeule, resume, fermer, poser, modifier }: {
    r: RemiseLue;
    etab: number;
    lectureSeule: boolean;
    resume: string;
    fermer: () => void;
    poser: (d: RemisesRendues) => void;
    modifier: () => void;
}) {
    const t = useTexte();
    const { langue } = useLangue();
    const [sup, setSup] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const ea = etatAffiche(r);
    const modifiable = !lectureSeule && (r.source === "portail" || r.source === "agent") && r.etat !== "terminee";
    const aller = async (etat: EtatRemise, texte: { fr: string; en: string }) => {
        setEnCours(true);
        const res = await changerLEtatDUneRemise(etab, r.id, etat);
        setEnCours(false);
        if (res.error || !res.data) return void notifier.echec(ECHECS.restaurationRemiseEnregistrer, { erreur: res.error });
        poser(res.data);
        notifier.succes(texte);
    };
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={r.nom}
            sous={<PointEtat etat={ETATS[ea].point}>{ETATS[ea][langue]}</PointEtat>}
            valider={null}
            pied={
                <>
                    {modifiable && r.etat !== "terminee" && <Button variant="ghost" size="sm" className="mr-auto cursor-pointer text-destructive" onClick={() => setSup(true)}><Trash2 className="size-3.5" /> {t("Supprimer", "Delete")}</Button>}
                    {modifiable && <Button variant="outline" className="cursor-pointer" disabled={enCours} onClick={modifier}>{t("Modifier", "Edit")}</Button>}
                    {modifiable && r.etat === "brouillon" && <Button className="cursor-pointer" disabled={enCours} onClick={() => void aller("active", { fr: "Remise allumée : l'agent peut la proposer.", en: "Discount switched on: the agent may offer it." })}><Play className="size-3.5" /> {t("Allumer", "Switch on")}</Button>}
                    {modifiable && r.etat === "active" && <Button variant="outline" className="cursor-pointer" disabled={enCours} onClick={() => void aller("suspendue", { fr: "Remise mise en pause : l'agent n'en parle plus.", en: "Discount paused: the agent stops mentioning it." })}><Pause className="size-3.5" /> {t("Mettre en pause", "Pause")}</Button>}
                    {modifiable && r.etat === "suspendue" && <Button variant="outline" className="cursor-pointer" disabled={enCours} onClick={() => void aller("active", { fr: "Remise reprise.", en: "Discount resumed." })}><Play className="size-3.5" /> {t("Reprendre", "Resume")}</Button>}
                    {modifiable && (r.etat === "active" || r.etat === "suspendue") && <Button variant="outline" className="cursor-pointer" disabled={enCours} onClick={() => void aller("terminee", { fr: "Remise terminée.", en: "Discount ended." })}>{t("Terminer", "End")}</Button>}
                </>
            }
        >
            <div className="space-y-5 px-6 py-4">
                <Section titre={t("Résultats", "Results")} info={t("D'après les commandes gardées (30 jours) qui portent cette remise : jamais une estimation.", "From the kept orders (30 days) that carry this discount: never an estimate.")}>
                    <div className="grid grid-cols-3 gap-3 text-center">
                        {[[t("Dite", "Mentioned"), r.dite], [t("Acceptée", "Accepted"), `${r.acceptee}${r.dite ? ` (${Math.round((r.acceptee / r.dite) * 100)} %)` : ""}`], [t("Utilisations", "Uses"), r.utilisations], [t("CA", "Revenue"), euros(r.ca_centimes)], [t("Remise", "Discount"), euros(r.remise_centimes)]].map(([l, v]) => (
                            <div key={String(l)} className="rounded-xl border p-3"><p className="text-xl font-semibold tabular-nums">{v}</p><p className="text-xs text-muted-foreground">{l}</p></div>
                        ))}
                    </div>
                </Section>
                <Section titre={t("La remise", "The discount")}>
                    <Champs>
                        <Ligne libelle={t("Mécanisme", "Mechanism")}><span className="text-sm text-muted-foreground">{nomMec(r.mecanisme, langue)}</span></Ligne>
                        <Ligne libelle={t("Effet", "Effect")}><span className="text-sm text-muted-foreground">{resume}</span></Ligne>
                        <Ligne libelle={t("Quand", "When")}><span className="text-sm text-muted-foreground">{quand(r, t)}</span></Ligne>
                        <Ligne libelle={t("Cumul", "Stacking")}><span className="text-sm text-muted-foreground">{r.cumul === "cumulable" ? t("cumulable", "combinable") : t("exclusive", "exclusive")}</span></Ligne>
                        {r.source !== "portail" && <Ligne libelle={t("Source", "Source")}><span className="text-sm text-muted-foreground">{r.source === "caisse" ? t("la caisse", "the till") : r.source}</span></Ligne>}
                        {r.phrase && <Ligne libelle={t("Ce que dit l'agent", "What the agent says")}><span className="rounded-lg bg-muted px-3 py-2 text-sm">« {r.phrase} »</span></Ligne>}
                    </Champs>
                </Section>
            </div>
            {sup && (
                <Confirmer
                    titre={t("Supprimer cette remise ?", "Delete this discount?")}
                    texte={t("L'historique des changements la garde. Les commandes déjà prises gardent leur remise.", "The change history keeps it. Orders already taken keep their discount.")}
                    bouton={t("Supprimer", "Delete")}
                    fermer={() => setSup(false)}
                    valider={() => void supprimerUneRemise(etab, r.id).then((res) => {
                        if (res.error || !res.data) return void notifier.echec(ECHECS.restaurationRemiseEnregistrer, { erreur: res.error });
                        poser(res.data);
                        notifier.succes({ fr: "Remise supprimée.", en: "Discount deleted." });
                        fermer();
                    })}
                />
            )}
        </FenetreOnglets>
    );
}

// Création en 3 étapes dans le panneau de droite : Quoi, Quand, Comment l'agent le dit.
function CreationRemise({ etab, depart, choix, fermer, poser }: {
    etab: number;
    depart?: RemiseLue;
    choix: { categories: { ref: string; nom: string }[]; produits: { code: string; nom: string }[] };
    fermer: () => void;
    poser: (d: RemisesRendues) => void;
}) {
    const t = useTexte();
    const { langue } = useLangue();
    const lu = depart ? depuisLaBase(depart) : null;
    const [etape, setEtape] = useState(0);
    const [reglage, setReglage] = useState<Reglage>(lu?.reglage ?? { mecanisme: "pourcentage", ...DEFAUT.pourcentage, cible: CIBLE_VIDE, cases: [], effetSeuil: "pourcentage" });
    const [modes, setModes] = useState<string[]>(lu?.modes ?? []);
    const [nom, setNom] = useState(depart?.nom ?? "");
    const moment = objet(depart?.moment);
    const [jours, setJours] = useState<number[]>(Array.isArray(moment.jours) ? (moment.jours as number[]) : []);
    const heures = Array.isArray(moment.heures) && Array.isArray(moment.heures[0]) ? (moment.heures[0] as string[]) : ["18:00", "19:00"];
    const [heureDe, setHeureDe] = useState(heures[0]);
    const [heureA, setHeureA] = useState(heures[1]);
    const [debut, setDebut] = useState(jourLocal(depart?.debut ?? null) ?? "");
    const [fin, setFin] = useState(jourLocal(depart?.fin ?? null) ?? "");
    const [cumul, setCumul] = useState(depart?.cumul === "cumulable");
    const [phrase, setPhrase] = useState(depart?.phrase ?? "");
    const [max, setMax] = useState(String(objet(depart?.limite).max_par_achat ?? ""));
    const [enCours, setEnCours] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);
    const m = reglage.mecanisme;
    const choisir = (id: Mecanisme) => setReglage({ mecanisme: id, ...DEFAUT[id], cible: CIBLE_VIDE, cases: id === "passage_en_menu" || id === "offre_famille" ? [{ categorie: "", quantite: 1 }] : [], effetSeuil: "pourcentage" });
    const remise = apercu(reglage);
    const etapes = [t("Quoi", "What"), t("Quand", "When"), t("Comment l'agent le dit", "How the agent says it")];
    const champs = LIBELLES[m];

    const enregistrer = async (etatVoulu: "brouillon" | "active") => {
        setErreur(null);
        let forme;
        try {
            forme = versLaBase(reglage, modes, t);
            if (m === "creneau" && !(heureDe < heureA)) throw new Error(t("L'heure de fin doit suivre l'heure de début.", "The end time must be after the start time."));
            if (debut && fin && fin < debut) throw new Error(t("La date de fin doit suivre la date de début.", "The end date must be after the start date."));
            if (!nom.trim() && !NOM[m]) throw new Error(t("Donnez un nom à la remise.", "Name the discount."));
        } catch (e) {
            setErreur((e as Error).message);
            return;
        }
        const momentEcrit: Record<string, unknown> = { ...(jours.length ? { jours } : {}), ...(m === "creneau" ? { heures: [[heureDe, heureA]] } : {}) };
        const corps: RemiseEcrite = {
            nom: nom.trim() || NOM[m][langue], mecanisme: m, ...forme, cumul: cumul ? "cumulable" : "exclusive",
            limite: nombre(max) >= 1 ? { max_par_achat: Math.round(nombre(max)) } : null, phrase: phrase.trim() || null, moment: Object.keys(momentEcrit).length ? momentEcrit : null,
            debut: debut ? new Date(`${debut}T00:00:00`).toISOString() : null, fin: fin ? new Date(`${fin}T23:59:59`).toISOString() : null,
            etat: depart && depart.etat !== "brouillon" ? "active" : etatVoulu,
        };
        setEnCours(true);
        const res = depart ? await modifierUneRemise(etab, depart.id, corps) : await creerUneRemise(etab, corps);
        setEnCours(false);
        if (res.error || !res.data) return void notifier.echec(ECHECS.restaurationRemiseEnregistrer, { erreur: res.error });
        poser(res.data);
        notifier.succes(depart ? { fr: "Remise enregistrée.", en: "Discount saved." } : etatVoulu === "active" ? { fr: "Remise créée et allumée.", en: "Discount created and switched on." } : { fr: "Remise créée en brouillon.", en: "Discount created as a draft." });
        fermer();
    };
    const selecteurCible = (obligatoire: "produit" | "tout" | "aucune") => (
        <Ligne libelle={obligatoire === "produit" ? t("Article", "Item") : t("Sur", "On")}>
            <Liste
                className="w-64"
                libelle={t("Cible de la remise", "Discount target")}
                valeur={reglage.cible.codes[0] ? `p:${reglage.cible.codes[0]}` : reglage.cible.categories[0] ? `c:${reglage.cible.categories[0]}` : ""}
                vide={obligatoire === "produit" ? t("Choisir…", "Choose…") : t("Tout le panier", "The whole basket")}
                changer={(v) => setReglage({ ...reglage, cible: v.startsWith("p:") ? { categories: [], codes: [v.slice(2)] } : v.startsWith("c:") ? { categories: [v.slice(2)], codes: [] } : CIBLE_VIDE })}
                options={[
                    ...(obligatoire !== "produit" ? choix.categories.map((c) => ({ valeur: `c:${c.ref}`, libelle: `${t("Catégorie", "Category")} · ${c.nom}` })) : []),
                    ...choix.produits.map((p) => ({ valeur: `p:${p.code}`, libelle: p.nom })),
                ]}
            />
        </Ligne>
    );
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={depart ? t("Modifier la remise", "Edit the discount") : t("Nouvelle remise", "New discount")}
            sous={
                <ol className="flex items-center gap-2 pt-1 text-xs">
                    {etapes.map((e, i) => (
                        <li key={e} className={`flex items-center gap-1.5 ${i === etape ? "font-semibold text-foreground" : i < etape ? "text-foreground" : "text-muted-foreground"}`}>
                            <span className={`flex size-5 items-center justify-center rounded-full border text-[11px] ${i < etape ? "border-primary bg-primary text-primary-foreground" : i === etape ? "border-primary" : ""}`}>{i < etape ? <Check className="size-3" /> : i + 1}</span>
                            {e}{i < 2 && <span className="mx-1 text-muted-foreground">›</span>}
                        </li>
                    ))}
                </ol>
            }
            valider={null}
            modifie
            pied={
                <>
                    <Button variant="outline" className="cursor-pointer" onClick={etape === 0 ? fermer : () => setEtape(etape - 1)}>{etape === 0 ? t("Annuler", "Cancel") : t("Retour", "Back")}</Button>
                    {etape < 2 ? (
                        <Button className="cursor-pointer" onClick={() => setEtape(etape + 1)}>{t("Suivant", "Next")}</Button>
                    ) : (
                        <>
                            {(!depart || depart.etat === "brouillon") && <Button variant="outline" className="cursor-pointer" disabled={enCours} onClick={() => void enregistrer("brouillon")}>{t("Enregistrer en brouillon", "Save as draft")}</Button>}
                            <Button className="cursor-pointer" disabled={enCours} onClick={() => void enregistrer("active")}>{depart ? t("Enregistrer", "Save") : t("Créer et allumer", "Create and switch on")}</Button>
                        </>
                    )}
                </>
            }
        >
            <div className="space-y-5 px-6 py-4">
                {etape === 0 && (
                    <>
                        <div className="grid grid-cols-2 gap-2.5">
                            {MECANISMES.map((id) => {
                                const I = ICONES[id] ?? Layers;
                                return (
                                    <button key={id} type="button" aria-pressed={m === id} disabled={!!depart} onClick={() => choisir(id)} className={`cursor-pointer rounded-xl border p-3 text-left disabled:cursor-default disabled:opacity-60 ${m === id ? "border-primary bg-muted/60" : "hover:bg-muted/50"}`}>
                                        <I className="mb-1.5 size-4 text-muted-foreground" />
                                        <p className="text-sm leading-tight font-medium">{NOM[id][langue]}</p>
                                        <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{NOM[id].exemple[langue]}</p>
                                    </button>
                                );
                            })}
                        </div>
                        <Section titre={t("Réglages", "Settings")}>
                            <Champs>
                                {(m === "prix_du_jour" || m === "nouveaute" || m === "taille_superieure") && selecteurCible("produit")}
                                {(m === "pourcentage" || m === "montant" || m === "x_achetes_y_offert" || m === "deuxieme_moitie_prix" || m === "creneau") && selecteurCible("tout")}
                                {m === "taille_superieure" ? (
                                    <Ligne libelle={t("Au prix de", "At the price of")}>
                                        <Liste className="w-64" libelle={t("Article dont il prend le prix", "Item whose price it takes")} valeur={reglage.a} vide={t("Choisir…", "Choose…")} changer={(v) => setReglage({ ...reglage, a: v })} options={choix.produits.map((p) => ({ valeur: p.code, libelle: p.nom }))} />
                                    </Ligne>
                                ) : (
                                    <Ligne libelle={t(champs.a[0], champs.a[1])}><Input className="h-8 w-28 text-right" inputMode="decimal" aria-label={t(champs.a[0], champs.a[1])} value={reglage.a} onChange={(e) => setReglage({ ...reglage, a: e.target.value })} /></Ligne>
                                )}
                                {champs.b && <Ligne libelle={t(champs.b[0], champs.b[1])}><Input className="h-8 w-28 text-right" inputMode="decimal" aria-label={t(champs.b[0], champs.b[1])} value={reglage.b} onChange={(e) => setReglage({ ...reglage, b: e.target.value })} /></Ligne>}
                                {m === "seuil_panier" && (
                                    <Ligne libelle={t("L'avantage est", "The benefit is")}>
                                        <Segment3 valeur={reglage.effetSeuil} changer={(v) => setReglage({ ...reglage, effetSeuil: v })} options={[{ v: "pourcentage", l: "%" }, { v: "montant", l: "€" }]} />
                                    </Ligne>
                                )}
                                {(m === "passage_en_menu" || m === "offre_famille") && (
                                    <>
                                        {reglage.cases.map((c, i) => (
                                            <Ligne key={i} libelle={t(`Case ${i + 1}`, `Slot ${i + 1}`)}>
                                                <span className="flex items-center gap-2">
                                                    <Input className="h-8 w-16 text-right" type="number" min={1} max={10} aria-label={t("Quantité", "Quantity")} value={c.quantite} onChange={(e) => setReglage({ ...reglage, cases: reglage.cases.map((x, k) => (k === i ? { ...x, quantite: Number(e.target.value) } : x)) })} />
                                                    <Liste className="w-44" libelle={t("Catégorie", "Category")} valeur={c.categorie} vide={t("Choisir…", "Choose…")} changer={(v) => setReglage({ ...reglage, cases: reglage.cases.map((x, k) => (k === i ? { ...x, categorie: v } : x)) })} options={choix.categories.map((x) => ({ valeur: x.ref, libelle: x.nom }))} />
                                                    {reglage.cases.length > 1 && <Button variant="ghost" size="icon" className="size-8 cursor-pointer" aria-label={t("Retirer la case", "Remove the slot")} onClick={() => setReglage({ ...reglage, cases: reglage.cases.filter((_, k) => k !== i) })}><Trash2 className="size-3.5" /></Button>}
                                                </span>
                                            </Ligne>
                                        ))}
                                        {reglage.cases.length < 8 && <Ligne libelle=""><Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setReglage({ ...reglage, cases: [...reglage.cases, { categorie: "", quantite: 1 }] })}><Plus className="size-3.5" /> {t("Case", "Slot")}</Button></Ligne>}
                                    </>
                                )}
                                <Ligne libelle={t("Types de commande", "Order types")}>
                                    <span className="flex gap-1.5">
                                        {(["emporter", "livraison", "sur_place"] as const).map((k) => (
                                            <button key={k} type="button" aria-pressed={modes.includes(k)} onClick={() => setModes(modes.includes(k) ? modes.filter((x) => x !== k) : [...modes, k])} className={`cursor-pointer rounded-md border px-2.5 py-1 text-sm ${modes.includes(k) ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted hover:font-medium"}`}>
                                                {k === "emporter" ? t("À emporter", "Takeaway") : k === "livraison" ? t("Livraison", "Delivery") : t("Sur place", "Dine-in")}
                                            </button>
                                        ))}
                                    </span>
                                </Ligne>
                            </Champs>
                            <p className="pt-2 text-xs text-muted-foreground">{t("Aucun type coché : tous les types de commande.", "No type ticked: every order type.")}</p>
                        </Section>
                    </>
                )}
                {etape === 1 && (
                    <Section titre={t("Quand", "When")}>
                        <Champs>
                            <Ligne libelle={t("Nom (pour vous)", "Name (for you)")}><Input value={nom} maxLength={80} onChange={(e) => setNom(e.target.value)} placeholder={NOM[m][langue]} className="h-8 w-56" /></Ligne>
                            <Ligne libelle={t("Du", "From")}><Input type="date" value={debut} onChange={(e) => setDebut(e.target.value)} className="h-8 w-40" /></Ligne>
                            <Ligne libelle={t("Au", "To")}><Input type="date" value={fin} onChange={(e) => setFin(e.target.value)} className="h-8 w-40" /></Ligne>
                            <Ligne libelle={t("Jours", "Days")}>
                                <span className="flex flex-wrap gap-1.5">
                                    {JOURS.map((j, i) => (
                                        <button key={j} type="button" aria-pressed={jours.includes(i + 1)} onClick={() => setJours(jours.includes(i + 1) ? jours.filter((x) => x !== i + 1) : [...jours, i + 1].sort())} className={`cursor-pointer rounded-md border px-2.5 py-1 text-sm ${jours.includes(i + 1) ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted hover:font-medium"}`}>{j}</button>
                                    ))}
                                </span>
                            </Ligne>
                            {m === "creneau" && (
                                <Ligne libelle={t("Heures", "Hours")}>
                                    <span className="flex items-center gap-2"><Input type="time" value={heureDe} onChange={(e) => setHeureDe(e.target.value)} className="h-8 w-28" aria-label={t("De", "From")} />›<Input type="time" value={heureA} onChange={(e) => setHeureA(e.target.value)} className="h-8 w-28" aria-label={t("À", "To")} /></span>
                                </Ligne>
                            )}
                            <Ligne libelle={t("Par achat, au plus", "Per order, at most")}><Input className="h-8 w-20 text-right" type="number" min={1} max={20} value={max} onChange={(e) => setMax(e.target.value)} aria-label={t("Utilisations au plus par achat", "Uses at most per order")} /></Ligne>
                            <Ligne libelle={t("Cumulable avec une autre remise", "Combinable with another discount")}><Switch checked={cumul} onCheckedChange={setCumul} /></Ligne>
                        </Champs>
                        <p className="pt-2 text-xs text-muted-foreground">{t("Aucun jour coché : tous les jours. Une remise programmée s'allume et s'éteint toute seule aux dates choisies.", "No day ticked: every day. A scheduled discount switches on and off by itself on the chosen dates.")}</p>
                    </Section>
                )}
                {etape === 2 && (
                    <Section titre={t("Comment l'agent le dit", "How the agent says it")} info={t("Une mention par appel en plus de la vente en plus, jamais à un client pressé ou qui a dit non.", "One mention per call on top of the upsell, never to a rushed customer or one who said no.")}>
                        <Champs>
                            <Ligne libelle={t("Phrase", "Sentence")}><Textarea value={phrase} maxLength={300} onChange={(e) => setPhrase(e.target.value)} placeholder={t("Ce soir, la deuxième pizza est à moitié prix.", "Tonight, the second pizza is half price.")} className="min-h-16 w-72 text-sm" aria-label={t("Phrase de l'agent", "Agent sentence")} /></Ligne>
                        </Champs>
                    </Section>
                )}
                {erreur && <p role="alert" className="text-sm text-destructive">{erreur}</p>}
                <div className="mt-6 rounded-xl border bg-muted/40 p-4 text-sm">
                    <p className="flex items-center gap-1.5 pb-2 text-xs font-medium tracking-wider text-muted-foreground uppercase">
                        {t("Aperçu du total", "Total preview")}
                        <Info>{t("Un panier d'exemple (2 pizzas à 12,50 € et une boisson à 2,50 €) : jamais une commande réelle. Le calcul exact est fait par le comptoir.", "A sample basket (2 pizzas at €12.50 and a drink at €2.50): never a real order. The exact calculation is done by the counter.")}</Info>
                    </p>
                    {PANIER.map((l, i) => <p key={i} className="flex justify-between text-muted-foreground"><span>{l.n}</span><span className="tabular-nums">{euros(l.c)}</span></p>)}
                    <p className="mt-1.5 flex justify-between border-t pt-1.5"><span>{t("Avant", "Before")}</span><span className="tabular-nums">{euros(TOTAL)}</span></p>
                    <p className="flex justify-between"><span>{t("Remise", "Discount")}</span><span className="tabular-nums">{remise ? "-" + euros(remise) : "–"}</span></p>
                    <p className="flex justify-between font-semibold"><span>{t("Total", "Total")}</span><span className="tabular-nums">{euros(TOTAL - remise)}</span></p>
                </div>
            </div>
        </FenetreOnglets>
    );
}

/** Les libellés des deux nombres de chaque mécanisme (le second quand il y en a un). */
const LIBELLES: Record<Mecanisme, { a: [string, string]; b?: [string, string] }> = {
    pourcentage: { a: ["Remise (%)", "Discount (%)"] },
    montant: { a: ["Montant (€)", "Amount (€)"] },
    x_achetes_y_offert: { a: ["Achetés (X)", "Bought (X)"], b: ["Offerts (Y)", "Free (Y)"] },
    deuxieme_moitie_prix: { a: ["Réduction (%)", "Reduction (%)"], b: ["Sur le … e article", "On the … th item"] },
    prix_du_jour: { a: ["Prix du jour (€)", "Price of the day (€)"] },
    seuil_panier: { a: ["Seuil de panier (€)", "Basket threshold (€)"], b: ["Valeur de l'avantage", "Benefit value"] },
    passage_en_menu: { a: ["Prix du menu (€)", "Meal deal price (€)"] },
    taille_superieure: { a: ["", ""] },
    offre_famille: { a: ["Prix de l'offre (€)", "Offer price (€)"] },
    creneau: { a: ["Remise (%)", "Discount (%)"] },
    nouveaute: { a: ["Prix de lancement (€)", "Launch price (€)"] },
    fidelite: { a: ["Tous les … commandes", "Every … orders"], b: ["Remise (%)", "Discount (%)"] },
};
