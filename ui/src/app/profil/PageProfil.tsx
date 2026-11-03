"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
    changerMonMotDePasseApiV1EquipeMarkMoiMotDePassePost,
    modifierMonProfilApiV1EquipeMarkMoiPatch,
    monProfilApiV1EquipeMarkMoiGet,
} from "@/client/sdk.gen";
import type { ProfilResponse } from "@/client/types.gen";
import { type Langue, useLangue } from "@/components/mark/langue/langue";
import { LigneChamp } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

const MOT_DE_PASSE_MIN = 12;

/** Un champ en lecture seule : le texte, sans bouton Copier (E59). */
const Lu = ({ children }: { children: React.ReactNode }) => <span className="text-sm text-muted-foreground">{children}</span>;

/** [.mark] Mon profil (U2 ter, E59) : identité, rôle lu, mot de passe, langue, alertes par e-mail. Tout vient de `GET /equipe-mark/moi`. */
export function PageProfil() {
    const { t, choisir } = useLangue();
    const { user, loading } = useAuth();
    const [profil, setProfil] = useState<ProfilResponse | null>(null);
    const [prenom, setPrenom] = useState("");
    const [nom, setNom] = useState("");
    const [actuel, setActuel] = useState("");
    const [nouveau, setNouveau] = useState("");
    const [confirmation, setConfirmation] = useState("");
    const [enCours, setEnCours] = useState(false);
    const lu = useRef(false);

    useEffect(() => {
        if (loading || !user || lu.current) return;
        lu.current = true;
        monProfilApiV1EquipeMarkMoiGet().then((res) => {
            if (res.error || !res.data) {
                toast.error(detailFromError(res.error, t({ en: "The profile could not be read", fr: "Le profil n'a pas pu être lu" })));
                return;
            }
            setProfil(res.data);
            setPrenom(res.data.prenom ?? "");
            setNom(res.data.nom ?? "");
        });
    }, [loading, user, t]);

    const modifier = async (corps: { prenom?: string; nom?: string; langue?: string; alertes_mail?: boolean }) => {
        const res = await modifierMonProfilApiV1EquipeMarkMoiPatch({ body: corps });
        if (res.error || !res.data) {
            toast.error(detailFromError(res.error, t({ en: "The change failed", fr: "La modification a échoué" })));
            return false;
        }
        setProfil(res.data);
        return true;
    };

    const changerMotDePasse = async () => {
        setEnCours(true);
        try {
            const res = await changerMonMotDePasseApiV1EquipeMarkMoiMotDePassePost({ body: { actuel, nouveau } });
            if (res.error) {
                toast.error(detailFromError(res.error, t({ en: "The password was not changed", fr: "Le mot de passe n'a pas changé" })));
                return;
            }
            setActuel("");
            setNouveau("");
            setConfirmation("");
            toast.success(t({ en: "Password changed", fr: "Mot de passe changé" }));
        } finally {
            setEnCours(false);
        }
    };

    if (!profil) return <div className="mx-auto w-full max-w-2xl p-6" />;

    const peutChangerLeMotDePasse = actuel.length > 0 && nouveau.length >= MOT_DE_PASSE_MIN && nouveau === confirmation;
    const nomModifie = prenom !== (profil.prenom ?? "") || nom !== (profil.nom ?? "");

    return (
        <div className="mx-auto w-full max-w-2xl space-y-8 p-6">
            <TitrePage titre={t({ en: "My profile", fr: "Mon profil" })} />

            <section>
                <p className="pb-1 text-sm font-semibold">{t({ en: "Identity", fr: "Identité" })}</p>
                <div className="divide-y">
                    <LigneChamp libelle={t({ en: "First name", fr: "Prénom" })}>
                        <Input className="w-64" value={prenom} onChange={(e) => setPrenom(e.target.value)} disabled={!profil.role} />
                    </LigneChamp>
                    <LigneChamp libelle={t({ en: "Last name", fr: "Nom" })}>
                        <Input className="w-64" value={nom} onChange={(e) => setNom(e.target.value)} disabled={!profil.role} />
                    </LigneChamp>
                    <LigneChamp libelle={t({ en: "Email", fr: "Adresse e-mail" })}>
                        <Lu>{profil.email}</Lu>
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "Role", fr: "Rôle" })}
                        info={t({
                            en: "Your role sets the spaces you can open and what you can do. An administrator changes it.",
                            fr: "Votre rôle fixe les espaces que vous ouvrez et ce que vous pouvez faire. Un administrateur le change.",
                        })}
                    >
                        <Lu>{profil.role ?? t({ en: "None", fr: "Aucun" })}</Lu>
                    </LigneChamp>
                </div>
                {nomModifie && (
                    <div className="flex justify-end pt-3">
                        <Button className="cursor-pointer" onClick={() => void modifier({ prenom, nom })}>
                            {t({ en: "Save", fr: "Enregistrer" })}
                        </Button>
                    </div>
                )}
            </section>

            <section>
                <p className="pb-1 text-sm font-semibold">{t({ en: "Preferences", fr: "Préférences" })}</p>
                <div className="divide-y">
                    <LigneChamp libelle={t({ en: "Language", fr: "Langue" })}>
                        <Liste
                            className="w-40"
                            valeur={profil.langue}
                            options={[
                                { valeur: "fr", libelle: "Français" },
                                { valeur: "en", libelle: "English" },
                            ]}
                            changer={(v) => {
                                void modifier({ langue: v }).then((ok) => ok && choisir(v as Langue));
                            }}
                        />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "Email alerts", fr: "Alertes par e-mail" })}
                        info={t({
                            en: "Receive the alerts of the organizations you can open by email.",
                            fr: "Recevoir par e-mail les alertes des organisations que vous ouvrez.",
                        })}
                    >
                        <Switch
                            checked={profil.alertes_mail}
                            onCheckedChange={(v) => void modifier({ alertes_mail: v })}
                            aria-label={t({ en: "Email alerts", fr: "Alertes par e-mail" })}
                        />
                    </LigneChamp>
                </div>
            </section>

            <section>
                <p className="pb-1 text-sm font-semibold">{t({ en: "Password", fr: "Mot de passe" })}</p>
                <div className="divide-y">
                    <LigneChamp libelle={t({ en: "Current password", fr: "Mot de passe actuel" })}>
                        <Input className="w-64" type="password" autoComplete="current-password" value={actuel} onChange={(e) => setActuel(e.target.value)} />
                    </LigneChamp>
                    <LigneChamp
                        libelle={t({ en: "New password", fr: "Nouveau mot de passe" })}
                        info={t({ en: "12 characters at least.", fr: "12 caractères au moins." })}
                    >
                        <Input className="w-64" type="password" autoComplete="new-password" value={nouveau} onChange={(e) => setNouveau(e.target.value)} />
                    </LigneChamp>
                    <LigneChamp libelle={t({ en: "Confirm", fr: "Confirmation" })}>
                        <Input className="w-64" type="password" autoComplete="new-password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
                    </LigneChamp>
                </div>
                <div className="flex justify-end pt-3">
                    <Button className="cursor-pointer" disabled={!peutChangerLeMotDePasse || enCours} onClick={() => void changerMotDePasse()}>
                        {t({ en: "Change the password", fr: "Changer le mot de passe" })}
                    </Button>
                </div>
            </section>
        </div>
    );
}
