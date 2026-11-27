"use client";

/**
 * [.mark] Module Restauration, lot 12 (F4) : l'onglet « Réglages restaurant » d'Entreprise.
 *
 * Six parties, reprises de la maquette (`reglages-restaurant.tsx`) sur les vraies données (``GET …/reglages``, ``…/temps``, ``…/historique``) :
 * Sources, Horaires, Commandes (types, planifiées, paiement, numéro, notes, seuils de la liaison), Temps d'attente (la puce, l'aperçu de ce que l'agent
 * annonce, le format, les soirs toujours chargés), Envois SMS, Historique.
 *
 * Vrai à l'écran, rien de simulé : l'aperçu est ce que le serveur annonce MAINTENANT ; une source n'est pas un interrupteur (elle suit la prise
 * branchée et sa fiche de capacités) ; un objet que la caisse porte peut être tenu ICI (interrupteur : carte, ruptures, état, horaires), le comptoir
 * ne le lit alors plus chez la caisse. Les horaires se règlent dans la fiche de l'établissement ; les fermetures exceptionnelles s'écrivent ici (jour de
 * début et de fin inclus) ; la pause de la caisse met le téléphone en pause (T-05), décochable. Les envois autres que « heure changée »
 * (faits au lot 13 : les sept envois du mécanisme du lot 7, éteints par défaut).
 */
import { Lock, Pause, Play, Plus, Settings2, Trash2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { echecAffiche } from "../notifications/echec-affiche";
import { ECHECS } from "../notifications/phrases-echec";
import { Defileur } from "../studio/defileur";
import { BlocChamp as Bloc, Champs, FenetreOnglets, LigneChamp as Ligne, Section, Segmente } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Info, Marque, PointEtat } from "../studio/marques";
import { Cellule, Ligne as LigneT, Tableau, TitreTableau } from "../studio/tableau";
import { AUCUN_ETABLISSEMENT,centimes, EcranDonnees, Nombre, SelecteurEtab, useTexte } from "./commun";
import { useCharge, useModuleRestauration } from "./contexte";
import {
    ecrireLesReglages,
    type FermetureExceptionnelle,
    type FormatAnnonce,
    type LigneDHistorique,
    lireLesReglages,
    lireLeTemps,
    lireLHistorique,
    type MoyenDePaiement,
    type ObjetReglable,
    poserLeTemps,
    type ReglagesChanges,
    type ReglagesRendus,
    type TempsRecurrent,
    type TempsRendu,
    type TypeDeCommande,
    type TypeReglage,
} from "./donnees";
import { type DeclencheurDEnvoi, ecrireLesEnvois, type EnvoiLu, lireLesEnvois } from "./donnees-salle";

const PARTIES = ["sources", "horaires", "commandes", "attente", "envois", "historique"] as const;
type Partie = (typeof PARTIES)[number];
const TYPES_OUVERTS: TypeDeCommande[] = ["emporter", "livraison", "sur_place"];

export function OngletReglagesRestaurant() {
    const t = useTexte();
    const { etab } = useModuleRestauration();
    const [partie, setPartie] = useState<Partie>("sources");
    const reglages = useCharge(etab === null ? null : () => lireLesReglages(etab), `reglages-${etab}`, ECHECS.restaurationReglages);
    const temps = useCharge(etab === null ? null : () => lireLeTemps(etab), `temps-${etab}`, ECHECS.restaurationReglages);
    const noms: Record<Partie, string> = { sources: t("Sources", "Sources"), horaires: t("Horaires", "Hours"), commandes: t("Commandes", "Orders"), attente: t("Temps d'attente", "Waiting time"), envois: t("Envois SMS", "SMS sending"), historique: t("Historique", "History") };
    const etat = etab === null ? "pret" : reglages.etat === "erreur" || temps.etat === "erreur" ? "erreur" : reglages.etat === "chargement" || temps.etat === "chargement" ? "chargement" : "pret";
    const r = reglages.donnee;
    return (
        <EcranDonnees etat={etat} relire={() => { void reglages.relire(); void temps.relire(); }} vide={etab === null} iconeVide={Settings2} titreVide={t(AUCUN_ETABLISSEMENT.fr, AUCUN_ETABLISSEMENT.en)}>
            <div className="flex flex-wrap items-center gap-3 pt-2"><SelecteurEtab /></div>
            <Defileur className="border-b">
                {PARTIES.map((p) => (
                    <button key={p} type="button" onClick={() => setPartie(p)} className={`-mb-px cursor-pointer rounded-t-md border-b-2 px-3 py-2.5 text-sm outline-none focus-visible:bg-muted ${partie === p ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:font-medium hover:text-foreground"}`}>
                        {noms[p]}
                    </button>
                ))}
            </Defileur>
            {r && etab !== null && (
                <>
                    {partie === "sources" && <Sources key={etab} etab={etab} r={r} poser={reglages.poser} />}
                    {partie === "horaires" && <Horaires key={etab} etab={etab} r={r} poser={reglages.poser} />}
                    {partie === "commandes" && <Commandes key={etab} etab={etab} r={r} temps={temps.donnee} poser={reglages.poser} relireTemps={temps.relire} />}
                    {partie === "attente" && <Attente key={etab} etab={etab} r={r} temps={temps.donnee} poser={reglages.poser} poserTemps={temps.poser} />}
                    {partie === "envois" && <Envois key={etab} etab={etab} r={r} poser={reglages.poser} />}
                    {partie === "historique" && <Historique key={etab} etab={etab} />}
                </>
            )}
        </EcranDonnees>
    );
}

/** Écrit des changements de réglages, remplace l'état par ce que la route rend, dit le résultat. */
async function enregistrer(etab: number, changes: ReglagesChanges, poser: (r: ReglagesRendus) => void, message: { fr: string; en: string }): Promise<boolean> {
    const r = await ecrireLesReglages(etab, changes);
    if (r.error || !r.data) {
        echecAffiche(r.error, ECHECS.restaurationReglagesEnregistrer);
        return false;
    }
    poser(r.data);
    notifier.succes(message);
    return true;
}

// ---- Sources : qui tient quoi (suit la prise branchée) ---------------------------------------------------------------------------------------

