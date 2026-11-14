"""Menu / prompt / dialogue skills (see game.menu.MenuDriver). Mixed into AgentClient."""
from game.menu import MenuDriver


class MenuMixin:

    @property
    def _menus(self) -> MenuDriver:
        d = getattr(self, "_menu_driver", None)
        if d is None:
            d = self._menu_driver = MenuDriver(self.mgba, self.reader)
        return d

    def _open_menu(self, name: str) -> str:
        return self._menus.open_menu(name)

    def _answer_prompt(self, answer: str) -> str:
        return self._menus.answer_prompt(answer)

    def _advance_dialog(self) -> str:
        from game.menu import forced_party_screen
        from game.state import GameContext
        # In a battle the "dialogue" is battle text: drive it to the next decision point
        # instead of refusing (the old reply — "a battle started" — pressed nothing).
        if (self.reader.detect_context() == GameContext.IN_BATTLE
                or forced_party_screen(self.mgba, self.reader)):
            return self._battle_settle()
        return self._menus.advance_dialog()

    def _close_menus(self) -> str:
        return self._menus.close_menus()
