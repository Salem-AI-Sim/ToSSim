"""runner.match_runner – drives one Town-of-Salem match with LLM agents.

Outline workflow (simplified):
1. GameConfiguration builds the 15-role lobby.
2. InferenceEngine spun up externally and passed in.
3. For each player: create AgentContext containing
     • player_id / name
     • base_model   (from a YAML config or default)
     • InferenceClient bound to that model's lane.
4. Advance phases:
     – build phase prompt via prompt_builder.build_chat_messages()
     – call client.chat()
     – detect tool tags, run tool_router, inject observation, loop until a
       public action ( <speak>/<vote>/<wait> ) is returned.
5. Feed the action back to Simulation.game.

This file provides only a **minimal skeleton** so the rest of the system can
compile.  Real error-handling, logging, and timeouts should be added later.
"""

from __future__ import annotations

from typing import Dict, List, Any
import re

from Simulation.game import Game
from Simulation.config import GameConfiguration
from Simulation.player import Player
from Simulation.roles import Role

from inference.engine import InferenceEngine
from inference.client import InferenceClient
from inference.templates import prompt_builder as pb
from Simulation import interaction_handler as ih

from inference.tool_router import apply_first_tool_call

from runner.lobby_loader import load_lobby, LobbyConfig

from Simulation.token_budget import TokenBudgetManager

# Custom chat role used by the simulator to indicate an *environment* observation.
# Before sending to the OpenAI-compatible HTTP API we remap it back to "user"
# because the reference schema only recognises system/user/assistant/tool.
OBSERVATION_ROLE = "observation"

# ------------------------------------------------------------
# Model-specific chat-template quirks
# ------------------------------------------------------------

def _model_family(model_name: str) -> str | None:
    """Return a coarse family identifier (gemma/qwen/llama/mistral) or *None*."""
    name = model_name.lower()
    if "gemma" in name:
        return "gemma"
    if "qwen" in name:
        return "qwen"
    if "llama" in name or "llemma" in name:  # typo safeguard
        return "llama"
    if "mistral" in name:
        return "mistral"
    return None

class AgentContext:
    def __init__(self, player: Player, model_name: str, lane_url: str):
        self.player = player
        self.model = model_name
        self.client = InferenceClient(lane_url, model_name)
        self.chat_history: List[Dict[str, str]] = []
        self.pending_observation: str | None = None