function Sources({ etab, r, poser }: { etab: number; r: ReglagesRendus; poser: (r: ReglagesRendus) => void }) {
    const t = useTexte();
    const { langue } = useLangue();
    const NOMS = { carte: { fr: "Carte et prix", en: "Menu and prices" }, ruptures: { fr: "Ruptures", en: "Out of stock" }, etat: { fr: "État du restaurant", en: "Restaurant state" }, horaires: { fr: "Horaires", en: "Opening hours" }, remises: { fr: "Remises", en: "Discounts" }, clients: { fr: "Clients", en: "Customers" } } as const;
    const sansCaisse = r.prise === "portail";
    const tenirIci = (objet: ObjetReglable, ici: boolean) =>
        void enregistrer(etab, { reglage: { sources: { [objet]: ici ? "ici" : "caisse" } } }, poser, ici ? { fr: `${NOMS[objet].fr} : tenu ici, la caisse n'est plus lue.`, en: `${NOMS[objet].en}: kept here, the till is no longer read.` } : { fr: `${NOMS[objet].fr} : lu dans la caisse.`, en: `${NOMS[objet].en}: read from the till.` });
    return (
        <>
            <TitreTableau titre={t("Qui tient quoi", "Who keeps what")} info={<Info>{t("Un maître par objet : la caisse ou ici. Il suit la caisse branchée à cet établissement et ce que sa fiche de capacités sait lire ; on peut choisir de tenir un objet ici, la caisse n'est alors plus lue pour lui (la caisse prime tant que l'interrupteur est éteint).", "One master per object: the till or here. It follows the till plugged in to this site and what its capability sheet can read; an object can be kept here, the till is then no longer read for it (the till wins while the switch is off).")}</Info>} />
            <div className="divide-y border-y">
                {r.sources.map((s) => (
                    <div key={s.objet} className="flex items-center gap-4 py-3.5">
                        <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium">{NOMS[s.objet][langue]}</p>
                            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                                {s.mode === "caisse" && <Lock className="size-3" />}
                                {s.mode === "caisse"
                                    ? t(`Lu dans la caisse (${r.prise}). Lecture seule ici.`, `Read from the till (${r.prise}). Read-only here.`)
                                    : s.reglable
                                      ? t("Tenu ici : la caisse n'est plus lue pour cet objet.", "Kept here: the till is no longer read for this object.")
                                      : sansCaisse
                                      ? t("Tenu ici : le restaurant le modifie depuis son portail.", "Kept here: the restaurant edits it from its portal.")
                                      : s.prise_sait
                                        ? t("La caisse sait le lire, mais la liaison n'est pas en état : tenu ici en attendant.", "The till can read it, but the link is not healthy: kept here meanwhile.")
                                        : t(`${r.prise} ne sait pas lire « ${NOMS[s.objet].fr.toLowerCase()} » : tenu ici.`, `${r.prise} cannot read “${NOMS[s.objet].en.toLowerCase()}”: kept here.`)}
                            </p>
                        </div>
                        {s.reglable && (
                            <span className="flex items-center gap-2 text-xs text-muted-foreground">
                                {t("Tenir ici", "Keep here")}
                                <Switch checked={s.mode === "ici"} onCheckedChange={(v) => tenirIci(s.objet as ObjetReglable, v)} aria-label={`${NOMS[s.objet][langue]} : ${t("tenir ici", "keep here")}`} />
                            </span>
                        )}
                        <Marque ton={s.mode === "caisse" ? "plein" : "neutre"}>{s.mode === "caisse" ? t("Ma caisse", "My till") : t("Ici", "Here")}</Marque>
                    </div>
                ))}
            </div>
        </>
    );
}

// ---- Horaires : ceux de la fiche de l'établissement, et ceux de la caisse ---------------------------------------------------------------------------

const JOURS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
function Horaires({ etab, r, poser }: { etab: number; r: ReglagesRendus; poser: (r: ReglagesRendus) => void }) {
    const t = useTexte();
    const { langue } = useLangue();
    const [fermetures, setFermetures] = useState<FermetureExceptionnelle[]>(r.fermetures);
    const [nouvelle, setNouvelle] = useState<{ du: string; au: string; motif: string }>({ du: "", au: "", motif: "" });
    const modifie = JSON.stringify(fermetures) !== JSON.stringify(r.fermetures);
    const ajouter = () => {
        if (!nouvelle.du) return;
        setFermetures([...fermetures, { du: nouvelle.du, au: nouvelle.au && nouvelle.au >= nouvelle.du ? nouvelle.au : nouvelle.du, motif: nouvelle.motif.trim() || null }]);
        setNouvelle({ du: "", au: "", motif: "" });
    };
    const sauver = async () => {
        if (await enregistrer(etab, { fermetures: fermetures.map((f) => ({ id: f.id ?? null, du: f.du, au: f.au, motif: f.motif ?? null })) }, (x) => { poser(x); setFermetures(x.fermetures); }, { fr: "Fermetures exceptionnelles enregistrées : l'agent les dit.", en: "Exceptional closures saved: the agent tells callers." })) setNouvelle({ du: "", au: "", motif: "" });
    };
    const noms: Record<(typeof JOURS)[number], [string, string]> = { monday: ["Lundi", "Monday"], tuesday: ["Mardi", "Tuesday"], wednesday: ["Mercredi", "Wednesday"], thursday: ["Jeudi", "Thursday"], friday: ["Vendredi", "Friday"], saturday: ["Samedi", "Saturday"], sunday: ["Dimanche", "Sunday"] };
    const delaCaisse = r.sources.find((s) => s.objet === "horaires")?.mode === "caisse";
    const horaires = delaCaisse && r.horaires_caisse ? (r.horaires_caisse as Record<string, { from: string; to: string }[]>) : r.horaires_fiche;
    return (
        <>
            <TitreTableau
                titre={t("Horaires d'ouverture", "Opening hours")}
                info={<Info>{t("Quand la caisse porte les horaires, ils viennent d'elle et se lisent ici. Sinon ils se règlent dans la fiche de l'établissement (Établissements). Les fermetures exceptionnelles se règlent plus bas.", "When the till carries the hours, they come from it and are read here. Otherwise they are set in the site's sheet (Establishments). Exceptional closures are set below.")}</Info>}
            />
            <div className="divide-y border-y">
                {JOURS.map((j) => {
                    const plages = horaires[j] ?? [];
                    return (
                        <div key={j} className="flex items-center gap-4 py-3 text-sm">
                            <span className="w-40 text-muted-foreground">{noms[j][langue === "en" ? 1 : 0]}</span>
                            <span className="flex flex-1 items-center gap-2">
                                {plages.length ? plages.map((p) => `${p.from}-${p.to}`).join(" · ") : t("fermé", "closed")}
                                {delaCaisse && <Lock className="size-3.5 text-muted-foreground" aria-label={t("Lu dans la caisse", "Read from the till")} />}
                            </span>
                        </div>
                    );
                })}
            </div>
            <TitreTableau titre={t("Fermetures exceptionnelles", "Exceptional closures")} info={<Info>{t("Un jour ou plusieurs (début et fin inclus) où le restaurant est fermé malgré ses horaires : congés, mariage, travaux. L'agent dit qu'on est fermé et ne prend pas de commande.", "One or several days (start and end included) when the restaurant is closed despite its hours: holidays, event, works. The agent says it is closed and takes no order.")}</Info>} />
            <div className="divide-y border-y">
                {fermetures.map((f, i) => (
                    <div key={f.id ?? `n${i}`} className="flex items-center gap-3 py-2.5 text-sm">
                        <Input type="date" value={f.du} onChange={(e) => setFermetures(fermetures.map((x, k) => (k === i ? { ...x, du: e.target.value, au: x.au < e.target.value ? e.target.value : x.au } : x)))} className="h-8 w-40" aria-label={t("Du", "From")} />
                        <span className="text-muted-foreground">{t("au", "to")}</span>
                        <Input type="date" value={f.au} min={f.du} onChange={(e) => setFermetures(fermetures.map((x, k) => (k === i ? { ...x, au: e.target.value } : x)))} className="h-8 w-40" aria-label={t("Au", "To")} />
                        <Input value={f.motif ?? ""} maxLength={120} onChange={(e) => setFermetures(fermetures.map((x, k) => (k === i ? { ...x, motif: e.target.value } : x)))} placeholder={t("Motif (facultatif)", "Reason (optional)")} className="h-8 flex-1" aria-label={t("Motif", "Reason")} />
                        <button type="button" aria-label={t("Retirer cette fermeture", "Remove this closure")} className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => setFermetures(fermetures.filter((_, k) => k !== i))}><Trash2 className="size-4" /></button>
                    </div>
                ))}
                {fermetures.length === 0 && <p className="py-3 text-sm text-muted-foreground">{t("Aucune fermeture exceptionnelle à venir.", "No upcoming exceptional closure.")}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-1">
                <Input type="date" value={nouvelle.du} onChange={(e) => setNouvelle({ ...nouvelle, du: e.target.value })} className="h-8 w-40" aria-label={t("Premier jour fermé", "First closed day")} />
                <Input type="date" value={nouvelle.au} min={nouvelle.du} onChange={(e) => setNouvelle({ ...nouvelle, au: e.target.value })} className="h-8 w-40" aria-label={t("Dernier jour fermé", "Last closed day")} />
                <Input value={nouvelle.motif} maxLength={120} onChange={(e) => setNouvelle({ ...nouvelle, motif: e.target.value })} placeholder={t("Motif (facultatif)", "Reason (optional)")} className="h-8 min-w-40 flex-1" aria-label={t("Motif de la nouvelle fermeture", "Reason of the new closure")} />
                <Button size="sm" variant="outline" className="cursor-pointer" disabled={!nouvelle.du} onClick={ajouter}><Plus className="size-3.5" /> {t("Ajouter", "Add")}</Button>
                <Button size="sm" className="cursor-pointer" disabled={!modifie} onClick={() => void sauver()}>{t("Enregistrer", "Save")}</Button>
            </div>
            {r.caisse_porte_l_etat && <p className="text-xs text-muted-foreground">{t("L'état du restaurant (normal, débordé, pause) est porté par la caisse.", "The restaurant state (normal, busy, pause) is carried by the till.")}</p>}
            {r.horaires_caisse && !delaCaisse && <p className="text-xs text-muted-foreground">{t("La caisse envoie aussi ses horaires : ils ne remplacent jamais ceux de la fiche.", "The till also sends its hours: they never replace the sheet's.")}</p>}
        </>
    );
}

