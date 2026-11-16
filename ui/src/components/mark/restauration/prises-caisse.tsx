"use client";

/**
 * [.mark] Module Restauration, lot 13 (F8, M6) : Intégrations › Logiciels › Caisse, repris de la maquette (`prises-caisse.tsx`) et branché sur la fiche de liaison
 * (``GET …/caisse``), « Brancher » (``POST …/caisse/brancher``, page d'autorisation de la caisse), « Débrancher » (``DELETE …/caisse``), « Resynchroniser »
 * (``POST …/caisse/resynchroniser``) et les dernières commandes (``GET …/commandes-recentes``).
 *
 * Une carte par prise qui se branche (HubRise, imprimante de tickets) avec ses pastilles de capacités, l'état de la liaison de l'établissement choisi, et sa fenêtre
 * dans le panneau de droite. La « Caisse de simulation » est au Labo, rangée dans Outils › Simulateurs (lot 20) ; rien n'en est dit ici chez un client.
 * « Commande d'essai » n'est pas ici : elle enverrait une vraie commande à la caisse d'un tiers, ce qui ne se fait que sur instruction explicite (compte rendu du lot 13).
 */
import { FlaskConical, Plug, Printer, RefreshCw, Unplug } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

import { logoDe } from "../integrations/logos";
import { notifier } from "../notifications";
import { ECHECS } from "../notifications/phrases-echec";
import { Champs, FenetreOnglets, LigneChamp as Ligne, Section } from "../studio/fenetre-onglets";
import { Info, Marque, PointEtat } from "../studio/marques";
import { Cellule, Ligne as LigneT, Tableau, TitreTableau } from "../studio/tableau";
import { Confirmer, euros, SelecteurEtab, useTexte } from "./commun";
import { FournisseurModuleRestauration, useCharge, useModuleRestauration } from "./contexte";
import { type CaisseRendue, lireLaCaisse } from "./donnees";
import { brancherLaCaisse, debrancherLaCaisse, envoyerUneCommandeDEssai, lireLesCommandesRecentes, poserLImprimante, resynchroniserLaCaisse } from "./donnees-salle";

type Prise = "hubrise" | "imprimante";
const PRISES: Prise[] = ["hubrise", "imprimante"];
const NOM: Record<Prise, string> = { hubrise: "HubRise", imprimante: "Imprimante de tickets" };
/** L'état d'une commande vue de la caisse, en clair (jamais le code brut à l'écran). */
const STATUTS: Record<string, [string, string]> = {
    nouvelle: ["nouvelle", "new"], envoyee: ["envoyée", "sent"], recue: ["reçue", "received"], acceptee: ["acceptée", "accepted"],
    en_preparation: ["en préparation", "in preparation"], prete: ["prête", "ready"], terminee: ["terminée", "done"],
    refusee: ["refusée", "refused"], annulee: ["annulée", "cancelled"], echec: ["échec", "failed"],
};
const statutDe = (statut: string, t: (fr: string, en: string) => string) => (STATUTS[statut] ? t(...STATUTS[statut]) : statut);

const ETAT: Record<CaisseRendue["etat"], "publie" | "brouillon" | "panne"> = { ok: "publie", aucune: "brouillon", erreur: "panne", rompue: "panne" };

/** Ce que la fiche d'une prise dit qu'elle sait faire : une pastille par capacité, lue de la fiche (jamais devinée d'après un nom). */
function pastilles(c: Record<string, unknown> | undefined, t: (fr: string, en: string) => string): string[] {
    if (!c) return [];
    const p: string[] = [];
    if (c.carte === "lue") p.push(t("Carte lue", "Menu read"));
    if (c.carte_notifiee) p.push(t("Carte notifiée", "Menu notified"));
    if (c.ruptures === "lues") p.push(t("Ruptures lues", "Stock read"));
    if (c.ruptures_posees_par_nous) p.push(t("Ruptures posées", "Stock pushed"));
    if (c.etat_restaurant !== "non") p.push(t("État du restaurant", "Restaurant status"));
    if (c.temps_preparation) p.push(t("Temps de préparation", "Prep time"));
    if (c.horaires) p.push(t("Horaires", "Hours"));
    if (c.annulation) p.push(t("Annulation", "Cancellation"));
    if (c.clients_lus) p.push(t("Clients lus", "Customers read"));
    if (c.remises_lues) p.push(t("Remises lues", "Discounts read"));
    if (Array.isArray(c.etapes) && c.etapes.length > 0) p.push(t(`${c.etapes.length} étapes renvoyées`, `${c.etapes.length} steps sent back`));
    return p;
}

