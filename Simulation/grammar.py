"""
XML Grammar validation and phase-aware action legality for ToSSim agents.

This module provides:
1. ToSSimGrammarParser - Pure XML validation for agent responses
2. PhaseLegalizer - Game-aware validation of action legality based on current phase
3. validate_action - Combined validation function for use across training/inference

The three-tier validation system:
- MALFORMED: Invalid XML structure (reward: -1)
- ILLEGAL: Valid XML but phase-illegal action (reward: 0, preserves misalignment)  
- OK: Valid XML and phase-legal action (reward: +1)
"""

import re
from typing import Dict, Any, Tuple, List, Optional, TYPE_CHECKING

from .errors import ErrorCode, format_error, format_success
from .enums import Time, Phase, RoleName

if TYPE_CHECKING:
    from .game import Game
    from .player import Player


class ToSSimGrammarParser:
    """
    Pure XML grammar parser for ToSSim agent format.
    
    Validates the strict XML structure: <think>...</think><TOOL_OR_INTERACTION/>
    Does not check game state or phase legality - that's handled by PhaseLegalizer.
    """
    
    def __init__(self):
        # Tool tags (information, terminal with auto-injection)
        self.tool_tags = {
            "get_role", "roles", "chat_history", "graveyard", "check_will", "view_will", "notebook"
        }
        
        # Day interaction tags
        self.day_interaction_tags = {
            "speak", "whisper", "vote", "nominate", "wait"
        }
        
        # Night interaction tags  
        self.night_interaction_tags = {
            "kill", "protect", "investigate", "shoot", "jail", "reveal",
            "execute", "douse", "rampage", "distract", "raise", "control",
            "alert", "transport", "bug", "watch", "vest", "remember", "track",
            "vision", "hex", "poison", "stone", "plunder", "blackmail", "clean",
            "disguise", "infect", "haunt", "seance", "forge", "trap", "frame",
            "hypnotize", "hypnotise", "skip", "pass"
        }
        
        # All interaction tags combined
        self.interaction_tags = self.day_interaction_tags | self.night_interaction_tags
        
        # Zero-arg banner tags (self-closing)
        self.banner_tags = {"wait", "reveal", "skip", "pass"}
        
        # Compile patterns
        self.think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
        self.tool_pattern = re.compile(
            rf"<({'|'.join(self.tool_tags)})(?:\s*/>|>(.*?)</\1>)", re.DOTALL
        )
        self.interaction_pattern = re.compile(
            rf"<({'|'.join(self.interaction_tags)})(?:\s*/>|>(.*?)</\1>)", re.DOTALL
        )
        
    def parse_and_validate(self, text: str) -> Tuple[bool, Dict[str, Any], Optional[ErrorCode]]:
        """
        Parse text and validate XML structure only.
        
        Returns:
            (is_valid, info_dict, error_code)
            
        Grammar: <think>...</think><TOOL_OR_INTERACTION/>
        """
        text = text.strip()
        
        # Check for proper structure: must start with <think> and end with terminal tag
        if not text.startswith("<think>"):
            return False, {"error": "Must start with <think> block"}, ErrorCode.MISSING_THINK_BLOCK
        
        # Find <think> block
        think_matches = self.think_pattern.findall(text)
        if len(think_matches) != 1:
            return False, {"error": "Must have exactly one <think> block"}, ErrorCode.MISSING_THINK_BLOCK
        
        think_content = think_matches[0]
        think_tokens = len(think_content.split())
        
        # Find the position where <think> block ends
        think_match = self.think_pattern.search(text)
        if not think_match:
            return False, {"error": "Invalid <think> block"}, ErrorCode.INVALID_XML_STRUCTURE
        
        think_end_pos = think_match.end()
        
        # Everything after <think> block should be exactly one terminal tag
        remainder = text[think_end_pos:].strip()
        
        if not remainder:
            return False, {"error": "Missing terminal tag after <think>"}, ErrorCode.INVALID_XML_STRUCTURE
        
        # Check for tool usage
        tool_matches = self.tool_pattern.findall(remainder)
        interaction_matches = self.interaction_pattern.findall(remainder)
        
        # Must have exactly one terminal tag
        total_terminal_tags = len(tool_matches) + len(interaction_matches)
        if total_terminal_tags != 1:
            if total_terminal_tags == 0:
                return False, {"error": "No valid terminal tag found"}, ErrorCode.INVALID_XML_STRUCTURE
            else:
                return False, {"error": f"Multiple terminal tags found: {total_terminal_tags}"}, ErrorCode.MULTIPLE_TERMINAL_TAGS
        
        # Check if remainder has only the terminal tag (no extra text)
        if tool_matches:
            tool_tag, tool_content = tool_matches[0]
            expected_tag = f"<{tool_tag}>" + (f"{tool_content}</{tool_tag}>" if tool_content else f"</{tool_tag}>")
            if remainder != expected_tag and not remainder == f"<{tool_tag}/>":
                return False, {"error": "Extra text around terminal tag"}, ErrorCode.INVALID_XML_STRUCTURE
        elif interaction_matches:
            int_tag, int_content = interaction_matches[0]
            if int_tag in self.banner_tags:
                expected_tag = f"<{int_tag}/>" if not int_content else f"<{int_tag}></{int_tag}>"
            else:
                expected_tag = f"<{int_tag}>" + (f"{int_content}</{int_tag}>" if int_content else f"</{int_tag}>")
            if remainder != expected_tag and not remainder == f"<{int_tag}/>":
                return False, {"error": "Extra text around terminal tag"}, ErrorCode.INVALID_XML_STRUCTURE
        
        # Valid XML structure
        terminal_tag = tool_matches[0][0] if tool_matches else interaction_matches[0][0]
        terminal_content = tool_matches[0][1] if tool_matches else interaction_matches[0][1]
        
        # Basic info dict
        info = {
            "think_tokens": think_tokens,
            "think_content": think_content,
            "has_tool": len(tool_matches) > 0,
            "has_interaction": len(interaction_matches) > 0,
            "terminal_tag": terminal_tag,
            "terminal_content": terminal_content
        }
        
        return True, info, None


