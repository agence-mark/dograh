"use client";

/**
 * [.mark] Module Restauration, lot 12 (F1 et F5) : ce que le module ajoute à la page Entreprise.
 *
 *  - le bouton « + Ajouter un module » de la barre de titre et son catalogue (petite fenêtre centrée : exception écrite T-19) ;
 *  - la pastille « Restauration » qui suit un séparateur dans la rangée d'onglets, avec « Retirer le module » (les données sont gardées) ;
 *  - les onglets du module (un par objet) : Carte, Livraison, Réglages restaurant (le lot 13 y ajoute Salle et Remises) ;
 *  - la section « Caisse de cet établissement » de la fiche d'un établissement.
 */
import { Check, ChevronDown, Plus, Unplug,UtensilsCrossed } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

import { notifier } from "../notifications";
import { ECHECS } from "../notifications/phrases-echec";
import { LigneChamp as Ligne } from "../studio/fenetre-onglets";
import { Info, PointEtat } from "../studio/marques";
import type { OngletPage } from "../studio/onglets-page";
import { OngletCarte } from "./carte";
import { Confirmer, useTexte } from "./commun";
import { useCharge,useModuleRestauration } from "./contexte";
import { type CaisseRendue, lireLaCaisse } from "./donnees";
import { OngletLivraison } from "./livraison";
import { OngletReglagesRestaurant } from "./reglages-restaurant";

export const ID_ONGLET_MODULE = ["carte", "livraison", "reglages-restaurant"] as const;

/** Le bouton de la barre de titre de la page Entreprise. */
export function BoutonAjouterModule({ ouvrir }: { ouvrir: () => void }) {
    const t = useTexte();
    return (
        <Button variant="outline" onClick={ouvrir} className="cursor-pointer">
            <Plus className="size-4" /> {t("Ajouter un module", "Add a module")}
        </Button>
    );
}

