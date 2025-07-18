import re
from typing import TYPE_CHECKING, List, Union

from Simulation.enums import Time, Phase, RoleName, Attack, DuelMove, Faction
from Simulation.errors import ErrorCode, format_error, format_success
from Simulation.grammar import ToSSimGrammarParser  # <-- Add this import

if TYPE_CHECKING:
    from .game import Game
    from .player import Player

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
        
        for match in matches:
            tag_name = match.group(1).lower()
            content = match.group(2) if match.group(2) is not None else ""
            debug_seen.append(f"<{tag_name}>{content}")
            actor.research_metrics['total_tool_calls'] += 1

            handler_method = getattr(self, f"_handle_{tag_name}", None)
            if not handler_method:
                actor.research_metrics['unsuccessful_tool_uses'] += 1
                results.append(format_error(ErrorCode.UNKNOWN_TOOL, f"Unknown tool '{tag_name}'"))
                continue

            try:
                result = handler_method(actor, content)
                print(f"[Debug] Handler result for {tag_name}: {result}")
                if tag_name in self.tool_tags:
                    # Only wrap tool results in <observation>
                    if result:
                        results.append(format_success(result))
                elif tag_name in self.interaction_tags:
                    # For interactions, only return result if it's a meaningful message (error, confirmation, or private feedback)
                    if result and (result.startswith("Error:") or result.startswith("Success:") or result.startswith("[")):
                        results.append(format_success(result))
                    # Otherwise, do not return an observation (environment effect only)
                else:
                    # Unknown tag (should not happen due to earlier check)
                    results.append(format_error(ErrorCode.UNKNOWN_TOOL, f"Unknown tag '{tag_name}'"))
            except Exception as e:
                actor.research_metrics['unsuccessful_tool_uses'] += 1
                results.append(format_error(ErrorCode.HANDLER_ERROR, f"Error executing '{tag_name}': {e}"))
        if debug_seen:
            print(f"[Debug] Parsed commands from '{actor.name}': {', '.join(debug_seen)}")
        return results

    # --- Day Action Handlers ---

    def _handle_jail(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.DAY:
            return "Error: You can only decide to jail someone during the day."
        if actor.role.name != RoleName.JAILOR:
            return "Error: You are not the Jailor."
        if actor.role.jailed_target:
            return "Error: You have already decided who to jail tonight."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target # Return error string from resolver

        if target == actor:
            return "Error: You cannot jail yourself."
        
        self.game.submit_day_action(actor, target)
        # This message is not printed to all, it's a confirmation for the agent
        return f"Success: You will jail {target.name} tonight."

    def _handle_reveal(self, actor: 'Player', content: str) -> str:
        # Content is ignored for reveal
        if self.game.time != Time.DAY:
            return "Error: You can only reveal during the day."
        if actor.role.name != RoleName.MAYOR:
            return "Error: You are not the Mayor."
        if actor.role.revealed:
            return "Error: You have already revealed."

        self.game.submit_day_action(actor)
        return "Success: You have revealed yourself as the Mayor!"

    # --- Night Action Handlers ---

    def _handle_shoot(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only shoot at night."
        if actor.role.name != RoleName.VIGILANTE:
            return "Error: Your role cannot shoot."
        
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        self.game.submit_night_action(actor, target)
        return f"Success: You will shoot {target.name} tonight."

    def _handle_protect(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only protect at night."
        if actor.role.name not in [RoleName.DOCTOR, RoleName.BODYGUARD, RoleName.CRUSADER, RoleName.GUARDIAN_ANGEL]:
             return "Error: Your role cannot protect."

        # Guardian Angel always protects their assigned target; content is ignored.
        if actor.role.name == RoleName.GUARDIAN_ANGEL:
            target = getattr(actor.role, 'protect_target', None)
            if not target:
                return "Error: No assigned target to guard."
        else:
            target = self._resolve_target(actor, content)
            if isinstance(target, str):
                return target
            
        self.game.submit_night_action(actor, target)
        print(f"[Debug] {actor.name} will protect {target.name}")
        return f"Success: You will protect {target.name} tonight."

    def _handle_investigate(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only investigate at night."
        if actor.role.name not in [RoleName.SHERIFF, RoleName.INVESTIGATOR, RoleName.CONSIGLIERE]:
             return "Error: Your role cannot investigate."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot target yourself."

        self.game.submit_night_action(actor, target)
        print(f"[Debug] {actor.name} will investigate {target.name}")
        return f"Success: You will investigate {target.name} tonight."

    def _handle_kill(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only kill at night."

        # Resolve target first so we can reference it in all branches below.
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot target yourself."

        if actor.role.name == RoleName.GODFATHER:
            mafioso = self.game.find_player_by_role(RoleName.MAFIOSO)
            if mafioso and mafioso.is_alive and not mafioso.is_jailed:
                self.game.submit_night_action(mafioso, target)
                print(f"[Debug] Godfather ordered Mafioso ({mafioso.name}) to kill {target.name}")
                return f"Success: You ordered the Mafioso to kill {target.name} tonight."
            # If no Mafioso is available, the Godfather performs the kill directly with BASIC attack.
            self.game.submit_night_action(actor, target)
            print(f"[Debug] Godfather personally will kill {target.name}")
            return f"Success: You will personally kill {target.name} tonight."

        # For all other roles, ensure they actually have killing power
        if actor.role.attack == Attack.NONE:
            return "Error: Your role cannot kill."

        self.game.submit_night_action(actor, target)
        print(f"[Debug] {actor.name} recorded kill on {target.name}")
        return f"Success: You will attempt to kill {target.name} tonight."

    def _handle_execute(self, actor: 'Player', content: str) -> str:
        """Night-time execute performed by a Jailor on their jailed target."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only execute at night."
        if actor.role.name != RoleName.JAILOR:
            return "Error: You are not the Jailor."

        target = actor.role.jailed_target
        if not target or not target.is_alive:
            return "Error: You have no living jailed target to execute."

        # Optional safety: if player provides a name, ensure it matches current jailed target
        if content:
            resolved = self._resolve_target(actor, content)
            if isinstance(resolved, str):
                return resolved
            if resolved != target:
                return f"Error: {resolved.name} is not your current jailed prisoner."

        # Submit execute as a night action (Jailor already registers unstoppable attack in role logic)
        self.game.submit_night_action(actor, target)
        return f"Success: You will execute {target.name} tonight."

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

    def _handle_nominate(self, actor: 'Player', content: str) -> str:
        from Simulation.enums import Phase as PhaseEnum
        if self.game.phase != PhaseEnum.NOMINATION:
            return "Error: You cannot nominate during this phase."
        if not content:
            return "Error: Please specify a target to nominate."
        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target
        if not self.game.day_phase_manager:
            return "Error: Nomination system not active."
        return self.game.day_phase_manager.add_nomination(actor, target)

    def _handle_vote(self, actor: 'Player', content: str) -> str:
        from Simulation.enums import Phase as PhaseEnum

        # Check for vote removal
        if content.strip().lower() == "remove":
            if self.game.phase == PhaseEnum.NOMINATION:
                # Remove nomination vote
                if not self.game.day_phase_manager:
                    return "Error: Nomination system not active."
                # Reset the player's nomination status
                if actor in self.game.day_phase_manager.player_has_nominated:
                    self.game.day_phase_manager.player_has_nominated.remove(actor)
                    # Remove from all nominations
                    for nominee, voters in self.game.day_phase_manager.nominations.items():
                        if actor in voters:
                            voters.remove(actor)
                    return "Success: You have removed your nomination vote."
                return "Error: You have not nominated anyone to remove."
            
            elif self.game.phase == PhaseEnum.JUDGEMENT:
                # Remove verdict vote
                if not self.game.day_phase_manager:
                    return "Error: Voting system not active."
                if actor in self.game.day_phase_manager.verdict_votes:
                    del self.game.day_phase_manager.verdict_votes[actor]
                    return "Success: You have removed your verdict vote."
                return "Error: You have not voted to remove."
            
            return "Error: Vote removal is not allowed in the current phase."

        if self.game.phase == PhaseEnum.NOMINATION:
            # Voting to nominate someone (<vote>Bob</vote>)
            target = self._resolve_target(actor, content)
            if isinstance(target, str):
                return target
            if not self.game.day_phase_manager:
                return "Error: Nomination system not active."
            return self.game.day_phase_manager.add_nomination(actor, target)

        if self.game.phase == PhaseEnum.JUDGEMENT:
            verdict = content.strip().upper()
            if verdict not in {"GUILTY", "INNOCENT", "ABSTAIN"}:
                return "Error: Vote must be GUILTY, INNOCENT, or ABSTAIN."
            if not self.game.day_phase_manager:
                return "Error: Voting system not active."
            return self.game.day_phase_manager.add_verdict(actor, verdict)

        return "Error: Voting is not allowed in the current phase."

    def _handle_distract(self, actor: 'Player', content: str) -> str:
        """Generic role‐block action used by Tavern Keeper/Escort (Town) and Bootlegger/Consort (Mafia)."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only distract at night."

        allowed_roles = {
            RoleName.TAVERN_KEEPER,
            RoleName.ESCORT,
            RoleName.BOOTLEGGER,
            RoleName.CONSORT,
        }
        if actor.role.name not in allowed_roles:
            return "Error: Your role cannot distract."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot target yourself."

        # Record the night action; role logic will handle the block effects.
        self.game.submit_night_action(actor, target)
        print(f"[Debug] {actor.name} will distract {target.name}")
        return f"Success: You will distract {target.name} tonight."

    def _handle_raise(self, actor: 'Player', content: str) -> str:
        """Retributionist ability: raise a dead Town corpse to use its ability on a target.
        Syntax: <raise>CorpseName,TargetName</raise>
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only raise corpses at night."
        if actor.role.name not in {RoleName.RETRIBUTIONIST, RoleName.NECROMANCER}:
            return "Error: Your role cannot raise corpses."

        # Expect two names separated by comma or semicolon
        if not content or ',' not in content:
            return "Error: Provide corpse and target as 'Corpse,Target'."
        corpse_name, target_name = [s.strip() for s in re.split(r'[;,]', content, maxsplit=1)]

        corpse = next((p for p in self.game.players if p.name.lower() == corpse_name.lower()), None)
        if not corpse or corpse.is_alive:
            return f"Error: No dead player named '{corpse_name}' found."

        target = self._resolve_target(actor, target_name)
        if isinstance(target, str):
            return target

        # Record visit for tracking
        actor.visit(corpse)

        # Submit special tuple to night actions
        self.game.submit_night_action(actor, (corpse, target))
        return f"Success: You will raise {corpse.name}'s corpse to act on {target.name} tonight."

    def _handle_control(self, actor: 'Player', content: str) -> str:
        """Witch/Coven Leader control ability.

        Syntax: <control>PuppetName,VictimName</control>
        The first player will be forced to act on the second player.
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only control at night."

        if actor.role.name not in [RoleName.WITCH, RoleName.COVEN_LEADER]:
            return "Error: Your role cannot control others."

        if not content or ',' not in content:
            return "Error: Provide puppet and victim as 'Puppet,Victim'."

        puppet_name, victim_name = [s.strip() for s in re.split(r'[;,]', content, maxsplit=1)]

        puppet = self._resolve_target(actor, puppet_name)
        if isinstance(puppet, str):
            return puppet

        victim = self._resolve_target(actor, victim_name)
        if isinstance(victim, str):
            return victim

        # Save special tuple (puppet, victim)
        self.game.submit_night_action(actor, (puppet, victim))
        return f"Success: You will control {puppet.name} to target {victim.name} tonight."

    # --- Veteran Alert ---
    def _handle_alert(self, actor: 'Player', content: str) -> str:
        """Veteran ability – go on alert by targeting self (no content needed)."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only alert at night."

        if actor.role.name != RoleName.VETERAN:
            return "Error: You are not the Veteran."

        # Optional: allow <alert/> or <alert>self</alert>
        if content and content.strip().lower() not in ["self", actor.name.lower()]:
            return "Error: Alert has no target – use <alert/> or <alert>self</alert>."

        # Submit self‐target so role logic handles alerts left.
        self.game.submit_night_action(actor, actor)
        return "Success: You will go on alert tonight."

    # --- Transporter ---
    def _handle_transport(self, actor: 'Player', content: str) -> str:
        """Transporter ability: swap two players.

        Syntax: <transport>PlayerA,PlayerB</transport>
        Either name may be 'self'.
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only transport at night."

        if actor.role.name != RoleName.TRANSPORTER:
            return "Error: You are not the Transporter."

        if not content or ',' not in content:
            return "Error: Provide two names separated by a comma: 'A,B'."

        name1, name2 = [s.strip() for s in re.split(r'[;,]', content, maxsplit=1)]

        p1 = actor if name1.lower() == 'self' else self._resolve_target(actor, name1)
        if isinstance(p1, str):
            return p1

        p2 = actor if name2.lower() == 'self' else self._resolve_target(actor, name2)
        if isinstance(p2, str):
            return p2

        if p1 == p2:
            return "Error: You must select two different players (they can include yourself)."

        # Record tuple for game processing
        self.game.submit_night_action(actor, (p1, p2))
        return f"Success: You will transport {p1.name} with {p2.name} tonight."

    # --- Spy bug ---
    def _handle_bug(self, actor: 'Player', content: str) -> str:
        """Spy ability to bug a player's house (passive for now)."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only bug at night."

        if actor.role.name != RoleName.SPY:
            return "Error: You are not the Spy."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        self.game.submit_night_action(actor, target)
        return f"Success: You will bug {target.name}'s house tonight."

    # --- Lookout Watch ---
    def _handle_watch(self, actor: 'Player', content: str) -> str:
        """Lookout ability: watch a player to see who visits them.

        Syntax: <watch>TargetName</watch> or <watch>self</watch>
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only watch at night."

        if actor.role.name != RoleName.LOOKOUT:
            return "Error: You are not the Lookout."

        if not content:
            return "Error: You must specify someone to watch (use 'self' to watch your own house)."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        # Record the night action
        self.game.submit_night_action(actor, target)
        return f"Success: You will watch {target.name} tonight."

    # --- Survivor Vest ---
    def _handle_vest(self, actor: 'Player', content: str) -> str:
        """Survivor ability: put on a bulletproof vest (self‐target only).

        Syntax: <vest/> or <vest>self</vest>
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only vest at night."

        if actor.role.name != RoleName.SURVIVOR:
            return "Error: You are not the Survivor."

        # Content, if provided, must indicate self.
        if content and content.strip().lower() not in ["self", actor.name.lower()]:
            return "Error: The vest ability only targets yourself – use <vest/> or <vest>self</vest>."

        # Submit self‐target to activate vest logic in Survivor.perform_night_action.
        self.game.submit_night_action(actor, actor)
        return "Success: You will wear a bulletproof vest tonight."

    # --- Amnesiac Remember ---
    def _handle_remember(self, actor: 'Player', content: str) -> str:
        """Amnesiac ability: remember the role of a dead player.

        Syntax: <remember>CorpseName</remember>
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only remember a role at night."

        if actor.role.name != RoleName.AMNESIAC:
            return "Error: You are not the Amnesiac."

        if not content:
            return "Error: Specify whose role to remember.";

        corpse = next((p for p in self.game.graveyard if p.name.lower() == content.strip().lower()), None)
        if not corpse:
            return f"Error: No dead player named '{content}' found in the graveyard.";

        # Cannot remember cleaned/stoned; simplified: check attribute flags
        if getattr(corpse, "was_stoned", False) or getattr(corpse, "was_cleaned", False):
            return "Error: You cannot remember a cleaned or stoned player.";

        # Record special night action as the corpse (player object) – role logic will handle validation.
        self.game.submit_night_action(actor, corpse)
        return f"Success: You will remember that you were a {corpse.role.name.value}."

    # --- Tracker ---
    def _handle_track(self, actor: 'Player', content: str) -> str:
        """Tracker ability: follow a player to see who they visit.

        Syntax: <track>TargetName</track>
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only track at night."

        if actor.role.name != RoleName.TRACKER:
            return "Error: You are not the Tracker."

        if not content:
            return "Error: You must specify someone to track."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot track yourself."

        self.game.submit_night_action(actor, target)
        return f"Success: You will track {target.name} tonight."

    # --- Psychic Vision ---
    def _handle_vision(self, actor: 'Player', content: str) -> str:
        """Psychic ability – trigger nightly vision (no target)."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only use your vision at night."

        if actor.role.name != RoleName.PSYCHIC:
            return "Error: You are not the Psychic."

        # Submit with None target; role logic handles vision.
        self.game.submit_night_action(actor, None)
        return "Success: You focus on your crystal ball tonight."

    # --- Hex Master ---
    def _handle_hex(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only hex at night."

        if actor.role.name != RoleName.HEX_MASTER:
            return "Error: You are not the Hex Master."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot target yourself."

        self.game.submit_night_action(actor, target)
        return f"Success: You will hex {target.name} tonight."

    # --- Poisoner ---
    def _handle_poison(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only poison at night."

        if actor.role.name != RoleName.POISONER:
            return "Error: You are not the Poisoner."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot target yourself."

        self.game.submit_night_action(actor, target)
        return f"Success: You will poison {target.name} tonight."

    # --- Medusa Stone Gaze / Attack ---
    def _handle_stone(self, actor: 'Player', content: str) -> str:
        if self.game.time != Time.NIGHT:
            return "Error: You can only use stone gaze at night."

        if actor.role.name != RoleName.MEDUSA:
            return "Error: You are not Medusa."

        # Empty content or 'self' means gaze at home
        if not content or content.strip().lower() in ["self", actor.name.lower()]:
            self.game.submit_night_action(actor, actor)  # treat as self-target
            return "Success: You will use stone gaze on visitors tonight."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            self.game.submit_night_action(actor, actor)
            return "Success: You will use stone gaze on visitors tonight."

        # Attack mode with Necronomicon
        self.game.submit_night_action(actor, target)
        return f"Success: You will attempt to petrify {target.name} tonight."

    # --- Pirate ---
    def _handle_plunder(self, actor: 'Player', content: str) -> str:
        """Pirate ability – select a duel target and optionally a weapon.

        Syntax:
            <plunder>TargetName</plunder>               – weapon chosen at random
            <plunder>TargetName,Weapon</plunder>        – specify weapon (rapier, scimitar, pistol)

        Tag name is case-insensitive; weapon name is also case-insensitive.
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only plunder at night."
        if actor.role.name != RoleName.PIRATE:
            return "Error: You are not the Pirate."

        if not content:
            return "Error: You must specify a target (and optionally a weapon)."

        # Split by comma/semicolon
        parts = [p.strip() for p in re.split(r'[;,]', content) if p.strip()]
        target_name = parts[0] if parts else ""
        weapon_name = parts[1] if len(parts) > 1 else None

        target = self._resolve_target(actor, target_name)
        if isinstance(target, str):
            return target
        if target == actor:
            return "Error: You cannot target yourself."

        # Validate weapon (optional)
        chosen_move = None
        if weapon_name:
            weapon_lc = weapon_name.lower()
            mapping = {
                "rapier": DuelMove.RAPIER,
                "scimitar": DuelMove.SCIMITAR,
                "pistol": DuelMove.PISTOL,
            }
            if weapon_lc not in mapping:
                return "Error: Weapon must be Rapier, Scimitar, or Pistol."
            chosen_move = mapping[weapon_lc]
            actor.role.chosen_move = chosen_move  # store for night resolution
        else:
            actor.role.chosen_move = None  # random later

        # Submit night action – we only need the target; weapon stored on role
        self.game.submit_night_action(actor, target)
        if chosen_move:
            return f"Success: You will plunder {target.name} tonight with your {chosen_move.value}."
        else:
            return f"Success: You will plunder {target.name} tonight with a random weapon."

    def _handle_blackmail(self, actor: 'Player', content: str) -> str:
        """Blackmailer ability: prevent a player from speaking the following day."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only blackmail at night."

        if actor.role.name != RoleName.BLACKMAILER:
            return "Error: You are not the Blackmailer."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot blackmail yourself."

        self.game.submit_night_action(actor, target)
        print(f"[Debug] {actor.name} will blackmail {target.name}")
        return f"Success: You will blackmail {target.name} tonight."

    def _handle_clean(self, actor: 'Player', content: str) -> str:
        """Janitor ability: attempt to hide a player's role/will if they die tonight."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only clean at night."

        if actor.role.name != RoleName.JANITOR:
            return "Error: You are not the Janitor."

        if actor.role.charges <= 0:
            return "Error: You have no cleanings left."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot clean yourself."

        self.game.submit_night_action(actor, target)
        print(f"[Debug] {actor.name} will attempt to clean {target.name}")
        return f"Success: You will attempt to clean {target.name} tonight."

    def _handle_disguise(self, actor: 'Player', content: str) -> str:
        """Disguiser ability: disguise yourself as another (non-Mafia) player."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only disguise at night."

        if actor.role.name != RoleName.DISGUISER:
            return "Error: You are not the Disguiser."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target.role.faction == Faction.MAFIA:
            return "Error: You cannot disguise as a Mafia member."

        if target == actor:
            return "Error: You cannot disguise as yourself."

        self.game.submit_night_action(actor, target)
        print(f"[Debug] {actor.name} will disguise as {target.name}")
        return f"Success: You will disguise yourself as {target.name} tonight."

    # --- Plaguebearer Infection ---
    def _handle_infect(self, actor: 'Player', content: str) -> str:
        """Plaguebearer ability: visit a player and infect them (and anyone who visits either of you)."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only infect at night."

        if actor.role.name != RoleName.PLAGUEBEARER:
            return "Error: You are not the Plaguebearer."

        # If the agent provided an empty tag like <infect/>, treat it as staying home.
        if not content.strip():
            target = actor  # Infect visitors to yourself only.
        else:
            target = self._resolve_target(actor, content)
            if isinstance(target, str):
                return target

        # Submit infection action
        self.game.submit_night_action(actor, target)
        if target == actor:
            return "Success: You will stay home and spread disease to any visitors tonight."
        else:
            return f"Success: You will infect {target.name} tonight."

    # --- Jester Haunt ---
    def _handle_haunt(self, actor: 'Player', content: str) -> str:
        """Jester selects a haunt target on the night after being lynched."""
        if self.game.time != Time.NIGHT:
            return "Error: Haunting can only be performed at night."

        if actor.role.name != RoleName.JESTER:
            return "Error: Only a Jester can haunt."

        if actor.is_alive:
            return "Error: You are still alive and cannot haunt anyone."

        # Ensure jester was actually lynched and has candidates
        candidates = getattr(actor, "haunt_candidates", None)
        if not candidates:
            return "Error: No valid haunt candidates available."

        # Empty content ⇒ random choice will happen automatically by Game
        if not content.strip():
            actor.haunt_target = None  # explicit none, random later
            return "Success: You have left your haunting to fate."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target not in candidates:
            return "Error: You may only haunt someone who voted against you."

        actor.haunt_target = target
        return f"Success: You will haunt {target.name} tonight."

    # --- Medium Seance ---
    def _handle_seance(self, actor: 'Player', content: str) -> str:
        """Medium ability: create private chat with one living player once (can be used alive or dead).

        Syntax: <seance>PlayerName</seance>
        """
        if self.game.time != Time.NIGHT:
            return "Error: Séance can only be performed at night."

        if actor.role.name != RoleName.MEDIUM:
            return "Error: You are not the Medium."

        if actor.role.seances <= 0:
            return "Error: You have already used your séance."

        if not content.strip():
            return "Error: You must specify a living player to contact."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if not target.is_alive:
            return "Error: You may only seance a living player."

        if actor == target:
            return "Error: You cannot seance yourself."

        # Use the seance ability through role's method
        result = actor.role.seance(actor, target, self.game)
        if "established a seance" in result:
            # Also submit to game for tracking
            self.game.submit_night_action(actor, target)
        
        return result

    # --- Forger ---
    def _handle_forge(self, actor: 'Player', content: str) -> str:
        """Forger ability: falsify a player's last will if they die tonight.

        Syntax: <forge>TargetName</forge>
        (Custom wills not implemented – simulator just hides real will.)
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only forge at night."

        if actor.role.name != RoleName.FORGER:
            return "Error: You are not the Forger."

        if actor.role.charges <= 0:
            return "Error: You have no forging supplies left."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            return "Error: You cannot forge your own will."

        self.game.submit_night_action(actor, target)
        return f"Success: You will forge {target.name}'s last will tonight."

    # --- Trapper ---
    def _handle_trap(self, actor: 'Player', content: str) -> str:
        """Trapper ability: set or remove a trap.

        Syntax:
          <trap>TargetName</trap> – begin building trap at target's house
          <trap/> or <trap>self</trap> – dismantle current trap
        """
        if self.game.time != Time.NIGHT:
            return "Error: You can only set/remove traps at night.";

        if actor.role.name != RoleName.TRAPPER:
            return "Error: You are not the Trapper.";

        # Self target or empty ⇒ dismantle
        if not content or content.strip().lower() in ["self", actor.name.lower()]:
            self.game.submit_night_action(actor, actor)
            return "Success: You will dismantle your trap tonight.";

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        if target == actor:
            # already handled above
            target = actor

        self.game.submit_night_action(actor, target)
        return f"Success: You will start building a trap at {target.name}'s house tonight."

    def _handle_frame(self, actor: 'Player', content: str) -> str:
        """Framer ability: choose one target to frame for the night."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only frame at night."
        if actor.role.name != RoleName.FRAMER:
            return "Error: Your role cannot frame."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        # Allow framing self (rare, but possible)
        self.game.submit_night_action(actor, target)
        return f"Success: You will frame {('yourself' if target==actor else target.name)} tonight."

    # Support both British and US spelling
    def _handle_hypnotise(self, actor: 'Player', content: str) -> str:
        return self._handle_hypnotize(actor, content)

    def _handle_hypnotize(self, actor: 'Player', content: str) -> str:  # alias
        if self.game.time != Time.NIGHT:
            return "Error: You can only hypnotize at night."
        if actor.role.name != RoleName.HYPNOTIST:
            return "Error: Your role cannot hypnotize."

        target = self._resolve_target(actor, content)
        if isinstance(target, str):
            return target

        self.game.submit_night_action(actor, target)
        return f"Success: You will hypnotize {target.name} tonight."

    # --- Skip/Pass Aliases ---
    def _handle_skip(self, actor: 'Player', content: str) -> str:
        """Skip action - alias for not performing any night action."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only skip during the night."
        
        # Submit None as target to indicate no action
        self.game.submit_night_action(actor, None)
        return "Success: You will skip your night action."

    def _handle_pass(self, actor: 'Player', content: str) -> str:
        """Pass action - alias for not performing any night action."""
        if self.game.time != Time.NIGHT:
            return "Error: You can only pass during the night."
        
        # Submit None as target to indicate no action
        self.game.submit_night_action(actor, None)
        return "Success: You will pass your night action."

    def _handle_wait(self, actor: 'Player', content: str) -> str:
        """Wait action - defer speaking to observe ongoing discussion."""
        # Terminal action - just observes, doesn't submit anything to game state
        # Works in all phases since there are always communication channels available
        return "You choose to wait and observe the ongoing discussion."

    def _handle_notebook(self, actor: 'Player', content: str) -> str:
        """Write to notebook - terminal action that ends the turn."""
        if not actor.is_alive:
            return "Error: You cannot use notebook while dead."
        
        # TODO: RESEARCH METRICS - Track notebook usage
        actor.research_metrics['times_used_notebook'] += 1
        
        # Use the notebook tool directly
        from Simulation.tools.registry import _exec_notebook
        return _exec_notebook(content, game=self.game, player=actor) 

    def _handle_speak(self, actor: 'Player', content: str) -> str:
        """Handle the <speak> interaction: send a public message to chat."""
        if not content or not content.strip():
            return "Error: No message provided to speak."
        # Add the message to the public chat (assuming game has a chat manager)
        if hasattr(self.game, 'chat') and hasattr(self.game.chat, 'send_speak'):
            self.game.chat.send_speak(actor, content.strip())
        # Confirmation is not needed as an observation, but return for logging
        return f"[Your message has been sent to the public channel.]"

    def _handle_whisper(self, actor: 'Player', content: str) -> str:
        """Handle the <whisper> interaction: send a private message to another player."""
        # Expecting format: <whisper target="PlayerName">message</whisper>
        import re
        match = re.match(r'\s*target\s*=\s*"([^"]+)"\s*>(.*)', content, re.DOTALL)
        if not match:
            return "Error: Invalid whisper format. Use <whisper target=\"PlayerName\">message</whisper>"
        target_name, message = match.groups()
        target_name = target_name.strip()
        message = message.strip()
        if not target_name or not message:
            return "Error: Whisper must specify a target and a message."
        # Find the target player
        target_player = None
        for p in self.game.players:
            if p.name.lower() == target_name.lower() and p.is_alive:
                target_player = p
                break
        if not target_player:
            return f"Error: No living player named '{target_name}' found."
        # Add the message to the private chat (assuming game has a chat manager)
        if hasattr(self.game, 'chat') and hasattr(self.game.chat, 'send_whisper'):
            self.game.chat.send_whisper(actor, target_player, message)
        # Confirmation is not needed as an observation, but return for logging
        return f"[Your message has been privately delivered to {target_player.name}.]" 

    def _handle_roles(self, actor: 'Player', content: str) -> str:
        """Return detailed information about a role from roles.json."""
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
        # Try to find the role (case-insensitive)
        for key, value in roles_data.items():
            if key.lower() == role_name.lower():
                # Return a formatted string with the role details
                details = f"Role: {key}\n"
                for k, v in value.items():
                    details += f"{k}: {v}\n"
                return details.strip()
        return f"Error: Role '{role_name}' not found." 