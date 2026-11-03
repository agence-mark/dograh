"use client";

/**
 * [.mark] Le sélecteur d'espace (U2, E3) : le Labo et les clients que le rôle du compte ouvre (`GET /espaces`).
 * Choisir un espace ouvre son adresse (`/labo` ou `/clients/<id>`) ; l'organisation de chaque requête est lue dans
 * l'adresse de l'onglet (`lib/espaceCourant.ts`), jamais dans un réglage du compte : deux onglets, deux espaces.
 * « Nouveau client » crée une organisation (permission `clients.creer`, vérifiée par le serveur) et l'ouvre.
 */
import { Building2, Check, ChevronsUpDown, FlaskConical, Loader2, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { retenirEspace } from "@/lib/espaceCourant";
import { adresseDe, type Espace, listerEspaces } from "@/lib/espaces";
import logger from "@/lib/logger";
import { createOrganization } from "@/lib/organizationMembership";

type Props = { espace: "labo" | "client"; org: string | null; className?: string };

export function SelecteurEspace({ espace, org, className }: Props) {
    const { t } = useLangue();
    const router = useRouter();
    const { loading, user } = useAuth();
    const [espaces, setEspaces] = useState<Espace[]>([]);
    const [nouveau, setNouveau] = useState(false);
    const recupere = useRef(false);

    // L'intercepteur qui joint le jeton n'existe qu'une fois l'authentification chargée (ui/AGENTS.md).
    useEffect(() => {
        if (loading || !user || recupere.current) return;
        recupere.current = true;
        listerEspaces()
            .then(setEspaces)
            .catch((e) => logger.error("Failed to list the spaces", e));
    }, [loading, user]);

    const courant = espaces.find((e) => (espace === "labo" ? e.espace === "labo" : String(e.id) === org));
    const libelle = courant?.nom ?? (espace === "labo" ? "Labo" : "");
    const labo = espaces.find((e) => e.espace === "labo");
    const clients = espaces.filter((e) => e.espace === "client");

    const ouvrir = (e: Espace) => {
        retenirEspace(adresseDe(e));
        router.push(adresseDe(e));
    };

    const ligne = (e: Espace) => (
        <DropdownMenuItem key={e.id} onSelect={() => ouvrir(e)} className="cursor-pointer hover:font-medium">
            {e.espace === "labo" ? (
                <span className="mr-2 flex size-5 items-center justify-center rounded bg-primary text-primary-foreground">
                    <FlaskConical className="size-3 text-white" />
                </span>
            ) : (
                <Building2 className="mr-2 size-4" />
            )}
            <span className="min-w-0 flex-1 truncate">{e.nom}</span>
            {e.id === courant?.id && <Check className="ml-1 size-4" />}
        </DropdownMenuItem>
    );

    return (
        <div className={className}>
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button
                        type="button"
                        data-espace={espace}
                        className="flex w-full cursor-pointer items-center gap-2 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors hover:bg-accent group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:border-0 group-data-[collapsible=icon]:p-0"
                    >
                        <span
                            className={`flex size-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold ${
                                espace === "labo" ? "bg-primary text-primary-foreground" : "bg-accent text-accent-foreground"
                            }`}
                        >
                            {espace === "labo" ? <FlaskConical className="size-4" /> : <Building2 className="size-4" />}
                        </span>
                        <span className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
                            <span className="mb-1 block text-[11px] leading-none text-muted-foreground">
                                {espace === "labo" ? t({ en: "Space", fr: "Espace" }) : t({ en: "Client", fr: "Client" })}
                            </span>
                            <span className="block truncate text-sm font-medium">{libelle}</span>
                        </span>
                        <ChevronsUpDown className="size-4 text-muted-foreground group-data-[collapsible=icon]:hidden" />
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-64">
                    {labo && (
                        <>
                            <DropdownMenuLabel className="text-xs text-muted-foreground">{t({ en: "Our tool", fr: "Notre outil" })}</DropdownMenuLabel>
                            {ligne(labo)}
                            <DropdownMenuSeparator />
                        </>
                    )}
                    <DropdownMenuLabel className="text-xs text-muted-foreground">{t({ en: "Clients", fr: "Clients" })}</DropdownMenuLabel>
                    {clients.map(ligne)}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => setNouveau(true)} className="cursor-pointer hover:font-medium">
                        <Plus className="mr-2 size-4" />
                        {t({ en: "New client", fr: "Nouveau client" })}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
            <NouveauClient ouvert={nouveau} onOuvert={setNouveau} />
        </div>
    );
}

function NouveauClient({ ouvert, onOuvert }: { ouvert: boolean; onOuvert: (o: boolean) => void }) {
    const { t } = useLangue();
    const router = useRouter();
    const [identifiant, setIdentifiant] = useState("");
    const [enCours, setEnCours] = useState(false);

    const creer = async () => {
        const propre = identifiant.trim();
        if (!propre) return;
        setEnCours(true);
        try {
            const cree = await createOrganization(propre, { select: false });
            onOuvert(false);
            setIdentifiant("");
            retenirEspace(`/clients/${cree.id}`);
            router.push(`/clients/${cree.id}`);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : t({ en: "Could not create the client", fr: "Impossible de créer le client" }));
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Dialog open={ouvert} onOpenChange={onOuvert}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{t({ en: "New client", fr: "Nouveau client" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "A client holds its own agents, numbers and keys. Nothing is shared with the others.",
                            fr: "Un client a ses propres agents, numéros et clés. Rien n'est partagé avec les autres.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-2">
                    <Label htmlFor="nouveau-client">{t({ en: "Identifier", fr: "Identifiant" })}</Label>
                    <Input
                        id="nouveau-client"
                        value={identifiant}
                        onChange={(e) => setIdentifiant(e.target.value)}
                        autoComplete="off"
                    />
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOuvert(false)} disabled={enCours}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void creer()} disabled={enCours || !identifiant.trim()}>
                        {enCours && <Loader2 className="mr-2 size-4 animate-spin" />}
                        {t({ en: "Create", fr: "Créer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