// ---- Commandes : types, planifiées, paiement, numéro, notes, seuils -----------------------------------------------------------------------------

const NOM_TYPE: Record<TypeDeCommande, [string, string]> = { emporter: ["À emporter", "Pickup"], livraison: ["Livraison", "Delivery"], sur_place: ["Sur place", "Dine-in"], reservation: ["Réservation", "Booking"] };
export const MOYENS: { code: MoyenDePaiement; fr: string; en: string }[] = [
    { code: "carte", fr: "Carte bancaire", en: "Bank card" }, { code: "especes", fr: "Espèces", en: "Cash" }, { code: "carte_livraison", fr: "Carte à la livraison", en: "Card on delivery" }, { code: "titre_restaurant", fr: "Titre-restaurant ou carte restaurant", en: "Meal voucher or card" },
    { code: "cheque", fr: "Chèque", en: "Cheque" }, { code: "en_ligne", fr: "Paiement en ligne", en: "Online payment" },
];

const finUnique = (fin: Record<string, string>) => {
    const valeurs = new Set(Object.values(fin));
    return valeurs.size === 1 && Object.keys(fin).length === 7 ? [...valeurs][0] : valeurs.size === 0 ? "" : null;
};

function Commandes({ etab, r, temps, poser, relireTemps }: { etab: number; r: ReglagesRendus; temps: TempsRendu | null; poser: (r: ReglagesRendus) => void; relireTemps: () => Promise<void> }) {
    const t = useTexte();
    const { langue } = useLangue();
    const [types, setTypes] = useState<TypeReglage[]>(r.types);
    const [reglage, setReglage] = useState(r.reglage);
    const [plafond, setPlafond] = useState(r.reglage.plafond_titre_restaurant === null ? "" : String(r.reglage.plafond_titre_restaurant / 100));
    const [seuils, setSeuils] = useState(r.seuils);
    const [imprimante, setImprimante] = useState(r.imprimante);
    const lecturePuce = temps?.lecture_seule ?? false;
    const touche = (nom: TypeDeCommande, patch: Partial<TypeReglage>) => setTypes(types.map((x) => (x.type === nom ? { ...x, ...patch } : x)));
    const exemple = reglage.numero_mode === "aucun" ? "12, 13, 35" : reglage.numero_mode === "moyen" ? `CB12, ESP13, TR35, ${reglage.prefixe_mixte || "MIX"}14` : "L12, E13";

    const pause = async (nom: TypeDeCommande, enPause: boolean) => {
        const ligne = temps?.types.find((x) => x.type === nom);
        if (!ligne) return;
        // La puce REMPLACE la durée ajoutée : on renvoie celle du type pour ne pas l'effacer.
        const rendu = await poserLeTemps(etab, { type: nom, minutes_ajoutees: ligne.minutes_ajoutees, jusqu_a: ligne.ajout_jusqu_a, pause: enPause ? null : {} });
        if (rendu.error) return void echecAffiche(rendu.error, ECHECS.restaurationTemps);
        notifier.succes(enPause ? { fr: "Reprise des commandes.", en: "Orders resumed." } : { fr: "Pause : l'agent le dit aux appelants.", en: "Paused: the agent tells callers." });
        await relireTemps();
    };
    const sauver = () => {
        const changes: ReglagesChanges = {
            types: types.filter((x) => x.type !== "reservation").map((x) => ({ type: x.type, ouvert: x.ouvert, fin_par_jour: x.fin_par_jour, planifiee_permise: x.planifiee_permise, delai_minimal: x.delai_minimal, jours_a_l_avance: x.jours_a_l_avance })) as ReglagesChanges["types"],
            reglage: {
                moyens_paiement: reglage.moyens_paiement, plafond_titre_restaurant: reglage.moyens_paiement.includes("titre_restaurant") && plafond !== "" ? centimes(plafond) : undefined, numero_mode: reglage.numero_mode,
                prefixe_mixte: reglage.prefixe_mixte, prefixe_numero_court: reglage.prefixe_numero_court, notes_libres: reglage.notes_libres, titre_alcool_exclu: reglage.titre_alcool_exclu, titre_sans_rendu: reglage.titre_sans_rendu, pause_caisse_pause_telephone: reglage.pause_caisse_pause_telephone,
                conservation_client_mois: reglage.conservation_client_mois, filet_retenue_min: reglage.filet_retenue_min,
            },
            ...(seuils ? { seuils: { alerte_sans_reponse_min: seuils.alerte_sans_reponse_min, releve_messages_min: seuils.releve_messages_min } } : {}),
            ...(imprimante ? { imprimante } : {}),
        };
        void enregistrer(etab, changes, poser, { fr: "Réglages des commandes enregistrés.", en: "Order settings saved." });
    };
    return (
        <>
            <TitreTableau titre={t("Types de commande", "Order types")} info={<Info>{t("Chaque type s'ouvre ou se met en pause : bouton manuel, et heure de fin habituelle. L'agent dit « les livraisons sont terminées ».", "Each type opens or pauses: manual button, plus usual end time. The agent says “deliveries are over”.")}</Info>} />
            <Tableau colonnes={[{ titre: t("Type", "Type") }, { titre: t("Ouvert", "Open") }, { titre: t("Heure de fin", "End time"), secondaire: 1 }, { titre: t("Pause manuelle", "Manual pause"), droite: true }]}>
                {TYPES_OUVERTS.map((nom) => {
                    const x = types.find((y) => y.type === nom)!;
                    const ligne = temps?.types.find((y) => y.type === nom);
                    const enPause = !!ligne?.pause_jusqu_a;
                    const fin = finUnique(x.fin_par_jour);
                    return (
                        <LigneT key={nom}>
                            <Cellule principale sous={enPause ? t("en pause", "paused") : undefined}>{NOM_TYPE[nom][langue === "en" ? 1 : 0]}</Cellule>
                            <td className="pl-4"><Switch checked={x.ouvert} onCheckedChange={(v) => touche(nom, { ouvert: v })} aria-label={`${NOM_TYPE[nom][langue === "en" ? 1 : 0]} : ${t("ouvert", "open")}`} /></td>
                            <td className="pl-4">
                                <Input type="time" value={fin ?? ""} placeholder={fin === null ? t("variable", "varies") : ""} onChange={(e) => touche(nom, { fin_par_jour: e.target.value ? Object.fromEntries([1, 2, 3, 4, 5, 6, 7].map((j) => [String(j), e.target.value])) : {} })} className="h-8 w-28" aria-label={t("Heure de fin", "End time")} />
                            </td>
                            <td className="text-right">
                                <Button variant="outline" size="sm" className="cursor-pointer" disabled={lecturePuce || !ligne} onClick={() => void pause(nom, enPause)}>
                                    {enPause ? <><Play className="size-3.5" /> {t("Reprendre", "Resume")}</> : <><Pause className="size-3.5" /> {t("Mettre en pause", "Pause")}</>}
                                </Button>
                            </td>
                        </LigneT>
                    );
                })}
            </Tableau>
            {lecturePuce && <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Lock className="size-3" /> {t("L'état de l'établissement est porté par la caisse : la pause se fait là-bas.", "The site's state is carried by the till: pause there.")}</p>}

            <Section titre={t("Commandes planifiées", "Scheduled orders")} info={t("Date, heure, type, articles : permise y compris fermé, l'agent le dit et propose de planifier.", "Date, time, type, items: allowed even when closed; the agent says so and offers to schedule.")}>
                <Champs>
                    {(["emporter", "livraison"] as TypeDeCommande[]).map((nom) => {
                        const x = types.find((y) => y.type === nom)!;
                        const n = NOM_TYPE[nom][langue === "en" ? 1 : 0];
                        return (
                            <div key={nom}>
                                <Ligne libelle={`${t("Permettre les commandes planifiées", "Allow scheduled orders")} · ${n}`}><Switch checked={x.planifiee_permise} onCheckedChange={(v) => touche(nom, { planifiee_permise: v })} aria-label={`${t("Planifiées", "Scheduled")} ${n}`} /></Ligne>
                                {x.planifiee_permise && (
                                    <>
                                        <Ligne libelle={t("Délai minimal", "Minimum lead time")}><Nombre valeur={String(x.delai_minimal)} changer={(v) => touche(nom, { delai_minimal: Math.max(0, Math.round(Number(v)) || 0) })} unite="min" min={0} max={1440} libelle={`${t("Délai minimal", "Minimum lead time")} ${n}`} /></Ligne>
                                        <Ligne libelle={t("Jours à l'avance", "Days ahead")}><Nombre valeur={String(x.jours_a_l_avance)} changer={(v) => touche(nom, { jours_a_l_avance: Math.max(0, Math.round(Number(v)) || 0) })} unite={t("jours", "days")} min={0} max={365} libelle={`${t("Jours à l'avance", "Days ahead")} ${n}`} /></Ligne>
                                    </>
                                )}
                            </div>
                        );
                    })}
                    {imprimante && (
                        <Ligne libelle={t("Sur imprimante", "On printer")} info={t("Quand la commande planifiée part en ticket.", "When the scheduled order goes out as a ticket.")}>
                            <Segmente
                                valeur={imprimante.mode_planifiee === "differe" ? t(`Libéré ${imprimante.minutes_avant} min avant`, `Released ${imprimante.minutes_avant} min before`) : t("Tout de suite, marqué PROGRAMMÉE", "Now, marked SCHEDULED")}
                                options={[t(`Libéré ${imprimante.minutes_avant} min avant`, `Released ${imprimante.minutes_avant} min before`), t("Tout de suite, marqué PROGRAMMÉE", "Now, marked SCHEDULED")]}
                                changer={(v) => setImprimante({ ...imprimante, mode_planifiee: v.startsWith("Tout") || v.startsWith("Now") ? "immediat" : "differe" })}
                            />
                        </Ligne>
                    )}
                </Champs>
            </Section>

            <Section titre={t("Moyens de paiement", "Payment methods")} info={t("Le paiement en deux moyens (titre-restaurant plus espèces) est permis : le numéro court prend alors le préfixe réglé plus bas.", "Mixed payment (meal voucher plus cash) is allowed: the short number then takes the prefix set below.")}>
                <Champs>
                    {MOYENS.map((m) => (
                        <Ligne key={m.code} libelle={langue === "en" ? m.en : m.fr}>
                            <Switch checked={reglage.moyens_paiement.includes(m.code)} onCheckedChange={(v) => setReglage({ ...reglage, moyens_paiement: v ? [...reglage.moyens_paiement, m.code] : reglage.moyens_paiement.filter((x) => x !== m.code) })} aria-label={langue === "en" ? m.en : m.fr} />
                        </Ligne>
                    ))}
                    {reglage.moyens_paiement.includes("titre_restaurant") && (
                        <>
                            <Ligne libelle={t("Plafond du titre-restaurant par commande", "Meal-voucher cap per order")} info={t("Au-delà, le reste se règle autrement (carte ou espèces). Vide : aucun plafond posé.", "Beyond it, the rest is paid another way (card or cash). Empty: no cap set.")}>
                                <Nombre valeur={plafond} changer={setPlafond} unite="€" min={0} libelle={t("Plafond du titre-restaurant", "Meal-voucher cap")} />
                            </Ligne>
                            <Ligne libelle={t("Pas de rendu de monnaie sur le papier", "No change given on paper vouchers")} info={t("Le complément est demandé en espèces.", "The balance is asked in cash.")}>
                                <Switch checked={reglage.titre_sans_rendu} onCheckedChange={(v) => setReglage({ ...reglage, titre_sans_rendu: v })} aria-label={t("Pas de rendu de monnaie", "No change given")} />
                            </Ligne>
                            <Ligne libelle={t("Alcool exclu du titre-restaurant", "Alcohol excluded from vouchers")}>
                                <Switch checked={reglage.titre_alcool_exclu} onCheckedChange={(v) => setReglage({ ...reglage, titre_alcool_exclu: v })} aria-label={t("Alcool exclu", "Alcohol excluded")} />
                            </Ligne>
                        </>
                    )}
                </Champs>
            </Section>

            <Section titre={t("Numéro de commande", "Order number")} info={t("Numéro court par établissement, remis à 1 chaque jour. Quand la caisse donne son numéro, il s'affiche à côté.", "Short number per site, reset to 1 each day. When the till gives its own number, it shows next to it.")}>
                <Champs>
                    <Ligne libelle={t("Préfixe", "Prefix")}>
                        <Segmente
                            valeur={reglage.numero_mode === "aucun" ? t("Aucun", "None") : reglage.numero_mode === "moyen" ? t("Par moyen de paiement", "By payment") : t("Par type", "By type")}
                            options={[t("Aucun", "None"), t("Par moyen de paiement", "By payment"), t("Par type", "By type")]}
                            changer={(v) => setReglage({ ...reglage, numero_mode: v === t("Aucun", "None") ? "aucun" : v === t("Par type", "By type") ? "type" : "moyen" })}
                        />
                    </Ligne>
                    {reglage.numero_mode === "moyen" && (
                        <Ligne libelle={t("Préfixe d'un paiement en deux moyens", "Mixed-payment prefix")}>
                            <Input value={reglage.prefixe_mixte} onChange={(e) => setReglage({ ...reglage, prefixe_mixte: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4) })} className="h-8 w-24 font-mono" aria-label={t("Préfixe d'un paiement en deux moyens", "Mixed-payment prefix")} />
                        </Ligne>
                    )}
                    <Ligne libelle={t("Préfixe de l'établissement", "Site prefix")} info={t("Quatre caractères au plus (lettres et chiffres).", "Four characters at most (letters and digits).")}>
                        <Input value={reglage.prefixe_numero_court} onChange={(e) => setReglage({ ...reglage, prefixe_numero_court: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4) })} className="h-8 w-24 font-mono" aria-label={t("Préfixe de l'établissement", "Site prefix")} />
                    </Ligne>
                    <Ligne libelle={t("Exemples", "Examples")}><span className="font-mono text-sm">{reglage.prefixe_numero_court}{exemple}</span></Ligne>
                </Champs>
            </Section>

            <Section titre={t("Notes libres", "Free-text notes")}>
                <Champs>
                    <Ligne libelle={t("Accepter les notes libres", "Accept free-text notes")} info={t("« Bien cuite », « sauce à part » : la note s'imprime et passe en caisse. Oui par défaut.", "“Well done”, “sauce on the side”: the note prints and goes to the till. On by default.")}>
                        <Switch checked={reglage.notes_libres} onCheckedChange={(v) => setReglage({ ...reglage, notes_libres: v })} aria-label={t("Accepter les notes libres", "Accept free-text notes")} />
                    </Ligne>
                </Champs>
            </Section>

            <Section titre={t("Pause avec la caisse", "Pause with the till")} info={t("Quand la caisse passe en pause (commande en ligne coupée), l'agent du téléphone se met en pause aussi et le dit aux appelants. Décoché, la pause de la caisse ne ferme plus le téléphone.", "When the till goes on pause (online ordering off), the phone agent pauses too and tells callers. Unticked, the till's pause no longer closes the phone.")}>
                <Champs>
                    <Ligne libelle={t("Mettre le téléphone en pause avec la caisse", "Pause the phone with the till")} info={t("Oui par défaut.", "On by default.")}>
                        <Switch checked={reglage.pause_caisse_pause_telephone} onCheckedChange={(v) => setReglage({ ...reglage, pause_caisse_pause_telephone: v })} aria-label={t("Mettre le téléphone en pause avec la caisse", "Pause the phone with the till")} />
                    </Ligne>
                </Champs>
            </Section>

            <Section titre={t("Fiche client", "Customer record")} info={t("Combien de mois on garde la fiche d'un client après sa dernière commande (36 au plus).", "How many months a customer record is kept after the last order (36 at most).")}>
                <Champs>
                    <Ligne libelle={t("Conservation de la fiche", "Record retention")}>
                        <Nombre valeur={String(reglage.conservation_client_mois)} changer={(v) => setReglage({ ...reglage, conservation_client_mois: Math.min(36, Math.max(1, Math.round(Number(v)) || 1)) })} unite={t("mois", "months")} min={1} max={36} libelle={t("Conservation de la fiche", "Record retention")} />
                    </Ligne>
                </Champs>
            </Section>

            <Section titre={t("Commande d'un appel coupé", "Order from a dropped call")} info={t("Si la fin d'un appel n'a pas pu être jouée, la commande acceptée part quand même en cuisine : au plus tôt ce nombre de minutes après le dernier « oui », et seulement une fois l'appel fini. Si elle ne peut pas partir, le restaurant reçoit une alerte au bout de 3 heures. Réglable de 1 à 120 minutes.", "If a call's end could not run, the accepted order still goes to the kitchen: no sooner than this many minutes after the last “yes”, and only once the call is over. If it cannot go, the restaurant gets an alert after 3 hours. Adjustable from 1 to 120 minutes.")}>
                <Champs>
                    <Ligne libelle={t("Délai avant l'envoi", "Delay before sending")}>
                        <Nombre valeur={String(reglage.filet_retenue_min)} changer={(v) => setReglage({ ...reglage, filet_retenue_min: Math.min(120, Math.max(1, Math.round(Number(v)) || 1)) })} unite={t("min", "min")} min={1} max={120} libelle={t("Délai avant l'envoi", "Delay before sending")} />
                    </Ligne>
                </Champs>
            </Section>

            {seuils && (
                <Section titre={t("Alertes de la caisse", "Till alerts")} info={t("Quand une commande envoyée à la caisse reste sans réponse, on alerte ; la relève des messages se fait à intervalle régulier.", "When an order sent to the till gets no answer, an alert goes out; messages are polled at a regular interval.")}>
                    <Champs>
                        <Ligne libelle={t("Alerte d'une commande sans réponse", "Alert for an unanswered order")}><Nombre valeur={String(seuils.alerte_sans_reponse_min)} changer={(v) => setSeuils({ ...seuils, alerte_sans_reponse_min: Math.min(120, Math.max(1, Math.round(Number(v)) || 1)) })} unite="min" min={1} max={120} libelle={t("Alerte d'une commande sans réponse", "Alert for an unanswered order")} /></Ligne>
                        <Ligne libelle={t("Relève des messages de la caisse", "Till message polling")}><Nombre valeur={String(seuils.releve_messages_min)} changer={(v) => setSeuils({ ...seuils, releve_messages_min: Math.min(120, Math.max(1, Math.round(Number(v)) || 1)) })} unite="min" min={1} max={120} libelle={t("Relève des messages de la caisse", "Till message polling")} /></Ligne>
                    </Champs>
                </Section>
            )}
            <div className="flex justify-end"><Button size="sm" className="cursor-pointer" onClick={sauver}>{t("Enregistrer", "Save")}</Button></div>
        </>
    );
}

