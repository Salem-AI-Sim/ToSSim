import re
from typing import TYPE_CHECKING, List, Union

from Simulation.enums import Time, Phase, RoleName, Attack, DuelMove, Faction
from Simulation.errors import ErrorCode, format_error, format_success
from Simulation.grammar import ToSSimGrammarParser  # <-- Add this import
from transformers import AutoTokenizer

# Try to load the HuggingFace tokenizer locally; fall back gracefully.
try:
     from transformers import AutoTokenizer
     # local_files_only=True prevents network downloads
     _tokenizer = AutoTokenizer.from_pretrained(
         "google/gemma-3-4b-it", local_files_only=True
     )
except Exception:
    # If the model is unavailable or HF isn't installed, disable the tokenizer
    _tokenizer = None



class InteractionHandler:
    """
    Parses agent text, validates tool-like interactions, and mutates game state.
    This is the primary bridge between agent output and the game simulation.
    """

    def __init__(self, game: 'Game'):
        self.game = game
        # Simple regex to find <tag>content</tag> or <tag/>
        self.tool_pattern = re.compile(r"<([a-zA-Z_]+)(?:\s*/>|>(.*?)</\1>)", re.DOTALL)
        # Get tool and interaction tags from grammar
        parser = ToSSimGrammarParser()
        self.tool_tags = parser.tool_tags
        self.interaction_tags = parser.interaction_tags
        # Get logger from game for action logging
        self.logger = getattr(game, 'logger', None)

    def _resolve_target(self, actor: 'Player', target_name: str) -> Union['Player', str]:
        """Finds a player based on a name string.
        
        Handles 'self', case-insensitivity, and ambiguity.
        Returns a Player object on success or an error string on failure.
        """
        if not target_name:
            return format_error(ErrorCode.INVALID_TARGET, "Target name is empty")
        
        target_name = target_name.strip()

        if target_name.lower() == 'self':
            return actor

        # 1. Case-insensitive search
        alive_players = [p for p in self.game.players if p.is_alive]
        matches_ci = [p for p in alive_players if p.name.lower() == target_name.lower()]

        if not matches_ci:
            return format_error(ErrorCode.TARGET_NOT_FOUND, f"No living player named '{target_name}' found")
        
        if len(matches_ci) == 1:
            return matches_ci[0]

        # 2. If multiple CI matches, try case-sensitive to resolve
        matches_cs = [p for p in matches_ci if p.name == target_name]
        
        if len(matches_cs) == 1:
            return matches_cs[0]
        
        # 3. Ambiguous if multiple CS matches (e.g. "Bob", "bob") or no CS match
        return format_error(ErrorCode.INVALID_TARGET, f"Ambiguous target '{target_name}'. Multiple players have similar names")

    def parse_and_execute(self, actor: 'Player', text: str) -> List[str]:
        """
        Parses text for all valid tool calls and executes them.
        Returns a list of result strings for each action attempted.
        """
        results = []
        debug_seen = []
        # Remove <think>...</think> blocks before processing
        text_wo_think = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        matches = self.tool_pattern.finditer(text_wo_think)

        # --- Allowed tags for dead players (per Town of Salem logic) ---
        allowed_dead_tags = {
            "speak", "wait", "graveyard", "view_will", "check_will", "chat_history", "view_notebook"
        }

        for match in matches:
            tag_name = match.group(1).lower()
            content = match.group(2) if match.group(2) is not None else ""
            debug_seen.append(f"<{tag_name}>{content}")
            actor.research_metrics['total_tool_calls'] += 1

            # --- Dead player block: only allow certain tags if dead ---
            if not actor.is_alive and tag_name not in allowed_dead_tags:
                self.game.chat.add_player_notification(actor, f"Error: You are dead and cannot use <{tag_name}>.")
                continue

            handler_method = getattr(self, f"_handle_{tag_name}", None)
            if not handler_method:
                actor.research_metrics['unsuccessful_tool_uses'] += 1
                self.game.chat.add_player_notification(actor, f"Error: Unknown tool '{tag_name}'")
                continue

            try:
                # Interactions now send notifications directly and don't return observation strings
                if tag_name in self.interaction_tags:
                    handler_method(actor, content)
                # Tools still return strings to be displayed as observations
                elif tag_name in self.tool_tags:
                    result = handler_method(actor, content)
                    if result:
                        results.append(result)
                        # Persist environment static tool results
                        from Simulation.tools.registry import _TOOL_REGISTRY
                        tool_info = _TOOL_REGISTRY.get(tag_name, {})
                        if tool_info.get('class') == 'environment_static':
                            if not hasattr(actor, 'environment_static_tool_results'):
                                actor.environment_static_tool_results = {}
                            if not hasattr(actor, 'environment_static_tools_used'):
                                actor.environment_static_tools_used = set()
                            actor.environment_static_tool_results[tag_name] = result
                            actor.environment_static_tools_used.add(tag_name)

                # Log the action if logger is available
                if self.logger:
                    turn_name = f"Night {self.game.day}" if self.game.time == Time.NIGHT else f"Day {self.game.day}"
                    if tag_name in self.tool_tags:
                        self.logger.log_tool_call(actor.name, tag_name, content, result, turn_name)
                    elif tag_name in self.interaction_tags:
                        self.logger.log_interaction(actor.name, tag_name, content, turn_name)

            except Exception as e:
                actor.research_metrics['unsuccessful_tool_uses'] += 1
                self.game.chat.add_player_notification(actor, f"Error executing '{tag_name}': {e}")
        
        if debug_seen:
            print(f"[Debug] Parsed commands from '{actor.name}': {', '.join(debug_seen)}")
        
        # Return only the direct results from tools
        return results

    # --- Day Action Handlers ---

    def _handle_jail(self, actor: 'Player', content: str):
        if self.game.time != Time.DAY:
            self.game.chat.add_player_notification(actor, "Error: You can only decide to jail someone during the day.")
            return
        if actor.role.name != RoleName.JAILOR:
            self.game.chat.add_player_notification(actor, "Error: You are not the Jailor.")
            return
        if actor.role.jailed_target:
            self.game.chat.add_player_notification(actor, "Error: You have already decided who to jail tonight.")
            return

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target) # Send error string from resolver
            return

        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot jail yourself.")
            return
        
        self.game.submit_day_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will jail {target.name} tonight.")

    def _handle_reveal(self, actor: 'Player', content: str):
        # Content is ignored for reveal
        if self.game.time != Time.DAY:
            self.game.chat.add_player_notification(actor, "Error: You can only reveal during the day.")
            return
        if actor.role.name != RoleName.MAYOR:
            self.game.chat.add_player_notification(actor, "Error: You are not the Mayor.")
            return
        if actor.role.revealed:
            self.game.chat.add_player_notification(actor, "Error: You have already revealed.")
            return

        self.game.submit_day_action(actor)
        self.game.chat.add_player_notification(actor, "Success: You have revealed yourself as the Mayor!")
    
    # --- Night Action Handlers ---

    def _handle_shoot(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only shoot at night.")
            return
        if actor.role.name != RoleName.VIGILANTE:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot shoot.")
            return
        
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return

        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will shoot {target.name} tonight.")

    def _handle_protect(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only protect at night.")
            return
        if actor.role.name not in [RoleName.DOCTOR, RoleName.BODYGUARD, RoleName.CRUSADER, RoleName.GUARDIAN_ANGEL]:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot protect.")
            return

        if actor.role.name == RoleName.GUARDIAN_ANGEL:
            target = getattr(actor.role, 'protect_target', None)
            if not target:
                self.game.chat.add_player_notification(actor, "Error: No assigned target to guard.")
                return
        else:
            target = self._resolve_target(actor, content)
            if isinstance(target, str):
                self.game.chat.add_player_notification(actor, target)
                return
            
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will protect {target.name} tonight.")

    def _handle_investigate(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only investigate at night.")
            return
        if actor.role.name not in [RoleName.SHERIFF, RoleName.INVESTIGATOR, RoleName.CONSIGLIERE]:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot investigate.")
            return

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return

        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot target yourself.")
            return

        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will investigate {target.name} tonight.")

    def _handle_kill(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only kill at night.")
            return

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return

        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot target yourself.")
            return

        if actor.role.name == RoleName.GODFATHER:
            mafioso = self.game.find_player_by_role(RoleName.MAFIOSO)
            if mafioso and mafioso.is_alive and not mafioso.is_jailed:
                self.game.submit_night_action(mafioso, target)
                self.game.chat.add_player_notification(actor, f"Success: You ordered the Mafioso to kill {target.name} tonight.")
            else:
                self.game.submit_night_action(actor, target)
                self.game.chat.add_player_notification(actor, f"Success: You will personally kill {target.name} tonight.")
            return

        if actor.role.attack == Attack.NONE:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot kill.")
            return

        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will attempt to kill {target.name} tonight.")

    def _handle_execute(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only execute at night.")
            return
        if actor.role.name != RoleName.JAILOR:
            self.game.chat.add_player_notification(actor, "Error: You are not the Jailor.")
            return

        target = actor.role.jailed_target
        if not target or not target.is_alive:
            self.game.chat.add_player_notification(actor, "Error: You have no living jailed target to execute.")
            return

        if content:
            resolved = self._resolve_target(actor, content)
            if isinstance(resolved, str):
                self.game.chat.add_player_notification(actor, resolved)
                return
            if resolved != target:
                self.game.chat.add_player_notification(actor, f"Error: {resolved.name} is not your current jailed prisoner.")
                return

        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will execute {target.name} tonight.")

    # --- Arsonist ---
    def _handle_douse(self, actor: 'Player', content: str) -> str:
        """Arsonist ability: douse a target or ignite by targeting self."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only act at night."

        if actor.role.name != RoleName.ARSONIST:
            return "Error: You are not the Arsonist."

        # If no content, treat as cleaning (handled in role logic by passing None)
        if not content:
            self.game.submit_night_action(actor, None)
            return "Success: You will attempt to clean gasoline off yourself tonight."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        self.game.submit_night_action(actor, target)

        if target == actor:
            return "Success: You will ignite all doused players tonight!"
        else:
            return f"Success: You will douse {target.name} in gasoline tonight."

    # --- Werewolf Rampage ---
    def _handle_rampage(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only rampage at night."
        if actor.role.name != RoleName.WEREWOLF:
            return "Error: You are not the Werewolf."

        # Empty content or 'self' means rampage at home
        if not content:
            self.game.submit_night_action(actor, None)
            return "Success: You will rampage at your own home tonight."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        self.game.submit_night_action(actor, target)
        return f"Success: You will rampage at {target.name}'s house tonight."

    # --- Voting Handlers (Special) ---

    def _handle_nominate(self, actor: 'Player', content: str):
        from Simulation.enums import Phase as PhaseEnum
        if self.game.phase != PhaseEnum.NOMINATION:
            self.game.chat.add_player_notification(actor, "Error: You cannot nominate during this phase.")
            return
        if not content:
            self.game.chat.add_player_notification(actor, "Error: Please specify a target to nominate.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if self.game.nomination_threshold is None:
            self.game.chat.add_player_notification(actor, "Error: Nomination system not active.")
            return
        result = self.game.add_nomination(actor, target)
        self.game.chat.add_player_notification(actor, result)

    def _handle_vote(self, actor: 'Player', content: str):
        from Simulation.enums import Phase as PhaseEnum
        
        if not content.strip():
            self.game.chat.add_player_notification(actor, "Error: Please specify a target or verdict.")
            return

        if self.game.phase == PhaseEnum.NOMINATION:
            # Nominating a player for trial
            target = self._resolve_target(actor, content)
            if isinstance(target, str):
                self.game.chat.add_player_notification(actor, target)
                return
            result = self.game.add_nomination(actor, target)
            self.game.chat.add_player_notification(actor, result)
            
        elif self.game.phase == PhaseEnum.JUDGEMENT:
            # Voting guilty/innocent/abstain
            verdict = content.strip().upper()
            if verdict not in {"GUILTY", "INNOCENT", "ABSTAIN"}:
                self.game.chat.add_player_notification(actor, "Error: Vote must be GUILTY, INNOCENT, or ABSTAIN.")
                return
            result = self.game.cast_verdict(actor, verdict)
            self.game.chat.add_player_notification(actor, result)
            
        else:
            self.game.chat.add_player_notification(actor, f"Error: Voting is not allowed during {self.game.phase.name} phase.")

    def _handle_distract(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only distract at night.")
            return
        allowed_roles = {RoleName.TAVERN_KEEPER, RoleName.ESCORT, RoleName.BOOTLEGGER, RoleName.CONSORT}
        if actor.role.name not in allowed_roles:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot distract.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot target yourself.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will distract {target.name} tonight.")

    def _handle_raise(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only raise corpses at night.")
            return
        if actor.role.name not in {RoleName.RETRIBUTIONIST, RoleName.NECROMANCER}:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot raise corpses.")
            return
        if not content or ',' not in content:
            self.game.chat.add_player_notification(actor, "Error: Provide corpse and target as 'Corpse,Target'.")
            return
        corpse_name, target_name = [s.strip() for s in re.split(r'[;,]', content, maxsplit=1)]
        corpse = next((p for p in self.game.players if p.name.lower() == corpse_name.lower()), None)
        if not corpse or corpse.is_alive:
            self.game.chat.add_player_notification(actor, f"Error: No dead player named '{corpse_name}' found.")
            return
        target = self._resolve_target(actor, target_name)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        actor.visit(corpse)
        self.game.submit_night_action(actor, (corpse, target))
        self.game.chat.add_player_notification(actor, f"Success: You will raise {corpse.name}'s corpse to act on {target.name} tonight.")

    def _handle_control(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only control at night.")
            return
        if actor.role.name not in [RoleName.WITCH, RoleName.COVEN_LEADER]:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot control others.")
            return
        if not content or ',' not in content:
            self.game.chat.add_player_notification(actor, "Error: Provide puppet and victim as 'Puppet,Victim'.")
            return
        puppet_name, victim_name = [s.strip() for s in re.split(r'[;,]', content, maxsplit=1)]
        puppet = self._resolve_target(actor, puppet_name)
        if isinstance(puppet, str):
            self.game.chat.add_player_notification(actor, puppet)
            return
        victim = self._resolve_target(actor, victim_name)
        if isinstance(victim, str):
            self.game.chat.add_player_notification(actor, victim)
            return
        self.game.submit_night_action(actor, (puppet, victim))
        self.game.chat.add_player_notification(actor, f"Success: You will control {puppet.name} to target {victim.name} tonight.")

    def _handle_alert(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only alert at night.")
            return
        if actor.role.name != RoleName.VETERAN:
            self.game.chat.add_player_notification(actor, "Error: You are not the Veteran.")
            return
        if content and content.strip().lower() not in ["self", actor.name.lower()]:
            self.game.chat.add_player_notification(actor, "Error: Alert has no target – use <alert/> or <alert>self</alert>.")
            return
        self.game.submit_night_action(actor, actor)
        self.game.chat.add_player_notification(actor, "Success: You will go on alert tonight.")

    def _handle_transport(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only transport at night.")
            return
        if actor.role.name != RoleName.TRANSPORTER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Transporter.")
            return
        if not content or ',' not in content:
            self.game.chat.add_player_notification(actor, "Error: Provide two names separated by a comma: 'A,B'.")
            return
        name1, name2 = [s.strip() for s in re.split(r'[;,]', content, maxsplit=1)]
        p1 = actor if name1.lower() == 'self' else self._resolve_target(actor, name1)
        if isinstance(p1, str):
            self.game.chat.add_player_notification(actor, p1)
            return
        p2 = actor if name2.lower() == 'self' else self._resolve_target(actor, name2)
        if isinstance(p2, str):
            self.game.chat.add_player_notification(actor, p2)
            return
        if p1 == p2:
            self.game.chat.add_player_notification(actor, "Error: You must select two different players (they can include yourself).")
            return
        self.game.submit_night_action(actor, (p1, p2))
        self.game.chat.add_player_notification(actor, f"Success: You will transport {p1.name} with {p2.name} tonight.")

    def _handle_bug(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only bug at night.")
            return
        if actor.role.name != RoleName.SPY:
            self.game.chat.add_player_notification(actor, "Error: You are not the Spy.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will bug {target.name}'s house tonight.")

    def _handle_watch(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only watch at night.")
            return
        if actor.role.name != RoleName.LOOKOUT:
            self.game.chat.add_player_notification(actor, "Error: You are not the Lookout.")
            return
        if not content:
            self.game.chat.add_player_notification(actor, "Error: You must specify someone to watch (use 'self' to watch your own house).")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will watch {target.name} tonight.")

    def _handle_vest(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only vest at night.")
            return
        if actor.role.name != RoleName.SURVIVOR:
            self.game.chat.add_player_notification(actor, "Error: You are not the Survivor.")
            return
        if content and content.strip().lower() not in ["self", actor.name.lower()]:
            self.game.chat.add_player_notification(actor, "Error: The vest ability only targets yourself – use <vest/> or <vest>self</vest>.")
            return
        self.game.submit_night_action(actor, actor)
        self.game.chat.add_player_notification(actor, "Success: You will wear a bulletproof vest tonight.")

    def _handle_remember(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only remember a role at night.")
            return
        if actor.role.name != RoleName.AMNESIAC:
            self.game.chat.add_player_notification(actor, "Error: You are not the Amnesiac.")
            return
        if not content:
            self.game.chat.add_player_notification(actor, "Error: Specify whose role to remember.")
            return
        corpse = next((p for p in self.game.graveyard if p.name.lower() == content.strip().lower()), None)
        if not corpse:
            self.game.chat.add_player_notification(actor, f"Error: No dead player named '{content}' found in the graveyard.")
            return
        if getattr(corpse, "was_stoned", False) or getattr(corpse, "was_cleaned", False):
            self.game.chat.add_player_notification(actor, "Error: You cannot remember a cleaned or stoned player.")
            return
        self.game.submit_night_action(actor, corpse)
        self.game.chat.add_player_notification(actor, f"Success: You will remember that you were a {corpse.role.name.value}.")

    def _handle_track(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only track at night.")
            return
        if actor.role.name != RoleName.TRACKER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Tracker.")
            return
        if not content:
            self.game.chat.add_player_notification(actor, "Error: You must specify someone to track.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot track yourself.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will track {target.name} tonight.")

    def _handle_vision(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only use your vision at night.")
            return
        if actor.role.name != RoleName.PSYCHIC:
            self.game.chat.add_player_notification(actor, "Error: You are not the Psychic.")
            return
        self.game.submit_night_action(actor, None)
        self.game.chat.add_player_notification(actor, "Success: You focus on your crystal ball tonight.")

    def _handle_hex(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only hex at night.")
            return
        if actor.role.name != RoleName.HEX_MASTER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Hex Master.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot target yourself.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will hex {target.name} tonight.")

    def _handle_poison(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only poison at night.")
            return
        if actor.role.name != RoleName.POISONER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Poisoner.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot target yourself.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will poison {target.name} tonight.")

    def _handle_stone(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only use stone gaze at night.")
            return
        if actor.role.name != RoleName.MEDUSA:
            self.game.chat.add_player_notification(actor, "Error: You are not Medusa.")
            return
        if not content or content.strip().lower() in ["self", actor.name.lower()]:
            self.game.submit_night_action(actor, actor)
            self.game.chat.add_player_notification(actor, "Success: You will use stone gaze on visitors tonight.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.submit_night_action(actor, actor)
            self.game.chat.add_player_notification(actor, "Success: You will use stone gaze on visitors tonight.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will attempt to petrify {target.name} tonight.")

    def _handle_plunder(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only plunder at night.")
            return
        if actor.role.name != RoleName.PIRATE:
            self.game.chat.add_player_notification(actor, "Error: You are not the Pirate.")
            return
        if not content:
            self.game.chat.add_player_notification(actor, "Error: You must specify a target (and optionally a weapon).")
            return
        parts = [p.strip() for p in re.split(r'[;,]', content) if p.strip()]
        target_name = parts[0] if parts else ""
        weapon_name = parts[1] if len(parts) > 1 else None
        target = self._resolve_target(actor, target_name)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot target yourself.")
            return
        chosen_move = None
        if weapon_name:
            weapon_lc = weapon_name.lower()
            mapping = {"rapier": DuelMove.RAPIER, "scimitar": DuelMove.SCIMITAR, "pistol": DuelMove.PISTOL}
            if weapon_lc not in mapping:
                self.game.chat.add_player_notification(actor, "Error: Weapon must be Rapier, Scimitar, or Pistol.")
                return
            chosen_move = mapping[weapon_lc]
            actor.role.chosen_move = chosen_move
        else:
            actor.role.chosen_move = None
        self.game.submit_night_action(actor, target)
        if chosen_move:
            self.game.chat.add_player_notification(actor, f"Success: You will plunder {target.name} tonight with your {chosen_move.value}.")
        else:
            self.game.chat.add_player_notification(actor, f"Success: You will plunder {target.name} tonight with a random weapon.")

    def _handle_blackmail(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only blackmail at night.")
            return
        if actor.role.name != RoleName.BLACKMAILER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Blackmailer.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot blackmail yourself.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will blackmail {target.name} tonight.")

    def _handle_clean(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only clean at night.")
            return
        if actor.role.name != RoleName.JANITOR:
            self.game.chat.add_player_notification(actor, "Error: You are not the Janitor.")
            return
        if actor.role.charges <= 0:
            self.game.chat.add_player_notification(actor, "Error: You have no cleanings left.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot clean yourself.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will attempt to clean {target.name} tonight.")

    def _handle_disguise(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only disguise at night.")
            return
        if actor.role.name != RoleName.DISGUISER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Disguiser.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target.role.faction == Faction.MAFIA:
            self.game.chat.add_player_notification(actor, "Error: You cannot disguise as a Mafia member.")
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot disguise as yourself.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will disguise yourself as {target.name} tonight.")

    def _handle_infect(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only infect at night.")
            return
        if actor.role.name != RoleName.PLAGUEBEARER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Plaguebearer.")
            return
        if not content.strip():
            target = actor
        else:
            target = self._resolve_target(actor, content)
            if isinstance(target, str):
                self.game.chat.add_player_notification(actor, target)
                return
        self.game.submit_night_action(actor, target)
        if target == actor:
            self.game.chat.add_player_notification(actor, "Success: You will stay home and spread disease to any visitors tonight.")
        else:
            self.game.chat.add_player_notification(actor, f"Success: You will infect {target.name} tonight.")

    def _handle_haunt(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: Haunting can only be performed at night.")
            return
        if actor.role.name != RoleName.JESTER:
            self.game.chat.add_player_notification(actor, "Error: Only a Jester can haunt.")
            return
        if actor.is_alive:
            self.game.chat.add_player_notification(actor, "Error: You are still alive and cannot haunt anyone.")
            return
        candidates = getattr(actor, "haunt_candidates", None)
        if not candidates:
            self.game.chat.add_player_notification(actor, "Error: No valid haunt candidates available.")
            return
        if not content.strip():
            actor.haunt_target = None
            self.game.chat.add_player_notification(actor, "Success: You have left your haunting to fate.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target not in candidates:
            self.game.chat.add_player_notification(actor, "Error: You may only haunt someone who voted against you.")
            return
        actor.haunt_target = target
        self.game.chat.add_player_notification(actor, f"Success: You will haunt {target.name} tonight.")

    def _handle_seance(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: Séance can only be performed at night.")
            return
        if actor.role.name != RoleName.MEDIUM:
            self.game.chat.add_player_notification(actor, "Error: You are not the Medium.")
            return
        if actor.role.seances <= 0:
            self.game.chat.add_player_notification(actor, "Error: You have already used your séance.")
            return
        if not content.strip():
            self.game.chat.add_player_notification(actor, "Error: You must specify a living player to contact.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if not target.is_alive:
            self.game.chat.add_player_notification(actor, "Error: You may only seance a living player.")
            return
        if actor == target:
            self.game.chat.add_player_notification(actor, "Error: You cannot seance yourself.")
            return
        result = actor.role.seance(actor, target, self.game)
        self.game.chat.add_player_notification(actor, result)
        if "established a seance" in result:
            self.game.submit_night_action(actor, target)

    def _handle_forge(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only forge at night.")
            return
        if actor.role.name != RoleName.FORGER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Forger.")
            return
        if actor.role.charges <= 0:
            self.game.chat.add_player_notification(actor, "Error: You have no forging supplies left.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            self.game.chat.add_player_notification(actor, "Error: You cannot forge your own will.")
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will forge {target.name}'s last will tonight.")

    def _handle_trap(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only set/remove traps at night.")
            return
        if actor.role.name != RoleName.TRAPPER:
            self.game.chat.add_player_notification(actor, "Error: You are not the Trapper.")
            return
        if not content or content.strip().lower() in ["self", actor.name.lower()]:
            self.game.submit_night_action(actor, actor)
            self.game.chat.add_player_notification(actor, "Success: You will dismantle your trap tonight.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        if target == actor:
            target = actor
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will start building a trap at {target.name}'s house tonight.")

    def _handle_frame(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only frame at night.")
            return
        if actor.role.name != RoleName.FRAMER:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot frame.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will frame {('yourself' if target==actor else target.name)} tonight.")

    def _handle_hypnotise(self, actor: 'Player', content: str):
        self._handle_hypnotize(actor, content)

    def _handle_hypnotize(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only hypnotize at night.")
            return
        if actor.role.name != RoleName.HYPNOTIST:
            self.game.chat.add_player_notification(actor, "Error: Your role cannot hypnotize.")
            return
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            self.game.chat.add_player_notification(actor, target)
            return
        self.game.submit_night_action(actor, target)
        self.game.chat.add_player_notification(actor, f"Success: You will hypnotize {target.name} tonight.")

    def _handle_skip(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only skip during the night.")
            return
        self.game.submit_night_action(actor, None)
        self.game.chat.add_player_notification(actor, "Success: You will skip your night action.")

    def _handle_pass(self, actor: 'Player', content: str):
        if self.game.time != Time.NIGHT:
            self.game.chat.add_player_notification(actor, "Error: You can only pass during the night.")
            return
        self.game.submit_night_action(actor, None)
        self.game.chat.add_player_notification(actor, "Success: You will pass your night action.")

    def _handle_wait(self, actor: 'Player', content: str):
        self.game.chat.add_player_notification(actor, "You choose to wait and observe the ongoing discussion.")

    def _handle_notebook(self, actor: 'Player', content: str) -> str:
        if not actor.is_alive:
            return "Error: You cannot use notebook while dead."
        actor.research_metrics['times_used_notebook'] += 1
        from Simulation.tools.registry import _exec_notebook
        return _exec_notebook(content, game=self.game, player=actor)

    def _handle_speak(self, actor: 'Player', content: str):
        if not content or not content.strip():
            self.game.chat.add_player_notification(actor, "Error: No message provided to speak.")
            return
        if hasattr(self.game, 'chat') and hasattr(self.game.chat, 'send_speak'):
            self.game.chat.send_speak(actor, content.strip())

    def _handle_whisper(self, actor: 'Player', content: str):
        import re
        match = re.match(r'\s*target\s*=\s*"([^"]+)"\s*>(.*)', content, re.DOTALL)
        if not match:
            self.game.chat.add_player_notification(actor, "Error: Invalid whisper format. Use <whisper target=\"PlayerName\">message<\/whisper>")
            return
        target_name, message = match.groups()
        target_name = target_name.strip()
        message = message.strip()
        if not target_name or not message:
            self.game.chat.add_player_notification(actor, "Error: Whisper must specify a target and a message.")
            return
        target_player = None
        for p in self.game.players:
            if p.name.lower() == target_name.lower() and p.is_alive:
                target_player = p
                break
        if not target_player:
            self.game.chat.add_player_notification(actor, f"Error: No living player named '{target_name}' found.")
            return
        if hasattr(self.game, 'chat') and hasattr(self.game.chat, 'send_whisper'):
            self.game.chat.send_whisper(actor, target_player, message)
            self.game.chat.add_player_notification(actor, f"Success: Your message has been privately delivered to {target_player.name}.")

    def extract_action_text(self, text: str) -> str:
        """
        Removes <think>...</think> blocks from the text.
        """
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    def _handle_roles(self, actor: 'Player', content: str) -> str:
        import json
        from pathlib import Path
        role_name = content.strip()
        if not role_name:
            return "Error: No role name provided."
        roles_path = Path(__file__).parent / "tools" / "roles.json"
        try:
            with open(roles_path, "r", encoding="utf-8") as f:
                roles_data = json.load(f)
        except FileNotFoundError:
            return "Error: roles.json not found."
        except json.JSONDecodeError as e:
            return f"Error: Could not parse roles.json: {e}"
        for key, value in roles_data.items():
            if key.lower() == role_name.lower():
                details = f"Role: {key}\n"
                for k, v in value.items():
                    details += f"{k}: {v}\n"
                return details.strip()
        return f"Error: Role '{role_name}' not found." 

    @staticmethod
    def extract_interaction_content(text: str, tag: str) -> str:
        """
        Extracts the content inside a given interaction tag (e.g., <speak>...</speak>).
        Returns the inner string, or an empty string if not found.
        """
        pattern = fr"<{tag}[^>]*>(.*?)</{tag}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def count_interaction_tokens(text: str, tag: str) -> int:
        """
        Counts the number of tokens (using google/gemma-3-4b-it tokenizer) for the content inside the specified interaction tag.
        Returns 0 if the tag is not found.
        """
        content = InteractionHandler.extract_interaction_content(text, tag)
        if not content:
            return 0

        # If a tokenizer is available, use it.  Otherwise fall back to whitespace tokenisation.
        if _tokenizer is not None:
            try:
                return len(_tokenizer.encode(content, add_special_tokens=False))
            except Exception:
                pass
        return len(content.split())