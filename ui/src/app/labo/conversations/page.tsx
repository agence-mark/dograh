"use client";

// [.mark] U1 : cette adresse monte l'écran actuel dans le nouveau cadre (les écrans refondus le remplaceront).
// Partie 3, sous-lot 10 (SE-3) : dans le Labo, « Tous les clients » (colonne Client, lecture seule) devant les appels du Labo.
import UsagePage from "@/app/usage/page";
import { ConversationsTousClients } from "@/components/mark/equipe/VuesTousClients";
import { useLangue } from "@/components/mark/langue/langue";
import { useOngletDeLAdresse } from "@/components/mark/studio/onglets-page";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";

export default function ConversationsDuLabo() {
    const { t } = useLangue();
    const { actif, choisir } = useOngletDeLAdresse(["clients", "labo"], "clients");
    const onglets = [
        { id: "clients", titre: t({ en: "All clients", fr: "Tous les clients" }) },
        { id: "labo", titre: "Labo" },
    ];
    const barre = (
        <div role="tablist" className="flex items-center gap-1 border-b">
            {onglets.map((o) => (
                <button
                    key={o.id}
                    type="button"
                    role="tab"
                    aria-selected={actif === o.id}
                    onClick={() => choisir(o.id)}
                    className={`-mb-px cursor-pointer border-b-2 px-3 py-2.5 text-sm ${actif === o.id ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:font-medium hover:text-foreground"}`}
                >
                    {o.titre}
                </button>
            ))}
        </div>
    );
    if (actif === "labo") {
        return (
            <>
                <div className="mx-auto w-full max-w-6xl px-4 pt-8 sm:px-8">{barre}</div>
                <UsagePage />
            </>
        );
    }
    return (
        <PageStudio>
            <TitrePage titre={t({ en: "Conversations", fr: "Conversations" })} />
            {barre}
            <ConversationsTousClients />
        </PageStudio>
    );
}
