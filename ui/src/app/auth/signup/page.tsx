"use client";

/**
 * [.mark] Le premier compte de l'installation (K1) : l'écran de l'amont est remplacé par un écran à la forme de la
 * maquette (cadre des pages d'accès, mêmes champs que « Rejoindre l'équipe .mark »). Le serveur ne l'accepte que tant
 * que l'installation n'a aucun compte (`signup_enabled`) ; ce compte devient Administrateur et son organisation le Labo.
 */
import { useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { signupApiV1AuthSignupPost } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { CadreAcces, ChampAcces, PiedAcces } from "@/components/mark/studio/cadre-acces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const MOT_DE_PASSE_MIN = 12;

export default function PagePremierCompte() {
    const { t } = useLangue();
    const [prenom, setPrenom] = useState("");
    const [nom, setNom] = useState("");
    const [email, setEmail] = useState("");
    const [motDePasse, setMotDePasse] = useState("");
    const [confirmation, setConfirmation] = useState("");
    const [enCours, setEnCours] = useState(false);

    const tropCourt = motDePasse.length > 0 && motDePasse.length < MOT_DE_PASSE_MIN;
    const different = confirmation.length > 0 && confirmation !== motDePasse;

    const envoyer = async (e: React.FormEvent) => {
        e.preventDefault();
        if (motDePasse.length < MOT_DE_PASSE_MIN || motDePasse !== confirmation) return;
        setEnCours(true);
        try {
            const res = await signupApiV1AuthSignupPost({
                body: { email, password: motDePasse, name: [prenom, nom].filter(Boolean).join(" ") || null },
            });
            if (res.error || !res.data) {
                notifier.echec({ fr: "Compte non créé. Vérifiez vos informations et réessayez.", en: "Account not created. Check your details and try again." }, { erreur: res.error });
                return;
            }
            await fetch("/api/auth/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: res.data.token, user: res.data.user }),
            });
            window.location.href = "/after-sign-in";
        } catch {
            notifier.echec({ fr: "Compte non créé. Réessayez dans un instant.", en: "Account not created. Try again in a moment." });
        } finally {
            setEnCours(false);
        }
    };

    return (
        <CadreAcces
            titre={t({ en: "Create the first account", fr: "Créer le premier compte" })}
            sousTitre={t({ en: "The .mark team's workshop.", fr: "L'atelier de l'équipe .mark." })}
        >
            <form onSubmit={envoyer} className="space-y-4">
                <ChampAcces libelle={t({ en: "Email", fr: "E-mail" })}>
                    <Input
                        type="email"
                        autoComplete="username"
                        placeholder={t({ en: "first.last@company.com", fr: "prenom@agence-mark.com" })}
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                    />
                </ChampAcces>
                <div className="grid grid-cols-2 gap-3">
                    <ChampAcces libelle={t({ en: "First name", fr: "Prénom" })}>
                        <Input autoComplete="given-name" value={prenom} onChange={(e) => setPrenom(e.target.value)} required />
                    </ChampAcces>
                    <ChampAcces libelle={t({ en: "Last name", fr: "Nom" })}>
                        <Input autoComplete="family-name" value={nom} onChange={(e) => setNom(e.target.value)} required />
                    </ChampAcces>
                </div>
                <ChampAcces libelle={t({ en: "Password", fr: "Mot de passe" })} aide={tropCourt ? undefined : t({ en: "12 characters at least.", fr: "12 caractères au moins." })}>
                    <Input
                        type="password"
                        autoComplete="new-password"
                        value={motDePasse}
                        onChange={(e) => setMotDePasse(e.target.value)}
                        required
                        className={tropCourt ? "border-(--pastille-urgente)" : ""}
                    />
                    {tropCourt && (
                        <span className="block text-xs text-(--marque-danger-texte)">{t({ en: "12 characters at least.", fr: "12 caractères au moins." })}</span>
                    )}
                </ChampAcces>
                <ChampAcces libelle={t({ en: "Confirm the password", fr: "Confirmer le mot de passe" })}>
                    <Input
                        type="password"
                        autoComplete="new-password"
                        value={confirmation}
                        onChange={(e) => setConfirmation(e.target.value)}
                        required
                        className={different ? "border-(--pastille-urgente)" : ""}
                    />
                    {different && (
                        <span className="block text-xs text-(--marque-danger-texte)">
                            {t({ en: "The two passwords differ.", fr: "Les deux mots de passe diffèrent." })}
                        </span>
                    )}
                </ChampAcces>
                <Button type="submit" className="w-full" disabled={enCours || motDePasse.length < MOT_DE_PASSE_MIN || motDePasse !== confirmation}>
                    {enCours ? t({ en: "Creating...", fr: "Création..." }) : t({ en: "Create my account", fr: "Créer mon compte" })}
                </Button>
            </form>
            <PiedAcces>
                {t({
                    en: "This account becomes Administrator and its organization becomes the Lab. Afterwards, members join by invitation.",
                    fr: "Ce compte devient Administrateur et son organisation devient le Labo. Ensuite, on entre par invitation.",
                })}
            </PiedAcces>
        </CadreAcces>
    );
}
