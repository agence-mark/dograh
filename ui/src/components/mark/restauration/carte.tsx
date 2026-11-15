"use client";

/**
 * [.mark] Module Restauration, lot 12 (F2) : l'onglet « Carte » d'Entreprise.
 *
 * Reprend la maquette (`components/restauration/carte.tsx`) sur les vraies données (``GET …/carte``) : produits, groupes de choix, formules,
 * catégories, avec leur portée (toute l'enseigne, cet établissement, exception), leurs codes de caisse et leur source.
 *
 * Ce que l'écran écrit (les surcouches, toujours possibles, même quand la caisse tient la carte) : l'étoile « plus demandé », les synonymes
 * (et leur relecture), les ingrédients, les allergènes (inconnu et aucun distincts) et le drapeau alcool (en surcouche quand la caisse ou un fichier
 * porte le produit, en direct sinon), les ruptures (par la route de la caisse). Ce qu'il n'écrit pas : nom, prix, groupes, qui viennent de la caisse,
 * d'un import ou du portail ; il les montre en lecture.
 * Import : depuis la caisse (relit la prise), depuis un fichier au format commun (JSON). Le scan d'une carte papier n'est pas fait.
 */
import { BookOpen, FileUp, Plus, RefreshCw, Star, Upload, X } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { echecAffiche } from "../notifications/echec-affiche";
import { ECHECS } from "../notifications/phrases-echec";
import { EtatVide } from "../studio/etat-vide";
import { Champs, FenetreOnglets, LigneChamp as Ligne, Section } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Info, Marque, PointEtat } from "../studio/marques";
import { Cellule, Ligne as LigneT, Tableau } from "../studio/tableau";
import { EcranDonnees, euros, LigneSource, PorteePastille, Segment3, SelecteurEtab, useTexte } from "./commun";
import { useCharge, useModuleRestauration } from "./contexte";
import {
    type CarteRendue,
    ecrireLeProduit,
    type Formule,
    type Groupe,
    importerLaCarte,
    lireLaCarte,
    poserEtoile,
    poserLesSynonymes,
    poserUneRupture,
    type Produit,
    validerLesSynonymes,
} from "./donnees";

const ALLERGENES: { code: string; fr: string; en: string }[] = [
    { code: "gluten", fr: "Gluten", en: "Gluten" }, { code: "crustaces", fr: "Crustacés", en: "Crustaceans" }, { code: "oeufs", fr: "Œufs", en: "Eggs" },
    { code: "poissons", fr: "Poissons", en: "Fish" }, { code: "arachides", fr: "Arachides", en: "Peanuts" }, { code: "soja", fr: "Soja", en: "Soy" },
    { code: "lait", fr: "Lait", en: "Milk" }, { code: "fruits_a_coque", fr: "Fruits à coque", en: "Tree nuts" }, { code: "celeri", fr: "Céleri", en: "Celery" },
    { code: "moutarde", fr: "Moutarde", en: "Mustard" }, { code: "sesame", fr: "Sésame", en: "Sesame" }, { code: "sulfites", fr: "Sulfites", en: "Sulphites" },
    { code: "lupin", fr: "Lupin", en: "Lupin" }, { code: "mollusques", fr: "Mollusques", en: "Molluscs" },
];

const codesDe = (p: Produit): string[] => p.declinaisons.map((d) => d.code_caisse).filter((c): c is string => !!c);
/** Les codes en rupture AUJOURD'HUI : indisponibles, et dont la fin n'est pas passée. */
const ruptureActive = (carte: CarteRendue): Set<string> =>
    new Set(carte.ruptures.filter((r) => !r.disponible && (!r.fin || new Date(r.fin) > new Date())).map((r) => r.code_caisse));
const enRupture = (p: Produit, actives: Set<string>) => codesDe(p).length > 0 && codesDe(p).every((c) => actives.has(c));

function prixDit(p: Produit): string {
    const l = p.declinaisons.map((d) => d.prix);
    if (!l.length) return "–";
    const mn = Math.min(...l), mx = Math.max(...l);
    return mn === mx ? euros(mn) : `${euros(mn)} – ${euros(mx)}`;
}
const compteAllergenes = (p: Produit) => (p.allergenes === null ? { c: 0, inconnu: true } : { c: p.allergenes.length, inconnu: false });

