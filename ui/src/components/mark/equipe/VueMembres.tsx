"use client";

import { Copy, Mail, Trash2, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";
import type { Texte } from "@/components/mark/langue/langue";

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
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { fenetrePage, Paginee } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/dateTime";
import { Input } from "@/components/ui/input";

/** Rend les données d'une réponse, ou affiche l'erreur du serveur et rend `null`. */
export function lireOuSignaler<T>(res: { data?: T; error?: unknown }, echec: Texte): T | null {
    if (res.error || res.data === undefined) {
        notifier.echec(echec, { erreur: res.error });
        return null;
    }
    return res.data;
}

const identite = (m: Pick<MembreResponse, "prenom" | "nom" | "email">) =>
    [m.prenom, m.nom].filter(Boolean).join(" ") || m.email || "";

export function VueMembres() {
    const { t, langue } = useLangue();
    const [page, setPage] = useState(0);
    const [pageInv, setPageInv] = useState(0);
    const [membres, setMembres] = useState<{ lignes: MembreResponse[]; total: number } | null>(null);
    const [invitations, setInvitations] = useState<{ lignes: InvitationResponse[]; total: number }>({ lignes: [], total: 0 });
    const [roles, setRoles] = useState<RoleResponse[]>([]);
    const [inviter, setInviter] = useState(false);
    const [ouvert, setOuvert] = useState<MembreResponse | null>(null);
    const [invitation, setInvitation] = useState<InvitationResponse | null>(null);
    const [lien, setLien] = useState<{ lien: string; envoye: boolean; email: string } | null>(null);

    const charger = useCallback(async () => {
        const [m, i, r] = await Promise.all([
            listerLesMembresApiV1EquipeMarkMembresGet({ query: fenetrePage(page) }),
            listerLesInvitationsApiV1EquipeMarkInvitationsGet({ query: fenetrePage(pageInv) }),
            listerLesRolesApiV1EquipeMarkRolesGet(),
        ]);
        const membresLus = lireOuSignaler(m, { fr: "Membres illisibles. Rechargez la page.", en: "Could not load members. Reload the page." });
        if (membresLus) setMembres({ lignes: membresLus.membres, total: membresLus.total });
        const invitationsLues = lireOuSignaler(i, { fr: "Invitations illisibles. Rechargez la page.", en: "Could not load invitations. Reload the page." });
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
        <div>
            <section className="space-y-6">
                <TitreTableau
                    titre={t({ en: "Members", fr: "Membres" })}
                    info={
                        <Info>
                            {t({
                                en: "A member joins by invitation (single-use link, valid 48 h); open sign-up is closed. They use the keys of the organizations their role opens, without ever seeing them.",
                                fr: "Un membre entre par invitation (lien à usage unique, valable 48 h) ; l'inscription libre est fermée. Il utilise les clés des organisations que son rôle lui ouvre, sans jamais les voir.",
                            })}
                        </Info>
                    }
                    action={
                        <Button size="sm" onClick={() => setInviter(true)} disabled={roles.length === 0}>
                            <Mail className="size-3.5" /> {t({ en: "Invite", fr: "Inviter" })}
                        </Button>
                    }
                />
                {membres.total === 0 && invitations.total === 0 ? (
                    <EtatVide cas="premier" icone={Users} titre={t({ en: "No member yet", fr: "Aucun membre" })} />
                ) : (
                    <Paginee total={membres.total} page={page} changerPage={setPage}>
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Person", fr: "Personne" }) },
                                { titre: t({ en: "Role", fr: "Rôle" }) },
                                { titre: t({ en: "State", fr: "État" }) },
                                { titre: t({ en: "Since", fr: "Depuis" }), droite: true },
                            ]}
                        >
                            {membres.lignes.map((m) => (
                                <Ligne key={`m${m.user_id}`} onClick={() => setOuvert(m)}>
                                    <Cellule principale sous={identite(m) !== m.email ? m.email : undefined}>
                                        {identite(m)}
                                    </Cellule>
                                    <Cellule>{m.role_nom}</Cellule>
                                    <Cellule>
                                        <PointEtat etat="publie">{t({ en: "Active", fr: "Actif" })}</PointEtat>
                                    </Cellule>
                                    <Cellule droite>{m.depuis ? formatDate(m.depuis, null, langue) : "—"}</Cellule>
                                </Ligne>
                            ))}
                            {page === 0 &&
                                invitations.lignes.map((i) => (
                                    <Ligne key={`i${i.id}`} onClick={() => setInvitation(i)}>
                                        <Cellule principale>{i.email}</Cellule>
                                        <Cellule>{i.role_nom}</Cellule>
                                        <Cellule>
                                            <PointEtat etat="attente">{t({ en: "Invitation sent", fr: "Invitation envoyée" })}</PointEtat>
                                        </Cellule>
                                        <Cellule droite>—</Cellule>
                                    </Ligne>
                                ))}
                        </Tableau>
                    </Paginee>
                )}
            </section>

            {invitation && (
                <FenetreChamps
                    ouverte
                    fermer={() => setInvitation(null)}
                    titre={invitation.email}
                    info={t({
                        en: "The link has not been used yet. Revoking it closes it right away.",
                        fr: "Le lien n'a pas encore servi. Le révoquer le ferme tout de suite.",
                    })}
                    valider={t({ en: "Close", fr: "Fermer" })}
                    sections={[
                        {
                            champs: [
                                { id: "e", l: t({ en: "Email", fr: "E-mail" }), t: "lu", v: invitation.email },
                                { id: "r", l: t({ en: "Role", fr: "Rôle" }), t: "lu", v: invitation.role_nom },
                                { id: "x", l: t({ en: "Expires", fr: "Expire" }), t: "lu", v: new Date(invitation.expire_le).toLocaleString() },
                            ],
                        },
                    ]}
                    pied={
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-(--marque-danger-texte)"
                            onClick={async () => {
                                const res = await annulerUneInvitationApiV1EquipeMarkInvitationsInvitationIdDelete({
                                    path: { invitation_id: invitation.id },
                                });
                                if (res.error) notifier.echec({ fr: "Invitation non annulée. Réessayez.", en: "Invitation not cancelled. Try again." }, { erreur: res.error });
                                else {
                                    notifier.succes({ fr: "Invitation annulée.", en: "Invitation cancelled." });
                                    setInvitation(null);
                                    void charger();
                                }
                            }}
                        >
                            <Trash2 className="size-3.5" /> {t({ en: "Revoke the invitation", fr: "Révoquer l'invitation" })}
                        </Button>
                    }
                />
            )}

            <FenetreChamps
                ouverte={inviter}
                fermer={() => setInviter(false)}
                titre={t({ en: "Invite to the .mark team", fr: "Inviter dans l'équipe .mark" })}
                info={t({
                    en: "The link works once and expires after 48 hours. If a mail server is set for the installation, it is also sent by email; otherwise it is shown here to copy.",
                    fr: "Le lien sert une seule fois et expire au bout de 48 heures. Si l'installation a un serveur de mail, il part aussi par e-mail ; sinon il s'affiche ici pour être copié.",
                })}
                valider={t({ en: "Send the invitation", fr: "Envoyer l'invitation" })}
                sections={[
                    {
                        champs: [
                            { id: "email", l: t({ en: "Email", fr: "E-mail" }), t: "texte" },
                            { id: "role", l: t({ en: "Role", fr: "Rôle" }), t: "choix", o: nomsDeRoles, v: roleParNom("Membre")?.nom ?? nomsDeRoles[0] },
                        ],
                    },
                ]}
                onValider={async (v) => {
                    const role = roleParNom(String(v.role));
                    if (!role) return;
                    const res = await inviterApiV1EquipeMarkInvitationsPost({ body: { email: String(v.email), role_id: role.id } });
                    const cree = lireOuSignaler(res, { fr: "Invitation non créée. Réessayez.", en: "Invitation not created. Try again." });
                    if (!cree) return;
                    setLien({ lien: cree.lien, envoye: cree.envoye, email: cree.email });
                    if (cree.envoye) notifier.succes({ fr: "Invitation envoyée.", en: "Invitation sent." });
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
                                    notifier.succes({ fr: "Lien copié.", en: "Link copied." });
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
                    info={t({
                        en: "Removing a member closes their access right away; what they did stays in the journal under their name.",
                        fr: "Retirer un membre ferme son accès tout de suite ; ce qu'il a fait reste au journal sous son nom.",
                    })}
                    sections={[
                        {
                            champs: [
                                { id: "e", l: t({ en: "Email", fr: "E-mail" }), t: "lu", v: ouvert.email ?? "" },
                                { id: "role", l: t({ en: "Role", fr: "Rôle" }), t: "choix", o: nomsDeRoles, v: ouvert.role_nom },
                            ],
                        },
                    ]}
                    pied={
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-(--marque-danger-texte)"
                            onClick={async () => {
                                const res = await retirerUnMembreApiV1EquipeMarkMembresUserIdDelete({ path: { user_id: ouvert.user_id } });
                                if (res.error) notifier.echec({ fr: "Membre non retiré. Réessayez.", en: "Member not removed. Try again." }, { erreur: res.error });
                                else {
                                    notifier.succes({ fr: "Membre retiré.", en: "Member removed." });
                                    setOuvert(null);
                                    void charger();
                                }
                            }}
                        >
                            <Trash2 className="size-3.5" /> {t({ en: "Remove from the team", fr: "Retirer de l'équipe" })}
                        </Button>
                    }
                    onValider={async (v) => {
                        const role = roleParNom(String(v.role));
                        if (!role || role.id === ouvert.role_id) return;
                        const res = await changerLeRoleDUnMembreApiV1EquipeMarkMembresUserIdRolePut({
                            path: { user_id: ouvert.user_id },
                            body: { role_id: role.id },
                        });
                        if (res.error) notifier.echec({ fr: "Rôle inchangé. Réessayez.", en: "Role unchanged. Try again." }, { erreur: res.error });
                        else notifier.succes({ fr: "Rôle changé.", en: "Role changed." });
                        void charger();
                    }}
                />
            )}
        </div>
    );
}
