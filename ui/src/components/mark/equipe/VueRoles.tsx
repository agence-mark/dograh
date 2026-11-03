"use client";

import { Shield } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
    catalogueApiV1EquipeMarkPermissionsGet,
    creerUnRoleApiV1EquipeMarkRolesPost,
    listerLesRolesApiV1EquipeMarkRolesGet,
    modifierUnRoleApiV1EquipeMarkRolesRoleIdPut,
    supprimerUnRoleApiV1EquipeMarkRolesRoleIdDelete,
} from "@/client/sdk.gen";
import type { PermissionResponse, RoleResponse } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { type Champ, FenetreChamps, type SectionChamps } from "@/components/mark/studio/fenetre-champs";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";
import { listerEspaces } from "@/lib/espaces";

import { lireOuSignaler } from "./VueMembres";

type Client = { id: number; nom: string };

/** Le formulaire d'un rôle : son nom, les espaces qu'il ouvre, ses permissions groupées en interrupteurs. */
function sectionsDuRole(
    role: RoleResponse | null,
    catalogue: PermissionResponse[],
    clients: Client[],
    t: ReturnType<typeof useLangue>["t"],
): SectionChamps[] {
    if (role?.fixe) {
        return [
            {
                champs: [
                    { id: "nom", l: t({ en: "Name", fr: "Nom" }), t: "lu", v: role.nom },
                    { id: "esp", l: t({ en: "Spaces", fr: "Espaces" }), t: "lu", v: t({ en: "The Lab and every client", fr: "Le Labo et tous les clients" }) },
                    { id: "perm", l: t({ en: "Permissions", fr: "Permissions" }), t: "lu", v: t({ en: "All of them", fr: "Toutes" }) },
                ],
            },
        ];
    }
    const champsClients: Champ[] = clients.map((c) => ({
        id: `o:${c.id}`,
        l: c.nom,
        t: "inter",
        v: role?.organisations.includes(c.id) ?? false,
        si: ["tous", [false]],
    }));
    const groupes = new Map<string, Champ[]>();
    for (const p of catalogue) {
        const champs = groupes.get(p.groupe) ?? [];
        champs.push({ id: `p:${p.cle}`, l: p.libelle, t: "inter", v: role?.permissions.includes(p.cle) ?? false });
        groupes.set(p.groupe, champs);
    }
    return [
        {
            champs: [{ id: "nom", l: t({ en: "Name", fr: "Nom" }), t: "texte", v: role?.nom ?? "" }],
        },
        {
            titre: t({ en: "Spaces opened", fr: "Espaces ouverts" }),
            champs: [
                { id: "labo", l: t({ en: "The Lab", fr: "Le Labo" }), t: "inter", v: role?.labo_ouvert ?? false },
                { id: "tous", l: t({ en: "Every client", fr: "Tous les clients" }), t: "inter", v: role?.tous_les_clients ?? false },
                ...champsClients,
            ],
        },
        ...[...groupes.entries()].map(([titre, champs]) => ({ titre, champs })),
    ];
}

