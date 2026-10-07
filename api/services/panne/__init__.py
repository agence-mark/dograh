"""[.mark] The outage fallback (chantier l-agent-travaille, L7; plan panne-vers-magasin, PN1 to PN8).

- ``consigne``   the Twilio instructions (TwiML): hand-over, call-back promise, apology, the
                 instruction after the stream (PN5), the text of the TwiML Bin
- ``twilio``     the client's Twilio: update a live call, read its call log, write the
                 emergency address of a number (never called on a real number by a test)
- ``raccroche``  the hang-up strategy that leaves a handed-over call alone (C2)
- ``gardien``    the decision for ONE call: once, the state of the establishment at that
                 instant, the instruction, the record, the alert
- ``declencheurs`` what calls the guard: an error the call cannot survive, the model too slow
                 twice (PN2), the voice too slow (PN3)
- ``rattrapage`` the calls lost while our server was down (PN5), rebuilt from the call log
- ``routes``     the result of the hand-over (Twilio, signature checked) and the settings

Off by default (X2): an agent that does not switch it on is not touched.
"""
