"""[.mark] The appointment planner (chantier l-agent-collegue, L5, P1 to P10).

- ``souhaits``   the caller's wish read by the code, from a closed list (P4, repli 6)
- ``feries``     the public holidays, metropolitan France or Alsace-Moselle (P10)
- ``trajets``    the ONE function that counts a journey (P5), and the address's position (repli 7)
- ``calcul``     the slots: agendas, length, margins, journeys, zone, holidays, distribution (P7)
- ``action``     the two actions of the agent, ``proposer_creneaux`` and ``poser_rendez_vous`` (P1),
                 the fallback (P8), the useful result only (P9)

Everything off by default (X2): an agent without the planner's tools, or an organization with no
calendar software chosen, is untouched.
"""