function Capacites({ fiche }: { fiche: Record<string, unknown> | undefined }) {
    const t = useTexte();
    const liste = pastilles(fiche, t);
    if (liste.length === 0) return <span className="text-sm text-muted-foreground">{t("Envoie les commandes seulement", "Sends orders only")}</span>;
    return <span className="flex flex-wrap gap-1">{liste.map((x) => <Marque key={x} ton="neutre">{x}</Marque>)}</span>;
}

const libelleErreur = (code: string | null, t: (fr: string, en: string) => string) =>
    code === "jeton_refuse" ? t("accès refusé par la caisse : à rebrancher", "access refused by the till: plug it in again")
        : code === "caisse_injoignable" ? t("la caisse ne répond pas", "the till does not answer")
        : code === "papier" ? t("plus de papier", "out of paper")
        : code === "capot" ? t("capot ouvert", "cover open")
        : code ? t("erreur de liaison", "link error") : null;

function Visuel({ prise }: { prise: Prise }) {
    const logo = prise === "hubrise" ? logoDe("hubrise") : null;
    if (logo) {
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={logo} alt="" className="size-11 shrink-0 rounded-lg border bg-white object-contain p-1" aria-hidden />;
    }
    return <span className="flex size-11 shrink-0 items-center justify-center rounded-lg border bg-muted" aria-hidden>{prise === "imprimante" ? <Printer className="size-5 text-muted-foreground" /> : <span className="text-sm font-semibold text-muted-foreground">{"HR"}</span>}</span>;
}

