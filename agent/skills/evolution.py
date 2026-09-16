"""Post-battle evolution scene: let it run with A, never cancel with B.
See agent.lm_studio_client.AgentClient (which inherits EvolutionMixin)."""


class EvolutionMixin:


    def _in_evolution_scene(self) -> bool:
        """True while the post-battle evolution scene is on screen (its own callback).
        A normal battle end goes straight to the overworld, so this is unambiguous."""
        from game.constants import Addr
        return self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_EVOLUTION

    def _finish_evolution(self) -> bool:
        """Let an active evolution scene run to completion by advancing with A. NEVER
        press B here — B cancels the evolution ("Huh? … stopped evolving!"), which is
        why a levelled-up lead never evolved (the scene flickers into IN_MENU and the
        agent dismissed it with B). Returns True if it drove a scene. (#… allow-evolution)"""
        if not self._in_evolution_scene():
            return False
        for _ in range(200):
            if not self._in_evolution_scene():
                break
            self.mgba.tap("A")
            self.mgba.tick(4)
        return True

    def _settle_evolution(self) -> bool:
        """Call right after a battle ends. The evolution scene launches a few frames
        AFTER the battle's return-to-field, so a single _in_evolution_scene() check can
        miss it; wait briefly for it to appear, then complete it (A, never B). Exits
        immediately once we're back on the field (the common no-evolution case). Returns
        True if it completed an evolution. Used by every deterministic battle-end path so
        the model never sees the flickering scene and cancels it with B."""
        from game.state import GameContext
        for _ in range(20):
            if self._finish_evolution():
                return True
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return False
            self.mgba.tick(2)
        return False