// ---- Temps d'attente : la puce, l'aperçu, le format, les soirs chargés (jamais « coup de feu » à l'écran) ----------------------------------------

const AJOUTS = [0, 5, 10, 15, 20, 30];
const JUSQUA = [
    { v: "indefini", fr: "Jusqu'à nouvel ordre", en: "Until further notice" }, { v: "30", fr: "Dans 30 min", en: "In 30 min" }, { v: "60", fr: "Dans 1 h", en: "In 1 hour" }, { v: "fin", fr: "Jusqu'à la fin du service", en: "Until the end of service" },
];
const FORMATS: { v: FormatAnnonce; fr: string; en: string }[] = [{ v: "heure_fixe", fr: "Heure fixe", en: "Fixed time" }, { v: "tranche", fr: "Tranche", en: "Slot" }, { v: "duree", fr: "Durée", en: "Duration" }];
const JOURS_COURTS: [string, string][] = [["L", "M"], ["M", "T"], ["M", "W"], ["J", "T"], ["V", "F"], ["S", "S"], ["D", "S"]];

function Attente({ etab, r, temps, poser, poserTemps }: { etab: number; r: ReglagesRendus; temps: TempsRendu | null; poser: (r: ReglagesRendus) => void; poserTemps: (t: TempsRendu) => void }) {
    const t = useTexte();
    const { langue } = useLangue();
    const lecture = temps?.lecture_seule ?? false;
    const [jusqua, setJusqua] = useState("indefini");
    const [recurrents, setRecurrents] = useState<TempsRecurrent[]>(r.recurrents);
    const [formats, setFormats] = useState<Record<string, FormatAnnonce>>(Object.fromEntries(r.types.map((x) => [x.type, x.annonce])));
    const [delais, setDelais] = useState<Record<string, string>>(Object.fromEntries(r.types.map((x) => [x.type, x.delai_annonce === null ? "" : String(x.delai_annonce)])));
    const ajoutCourant = temps?.types.find((x) => x.type === "emporter")?.minutes_ajoutees ?? 0;

    const poserAjout = async (minutes: number) => {
        let dernier: TempsRendu | undefined;
        for (const type of TYPES_OUVERTS) {
            const jusqu_a = minutes === 0 || jusqua === "indefini" ? null : jusqua === "fin" ? ("fin_du_service" as string) : new Date(Date.now() + Number(jusqua) * 60_000).toISOString();
            const rendu = await poserLeTemps(etab, { type, minutes_ajoutees: minutes, jusqu_a });
            if (rendu.error || !rendu.data) return void echecAffiche(rendu.error, ECHECS.restaurationTemps);
            dernier = rendu.data;
        }
        if (dernier) poserTemps(dernier);
        notifier.succes({ fr: `Temps d'attente : +${minutes} min. Les commandes déjà annoncées gardent leur heure.`, en: `Waiting time: +${minutes} min. Orders already announced keep their time.` });
    };
    const sauverFormats = () => {
        const types = (["emporter", "livraison", "sur_place"] as TypeDeCommande[]).map((type) => ({
            type, annonce: formats[type],
            ...(type !== "livraison" && delais[type] !== "" ? { delai_annonce: Math.max(0, Math.round(Number(delais[type])) || 0) } : {}),
        }));
        void enregistrer(etab, { types: types as ReglagesChanges["types"] }, poser, { fr: "Format et délais enregistrés.", en: "Format and times saved." });
    };
    const sauverRecurrents = () => {
        const valides = recurrents.filter((x) => x.jours.length > 0 && x.debut && x.fin && x.fin > x.debut && x.minutes_ajoutees >= 1);
        if (valides.length !== recurrents.length) return void notifier.avertissement({ fr: "Chaque ligne veut au moins un jour, une plage d'heures qui finit après son début et des minutes.", en: "Each row needs at least one day, a time range ending after it starts, and minutes." });
        void enregistrer(etab, { recurrents: valides }, poser, { fr: "Temps d'attente récurrents enregistrés.", en: "Recurring waiting times saved." }).then((ok) => ok && setRecurrents(valides));
    };
    const touche = (i: number, patch: Partial<TempsRecurrent>) => setRecurrents(recurrents.map((x, j) => (j === i ? { ...x, ...patch } : x)));
    return (
        <>
            <TitreTableau titre={t("Temps d'attente", "Waiting time")} info={<Info>{t("Un temps ajouté, choisi en un geste. L'effet vaut pour les commandes à venir : celles déjà annoncées gardent leur heure.", "An added time, chosen in one gesture. It applies to upcoming orders: those already announced keep their time.")}</Info>} />
            {lecture && <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Lock className="size-3" /> {t("L'état de l'établissement est porté par la caisse : le temps ajouté se règle là-bas.", "The site's state is carried by the till: the added time is set there.")}</p>}
            <Champs>
                <Ligne libelle={t("Temps ajouté", "Added time")}>
                    <Segmente valeur={`+${ajoutCourant} min`} options={AJOUTS.map((a) => `+${a} min`)} changer={(v) => !lecture && void poserAjout(Number(v.replace(/\D/g, "")))} />
                </Ligne>
                <Ligne libelle={t("Jusqu'à quand", "Until when")}>
                    <Liste valeur={jusqua} changer={setJusqua} options={JUSQUA.map((j) => ({ valeur: j.v, libelle: langue === "en" ? j.en : j.fr }))} className="w-56" libelle={t("Jusqu'à quand", "Until when")} />
                </Ligne>
            </Champs>
            <div className="space-y-1.5 rounded-xl border bg-muted/40 p-4 text-sm" data-testid="apercu-annonce">
                <p className="flex items-center gap-1.5 text-xs font-medium tracking-wider text-muted-foreground uppercase">{t("Ce que l'agent annonce", "What the agent announces")}<Info>{t("Une commande passée maintenant, d'après les réglages en vigueur (temps ajouté et soirs chargés compris).", "An order placed right now, from the settings in force (added time and busy evenings included).")}</Info></p>
                {temps?.types.filter((x) => x.type === "emporter" || x.type === "sur_place").map((x) => (
                    <p key={x.type} className="flex justify-between gap-3"><span>{NOM_TYPE[x.type][langue === "en" ? 1 : 0]} <span className="text-muted-foreground">{x.ajout_actif ? t(`(${x.ajout_actif} min ajoutées)`, `(${x.ajout_actif} min added)`) : ""}</span></span><b>{x.annonce?.phrase ?? "–"}</b></p>
                ))}
                {temps?.types.find((x) => x.type === "livraison")?.par_zone.map((z) => (
                    <p key={z.zone_id} className="flex justify-between gap-3"><span>{t("Livraison", "Delivery")} · {z.nom} <span className="text-muted-foreground">{t(`(délai de la zone ${z.delai_zone} min)`, `(zone time ${z.delai_zone} min)`)}</span></span><b>{z.annonce.phrase}</b></p>
                ))}
                {temps && temps.types.some((x) => !x.ouvert && x.type !== "reservation") && <p className="text-xs text-muted-foreground">{t("Un type fermé ou en pause ne s'annonce pas.", "A closed or paused type announces nothing.")}</p>}
            </div>
            <Section titre={t("Format de l'heure annoncée et délai, par type", "Announced time format and time, by type")} info={t("Heure fixe (« à 20 h 35 »), tranche (« entre 20 h 30 et 20 h 45 ») ou durée (« dans 25 minutes »). Le délai de la livraison est celui de la zone.", "Fixed time (“at 8:35 pm”), slot (“between 8:30 and 8:45”) or duration (“in 25 minutes”). Delivery time is the zone's.")}>
                <Champs>
                    {(["emporter", "livraison", "sur_place"] as TypeDeCommande[]).map((type) => (
                        <Ligne key={type} libelle={NOM_TYPE[type][langue === "en" ? 1 : 0]}>
                            <span className="inline-flex items-center gap-3">
                                {type !== "livraison" && <Nombre valeur={delais[type] ?? ""} changer={(v) => setDelais({ ...delais, [type]: v })} unite="min" min={0} max={600} libelle={`${t("Délai", "Time")} ${NOM_TYPE[type][langue === "en" ? 1 : 0]}`} />}
                                <Segmente valeur={FORMATS.find((f) => f.v === formats[type])![langue === "en" ? "en" : "fr"]} options={FORMATS.map((f) => (langue === "en" ? f.en : f.fr))} changer={(v) => setFormats({ ...formats, [type]: FORMATS.find((f) => f.fr === v || f.en === v)!.v })} />
                            </span>
                        </Ligne>
                    ))}
                </Champs>
                {lecture && <p className="pt-1 text-xs text-muted-foreground">{t("Le temps de préparation de la caisse prime sur le délai réglé ici.", "The till's preparation time takes precedence over the time set here.")}</p>}
                <div className="flex justify-end pt-2"><Button size="sm" variant="outline" className="cursor-pointer" onClick={sauverFormats}>{t("Enregistrer le format et les délais", "Save format and times")}</Button></div>
            </Section>
            <TitreTableau
                titre={t("Temps d'attente récurrents", "Recurring waiting times")}
                info={<Info>{t("Les soirs toujours chargés : des minutes ajoutées certains jours, dans une plage d'heures. Elles s'ajoutent au temps ajouté ; deux plages qui se recouvrent, la plus grande compte.", "Always-busy evenings: minutes added on certain days, within a time range. They add to the added time; two overlapping ranges, the larger counts.")}</Info>}
                action={<Button variant="outline" size="sm" className="cursor-pointer" onClick={() => setRecurrents([...recurrents, { type: "emporter", jours: [5], debut: "19:00", fin: "21:30", minutes_ajoutees: 10 }])}><Plus className="size-3.5" /> {t("Récurrence", "Recurrence")}</Button>}
            />
            {recurrents.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("Aucune récurrence.", "No recurrence.")}</p>
            ) : (
                <div className="divide-y border-y">
                    {recurrents.map((x, i) => (
                        <div key={x.id ?? `n${i}`} className="flex flex-wrap items-center gap-3 py-2.5">
                            <Liste valeur={x.type} changer={(v) => touche(i, { type: v as TempsRecurrent["type"] })} options={TYPES_OUVERTS.map((v) => ({ valeur: v, libelle: NOM_TYPE[v][langue === "en" ? 1 : 0] }))} className="w-36" libelle={t("Type", "Type")} />
                            <span role="group" aria-label={t("Jours", "Days")} className="inline-flex gap-1">
                                {JOURS_COURTS.map((j, k) => (
                                    <button key={k} type="button" aria-pressed={x.jours.includes(k + 1)} onClick={() => touche(i, { jours: x.jours.includes(k + 1) ? x.jours.filter((d) => d !== k + 1) : [...x.jours, k + 1].sort() })} className={`size-7 cursor-pointer rounded-md border text-xs ${x.jours.includes(k + 1) ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted hover:font-medium"}`}>{j[langue === "en" ? 1 : 0]}</button>
                                ))}
                            </span>
                            <Input type="time" value={x.debut} onChange={(e) => touche(i, { debut: e.target.value })} className="h-8 w-28" aria-label={t("De", "From")} />
                            <Input type="time" value={x.fin} onChange={(e) => touche(i, { fin: e.target.value })} className="h-8 w-28" aria-label={t("À", "To")} />
                            <Nombre valeur={String(x.minutes_ajoutees)} changer={(v) => touche(i, { minutes_ajoutees: Math.min(240, Math.max(0, Math.round(Number(v)) || 0)) })} unite="min" min={1} max={240} libelle={t("Ajouté", "Added")} />
                            <button type="button" aria-label={t("Retirer", "Remove")} className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => setRecurrents(recurrents.filter((_, j) => j !== i))}><X className="size-4" /></button>
                        </div>
                    ))}
                </div>
            )}
            <div className="flex justify-end"><Button size="sm" variant="outline" className="cursor-pointer" onClick={sauverRecurrents}>{t("Enregistrer les récurrences", "Save recurrences")}</Button></div>
        </>
    );
}