/** La fenêtre d'une prise (panneau de droite) : état de la liaison, ce que la prise sait faire, dernières commandes ; Brancher, Débrancher, Resynchroniser. */
function FenetrePrise({ prise, etab, nomEtab, fiche, relire, fermer }: { prise: Prise; etab: number; nomEtab: string; fiche: CaisseRendue; relire: () => Promise<void>; fermer: () => void }) {
    const t = useTexte();
    const branchee = fiche.prise === prise && fiche.etat !== "aucune";
    const autre = fiche.etat !== "aucune" && fiche.prise !== prise && fiche.prise !== "portail";
    const [debrancher, setDebrancher] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [adresse, setAdresse] = useState<string | null>(null);
    const commandes = useCharge(branchee ? () => lireLesCommandesRecentes(etab) : null, `${etab}-${prise}-${fiche.derniere_synchro ?? ""}`, ECHECS.restaurationCaisse);
    const erreur = libelleErreur(fiche.derniere_erreur, t);
    const brancher = async () => {
        setEnCours(true);
        if (prise === "hubrise") {
            const r = await brancherLaCaisse(etab);
            setEnCours(false);
            if (r.error || !r.data) return void notifier.echec({ fr: "Le branchement de la caisse ne démarre pas. La connexion à HubRise n'est peut-être pas configurée sur ce serveur.", en: "Plugging in the till did not start. The HubRise connection may not be set up on this server." }, { erreur: r.error });
            window.location.assign(r.data.adresse_autorisation);
            return;
        }
        const r = await poserLImprimante(etab);
        setEnCours(false);
        if (r.error || !r.data) return void notifier.echec(ECHECS.restaurationCaisse, { erreur: r.error });
        setAdresse(r.data.adresse);
        notifier.succes({ fr: "Imprimante posée : saisissez l'adresse dans son réglage CloudPRNT.", en: "Printer set: enter the address in its CloudPRNT setting." });
        await relire();
    };
    const resync = async () => {
        setEnCours(true);
        const c = notifier.enCours({ fr: "Resynchronisation avec la caisse…", en: "Resyncing with the till…" });
        const r = await resynchroniserLaCaisse(etab);
        setEnCours(false);
        if (r.error || !r.data) c.echec(ECHECS.restaurationCaisseResynchro, { erreur: r.error });
        else if (!r.data.ok) c.echec({ fr: "La caisse n'a pas pu être relue : l'état de la liaison dit pourquoi.", en: "The till could not be read: the link status says why." });
        else c.succes({ fr: "Carte, ruptures et état relus.", en: "Menu, stock and status read again." });
        await relire();
    };
    // F8 : contre la caisse de démo du Labo (interne, aucun tiers) ; contre une vraie caisse l'essai réel se fait au lot 19, et l'écran le dit.
    const essai = async () => {
        setEnCours(true);
        const c = notifier.enCours({ fr: "Envoi de la commande d'essai…", en: "Sending the test order…" });
        const r = await envoyerUneCommandeDEssai(etab);
        setEnCours(false);
        if (r.error || !r.data) c.echec(ECHECS.restaurationCaisseEssai, { erreur: r.error });
        else if (r.data.statut === "refusee" && r.data.raison === "vraie_caisse") { c.fermer(); notifier.avertissement({ fr: "Essai réel avec une vraie caisse : pas encore ici, il se fait à la mise en service.", en: "Real trial with a real till: not here yet, it is done at go-live." }); }
        else if (r.data.statut === "refusee") c.echec(ECHECS.restaurationCaisseEssai);
        else c.succes({ fr: `Commande d'essai ${r.data.numero_court ?? ""} envoyée à la caisse de démo.`, en: `Test order ${r.data.numero_court ?? ""} sent to the demo till.` });
        await relire();
    };
    const debrancherMaintenant = async () => {
        setEnCours(true);
        const r = await debrancherLaCaisse(etab);
        setEnCours(false);
        if (r.error) return void notifier.echec(ECHECS.restaurationCaisseDebrancher, { erreur: r.error });
        notifier.avertissement({ fr: `${NOM[prise]} débranchée : les commandes ne partent plus à la caisse.`, en: `${NOM[prise]} unplugged: orders no longer reach the till.` });
        await relire();
    };
    return (
        <FenetreOnglets
            fermer={fermer}
            visuel={<Visuel prise={prise} />}
            titre={NOM[prise]}
            sous={`${t("Caisse", "Till")} · ${prise === "hubrise" ? t("Caisse connectée", "Connected till") : t("Ticket en cuisine", "Kitchen ticket")}`}
            valider={null}
            pied={
                branchee ? (
                    <>
                        <Button variant="ghost" size="sm" className="cursor-pointer text-destructive" disabled={enCours} onClick={() => setDebrancher(true)}><Unplug className="size-3.5" /> {t("Débrancher", "Unplug")}</Button>
                        {fiche.etat === "rompue" ? (
                            prise === "hubrise" && <Button size="sm" className="cursor-pointer" disabled={enCours} onClick={() => void brancher()}><Plug className="size-3.5" /> {t("Reconnecter", "Reconnect")}</Button>
                        ) : (
                            <Button variant="outline" size="sm" className="cursor-pointer" disabled={enCours} onClick={() => void resync()}><RefreshCw className="size-3.5" /> {t("Resynchroniser", "Resync")}</Button>
                        )}
                        {fiche.etat !== "rompue" && prise === "hubrise" && <Button variant="outline" size="sm" className="cursor-pointer" disabled={enCours} onClick={() => void essai()}><FlaskConical className="size-3.5" /> {t("Commande d'essai", "Test order")}</Button>}
                    </>
                ) : (
                    <Button size="sm" className="cursor-pointer" disabled={enCours || autre} onClick={() => void brancher()}><Plug className="size-3.5" /> {t("Brancher", "Plug in")}</Button>
                )
            }
        >
            <div className="space-y-5 px-6 py-4">
                <Section titre={t("État", "Status")}>
                    <Champs>
                        <Ligne libelle={t("Liaison", "Link")}>
                            {branchee ? (
                                <PointEtat etat={ETAT[fiche.etat]}>{fiche.etat === "ok" ? t("connectée", "connected") : fiche.etat === "rompue" ? t("rompue", "broken") : t("en erreur", "in error")}{fiche.derniere_synchro ? ` · ${t("relue", "read")} ${new Date(fiche.derniere_synchro).toLocaleString()}` : ""}</PointEtat>
                            ) : (
                                <PointEtat etat="brouillon">{t("non branchée", "not plugged in")}</PointEtat>
                            )}
                        </Ligne>
                        {erreur && branchee && <Ligne libelle={t("Dernière erreur", "Last error")}><span className="text-sm text-muted-foreground">{erreur}</span></Ligne>}
                        <Ligne libelle={t("Établissement", "Site")}><span className="text-sm text-muted-foreground">{nomEtab}</span></Ligne>
                        {branchee && prise === "hubrise" && <Ligne libelle={t("Point de vente", "Point of sale")}><span className="text-sm text-muted-foreground">{fiche.point_de_vente ?? "–"}</span></Ligne>}
                        {branchee && fiche.mode_passif && <Ligne libelle={t("Réception", "Receiving")}><span className="text-sm text-muted-foreground">{t("relève régulière (adresse de réception non joignable)", "regular polling (receiving address not reachable)")}</span></Ligne>}
                        {fiche.etat_caisse && branchee && <Ligne libelle={t("État porté par la caisse", "Status held by the till")}><span className="text-sm text-muted-foreground">{fiche.etat_caisse.mode === "normal" ? t("normal", "normal") : fiche.etat_caisse.mode === "deborde" ? t(`débordé, +${fiche.etat_caisse.minutes_en_plus} min`, `busy, +${fiche.etat_caisse.minutes_en_plus} min`) : t("en pause", "paused")}</span></Ligne>}
                    </Champs>
                    {autre && <p className="pt-2 text-xs text-muted-foreground">{t(`Cet établissement a déjà une autre prise (${fiche.prise}) : débranchez-la d'abord.`, `This site already has another gateway (${fiche.prise}): unplug it first.`)}</p>}
                    {prise === "hubrise" && !branchee && <p className="pt-2 text-xs text-muted-foreground">{t("« Brancher » ouvre la page d'autorisation de la caisse. À votre retour, la carte, les ruptures et l'état sont relus.", "“Plug in” opens the till's authorization page. When you come back, the menu, stock and status are read.")}</p>}
                    {adresse && (
                        <div className="mt-3 rounded-lg border bg-muted/40 p-3 text-sm">
                            <p className="pb-1 text-xs font-medium text-muted-foreground">{t("Adresse à saisir dans l'imprimante (montrée une seule fois)", "Address to enter in the printer (shown once)")}</p>
                            <p className="font-mono text-xs break-all select-all">{adresse}</p>
                        </div>
                    )}
                </Section>
                <Section titre={t("Ce que cette prise sait faire", "What this gateway can do")} info={t("Les capacités décident des réglages possibles : si la prise ne sait pas lire les remises, « Ma caisse » est grisé pour elles.", "Capabilities decide the possible settings: if the gateway cannot read discounts, “My till” is greyed out for them.")}>
                    <div className="py-2"><Capacites fiche={fiche.prises?.[prise]} /></div>
                </Section>
                {branchee && commandes.donnee && commandes.donnee.commandes.length > 0 && (
                    <Section titre={t("Dernières commandes", "Latest orders")}>
                        <Tableau colonnes={[{ titre: t("N°", "No.") }, { titre: t("Heure", "Time"), secondaire: 2 }, { titre: t("Total", "Total"), droite: true }, { titre: t("Paiement", "Payment"), secondaire: 1 }, { titre: t("État", "Status") }]}>
                            {commandes.donnee.commandes.map((c) => (
                                <LigneT key={c.numero}>
                                    <Cellule principale sous={c.ref_caisse ? `${t("caisse", "till")} : ${c.ref_caisse}` : undefined}>{c.numero_court}</Cellule>
                                    <Cellule>{c.le}</Cellule>
                                    <Cellule droite>{euros(c.total)}</Cellule>
                                    <Cellule>{c.paiement ?? "–"}</Cellule>
                                    <Cellule>{statutDe(c.statut, t)}</Cellule>
                                </LigneT>
                            ))}
                        </Tableau>
                    </Section>
                )}
            </div>
            {debrancher && (
                <Confirmer
                    titre={t(`Débrancher ${NOM[prise]} ?`, `Unplug ${NOM[prise]}?`)}
                    texte={t("Les commandes ne partent plus à la caisse et la carte n'est plus relue. Rien n'est supprimé ici : la carte et les commandes déjà lues restent.", "Orders no longer go to the till and the menu is no longer re-read. Nothing is deleted here: the menu and orders already read stay.")}
                    bouton={t("Débrancher", "Unplug")}
                    fermer={() => setDebrancher(false)}
                    valider={() => void debrancherMaintenant()}
                />
            )}
        </FenetreOnglets>
    );
}

