"use client";

/**
 * [.mark] Module Restauration, lot 20 (F11) : l'écran Outils › Simulateurs › Caisse / POS, Labo seulement.
 *
 * Reprend la maquette (`components/restauration/simulation.tsx`) sur les vraies données de la caisse de démo (``api/routes/restauration_caisse_demo.py``) :
 * le restaurant de test (choisir, créer, renommer, dupliquer, supprimer), ses onglets Carte (recherche, fiche produit dans le panneau de droite, rupture,
 * import d'un fichier, import d'une photo par le scan W46, ajout), Restaurant (état, délai, types de commande, paiements), Livraison (zones à la main),
 * Clients connus, Comportements, Scénarios. Tout s'écrit ici, rien dans le code. Les horaires du restaurant de test ne sont pas faits (la caisse de démo
 * n'a aucune réponse enregistrée de HubRise qui porte ``opening_hours`` : jamais écrite de mémoire).
 */
import { FileUp, ImageUp, MoreHorizontal, Pencil, Plus, Search, Store, Trash2, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";

import { notifier } from "../notifications";
import { echecAffiche } from "../notifications/echec-affiche";
import { ECHECS } from "../notifications/phrases-echec";
import { Defileur } from "../studio/defileur";
import { EtatVide } from "../studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp as Ligne, Section } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Info, PointEtat } from "../studio/marques";
import { Cellule, Ligne as LigneT, Tableau } from "../studio/tableau";
import { Confirmer, EcranDonnees, euros, Nombre, Segment3, useTexte } from "./commun";
import { useCharge } from "./contexte";
import {
    type CarteDeTest, type ClientConnu, type Comportement, creerUnResto, dupliquerUnResto, enCentimes, enEuros, enregistrerUnScenario, type EtatResto,
    faireUnGeste, identifiantDe, importerUneCarte, lireLesRestos, lireLeReglageDuScan, lireUnePhoto, lireUnResto, mettreUnScenarioEnPlace, type ProduitDeTest,
    poserLeReglageDuScan, reglerUnResto, type RestoDetail, supprimerUnResto, supprimerUnScenario, type Zone,
} from "./simulation-donnees";

const ONGLETS = ["carte", "restaurant", "livraison", "clients", "comportements", "scenarios"] as const;
type Onglet = (typeof ONGLETS)[number];
const REFUS = ["produit_inconnu", "prix_different", "ferme", "remise_inconnue"] as const;
const TYPES = ["emporter", "livraison", "sur_place"] as const;
const MOYENS = ["carte", "especes", "titre_restaurant", "cheque"] as const;

export function resume(c: Comportement, t: (fr: string, en: string) => string): string {
    const x: string[] = [];
    x.push(c.reponse === "controle" ? t("refuse ce qui ne colle pas à sa carte", "refuses what does not match its menu") : c.reponse === "silence" ? t("ne répond pas" , "does not answer") : c.reponse === "panne" ? t("tombe en panne", "breaks down") : t("accepte et rend son numéro", "accepts and returns its number"));
    if (c.reponse !== "silence" && c.delai_s) x.push(t(`répond en ${String(c.delai_s).replace(".", ",")} s`, `answers in ${c.delai_s} s`));
    if (c.acceptation === "refus") x.push(t("puis refuse la commande", "then rejects the order"));
    if (c.acceptation === "manuelle") x.push(t("n'accepte pas toute seule", "does not accept by itself"));
    if (c.doublon) x.push(t("messages rendus deux fois", "messages delivered twice"));
    return x.join(" · ");
}

/** Les rangées d'un tableau de saisie (zones, clients) : un titre de colonne par champ, un bouton d'ajout, un bouton de retrait par rangée. */
function Rangees<T>({ colonnes, lignes, changer, nouvelle, ajouter, vide, rendu }: {
    colonnes: string[]; lignes: T[]; changer: (l: T[]) => void; nouvelle: () => T; ajouter: string; vide: string;
    rendu: (l: T, maj: (p: Partial<T>) => void) => React.ReactNode[];
}) {
    const t = useTexte();
    return (
        <div className="space-y-2 py-2">
            {lignes.length === 0 ? <p className="text-sm text-muted-foreground">{vide}</p> : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="text-xs text-muted-foreground"><tr>{colonnes.map((c) => <th key={c} className="px-1 py-1 text-left font-normal">{c}</th>)}<th /></tr></thead>
                        <tbody>{lignes.map((l, i) => (
                            <tr key={i}>
                                {rendu(l, (p) => changer(lignes.map((x, j) => (j === i ? { ...x, ...p } : x)))).map((c, j) => <td key={j} className="px-1 py-1">{c}</td>)}
                                <td className="px-1 py-1 text-right"><Button variant="ghost" size="icon" className="size-8 text-muted-foreground" aria-label={t("Retirer la ligne", "Remove the row")} onClick={() => changer(lignes.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button></td>
                            </tr>))}</tbody>
                    </table>
                </div>)}
            <Button variant="ghost" size="sm" className="-ml-2" onClick={() => changer([...lignes, nouvelle()])}><Plus className="size-4" /> {ajouter}</Button>
        </div>
    );
}

/** Le réglage « lecture de photo » de l'organisation : éteint par défaut (une lecture coûte un appel au modèle), allumé par une personne, ici. */
export function ReglageDuScan() {
    const t = useTexte();
    const [actif, setActif] = useState<boolean | null>(null);
    const { user, loading } = useAuth();
    const lu = useRef(false);
    useEffect(() => {
        if (loading || !user || lu.current) return;
        lu.current = true;
        void lireLeReglageDuScan().then((r) => setActif(!r.error && r.data?.actif === true));
    }, [loading, user]);
    return (
        <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Switch checked={actif === true} disabled={actif === null} aria-label={t("Lecture de photo", "Photo reading")}
                onCheckedChange={(v) => void poserLeReglageDuScan(v).then((r) => { if (r.error) echecAffiche(r.error, ECHECS.simulationEnregistrer); else setActif(v); })} />
            {t("Lecture de photo", "Photo reading")}
            <Info>{t("Éteinte par défaut : une lecture appelle le modèle de l'organisation (sa clé) et coûte. Au plus 20 lectures par heure.", "Off by default: a reading calls the organization's model (its key) and costs money. At most 20 readings per hour.")}</Info>
        </label>
    );
}

const codesDe = (p: ProduitDeTest) => p.declinaisons.map((d) => d.code_caisse).filter((c): c is string => !!c);
const enRupture = (r: RestoDetail, p: ProduitDeTest) => {
    const codes = codesDe(p);
    return codes.length > 0 && codes.every((c) => r.stocks.some((s) => (s.sku_ref === c || s.option_ref === c) && Number(s.stock) <= 0));
};

export function EcranCaissePos() {
    const t = useTexte();
    const liste = useCharge(lireLesRestos, "restos", ECHECS.simulationLire);
    const [choisi, setChoisi] = useState<number | null>(null);
    const [onglet, setOnglet] = useState<Onglet>("carte");
    const restos = liste.donnee?.restaurants ?? [];
    const courant = choisi !== null && restos.some((x) => x.id === choisi) ? choisi : (restos[0]?.id ?? null);
    const detail = useCharge(courant === null ? null : () => lireUnResto(courant), `resto-${courant}`, ECHECS.simulationLire);
    const r = detail.donnee;
    const [nom, setNom] = useState<string | null>(null);
    const [sup, setSup] = useState(false);

    const relireTout = async () => { await Promise.all([liste.relire(), detail.relire()]); };
    const ecrire = async (champs: Record<string, unknown>, ok?: string) => {
        if (!r) return false;
        const rep = await reglerUnResto(r.id, champs);
        if (rep.error) { echecAffiche(rep.error, ECHECS.simulationEnregistrer); return false; }
        if (ok) notifier.succes({ fr: ok, en: ok });
        await relireTout();
        return true;
    };
    const nouveau = async () => {
        const rep = await creerUnResto(t("Nouveau restaurant de test", "New test restaurant"));
        if (rep.error || !rep.data) return void echecAffiche(rep.error, ECHECS.simulationEnregistrer);
        setChoisi(rep.data.id);
        notifier.succes({ fr: "Restaurant de test créé : remplissez sa carte.", en: "Test restaurant created: fill in its menu." });
        await liste.relire();
    };
    const dupliquer = async () => {
        if (!r) return;
        const rep = await dupliquerUnResto(r.id);
        if (rep.error || !rep.data) return void echecAffiche(rep.error, ECHECS.simulationEnregistrer);
        setChoisi(rep.data.id);
        notifier.succes({ fr: "Restaurant de test dupliqué.", en: "Test restaurant duplicated." });
        await liste.relire();
    };
    const supprimer = async () => {
        if (!r) return;
        const rep = await supprimerUnResto(r.id);
        if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationEnregistrer);
        setChoisi(null);
        notifier.succes({ fr: "Restaurant de test supprimé.", en: "Test restaurant deleted." });
        await liste.relire();
    };
    const noms: Record<Onglet, string> = { carte: t("Carte", "Menu"), restaurant: t("Restaurant", "Restaurant"), livraison: t("Livraison", "Delivery"), clients: t("Clients connus", "Known customers"), comportements: t("Comportements", "Behaviours"), scenarios: t("Scénarios", "Scenarios") };

    return (
        <div className="@container space-y-4">
            <div className="flex flex-wrap items-center gap-2">
                <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
                    {t("Caisse / POS", "Till / POS")}
                    <Info>{t("Une caisse de démo qui répond comme HubRise : la vraie prise HubRise s'y branche, les outils de l'agent ne changent pas. Réservée au Labo.", "A demo till that answers like HubRise: the real HubRise socket plugs into it, the agent's tools do not change. Labo only.")}</Info>
                </h1>
                <span className="ml-auto flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">{t("Restaurant de test", "Test restaurant")}</span>
                    {nom !== null && r ? (
                        <Input autoFocus value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t("Nom du restaurant de test", "Test restaurant name")} className="h-8 w-56"
                            onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") setNom(null); }}
                            onBlur={() => { const n = nom.trim(); setNom(null); if (n && n !== r.nom) void ecrire({ nom: n }, "Restaurant de test renommé."); }} />
                    ) : (
                        <span className="inline-flex items-center gap-1.5">
                            <Liste valeur={courant === null ? "" : String(courant)} changer={(v) => setChoisi(Number(v))} options={restos.map((x) => ({ valeur: String(x.id), libelle: x.nom }))} className="w-52" libelle={t("Restaurant de test", "Test restaurant")} />
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="size-8 text-muted-foreground" aria-label={t("Gestes du restaurant de test", "Test restaurant actions")}><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-60">
                                    <DropdownMenuItem onClick={() => void nouveau()}><Plus className="size-4" /> {t("Nouveau restaurant de test", "New test restaurant")}</DropdownMenuItem>
                                    {r && <>
                                        <DropdownMenuItem onClick={() => setNom(r.nom)}><Pencil className="size-4" /> {t("Renommer", "Rename")}</DropdownMenuItem>
                                        <DropdownMenuItem onClick={() => void dupliquer()}><Copy className="size-4" /> {t("Dupliquer", "Duplicate")}</DropdownMenuItem>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem className="text-destructive" onClick={() => setSup(true)}><Trash2 className="size-4" /> {t("Supprimer", "Delete")}</DropdownMenuItem>
                                    </>}
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </span>)}
                </span>
            </div>
            {sup && r && <Confirmer titre={t(`Supprimer « ${r.nom} » ?`, `Delete “${r.nom}”?`)} texte={t("Sa carte, ses clients connus et ses commandes reçues sont supprimés ; il est débranché de son établissement. Aucun agent n'est touché.", "Its menu, known customers and received orders are deleted; it is unplugged from its site. No agent is affected.")} bouton={t("Supprimer", "Delete")} fermer={() => setSup(false)} valider={() => void supprimer()} />}
            <EcranDonnees etat={liste.etat} relire={liste.relire} vide={restos.length === 0} iconeVide={Store} titreVide={t("Aucun restaurant de test", "No test restaurant")}>
                {r && (
                    <>
                        <Defileur className="border-b">
                            {ONGLETS.map((o) => (
                                <button key={o} onClick={() => setOnglet(o)} className={`-mb-px cursor-pointer border-b-2 px-3 py-2.5 text-sm ${onglet === o ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:font-semibold"}`}>
                                    {noms[o]}{o === "carte" && <span className="ml-1.5 tabular-nums text-muted-foreground">{r.carte.produits.length}</span>}
                                </button>))}
                        </Defileur>
                        {onglet === "carte" && <CarteDeTestOnglet key={r.id} r={r} ecrire={ecrire} relire={relireTout} />}
                        {onglet === "restaurant" && <ReglagesDeTest r={r} ecrire={ecrire} />}
                        {onglet === "livraison" && <LivraisonDeTest r={r} ecrire={ecrire} />}
                        {onglet === "clients" && <ClientsDeTest r={r} ecrire={ecrire} />}
                        {onglet === "comportements" && <Comportements r={r} ecrire={ecrire} relire={relireTout} />}
                        {onglet === "scenarios" && <Scenarios r={r} scenarios={liste.donnee?.scenarios ?? []} relire={relireTout} versReglages={() => setOnglet("comportements")} />}
                    </>)}
            </EcranDonnees>
        </div>
    );
}