// ---- Envois SMS : éteints par défaut (lot 13, M7 : les sept envois du mécanisme du lot 7, un seul endroit de configuration) -------------------------------

const NOM_ENVOI: Record<DeclencheurDEnvoi, { nom: [string, string]; quand: [string, string] }> = {
    commande_enregistree: { nom: ["Commande enregistrée", "Order saved"], quand: ["Quand une commande est enregistrée", "When an order is saved"] },
    reservation_enregistree: { nom: ["Réservation confirmée", "Booking confirmed"], quand: ["Quand l'agent ou le restaurant prend une réservation", "When the agent or the restaurant takes a booking"] },
    reservation_modifiee: { nom: ["Réservation modifiée", "Booking changed"], quand: ["Quand l'heure ou le nombre de couverts change", "When the time or the guests change"] },
    reservation_annulee: { nom: ["Réservation annulée", "Booking cancelled"], quand: ["Quand une réservation est annulée", "When a booking is cancelled"] },
    carte: { nom: ["Envoyer la carte", "Send the menu"], quand: ["Quand l'appelant demande la carte", "When the caller asks for the menu"] },
    avis: { nom: ["Demander un avis", "Ask for a review"], quand: ["Quand l'appelant accepte de laisser un avis", "When the caller agrees to leave a review"] },
    heure_changee: { nom: ["Heure changée par la caisse", "Time changed by the till"], quand: ["Quand la caisse change l'heure d'une commande", "When the till changes an order's time"] },
};
const EXEMPLE: Record<string, string> = { prenom: "Marie", numero_court: "CB14", heure: "20:35", quand: "samedi à 20 h", personnes: "4" };

