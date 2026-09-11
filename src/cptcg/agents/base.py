"""The agent interface.

An agent answers each ``Choice`` with an index into ``choice.options``. It receives the full
GameState for now; the heuristic agent is written to read only public information and its own
hand (a redacting view and a paranoid check come with the search agent).
"""

from __future__ import annotations

from cptcg.core.actions import Choice
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState


class Agent:
    name = "agent"

    #: True on an agent that samples hidden information (``core.view.determinize``) rather than
    #: reading the true state. Only such an agent can be asked to cheat; see ``CHEAT_PREFIX``.
    uses_determinization = False

    #: When True the agent searches the *true* state instead of a sampled world. Set only by
    #: ``make_agent("cheat:NAME")``, and only for measuring the cost of hidden information.
    cheating = False

    def __init__(self, seed: int = 0) -> None:
        self.rng = Pcg32(seed, seq=7)
        self.me = -1

    def new_game(self, seed: int, me: int) -> None:
        self.rng = Pcg32(seed ^ 0xA6E17, seq=11 + me)
        self.me = me

    def act(self, s: GameState, choice: Choice) -> int:  # pragma: no cover - interface
        raise NotImplementedError


AGENTS: dict[str, type[Agent]] = {}


def register(cls: type[Agent]) -> type[Agent]:
    AGENTS[cls.name] = cls
    return cls


#: Name prefix that builds the *cheating* variant of an agent: same budget, same evaluation, same
#: policy, but it searches the true state instead of a world sampled from what its seat may
#: legitimately know. It exists so that ``tools/arena.py exploit`` can measure the cost of hidden
#: information, and it travels as part of the agent *name* so a worker process can build it too.
CHEAT_PREFIX = "cheat:"

#: Separator that points an agent at a *particular* file of fitted weights:
#: ``"ismcts@out/learn/gen-003/weights.json"``. Like ``cheat:`` it travels inside the agent name,
#: which is what matters — the arena builds its agents inside worker processes, so a generational
#: gate can only pit two sets of weights against each other if "which weights" is part of the name
#: rather than something the parent configured. ``make_agent`` sets it as an *instance* attribute
#: over the class default, and ``learn.model.load_weights`` caches per path, so a worker playing
#: gen 7 against gen 6 holds exactly two models however many games it plays.
WEIGHTS_SEP = "@"


def make_agent(name: str, seed: int = 0) -> Agent:
    import cptcg.agents.random_agent  # noqa: F401
    import cptcg.agents.heuristic  # noqa: F401
    import cptcg.agents.neural  # noqa: F401
    import cptcg.agents.search.ismcts  # noqa: F401
    cheat = name.startswith(CHEAT_PREFIX)
    if cheat:
        name = name[len(CHEAT_PREFIX):]
    weights = ""
    if WEIGHTS_SEP in name:
        name, _, weights = name.partition(WEIGHTS_SEP)
    try:
        agent = AGENTS[name](seed)
    except KeyError:
        raise KeyError(f"unknown agent {name!r}; known: {sorted(AGENTS)}") from None
    if cheat:
        if not agent.uses_determinization:
            raise ValueError(f"agent {name!r} does not sample hidden information, so there is "
                             f"nothing for {CHEAT_PREFIX!r} to take away from it")
        agent.cheating = True
    if weights:
        if not hasattr(type(agent), "weights_path"):
            raise ValueError(f"agent {name!r} has no weights to point somewhere else; "
                             f"{WEIGHTS_SEP!r} is for the fitted agents")
        agent.weights_path = weights
    return agent
