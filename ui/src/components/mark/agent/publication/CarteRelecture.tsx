"use client";

/**
 * [.mark] Partie 3, sous-lot 3 (SE-12 / D-4) : « Demander au builder de relire » dans la fenêtre Publier. Une demande au builder
 * (une conversation du Chat, lancée sur l'agent), et sa réponse en carte sous le tableau des changements. Le builder ne publie
 * jamais (action interdite côté serveur) : la carte le dit, et la publication reste un clic de la personne.
 */
import { ExternalLink, Sparkles } from "lucide-react";
import Link from "next/link";

import { useFil } from "@/components/builder/chat/useFil";
import { Markdown } from "@/components/builder/chat/Markdown";
import { useAdressesDuBuilder } from "@/components/builder/chat/adresses";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";

const TEXTES = {
    titre: { en: "The builder's review", fr: "La relecture du builder" },
    enCours: { en: "reading", fr: "relecture en cours" },
    fini: { en: "done", fr: "terminée" },
    arrete: { en: "stopped", fr: "arrêtée" },
    rien: { en: "The builder is reading the changes...", fr: "Le builder relit les changements..." },
    sansTexte: { en: "The builder has no remark to make.", fr: "Le builder n'a pas de remarque à faire." },
    jamais: {
        en: "A review never publishes anything: you publish with the button below.",
        fr: "Une relecture ne publie jamais rien : vous publiez avec le bouton en bas de la fenêtre.",
    },
    ouvrir: { en: "Open in the Chat", fr: "Ouvrir dans le Chat" },
} satisfies Record<string, Texte>;

/** La demande écrite au builder, dans la langue de l'écran. */
export const DEMANDE_DE_RELECTURE: Texte = {
    en: "Review the changes of this agent's draft before it is published: compare the draft with the published version and tell me, step by step and in a few words, what looks risky or inconsistent. Change nothing and publish nothing.",
    fr: "Relis les changements du brouillon de cet agent avant sa publication : compare le brouillon à la version publiée et dis-moi, étape par étape et en peu de mots, ce qui te paraît risqué ou incohérent. Ne modifie rien et ne publie rien.",
};

export function CarteRelecture({ filId }: { filId: number }) {
    const { t } = useLangue();
    const adresses = useAdressesDuBuilder();
    const { fil, lignes, erreur, enCours } = useFil(filId);
    const texte = lignes
        .flatMap((l) => (l.genre === "texte" ? [l.texte] : []))
        .join("\n\n")
        .trim();
    const fini = fil !== null && !enCours;
    return (
        <section className="mt-4 rounded-lg border p-4" data-carte="relecture-du-builder" aria-live="polite">
            <div className="flex items-center justify-between gap-3">
                <p className="flex items-center gap-1.5 text-sm font-medium">
                    <Sparkles className="size-4" /> {t(TEXTES.titre)}
                </p>
                {fil && <PointEtat etat={enCours ? "attente" : fil.etat === "arrete" ? "fini" : "publie"}>{enCours ? t(TEXTES.enCours) : fil.etat === "arrete" ? t(TEXTES.arrete) : t(TEXTES.fini)}</PointEtat>}
            </div>
            <div className="mt-3 text-sm">
                {erreur ? (
                    <EtatVide cas="erreur" />
                ) : texte ? (
                    <Markdown texte={texte} />
                ) : fini ? (
                    <p className="text-muted-foreground">{t(TEXTES.sansTexte)}</p>
                ) : (
                    <p className="text-muted-foreground">{t(TEXTES.rien)}</p>
                )}
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span>{t(TEXTES.jamais)}</span>
                <Button variant="ghost" size="sm" asChild>
                    <Link href={adresses.fil(filId)}>
                        <ExternalLink className="size-3.5" /> {t(TEXTES.ouvrir)}
                    </Link>
                </Button>
            </div>
        </section>
    );
}
