"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { loginApiV1AuthLoginPost } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { CadreAcces } from "@/components/mark/studio/cadre-acces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";

/** [.mark] La connexion au nouveau design (U2 ter). `premierCompte` : l'installation est vide, le premier compte peut s'inscrire. */
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
                toast.error(detailFromError(res.error, t({ en: "Sign-in failed", fr: "Connexion impossible" })));
                return;
            }
            await fetch("/api/auth/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: res.data.token, user: res.data.user }),
            });
            window.location.href = "/after-sign-in";
        } catch {
            toast.error(t({ en: "An error occurred. Please try again.", fr: "Une erreur est survenue. Réessayez." }));
        } finally {
            setEnCours(false);
        }
    };

    return (
        <CadreAcces
            titre={t({ en: "Sign in", fr: "Connexion" })}
            sousTitre={t({ en: "Enter your email and password", fr: "Saisissez votre adresse et votre mot de passe" })}
        >
            <form onSubmit={envoyer} className="space-y-4">
                <div className="space-y-2">
                    <Label htmlFor="email">{t({ en: "Email", fr: "Adresse e-mail" })}</Label>
                    <Input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </div>
                <div className="space-y-2">
                    <Label htmlFor="mot-de-passe">{t({ en: "Password", fr: "Mot de passe" })}</Label>
                    <Input
                        id="mot-de-passe"
                        type="password"
                        autoComplete="current-password"
                        value={motDePasse}
                        onChange={(e) => setMotDePasse(e.target.value)}
                        required
                    />
                </div>
                <Button type="submit" className="w-full cursor-pointer" disabled={enCours}>
                    {enCours ? t({ en: "Signing in...", fr: "Connexion..." }) : t({ en: "Sign in", fr: "Se connecter" })}
                </Button>
            </form>
            {premierCompte && (
                <p className="text-center text-sm text-muted-foreground">
                    {t({ en: "New installation?", fr: "Nouvelle installation ?" })}{" "}
                    <Link href="/auth/signup" className="cursor-pointer text-primary hover:font-medium">
                        {t({ en: "Create the first account", fr: "Créer le premier compte" })}
                    </Link>
                </p>
            )}
        </CadreAcces>
    );
}