function Envois({ etab }: { etab: number; r: ReglagesRendus; poser: (r: ReglagesRendus) => void }) {
    const t = useTexte();
    const [ouvert, setOuvert] = useState<DeclencheurDEnvoi | null>(null);
    const { donnee, etat, relire, poser } = useCharge(() => lireLesEnvois(etab), `envois-${etab}`, ECHECS.restaurationEnvois);
    const ecrire = async (e: { declencheur: DeclencheurDEnvoi; texte?: string; actif?: boolean }, ok: { fr: string; en: string }) => {
        const r = await ecrireLesEnvois(etab, [e]);
        if (r.error || !r.data) {
            notifier.echec(ECHECS.restaurationEnvoisEnregistrer, { erreur: r.error });
            return false;
        }
        poser(r.data);
        notifier.succes(ok);
        return true;
    };
    return (
        <>
            <TitreTableau titre={t("Envois SMS", "SMS sending")} info={<Info>{t("Un SMS part après une action, seulement si l'envoi est allumé. Éteints par défaut ; un seul endroit pour les régler. Les trous entre doubles accolades sont remplis par le code, jamais par le modèle ; le SMS tient sur une ligne (160 caractères) et part du compte SMS de « Téléphonie ».", "A text goes out after an action, only if the message is on. Off by default; one place to set them. Blanks in double braces are filled by the code, never by the model; the text fits one line (160 characters) and leaves from the “Telephony” SMS account.")}</Info>} />
            {etat === "erreur" ? (
                <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => void relire()}>{t("Réessayer", "Retry")}</Button>
            ) : (
                <Tableau colonnes={[{ titre: t("Envoi", "Message") }, { titre: t("Déclencheur", "Trigger"), secondaire: 1 }, { titre: t("État", "Status") }, { titre: t("Allumé", "On"), droite: true }]}>
                    {(donnee?.envois ?? []).map((e) => (
                        <LigneT key={e.declencheur} onClick={() => setOuvert(e.declencheur)}>
                            <Cellule principale>{t(...NOM_ENVOI[e.declencheur].nom)}</Cellule>
                            <Cellule>{t(...NOM_ENVOI[e.declencheur].quand)}</Cellule>
                            <Cellule>{e.actif ? <PointEtat etat="publie">{t("allumé", "on")}</PointEtat> : <PointEtat etat="brouillon">{t("éteint", "off")}</PointEtat>}</Cellule>
                            <td className="pl-4 text-right" onClick={(ev) => ev.stopPropagation()}>
                                <Switch
                                    checked={e.actif}
                                    onCheckedChange={(v) => void ecrire({ declencheur: e.declencheur, actif: v }, v ? { fr: "Envoi allumé.", en: "Sending on." } : { fr: "Envoi éteint.", en: "Sending off." })}
                                    aria-label={t("Allumer l'envoi", "Turn the sending on")}
                                />
                            </td>
                        </LigneT>
                    ))}
                </Tableau>
            )}
            {ouvert && donnee && (
                <PanneauEnvoi
                    key={ouvert}
                    envoi={donnee.envois.find((e) => e.declencheur === ouvert)!}
                    fermer={() => setOuvert(null)}
                    enregistrer={(texte) => ecrire({ declencheur: ouvert, texte }, { fr: "Texte enregistré.", en: "Text saved." })}
                />
            )}
        </>
    );
}