function Contenu() {
    const t = useTexte();
    const { actif, etab, etablissements } = useModuleRestauration();
    const { donnee, relire } = useCharge(actif && etab !== null ? () => lireLaCaisse(etab) : null, `caisse-${etab}`, ECHECS.restaurationCaisse);
    const [ouverte, setOuverte] = useState<Prise | null>(null);
    if (!actif || etab === null || !donnee) return null;
    const nomEtab = etablissements.find((e) => e.id === etab)?.nom ?? "";
    const etatDe = (p: Prise) => (donnee.prise === p && donnee.etat !== "aucune" ? donnee.etat : null);
    return (
        <div className="space-y-3 pt-8" data-testid="section-caisse">
            <TitreTableau
                titre={t("Caisse", "Till")}
                info={<Info>{t("La caisse s'attache à l'établissement : deux restaurants de la même enseigne peuvent avoir deux caisses. Sans caisse, le classeur est maître et la commande sort en ticket si une imprimante est posée.", "The till attaches to the site: two restaurants of the same chain may have two tills. Without a till, the register is the master and the order prints as a ticket if a printer is set.")}</Info>}
                action={<SelecteurEtab />}
            />
            <Tableau colonnes={[{ titre: t("Prise", "Gateway") }, { titre: t("Ce qu'elle sait faire", "What it can do"), secondaire: 1 }, { titre: t("Liaison", "Link") }]}>
                {PRISES.map((p) => {
                    const e = etatDe(p);
                    return (
                        <LigneT key={p} onClick={() => setOuverte(p)}>
                            <Cellule principale sous={p === "hubrise" ? t("Caisse connectée", "Connected till") : t("Ticket en cuisine", "Kitchen ticket")}>{NOM[p]}</Cellule>
                            <Cellule><Capacites fiche={donnee.prises?.[p]} /></Cellule>
                            <Cellule>{e ? <PointEtat etat={ETAT[e]}>{e === "ok" ? t("connectée", "connected") : e === "rompue" ? t("rompue", "broken") : t("en erreur", "in error")}</PointEtat> : <PointEtat etat="brouillon">{t("non branchée", "not plugged in")}</PointEtat>}</Cellule>
                        </LigneT>
                    );
                })}
            </Tableau>
            {ouverte && <FenetrePrise key={ouverte} prise={ouverte} etab={etab} nomEtab={nomEtab} fiche={donnee} relire={relire} fermer={() => setOuverte(null)} />}
        </div>
    );
}

/** La section « Caisse » d'Intégrations › Logiciels : visible seulement quand le module Restauration est allumé pour l'organisation. */
export function SectionCaisse() {
    return (
        <FournisseurModuleRestauration>
            <Contenu />
        </FournisseurModuleRestauration>
    );
}