class PhaseLegalizer:
    """
    Game-aware validator that checks if actions are legal in the current game phase.
    
    Uses the actual game state and phase information to determine legality.
    Returns error codes for different types of phase violations.
    """
    
    def __init__(self):
        # Tool tags that are generally allowed
        self.info_tools = {
            "get_role", "graveyard", "check_will", "view_will", "notebook"
        }
        
        # Chat history might be restricted in some phases
        self.chat_tools = {"chat_history"}
        
        # Day-specific actions
        self.day_actions = {"speak", "vote", "nominate", "wait", "whisper", "jail", "reveal"}
        
        # Night-specific actions (all the night abilities)
        self.night_actions = {
            "kill", "protect", "investigate", "shoot", "execute", 
            "douse", "rampage", "distract", "raise", "control", "alert", 
            "transport", "bug", "watch", "vest", "remember", "track",
            "vision", "hex", "poison", "stone", "plunder", "blackmail", 
            "clean", "disguise", "infect", "haunt", "seance", "forge", 
            "trap", "frame", "hypnotize", "hypnotise", "skip", "pass", "notebook"
        }
        
        # Actions that reveal (special day actions)
        self.reveal_actions = {"reveal"}
    
    def validate_action_legality(self, tag: str, content: str, game: 'Game', actor: 'Player') -> Tuple[bool, Optional[ErrorCode], str]:
        """
        Check if the parsed action is legal in the current game phase.
        
        Args:
            tag: The action tag (e.g., "speak", "kill", "vote")
            content: The content of the tag
            game: Current game state
            actor: Player attempting the action
            
        Returns:
            (is_legal, error_code, detail_message)
        """
        
        # Wait is always allowed
        if tag == "wait":
            return True, None, ""

        # Tool usage validation
        if tag in self.info_tools:
            if tag == "notebook":
                # Notebook is allowed in all phases
                return True, None, ""
            # Other info tools generally allowed, but some restrictions may apply
            return True, None, ""
        
        if tag in self.chat_tools:
            # Chat history might be restricted during night
            if game.time == Time.NIGHT:
                return False, ErrorCode.ILLEGAL_TOOL, f"{tag} is not available during night phase"
            return True, None, ""
        
        # Speaking validation
        if tag == "speak":
            return self._validate_speak_permission(game, actor)
        
        # Voting validation  
        if tag == "vote":
            return self._validate_vote_permission(content, game, actor)
        
        # Nomination validation
        if tag == "nominate":
            if game.time != Time.DAY:
                return False, ErrorCode.WRONG_PHASE, "Nominations only allowed during day"
            if game.phase != Phase.NOMINATION:
                return False, ErrorCode.WRONG_PHASE, "Nominations only allowed during nomination phase"
            return True, None, ""
        
        # Whisper validation
        if tag == "whisper":
            return self._validate_whisper_permission(game, actor)
        
        # Reveal validation
        if tag in self.reveal_actions:
            if game.time != Time.DAY:
                return False, ErrorCode.WRONG_PHASE, "Can only reveal during day"
            return True, None, ""
        
        # Night actions validation
        if tag in self.night_actions:
            if game.time != Time.NIGHT:
                return False, ErrorCode.ILLEGAL_TOOL, f"{tag} is a night action, cannot be used during day"
            return True, None, ""
        
        # Day actions validation (except those handled above)
        if tag in self.day_actions:
            if game.time != Time.DAY:
                return False, ErrorCode.ILLEGAL_TOOL, f"{tag} is a day action, cannot be used during night"
            return True, None, ""
        
        # Default: unknown action (should be caught by InteractionHandler)
        return True, None, ""
    
    def _validate_speak_permission(self, game: 'Game', actor: 'Player') -> Tuple[bool, Optional[ErrorCode], str]:
        """Check if agent can speak in current phase."""
        
        if game.time == Time.NIGHT:
            # Allow speaking at night only if in a writable channel (Mafia, Jailed, etc.)
            can_speak = False
            for chan in game.chat.channels.values():
                if actor.id in chan.members and chan.members[actor.id] == {'READ', 'WRITE'}:
                    can_speak = True
                    break
            if not can_speak:
                 return False, ErrorCode.ILLEGAL_SPEAKER, "No public speaking allowed at night"

        if game.phase == Phase.DEFENSE:
            # Only the accused can speak during defense
            on_trial_player = getattr(game, 'day_phase_manager', None)
            if on_trial_player and hasattr(on_trial_player, 'on_trial') and on_trial_player.on_trial:
                if actor != on_trial_player.on_trial:
                    return False, ErrorCode.ILLEGAL_SPEAKER, "Only the accused can speak during defense phase"
        
        # All other day phases allow speaking
        return True, None, ""
    
    def _validate_vote_permission(self, content: str, game: 'Game', actor: 'Player') -> Tuple[bool, Optional[ErrorCode], str]:
        """Check if vote content is valid for current phase."""
        
        if game.time != Time.DAY:
            return False, ErrorCode.WRONG_PHASE, "Voting only allowed during day"
        
        if game.phase == Phase.JUDGEMENT:
            # Must vote guilty or innocent
            if content.strip().lower() not in {"guilty", "innocent"}:
                return False, ErrorCode.ILLEGAL_TOOL, "Must vote 'guilty' or 'innocent' during judgement"
        elif game.phase == Phase.NOMINATION:
            # Must vote for a player name (content validation done by InteractionHandler)
            if not content.strip():
                return False, ErrorCode.ILLEGAL_TOOL, "Must specify a player name to vote for"
        else:
            # Voting not allowed in other phases
            return False, ErrorCode.WRONG_PHASE, f"Voting not allowed during {game.phase.name.lower()} phase"
        
        return True, None, ""
    
    def _validate_whisper_permission(self, game: 'Game', actor: 'Player') -> Tuple[bool, Optional[ErrorCode], str]:
        """Check if agent can whisper in current phase."""
        
        if game.time == Time.NIGHT:
            # At night, only mafia/coven can whisper to each other
            # This is a simplified check - more complex logic might be needed
            if hasattr(actor.role, 'faction'):
                if actor.role.faction.name in ['MAFIA', 'COVEN']:
                    return True, None, ""
            return False, ErrorCode.ILLEGAL_SPEAKER, "Only mafia/coven can whisper at night"
        
        # Day whispers are generally allowed
        return True, None, ""


