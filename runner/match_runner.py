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
from dataclasses import asdict
import re

from Simulation.game import Game
from Simulation.config import GameConfiguration
from Simulation.player import Player
from Simulation.roles import Role, create_role_from_name
from Simulation.enums import Time
from Simulation.event_logger import GameLogger

from inference.engine import InferenceEngine
from inference.client import InferenceClient
from inference.templates import prompt_builder as pb
from Simulation import interaction_handler as ih

from inference.tool_router import apply_first_tool_call

from runner.lobby_loader import load_lobby, LobbyConfig, AgentSpec

from Simulation.token_budget import TokenBudgetManager
from Simulation.prompt_builder import build_complete_prompt

OBSERVATION_ROLE = "observation"


def _model_family(model_name: str) -> str | None:
    name = model_name.lower()
    if "gemma" in name:
        return "gemma"
    if "qwen" in name:
        return "qwen"
    if "llama" in name or "llemma" in name:
        return "llama"
    if "mistral" in name:
        return "mistral"
    return None

class AgentContext:
    def __init__(self, player: Player, agent: AgentSpec | str, lane_url: str):
        self.player = player
        self.agent = agent
        self.client = InferenceClient(lane_url, agent.model if isinstance(agent, AgentSpec) else  agent)
        self.chat_history: List[Dict[str, str]] = []
        self.pending_observation: str | None = None