export function OngletCarte() {
    const t = useTexte();
    const { etab } = useModuleRestauration();
    const { donnee: carte, etat, relire } = useCharge(etab === null ? null : () => lireLaCarte(etab), `carte-${etab}`, ECHECS.restaurationCarte);
    const [vue, setVue] = useState<"produits" | "groupes" | "formules" | "categories">("produits");
    const [produit, setProduit] = useState<string | null>(null);
    const [groupe, setGroupe] = useState<string | null>(null);
    const [formule, setFormule] = useState<string | null>(null);
    const [importer, setImporter] = useState(false);

    const actives = carte ? ruptureActive(carte) : new Set<string>();
    const lecture = carte?.lecture_seule ?? false;
    const bascule = async (cle: "etoile" | "rupture", p: Produit, fin?: Date | null) => {
        if (etab === null || !carte) return;
        if (cle === "etoile") {
            const r = await poserEtoile(etab, p.id, !p.etoile);
            if (r.error) return void echecAffiche(r.error, ECHECS.restaurationCarteEnregistrer);
            notifier.succes(p.etoile ? { fr: "Retiré des plus demandés.", en: "Removed from most requested." } : { fr: "Ajouté aux plus demandés : l'agent le cite en premier.", en: "Added to most requested: the agent mentions it first." });
        } else {
            const rupture = !enRupture(p, actives);
            const rendus = await Promise.all(codesDe(p).map((c) => poserUneRupture(etab, c, !rupture, rupture ? (fin ? fin.toISOString() : null) : null)));
            const erreur = rendus.find((r) => r.error)?.error;
            if (erreur) return void echecAffiche(erreur, ECHECS.restaurationCarteEnregistrer);
            notifier.succes(rupture ? { fr: `« ${p.nom} » est en rupture : l'agent ne le propose plus.`, en: `“${p.nom}” is out of stock: the agent stops offering it.` } : { fr: `« ${p.nom} » est de nouveau disponible.`, en: `“${p.nom}” is available again.` });
        }
        await relire();
    };

    const produits = carte?.produits ?? [];
    const categorie = (id: string | null) => carte?.categories.find((c) => c.id === id)?.nom;
    return (
        <EcranDonnees etat={etab === null ? "pret" : etat} relire={() => void relire()} vide={etab === null || (!!carte && !carte.produits.length && !carte.formules.length && !carte.groupes.length)} iconeVide={BookOpen} titreVide={etab === null ? t("Aucun établissement dans la base du client", "No site in the client's database") : t("Aucun produit dans la carte", "No product in the menu")}>
            <div className="flex flex-wrap items-center gap-3 pt-2">
                <SelecteurEtab />
                <span className="flex-1" />
                <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setImporter(true)}>
                    <Upload className="size-3.5" /> {t("Importer", "Import")}
                </Button>
            </div>
            {carte && <LigneSource caisse={lecture} prise={carte.prise} objet={t("Carte gérée", "Menu managed")} />}
            <div className="flex items-center gap-3">
                <Segment3
                    valeur={vue}
                    changer={setVue}
                    options={[
                        { v: "produits", l: `${t("Produits", "Products")} (${produits.length})` },
                        { v: "groupes", l: `${t("Groupes de choix", "Choice groups")} (${carte?.groupes.length ?? 0})` },
                        { v: "formules", l: `${t("Formules", "Set menus")} (${carte?.formules.length ?? 0})` },
                        { v: "categories", l: `${t("Catégories", "Categories")} (${carte?.categories.length ?? 0})` },
                    ]}
                />
                <Info>
                    {t(
                        "Les « plus demandés » (étoile), les synonymes, les ingrédients, les allergènes et les ruptures sont des surcouches : ils tiennent même quand la caisse relit la carte, rattachés par le code de caisse.",
                        "“Most requested” (star), synonyms, ingredients, allergens and out-of-stock are overlays: they survive when the till re-reads the menu, attached by till code.",
                    )}
                </Info>
            </div>

            {vue === "produits" && (
                <Tableau colonnes={[{ titre: t("Produit", "Product") }, { titre: t("Prix", "Price"), droite: true }, { titre: t("Allergènes", "Allergens"), secondaire: 2 }, { titre: t("Portée", "Scope"), secondaire: 3 }, { titre: t("Code de caisse", "Till code"), secondaire: 4 }, { titre: t("Synonymes", "Synonyms"), secondaire: 1 }, { titre: t("État", "Status") }, { titre: "", droite: true }]}>
                    {produits.map((p) => {
                        const a = compteAllergenes(p);
                        const codes = codesDe(p);
                        return (
                            <LigneT key={p.id} onClick={() => setProduit(p.id)}>
                                <Cellule principale sous={categorie(p.categorie_id)}>{p.nom}</Cellule>
                                <Cellule droite className="whitespace-nowrap">{prixDit(p)}</Cellule>
                                <Cellule>{a.inconnu ? t("inconnus", "unknown") : `${a.c} ${t("contient", "contains")}`}</Cellule>
                                <Cellule><PorteePastille portee={p.portee} /></Cellule>
                                <Cellule><span className="font-mono text-xs">{codes[0] ?? "–"}{codes.length > 1 ? ` +${codes.length - 1}` : ""}</span></Cellule>
                                <Cellule>{p.synonymes_a_relire.length > 0 ? <Marque ton="attention">{p.synonymes_a_relire.length} {t("à relire", "to review")}</Marque> : p.synonymes.length}</Cellule>
                                <Cellule>{enRupture(p, actives) ? <PointEtat etat="panne">{t("rupture", "out of stock")}</PointEtat> : <PointEtat etat="publie">{t("disponible", "available")}</PointEtat>}</Cellule>
                                <td className="pl-2 text-right" onClick={(e) => e.stopPropagation()}>
                                    <button type="button" aria-label={t("Plus demandé", "Most requested")} title={t("Plus demandé", "Most requested")} aria-pressed={p.etoile} onClick={() => void bascule("etoile", p)} className="cursor-pointer p-1 hover:scale-110">
                                        <Star className={`size-4 ${p.etoile ? "fill-foreground text-foreground" : "text-muted-foreground"}`} />
                                    </button>
                                </td>
                            </LigneT>
                        );
                    })}
                </Tableau>
            )}
            {vue === "groupes" && (
                <Tableau colonnes={[{ titre: t("Groupe de choix", "Choice group") }, { titre: t("Minimum", "Min"), droite: true }, { titre: t("Maximum", "Max"), droite: true }, { titre: t("Options", "Options"), secondaire: 2 }, { titre: t("Portée", "Scope"), secondaire: 1 }]}>
                    {(carte?.groupes ?? []).map((g) => (
                        <LigneT key={g.id} onClick={() => setGroupe(g.id)}>
                            <Cellule principale sous={g.role === "moities" ? t("moitié-moitié", "half and half") : undefined}>{g.nom}</Cellule>
                            <Cellule droite>{g.min}</Cellule>
                            <Cellule droite>{g.max}</Cellule>
                            <Cellule>{g.options.map((o) => o.nom).join(", ")}</Cellule>
                            <Cellule><PorteePastille portee={g.portee} /></Cellule>
                        </LigneT>
                    ))}
                </Tableau>
            )}
            {vue === "formules" && (
                <Tableau colonnes={[{ titre: t("Formule", "Set menu") }, { titre: t("Prix", "Price"), droite: true }, { titre: t("Code de caisse", "Till code"), secondaire: 1 }, { titre: t("Portée", "Scope"), secondaire: 2 }]}>
                    {(carte?.formules ?? []).map((f) => (
                        <LigneT key={f.id} onClick={() => setFormule(f.id)}>
                            <Cellule principale>{f.nom}</Cellule>
                            <Cellule droite>{euros(f.prix)}</Cellule>
                            <Cellule><span className="font-mono text-xs">{f.code_caisse ?? "–"}</span></Cellule>
                            <Cellule><PorteePastille portee={f.portee} /></Cellule>
                        </LigneT>
                    ))}
                </Tableau>
            )}
            {vue === "categories" && (
                <Tableau colonnes={[{ titre: t("Catégorie", "Category") }, { titre: t("Produits", "Products"), droite: true }, { titre: t("Ordre", "Order"), droite: true }]}>
                    {(carte?.categories ?? []).map((c) => (
                        <LigneT key={c.id}>
                            <Cellule principale>{c.nom}</Cellule>
                            <Cellule droite>{produits.filter((p) => p.categorie_id === c.id).length}</Cellule>
                            <Cellule droite>{c.ordre}</Cellule>
                        </LigneT>
                    ))}
                </Tableau>
            )}
            {etat === "pret" && vue === "produits" && produits.length === 0 && <EtatVide cas="premier" icone={BookOpen} titre={t("Aucun produit pour cet établissement", "No product for this site")} compact />}

            {carte && produit && produits.find((p) => p.id === produit) && (
                <PanneauProduit key={produit} carte={carte} produit={produits.find((p) => p.id === produit)!} actives={actives} lecture={lecture} etab={etab!} fermer={() => setProduit(null)} bascule={bascule} relire={relire} />
            )}
            {carte && groupe && carte.groupes.find((g) => g.id === groupe) && <PanneauGroupe g={carte.groupes.find((g) => g.id === groupe)!} fermer={() => setGroupe(null)} />}
            {carte && formule && carte.formules.find((f) => f.id === formule) && <PanneauFormule f={carte.formules.find((f) => f.id === formule)!} fermer={() => setFormule(null)} />}
            {importer && etab !== null && <FenetreImport etab={etab} peutLireLaCaisse={!!carte && carte.prise !== "portail"} fermer={() => setImporter(false)} relire={relire} />}
        </EcranDonnees>
    );
}