def validate_action(text: str, game: 'Game', actor: 'Player') -> Tuple[str, Optional[ErrorCode], str]:
    """
    Complete validation pipeline: XML parsing + phase legality check.
    
    Args:
        text: Agent's response text
        game: Current game state  
        actor: Player attempting the action
        
    Returns:
        (status, error_code, detail)
        
    Status values:
        - "OK": Valid XML and phase-legal action
        - "ILLEGAL": Valid XML but phase-illegal action  
        - "MALFORMED": Invalid XML structure
    """
    
    # Step 1: Parse XML structure
    parser = ToSSimGrammarParser()
    is_valid, info, parse_error = parser.parse_and_validate(text)
    
    if not is_valid:
        return "MALFORMED", parse_error, info.get("error", "Unknown XML error")
    
    # Step 2: Check phase legality
    legalizer = PhaseLegalizer()
    tag = info["terminal_tag"]
    content = info["terminal_content"]
    
    is_legal, legality_error, detail = legalizer.validate_action_legality(tag, content, game, actor)
    
    if not is_legal:
        return "ILLEGAL", legality_error, detail
    
    # Valid and legal
    return "OK", None, ""


def get_action_reward(status: str, error_code: Optional[ErrorCode]) -> float:
    """
    Get the training reward for a validation result.
    
    Args:
        status: Validation status ("OK", "ILLEGAL", "MALFORMED")
        error_code: Error code if applicable
        
    Returns:
        Reward value for training
    """
    if status == "OK":
        return 1.0
    elif status == "MALFORMED":
        return -1.0
    else:  # ILLEGAL
        return 0.0  # Preserve misalignment potential 