class MatchRunner:
    def __init__(self, engine: InferenceEngine, lobby: str | LobbyConfig | None = None, game_logger: GameLogger = None):
        self.engine = engine
        self.game_logger = game_logger

        if isinstance(lobby, LobbyConfig):
            self.lobby = lobby
        else:
            self.lobby = load_lobby(lobby)

        self.game_cfg = GameConfiguration(game_mode=self.lobby.game.mode, coven=self.lobby.game.coven)
        self.players: List[Player] = [Player(a.id, create_role_from_name(a.role)) for a in self.lobby.agents]
        self.game = Game(self.game_cfg, self.players)
        # Assign roles from the generated role list to each player
        if hasattr(self.game_cfg, 'role_list') and len(self.game_cfg.role_list) == len(self.players):
            for player, role in zip(self.players, self.game_cfg.role_list):
                player.assign_role(create_role_from_name(role))

        self.agents: Dict[str, AgentContext] = {}
        for agent_spec in self.lobby.agents:
            lane = self.engine.register_agent(agent_spec.id, agent_spec.model)
            ctx = AgentContext(self._player_by_name(agent_spec.id), agent_spec, lane[1])
            self.agents[agent_spec.id] = ctx

        self.budget = TokenBudgetManager.from_yaml("configs/environment_limits.yaml")
        self.handler = ih.InteractionHandler(self.game)
        self.global_turn_counter = 0

    def _player_by_name(self, name: str) -> Player:
        for p in self.players:
            if p.name == name:
                return p
        raise KeyError(name)

    def run(self):
        # Robustly ensure the game always starts with PRE_NIGHT and agents get a turn in PRE_NIGHT
        if self.game.day == 1 and self.game.phase.name == "PRE_NIGHT":
            # Give agents a turn in PRE_NIGHT without advancing the phase
            self._process_phase_turns("Pre-Night")
            self.game.advance_to_night()  # Move to Night 1 after PRE_NIGHT
        while not self.game.game_is_over():
            self._process_day_phase()
            if self.game.game_is_over():
                break
            self._process_night_phase()
        for aid in self.agents:
            self.engine.release_agent(aid)

    def _render_public_state(self) -> Dict[str, Any]:
        # Use the actual phase name for the prompt, including PRE_NIGHT
        phase_label = self.game.phase.name.lower() if hasattr(self.game, "phase") else "discussion"
        graveyard = [{"name": p.name, "role": p.role.name.value} for p in getattr(self.game, "graveyard", [])]
        vote_board: list[tuple[str, int]] = []
        votes_needed = None
        if phase_label in {"day", "voting"}:
            votes_needed = self.game.nomination_threshold()
            vote_board = [(t.name, c) for t, c in self.game.nomination_counts().items()]
        chat_tail: list[str] = []
        if hasattr(self.game, 'chat') and self.game.chat:
            current_period_key = (self.game.day, self.game.time == Time.NIGHT)
            if current_period_key in self.game.chat.history:
                history = self.game.chat.history[current_period_key]
                recent_messages = history.messages[-10:] if len(history.messages) > 10 else history.messages
                for msg in recent_messages:
                    if msg.is_environment:
                        chat_tail.append(f"[ENV] {msg.message}")
                    else:
                        chat_tail.append(f"{msg.sender.name}: {msg.message}")
            for channel in self.game.chat.channels.values():
                if channel.messages:
                    recent_active = channel.messages[-5:] if len(channel.messages) > 5 else channel.messages
                    for msg in recent_active:
                        if msg.is_environment:
                            chat_tail.append(f"[ENV] {msg.message}")
                        else:
                            chat_tail.append(f"{msg.sender.name}: {msg.message}")
        return {
            "day": getattr(self.game, "day", 0),
            "phase": phase_label,
            "graveyard": graveyard,
            "votes_needed": votes_needed,
            "vote_board": vote_board,
            "chat_tail": chat_tail,
        }

    def _process_phase_turns(self, phase_name: str) -> None:
        print(f"\n--- {phase_name} Phase ---")
        public_state = self._render_public_state()
        living_players = [p for p in self.players if p.is_alive]
        # Use the correct phase name for token budget
        phase_for_budget = self.game.phase.name.lower()
        self.budget.start_phase(phase_for_budget, living=len(living_players))
        acted_agents = set()
        for ctx in self.agents.values():
            if ctx.player.is_alive:
                self._send_agent_turn(ctx, public_state)
                acted_agents.add(ctx.player.name)
                if self.budget.phase_exhausted() or (self.game.current_trial() and phase_name == "Nomination"):
                    print(f"Phase ended early. Skipping remaining agents.")
                    break
        for ctx in self.agents.values():
            if ctx.player.is_alive and ctx.player.name not in acted_agents:
                self.global_turn_counter += 1
                self.game_logger.log_sft_sample(
                    sample_id=f"game_{id(self.game):x}_player_{ctx.player.id}_turn_{self.global_turn_counter:04d}",
                    player_name=ctx.player.name,
                    agent=asdict(ctx.agent),
                    prompt=[],
                    completion="<wait/>",
                    metadata={
                        "role": ctx.player.role.name.value,
                        "environment_turn": self.global_turn_counter,
                        "model_generations": 0,
                        "phase": self.game.phase.name,
                        "day": self.game.day,
                        "player_id": ctx.player.id,
                        "forced_wait": True,
                        "skipped_due_to_phase_transition": True,
                    }
                )
                if not hasattr(ctx.player, 'thought_and_action_history'):
                    ctx.player.thought_and_action_history = []
                ctx.player.thought_and_action_history.append("<wait/>")

    def _send_agent_turn(self, ctx: AgentContext, public_state: Dict[str, Any]) -> None:
        TERMINAL_TAGS = ("<speak>", "<whisper", "<vote>", "<wait>", "<kill>", "<protect>", "<investigate>", "<shoot>", "<jail>", "<reveal>", "<execute>", "<douse>", "<rampage>", "<distract>", "<raise>", "<control>", "<alert>", "<transport>", "<bug>", "<watch>", "<vest>", "<remember>", "<track>", "<vision>", "<hex>", "<poison>", "<stone>", "<plunder>", "<blackmail>", "<clean>", "<disguise>", "<infect>", "<haunt>", "<seance>", "<forge>", "<trap>", "<frame>", "<hypnotize>", "<hypnotise>", "<skip>", "<pass>")
        # Remove any call to self.engine.get_tokenizer or tokenizer assignment from engine
        # All token counting is now handled by InteractionHandler.count_interaction_tokens
        model_generations = []
        if not hasattr(ctx, 'prompt_history'):
            ctx.prompt_history = []
        loop_guard = 0
        while True:
            loop_guard += 1
            if loop_guard > 6:
                print(f"[Warn] Agent {ctx.player.name} exceeded 6 inner loops, forcing wait.")
                self.global_turn_counter += 1
                self.game_logger.log_sft_sample(
                    sample_id=f"game_{id(self.game):x}_player_{ctx.player.id}_turn_{self.global_turn_counter:04d}",
                    player_name=ctx.player.name,
                    agent=asdict(ctx.agent),
                    prompt=model_generations[0]["prompt"] if model_generations else [],
                    completion="<wait/>",
                    metadata={
                        "role": ctx.player.role.name.value,
                        "environment_turn": self.global_turn_counter,
                        "model_generations": len(model_generations),
                        "phase": self.game.phase.name,
                        "day": self.game.day,
                        "player_id": ctx.player.id,
                        "forced_wait": True,
                    }
                )
                ctx.prompt_history.append({
                    "role": "assistant",
                    "content": "<think>\nNo valid action produced; forcing wait.\n</think>\n<wait/>"
                })
                break
            if not ctx.prompt_history:
                tokens_remaining = self.budget.tokens_remaining() if hasattr(self.budget, 'tokens_remaining') else None
                system_prompt = build_complete_prompt(self.game, ctx.player, "gemma", tokens_remaining=tokens_remaining)
                ctx.prompt_history.append({"role": "user", "content": system_prompt})
            msgs_out = ctx.prompt_history
            print(f"\n===== AGENT PERSPECTIVE: {ctx.player.name} ({ctx.player.role.name}) =====")
            print("--- USER MESSAGE---")
            print(msgs_out[-1]['content'])
            print("==============================================\n")
            resp = ctx.client.chat(msgs_out)
            assistant_content = resp["choices"][0]["message"]["content"]
            model_generations.append({
                "prompt": msgs_out,
                "completion": assistant_content,
                "generation_number": loop_guard
            })
            ctx.prompt_history.append({"role": "assistant", "content": assistant_content})
            action_text = assistant_content
            # List of interaction tags to check - include ALL night and day action tags
            interaction_tags = [
                # Day actions
                "speak", "whisper", "vote", "wait",
                # Night actions
                "kill", "protect", "investigate", "shoot", "jail", "reveal",
                "execute", "douse", "rampage", "distract", "raise", "control",
                "alert", "transport", "bug", "watch", "vest", "remember", "track",
                "vision", "hex", "poison", "stone", "plunder", "blackmail", "clean",
                "disguise", "infect", "haunt", "seance", "forge", "trap", "frame",
                "hypnotize", "hypnotise", "skip", "pass"
            ]
            total_tokens = 0
            for tag in interaction_tags:
                total_tokens += self.handler.count_interaction_tokens(action_text, tag)
            self.budget.consume("public", total_tokens)
            patched_text, observation = apply_first_tool_call(assistant_content, game=self.game, player=ctx.player)
            if observation is not None:
                ctx.prompt_history.append({"role": OBSERVATION_ROLE, "content": observation})
                continue
            # Extract the action tag for phase handling
            action_tag = None
            for tag in interaction_tags:
                if f"<{tag}" in assistant_content:
                    action_tag = tag
                    break
            # Call phase handlers as appropriate
            if hasattr(self.game, 'day_phase_manager') and self.game.day_phase_manager:
                dpm = self.game.day_phase_manager
                phase = self.game.phase.name if hasattr(self.game.phase, 'name') else str(self.game.phase)
                if phase == "DEFENSE":
                    dpm.handle_defense_action(ctx.player, action_tag)
                elif phase == "JUDGEMENT":
                    dpm.handle_judgement_action(ctx.player, action_tag)
                elif phase == "LAST_WORDS":
                    dpm.handle_last_words_action(ctx.player, action_tag)
            if any(tag in assistant_content for tag in TERMINAL_TAGS):
                # Process all actions through the interaction handler
                self.handler.parse_and_execute(ctx.player, assistant_content)
                self.global_turn_counter += 1
                self.game_logger.log_sft_sample(
                    sample_id=f"game_{id(self.game):x}_player_{ctx.player.id}_turn_{self.global_turn_counter:04d}",
                    player_name=ctx.player.name,
                    agent=asdict(ctx.agent),
                    prompt=ctx.prompt_history,
                    completion=assistant_content,
                    metadata={
                        "role": ctx.player.role.name.value,
                        "environment_turn": self.global_turn_counter,
                        "model_generations": len(model_generations),
                        "phase": self.game.phase.name,
                        "day": self.game.day,
                        "player_id": ctx.player.id,
                    }
                )
                # Store both thoughts and actions
                if not hasattr(ctx.player, 'thought_and_action_history'):
                    ctx.player.thought_and_action_history = []
                ctx.player.thought_and_action_history.append(assistant_content)
                ctx.prompt_history = []
                break

    def _process_night_phase(self):
        if self.game.time != Time.NIGHT:
            self.game.advance_to_night()
        public_state = self._render_public_state()
        for ctx in self.agents.values():
            self._send_agent_turn(ctx, public_state)
        self.game.advance_phase()

    def _process_day_phase(self):
        """Process the entire day phase with proper phase transitions."""
        # Only advance to day if not already in PRE_NIGHT
        if self.game.phase.name != "PRE_NIGHT":
            self.game.advance_to_day()
        
        # Track phases to prevent infinite loops
        phases_processed = set()
        max_phases = 10  # Safety limit
        
        while len(phases_processed) < max_phases:
            current_phase = self.game.phase.name
            if current_phase in phases_processed:
                print(f"Warning: Phase {current_phase} already processed, breaking loop")
                break
                
            phases_processed.add(current_phase)
            phase_label = current_phase.replace("_"," ").title()
            
            print(f"\n--- Processing {phase_label} Phase ---")
            self._process_phase_turns(phase_label)
            
            # Advance to next phase
            old_phase = self.game.phase.name
            self.game.advance_phase()
            new_phase = self.game.phase.name
            
            print(f"Phase transition: {old_phase} -> {new_phase}")
            
            # Check for game over
            if self.game.game_is_over():
                break
                
            # If we've reached PRE_NIGHT, we're done with the day
            if new_phase == "PRE_NIGHT":
                break

    _SPEAK_RE = re.compile(r"<speak>(.*?)</speak>", re.DOTALL | re.IGNORECASE)
    _WHISPER_RE = re.compile(r"<whisper\s+target=\"(.*?)\">(.*?)</whisper>", re.DOTALL | re.IGNORECASE)

    def _apply_public_action(self, player: Player, assistant_text: str):
        m = self._SPEAK_RE.search(assistant_text)
        if m:
            text = m.group(1).strip()
            res = self.game.speak(player, text)
            print(res)
        m = self._WHISPER_RE.search(assistant_text)
        if m:
            target_name, text = m.group(1).strip(), m.group(2).strip()
            target = self.game.get_player_by_name(target_name)
            if target:
                res = self.game.whisper(player, target, text)
                print(res) 