// ---- Carte ------------------------------------------------------------------------------------------------------------------------------------

type Ecrire = (champs: Record<string, unknown>, ok?: string) => Promise<boolean>;

function CarteDeTestOnglet({ r, ecrire, relire }: { r: RestoDetail; ecrire: Ecrire; relire: () => Promise<void> }) {
    const t = useTexte();
    const [q, setQ] = useState("");
    const [ouvert, setOuvert] = useState<ProduitDeTest | "nouveau" | null>(null);
    const [proposition, setProposition] = useState<{ carte: CarteDeTest; lus: number; ecartes: number } | null>(null);
    const fichier = useRef<HTMLInputElement>(null);
    const photo = useRef<HTMLInputElement>(null);
    const nomDe = (id: string | null) => r.carte.categories.find((c) => c.id === id)?.nom ?? "";
    const liste = r.carte.produits.filter((p) => `${p.nom} ${nomDe(p.categorie_id)}`.toLowerCase().includes(q.toLowerCase()));
    const ruptures = r.carte.produits.filter((p) => enRupture(r, p)).length;

    const basculer = async (p: ProduitDeTest, dispo: boolean) => {
        // Une rupture se pose PAR LA CAISSE (message signé comme une vraie caisse) : un code après l'autre.
        for (const code of codesDe(p)) {
            const rep = await faireUnGeste(r.id, { geste: "rupture", code, disponible: dispo });
            if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationGeste);
        }
        notifier.succes(dispo ? { fr: `« ${p.nom} » est de nouveau disponible.`, en: `“${p.nom}” is available again.` } : { fr: `« ${p.nom} » passe en rupture.`, en: `“${p.nom}” is now out of stock.` });
        await relire();
    };
    const lireLeFichier = async (f: File | undefined) => {
        if (!f) return;
        let carte: unknown;
        try { carte = JSON.parse(await f.text()); } catch { return void notifier.echec(ECHECS.simulationFichier, { groupe: "simulation-fichier" }); }
        const rep = await importerUneCarte(r.id, carte);
        if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationFichier);
        notifier.succes({ fr: `Carte importée : ${rep.data?.produits ?? 0} produits.`, en: `Menu imported: ${rep.data?.produits ?? 0} products.` });
        await relire();
    };
    const lireLaPhoto = async (f: File | undefined) => {
        if (!f) return;
        const octets = new Uint8Array(await f.arrayBuffer());
        let binaire = "";
        octets.forEach((o) => { binaire += String.fromCharCode(o); });
        const cours = notifier.enCours({ fr: "Lecture de la photo en cours…", en: "Reading the photo…" });
        const rep = await lireUnePhoto(r.id, btoa(binaire), f.type);
        cours.fermer();
        if (rep.error || !rep.data) return void echecAffiche(rep.error, ECHECS.simulationPhoto);
        setProposition(rep.data);
    };
    const importerLaProposition = async () => {
        if (!proposition) return;
        const rep = await importerUneCarte(r.id, proposition.carte);
        if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationFichier);
        setProposition(null);
        notifier.succes({ fr: "Carte de la photo importée.", en: "Menu from the photo imported." });
        await relire();
    };
    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
                <div className="relative w-full max-w-64"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Rechercher un produit", "Search a product")} aria-label={t("Rechercher un produit", "Search a product")} className="h-9 border-transparent bg-muted/50 pl-9 shadow-none focus-visible:bg-background" /></div>
                <span className="text-sm text-muted-foreground">{ruptures > 0 ? t(`${ruptures} en rupture`, `${ruptures} out of stock`) : t("Tout est disponible", "Everything is available")}</span>
                <span className="ml-auto flex flex-wrap gap-2">
                    <input ref={fichier} type="file" accept="application/json,.json" className="hidden" onChange={(e) => { void lireLeFichier(e.target.files?.[0]); e.target.value = ""; }} />
                    <input ref={photo} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => { void lireLaPhoto(e.target.files?.[0]); e.target.value = ""; }} />
                    <Button variant="outline" size="sm" onClick={() => fichier.current?.click()}><FileUp className="size-4" /> {t("Importer un fichier", "Import a file")}</Button>
                    <ReglageDuScan />
                    <Button variant="outline" size="sm" onClick={() => photo.current?.click()}><ImageUp className="size-4" /> {t("Importer une photo", "Import a photo")}</Button>
                    <Button size="sm" onClick={() => setOuvert("nouveau")}><Plus className="size-4" /> {t("Ajouter un produit", "Add a product")}</Button>
                </span>
            </div>
            {r.carte.produits.length === 0 ? <EtatVide cas="premier" icone={Store} titre={t("Carte vide", "Empty menu")} /> : (
                <Tableau colonnes={[{ titre: t("Produit", "Product") }, { titre: t("Catégorie", "Category"), secondaire: 1 }, { titre: t("Tailles et prix", "Sizes and prices") }, { titre: t("Disponible", "Available"), droite: true }]}>
                    {liste.map((p) => (
                        <LigneT key={p.id} onClick={() => setOuvert(p)}>
                            <Cellule principale sous={p.description ?? undefined}>{p.nom}</Cellule>
                            <Cellule>{nomDe(p.categorie_id)}</Cellule>
                            <Cellule>{p.declinaisons.map((d, i) => <span key={d.id} className="whitespace-nowrap">{i ? " · " : ""}{d.nom} {euros(d.prix)}</span>)}</Cellule>
                            <Cellule droite><span onClick={(e) => e.stopPropagation()}><Switch checked={!enRupture(r, p)} aria-label={t(`${p.nom} disponible`, `${p.nom} available`)} onCheckedChange={(v) => void basculer(p, v)} /></span></Cellule>
                        </LigneT>))}
                </Tableau>)}
            {ouvert && <FicheProduit key={ouvert === "nouveau" ? "n" : ouvert.id} r={r} p={ouvert === "nouveau" ? null : ouvert} fermer={() => setOuvert(null)} ecrire={ecrire} />}
            {proposition && (
                <Confirmer danger={false} titre={t("Carte lue sur la photo", "Menu read from the photo")}
                    texte={t(`${proposition.carte.produits.length} produits lus (${proposition.ecartes} lignes écartées) : ${proposition.carte.produits.slice(0, 6).map((p) => p.nom).join(", ")}… L'import remplace la carte de ce restaurant de test.`, `${proposition.carte.produits.length} products read (${proposition.ecartes} lines dropped): ${proposition.carte.produits.slice(0, 6).map((p) => p.nom).join(", ")}… Importing replaces this test restaurant's menu.`)}
                    bouton={t("Importer", "Import")} fermer={() => setProposition(null)} valider={() => void importerLaProposition()} />)}
        </div>
    );
}