export function VueRoles({ peutGerer }: { peutGerer: boolean }) {
    const { t } = useLangue();
    const [roles, setRoles] = useState<RoleResponse[] | null>(null);
    const [catalogue, setCatalogue] = useState<PermissionResponse[]>([]);
    const [clients, setClients] = useState<Client[]>([]);
    const [ouvert, setOuvert] = useState<RoleResponse | "nouveau" | null>(null);

    const charger = useCallback(async () => {
        const [r, c] = await Promise.all([listerLesRolesApiV1EquipeMarkRolesGet(), catalogueApiV1EquipeMarkPermissionsGet()]);
        const lus = lireOuSignaler(r, t({ en: "The roles could not be read", fr: "Les rôles n'ont pas pu être lus" }));
        if (lus) setRoles(lus);
        if (c.data) setCatalogue(c.data);
        try {
            setClients((await listerEspaces()).filter((e) => e.espace === "client").map((e) => ({ id: e.id, nom: e.nom })));
        } catch {
            setClients([]);
        }
    }, [t]);

    useEffect(() => {
        void charger();
    }, [charger]);

    if (!roles) return <EtatVide cas="chargement" />;

    const enregistrer = async (role: RoleResponse | null, v: Record<string, string | boolean>) => {
        const corps = {
            nom: String(v.nom ?? ""),
            labo_ouvert: v.labo === true,
            tous_les_clients: v.tous === true,
            permissions: Object.keys(v).filter((k) => k.startsWith("p:") && v[k] === true).map((k) => k.slice(2)),
            organisations: Object.keys(v).filter((k) => k.startsWith("o:") && v[k] === true).map((k) => Number(k.slice(2))),
        };
        const res = role
            ? await modifierUnRoleApiV1EquipeMarkRolesRoleIdPut({ path: { role_id: role.id }, body: corps })
            : await creerUnRoleApiV1EquipeMarkRolesPost({ body: corps });
        if (res.error) toast.error(detailFromError(res.error, t({ en: "The role was not saved", fr: "Le rôle n'a pas été enregistré" })));
        void charger();
    };

    const role = ouvert === "nouveau" ? null : ouvert;
    const lecture = Boolean(role?.fixe) || !peutGerer;

    return (
        <div>
            <TitreTableau
                titre={t({ en: "Roles", fr: "Rôles" })}
                action={
                    peutGerer ? (
                        <Button className="cursor-pointer" onClick={() => setOuvert("nouveau")}>
                            {t({ en: "New role", fr: "Nouveau rôle" })}
                        </Button>
                    ) : undefined
                }
            />
            {roles.length === 0 ? (
                <EtatVide cas="premier" icone={Shield} titre={t({ en: "No role", fr: "Aucun rôle" })} />
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Role", fr: "Rôle" }) },
                        { titre: t({ en: "Spaces", fr: "Espaces" }) },
                        { titre: t({ en: "Permissions", fr: "Permissions" }), droite: true },
                        { titre: t({ en: "Members", fr: "Membres" }), droite: true },
                    ]}
                >
                    {roles.map((r) => (
                        <Ligne key={r.id} onClick={() => setOuvert(r)}>
                            <Cellule principale>{r.nom}</Cellule>
                            <Cellule>
                                {[
                                    r.labo_ouvert ? t({ en: "Lab", fr: "Labo" }) : null,
                                    r.tous_les_clients
                                        ? t({ en: "every client", fr: "tous les clients" })
                                        : r.organisations.length
                                          ? `${r.organisations.length} ${t({ en: "client(s)", fr: "client(s)" })}`
                                          : null,
                                ]
                                    .filter(Boolean)
                                    .join(" · ") || "—"}
                            </Cellule>
                            <Cellule droite>
                                {r.fixe ? `${catalogue.length}` : r.permissions.length}
                                {" / "}
                                {catalogue.length}
                            </Cellule>
                            <Cellule droite>{r.membres}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}

            {ouvert !== null && (
                <FenetreChamps
                    ouverte
                    fermer={() => setOuvert(null)}
                    titre={role ? role.nom : t({ en: "New role", fr: "Nouveau rôle" })}
                    info={
                        role?.fixe
                            ? t({
                                  en: "The Administrator role cannot be changed or deleted; there is always one administrator left.",
                                  fr: "Le rôle Administrateur ne se modifie ni ne se supprime ; il reste toujours un administrateur.",
                              })
                            : undefined
                    }
                    sections={sectionsDuRole(role, catalogue, clients, t)}
                    valider={lecture ? t({ en: "Close", fr: "Fermer" }) : t({ en: "Save", fr: "Enregistrer" })}
                    onValider={lecture ? undefined : (v) => void enregistrer(role, v)}
                    pied={
                        role && !role.fixe && peutGerer ? (
                            <Button
                                variant="destructive"
                                className="cursor-pointer"
                                onClick={async () => {
                                    const res = await supprimerUnRoleApiV1EquipeMarkRolesRoleIdDelete({ path: { role_id: role.id } });
                                    if (res.error) toast.error(detailFromError(res.error, t({ en: "The role was not deleted", fr: "Le rôle n'a pas été supprimé" })));
                                    else {
                                        setOuvert(null);
                                        void charger();
                                    }
                                }}
                            >
                                {t({ en: "Delete the role", fr: "Supprimer le rôle" })}
                            </Button>
                        ) : undefined
                    }
                />
            )}
        </div>
    );
}
