"use client";

import { Copy, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
    annulerUneInvitationApiV1EquipeMarkInvitationsInvitationIdDelete,
    changerLeRoleDUnMembreApiV1EquipeMarkMembresUserIdRolePut,
    inviterApiV1EquipeMarkInvitationsPost,
    listerLesInvitationsApiV1EquipeMarkInvitationsGet,
    listerLesMembresApiV1EquipeMarkMembresGet,
    listerLesRolesApiV1EquipeMarkRolesGet,
    retirerUnMembreApiV1EquipeMarkMembresUserIdDelete,
} from "@/client/sdk.gen";
import type { InvitationResponse, MembreResponse, RoleResponse } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Marque } from "@/components/mark/studio/marques";
import { fenetrePage, Paginee } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

/** Rend les données d'une réponse, ou affiche l'erreur du serveur et rend `null`. */
export function lireOuSignaler<T>(res: { data?: T; error?: unknown }, repli: string): T | null {
    if (res.error || res.data === undefined) {
        toast.error(detailFromError(res.error, repli));
        return null;
    }
    return res.data;
}

const identite = (m: Pick<MembreResponse, "prenom" | "nom" | "email">) =>
    [m.prenom, m.nom].filter(Boolean).join(" ") || m.email || "";

export function VueMembres() {
    const { t } = useLangue();
    const [page, setPage] = useState(0);
    const [pageInv, setPageInv] = useState(0);
    const [membres, setMembres] = useState<{ lignes: MembreResponse[]; total: number } | null>(null);
    const [invitations, setInvitations] = useState<{ lignes: InvitationResponse[]; total: number }>({ lignes: [], total: 0 });
    const [roles, setRoles] = useState<RoleResponse[]>([]);
    const [inviter, setInviter] = useState(false);
    const [ouvert, setOuvert] = useState<MembreResponse | null>(null);
    const [lien, setLien] = useState<{ lien: string; envoye: boolean; email: string } | null>(null);

    const charger = useCallback(async () => {
        const [m, i, r] = await Promise.all([
            listerLesMembresApiV1EquipeMarkMembresGet({ query: fenetrePage(page) }),
            listerLesInvitationsApiV1EquipeMarkInvitationsGet({ query: fenetrePage(pageInv) }),
            listerLesRolesApiV1EquipeMarkRolesGet(),
        ]);
        const membresLus = lireOuSignaler(m, t({ en: "The members could not be read", fr: "Les membres n'ont pas pu être lus" }));
        if (membresLus) setMembres({ lignes: membresLus.membres, total: membresLus.total });
        const invitationsLues = lireOuSignaler(i, t({ en: "The invitations could not be read", fr: "Les invitations n'ont pas pu être lues" }));
        if (invitationsLues) setInvitations({ lignes: invitationsLues.invitations, total: invitationsLues.total });
        if (r.data) setRoles(r.data);
    }, [page, pageInv, t]);

    useEffect(() => {
        void charger();
    }, [charger]);

    const nomsDeRoles = roles.map((r) => r.nom);
    const roleParNom = (nom: string) => roles.find((r) => r.nom === nom);

    if (!membres) return <EtatVide cas="chargement" />;

    return (
        <div className="space-y-8">
            <section>
                <TitreTableau
                    titre={t({ en: "Members", fr: "Membres" })}
                    action={
                        <Button className="cursor-pointer" onClick={() => setInviter(true)} disabled={roles.length === 0}>
                            {t({ en: "Invite", fr: "Inviter" })}
                        </Button>
                    }
                />
                {membres.total === 0 ? (
                    <EtatVide cas="premier" icone={Users} titre={t({ en: "No member yet", fr: "Aucun membre" })} />
                ) : (
                    <Paginee total={membres.total} page={page} changerPage={setPage}>
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Name", fr: "Nom" }) },
                                { titre: t({ en: "Email", fr: "Adresse e-mail" }) },
                                { titre: t({ en: "Role", fr: "Rôle" }) },
                            ]}
                        >
                            {membres.lignes.map((m) => (
                                <Ligne key={m.user_id} onClick={() => setOuvert(m)}>
                                    <Cellule principale>{identite(m)}</Cellule>
                                    <Cellule>{m.email}</Cellule>
                                    <Cellule>
                                        <Marque ton={m.role_nom === "Administrateur" ? "plein" : "neutre"}>{m.role_nom}</Marque>
                                    </Cellule>
                                </Ligne>
                            ))}
                        </Tableau>
                    </Paginee>
                )}
            </section>

            {invitations.total > 0 && (
                <section>
                    <TitreTableau titre={t({ en: "Pending invitations", fr: "Invitations en attente" })} />
                    <Paginee total={invitations.total} page={pageInv} changerPage={setPageInv}>
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Email", fr: "Adresse e-mail" }) },
                                { titre: t({ en: "Role", fr: "Rôle" }) },
                                { titre: t({ en: "Expires", fr: "Expire" }) },
                                { titre: "", droite: true },
                            ]}
                        >
                            {invitations.lignes.map((i) => (
                                <Ligne key={i.id}>
                                    <Cellule principale>{i.email}</Cellule>
                                    <Cellule>{i.role_nom}</Cellule>
                                    <Cellule>{new Date(i.expire_le).toLocaleString()}</Cellule>
                                    <Cellule droite>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="cursor-pointer hover:font-medium"
                                            onClick={async () => {
                                                const res = await annulerUneInvitationApiV1EquipeMarkInvitationsInvitationIdDelete({
                                                    path: { invitation_id: i.id },
                                                });
                                                if (res.error) toast.error(detailFromError(res.error, t({ en: "Not cancelled", fr: "Non annulée" })));
                                                else void charger();
                                            }}
                                        >
                                            {t({ en: "Cancel", fr: "Annuler" })}
                                        </Button>
                                    </Cellule>
                                </Ligne>
                            ))}
                        </Tableau>
                    </Paginee>
                </section>
            )}

            <FenetreChamps
                ouverte={inviter}
                fermer={() => setInviter(false)}
                titre={t({ en: "Invite a member", fr: "Inviter un membre" })}
                info={t({
                    en: "The link works once and expires after 48 hours. If a mail server is set for the installation, it is also sent by email; otherwise it is shown here to copy.",
                    fr: "Le lien sert une seule fois et expire au bout de 48 heures. Si l'installation a un serveur de mail, il part aussi par e-mail ; sinon il s'affiche ici pour être copié.",
                })}
                valider={t({ en: "Invite", fr: "Inviter" })}
                sections={[
                    {
                        champs: [
                            { id: "email", l: t({ en: "Email", fr: "Adresse e-mail" }), t: "texte" },
                            { id: "role", l: t({ en: "Role", fr: "Rôle" }), t: "choix", o: nomsDeRoles, v: roleParNom("Membre")?.nom ?? nomsDeRoles[0] },
                        ],
                    },
                ]}
                onValider={async (v) => {
                    const role = roleParNom(String(v.role));
                    if (!role) return;
                    const res = await inviterApiV1EquipeMarkInvitationsPost({ body: { email: String(v.email), role_id: role.id } });
                    const cree = lireOuSignaler(res, t({ en: "The invitation was not created", fr: "L'invitation n'a pas été créée" }));
                    if (!cree) return;
                    setLien({ lien: cree.lien, envoye: cree.envoye, email: cree.email });
                    void charger();
                }}
            />

            <FenetreChamps
                ouverte={lien !== null}
                fermer={() => setLien(null)}
                titre={t({ en: "Invitation link", fr: "Lien d'invitation" })}
                valider={t({ en: "Close", fr: "Fermer" })}
                sections={[
                    {
                        champs: [
                            { id: "a", l: t({ en: "Invited", fr: "Invité" }), t: "lu", v: lien?.email ?? "" },
                            {
                                id: "m",
                                l: t({ en: "Email sent", fr: "Envoyé par e-mail" }),
                                t: "lu",
                                v: lien?.envoye ? t({ en: "Yes", fr: "Oui" }) : t({ en: "No, copy the link", fr: "Non, copiez le lien" }),
                            },
                        ],
                    },
                ]}
                corps={
                    lien && (
                        <div className="flex items-center gap-2">
                            <Input readOnly value={lien.lien} aria-label={t({ en: "Invitation link", fr: "Lien d'invitation" })} onFocus={(e) => e.currentTarget.select()} />
                            <Button
                                variant="outline"
                                className="cursor-pointer"
                                onClick={() => {
                                    void navigator.clipboard.writeText(lien.lien);
                                    toast.success(t({ en: "Link copied", fr: "Lien copié" }));
                                }}
                            >
                                <Copy className="mr-2 size-4" />
                                {t({ en: "Copy", fr: "Copier" })}
                            </Button>
                        </div>
                    )
                }
            />

            {ouvert && (
                <FenetreChamps
                    ouverte
                    fermer={() => setOuvert(null)}
                    titre={identite(ouvert)}
                    valider={t({ en: "Save", fr: "Enregistrer" })}
                    sections={[
                        {
                            champs: [
                                { id: "e", l: t({ en: "Email", fr: "Adresse e-mail" }), t: "lu", v: ouvert.email ?? "" },
                                { id: "role", l: t({ en: "Role", fr: "Rôle" }), t: "choix", o: nomsDeRoles, v: ouvert.role_nom },
                            ],
                        },
                    ]}
                    pied={
                        <Button
                            variant="destructive"
                            className="cursor-pointer"
                            onClick={async () => {
                                const res = await retirerUnMembreApiV1EquipeMarkMembresUserIdDelete({ path: { user_id: ouvert.user_id } });
                                if (res.error) toast.error(detailFromError(res.error, t({ en: "Not removed", fr: "Non retiré" })));
                                else {
                                    setOuvert(null);
                                    void charger();
                                }
                            }}
                        >
                            {t({ en: "Remove from the team", fr: "Retirer de l'équipe" })}
                        </Button>
                    }
                    onValider={async (v) => {
                        const role = roleParNom(String(v.role));
                        if (!role || role.id === ouvert.role_id) return;
                        const res = await changerLeRoleDUnMembreApiV1EquipeMarkMembresUserIdRolePut({
                            path: { user_id: ouvert.user_id },
                            body: { role_id: role.id },
                        });
                        if (res.error) toast.error(detailFromError(res.error, t({ en: "Role not changed", fr: "Rôle non changé" })));
                        void charger();
                    }}
                />
            )}
        </div>
    );
}
