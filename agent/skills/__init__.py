"""The deterministic gameplay-skill layer for AgentClient.

Each module defines a mixin class that AgentClient inherits (see
agent.lm_studio_client), so skill methods stay reachable as `client._use_move(...)`
while each skill family lives in its own file with its own state:

  nav        — walk_to / go_to / go_to_map / challenge_leader / travel battles
  overworld  — heal / shop / grind / pick_up_items
  battle     — use_move / flee / catch / switch / use_item / auto_fight
  movelearn  — the level-up move-learn driver
  evolution  — post-battle evolution scene handling
"""
