import { describe, expect, it } from 'vitest';

import { formatCalendarDate, formatDate, formatDateRelative, formatDateTime } from '@/lib/dateTime';

describe('dateTime', () => {
    it('formats an instant in the requested timezone', () => {
        expect(formatDateTime('2026-07-23T10:00:00Z', 'Asia/Kolkata')).toBe(
            'Jul 23, 2026, 03:30 PM',
        );
    });

    it('formats the date represented in the requested timezone', () => {
        expect(formatDate('2026-07-23T01:00:00Z', 'America/Los_Angeles')).toBe(
            'Jul 22, 2026',
        );
    });

    it('does not shift calendar-only dates across timezones', () => {
        expect(formatCalendarDate('2026-07-23')).toBe('Jul 23, 2026');
    });
});

describe('formatDateRelative (V4)', () => {
    const maintenant = new Date('2026-11-04T12:00:00Z');
    it("dit « aujourd'hui » et « hier » avec l'heure, sinon jour et mois", () => {
        expect(formatDateRelative('2026-11-04T10:03:00Z', 'fr', 'UTC', maintenant)).toBe("aujourd'hui 10:03");
        expect(formatDateRelative('2026-11-03T17:22:00Z', 'fr', 'UTC', maintenant)).toBe('hier 17:22');
        expect(formatDateRelative('2026-10-29T08:05:00Z', 'fr', 'UTC', maintenant)).toBe('29/10 08:05');
    });
    it('suit la langue : today, yesterday, mois/jour', () => {
        expect(formatDateRelative('2026-11-04T10:03:00Z', 'en', 'UTC', maintenant)).toBe('today 10:03');
        expect(formatDateRelative('2026-11-03T17:22:00Z', 'en', 'UTC', maintenant)).toBe('yesterday 17:22');
        expect(formatDateRelative('2026-10-29T08:05:00Z', 'en', 'UTC', maintenant)).toBe('Oct 29 08:05');
    });
    it('compte le jour dans le fuseau demandé, pas en UTC', () => {
        // 23:30 UTC le 3 est déjà le 4 à Paris (UTC+1) : « aujourd'hui » pour un « maintenant » du 4 à Paris.
        expect(formatDateRelative('2026-11-03T23:30:00Z', 'fr', 'Europe/Paris', maintenant)).toBe("aujourd'hui 00:30");
    });
});