function PanneauEnvoi({ envoi, fermer, enregistrer }: { envoi: EnvoiLu; fermer: () => void; enregistrer: (texte: string) => Promise<boolean> }) {
    const t = useTexte();
    const [texte, setTexte] = useState(envoi.texte);
    const apercu = texte.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k: string) => EXEMPLE[k] ?? "");
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={t(...NOM_ENVOI[envoi.declencheur].nom)}
            sous={envoi.actif ? t("Allumé", "On") : t("Éteint par défaut", "Off by default")}
            modifie={texte !== envoi.texte}
            desactiver={!texte.trim() || texte.length > 160}
            valider={t("Enregistrer", "Save")}
            onValider={() => void enregistrer(texte.trim()).then((ok) => ok && fermer())}
        >
            <Section titre={t("Quand", "When")}>
                <Champs><Ligne libelle={t("Déclencheur", "Trigger")}><span className="text-sm text-muted-foreground">{t(...NOM_ENVOI[envoi.declencheur].quand)}</span></Ligne></Champs>
            </Section>
            <Section titre={t("Texte", "Text")} info={t("Les étiquettes entre doubles accolades sont remplacées au moment de l'envoi.", "Tags in double braces are replaced at sending time.")}>
                <Bloc libelle={t("Message", "Message")}>
                    <Textarea value={texte} onChange={(e) => setTexte(e.target.value)} maxLength={160} className="min-h-24 text-sm" aria-label={t("Message", "Message")} />
                    {envoi.trous.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                            {envoi.trous.map((x) => <button key={x} type="button" onClick={() => setTexte(`${texte} {{${x}}}`.trim())} className="cursor-pointer rounded-full border px-2 py-0.5 font-mono text-[11px] hover:bg-muted hover:font-semibold">{`{{${x}}}`}</button>)}
                        </div>
                    )}
                    <Button variant="ghost" size="sm" className="cursor-pointer self-start" onClick={() => setTexte(envoi.texte_par_defaut)}>{t("Reprendre le texte proposé", "Use the suggested text")}</Button>
                </Bloc>
                <Bloc libelle={t("Aperçu", "Preview")}>
                    <p className="max-w-xs rounded-2xl bg-muted px-3.5 py-2.5 text-sm">{apercu}</p>
                    <p className="text-xs text-muted-foreground">{apercu.length} / 160 {t("caractères", "characters")}</p>
                </Bloc>
            </Section>
        </FenetreOnglets>
    );
}