interface Taille { libelle: string; prix: string }

function FicheProduit({ r, p, fermer, ecrire }: { r: RestoDetail; p: ProduitDeTest | null; fermer: () => void; ecrire: Ecrire }) {
    const t = useTexte();
    const [nom, setNom] = useState(p?.nom ?? "");
    const [categorie, setCategorie] = useState(r.carte.categories.find((c) => c.id === p?.categorie_id)?.nom ?? r.carte.categories[0]?.nom ?? "");
    const [tailles, setTailles] = useState<Taille[]>(p ? p.declinaisons.map((d) => ({ libelle: d.nom, prix: enEuros(d.prix) })) : [{ libelle: "", prix: "" }]);
    const [sup, setSup] = useState(false);
    const enregistrer = async () => {
        const n = nom.trim();
        if (!n) return void notifier.echec({ fr: "Donnez un nom au produit.", en: "Give the product a name." }, { groupe: "simulation-produit" });
        const idCat = identifiantDe(categorie || "Divers");
        const categories = r.carte.categories.some((c) => c.id === idCat) ? r.carte.categories : [...r.carte.categories, { id: idCat, nom: categorie.trim() || "Divers" }];
        const idProduit = p?.id ?? identifiantDe(n);
        const declinaisons = tailles.filter((x) => enCentimes(x.prix) > 0).map((x, i) => {
            const ancienne = p?.declinaisons[i];
            const id = ancienne?.id ?? identifiantDe(`${n} ${x.libelle || i}`);
            return { id, nom: x.libelle.trim() || n, prix: enCentimes(x.prix), disponibilite: null, code_caisse: ancienne?.code_caisse ?? id };
        });
        if (declinaisons.length === 0) return void notifier.echec({ fr: "Ajoutez au moins une taille avec un prix.", en: "Add at least one size with a price." }, { groupe: "simulation-produit" });
        const produit: ProduitDeTest = { ...(p ?? { ingredients: [], allergenes: null, tva_par_mode: {}, etoile: false, groupes: [] }), id: idProduit, nom: n, description: p?.description ?? null, categorie_id: idCat, declinaisons };
        const produits = p ? r.carte.produits.map((y) => (y.id === p.id ? produit : y)) : [...r.carte.produits, produit];
        if (await ecrire({ carte: { ...r.carte, categories, produits } }, p ? "Produit enregistré." : "Produit ajouté à la carte de test.")) fermer();
    };
    return (
        <FenetreOnglets fermer={fermer} titre={p ? p.nom : t("Nouveau produit", "New product")} sous={r.nom} valider={t("Enregistrer", "Save")} onValider={() => void enregistrer()}
            pied={undefined}>
            <Section titre={t("Produit", "Product")}>
                <Champs>
                    <Ligne libelle={t("Nom", "Name")}><Input value={nom} onChange={(e) => setNom(e.target.value)} className="h-8 w-60" aria-label={t("Nom", "Name")} /></Ligne>
                    <Ligne libelle={t("Catégorie", "Category")} info={t("Une catégorie nouvelle se crée en l'écrivant.", "A new category is created by typing it.")}>
                        <Input value={categorie} onChange={(e) => setCategorie(e.target.value)} className="h-8 w-60" list="categories-test" aria-label={t("Catégorie", "Category")} />
                        <datalist id="categories-test">{r.carte.categories.map((c) => <option key={c.id} value={c.nom} />)}</datalist>
                    </Ligne>
                </Champs>
            </Section>
            <Section titre={t("Tailles et prix", "Sizes and prices")}>
                <Rangees colonnes={[t("Taille", "Size"), t("Prix (€)", "Price (€)")]} lignes={tailles} changer={setTailles} vide={t("Aucune taille.", "No size.")} nouvelle={() => ({ libelle: "", prix: "" })} ajouter={t("Ajouter une taille", "Add a size")}
                    rendu={(l, m) => [
                        <Input key="l" value={l.libelle} onChange={(e) => m({ libelle: e.target.value })} className="h-8" aria-label={t("Taille", "Size")} />,
                        <Input key="p" value={l.prix} onChange={(e) => m({ prix: e.target.value.replace(/[^\d,.]/g, "") })} className="h-8 w-24 text-right" aria-label={t("Prix", "Price")} />,
                    ]} />
            </Section>
            {p && <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setSup(true)}><Trash2 className="size-3.5" /> {t("Supprimer", "Delete")}</Button>}
            {sup && p && <Confirmer titre={t(`Supprimer « ${p.nom} » ?`, `Delete “${p.nom}”?`)} texte={t("Le produit quitte la carte de ce restaurant de test.", "The product leaves this test restaurant's menu.")} bouton={t("Supprimer", "Delete")} fermer={() => setSup(false)}
                valider={() => void ecrire({ carte: { ...r.carte, produits: r.carte.produits.filter((y) => y.id !== p.id) } }, "Produit supprimé.").then((ok) => ok && fermer())} />}
        </FenetreOnglets>
    );
}

