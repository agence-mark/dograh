"use client";

/**
 * [.mark] « Mon profil » à son adresse (`/profil`, K1) : la fenêtre de la maquette (`FenetreProfil`), ouverte au-dessus du
 * Labo. Le menu du compte, en bas de la barre latérale, ouvre la même fenêtre sans changer de page.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { ProfilResponse } from "@/client/types.gen";
import { FenetreProfil } from "@/components/mark/studio/fenetre-profil";
import { useMoi } from "@/components/mark/studio/moi";

export function PageProfil() {
    const router = useRouter();
    const moi = useMoi();
    const [lu, setLu] = useState<ProfilResponse | null>(null);
    return <FenetreProfil profil={lu ?? moi} ouverte fermer={() => router.push("/labo")} apres={setLu} />;
}
