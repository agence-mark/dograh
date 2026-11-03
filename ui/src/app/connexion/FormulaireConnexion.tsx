"use client";

import Link from "next/link";
import { useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { loginApiV1AuthLoginPost } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { CadreAcces, ChampAcces, PiedAcces } from "@/components/mark/studio/cadre-acces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * [.mark] La connexion dans la forme de la maquette (`PageConnexion`, K1). `premierCompte` : l'installation est vide,
 * le premier compte peut s'inscrire (c'est la seule inscription ; ensuite, on entre par invitation).
 */
export function FormulaireConnexion({ premierCompte }: { premierCompte: boolean }) {
    const { t } = useLangue();
    const [email, setEmail] = useState("");
    const [motDePasse, setMotDePasse] = useState("");
    const [enCours, setEnCours] = useState(false);

    const envoyer = async (e: React.FormEvent) => {
        e.preventDefault();
        setEnCours(true);
        try {
            const res = await loginApiV1AuthLoginPost({ body: { email, password: motDePasse } });
            if (res.error || !res.data) {
                notifier.echec({ fr: "Connexion impossible. Vérifiez l'adresse et le mot de passe.", en: "Sign-in failed. Check your email and password." }, { erreur: res.error });
                return;
            }
            await fetch("/api/auth/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: res.data.token, user: res.data.user }),
            });
            window.location.href = "/after-sign-in";
        } catch {
            notifier.echec({ fr: "Connexion impossible. Réessayez dans un instant.", en: "Sign-in failed. Try again in a moment." });
        } finally {
            setEnCours(false);
        }
    };

    return (
        <CadreAcces
            titre={t({ en: "Sign in", fr: "Se connecter" })}
            sousTitre={t({ en: "The .mark team's workshop.", fr: "L'atelier de l'équipe .mark." })}
        >
            <form onSubmit={envoyer} className="space-y-4">
                <ChampAcces libelle={t({ en: "Email", fr: "E-mail" })}>
                    <Input
                        id="email"
                        type="email"
                        autoComplete="username"
                        placeholder="prenom@agence-mark.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                    />
                </ChampAcces>
                <ChampAcces libelle={t({ en: "Password", fr: "Mot de passe" })}>
                    <Input
                        id="mot-de-passe"
                        type="password"
                        autoComplete="current-password"
                        value={motDePasse}
                        onChange={(e) => setMotDePasse(e.target.value)}
                        required
                    />
                </ChampAcces>
                <Button type="submit" className="w-full" disabled={enCours}>
                    {enCours ? t({ en: "Signing in...", fr: "Connexion..." }) : t({ en: "Sign in", fr: "Se connecter" })}
                </Button>
            </form>
            <PiedAcces>
                {premierCompte ? (
                    <>
                        {t({ en: "New installation?", fr: "Nouvelle installation ?" })}{" "}
                        <Link href="/auth/signup" className="font-medium text-foreground hover:font-semibold">
                            {t({ en: "Create the first account", fr: "Créer le premier compte" })}
                        </Link>
                    </>
                ) : (
                    t({
                        en: "No account? A member of the team invites you from Settings › Team and roles.",
                        fr: "Pas de compte ? Un membre de l'équipe vous invite depuis Réglages › Équipe et rôles.",
                    })
                )}
            </PiedAcces>
        </CadreAcces>
    );
}