// ---- Horaires (forme publique HubRise : monday..sunday, créneaux {from, to} en HH:mm) --------------------------------------------------------

const JOURS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
type Horaires = Partial<Record<(typeof JOURS)[number], { from: string; to: string }[]>>;
const CRENEAU = /^\s*([0-2]\d:[0-5]\d)\s*-\s*([0-2]\d:[0-5]\d)\s*$/;

/** « 11:30-14:30, 18:00-01:00 » en créneaux ; ``null`` si le texte n'est pas de cette forme (le champ le dit, rien n'est envoyé). */
export const creneauxDe = (texte: string): { from: string; to: string }[] | null => {
    if (!texte.trim()) return [];
    const sortie: { from: string; to: string }[] = [];
    for (const morceau of texte.split(",")) {
        const m = CRENEAU.exec(morceau);
        if (!m) return null;
        sortie.push({ from: m[1], to: m[2] });
    }
    return sortie;
};
export const texteDes = (creneaux: { from: string; to: string }[] | undefined): string => (creneaux ?? []).map((c) => `${c.from}-${c.to}`).join(", ");

function HorairesDeTest({ r, ecrire }: { r: RestoDetail; ecrire: Ecrire }) {
    const t = useTexte();
    const noms: Record<(typeof JOURS)[number], string> = {
        monday: t("Lundi", "Monday"), tuesday: t("Mardi", "Tuesday"), wednesday: t("Mercredi", "Wednesday"), thursday: t("Jeudi", "Thursday"),
        friday: t("Vendredi", "Friday"), saturday: t("Samedi", "Saturday"), sunday: t("Dimanche", "Sunday"),
    };
    const actuels = (r.reglages.horaires ?? null) as Horaires | null;
    const [saisies, setSaisies] = useState<Record<string, string>>(() => Object.fromEntries(JOURS.map((j) => [j, texteDes(actuels?.[j])])));
    const [fautes, setFautes] = useState<Record<string, boolean>>({});
    const poser = (jour: (typeof JOURS)[number]) => {
        const creneaux = creneauxDe(saisies[jour]);
        if (creneaux === null) { setFautes((f) => ({ ...f, [jour]: true })); return; }
        setFautes((f) => ({ ...f, [jour]: false }));
        const suite: Horaires = { ...(actuels ?? {}) };
        if (creneaux.length) suite[jour] = creneaux; else delete suite[jour];
        void ecrire({ reglages: { horaires: Object.keys(suite).length ? suite : null } });
    };
    return (
        <Section titre={t("Horaires d'ouverture", "Opening hours")}>
            <Champs>
                {JOURS.map((j) => (
                    <Ligne key={j} libelle={noms[j]}>
                        <div className="flex flex-col items-end gap-1">
                            <Input
                                value={saisies[j]} placeholder={t("fermé", "closed")} aria-label={noms[j]} aria-invalid={fautes[j] || undefined} className="h-8 w-56 text-right"
                                onChange={(e) => setSaisies((s) => ({ ...s, [j]: e.target.value }))} onBlur={() => poser(j)} onKeyDown={(e) => { if (e.key === "Enter") poser(j); }}
                            />
                            {fautes[j] && <span className="text-xs text-destructive">{t("Écris 11:30-14:30, 18:00-01:00", "Write 11:30-14:30, 18:00-01:00")}</span>}
                        </div>
                    </Ligne>
                ))}
            </Champs>
        </Section>
    );
}