class MatchRunner:
    def __init__(self, engine: InferenceEngine, lobby: str | LobbyConfig | None = None):
        """Create a match runner.

        Parameters
        ----------
        engine : InferenceEngine
        lobby  : Either a path to the YAML file, a pre-parsed `LobbyConfig`, or
                 *None* (in which case `configs/lobby_default.yaml` is used).
        """

        self.engine = engine

        if isinstance(lobby, LobbyConfig):
            self.lobby = lobby
        else:
            self.lobby = load_lobby(lobby)  # path or None

        self.game_cfg = GameConfiguration(game_mode=self.lobby.game.mode, coven=self.lobby.game.coven)

        # Build players with dummy roles for now – real roles assigned by Game
        self.players: List[Player] = [Player(a.id, Role()) for a in self.lobby.agents]
        self.game = Game(self.game_cfg, self.players)

        # Register agents with the engine and create contexts
        self.agents: Dict[str, AgentContext] = {}
        for spec in self.lobby.agents:
            lane = self.engine.register_agent(spec.id, spec.model)
            ctx = AgentContext(self._player_by_name(spec.id), spec.model, lane[1])
            self.agents[spec.id] = ctx

        # Token budget manager
        self.budget = TokenBudgetManager.from_yaml("configs/environment_limits.yaml")

        # Interaction handler (game moves)
        self.handler = ih.InteractionHandler(self.game)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _player_by_name(self, name: str) -> Player:
        for p in self.players:
            if p.name == name:
                return p
        raise KeyError(name)

    # ------------------------------------------------------------------

    def run(self):
        """Blocking – plays through day/night cycles until game ends."""
        while not self.game.game_is_over():
            self._process_day_phase()
            if self.game.game_is_over():
                break
            self._process_night_phase()

        # Clean-up
        for aid in self.agents:
            self.engine.release_agent(aid)

    # ------------------------------------------------------------------
    # Phase drivers (very simplified)
    # ------------------------------------------------------------------

    # Helper ------------------------------------------------------------

    def _render_public_state(self) -> Dict[str, Any]:
        """Return a **minimal** serialisation of the public game state.

        This will be expanded later to include vote tallies, chat log, etc.
        """
        # Phase label mapping
        phase_label = "discussion"
        if hasattr(self.game, "phase"):
            phase_enum = getattr(self.game, "phase")
            phase_label = phase_enum.name.lower()

        # Build graveyard list
        graveyard = [{"name": p.name, "role": p.role.name.value} for p in getattr(self.game, "graveyard", [])]

        # Vote board appears only during nomination / voting / judgement
        vote_board: list[tuple[str, int]] = []
        votes_needed = None
        if phase_label in {"day", "voting"} and hasattr(self.game, "day_phase_manager") and self.game.day_phase_manager:
            dpm = self.game.day_phase_manager
            votes_needed = getattr(dpm, "nomination_threshold", None)
            vote_board = [(t.name, len(v)) for t, v in dpm.nominations.items() if v]

        # Chat tail placeholder – in future gather from ChatManager
        chat_tail: list[str] = []

        return {
            "day": getattr(self.game, "day", 0),
            "phase": phase_label,
            "graveyard": graveyard,
            "votes_needed": votes_needed,
            "vote_board": vote_board,
            "chat_tail": chat_tail,
        }

    def _send_agent_turn(self, ctx: AgentContext, public_state: Dict[str, Any]) -> None:
        """Iteratively chat with the agent until a terminal public action is produced."""

        TERMINAL_TAGS = ("<speak>", "<whisper", "<vote>", "<wait>")

        loop_guard = 0
        while True:
            loop_guard += 1
            if loop_guard > 6:
                print(f"[Warn] Agent {ctx.player.name} exceeded 6 inner loops, forcing wait.")
                break

            msgs = pb.build_chat_messages(
                role=ctx.player.role,
                public_state=public_state,
                observation=ctx.pending_observation,
                history=ctx.chat_history,
                observation_role=OBSERVATION_ROLE,
            )

            # Remap roles for backend compatibility
            family = _model_family(ctx.model)
            msgs_out = []
            for m in msgs:
                role = "user" if (m["role"] in {OBSERVATION_ROLE, "system"} and family == "gemma") else m["role"]
                if role not in {"system", "user", "assistant"}:
                    role = "user"
                msgs_out.append({"role": role, "content": m["content"]})

            resp = ctx.client.chat(msgs_out)
            assistant_content = resp["choices"][0]["message"]["content"]

            # Rough token count – whitespace split
            token_estimate = len(assistant_content.split())
            channel = "public"  # future refinement
            self.budget.consume(channel, token_estimate)

            patched_text, observation = apply_first_tool_call(assistant_content, game=self.game, player=ctx.player)
            ctx.chat_history.append({"role": "assistant", "content": patched_text})

            # Queue observation for next turn and continue loop
            if observation is not None:
                ctx.pending_observation = observation
                continue
            ctx.pending_observation = None

            # Check if terminal action present
            if any(tag in patched_text for tag in TERMINAL_TAGS):
                # Execute side effects
                self._apply_public_action(ctx.player, patched_text)
                break

        # After agent completes turn, log budget exhaustion
        if self.budget.phase_exhausted():
            print(f"[Budget] Phase '{self.budget._current_phase}' exhausted – advancing (logic TBD).")

    def _process_night_phase(self):
        self.game.advance_to_night()
        public_state = self._render_public_state()
        for ctx in self.agents.values():
            self._send_agent_turn(ctx, public_state)
        self.game.process_night_submissions()
        self.game.advance_to_day()

    def _process_day_phase(self):
        self.game.advance_to_day()

        public_state = self._render_public_state()
        for ctx in self.agents.values():
            self._send_agent_turn(ctx, public_state)

    # ------------------------------------------------------------------
    # Action routing helpers
    # ------------------------------------------------------------------

    _SPEAK_RE = re.compile(r"<speak>(.*?)</speak>", re.DOTALL | re.IGNORECASE)
    _WHISPER_RE = re.compile(r"<whisper\s+target=\"(.*?)\">(.*?)</whisper>", re.DOTALL | re.IGNORECASE)

    def _apply_public_action(self, player: Player, assistant_text: str):
        """Detect <speak>, <whisper>, <vote>, <nominate>, <wait> and apply to game."""

        # Speak
        m = self._SPEAK_RE.search(assistant_text)
        if m:
            text = m.group(1).strip()
            res = self.game.speak(player, text)
            print(res)

        # Whisper
        m = self._WHISPER_RE.search(assistant_text)
        if m:
            target_name, text = m.group(1).strip(), m.group(2).strip()
            target = self.game.get_player_by_name(target_name)
            if target:
                res = self.game.whisper(player, target, text)
                print(res)

        # Other tags – pass entire string to interaction handler to parse
        self.handler.parse_and_execute(player, assistant_text) 