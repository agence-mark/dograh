"use client";

/**
 * [.mark] Module Restauration, lot 20 (F12) : la fenêtre « Caisse / POS » de l'essai, à côté de la fenêtre d'appel.
 *
 * - le « + » en haut à gauche du panneau d'essai (``MenuSimulateurs``) : le menu des simulateurs (Caisse / POS, lien « Régler les simulateurs ») ; seulement au Labo,
 *   caisse de démo allumée ;
 * - la fenêtre (``FenetreCaisse``) : une fenêtre à elle (son cadre, son titre), COLLÉE à gauche de la fenêtre d'appel et de la même hauteur, qui survit à la fermeture de l'essai ;
 *   UNE SEULE VUE : la commande qui se remplit (le panier du direct, lot 15), le total, la TVA et la remise dès l'ouverture, puis ce que la caisse de démo a reçu et répondu.
 *   Le restaurant de test et le scénario sont derrière l'engrenage. Vaut pour l'appel dans le navigateur et le clavier (leur identifiant d'appel est posé par le panneau d'essai) ;
 *   l'appelant simulé joue côté serveur : la fenêtre suit l'appel qu'il joue (son panier, ses prix, sa réservation) comme celui du navigateur et du clavier.
 *   Une réservation faite pendant l'essai (connecteur réservation, lot 8) s'y montre en direct : l'heure, les couverts, l'état, les tables.
 * - ``Gestes de la caisse`` : la rupture d'un produit et le changement d'un prix PAR LA CAISSE, en plein appel (message signé, comme une vraie caisse).
 */
import { Check, Plus, Settings2, Store, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { create } from "zustand";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuth } from "@/lib/auth";

import { notifier } from "../notifications";
import { echecAffiche } from "../notifications/echec-affiche";
import { ECHECS } from "../notifications/phrases-echec";
import { Liste } from "../studio/liste";
import { PointEtat } from "../studio/marques";
import { euros, useTexte } from "./commun";
import {
    brancherUnResto, enCentimes, faireUnGeste, lireLaReservation, lireLePanier, lireLesRestos, lireLEtat, lireUnResto, mettreUnScenarioEnPlace, type PanierEnCours, type RestoDetail, type ListeRendue, type ReservationDeLEssai,
} from "./simulation-donnees";

interface EtatCaisseEssai {
    ouverte: boolean;
    /** L'exécution de l'essai en cours (navigateur ou clavier), pour lire son panier. */
    runId: number | null;
    ouvrir: (ouverte: boolean) => void;
    poserRun: (runId: number | null) => void;
}
export const useCaisseEssai = create<EtatCaisseEssai>((set) => ({
    ouverte: false,
    runId: null,
    ouvrir: (ouverte) => set({ ouverte }),
    poserRun: (runId) => set({ runId }),
}));

const SONDAGE_MS = 2000;

/** La caisse de démo existe-t-elle pour ce compte (Labo, interrupteur allumé) ? Lu une fois. */
export function useCaisseDeDemoActive(): boolean {
    const { user, loading } = useAuth();
    const [actif, setActif] = useState(false);
    const lu = useRef(false);
    useEffect(() => {
        if (loading || !user || lu.current) return;
        lu.current = true;
        void lireLEtat().then((r) => setActif(!r.error && r.data?.active === true));
    }, [loading, user]);
    return actif;
}

/** Le « + » en haut à gauche du panneau d'essai : le menu des simulateurs. Rien pour un compte qui n'est pas au Labo. */
export function MenuSimulateurs() {
    const t = useTexte();
    const actif = useCaisseDeDemoActive();
    const ouverte = useCaisseEssai((s) => s.ouverte);
    const ouvrir = useCaisseEssai((s) => s.ouvrir);
    if (!actif) return null;
    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" className="size-8" aria-label={t("Ajouter un simulateur à côté de l'appel", "Add a simulator next to the call")} title={t("Ajouter un simulateur", "Add a simulator")}><Plus className="size-4" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{t("Simulateurs", "Simulators")}</DropdownMenuLabel>
                <DropdownMenuCheckboxItem checked={ouverte} onCheckedChange={(v) => ouvrir(!!v)}><Store className="size-4" /> {t("Caisse / POS", "Till / POS")}</DropdownMenuCheckboxItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild><Link href="/labo/outils?simulateur=caisse"><Settings2 className="size-4" /> {t("Régler les simulateurs", "Set the simulators")}</Link></DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}

