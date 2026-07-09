"""Evaluation harness for the Pokémon LeafGreen agent.

Two tiers:
  • Tier 2 (end-to-end): `evals.runner` drives the real agent loop
    (main.run_episode) from a start state toward a goal, emitting an
    EpisodeResult scorecard. Run with `python -m evals`.
  • Tier 1 (deterministic skills): goal predicates + scenario definitions are
    pure/importable without the LLM or emulator, so they unit-test in CI; a
    ROM-gated skill test (tests/test_nav_scenarios.py) exercises the nav skills
    directly on a real save state.

Goals and scenarios live here (light imports, no openai/cffi) so they stay
CI-testable; only `evals.runner` pulls in the heavy agent stack.
"""
