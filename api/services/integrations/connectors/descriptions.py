"""[.mark] Partie 3, lot 14 (J-1, SE-19) : la description d'un logiciel du catalogue, dite en une phrase, en français et en anglais.

Elle s'affiche dans la fenêtre du logiciel (« À propos »). Une phrase sur ce que le logiciel sert à faire, jamais un
chiffre, un prix ni une promesse. Un test échoue si un connecteur du catalogue n'en a pas.
"""

from __future__ import annotations

# nom du connecteur -> (français, anglais)
DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "acuity": ("Prise de rendez-vous en ligne : horaires libres et réservations.", "Online booking: free slots and appointments."),
    "airtable": ("Bases de données en tableaux : chercher et créer des lignes.", "Spreadsheet-style databases: search and create rows."),
    "apimo": ("Logiciel d'agence immobilière : biens et contacts.", "Estate-agency software: properties and contacts."),
    "calendly": ("Prise de rendez-vous en ligne : disponibilités et invitations.", "Online booking: availability and invitations."),
    "cosium": ("Logiciel d'opticien : clients et rendez-vous.", "Optician software: customers and appointments."),
    "crisp": ("Messagerie de support : conversations et messages.", "Support messaging: conversations and messages."),
    "doctolib": ("Agenda de santé : créneaux et rendez-vous des patients.", "Health calendar: slots and patient appointments."),
    "dossier": ("Notre dossier interne : la fiche de l'appelant, tenue dans le fork.", "Our internal record: the caller's file, kept in the fork."),
    "equipe": ("Notre annuaire interne : joindre ou transférer vers une personne de l'équipe.", "Our internal directory: reach or transfer to a team member."),
    "folk": ("CRM léger : chercher et créer des contacts, ajouter des notes.", "Light CRM: search and create contacts, add notes."),
    "freshdesk": ("Support client : créer et suivre des tickets.", "Customer support: create and follow tickets."),
    "gmail": ("Messagerie Google : envoyer un courriel de confirmation.", "Google mail: send a confirmation email."),
    "google_agenda": ("Agenda Google : lire les horaires libres, créer un rendez-vous.", "Google Calendar: read free slots, create an appointment."),
    "google_sheets": ("Tableur Google : lire et ajouter des lignes.", "Google spreadsheet: read and append rows."),
    "hektor": ("Logiciel d'agence immobilière : biens, mandats et contacts.", "Estate-agency software: properties, mandates and contacts."),
    "hubspot": ("CRM : chercher et créer des contacts, des affaires et des notes.", "CRM: search and create contacts, deals and notes."),
    "nocrm": ("CRM de pistes commerciales : créer une piste, la commenter.", "Lead CRM: create a lead and comment on it."),
    "notion": ("Espace de notes et de bases : créer une page.", "Notes and databases workspace: create a page."),
    "outlook_agenda": ("Agenda Microsoft : lire les horaires libres, créer un rendez-vous.", "Microsoft calendar: read free slots, create an appointment."),
    "pennylane": ("Comptabilité et facturation : créer une facture.", "Accounting and invoicing: create an invoice."),
    "pipedrive": ("CRM de vente : chercher et créer des personnes et des notes.", "Sales CRM: search and create people and notes."),
    "planificateur": ("Notre planificateur interne : propose des créneaux à partir des horaires et des absences.", "Our internal planner: proposes slots from hours and absences."),
    "praxedo": ("Gestion d'interventions sur le terrain : planifier et suivre.", "Field-service management: plan and follow jobs."),
    "salesforce": ("CRM : chercher et créer des contacts et des opportunités.", "CRM: search and create contacts and opportunities."),
    "sellsy": ("CRM et facturation : contacts et opportunités.", "CRM and invoicing: contacts and opportunities."),
    "setmore": ("Prise de rendez-vous en ligne : services et réservations.", "Online booking: services and appointments."),
    "slack": ("Messagerie d'équipe : prévenir un canal.", "Team messaging: notify a channel."),
    "teamleader": ("CRM et gestion : contacts et affaires.", "CRM and management: contacts and deals."),
    "twilio_sms": ("Envoi de SMS : confirmation ou rappel à l'appelant.", "SMS sending: confirmation or reminder to the caller."),
    "vetstoria": ("Prise de rendez-vous vétérinaire en ligne.", "Online veterinary booking."),
    "whatsapp_business": ("Messages WhatsApp d'une entreprise : envoyer un message.", "Business WhatsApp messages: send a message."),
    "zendesk": ("Support client : créer et suivre des tickets.", "Customer support: create and follow tickets."),
}


def description_de(nom: str) -> tuple[str | None, str | None]:
    """``(français, anglais)`` du connecteur, ``(None, None)`` s'il n'en a pas (le test d'inventaire l'interdit)."""
    d = DESCRIPTIONS.get(nom)
    return (d[0], d[1]) if d else (None, None)
