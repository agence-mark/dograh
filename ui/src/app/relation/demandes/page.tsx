"use client";

// [.mark] U3 septies (E93) : l'ancienne adresse des demandes renvoie aux messages, où chaque demande est un fil.
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function Page() {
    const router = useRouter();
    useEffect(() => router.replace("/relation/messages"), [router]);
    return null;
}