// ---- Restaurant, livraison, clients ----------------------------------------------------------------------------------------------------------

function ReglagesDeTest({ r, ecrire }: { r: RestoDetail; ecrire: Ecrire }) {
    const t = useTexte();
    const etats: { v: EtatResto; l: string }[] = [{ v: "ouvert", l: t("Ouvert", "Open") }, { v: "ferme", l: t("Fermé", "Closed") }, { v: "deborde", l: t("Débordé", "Overloaded") }];
    const types: Record<string, string> = { emporter: t("À emporter", "Takeaway"), livraison: t("Livraison", "Delivery"), sur_place: t("Sur place", "Eat in") };
    const moyens: Record<string, string> = { carte: t("Carte bancaire", "Card"), especes: t("Espèces", "Cash"), titre_restaurant: t("Titre-restaurant", "Meal voucher"), cheque: t("Chèque", "Cheque") };
    const bascule = (cle: "types_de_commande" | "paiements", valeur: string, v: boolean) => {
        const actuels = r.reglages[cle] ?? [];
        void ecrire({ reglages: { [cle]: v ? [...new Set([...actuels, valeur])] : actuels.filter((x) => x !== valeur) } });
    };
    return (
        <div className="grid gap-x-10 @3xl:grid-cols-2">
            <div>
                <Section titre={t("État du restaurant", "Restaurant status")}>
                    <Champs>
                        <Ligne libelle={t("En ce moment", "Right now")} info={t("Fermé : la caisse met la prise en pause. Débordé : elle accepte et allonge le délai.", "Closed: the till pauses the socket. Overloaded: it accepts and lengthens the delay.")}>
                            <Segment3 valeur={r.etat} options={etats} changer={(v) => void ecrire({ etat: v })} />
                        </Ligne>
                        {r.etat === "deborde" && <Ligne libelle={t("Minutes en plus", "Extra minutes")}><Nombre valeur={String(r.minutes_en_plus)} min={0} max={240} unite="min" libelle={t("Minutes en plus", "Extra minutes")} changer={(v) => void ecrire({ minutes_en_plus: Math.max(0, Math.min(240, Math.round(Number(v) || 0))) })} /></Ligne>}
                        <Ligne libelle={t("Délai annoncé", "Announced delay")}><Nombre valeur={String(r.reglages.delai ?? 20)} min={5} max={120} unite="min" libelle={t("Délai annoncé", "Announced delay")} changer={(v) => void ecrire({ reglages: { delai: Math.max(5, Math.min(120, Math.round(Number(v) || 20))) } })} /></Ligne>
                    </Champs>
                </Section>
            </div>
            <div>
                <Section titre={t("Types de commande", "Order types")}><Champs>{TYPES.map((x) => <Ligne key={x} libelle={types[x]}><Switch checked={(r.reglages.types_de_commande ?? []).includes(x)} aria-label={types[x]} onCheckedChange={(v) => bascule("types_de_commande", x, v)} /></Ligne>)}</Champs></Section>
                <Section titre={t("Moyens de paiement", "Payment methods")}><Champs>{MOYENS.map((x) => <Ligne key={x} libelle={moyens[x]}><Switch checked={(r.reglages.paiements ?? []).includes(x)} aria-label={moyens[x]} onCheckedChange={(v) => bascule("paiements", x, v)} /></Ligne>)}</Champs></Section>
                <HorairesDeTest key={JSON.stringify(r.reglages.horaires ?? null)} r={r} ecrire={ecrire} />
            </div>
        </div>
    );
}

