"use client";

import { Plus } from "lucide-react";
import Link from "next/link";

import { useLangue } from "@/components/mark/langue/langue";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { Button } from "@/components/ui/button";

import { useAdressesDuBuilder } from "./adresses";
import { ListeDesFils } from "./ListeDesFils";

/** Le Chat : l'historique des conversations du builder (maquette `app/labo/builder`). « Nouveau chat » mène à l'accueil du builder. */
export default function PageHistorique() {
    const { t } = useLangue();
    const adresses = useAdressesDuBuilder();
    return (
        <PageStudio>
            <TitrePage
                titre={t({ en: "Chat", fr: "Chat" })}
                info={t({
                    en: "Every chat is tied to an agent; state, cost, context, Stop and Resume are in the chat.",
                    fr: "Chaque chat est lié à un agent ; état, coût, contexte, Arrêter et Reprendre sont dans le chat.",
                })}
                action={
                    <Button asChild>
                        <Link href={adresses.client ? adresses.liste.replace(/\/chat$/, "/builder") : "/labo"}>
                            <Plus className="size-4" aria-hidden /> {t({ en: "New chat", fr: "Nouveau chat" })}
                        </Link>
                    </Button>
                }
            />
            <div>
                <ListeDesFils />
            </div>
        </PageStudio>
    );
}