// ---- Un produit : fiche (lue), déclinaisons, choix, allergènes, synonymes (écrits) --------------------------------------------------------

const FINS: { cle: string; fr: string; en: string }[] = [
    { cle: "indefini", fr: "Jusqu'à nouvel ordre", en: "Until further notice" },
    { cle: "1h", fr: "Dans 1 h", en: "In 1 hour" },
    { cle: "soir", fr: "Ce soir 23:00", en: "Tonight 11 pm" },
    { cle: "demain", fr: "Demain 10:00", en: "Tomorrow 10 am" },
];
const finDe = (cle: string): Date | null => {
    const d = new Date();
    if (cle === "1h") return new Date(d.getTime() + 3_600_000);
    if (cle === "soir") return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 0, 0);
    if (cle === "demain") return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, 10, 0, 0);
    return null;
};

function PanneauProduit({ carte, produit: p, actives, lecture, etab, fermer, bascule, relire }: {
    carte: CarteRendue; produit: Produit; actives: Set<string>; lecture: boolean; etab: number; fermer: () => void;
    bascule: (cle: "etoile" | "rupture", p: Produit, fin?: Date | null) => Promise<void>; relire: () => Promise<void>;
}) {
    const t = useTexte();
    const { langue } = useLangue();
    const onglets = [t("Fiche", "Sheet"), t("Déclinaisons", "Variants"), t("Choix", "Choices"), t("Allergènes", "Allergens"), t("Synonymes", "Synonyms")];
    const [onglet, setOnglet] = useState(onglets[0]);
    const [actifs, setActifs] = useState<string[]>(p.synonymes);
    const [proposes, setProposes] = useState<string[]>(p.synonymes_a_relire);
    const [nouveau, setNouveau] = useState("");
    const [fin, setFin] = useState("indefini");
    // Ingrédients, allergènes et alcool : écrits en surcouche quand la caisse porte le produit (un réimport ne les écrase pas), en direct sinon.
    const ingredientsDe = (x: Produit) => x.ingredients.map((i) => ({ nom: i.nom, retirable: !!i.retirable }));
    const [ingredients, setIngredients] = useState<{ nom: string; retirable: boolean }[]>(ingredientsDe(p));
    const [nouvelIngredient, setNouvelIngredient] = useState("");
    const [allergenes, setAllergenes] = useState<string[] | null>(p.allergenes);
    const [alcool, setAlcool] = useState(!!p.alcool);
    const ingredientsModifies = JSON.stringify(ingredients) !== JSON.stringify(ingredientsDe(p));
    const allergenesModifies = JSON.stringify(allergenes) !== JSON.stringify(p.allergenes);
    const alcoolModifie = alcool !== !!p.alcool;
    const synonymesModifies = JSON.stringify(actifs) !== JSON.stringify(p.synonymes) || JSON.stringify(proposes) !== JSON.stringify(p.synonymes_a_relire);
    const modifie = synonymesModifies || ingredientsModifies || allergenesModifies || alcoolModifie;
    const lu = (v: string | null | undefined) => <span className="text-sm text-muted-foreground">{v || "–"}</span>;
    const rupture = enRupture(p, actives);
    const categorie = carte.categories.find((c) => c.id === p.categorie_id)?.nom ?? "";
    const enregistrer = async () => {
        if (ingredientsModifies || allergenesModifies || alcoolModifie) {
            const r = await ecrireLeProduit(etab, p.id, {
                ...(ingredientsModifies ? { ingredients } : {}), ...(allergenesModifies ? { allergenes } : {}), ...(alcoolModifie ? { alcool } : {}),
            });
            if (r.error) return void echecAffiche(r.error, ECHECS.restaurationCarteEnregistrer);
            notifier.succes({ fr: `« ${p.nom} » : fiche enregistrée.`, en: `“${p.nom}”: sheet saved.` });
        }
        if (synonymesModifies) {
            // Les propositions validées passent avec les synonymes actifs ; celles qu'on n'a pas validées sont retirées.
            const r = await poserLesSynonymes(etab, p.id, actifs);
            if (r.error) return void echecAffiche(r.error, ECHECS.restaurationCarteEnregistrer);
            notifier.succes({ fr: `« ${p.nom} » : synonymes enregistrés.`, en: `“${p.nom}”: synonyms saved.` });
        }
        if (modifie) await relire();
        fermer();
    };
    const validerProposes = async () => {
        const r = await validerLesSynonymes(etab, p.id, proposes);
        if (r.error) return void echecAffiche(r.error, ECHECS.restaurationCarteEnregistrer);
        setActifs([...actifs, ...proposes.filter((x) => !actifs.includes(x))]);
        setProposes([]);
        notifier.succes({ fr: "Propositions validées : l'agent les entend.", en: "Suggestions approved: the agent hears them." });
        await relire();
    };
    const ajouterIngredient = () => {
        const nom = nouvelIngredient.trim();
        if (nom && !ingredients.some((i) => i.nom.toLowerCase() === nom.toLowerCase())) setIngredients([...ingredients, { nom, retirable: false }]);
        setNouvelIngredient("");
    };
    const basculeAllergene = (code: string) =>
        setAllergenes((a) => ((a ?? []).includes(code) ? (a ?? []).filter((x) => x !== code) : [...(a ?? []), code]));
    const ajouter = () => {
        const mot = nouveau.trim();
        if (mot && !actifs.some((x) => x.toLowerCase() === mot.toLowerCase())) setActifs([...actifs, mot]);
        setNouveau("");
    };
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={p.nom}
            sous={<span className="flex items-center gap-2"><span className="font-mono text-xs">{codesDe(p).join(", ")}</span><PorteePastille portee={p.portee} /></span>}
            onglets={onglets}
            onglet={onglet}
            changerOnglet={setOnglet}
            modifie={modifie}
            valider={t("Enregistrer", "Save")}
            onValider={() => void enregistrer()}
        >
            {onglet === onglets[0] && (
                <>
                    <Section titre={t("Ce que dit l'agent", "What the agent says")} info={lecture ? t("Lus depuis la caisse : lecture seule.", "Read from the till: read-only.") : t("Le contenu de la carte vient de l'import ou du portail ; il se lit ici.", "The menu content comes from the import or the portal; it is read here.")}>
                        <Champs>
                            <Ligne libelle={t("Nom", "Name")}>{lu(p.nom)}</Ligne>
                            <Ligne libelle={t("Catégorie", "Category")}>{lu(categorie)}</Ligne>
                            <Ligne libelle={t("Description", "Description")}>{lu(p.description)}</Ligne>
                            <Ligne libelle={t("Origine", "Origin")}>{lu(p.origine)}</Ligne>
                            <Ligne libelle={t("Source", "Source")}>{lu(p.source)}</Ligne>
                        </Champs>
                    </Section>
                    <Section titre={t("Ingrédients", "Ingredients")} info={t("Dits seulement si l'appelant demande « il y a quoi dedans ». Un ingrédient « retirable » peut être enlevé à la demande. Écrits ici, ils survivent à une relecture de la carte.", "Said only when the caller asks what is in it. A “removable” ingredient can be left out on request. Written here, they survive a menu re-read.")}>
                        <div className="divide-y">
                            {ingredients.map((ing) => (
                                <div key={ing.nom} className="flex items-center gap-3 py-2.5 text-sm">
                                    <span className="flex-1 font-medium">{ing.nom}</span>
                                    <span className="text-xs text-muted-foreground">{t("retirable", "removable")}</span>
                                    <Switch checked={ing.retirable} onCheckedChange={(v) => setIngredients(ingredients.map((x) => (x.nom === ing.nom ? { ...x, retirable: v } : x)))} aria-label={`${t("Retirable", "Removable")} : ${ing.nom}`} />
                                    <button type="button" aria-label={`${t("Retirer", "Remove")} ${ing.nom}`} className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => setIngredients(ingredients.filter((x) => x.nom !== ing.nom))}><X className="size-4" /></button>
                                </div>
                            ))}
                            {ingredients.length === 0 && <p className="py-2 text-sm text-muted-foreground">{t("Aucun ingrédient renseigné.", "No ingredient filled in.")}</p>}
                        </div>
                        <div className="flex gap-2 pt-3">
                            <Input value={nouvelIngredient} onChange={(e) => setNouvelIngredient(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ajouterIngredient()} placeholder={t("Un ingrédient", "An ingredient")} className="h-8" aria-label={t("Nouvel ingrédient", "New ingredient")} />
                            <Button size="sm" variant="outline" className="cursor-pointer" disabled={!nouvelIngredient.trim()} onClick={ajouterIngredient}><Plus className="size-3.5" /> {t("Ajouter", "Add")}</Button>
                        </div>
                    </Section>
                    <Section titre={t("Surcouches (toujours modifiables)", "Overlays (always editable)")} info={t("Rattachées au code de caisse : elles survivent à une relecture de la carte.", "Attached to the till code: they survive a menu re-read.")}>
                        <Champs>
                            <Ligne libelle={t("Plus demandé (étoile)", "Most requested (star)")} info={t("L'agent le cite en premier quand on demande conseil.", "The agent mentions it first when asked for advice.")}>
                                <Switch checked={p.etoile} onCheckedChange={() => void bascule("etoile", p)} aria-label={t("Plus demandé", "Most requested")} />
                            </Ligne>
                            <Ligne libelle={t("Contient de l'alcool", "Contains alcohol")} info={t("Un titre-restaurant ne le paie pas (réglage « alcool exclu du titre »).", "A meal voucher does not pay for it (“alcohol excluded from vouchers” setting).")}>
                                <Switch checked={alcool} onCheckedChange={setAlcool} aria-label={t("Contient de l'alcool", "Contains alcohol")} />
                            </Ligne>
                            <Ligne libelle={t("En rupture", "Out of stock")} info={codesDe(p).length === 0 ? t("Ce produit n'a pas de code de caisse : il ne peut pas être mis en rupture.", "This product has no till code: it cannot be put out of stock.") : undefined}>
                                <Switch checked={rupture} disabled={codesDe(p).length === 0} onCheckedChange={() => void bascule("rupture", p, rupture ? null : finDe(fin))} aria-label={t("En rupture", "Out of stock")} />
                            </Ligne>
                            {!rupture && codesDe(p).length > 0 && (
                                <Ligne libelle={t("Jusqu'à", "Until")} info={t("Choisi avant de passer en rupture.", "Chosen before switching to out of stock.")}>
                                    <Liste valeur={fin} changer={setFin} options={FINS.map((f) => ({ valeur: f.cle, libelle: langue === "en" ? f.en : f.fr }))} className="w-48" libelle={t("Jusqu'à", "Until")} />
                                </Ligne>
                            )}
                        </Champs>
                    </Section>
                </>
            )}
            {onglet === onglets[1] && (
                <Section titre={t("Déclinaisons (tailles)", "Variants (sizes)")} info={t("Une déclinaison a son code de caisse et son prix en centimes. Le prix peut varier par mode.", "A variant has its till code and its price in cents. The price may vary by mode.")}>
                    <table className="w-full text-sm">
                        <thead className="border-b text-xs text-muted-foreground">
                            <tr>
                                <th className="py-2 text-left font-normal">{t("Déclinaison", "Variant")}</th>
                                <th className="pl-3 text-left font-normal">{t("Code de caisse", "Till code")}</th>
                                <th className="text-right font-normal">{t("Prix", "Price")}</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y">
                            {p.declinaisons.map((d) => (
                                <tr key={d.id}>
                                    <td className="py-2.5 font-medium">{d.nom}</td>
                                    <td className="pl-3 font-mono text-xs text-muted-foreground">{d.code_caisse ?? t("à renseigner", "to fill in")}</td>
                                    <td className="text-right tabular-nums">{euros(d.prix)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Section>
            )}
            {onglet === onglets[2] && (
                <Section titre={t("Groupes de choix rattachés", "Attached choice groups")}>
                    {p.groupes.length === 0 ? (
                        <p className="py-2 text-sm text-muted-foreground">{t("Aucun choix à faire pour ce produit.", "No choice to make for this product.")}</p>
                    ) : (
                        <div className="divide-y">
                            {p.groupes.map((id) => {
                                const g = carte.groupes.find((x) => x.id === id);
                                if (!g) return null;
                                return (
                                    <div key={id} className="py-3 text-sm">
                                        <p className="font-medium">{g.nom} <span className="font-normal text-muted-foreground">{`· ${t("min", "min")} ${g.min}, ${t("max", "max")} ${g.max}`}{g.role === "moities" ? ` · ${t("moitiés", "halves")}` : ""}</span></p>
                                        <p className="text-muted-foreground">{g.options.map((o) => o.nom + (o.prix ? ` (+${euros(o.prix)})` : "")).join(", ")}</p>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </Section>
            )}
            {onglet === onglets[3] && (
                <Section titre={t("Les 14 allergènes", "The 14 allergens")} info={t("Dits seulement si l'appelant parle d'allergie. Jamais « ne contient pas » par défaut : un doute reste « inconnu ».", "Said only if the caller mentions an allergy. Never “does not contain” by default: a doubt stays “unknown”.")}>
                    <div className="flex items-center gap-2 pb-3">
                        <Button size="sm" variant={allergenes === null ? "default" : "outline"} className="cursor-pointer" aria-pressed={allergenes === null} onClick={() => setAllergenes(null)}>{t("Inconnu", "Unknown")}</Button>
                        <Button size="sm" variant={allergenes !== null ? "default" : "outline"} className="cursor-pointer" aria-pressed={allergenes !== null} onClick={() => setAllergenes(allergenes ?? [])}>{t("Renseigné", "Filled in")}</Button>
                    </div>
                    <p className="pb-2 text-xs text-muted-foreground">
                        {allergenes === null
                            ? t("Un doute reste « inconnu » : l'agent ne dit jamais « ne contient pas ».", "A doubt stays “unknown”: the agent never says “does not contain”.")
                            : allergenes.length === 0
                              ? t("Aucun allergène : l'agent peut le dire.", "No allergen: the agent can say so.")
                              : t("Cochez ce que le produit contient.", "Tick what the product contains.")}
                    </p>
                    <div className="divide-y">
                        {ALLERGENES.map((a) => (
                            <div key={a.code} className="flex items-center gap-3 py-2 text-sm">
                                <span className="flex-1">{langue === "en" ? a.en : a.fr}</span>
                                {allergenes === null ? (
                                    <PointEtat etat="attente">{t("Inconnu", "Unknown")}</PointEtat>
                                ) : (
                                    <>
                                        <span className="text-xs text-muted-foreground">{allergenes.includes(a.code) ? t("Contient", "Contains") : t("Ne contient pas", "Does not contain")}</span>
                                        <Switch checked={allergenes.includes(a.code)} onCheckedChange={() => basculeAllergene(a.code)} aria-label={`${t("Contient", "Contains")} : ${langue === "en" ? a.en : a.fr}`} />
                                    </>
                                )}
                            </div>
                        ))}
                    </div>
                </Section>
            )}
            {onglet === onglets[4] && (
                <Section titre={t("Synonymes dits par les clients", "Synonyms said by customers")} info={t("Un synonyme proposé à l'import reste « à relire » : l'agent ne l'entend qu'après validation.", "A synonym proposed at import stays “to review”: the agent hears it only once approved.")}>
                    <div className="divide-y">
                        {actifs.map((mot) => (
                            <div key={mot} className="flex items-center gap-3 py-2.5 text-sm">
                                <span className="flex-1 font-medium">{mot}</span>
                                <PointEtat etat="publie">{t("actif", "active")}</PointEtat>
                                <button type="button" aria-label={`${t("Retirer", "Remove")} ${mot}`} className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => setActifs(actifs.filter((x) => x !== mot))}><X className="size-4" /></button>
                            </div>
                        ))}
                        {proposes.map((mot) => (
                            <div key={mot} className="flex items-center gap-3 py-2.5 text-sm">
                                <span className="flex-1 font-medium">{mot}</span>
                                <Marque ton="attention">{t("À relire", "To review")}</Marque>
                                <button type="button" aria-label={`${t("Retirer", "Remove")} ${mot}`} className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => setProposes(proposes.filter((x) => x !== mot))}><X className="size-4" /></button>
                            </div>
                        ))}
                        {actifs.length === 0 && proposes.length === 0 && <p className="py-2 text-sm text-muted-foreground">{t("Aucun synonyme.", "No synonym.")}</p>}
                    </div>
                    {proposes.length > 0 && (
                        <div className="flex items-center gap-2 pt-3">
                            <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => void validerProposes()}>{t("Valider les propositions", "Approve suggestions")}</Button>
                            <span className="text-xs text-muted-foreground">{t("Non validées, elles sont retirées à l'enregistrement.", "Not approved, they are dropped on save.")}</span>
                        </div>
                    )}
                    <div className="flex gap-2 pt-3">
                        <Input value={nouveau} onChange={(e) => setNouveau(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ajouter()} placeholder={t("Un mot dit par les clients", "A word customers say")} className="h-8" aria-label={t("Nouveau synonyme", "New synonym")} />
                        <Button size="sm" variant="outline" className="cursor-pointer" disabled={!nouveau.trim()} onClick={ajouter}><Plus className="size-3.5" /> {t("Ajouter", "Add")}</Button>
                    </div>
                </Section>
            )}
        </FenetreOnglets>
    );
}

function PanneauGroupe({ g, fermer }: { g: Groupe; fermer: () => void }) {
    const t = useTexte();
    return (
        <FenetreOnglets fermer={fermer} titre={g.nom} sous={<PorteePastille portee={g.portee} />} valider={null}>
            <Section titre={t("Règle du choix", "Choice rule")} info={t("Minimum 0 : le choix est facultatif. L'agent ne peut pas valider une ligne qui ne respecte pas le minimum ni le maximum.", "Minimum 0: the choice is optional. The agent cannot confirm a line outside the min and max.")}>
                <Champs>
                    <Ligne libelle={t("Minimum à choisir", "Minimum to pick")}><span className="text-sm text-muted-foreground">{g.min}</span></Ligne>
                    <Ligne libelle={t("Maximum à choisir", "Maximum to pick")}><span className="text-sm text-muted-foreground">{g.max}</span></Ligne>
                    {g.role === "moities" && <Ligne libelle={t("Type", "Type")}><span className="text-sm text-muted-foreground">{t("moitié-moitié", "half and half")}</span></Ligne>}
                </Champs>
            </Section>
            <Section titre={t("Options", "Options")}>
                <table className="w-full text-sm">
                    <thead className="border-b text-xs text-muted-foreground">
                        <tr>
                            <th className="py-2 text-left font-normal">{t("Option", "Option")}</th>
                            <th className="pl-3 text-left font-normal">{t("Retirable", "Removable")}</th>
                            <th className="text-right font-normal">{t("Supplément", "Extra")}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y">
                        {g.options.map((o) => (
                            <tr key={o.id}>
                                <td className="py-2.5 font-medium">{o.nom}</td>
                                <td className="pl-3 text-muted-foreground">{o.retirable ? t("oui", "yes") : "–"}</td>
                                <td className="text-right tabular-nums">{o.prix ? `+${euros(o.prix)}` : "–"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Section>
        </FenetreOnglets>
    );
}

function PanneauFormule({ f, fermer }: { f: Formule; fermer: () => void }) {
    const t = useTexte();
    return (
        <FenetreOnglets fermer={fermer} titre={f.nom} sous={<span className="flex items-center gap-2"><span className="font-mono text-xs">{f.code_caisse ?? "–"}</span><PorteePastille portee={f.portee} /></span>} valider={null}>
            <Section titre={t("Formule", "Set menu")}>
                <Champs>
                    <Ligne libelle={t("Prix", "Price")}><span className="text-sm text-muted-foreground">{euros(f.prix)}</span></Ligne>
                </Champs>
            </Section>
        </FenetreOnglets>
    );
}

// ---- Import : depuis la caisse, depuis un fichier ------------------------------------------------------------------------------------------

function FenetreImport({ etab, peutLireLaCaisse, fermer, relire }: { etab: number; peutLireLaCaisse: boolean; fermer: () => void; relire: () => Promise<void> }) {
    const t = useTexte();
    const [choix, setChoix] = useState<"caisse" | "fichier">(peutLireLaCaisse ? "caisse" : "fichier");
    const [fichier, setFichier] = useState<{ nom: string; carte: Record<string, unknown> } | null>(null);
    const [faute, setFaute] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const entree = useRef<HTMLInputElement>(null);
    const lireLeFichier = async (f: File | undefined) => {
        if (!f) return;
        setFaute(null);
        try {
            const carte = JSON.parse(await f.text());
            if (!carte || typeof carte !== "object" || Array.isArray(carte)) throw new Error("format");
            setFichier({ nom: f.name, carte });
        } catch {
            setFichier(null);
            setFaute(t("Ce fichier n'est pas une carte au format commun (JSON).", "This file is not a menu in the common format (JSON)."));
        }
    };
    const lancer = async () => {
        setEnCours(true);
        const cours = notifier.enCours({ fr: "Import de la carte en cours…", en: "Importing the menu…" });
        const r = await importerLaCarte(etab, choix, choix === "fichier" ? fichier?.carte : undefined);
        setEnCours(false);
        if (r.error || !r.data) {
            cours.echec(ECHECS.restaurationImport, { erreur: r.error });
            return;
        }
        const b = r.data;
        cours.succes({
            fr: `Carte importée : ${b.ajoutes} ajoutés, ${b.changes} changés, ${b.retires} retirés.${b.synonymes_proposes ? ` ${b.synonymes_proposes} produits ont des synonymes à relire.` : ""}`,
            en: `Menu imported: ${b.ajoutes} added, ${b.changes} changed, ${b.retires} removed.${b.synonymes_proposes ? ` ${b.synonymes_proposes} products have synonyms to review.` : ""}`,
        });
        await relire();
        fermer();
    };
    const CHOIX = [
        { id: "caisse" as const, icone: RefreshCw, titre: t("Depuis la caisse", "From the till"), sous: peutLireLaCaisse ? t("Relit la carte de la caisse branchée maintenant.", "Reads the menu of the plugged-in till now.") : t("Aucune caisse branchée à cet établissement.", "No till plugged in to this site."), ok: peutLireLaCaisse },
        { id: "fichier" as const, icone: FileUp, titre: t("Depuis un fichier", "From a file"), sous: t("La carte au format commun (JSON).", "The menu in the common format (JSON)."), ok: true },
    ];
    return (
        <FenetreOnglets fermer={fermer} titre={t("Importer la carte", "Import the menu")} valider={t("Lancer l'import", "Start import")} onValider={() => void lancer()} desactiver={enCours || (choix === "fichier" && !fichier) || (choix === "caisse" && !peutLireLaCaisse)} centree={false}>
            <p className="pb-3 text-sm text-muted-foreground">{t("Rien n'est écrasé : ce qu'une personne a écrit (synonymes, étoiles, lignes tenues à la main) reste.", "Nothing is overwritten: what a person wrote (synonyms, stars, hand-kept lines) stays.")}</p>
            <div className="grid gap-3">
                {CHOIX.map((c) => (
                    <button key={c.id} type="button" disabled={!c.ok} aria-pressed={choix === c.id} onClick={() => setChoix(c.id)} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 text-left disabled:cursor-not-allowed disabled:opacity-50 ${choix === c.id ? "border-primary bg-muted/50 dark:border-white" : "hover:bg-muted/50"}`}>
                        <c.icone className="mt-0.5 size-5 text-muted-foreground" />
                        <span>
                            <span className="block text-sm font-medium">{c.titre}</span>
                            <span className="block text-xs text-muted-foreground">{c.sous}</span>
                        </span>
                    </button>
                ))}
                <p className="text-xs text-muted-foreground">{t("Le scan d'une carte papier n'est pas encore disponible.", "Scanning a paper menu is not available yet.")}</p>
            </div>
            {choix === "fichier" && (
                <div className="space-y-2 pt-4">
                    <input ref={entree} type="file" accept="application/json,.json" className="hidden" onChange={(e) => void lireLeFichier(e.target.files?.[0])} />
                    <div className="flex items-center gap-3">
                        <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => entree.current?.click()}><Upload className="size-3.5" /> {t("Choisir le fichier", "Choose the file")}</Button>
                        <span className="text-sm text-muted-foreground">{fichier?.nom ?? t("Aucun fichier choisi", "No file chosen")}</span>
                    </div>
                    {faute && <p role="alert" className="text-sm text-destructive">{faute}</p>}
                </div>
            )}
        </FenetreOnglets>
    );
}
