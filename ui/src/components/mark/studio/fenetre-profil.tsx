"use client";

/**
 * [.mark] « Mon profil » (E59) : la fenêtre de la maquette (`FenetreProfil`), ouverte depuis le compte en bas de la barre
 * latérale. Identité, mot de passe, préférences ; tout vient de `/equipe-mark/moi` et rien n'est affiché qui n'existe pas
 * côté serveur (l'adresse e-mail et le rôle se lisent seulement).
 */
import { toast } from "sonner";

import { changerMonMotDePasseApiV1EquipeMarkMoiMotDePassePost, modifierMonProfilApiV1EquipeMarkMoiPatch } from "@/client/sdk.gen";
import type { ProfilResponse } from "@/client/types.gen";
import { type Langue, useLangue } from "@/components/mark/langue/langue";
import { detailFromError } from "@/lib/apiError";

import { FenetreChamps, type Valeurs } from "./fenetre-champs";

const MOT_DE_PASSE_MIN = 12;

export function FenetreProfil({
    profil,
    ouverte,
    fermer,
    apres,
}: {
    profil: ProfilResponse | null;
    ouverte: boolean;
    fermer: () => void;
    apres?: (p: ProfilResponse) => void;
}) {
    const { t, choisir } = useLangue();
    if (!profil) return null;

    const enregistrer = async (v: Valeurs) => {
        const corps: { prenom?: string; nom?: string; langue?: string; alertes_mail?: boolean } = {};
        if (v.prenom !== (profil.prenom ?? "")) corps.prenom = String(v.prenom);
        if (v.nom !== (profil.nom ?? "")) corps.nom = String(v.nom);
        if (v.langue !== (profil.langue === "en" ? "English" : "Français")) corps.langue = v.langue === "English" ? "en" : "fr";
        if (v.alertes !== profil.alertes_mail) corps.alertes_mail = v.alertes === true;
        if (Object.keys(corps).length) {
            const res = await modifierMonProfilApiV1EquipeMarkMoiPatch({ body: corps });
            if (res.error || !res.data) {
                toast.error(detailFromError(res.error, t({ en: "The change failed", fr: "La modification a échoué" })));
                return;
            }
            apres?.(res.data);
            if (corps.langue) choisir(corps.langue as Langue);
        }
        const actuel = String(v.actuel);
        const nouveau = String(v.nouveau);
        if (actuel || nouveau) {
            if (!actuel || nouveau.length < MOT_DE_PASSE_MIN) {
                toast.error(t({ en: "The password was not changed: 12 characters at least.", fr: "Le mot de passe n'a pas changé : 12 caractères au moins." }));
                return;
            }
            const res = await changerMonMotDePasseApiV1EquipeMarkMoiMotDePassePost({ body: { actuel, nouveau } });
            if (res.error) {
                toast.error(detailFromError(res.error, t({ en: "The password was not changed", fr: "Le mot de passe n'a pas changé" })));
                return;
            }
            toast.success(t({ en: "Password changed", fr: "Mot de passe changé" }));
        }
    };

    return (
        <FenetreChamps
            ouverte={ouverte}
            fermer={fermer}
            titre={t({ en: "My profile", fr: "Mon profil" })}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            onValider={(v) => void enregistrer(v)}
            sections={[
                {
                    titre: t({ en: "Identity", fr: "Identité" }),
                    champs: [
                        { id: "prenom", t: "texte", l: t({ en: "First name", fr: "Prénom" }), v: profil.prenom ?? "" },
                        { id: "nom", t: "texte", l: t({ en: "Last name", fr: "Nom" }), v: profil.nom ?? "" },
                        {
                            id: "email",
                            t: "lu",
                            l: t({ en: "Email", fr: "E-mail" }),
                            v: profil.email ?? "",
                            info: t({
                                en: "Used to sign in and to receive invitations and alerts.",
                                fr: "Sert à se connecter et à recevoir les invitations et les alertes.",
                            }),
                        },
                        {
                            id: "role",
                            t: "lu",
                            l: t({ en: "Role", fr: "Rôle" }),
                            v: profil.role ?? t({ en: "None", fr: "Aucun" }),
                            info: t({
                                en: "Changed by a member who can invite, remove and change a role.",
                                fr: "Changé par un membre qui a la permission « Inviter, retirer, changer un rôle ».",
                            }),
                        },
                    ],
                },
                {
                    titre: t({ en: "Password", fr: "Mot de passe" }),
                    champs: [
                        { id: "actuel", t: "secret", l: t({ en: "Current password", fr: "Mot de passe actuel" }) },
                        {
                            id: "nouveau",
                            t: "secret",
                            l: t({ en: "New password", fr: "Nouveau mot de passe" }),
                            info: t({ en: "12 characters at least.", fr: "12 caractères au moins." }),
                        },
                    ],
                },
                {
                    titre: t({ en: "Preferences", fr: "Préférences" }),
                    champs: [
                        {
                            id: "langue",
                            t: "choix",
                            l: t({ en: "Screen language", fr: "Langue de l'écran" }),
                            o: ["Français", "English"],
                            v: profil.langue === "en" ? "English" : "Français",
                        },
                        {
                            id: "alertes",
                            t: "inter",
                            l: t({ en: "Receive alerts by email", fr: "Recevoir les alertes par e-mail" }),
                            v: profil.alertes_mail,
                            info: t({
                                en: "Receive by email the alerts of the organizations you can open.",
                                fr: "Recevoir par e-mail les alertes des organisations que vous ouvrez.",
                            }),
                        },
                    ],
                },
            ]}
        />
    );
}
