"use client";

/** [.mark] Qui est connecté : nom, rôle, e-mail (`GET /equipe-mark/moi`), lu une fois par chargement de la page. */
import { useEffect, useState } from "react";

import { monProfilApiV1EquipeMarkMoiGet } from "@/client/sdk.gen";
import type { ProfilResponse } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

export function useMoi(): ProfilResponse | null {
    const { user, loading } = useAuth();
    const [moi, setMoi] = useState<ProfilResponse | null>(null);
    useEffect(() => {
        if (loading || !user) return;
        let vivant = true;
        monProfilApiV1EquipeMarkMoiGet().then((res) => {
            if (vivant && res.data) setMoi(res.data);
        });
        return () => {
            vivant = false;
        };
    }, [loading, user]);
    return moi;
}
