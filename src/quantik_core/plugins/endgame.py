from ..game_utils import has_winning_line as bb_has_winning_line
from ..core import State


def has_winning_line(state: State) -> bool:
    return bb_has_winning_line(state.bb)