/** Le catalogue des modules : seulement « Restauration » pour l'instant. */
export function CatalogueModules({ fermer, apresAjout }: { fermer: () => void; apresAjout: () => void }) {
    const t = useTexte();
    const { actif, poser, etat } = useModuleRestauration();
    const [enCours, setEnCours] = useState(false);
    const ajouter = async () => {
        setEnCours(true);
        const pris = await poser(true);
        setEnCours(false);
        if (!pris) return;
        notifier.succes({ fr: "Module Restauration ajouté : trois onglets de plus dans Entreprise.", en: "Restaurant module added: three more tabs in Company." });
        apresAjout();
        fermer();
    };
    return (
        <Dialog centree open onOpenChange={(o) => !o && fermer()}>
            <DialogContent className="sm:max-w-md" onOpenAutoFocus={(e) => e.preventDefault()}>
                <DialogTitle className="flex items-center gap-2">
                    {t("Ajouter un module", "Add a module")}
                    <Info>
                        {t(
                            "Un module ajoute des écrans et des outils à l'entreprise, sans rien changer aux autres agents. Rien n'est supprimé en le retirant.",
                            "A module adds screens and tools to the company, without changing other agents. Nothing is deleted when removing it.",
                        )}
                    </Info>
                </DialogTitle>
                <DialogDescription className="sr-only">{t("Catalogue des modules", "Module catalogue")}</DialogDescription>
                <div className="divide-y border-y">
                    <div className="flex items-center gap-3 py-4">
                        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                            <UtensilsCrossed className="size-5" />
                        </span>
                        <div className="min-w-0 flex-1">
                            <p className="font-medium">{t("Restauration", "Restaurant")}</p>
                            <p className="text-xs text-muted-foreground">
                                {t("Carte, commande, livraison, salle et réservations, remises, caisse.", "Menu, orders, delivery, dining room and bookings, discounts, till.")}
                            </p>
                            {etat === "erreur" && (
                                <p className="pt-1 text-xs text-muted-foreground">
                                    {t("Rattachez d'abord une base au client (« Données du client »).", "Attach a database to the client first (“Client data”).")}
                                </p>
                            )}
                        </div>
                        {actif ? (
                            <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
                                <Check className="size-4" /> {t("Ajouté", "Added")}
                            </span>
                        ) : (
                            <Button size="sm" disabled={enCours || etat !== "pret"} onClick={() => void ajouter()}>
                                {t("Ajouter", "Add")}
                            </Button>
                        )}
                    </div>
                </div>
                <div className="flex justify-end">
                    <Button variant="outline" onClick={fermer}>{t("Fermer", "Close")}</Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

/** Le séparateur et la pastille « Restauration » qui précèdent le premier onglet du module. */
export function PastilleModule({ retourBase }: { retourBase: () => void }) {
    const t = useTexte();
    const { poser } = useModuleRestauration();
    const [retirer, setRetirer] = useState(false);
    return (
        <>
            <span aria-hidden className="mx-2 h-5 w-px shrink-0 bg-border" />
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button
                        type="button"
                        aria-label={t("Module Restauration", "Restaurant module")}
                        className="inline-flex h-6 shrink-0 cursor-pointer items-center gap-1 rounded-full bg-muted px-2.5 text-xs font-medium text-foreground hover:font-semibold"
                    >
                        <UtensilsCrossed className="size-3" />
                        {t("Restauration", "Restaurant")}
                        <ChevronDown className="size-3" />
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                    <DropdownMenuItem className="cursor-pointer text-destructive" onSelect={() => setRetirer(true)}>
                        <Unplug className="size-4" /> {t("Retirer le module", "Remove the module")}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
            {retirer && (
                <Confirmer
                    titre={t("Retirer le module Restauration ?", "Remove the Restaurant module?")}
                    texte={t(
                        "Les onglets du module disparaissent et les agents n'ont plus ses outils. Les données (carte, salles, commandes, zones) sont gardées : le remettre les retrouve.",
                        "The module tabs disappear and agents lose its tools. Data (menu, rooms, orders, zones) is kept: adding it back restores them.",
                    )}
                    bouton={t("Retirer le module", "Remove module")}
                    fermer={() => setRetirer(false)}
                    valider={() => {
                        void poser(false).then((pris) => {
                            if (!pris) return;
                            retourBase();
                            notifier.succes({ fr: "Module Restauration retiré. Les données sont gardées.", en: "Restaurant module removed. Data is kept." });
                        });
                    }}
                />
            )}
        </>
    );
}

/** Les onglets du module, à poser à la suite de ceux de la page ; le premier porte le séparateur et la pastille. */
export function ongletsDuModule(t: (fr: string, en: string) => string, retourBase: () => void): OngletPage[] {
    return [
        { id: "carte", titre: t("Carte", "Menu"), precede: <PastilleModule retourBase={retourBase} />, contenu: <OngletCarte /> },
        { id: "livraison", titre: t("Livraison", "Delivery"), contenu: <OngletLivraison /> },
        { id: "reglages-restaurant", titre: t("Réglages restaurant", "Restaurant settings"), contenu: <OngletReglagesRestaurant /> },
    ];
}

const ETAT_LIAISON: Record<CaisseRendue["etat"], "publie" | "brouillon" | "panne"> = { ok: "publie", aucune: "brouillon", erreur: "panne", rompue: "panne" };

/** Fiche établissement › « Caisse de cet établissement » : prise, point de vente, état de la liaison (lecture de ``GET …/caisse``). */
export function CaisseEtablissement({ etablissementId }: { etablissementId: number }) {
    const t = useTexte();
    const { donnee, etat } = useCharge(() => lireLaCaisse(etablissementId), String(etablissementId), ECHECS.restaurationCaisse);
    const nomPrise = (prise: string) => (prise === "portail" ? t("Aucune", "None") : prise === "hubrise" ? "HubRise" : prise === "imprimante" ? t("Imprimante de tickets", "Ticket printer") : prise);
    const libelleEtat = (c: CaisseRendue) =>
        c.etat === "ok" ? t("connectée", "connected") : c.etat === "aucune" ? t("aucune caisse", "no till") : c.etat === "rompue" ? t("liaison rompue : à rebrancher", "link broken: plug it in again") : t("en erreur", "in error");
    return (
        <section className="pt-6" data-testid="caisse-etablissement">
            <p className="flex items-center gap-1.5 pb-1 text-sm font-semibold">
                {t("Caisse de cet établissement", "This site's till")}
                <Info>
                    {t(
                        "La caisse s'attache à l'établissement : deux restaurants de la même enseigne peuvent avoir deux caisses.",
                        "The till attaches to the site: two restaurants of the same chain may have two tills.",
                    )}
                </Info>
            </p>
            {etat === "chargement" ? (
                <p className="text-sm text-muted-foreground">{t("Lecture…", "Reading…")}</p>
            ) : !donnee ? (
                <p className="text-sm text-muted-foreground">{t("La fiche de la caisse ne se charge pas.", "The till sheet did not load.")}</p>
            ) : (
                <div className="divide-y">
                    <Ligne libelle={t("Prise", "Gateway")}>
                        <span className="text-sm text-muted-foreground">{nomPrise(donnee.prise)}</span>
                    </Ligne>
                    <Ligne libelle={t("Point de vente", "Point of sale")}>
                        <span className="text-sm text-muted-foreground">{donnee.point_de_vente ?? "–"}</span>
                    </Ligne>
                    <Ligne libelle={t("État de la liaison", "Link status")}>
                        <PointEtat etat={ETAT_LIAISON[donnee.etat]}>{libelleEtat(donnee)}</PointEtat>
                    </Ligne>
                </div>
            )}
            <p className="pt-1.5 text-xs text-muted-foreground">
                {t("Se branche et se débranche dans Intégrations › Logiciels › Caisse.", "Plug and unplug in Integrations › Software › Till.")}
            </p>
        </section>
    );
}