const ETATS_AFFICHES: Record<string, { fr: string; en: string; point: "publie" | "panne" | "attente" }> = {
    ouvert: { fr: "Ouvert", en: "Open", point: "publie" }, ferme: { fr: "Fermé", en: "Closed", point: "panne" }, deborde: { fr: "Débordé", en: "Overloaded", point: "attente" },
};

/** Le statut de la commande chez la caisse, dit simplement. */
function statutDit(statut: string, t: (fr: string, en: string) => string): string {
    const dits: Record<string, string> = {
        new: t("Commande reçue, pas encore prise en charge", "Order received, not taken yet"), received: t("Commande reçue", "Order received"), accepted: t("Commande acceptée par la caisse", "Order accepted by the till"),
        in_preparation: t("En préparation", "In preparation"), awaiting_collection: t("Prête", "Ready"), awaiting_shipment: t("Prête", "Ready"), in_delivery: t("En livraison", "Out for delivery"),
        completed: t("Terminée", "Completed"), rejected: t("Commande refusée par la caisse", "Order rejected by the till"), cancelled: t("Annulée", "Cancelled"),
    };
    return dits[statut] ?? statut;
}

export function FenetreCaisse() {
    const t = useTexte();
    const { user, loading } = useAuth();
    const { ouverte, runId, ouvrir } = useCaisseEssai();
    const [liste, setListe] = useState<ListeRendue | null>(null);
    const [choisi, setChoisi] = useState<number | null>(null);
    const [resto, setResto] = useState<RestoDetail | null>(null);
    const [panier, setPanier] = useState<PanierEnCours | null>(null);
    const [reservation, setReservation] = useState<ReservationDeLEssai | null>(null);
    const [place, setPlace] = useState<{ top: number; height: number; right: number } | null>(null);
    const [produit, setProduit] = useState("");
    const [prix, setPrix] = useState("");
    const vues = useRef<Set<string> | null>(null);

    // Collée à la fenêtre d'appel : même haut, même hauteur, juste à sa gauche. Sans fenêtre d'appel, elle se range contre le bord droit.
    useEffect(() => {
        if (!ouverte) return;
        const mesurer = () => {
            // Le panneau de droite tout entier (onglet « Essai » compris), pas seulement le corps de l'essai : même haut, même hauteur que lui.
            const essai = document.querySelector<HTMLElement>("[data-essai-panneau]");
            const p = essai?.closest<HTMLElement>("[data-panneau-droit]") ?? essai;
            if (!p) return setPlace((a) => (a === null ? a : null));
            const b = p.getBoundingClientRect();
            const suite = { top: b.top, height: b.height, right: window.innerWidth - b.left + 8 };
            // Jamais un nouvel objet pour la même place : l'observateur de l'arbre se redéclenche à chaque rendu (une liste qui s'ouvre l'a bouclé).
            setPlace((a) => (a && a.top === suite.top && a.height === suite.height && a.right === suite.right ? a : suite));
        };
        mesurer();
        const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(mesurer);
        ro?.observe(document.body);
        const mo = new MutationObserver(mesurer);
        mo.observe(document.body, { childList: true, subtree: true });
        window.addEventListener("resize", mesurer);
        return () => { ro?.disconnect(); mo.disconnect(); window.removeEventListener("resize", mesurer); };
    }, [ouverte]);

    const lireTout = async (id: number | null) => {
        const l = await lireLesRestos();
        if (l.error || !l.data) return;
        setListe(l.data);
        const voulu = id ?? l.data.restaurants.find((x) => x.branche)?.id ?? l.data.restaurants[0]?.id ?? null;
        if (voulu === null) return;
        const d = await lireUnResto(voulu);
        // Les commandes déjà là à l'ouverture (ou au début de cet essai) sont celles d'avant : la fenêtre ne montre que ce que CET essai envoie à la caisse.
        if (!d.error && d.data && vues.current === null) vues.current = new Set(d.data.commandes.map((c) => c.ref));
        if (!d.error && d.data) setResto(d.data);
        const etab = l.data.etablissements.find((e) => e.cle === d.data?.etablissement_cle);
        if (runId !== null && etab) {
            const p = await lireLePanier(etab.id, runId);
            setPanier(!p.error && p.data ? p.data : null);
            const rv = await lireLaReservation(etab.id, runId);
            setReservation(!rv.error && rv.data ? rv.data : null);
        } else { setPanier(null); setReservation(null); }
    };
    useEffect(() => { vues.current = null; }, [ouverte, runId, choisi]);
    const lecture = useRef(lireTout);
    lecture.current = lireTout;
    useEffect(() => {
        if (!ouverte || loading || !user) return;
        void lecture.current(choisi);
        const i = setInterval(() => void lecture.current(choisi), SONDAGE_MS);
        return () => clearInterval(i);
    }, [ouverte, loading, user, choisi, runId]);

    if (!ouverte || !resto) return ouverte ? null : null;
    const etat = ETATS_AFFICHES[resto.etat];
    const derniere = resto.commandes.find((c) => !vues.current?.has(c.ref)) ?? null;
    const lignes = panier && !derniere ? panier.lignes : [];
    const total = derniere?.total ? Math.round(Number(derniere.total.split(" ")[0]) * 100) : (panier?.total ?? 0);
    const tva = Math.round(total - total / 1.1);
    const remise = 0;
    const choisirResto = async (id: number) => {
        // Brancher ce restaurant de test sur l'établissement que joue l'agent : celui déjà relié, sinon le premier du Labo.
        const etab = liste?.etablissements.find((e) => e.cle === resto.etablissement_cle) ?? liste?.etablissements[0];
        if (!etab) return void notifier.echec({ fr: "Aucun établissement dans la base du Labo à jouer.", en: "No site in the Labo database to play." }, { groupe: "simulation-brancher" });
        const rep = await brancherUnResto(id, etab.id);
        if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationBrancher);
        setChoisi(id);
        notifier.succes({ fr: "Restaurant de test branché : l'agent le joue au prochain essai.", en: "Test restaurant plugged in: the agent plays it on the next test." });
    };
    const geste = async (corps: Record<string, unknown>, ok: string) => {
        const rep = await faireUnGeste(resto.id, corps);
        if (rep.error) return void echecAffiche(rep.error, ECHECS.simulationGeste);
        notifier.succes({ fr: ok, en: ok });
        void lireTout(choisi);
    };
    const produits = resto.carte.produits.map((p) => ({ valeur: p.declinaisons[0]?.code_caisse ?? p.id, libelle: p.nom }));

    return createPortal(
        <section role="dialog" aria-label={t("Caisse / POS de démo", "Demo till / POS")} data-fenetre-caisse
            style={place ? { top: place.top, height: place.height, right: place.right } : { top: 84, right: 16, height: "calc(100vh - 100px)" }}
            className="fixed z-40 flex w-[440px] max-w-[calc(100vw-16px)] flex-col rounded-xl border bg-card shadow-lg">
            <div className="flex h-12 shrink-0 items-center gap-2 border-b pl-4 pr-2">
                <Store className="size-4 text-muted-foreground" aria-hidden />
                <p className="min-w-0 flex-1 truncate text-sm font-medium">{t("Caisse / POS", "Till / POS")} <span className="font-normal text-muted-foreground">· {resto.nom}</span></p>
                <PointEtat etat={etat.point}>{t(etat.fr, etat.en)}</PointEtat>
                <Popover>
                    <PopoverTrigger asChild><Button variant="ghost" size="icon" className="size-8" aria-label={t("Réglages de la caisse", "Till settings")} title={t("Réglages de la caisse", "Till settings")}><Settings2 className="size-4" /></Button></PopoverTrigger>
                    <PopoverContent align="end" className="w-80 space-y-3 text-sm">
                        <p className="font-medium">{t("Réglages de la caisse", "Till settings")}</p>
                        <div className="space-y-1" role="radiogroup" aria-label={t("Restaurant de test", "Test restaurant")}>
                            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t("Restaurant de test", "Test restaurant")}</p>
                            {liste?.restaurants.map((x) => (
                                <button key={x.id} type="button" role="radio" aria-checked={x.id === resto.id} onClick={() => void choisirResto(x.id)} className={`flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted ${x.id === resto.id ? "font-medium" : ""}`}>
                                    <Check className={`size-4 ${x.id === resto.id ? "" : "invisible"}`} aria-hidden />{x.nom}
                                </button>))}
                        </div>
                        <div className="space-y-1" role="radiogroup" aria-label={t("Scénario", "Scenario")}>
                            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t("Scénario", "Scenario")}</p>
                            {liste?.scenarios.map((x) => (
                                <button key={x.cle} type="button" role="radio" aria-checked={x.cle === resto.scenario}
                                    onClick={() => void mettreUnScenarioEnPlace(resto.id, x.cle).then((rep) => { if (rep.error) echecAffiche(rep.error, ECHECS.simulationEnregistrer); else void lireTout(choisi); })}
                                    className={`flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted ${x.cle === resto.scenario ? "font-medium" : ""}`}>
                                    <Check className={`size-4 ${x.cle === resto.scenario ? "" : "invisible"}`} aria-hidden />{x.nom}
                                </button>))}
                        </div>
                        <Button asChild variant="outline" size="sm" className="w-full"><Link href="/labo/outils?simulateur=caisse">{t("Tous les réglages de la caisse", "All till settings")}</Link></Button>
                    </PopoverContent>
                </Popover>
                <Button variant="ghost" size="icon" className="size-8" onClick={() => ouvrir(false)} aria-label={t("Fermer la caisse", "Close the till")}><X className="size-4" /></Button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto px-4 pt-4 text-sm">
                <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {derniere ? t("Commande envoyée à la caisse", "Order sent to the till") : t("Commande en cours", "Order in progress")}
                    {runId !== null && !derniere && <span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-ok opacity-60" /><span className="relative inline-flex size-2 rounded-full bg-ok" /></span>}
                </p>
                {derniere ? (
                    <div className="mt-2 divide-y">
                        {derniere.lignes.map((l, i) => (
                            <div key={i} className="flex gap-3 py-2.5">
                                <span className="min-w-0 flex-1"><span className="block font-medium">{Number(l.quantite) > 1 ? `${Number(l.quantite)} × ` : ""}{l.nom}</span><span className="block text-xs text-muted-foreground">{[l.taille, ...l.options].filter(Boolean).join(" · ")}</span></span>
                                <span className="tabular-nums">{euros(Math.round(Number(l.prix.split(" ")[0]) * 100) || 0)}</span>
                            </div>))}
                    </div>
                ) : lignes.length === 0 ? (
                    <p className="py-8 text-center text-muted-foreground">{runId !== null ? t("L'agent écoute : la commande se remplit ici, ligne après ligne.", "The agent is listening: the order fills in here, line by line.") : t("Aucun article pour l'instant.", "No item yet.")}</p>
                ) : (
                    <div className="mt-2 divide-y">{lignes.map((l, i) => <div key={i} className="flex gap-3 py-2.5"><span className="min-w-0 flex-1 font-medium">{l.quantite > 1 ? `${l.quantite} × ` : ""}{l.nom}</span>{typeof l.prix === "number" && <span className="tabular-nums">{euros(l.prix)}</span>}</div>)}</div>
                )}
                {reservation && (
                    <div className="mt-4 border-t pt-3" data-reservation>
                        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t("Réservation en direct", "Live booking")}</p>
                        <div className="mt-2 flex gap-3">
                            <span className="min-w-0 flex-1">
                                <span className="block font-medium">{new Date(reservation.debut).toLocaleString(t("fr-FR", "en-GB"), { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</span>
                                <span className="block text-xs text-muted-foreground">{reservation.tables.length ? `${t("Table", "Table")} ${reservation.tables.join(", ")} · ` : ""}{reservation.duree_minutes} min</span>
                            </span>
                            <span className="text-right">
                                <span className="block font-medium tabular-nums">{reservation.couverts} {reservation.couverts > 1 ? t("couverts", "guests") : t("couvert", "guest")}</span>
                                <span className="block text-xs text-muted-foreground">{{ confirmee: t("Confirmée", "Confirmed"), annulee: t("Annulée", "Cancelled"), honoree: t("Honorée", "Honoured"), absente: t("Absente", "No-show") }[reservation.statut]}</span>
                            </span>
                        </div>
                    </div>
                )}
                <div className="mt-4 space-y-2 border-t pt-3">
                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t("Gestes de la caisse", "Till actions")}</p>
                    <div className="flex items-center gap-2">
                        <Liste valeur={produit} changer={setProduit} options={produits} placeholder={t("Produit", "Product")} className="w-44" libelle={t("Produit", "Product")} />
                        <Button size="sm" variant="outline" disabled={!produit} onClick={() => void geste({ geste: "rupture", code: produit, disponible: false }, "Rupture envoyée à l'agent par la caisse.")}>{t("Rupture", "Out of stock")}</Button>
                        <Button size="sm" variant="ghost" disabled={!produit} onClick={() => void geste({ geste: "rupture", code: produit, disponible: true }, "Produit de nouveau disponible.")}>{t("Remettre", "Restore")}</Button>
                    </div>
                    <div className="flex items-center gap-2">
                        <Input value={prix} onChange={(e) => setPrix(e.target.value.replace(/[^\d,.]/g, ""))} className="h-8 w-24 text-right" aria-label={t("Nouveau prix (€)", "New price (€)")} placeholder="€" />
                        <Button size="sm" variant="outline" disabled={!produit || enCentimes(prix) <= 0} onClick={() => void geste({ geste: "prix", code: produit, prix: enCentimes(prix) }, "Prix changé par la caisse.")}>{t("Changer le prix", "Change the price")}</Button>
                    </div>
                </div>
            </div>
            <div className="shrink-0 space-y-1 border-t px-4 py-3 text-sm" data-totaux>
                <p className="flex justify-between text-muted-foreground"><span>{t("Remise", "Discount")}</span><span className="tabular-nums">{remise ? "-" : ""}{euros(remise)}</span></p>
                <p className="flex justify-between text-muted-foreground"><span>{t("Dont TVA (10 %)", "Incl. VAT (10%)")}</span><span className="tabular-nums">{euros(tva)}</span></p>
                <p className="flex justify-between text-base font-semibold"><span>{t("Total", "Total")}</span><span className="tabular-nums">{euros(total)}</span></p>
            </div>
            {derniere && (
                <div className="shrink-0 space-y-1 border-t px-4 py-3 text-sm">
                    <p className={`flex items-center gap-2 font-medium ${derniere.statut === "rejected" ? "text-destructive" : ""}`}>
                        {derniere.statut !== "rejected" && <span className="inline-flex size-5 items-center justify-center rounded-full bg-ok text-white"><Check className="size-3.5" strokeWidth={3} /></span>}
                        {statutDit(derniere.statut, t)} · n° {derniere.ref}
                    </p>
                    {derniere.numero && <p className="text-muted-foreground">{t("Notre numéro de commande", "Our order number")} : {derniere.numero.slice(0, 8)}</p>}
                    <p className="text-muted-foreground">{t("Messages signés de la caisse", "Signed till messages")} : {resto.messages.length === 0 ? t("aucun", "none") : resto.messages.slice(0, 3).map((m) => `${m.type} (${m.statut})`).join(", ")}</p>
                </div>
            )}
            {!derniere && resto.comportement.reponse === "silence" && <p className="shrink-0 border-t px-4 py-3 text-sm text-muted-foreground">{t("Cette caisse ne répond pas : l'agent attendra jusqu'au délai de la prise.", "This till does not answer: the agent waits until the socket's timeout.")}</p>}
        </section>,
        document.body,
    );
}
