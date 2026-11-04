export function getLocalTimezone() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

type DateInput = Date | number | string;

export function formatDateTime(value: DateInput, timezone?: string | null, langue: 'fr' | 'en' = 'en') {
    // [.mark] K2b : une date lue en français se dit en français (« 3 nov. 2026, 13:59 »), à 24 heures.
    return new Date(value).toLocaleString(langue === 'fr' ? 'fr-FR' : 'en-US', {
        timeZone: timezone || getLocalTimezone(),
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: langue !== 'fr',
    });
}

export function formatDate(value: DateInput, timezone?: string | null, langue: 'fr' | 'en' = 'en') {
    // [.mark] K8 : une date lue en français se dit en français (« 14 oct. 2026 »).
    return new Date(value).toLocaleDateString(langue === 'fr' ? 'fr-FR' : 'en-US', {
        timeZone: timezone || getLocalTimezone(),
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

export function formatCalendarDate(value: string) {
    const calendarDate = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!calendarDate) {
        return formatDate(value, 'UTC');
    }

    const [, year, month, day] = calendarDate;
    return formatDate(
        Date.UTC(Number(year), Number(month) - 1, Number(day)),
        'UTC',
    );
}

export function formatLocalDateTime(value: Date) {
    return `${value.toLocaleDateString()} ${value.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
    })}`;
}

/**
 * [.mark] V4 : la date d'une ligne de tableau, comme la maquette : « aujourd'hui 11:03 », « hier 17:22 », sinon « 02/11 09:40 »
 * (jour/mois en français, mois/jour en anglais), à 24 heures. Le jour se compte dans le fuseau demandé (ou celui de la personne).
 */
export function formatDateRelative(value: DateInput, langue: 'fr' | 'en' = 'en', timezone?: string | null, maintenant: Date = new Date()) {
    const zone = timezone || getLocalTimezone();
    const jour = (d: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
    const date = new Date(value);
    const heure = new Intl.DateTimeFormat(langue === 'fr' ? 'fr-FR' : 'en-GB', { timeZone: zone, hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
    const aujourdhui = jour(maintenant);
    const hier = jour(new Date(maintenant.getTime() - 24 * 3600 * 1000));
    const celuiLa = jour(date);
    if (celuiLa === aujourdhui) return `${langue === 'fr' ? "aujourd'hui" : 'today'} ${heure}`;
    if (celuiLa === hier) return `${langue === 'fr' ? 'hier' : 'yesterday'} ${heure}`;
    const [, mois, j] = celuiLa.split('-');
    return `${langue === 'fr' ? `${j}/${mois}` : `${mois}/${j}`} ${heure}`;
}
