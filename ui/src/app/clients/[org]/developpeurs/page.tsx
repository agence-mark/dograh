// [.mark] K1 : Développeurs est une section des Réglages de l'organisation.
import { redirect } from "next/navigation";

export default async function Page({ params }: { params: Promise<{ org: string }> }) {
    const { org } = await params;
    redirect(`/clients/${org}/reglages?section=developpeurs`);
}
