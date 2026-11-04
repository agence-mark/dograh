"use client";

/**
 * [.mark] La fenêtre d'un rôle, dans la forme de la maquette (`FenetreRole`, K1) : un nom, les espaces ouverts (le Labo et
 * tous les clients, ou des clients choisis), puis les permissions par groupe, chacune avec sa clé technique en dessous.
 * Rien d'inventé : le Labo est une pastille de plus dans « Des clients choisis », car le modèle du serveur ouvre le Labo
 * et les clients séparément.
 */
import { Trash2 } from "lucide-react";
import { useState } from "react";

import type { PermissionResponse, RoleResponse } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { FenetreChamps, type RetourValidation } from "@/components/mark/studio/fenetre-champs";
import { Info } from "@/components/mark/studio/marques";
import { SuppressionConfirmee } from "@/components/mark/studio/suppression-confirmee";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

export type CorpsRole = {
    nom: string;
    labo_ouvert: boolean;
    tous_les_clients: boolean;
    permissions: string[];
    organisations: number[];
};

export function FenetreRole({
    role,
    catalogue,
    clients,
    lecture,
    fermer,
    enregistrer,
    supprimer,
}: {
    role: RoleResponse | null;
    catalogue: PermissionResponse[];
    clients: { id: number; nom: string }[];
    lecture: boolean;
    fermer: () => void;
    enregistrer: (corps: CorpsRole) => RetourValidation;
    supprimer?: () => void;
}) {
    const { t } = useLangue();
    const fixe = Boolean(role?.fixe);
    const [nom, setNom] = useState(role?.nom ?? "");
    const [tous, setTous] = useState(role ? role.labo_ouvert && role.tous_les_clients : true);
    const [labo, setLabo] = useState(role?.labo_ouvert ?? true);
    const [choisis, setChoisis] = useState<number[]>(role?.organisations ?? []);
    const [perms, setPerms] = useState<string[]>(role?.permissions ?? []);
    const fige = lecture || fixe;

    const groupes = new Map<string, PermissionResponse[]>();
    for (const p of catalogue) groupes.set(p.groupe, [...(groupes.get(p.groupe) ?? []), p]);

    const pastille = (actif: boolean, libelle: string, cle: string, basculer: () => void) => (
        <button
            key={cle}
            type="button"
            disabled={fige}
            onClick={basculer}
            className={`rounded-full border px-2.5 py-1 text-xs ${actif ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:font-medium"}`}
        >
            {libelle}
        </button>
    );

    return (
        <FenetreChamps
            ouverte
            fermer={fermer}
            titre={role ? role.nom : t({ en: "New role", fr: "Nouveau rôle" })}
            info={
                fixe
                    ? t({
                          en: "The Administrator role cannot be changed or deleted; there is always one administrator left.",
                          fr: "Le rôle Administrateur ne se modifie ni ne se supprime ; il reste toujours un administrateur.",
                      })
                    : t({
                          en: "A role is a list of permissions and the spaces it opens. Changing a role changes the rights of all its members at once.",
                          fr: "Un rôle est une liste de permissions et les espaces qu'il ouvre. Changer un rôle change aussitôt les droits de tous ses membres.",
                      })
            }
            sections={[]}
            lecture={lecture || fixe}
            valider={lecture || fixe ? t({ en: "Close", fr: "Fermer" }) : t({ en: "Save", fr: "Enregistrer" })}
            onValider={
                fige
                    ? undefined
                    : () =>
                          enregistrer({
                              nom,
                              labo_ouvert: tous || labo,
                              tous_les_clients: tous,
                              permissions: perms,
                              organisations: tous ? [] : choisis,
                          })
            }
            pied={
                role && !fixe && !lecture && supprimer ? (
                    <SuppressionConfirmee className="text-(--marque-danger-texte)" onConfirmer={supprimer}>
                        <Trash2 className="size-3.5" /> {t({ en: "Delete the role", fr: "Supprimer le rôle" })}
                    </SuppressionConfirmee>
                ) : undefined
            }
            corps={
                <>
                    <section>
                        <p className="pb-1 text-sm font-semibold">{t({ en: "Role", fr: "Rôle" })}</p>
                        <div className="divide-y">
                            <div className="space-y-2 py-3.5">
                                <p className="text-sm font-medium">{t({ en: "Name", fr: "Nom" })}</p>
                                <Input value={nom} onChange={(e) => setNom(e.target.value)} disabled={fige} aria-label={t({ en: "Name", fr: "Nom" })} />
                            </div>
                            <div className="space-y-2 py-3.5">
                                <p className="flex items-center gap-1.5 text-sm font-medium">
                                    {t({ en: "Spaces opened", fr: "Espaces ouverts" })}
                                    <Info>
                                        {t({
                                            en: "The Lab and the clients its members see. « All » includes the clients created later.",
                                            fr: "Le Labo et les clients que voient ses membres. « Tous » comprend les clients créés plus tard.",
                                        })}
                                    </Info>
                                </p>
                                <span className={`inline-flex rounded-lg bg-muted p-0.5 text-sm ${fige ? "pointer-events-none opacity-60" : ""}`}>
                                    {[true, false].map((v) => (
                                        <button
                                            key={String(v)}
                                            type="button"
                                            onClick={() => setTous(v)}
                                            className={`rounded-md px-3 py-1 ${tous === v ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                                        >
                                            {v ? t({ en: "The Lab and every client", fr: "Le Labo et tous les clients" }) : t({ en: "Chosen clients", fr: "Des clients choisis" })}
                                        </button>
                                    ))}
                                </span>
                                {!tous && (
                                    <div className="flex flex-wrap gap-1.5 pt-1">
                                        {pastille(labo, t({ en: "The Lab", fr: "Le Labo" }), "labo", () => setLabo(!labo))}
                                        {clients.map((c) =>
                                            pastille(choisis.includes(c.id), c.nom, String(c.id), () =>
                                                setChoisis(choisis.includes(c.id) ? choisis.filter((y) => y !== c.id) : [...choisis, c.id]),
                                            ),
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </section>
                    {[...groupes.entries()].map(([groupe, liste]) => (
                        <section key={groupe}>
                            <p className="pb-1 text-sm font-semibold">{groupe}</p>
                            <div className="divide-y">
                                {liste.map((p) => (
                                    <div key={p.cle} className="flex items-center gap-4 py-3">
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm">{p.libelle}</p>
                                            <p className="font-mono text-[11px] text-muted-foreground">{p.cle}</p>
                                        </div>
                                        <Switch
                                            checked={fixe || perms.includes(p.cle)}
                                            disabled={fige}
                                            aria-label={p.libelle}
                                            onCheckedChange={(v) => setPerms(v ? [...perms, p.cle] : perms.filter((x) => x !== p.cle))}
                                        />
                                    </div>
                                ))}
                            </div>
                        </section>
                    ))}
                </>
            }
        />
    );
}
