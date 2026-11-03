"use client";

/**
 * [.mark] La barre latérale du studio (E2, E3, E60) : repliable en icônes, sélecteur d'espace en tête, menu par
 * moment du métier, pied (personne, langue, thème).
 *
 * - Le sélecteur d'espace (U2) liste les espaces que le rôle ouvre (`GET /espaces`) et mène à `/labo` ou `/clients/<id>`.
 * - Les compteurs de la barre ne sont PAS branchés ici : l'emplacement existe (`compteurs`), sans fausse valeur.
 * - Aucun champ de recherche (E60).
 */
import "@/lib/espaces";

import { AlertTriangle, ChevronsUpDown, LogOut, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { SidebarTeamSwitcher } from "@/components/layout/SidebarTeamSwitcher";
import { useLangue } from "@/components/mark/langue/langue";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarGroup,
    SidebarGroupContent,
    SidebarGroupLabel,
    SidebarHeader,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    useSidebar,
} from "@/components/ui/sidebar";
import { useTelephonyConfigWarnings } from "@/context/TelephonyConfigWarningsContext";
import type { ProfilResponse } from "@/client/types.gen";
import type { LocalUser } from "@/lib/auth";
import { useAuth } from "@/lib/auth";

import { useCompteursBarre } from "./compteurs-barre";
import { retenirEspace } from "@/lib/espaceCourant";

import { FenetreProfil } from "./fenetre-profil";
import { Pastille } from "./marques";
import { useMoi } from "./moi";
import { useNomEspace } from "./nom-espace";
import { entreeActive, type EntreeMenu, espaceDe, lienDe, menuDe } from "./navigation-studio";
import { PuceEspace, SelecteurEspace } from "./selecteur-espace";

/** Un compteur de la barre : fourni par la page qui le sait (ordre 18), jamais inventé ici. */
export type CompteurMenu = { n: number; urgent?: boolean };

const initialesDe = (identite: string) =>
    identite
        .split(/[\s@]/)
        .filter(Boolean)
        .slice(0, 2)
        .map((s) => s[0]?.toUpperCase())
        .join("") || "U";