interface ZoneSaisie { nom: string; communes: string; frais: string; minimum: string; delai: string }

function LivraisonDeTest({ r, ecrire }: { r: RestoDetail; ecrire: Ecrire }) {
    const t = useTexte();
    const depart: ZoneSaisie[] = (r.reglages.zones ?? []).map((z) => ({ nom: z.nom, communes: z.communes, frais: enEuros(z.frais), minimum: enEuros(z.minimum), delai: String(z.delai) }));
    const [zones, setZones] = useState<ZoneSaisie[]>(depart);
    const modifie = JSON.stringify(zones) !== JSON.stringify(depart);
    const enregistrer = () => {
        const sortie: Zone[] = zones.filter((z) => z.nom.trim()).map((z) => ({ nom: z.nom.trim(), communes: z.communes.trim(), frais: enCentimes(z.frais), minimum: enCentimes(z.minimum), delai: Math.max(0, Math.round(Number(z.delai) || 0)) }));
        void ecrire({ reglages: { zones: sortie } }, "Zones de livraison enregistrées.");
    };
    return (
        <Section titre={t("Zones de livraison", "Delivery zones")} info={t("Saisies à la main pour ce restaurant de test : quelques communes par zone suffisent. Chaque zone porte ses frais, son minimum de commande et son délai de livraison, en entier. Les frais sont rendus par la caisse de démo.", "Typed by hand for this test restaurant: a few towns per zone are enough. Each zone carries its fee, minimum order and full delivery time. The fees are returned by the demo till.")}>
            {!(r.reglages.types_de_commande ?? []).includes("livraison") && <p className="py-2 text-sm text-muted-foreground">{t("La livraison est éteinte pour ce restaurant de test (onglet Restaurant).", "Delivery is off for this test restaurant (Restaurant tab).")}</p>}
            <Rangees colonnes={[t("Zone", "Zone"), t("Communes", "Towns"), t("Frais (€)", "Fee (€)"), t("Minimum (€)", "Minimum (€)"), t("Délai (min)", "Time (min)")]} lignes={zones} changer={setZones}
                vide={t("Aucune zone : toute adresse est hors zone.", "No zone: every address is out of range.")} nouvelle={() => ({ nom: `Zone ${zones.length + 1}`, communes: "", frais: "0", minimum: "0", delai: "30" })} ajouter={t("Ajouter une zone", "Add a zone")}
                rendu={(z, m) => [
                    <Input key="n" value={z.nom} onChange={(e) => m({ nom: e.target.value })} className="h-8 w-24" aria-label={t("Zone", "Zone")} />,
                    <Input key="c" value={z.communes} onChange={(e) => m({ communes: e.target.value })} placeholder={t("Communes séparées par une virgule", "Towns separated by a comma")} className="h-8 min-w-64" aria-label={t("Communes", "Towns")} />,
                    <Input key="f" value={z.frais} onChange={(e) => m({ frais: e.target.value.replace(/[^\d,.]/g, "") })} className="h-8 w-20 text-right" aria-label={t("Frais", "Fee")} />,
                    <Input key="m" value={z.minimum} onChange={(e) => m({ minimum: e.target.value.replace(/[^\d,.]/g, "") })} className="h-8 w-20 text-right" aria-label={t("Minimum", "Minimum")} />,
                    <Input key="d" value={z.delai} onChange={(e) => m({ delai: e.target.value.replace(/\D/g, "") })} className="h-8 w-20 text-right" aria-label={t("Délai", "Time")} />,
                ]} />
            <Button size="sm" disabled={!modifie} onClick={enregistrer}>{t("Enregistrer les zones", "Save the zones")}</Button>
        </Section>
    );
}

