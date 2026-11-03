"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    accepterUneInvitationApiV1AuthInvitationJetonAccepterPost,
    lireUneInvitationApiV1AuthInvitationJetonGet,
} from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { CadreAcces, ChampAcces, PiedAcces } from "@/components/mark/studio/cadre-acces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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
                notifier.echec({ fr: "Compte non créé. L'invitation a peut-être expiré.", en: "Account not created. The invitation may have expired." }, { erreur: res.error });
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

    if (etat === "refusee") {
        return (
            <CadreAcces
                titre={t({ en: "Invitation no longer valid", fr: "Invitation périmée" })}
                sousTitre={t({
                    en: "This link was already used, has expired (48 hours) or is unknown. Ask for a new invitation.",
                    fr: "Ce lien a déjà servi, a expiré (48 heures) ou n'existe pas. Demandez une nouvelle invitation.",
                })}
            >
                <Link href="/connexion" className="block text-sm font-medium text-foreground hover:font-semibold">
                    {t({ en: "Go to sign-in", fr: "Aller à la connexion" })}
                </Link>
            </CadreAcces>
        );
    }

    return (
        <CadreAcces
            titre={t({ en: "Join the .mark team", fr: "Rejoindre l'équipe .mark" })}
            sousTitre={
                invitation && (
                    <>
                        {t({ en: "You are invited as", fr: "Vous êtes invité comme" })}{" "}
                        <span className="font-medium text-foreground">{invitation.role_nom}</span>.
                    </>
                )
            }
        >
            <form onSubmit={envoyer} className="space-y-4">
                <ChampAcces libelle={t({ en: "Email", fr: "E-mail" })}>
                    <Input value={invitation?.email ?? ""} disabled readOnly />
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
                        minLength={MOT_DE_PASSE_MIN}
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
                <Button
                    type="submit"
                    className="w-full"
                    disabled={enCours || etat === "lecture" || motDePasse.length < MOT_DE_PASSE_MIN || motDePasse !== confirmation}
                >
                    {enCours ? t({ en: "Creating...", fr: "Création..." }) : t({ en: "Create my account", fr: "Créer mon compte" })}
                </Button>
            </form>
            <PiedAcces>
                {t({
                    en: "Your account joins the Lab and the clients your role opens. You will use their keys without ever seeing them.",
                    fr: "Votre compte rejoint le Labo et les clients que votre rôle ouvre. Vous utiliserez leurs clés sans jamais les voir.",
                })}
            </PiedAcces>
        </CadreAcces>
    );
}