export function SidebarStudio({ compteurs: compteursFournis }: { compteurs?: Record<string, CompteurMenu> }) {
    const pathname = usePathname();
    const { t } = useLangue();
    const { state, isMobile, setOpenMobile } = useSidebar();
    const { provider, logout, user } = useAuth();
    const { telnyxMissingWebhookPublicKeyCount, vonageMissingSignatureSecretCount } = useTelephonyConfigWarnings();
    const alerteTelephonie = telnyxMissingWebhookPublicKeyCount > 0 || vonageMissingSignatureSecretCount > 0;
    const [profilOuvert, setProfilOuvert] = useState(false);
    const [profilLu, setProfilLu] = useState<ProfilResponse | null>(null);
    const moi = useMoi();
    const profil = profilLu ?? moi;

    const { espace, base, org } = espaceDe(pathname);
    const compteursLus = useCompteursBarre(espace, pathname);
    const compteurs = { ...compteursLus, ...compteursFournis };
    // L'espace de cet onglet, retenu pour les adresses sans organisation (/agents/12, /conversations/3).
    useEffect(() => retenirEspace(pathname), [pathname]);
    const groupes = menuDe(espace);
    const active = entreeActive(groupes, pathname, base);

    const nomEspace = useNomEspace(espace, org);
    const nomComplet = [profil?.prenom, profil?.nom].filter(Boolean).join(" ");
    const identite =
        nomComplet ||
        user?.displayName ||
        (user as { primaryEmail?: string } | undefined)?.primaryEmail ||
        (user as LocalUser | undefined)?.email ||
        "";
    const courriel = (user as { primaryEmail?: string } | undefined)?.primaryEmail || (user as LocalUser | undefined)?.email;

    const Entree = ({ entree }: { entree: EntreeMenu }) => {
        const I = entree.icone;
        const compteur = compteurs[entree.id];
        const alerte = entree.id === "telephonie" && alerteTelephonie;
        return (
            <SidebarMenuItem>
                <SidebarMenuButton
                    asChild
                    isActive={active?.id === entree.id}
                    tooltip={t(entree.titre)}
                    className="h-9 px-3 data-[active=true]:bg-(--acc-soft) data-[active=true]:font-medium data-[active=true]:text-(--acc-text) hover:font-medium"
                >
                    <Link href={lienDe(entree, base)} onClick={() => isMobile && setOpenMobile(false)} translate="no">
                        <I className="shrink-0" />
                        <span className="text-sm">{t(entree.titre)}</span>
                        {alerte && (
                            <AlertTriangle
                                aria-label={t({ en: "Action required on a telephony configuration", fr: "Action requise sur une configuration de téléphonie" })}
                                className="ml-auto size-3.5 text-(--signal-warn) group-data-[collapsible=icon]:hidden"
                            />
                        )}
                        {compteur && (
                            <span className="ml-auto group-data-[collapsible=icon]:hidden">
                                <Pastille n={compteur.n} urgent={compteur.urgent} />
                            </span>
                        )}
                    </Link>
                </SidebarMenuButton>
            </SidebarMenuItem>
        );
    };

    return (
        <Sidebar collapsible="icon" className="lg:border-r-0!">
            <SidebarHeader className="p-3 pb-0 group-data-[collapsible=icon]:px-1 lg:p-4">
                <div className="flex items-center gap-2 px-2 pb-3 group-data-[collapsible=icon]:justify-center">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src="/mark-lockup.svg" alt={t({ en: ".mark logo", fr: "Logo .mark" })} className="h-6 group-data-[collapsible=icon]:hidden" />
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src="/mark-symbol.svg" alt={t({ en: ".mark logo", fr: "Logo .mark" })} className="hidden h-6 group-data-[collapsible=icon]:block" />
                </div>
                {/* Sélecteur d'espace : le Labo ou le client dont l'adresse porte l'organisation (U2, mode local). */}
                {provider === "local" ? (
                    <SelecteurEspace espace={espace} org={org} />
                ) : (
                    <div
                        data-espace={espace}
                        className="flex items-center gap-2 rounded-lg border px-2.5 py-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:border-0 group-data-[collapsible=icon]:p-0"
                    >
                        <PuceEspace espace={espace} />
                        <span className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
                            <span className="mb-1 block text-[11px] leading-none text-muted-foreground">
                                {espace === "client" ? t({ en: "Client", fr: "Client" }) : t({ en: "Space", fr: "Espace" })}
                            </span>
                            <span className="block truncate text-sm font-medium">{nomEspace ?? (org ? "" : "Labo")}</span>
                        </span>
                    </div>
                )}
                {provider === "stack" && (
                    <div className="mt-3 group-data-[collapsible=icon]:hidden" translate="no">
                        <SidebarTeamSwitcher />
                    </div>
                )}
            </SidebarHeader>

            <SidebarContent className="px-2 group-data-[collapsible=icon]:overflow-y-auto! [scrollbar-width:none]">
                {groupes.map((g) => (
                    <SidebarGroup key={g.id} className="mt-3 p-0">
                        {g.label && (
                            <SidebarGroupLabel className="px-3 text-[10px] font-semibold tracking-wider text-muted-foreground">
                                {t(g.label)}
                            </SidebarGroupLabel>
                        )}
                        <SidebarGroupContent>
                            <SidebarMenu>
                                {g.entrees.map((entree) => (
                                    <Entree key={entree.id} entree={entree} />
                                ))}
                            </SidebarMenu>
                        </SidebarGroupContent>
                    </SidebarGroup>
                ))}
            </SidebarContent>

            <SidebarFooter className="px-2 pb-4">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <button
                            type="button"
                            className="flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-accent group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-0"
                        >
                            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-medium text-accent-foreground">
                                {initialesDe(identite)}
                            </span>
                            <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
                                <p className="truncate text-sm font-medium">{identite || t({ en: "Account", fr: "Compte" })}</p>
                                {profil?.role && <p className="truncate text-xs text-muted-foreground">{profil.role}</p>}
                            </div>
                            <ChevronsUpDown className="size-4 text-muted-foreground group-data-[collapsible=icon]:hidden" />
                        </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent side="top" align="start" className="w-56">
                        {courriel && <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{courriel}</DropdownMenuLabel>}
                        <DropdownMenuItem onClick={() => setProfilOuvert(true)} className="cursor-pointer hover:font-medium">
                            <UserRound className="mr-2 size-4" /> {t({ en: "My profile", fr: "Mon profil" })}
                        </DropdownMenuItem>
                        <DropdownMenuItem asChild className="cursor-pointer hover:font-medium">
                            <Link href="/labo/reglages?onglet=equipe">
                                <Users className="mr-2 size-4" /> {t({ en: "Team and roles", fr: "Équipe et rôles" })}
                            </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => logout()} className="cursor-pointer hover:font-medium">
                            <LogOut className="mr-2 size-4" /> {t({ en: "Sign out", fr: "Se déconnecter" })}
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
                <FenetreProfil profil={profil} ouverte={profilOuvert} fermer={() => setProfilOuvert(false)} apres={setProfilLu} />
            </SidebarFooter>
        </Sidebar>
    );
}
