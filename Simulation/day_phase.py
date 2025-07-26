"""Simulation/day_phase.py

Day Phase Logic - Agent-Driven
------------------------------
This module manages the state of the day phase (nominations, trials,
verdicts) but is driven by an external controller and the InteractionHandler.
It no longer contains any random simulation logic.
"""

from typing import List, Dict, Optional

#Forward reference imports
from .player import Player
from .enums import RoleName

class DayPhase:
    """Manages the state of nominations, trials, verdicts, and last words."""

    def __init__(self, game: 'Game'):
        self.game = game
        self.alive_players: List[Player] = [p for p in game.players if p.is_alive]
        self.on_trial: Optional[Player] = None
        self.nominations: Dict[Player, set[Player]] = {}
        self.verdict_votes: Dict[Player, str] = {}
        self.player_has_nominated: set[Player] = set()
        import math
        self.nomination_threshold: int = max(1, math.ceil(len(self.alive_players) / 2))
        self.trials_remaining: int = 3
        # --- Last Words state ---
        self.last_words_player: Optional[Player] = None
        self.last_words_given: bool = False
        self.last_words_max_tokens: int = 64  # Default, can be set from config
        # --- Judgement phase state ---
        self.judgement_wait_streak: int = 0
        self.judgement_last_action: str = ""

    # ------------------------------------------------------------------
    # Public methods for InteractionHandler
    # ------------------------------------------------------------------

    def add_nomination(self, nominator: Player, target: Player) -> str:
        """Records a nomination from one player to another."""
        if nominator in self.player_has_nominated:
            return f"Error: You have already nominated someone today."
        if nominator == target:
            return f"Error: You cannot nominate yourself."
        if not target.is_alive:
            return f"Error: {target.name} is not alive."

        if target not in self.nominations:
            self.nominations[target] = set()
        
        self.nominations[target].add(nominator)
        self.player_has_nominated.add(nominator)
        
        # TODO: RESEARCH METRICS - Track nominations for research
        target.research_metrics['times_nominated'] += 1
        
        print(f"{nominator.name} nominates {target.name} (Total: {len(self.nominations[target])}/{self.nomination_threshold})")
        
        if len(self.nominations[target]) >= self.nomination_threshold:
            print(f"{target.name} has received enough nominations and is put on trial!")
            self.on_trial = target
            from .enums import Phase as PhaseEnum
            self.game.phase = PhaseEnum.DEFENSE
        
        return f"Success: You nominated {target.name}."

    def add_verdict(self, voter: Player, verdict: str) -> str:
        """Records a guilty/innocent/abstain vote during a trial."""
        if not self.on_trial:
            return "Error: There is no one on trial."
        if voter == self.on_trial:
            return "Error: You cannot vote on your own trial."
        if voter in self.verdict_votes:
            return "Error: You have already voted."

        self.verdict_votes[voter] = verdict
        
        # TODO: RESEARCH METRICS - Track voting patterns for research
        if verdict == "GUILTY":
            voter.research_metrics['times_voted_guilty'] += 1
        elif verdict == "INNOCENT":
            voter.research_metrics['times_voted_innocent'] += 1
        else:  # ABSTAIN
            voter.research_metrics['times_voted_abstain'] += 1
        
        return f"Success: You voted {verdict}."

    # ------------------------------------------------------------------
    # Public methods for the main game loop controller
    # ------------------------------------------------------------------

    def check_for_trial(self) -> Optional[Player]:
        """Called after nomination phase to see if a trial should start."""
        return self.on_trial

    def tally_verdict(self):
        """Called after verdict voting to determine the outcome."""
        if not self.on_trial:
            return

        guilty = innocent = abstain = 0
        
        # Add the defendant's vote as an abstain
        defendant_voters = [p for p in self.alive_players if p != self.on_trial]
        
        for voter in defendant_voters:
            vote = self.verdict_votes.get(voter, "ABSTAIN") # Default to abstain if no vote cast
            if vote == "GUILTY":
                guilty += voter.vote_weight
            elif vote == "INNOCENT":
                innocent += voter.vote_weight
            else:
                abstain += voter.vote_weight

        print("\n— Verdict —")
        from .enums import Phase as PhaseEnum
        if guilty > innocent:
            # Announce verdict and transition to LAST_WORDS phase
            self.game.chat.add_environment_message(f"The town has decided to execute {self.on_trial.name} with a vote of {guilty} to {innocent}.")
            self.on_trial.research_metrics['times_lynched'] += 1
            
            # Actually kill the player
            self._execute_player(self.on_trial)
            
            self.last_words_player = self.on_trial
            self.game.phase = PhaseEnum.LAST_WORDS
            self.game.chat.add_environment_message(f"Do you have any last words, {self.on_trial.name}?")

        else:
            # Announce innocent verdict and continue the day
            self.game.chat.add_environment_message(f"The town has found {self.on_trial.name} INNOCENT. (G:{guilty} / I:{innocent} / A:{abstain})")
            self.on_trial.research_metrics['times_defended_successfully'] += 1
            
            self.trials_remaining = max(0, self.trials_remaining - 1)
            self.on_trial = None
            
            if self.trials_remaining == 0:
                self.game.phase = PhaseEnum.PRE_NIGHT
            else:
                # Reset for next trial
                self.nominations.clear()
                self.verdict_votes.clear()
                self.player_has_nominated.clear()
                self.game.phase = PhaseEnum.NOMINATION

    # ------------------------------------------------------------------
    # Internal Mechanics
    # ------------------------------------------------------------------

    def _finalize_execution(self, player: Player):
        """Finalizes the execution after last words are given."""
        player.is_alive = False
        player.was_lynched = True
        
        # Mark that this was a lynch (no specific killer)
        player.killed_by = None  # Town collectively killed them
        player.killer_death_note = ""  # No death note for lynching
        
        self.game.graveyard.append(player)
        
        # Move lynched player to dead chat channel
        from .chat import ChatChannelType
        # Remove from all living player channels
        for channel in [ChatChannelType.DAY_PUBLIC, ChatChannelType.MAFIA_NIGHT, 
                      ChatChannelType.COVEN_NIGHT, ChatChannelType.VAMPIRE_NIGHT, ChatChannelType.JAILED]:
            self.game.chat.remove_player_from_channel(player, channel)
        # Move to dead channel
        self.game.chat.move_player_to_channel(player, ChatChannelType.DEAD, write=True, read=True)

        # Check if any Executioner achieves their win (or converts) due to this lynch.
        # The Game routine handles both win declaration and transformation into Jester
        # when their target dies by non-lynch causes.
        # Passing a single-element list keeps the signature consistent with night handling.
        if hasattr(self.game, "_check_executioners"):
            self.game._check_executioners([player])

        #Special case: Jester wins upon being lynched
        if player.role.name == RoleName.JESTER:
            self.game.winners.append(player)
            if hasattr(player.role, "on_lynch"):
                player.role.on_lynch(self.game)

            # Build list of guilty voters; if none, fall back to abstain voters
            guilty_voters = [v for v, verdict in self.verdict_votes.items() if verdict == "GUILTY" and v.is_alive]
            abstain_voters = [v for v, verdict in self.verdict_votes.items() if verdict == "ABSTAIN" and v.is_alive]
            player.haunt_candidates = guilty_voters if guilty_voters else abstain_voters

    def handle_last_words(self, actor: Player, content: str):
        """Handles the last words statement, finalizes execution, and transitions phase."""
        if self.game.phase.name != "LAST_WORDS":
            return
        if actor != self.last_words_player:
            return
        if self.last_words_given:
            return

        self.last_words_given = True
        
        # Truncate content if it exceeds the token limit
        tokens = content.split()
        if len(tokens) > self.last_words_max_tokens:
            content = " ".join(tokens[:self.last_words_max_tokens])
            self.game.chat.add_environment_message(f"({actor.name}'s statement was truncated due to length.)")

        # Announce the last words
        self.game.chat.add_environment_message(f"{actor.name}: \"{content}\"")
        self.game.chat.add_environment_message(f"May God have mercy on your soul, {actor.name}.")

        # Finalize the execution process
        self._finalize_execution(actor)

        # Reveal will and role
        self._reveal_will_and_role(actor)

        # End the phase and clean up
        self._end_last_words()

    def _end_last_words(self):
        """Ends the LAST_WORDS phase and transitions to PRE_NIGHT."""
        from .enums import Phase as PhaseEnum
        self.last_words_player = None
        self.last_words_given = False
        self.on_trial = None # Clear the player from trial
        
        self.trials_remaining = max(0, self.trials_remaining - 1)
        if self.trials_remaining == 0:
            self.game.phase = PhaseEnum.PRE_NIGHT
        else:
            # This case should ideally not be hit if a lynch happens,
            # but as a fallback, we move to the next logical step.
            self.game.phase = PhaseEnum.NOMINATION
        
        print("Exiting LAST_WORDS phase. Moving to PRE_NIGHT.")

    def _reveal_will_and_role(self, player: Player):
        """Reveals the executed player's will and role to the town."""
        self.game.chat.add_environment_message(f"We found a will next to their body.")
        if player.last_will_bloodied:
            self.game.chat.add_environment_message("Their last will was too bloody to read.")
        elif player.last_will:
            self.game.chat.add_environment_message(player.last_will)
        else:
            self.game.chat.add_environment_message("They left no last words.")
            
        self.game.chat.add_environment_message(f"Their role was {player.role.name.value}.") 

    # Add this method to be called after every agent action during DEFENSE
    def handle_defense_action(self, actor: Player, action_tag: str):
        """If the accused uses <speak> or <wait/>, immediately move to Judgement."""
        from .enums import Phase as PhaseEnum
        if self.game.phase == PhaseEnum.DEFENSE and actor == self.on_trial:
            if action_tag in {"speak", "wait"}:
                self.game.phase = PhaseEnum.JUDGEMENT
                self.judgement_wait_streak = 0
                self.judgement_last_action = ""

    # Add this method to be called after every agent action during JUDGEMENT
    def handle_judgement_action(self, actor: Player, action_tag: str):
        """Track <wait/> streak and end phase if all votes in and two consecutive <wait/>s."""
        from .enums import Phase as PhaseEnum
        if self.game.phase == PhaseEnum.JUDGEMENT:
            # Allow vote changes, so don't block on first vote
            if action_tag == "wait":
                if self.judgement_last_action == "wait":
                    self.judgement_wait_streak += 1
                else:
                    self.judgement_wait_streak = 1
                self.judgement_last_action = "wait"
            else:
                self.judgement_wait_streak = 0
                self.judgement_last_action = action_tag
            # Check if all votes are in
            alive_voters = [p for p in self.alive_players if p != self.on_trial]
            all_voted = all(p in self.verdict_votes for p in alive_voters)
            if all_voted and self.judgement_wait_streak >= 2:
                self.tally_verdict()

    # Add this method to be called after every agent action during LAST_WORDS
    def handle_last_words_action(self, actor: Player, action_tag: str):
        """If condemned uses any terminal action, move to Pre-Night."""
        from .enums import Phase as PhaseEnum
        if self.game.phase == PhaseEnum.LAST_WORDS and actor == self.last_words_player:
            if action_tag in {"speak", "wait"}:
                self.last_words_given = True
                self._finalize_execution(actor)
                self._reveal_will_and_role(actor)
                self._end_last_words() 

    def _execute_player(self, player):
        """Execute a player (lynch them)."""
        if not player.is_alive:
            return
            
        print(f"EXECUTING {player.name} by lynch!")
        
        # Mark player as dead
        player.is_alive = False
        player.was_lynched = True
        player.death_cause = "lynched"
        
        # Mark that this was a lynch (no specific killer)
        player.killed_by = None
        player.killer_death_note = ""  # No death note for lynching
        
        # Add to graveyard
        self.game.graveyard.append(player)
        
        # Note: Chat channel management is handled elsewhere
        # if hasattr(self.game, 'chat') and self.game.chat:
        #     self.game.chat.move_player_to_dead_chat(player)
        
        # Check if any Executioner achieves their win (or converts) due to this lynch.
        # Note: Executioner conversion happens in game._check_executioners()
        # when their target dies by non-lynch causes.
        
        #Special case: Jester wins upon being lynched
        if player.role.name == RoleName.JESTER:
            self.game.winners.append(player)
            if hasattr(player.role, "on_lynch"):
                player.role.on_lynch(self.game)

            # Build list of guilty voters; if none, fall back to abstain voters
            guilty_voters = [v for v, verdict in self.verdict_votes.items() if verdict == "GUILTY" and v.is_alive]
            abstain_voters = [v for v, verdict in self.verdict_votes.items() if verdict == "ABSTAIN" and v.is_alive]
            player.haunt_candidates = guilty_voters if guilty_voters else abstain_voters 