interface ClientSaisi { nom: string; telephone: string; adresse: string; habitude: string }

function ClientsDeTest({ r, ecrire }: { r: RestoDetail; ecrire: Ecrire }) {
    const t = useTexte();
    const depart: ClientSaisi[] = r.clients.map((c) => ({ nom: c.first_name ?? "", telephone: c.phone ?? "", adresse: c.address_1 ?? "", habitude: c.delivery_notes ?? "" }));
    const [clients, setClients] = useState<ClientSaisi[]>(depart);
    const modifie = JSON.stringify(clients) !== JSON.stringify(depart);
    const enregistrer = () => {
        const sortie: ClientConnu[] = clients.filter((c) => c.telephone.trim()).map((c) => ({ first_name: c.nom.trim() || null, phone: c.telephone.trim(), address_1: c.adresse.trim() || null, delivery_notes: c.habitude.trim() || null }));
        void ecrire({ clients: sortie }, "Clients connus enregistrés.");
    };
    return (
        <Section titre={t("Clients connus", "Known customers")} info={t("La caisse les reconnaît à leur numéro (format +33…) : l'agent retrouve leur nom, leur adresse et leurs habitudes.", "The till recognises them by number (+33… format): the agent finds their name, address and habits.")}>
            <Rangees colonnes={[t("Nom", "Name"), t("Téléphone", "Phone"), t("Adresse", "Address"), t("Habitudes", "Habits")]} lignes={clients} changer={setClients} vide={t("Aucun client connu : tout appelant est nouveau.", "No known customer: every caller is new.")} nouvelle={() => ({ nom: "", telephone: "", adresse: "", habitude: "" })} ajouter={t("Ajouter un client", "Add a customer")}
                rendu={(c, m) => [
                    <Input key="n" value={c.nom} onChange={(e) => m({ nom: e.target.value })} className="h-8 w-32" aria-label={t("Nom", "Name")} />,
                    <Input key="t" value={c.telephone} onChange={(e) => m({ telephone: e.target.value })} className="h-8 w-36" aria-label={t("Téléphone", "Phone")} />,
                    <Input key="a" value={c.adresse} onChange={(e) => m({ adresse: e.target.value })} className="h-8 min-w-44" aria-label={t("Adresse", "Address")} />,
                    <Input key="h" value={c.habitude} onChange={(e) => m({ habitude: e.target.value })} className="h-8 min-w-48" aria-label={t("Habitudes", "Habits")} />,
                ]} />
            <Button size="sm" disabled={!modifie} onClick={enregistrer}>{t("Enregistrer les clients", "Save the customers")}</Button>
        </Section>
    );
}

// ---- Comportements, scénarios ------------------------------------------------------------------------------------------------------------------

