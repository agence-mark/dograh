"""[.mark] The after-call, inside the fork (chantier l-agent-travaille, L4, A1 to A10).

At the end of a call whose agent switched it on (``workflow_configurations.apres_appel``,
off by default, X2), Dograh's own job queue (arq) runs a chain of steps, each one a job
of its own with spaced retries (A10):

    ecriture   the call, its contact and its request in the client's database
               (``mark.recevoir_appel``, A2)
    synthese   a summary by a smaller Mistral model, on the client's key (A3)
    mail       one mail per request to the people of its routing (A4)
    <module>   each module the agent uses (custom webhook A7; SMS L6; connectors L5)

A step that fails never blocks the next ones; a final failure is shown in red in the
section « After the call » of the run window (A9) and mailed to the notification
addresses (A5). The night task purges table by table and refreshes the counters (A8);
the recap mail leaves at the hours set (A4).

- ``reglages``      the organization's and the agent's settings, keys by reference
- ``envoi``         what is written for a call, built from the run
- ``synthese``      the summary
- ``mail``          the mail server
- ``notification``  the notification addresses
- ``modules``       the modules (registry: L5 and L6 add theirs)
- ``chaine``        the chain, its steps, its retries, their record on the run
- ``taches``        the recap and the night task
"""