// ---- Historique des changements -----------------------------------------------------------------------------------------------------------------------

function Historique({ etab }: { etab: number }) {
    const t = useTexte();
    const [lignes, setLignes] = useState<LigneDHistorique[]>([]);
    const [suite, setSuite] = useState<number | null>(null);
    const { etat, relire } = useCharge(
        () => lireLHistorique(etab).then((r) => { if (r.data) { setLignes(r.data.lignes); setSuite(r.data.suite); } return r; }),
        `historique-${etab}`,
        ECHECS.restaurationHistorique,
    );
    const plus = async () => {
        const r = await lireLHistorique(etab, suite);
        if (r.error || !r.data) return void echecAffiche(r.error, ECHECS.restaurationHistorique);
        setLignes([...lignes, ...r.data.lignes]);
        setSuite(r.data.suite);
    };
    const quand = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    const source = (s: string) => (s === "caisse" ? t("Caisse", "Till") : s === "portail" ? t("Portail", "Portal") : s === "agent" ? t("Agent", "Agent") : s === "import" ? "Import" : "Fork");
    return (
        <>
            <TitreTableau titre={t("Historique des changements", "Change history")} info={<Info>{t("Toute écriture, du fork comme du portail ou de la caisse, est journalisée : avant, après, source, qui, quand.", "Every write, from the fork, the portal or the till, is logged: before, after, source, who, when.")}</Info>} />
            {etat === "erreur" ? (
                <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => void relire()}>{t("Réessayer", "Retry")}</Button>
            ) : lignes.length === 0 && etat === "pret" ? (
                <p className="text-sm text-muted-foreground">{t("Aucun changement journalisé pour cet établissement.", "No change logged for this site.")}</p>
            ) : (
                <Tableau colonnes={[{ titre: t("Quand", "When") }, { titre: t("Objet", "Object") }, { titre: t("Avant", "Before"), secondaire: 2 }, { titre: t("Après", "After") }, { titre: t("Source", "Source"), secondaire: 1 }, { titre: t("Qui", "Who"), secondaire: 3 }]}>
                    {lignes.map((h) => (
                        <LigneT key={h.id}>
                            <Cellule principale>{quand(h.le)}</Cellule>
                            <Cellule>{h.objet_dit}</Cellule>
                            <Cellule>{h.avant ?? "–"}</Cellule>
                            <Cellule>{h.operation === "delete" ? t("retiré", "removed") : (h.apres ?? "–")}</Cellule>
                            <Cellule>{source(h.source)}</Cellule>
                            <Cellule>{h.auteur}</Cellule>
                        </LigneT>
                    ))}
                </Tableau>
            )}
            {suite !== null && <div className="flex justify-center"><Button variant="outline" size="sm" className="cursor-pointer" onClick={() => void plus()}>{t("Voir plus", "Show more")}</Button></div>}
        </>
    );
}

