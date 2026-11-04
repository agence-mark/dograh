"use client";

import { Plus, Shield } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";

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
import { Info } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { listerEspaces } from "@/lib/espaces";

import { type CorpsRole, FenetreRole } from "./FenetreRole";
import { lireOuSignaler } from "./VueMembres";

type Client = { id: number; nom: string };

export function VueRoles({ peutGerer }: { peutGerer: boolean }) {
    const { t } = useLangue();
    const [roles, setRoles] = useState<RoleResponse[] | null>(null);
    const [catalogue, setCatalogue] = useState<PermissionResponse[]>([]);
    const [clients, setClients] = useState<Client[]>([]);
    const [ouvert, setOuvert] = useState<RoleResponse | "nouveau" | null>(null);

    const charger = useCallback(async () => {
        const [r, c] = await Promise.all([listerLesRolesApiV1EquipeMarkRolesGet(), catalogueApiV1EquipeMarkPermissionsGet()]);
        const lus = lireOuSignaler(r, { fr: "Rôles illisibles. Rechargez la page.", en: "Could not load roles. Reload the page." });
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

    const enregistrer = async (role: RoleResponse | null, corps: CorpsRole) => {
        const res = role
            ? await modifierUnRoleApiV1EquipeMarkRolesRoleIdPut({ path: { role_id: role.id }, body: corps })
            : await creerUnRoleApiV1EquipeMarkRolesPost({ body: corps });
        if (res.error) notifier.echec({ fr: "Rôle non enregistré. Réessayez.", en: "Role not saved. Try again." }, { erreur: res.error });
        else notifier.succes({ fr: "Rôle enregistré.", en: "Role saved." });
        void charger();
    };

    const role = ouvert === "nouveau" ? null : ouvert;
    const lecture = Boolean(role?.fixe) || !peutGerer;

    return (
        <div className="space-y-6">
            <TitreTableau
                titre={t({ en: "Roles", fr: "Rôles" })}
                info={
                    <Info>
                        {t({
                            en: "A role is a set of permissions and the spaces it opens. Roles are created here, without code.",
                            fr: "Un rôle = des permissions et les espaces qu'il ouvre. Ils se créent ici, sans code.",
                        })}
                    </Info>
                }
                action={
                    peutGerer ? (
                        <Button variant="outline" size="sm" onClick={() => setOuvert("nouveau")}>
                            <Plus className="size-3.5" /> {t({ en: "Role", fr: "Rôle" })}
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
                            <Cellule principale sous={r.fixe ? t({ en: "fixed", fr: "fixe" }) : undefined}>
                                {r.nom}
                            </Cellule>
                            <Cellule>
                                {r.labo_ouvert && r.tous_les_clients
                                    ? t({ en: "The Lab and every client", fr: "Le Labo et tous les clients" })
                                    : [
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
                                {r.fixe ? catalogue.length : r.permissions.length} {t({ en: "of", fr: "sur" })} {catalogue.length}
                            </Cellule>
                            <Cellule droite>{r.membres}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}

            {ouvert !== null && (
                <FenetreRole
                    key={role ? role.id : "nouveau"}
                    role={role}
                    catalogue={catalogue}
                    clients={clients}
                    lecture={lecture}
                    fermer={() => setOuvert(null)}
                    enregistrer={(corps) => void enregistrer(role, corps)}
                    supprimer={
                        role
                            ? async () => {
                                  // suppression-confirmee : `FenetreRole` enveloppe `supprimer` dans `SuppressionConfirmee`.
                                  const res = await supprimerUnRoleApiV1EquipeMarkRolesRoleIdDelete({ path: { role_id: role.id } });
                                  if (res.error) notifier.echec({ fr: "Rôle non supprimé. Réessayez.", en: "Role not deleted. Try again." }, { erreur: res.error });
                                  else {
                                      notifier.succes({ fr: "Rôle supprimé.", en: "Role deleted." });
                                      setOuvert(null);
                                      void charger();
                                  }
                              }
                            : undefined
                    }
                />
            )}
        </div>
    );
}
