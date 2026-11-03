"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
    accepterUneInvitationApiV1AuthInvitationJetonAccepterPost,
    lireUneInvitationApiV1AuthInvitationJetonGet,
} from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { CadreAcces } from "@/components/mark/studio/cadre-acces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";

const MOT_DE_PASSE_MIN = 12;

/** [.mark] « Rejoindre l'équipe .mark » (U2 ter) : prénom, nom, mot de passe de 12 caractères au moins. */
export function PageInvitation({ jeton }: { jeton: string }) {
    const { t } = useLangue();
    const [invitation, setInvitation] = useState<{ email: string; role_nom: string } | null>(null);
    const [etat, setEtat] = useState<"lecture" | "ouverte" | "refusee">(jeton ? "lecture" : "refusee");
    const [prenom, setPrenom] = useState("");
    const [nom, setNom] = useState("");
    const [motDePasse, setMotDePasse] = useState("");
    const [confirmation, setConfirmation] = useState("");
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!jeton) return;
        lireUneInvitationApiV1AuthInvitationJetonGet({ path: { jeton } })
            .then((res) => {
                if (res.error || !res.data) setEtat("refusee");
                else {
                    setInvitation(res.data);
                    setEtat("ouverte");
                }
            })
            .catch(() => setEtat("refusee"));
    }, [jeton]);

    const tropCourt = motDePasse.length > 0 && motDePasse.length < MOT_DE_PASSE_MIN;
    const different = confirmation.length > 0 && confirmation !== motDePasse;

    const envoyer = async (e: React.FormEvent) => {
        e.preventDefault();
        if (motDePasse.length < MOT_DE_PASSE_MIN || motDePasse !== confirmation) return;
        setEnCours(true);
        try {
            const res = await accepterUneInvitationApiV1AuthInvitationJetonAccepterPost({
                path: { jeton },
                body: { prenom, nom, mot_de_passe: motDePasse },
            });
            if (res.error || !res.data) {
                toast.error(detailFromError(res.error, t({ en: "The account could not be created", fr: "Le compte n'a pas pu être créé" })));
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

    if (etat === "refusee") {
        return (
            <CadreAcces
                titre={t({ en: "Invitation no longer valid", fr: "Invitation périmée" })}
                sousTitre={t({
                    en: "This link was already used, has expired (48 hours) or is unknown. Ask for a new invitation.",
                    fr: "Ce lien a déjà servi, a expiré (48 heures) ou n'existe pas. Demandez une nouvelle invitation.",
                })}
            >
                <a href="/connexion" className="block cursor-pointer text-center text-sm text-primary hover:font-medium">
                    {t({ en: "Go to sign-in", fr: "Aller à la connexion" })}
                </a>
            </CadreAcces>
        );
    }

    return (
        <CadreAcces
            titre={t({ en: "Join the .mark team", fr: "Rejoindre l'équipe .mark" })}
            sousTitre={invitation ? `${invitation.email} · ${invitation.role_nom}` : undefined}
        >
            <form onSubmit={envoyer} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                        <Label htmlFor="prenom">{t({ en: "First name", fr: "Prénom" })}</Label>
                        <Input id="prenom" autoComplete="given-name" value={prenom} onChange={(e) => setPrenom(e.target.value)} required />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="nom">{t({ en: "Last name", fr: "Nom" })}</Label>
                        <Input id="nom" autoComplete="family-name" value={nom} onChange={(e) => setNom(e.target.value)} required />
                    </div>
                </div>
                <div className="space-y-2">
                    <Label htmlFor="mot-de-passe">{t({ en: "Password", fr: "Mot de passe" })}</Label>
                    <Input
                        id="mot-de-passe"
                        type="password"
                        autoComplete="new-password"
                        value={motDePasse}
                        onChange={(e) => setMotDePasse(e.target.value)}
                        required
                        minLength={MOT_DE_PASSE_MIN}
                    />
                    {tropCourt && <p className="text-xs text-destructive">{t({ en: "12 characters at least", fr: "12 caractères au moins" })}</p>}
                </div>
                <div className="space-y-2">
                    <Label htmlFor="confirmation">{t({ en: "Confirm the password", fr: "Confirmer le mot de passe" })}</Label>
                    <Input
                        id="confirmation"
                        type="password"
                        autoComplete="new-password"
                        value={confirmation}
                        onChange={(e) => setConfirmation(e.target.value)}
                        required
                    />
                    {different && (
                        <p className="text-xs text-destructive">{t({ en: "The passwords do not match", fr: "Les mots de passe ne correspondent pas" })}</p>
                    )}
                </div>
                <Button
                    type="submit"
                    className="w-full cursor-pointer"
                    disabled={enCours || etat === "lecture" || motDePasse.length < MOT_DE_PASSE_MIN || motDePasse !== confirmation}
                >
                    {enCours ? t({ en: "Creating...", fr: "Création..." }) : t({ en: "Create my account", fr: "Créer mon compte" })}
                </Button>
            </form>
        </CadreAcces>
    );
}
