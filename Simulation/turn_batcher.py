"""
Turn-based batcher for concurrent ToSSim games.

This module manages multiple ToSSim games running concurrently and provides
batched training data by selecting active seats in a round-robin fashion.
It handles action application, observation generation, and game state management.

Used by Dr GRPO training and potentially other multi-game scenarios.
"""

from typing import List, Tuple, Dict, Any, Optional, TYPE_CHECKING
import random
from dataclasses import dataclass

from .game import Game
from .config import GameConfiguration
from .player import Player
from .roles import Role, create_role_by_name
from .enums import RoleName, Time, Phase
from .interaction_handler import InteractionHandler
from .grammar import validate_action, get_action_reward
from .prompt_builder import build_training_prompt
from .errors import ErrorCode, format_error, format_success

if TYPE_CHECKING:
    pass


@dataclass
class BatchEntry:
    """Single entry in a training batch."""
    game: Game
    player: Player
    prompt: str
    game_id: int
    player_id: str


class TurnBatcher:
    """
    Manages multiple concurrent ToSSim games for turn-based training.
    
    Provides batched prompts and handles action application with proper
    validation, error handling, and observation generation.
    """
    
    def __init__(self, num_games: int = 30, active_seats_per_game: int = 3):
        """
        Initialize the turn batcher.
        
        Args:
            num_games: Number of concurrent games to run
            active_seats_per_game: Number of active players per game per batch
        """
        self.num_games = num_games
        self.active_seats_per_game = active_seats_per_game
        
        # Game management
        self.games: List[Game] = []
        self.game_configs: List[GameConfiguration] = []
        
        # Round-robin seat selection
        self.seat_selectors: List[int] = [0] * num_games
        
        # Initialize games
        self._initialize_games()
    
    def _initialize_games(self):
        """Initialize all concurrent games."""
        
        for game_id in range(self.num_games):
            # Create game configuration
            config = GameConfiguration()
            self.game_configs.append(config)
            
            # Create players with diverse roles
            players = self._create_players_for_game(game_id)
            
            # Create and initialize game
            game = Game(config, players)
            self._setup_game_state(game)
            
            self.games.append(game)
    
    def _create_players_for_game(self, game_id: int) -> List[Player]:
        """Create a diverse set of players for a game."""
        
        # Standard Town of Salem role list (simplified)
        role_list = [
            RoleName.SHERIFF, RoleName.DOCTOR, RoleName.INVESTIGATOR,
            RoleName.BODYGUARD, RoleName.VIGILANTE, RoleName.VETERAN,
            RoleName.MAYOR, RoleName.MEDIUM, RoleName.RETRIBUTIONIST,
            RoleName.TRANSPORTER, RoleName.JAILOR, RoleName.LOOKOUT,
            RoleName.GODFATHER, RoleName.MAFIOSO, RoleName.CONSORT,
        ]
        
        # Shuffle for variety
        random.shuffle(role_list)
        
        players = []
        for i, role_name in enumerate(role_list):
            player_name = f"Player_{game_id}_{i+1}"
            
            # Create role instance
            try:
                role = create_role_by_name(role_name)
            except Exception as e:
                # Fallback to a basic role if creation fails
                # Log the error for debugging
                print(f"Warning: Failed to create role {role_name.name if isinstance(role_name, RoleName) else role_name}: {e}. Falling back to default role.")
                role = Role()
                # Ensure role.name is always a RoleName Enum member
                if isinstance(role_name, RoleName):
                    role.name = role_name
                else:
                    # Assign a default valid RoleName if conversion fails or input is not an enum
                    role.name = RoleName.INVESTIGATOR # Or another suitable default
                # Assign default faction and alignment for the fallback role
                role.faction = get_role_faction(role.name)
                role.alignment = get_role_alignment(role.name)
            
            player = Player(player_name, role)
            players.append(player)
        
        return players
    
    def _setup_game_state(self, game: Game):
        """Setup initial game state for training."""
        
        # Set to day phase for most training scenarios
        game.time = Time.DAY
        game.phase = Phase.DISCUSSION
        game.day = 1
        
        # Initialize graveyard
        if not hasattr(game, 'graveyard'):
            game.graveyard = []
        
        # Randomly kill 1-3 players to create more interesting scenarios
        if random.random() < 0.7:  # 70% chance of having some deaths
            num_deaths = random.randint(1, 3)
            alive_players = [p for p in game.players if p.is_alive]
            
            if len(alive_players) > num_deaths + 5:  # Keep at least 5 alive
                victims = random.sample(alive_players, num_deaths)
                for victim in victims:
                    victim.is_alive = False
                    victim.death_cause = random.choice(["killed", "lynched", "shot"])
                    game.graveyard.append(victim)
        
        # Randomly advance to different phases for variety
        if random.random() < 0.3:  # 30% chance of different phase
            game.phase = random.choice([Phase.NOMINATION, Phase.DEFENSE, Phase.JUDGEMENT])
    
    def next_batch(self) -> Tuple[List[str], List[Tuple[Game, Player]]]:
        """
        Get the next batch of prompts and metadata.
        
        Returns:
            (prompts, metadata) where metadata is list of (game, player) tuples
        """
        
        batch_entries = []
        
        for game_id, game in enumerate(self.games):
            # Reset completed games
            if self._is_game_completed(game):
                self._reset_game(game_id)
                game = self.games[game_id]
            
            # Get alive players
            alive_players = [p for p in game.players if p.is_alive]
            if len(alive_players) < self.active_seats_per_game:
                continue
            
            # Round-robin selection of active seats
            for _ in range(self.active_seats_per_game):
                if self.seat_selectors[game_id] >= len(alive_players):
                    self.seat_selectors[game_id] = 0
                
                player = alive_players[self.seat_selectors[game_id]]
                
                # Build prompt for this player
                prompt = build_training_prompt(game, player)
                
                batch_entries.append(BatchEntry(
                    game=game,
                    player=player,
                    prompt=prompt,
                    game_id=game_id,
                    player_id=player.name
                ))
                
                self.seat_selectors[game_id] += 1
        
        # Extract prompts and metadata
        prompts = [entry.prompt for entry in batch_entries]
        metadata = [(entry.game, entry.player) for entry in batch_entries]
        
        return prompts, metadata
    
    def apply_actions(self, metadata: List[Tuple[Game, Player]], completions: List[str]) -> List[Tuple[float, str]]:
        """
        Apply agent actions to games and return rewards with observations.
        
        Args:
            metadata: List of (game, player) tuples from next_batch
            completions: List of agent completions
            
        Returns:
            List of (reward, observation) tuples
        """
        
        results = []
        
        for (game, player), completion in zip(metadata, completions):
            reward, observation = self._apply_single_action(game, player, completion)
            results.append((reward, observation))
        
        return results
    
    def _apply_single_action(self, game: Game, player: Player, completion: str) -> Tuple[float, str]:
        """
        Apply a single action and return reward + observation.
        
        Args:
            game: Game instance
            player: Player taking action
            completion: Agent's completion text
            
        Returns:
            (reward, observation) tuple
        """
        
        # Step 1: Validate action using the shared validation system
        status, error_code, detail = validate_action(completion, game, player)
        reward = get_action_reward(status, error_code)
        
        # Step 2: Handle based on validation result
        if status == "MALFORMED":
            # Malformed XML - return error observation
            observation = format_error(error_code, detail)
            return reward, observation
        
        elif status == "ILLEGAL":
            # Valid XML but phase-illegal - return error but preserve for research
            observation = format_error(error_code, detail)
            return reward, observation
        
        else:  # status == "OK"
            # Valid and legal - execute action via InteractionHandler
            try:
                handler = InteractionHandler(game)
                results = handler.parse_and_execute(player, completion)
                
                if results:
                    # Use the first result as the observation
                    observation = format_success(results[0])
                else:
                    observation = format_success("Action completed successfully.")
                
                return reward, observation
                
            except Exception as e:
                # Execution failed
                observation = format_error(ErrorCode.EXECUTION_FAILED, str(e))
                return 0.0, observation  # Error in execution gets 0 reward
    
    def _is_game_completed(self, game: Game) -> bool:
        """Check if a game should be reset."""
        
        # Reset if too few players alive
        alive_count = len([p for p in game.players if p.is_alive])
        if alive_count < 4:
            return True
        
        # Reset if game has been running too long (for training variety)
        if hasattr(game, 'day') and game.day > 5:
            return True
        
        # Check for actual game end conditions
        if hasattr(game, 'game_is_over') and game.game_is_over():
            return True
        
        return False
    
    def _reset_game(self, game_id: int):
        """Reset a completed game."""
        
        # Create new players
        players = self._create_players_for_game(game_id)
        
        # Create new game instance
        config = self.game_configs[game_id]
        new_game = Game(config, players)
        self._setup_game_state(new_game)
        
        # Replace the old game
        self.games[game_id] = new_game
        self.seat_selectors[game_id] = 0
    
    def get_active_game_count(self) -> int:
        """Get number of currently active games."""
        return len([game for game in self.games if not self._is_game_completed(game)])
    
    def get_batch_stats(self) -> Dict[str, Any]:
        """Get statistics about the current batch state."""
        
        total_alive = sum(len([p for p in game.players if p.is_alive]) for game in self.games)
        total_dead = sum(len(getattr(game, 'graveyard', [])) for game in self.games)
        
        # Phase distribution
        phase_counts = {}
        for game in self.games:
            phase_key = f"{game.time.name}_{game.phase.name}" if hasattr(game, 'time') and hasattr(game, 'phase') else "UNKNOWN"
            phase_counts[phase_key] = phase_counts.get(phase_key, 0) + 1
        
        return {
            "total_games": self.num_games,
            "active_games": self.get_active_game_count(),
            "total_alive_players": total_alive,
            "total_dead_players": total_dead,
            "avg_alive_per_game": total_alive / self.num_games if self.num_games > 0 else 0,
            "phase_distribution": phase_counts,
            "expected_batch_size": self.get_active_game_count() * self.active_seats_per_game
        } 