function Comportements({ r, ecrire, relire }: { r: RestoDetail; ecrire: Ecrire; relire: () => Promise<void> }) {
    const t = useTexte();
    const c = r.comportement;
    const reponse = c.reponse ?? "accepte";
    const refus = c.controles?.length === 1 ? c.controles[0] : "produit_inconnu";
    const [nom, setNom] = useState("");
    const poser = (x: Comportement) => void ecrire({ comportement: { ...c, ...x } });
    const reponses: { v: "accepte" | "controle" | "silence"; l: string }[] = [{ v: "accepte", l: t("Accepte", "Accepts") }, { v: "controle", l: t("Refuse", "Refuses") }, { v: "silence", l: t("Ne répond pas", "No answer") }];
    const raisons: Record<string, string> = { produit_inconnu: t("Produit inconnu", "Unknown product"), prix_different: t("Prix différent", "Different price"), ferme: t("Restaurant fermé", "Restaurant closed"), remise_inconnue: t("Remise inconnue", "Unknown discount") };
    const acceptations: { v: "auto" | "manuelle" | "refus"; l: string }[] = [{ v: "auto", l: t("Elle accepte", "It accepts") }, { v: "manuelle", l: t("Personne n'accepte", "Nobody accepts") }, { v: "refus", l: t("Elle refuse", "It rejects") }];
    return (
        <div className="max-w-2xl">
            <Section titre={t("Réponse de la caisse", "Till answer")} info={t("Ce que la caisse de démo répond quand la prise HubRise lui envoie la commande.", "What the demo till answers when the HubRise socket sends it the order.")}>
                <Champs>
                    <Ligne libelle={t("À l'envoi de la commande", "When the order is sent")} info={t("Accepte : elle rend son numéro. Refuse : elle compare à sa carte et rend les champs en cause. Ne répond pas : la prise attend jusqu'à son délai.", "Accepts: returns its number. Refuses: compares with its menu and returns the fields at fault. No answer: the socket waits until its timeout.")}>
                        <Segment3 valeur={reponse === "panne" ? "accepte" : reponse} options={reponses} changer={(v) => poser({ reponse: v, ...(v === "controle" && !c.controles?.length ? { controles: ["produit_inconnu", "prix_different", "ferme", "remise_inconnue"] } : {}) })} />
                    </Ligne>
                    {reponse === "controle" && <Ligne libelle={t("Ce qu'elle refuse", "What it refuses")}>
                        <Liste valeur={c.controles?.length === 1 ? refus : "tout"} changer={(v) => poser({ controles: v === "tout" ? [...REFUS] : [v] })} options={[{ valeur: "tout", libelle: t("Tout ce qui ne colle pas", "Anything that does not match") }, ...REFUS.map((x) => ({ valeur: x, libelle: raisons[x] }))]} className="w-56" />
                    </Ligne>}
                    {reponse !== "silence" && <Ligne libelle={t("Temps de réponse", "Response time")} info={t("Au-delà du seuil de la phrase d'attente (1 500 ms par défaut), l'agent dit une phrase d'attente ; au-delà de 10 s la prise renonce.", "Beyond the waiting-sentence threshold (1,500 ms by default), the agent says a waiting sentence; beyond 10 s the socket gives up.")}>
                        <Nombre valeur={String(Math.round((c.delai_s ?? 0) * 1000))} min={0} max={30000} unite="ms" libelle={t("Temps de réponse", "Response time")} changer={(v) => poser({ delai_s: Math.max(0, Math.min(30, (Number(v) || 0) / 1000)) })} />
                    </Ligne>}
                    <Ligne libelle={t("Ensuite, en cuisine", "Then, in the kitchen")} info={t("Après avoir reçu la commande, la caisse la dit acceptée ou refusée par un message signé, comme une vraie caisse.", "After receiving the order, the till says it accepted or rejected it by a signed message, like a real till.")}>
                        <Segment3 valeur={c.acceptation ?? "auto"} options={acceptations} changer={(v) => poser({ acceptation: v })} />
                    </Ligne>
                </Champs>
            </Section>
            <Section titre={t("Imprévus", "Surprises")}>
                <Champs>
                    <Ligne libelle={t("Messages rendus deux fois", "Messages delivered twice")} info={t("Le même message signé arrive deux fois : la commande ne doit avancer qu'une fois. La rupture, le prix et l'état se changent en plein appel depuis la fenêtre Caisse / POS de l'essai.", "The same signed message arrives twice: the order must move forward only once. Stock-outs, prices and state change mid-call from the Till / POS window of the test.")}>
                        <Switch checked={!!c.doublon} aria-label={t("Messages rendus deux fois", "Messages delivered twice")} onCheckedChange={(v) => poser({ doublon: v })} />
                    </Ligne>
                </Champs>
            </Section>
            <Section titre={t("Garder ces réglages", "Keep these settings")}>
                <div className="flex flex-wrap items-center gap-2 py-2">
                    <Input value={nom} onChange={(e) => setNom(e.target.value)} placeholder={t("Nom du scénario", "Scenario name")} aria-label={t("Nom du scénario", "Scenario name")} className="h-8 w-64" />
                    <Button size="sm" variant="outline" disabled={!nom.trim()} onClick={() => void enregistrerUnScenario(r.id, nom.trim()).then(async (rep) => {
                        if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationEnregistrer);
                        setNom(""); notifier.succes({ fr: "Scénario enregistré.", en: "Scenario saved." }); await relire();
                    })}>{t("Enregistrer comme scénario", "Save as a scenario")}</Button>
                    <Button size="sm" variant="ghost" onClick={() => void mettreUnScenarioEnPlace(r.id, "tout-va-bien").then(async (rep) => {
                        if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationEnregistrer);
                        notifier.succes({ fr: "Caisse remise à « Tout va bien ».", en: "Till reset to “All good”." }); await relire();
                    })}>{t("Tout remettre à la normale", "Reset to normal")}</Button>
                </div>
            </Section>
        </div>
    );
}

function Scenarios({ r, scenarios, relire, versReglages }: { r: RestoDetail; scenarios: { cle: string; nom: string; etat: EtatResto; comportement: Comportement; livre?: boolean }[]; relire: () => Promise<void>; versReglages: () => void }) {
    const t = useTexte();
    const [sup, setSup] = useState<string | null>(null);
    const etats: Record<EtatResto, string> = { ouvert: t("ouvert", "open"), ferme: t("fermé", "closed"), deborde: t("débordé", "overloaded") };
    return (
        <div className="space-y-3">
            <Tableau colonnes={[{ titre: t("Scénario", "Scenario") }, { titre: t("Ce que fait la caisse", "What the till does"), secondaire: 1 }, { titre: "", droite: true }]}>
                {scenarios.map((s) => (
                    <LigneT key={s.cle}>
                        <Cellule principale>{s.nom}{r.scenario === s.cle && <span className="ml-3 font-normal"><PointEtat etat="publie">{t("en place", "active")}</PointEtat></span>}</Cellule>
                        <Cellule>{`${etats[s.etat]} · ${resume(s.comportement, t)}`}</Cellule>
                        <Cellule droite>
                            <span className="inline-flex items-center gap-1">
                                <Button size="sm" variant="outline" disabled={r.scenario === s.cle} onClick={() => void mettreUnScenarioEnPlace(r.id, s.cle).then(async (rep) => {
                                    if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationEnregistrer);
                                    notifier.succes({ fr: `« ${s.nom} » en place pour le prochain essai.`, en: `“${s.nom}” active for the next test.` }); await relire();
                                })}>{t("Mettre en place", "Apply")}</Button>
                                <Button size="icon" variant="ghost" className="size-8 text-muted-foreground" aria-label={t("Supprimer le scénario", "Delete scenario")} onClick={() => setSup(s.cle)}><Trash2 className="size-4" /></Button>
                            </span>
                        </Cellule>
                    </LigneT>))}
            </Tableau>
            <Button variant="ghost" size="sm" className="-ml-2" onClick={versReglages}><Plus className="size-4" /> {t("Nouveau scénario : réglez les comportements, puis enregistrez-les", "New scenario: set the behaviours, then save them")}</Button>
            {sup && <Confirmer titre={t("Supprimer ce scénario ?", "Delete this scenario?")} texte={t("Les réglages en place ne changent pas.", "The active settings do not change.")} bouton={t("Supprimer", "Delete")} fermer={() => setSup(null)}
                valider={() => void supprimerUnScenario(sup).then(async (rep) => {
                    if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationEnregistrer);
                    notifier.succes({ fr: "Scénario supprimé.", en: "Scenario deleted." }); await relire();
                })} />}
        </div>
    );
}

