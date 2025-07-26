"""
Simulation.event_logger - Centralized logging system for ToSSim.

This module provides a comprehensive logging system that captures all game events
in structured JSONL format for research analysis and debugging.
"""

import logging
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from Simulation.logger import JSONLLogger, JSONLFormatter






@dataclass
class GameLogger:
    """
    Centralized game logging system that captures all events in structured JSONL format.
    
    Creates 6 JSONL streams as specified in docs/logging.md:
    - game_events.jsonl: High-level game state changes
    - chat.jsonl: Public messages and whispers
    - agent_actions.jsonl: Tool calls and interactions
    - agent_reasoning.jsonl: Agent thinking processes
    - inference_trace.jsonl: Performance and debugging info
    - research_metrics.jsonl: Per-agent metrics for analysis
    """
    
    game_id: str
    log_dir: Path
    
    def __post_init__(self):
        """Initialize all loggers after dataclass creation."""
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize all 6 JSONL loggers
        self.game_events_logger = JSONLLogger(
            "game_events", 
            log_file=self.log_dir / "game_events.jsonl"
        )
        
        self.chat_logger = JSONLLogger(
            "chat", 
            log_file=self.log_dir / "chat.jsonl"
        )
        
        self.agent_actions_logger = JSONLLogger(
            "agent_actions", 
            log_file=self.log_dir / "agent_actions.jsonl"
        )
        
        self.agent_reasoning_logger = JSONLLogger(
            "agent_reasoning", 
            log_file=self.log_dir / "agent_reasoning.jsonl"
        )
        
        self.inference_trace_logger = JSONLLogger(
            "inference_trace", 
            log_file=self.log_dir / "inference_trace.jsonl"
        )
        
        self.research_metrics_logger = JSONLLogger(
            "research_metrics", 
            log_file=self.log_dir / "research_metrics.jsonl"
        )
        
        self.sft_samples_logger = JSONLLogger(
            "sft_samples", 
            log_file=self.log_dir / "sft_samples.jsonl"
        )
    
    def _get_timestamp(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.utcnow().isoformat() + "Z"
    
    def log_game_event(self, event_type: str, payload: Dict[str, Any], turn: str = None):
        """Log a high-level game event."""
        self.game_events_logger.info({
            "timestamp": self._get_timestamp(),
            "turn": turn or "Unknown",
            "event_type": event_type,
            "payload": payload
        })
    
    def log_chat(self, speaker: str, message: str, turn: str, is_whisper: bool = False):
        """Log a chat message (public or whisper)."""
        self.chat_logger.info({
            "timestamp": self._get_timestamp(),
            "turn": turn,
            "speaker": speaker,
            "message": message,
            "is_whisper": is_whisper
        })
    
    def log_agent_action(self, agent: Union[str, Dict], action_type: str, payload: Dict[str, Any], turn: str):
        """Log an agent action (tool call, interaction, etc.)."""
        self.agent_actions_logger.info({
            "timestamp": self._get_timestamp(),
            "turn": turn,
            "agent": agent,
            "action_type": action_type,
            "payload": payload
        })
    
    def log_agent_reasoning(self, agent: Union[str, Dict], thinking_process: str, turn: str, completion: str = None):
        """Log an agent's thinking process."""
        self.agent_reasoning_logger.info({
            "timestamp": self._get_timestamp(),
            "turn": turn,
            "agent": agent,
            "thinking_process": thinking_process,
            "payload": {
                "completion": completion
            }
        })
    
    def log_inference_trace(self, event_type: str, agent: Union[str, Dict], payload: Dict[str, Any]):
        """Log inference engine performance and debugging info."""
        self.inference_trace_logger.info({
            "timestamp": self._get_timestamp(),
            "event_type": event_type,
            "agent": agent,
            "payload": payload
        })
    
    def log_research_metrics(self, player_name: str, metrics: Dict[str, Any], agent: Union[str, dict]):
        """Log per-agent research metrics."""
        self.research_metrics_logger.info({
            "timestamp": self._get_timestamp(),
            "game_id": self.game_id,
            "player_name": player_name,
            "agent": agent,
            "metrics": metrics
        })
    
    # Convenience methods for common game events
    def log_game_start(self, game_mode: str, players: List[str]):
        """Log game start event."""
        self.log_game_event("GAME_START", {
            "game_mode": game_mode,
            "players": players,
            "total_players": len(players)
        }, "Game Start")
    
    def log_day_start(self, day: int, living_players: List[str]):
        """Log day start event."""
        self.log_game_event("DAY_START", {
            "day": day,
            "living_players": living_players,
            "living_count": len(living_players)
        }, f"Day {day}")
    
    def log_night_start(self, night: int, living_players: List[str]):
        """Log night start event."""
        self.log_game_event("NIGHT_START", {
            "night": night,
            "living_players": living_players,
            "living_count": len(living_players)
        }, f"Night {night}")
    
    def log_death(self, player: str, role: str, killed_by: str, death_type: str):
        """Log player death event."""
        self.log_game_event("DEATH", {
            "player": player,
            "role": role,
            "killed_by": killed_by,
            "death_type": death_type
        }, "Death")
    
    def log_vote_start(self, defendant: str, nominators: List[str]):
        """Log trial start event."""
        self.log_game_event("VOTE_START", {
            "defendant": defendant,
            "nominators": nominators,
            "nomination_count": len(nominators)
        }, "Trial")
    
    def log_trial_result(self, defendant: str, verdict: str, guilty_votes: int, innocent_votes: int):
        """Log trial result event."""
        self.log_game_event("TRIAL_RESULT", {
            "defendant": defendant,
            "verdict": verdict,
            "guilty_votes": guilty_votes,
            "innocent_votes": innocent_votes
        }, "Trial Result")
    
    def log_game_end(self, winning_factions: List[str], surviving_players: List[str], duration_days: int):
        """Log game end event."""
        self.log_game_event("GAME_END", {
            "winning_factions": winning_factions,
            "surviving_players": surviving_players,
            "duration_days": duration_days
        }, "Game End")
    
    def log_tool_call(self, agent: Union[str, Dict], tool_name: str, arguments: str, result: str, turn: str):
        """Log a tool call."""
        self.log_agent_action(agent, "TOOL_CALL", {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result
        }, turn)
    
    def log_interaction(self, agent: Union[str, Dict], interaction_type: str, target: str, turn: str):
        """Log an interaction (speak, vote, etc.)."""
        self.log_agent_action(agent, "INTERACTION", {
            "interaction_type": interaction_type,
            "target": target
        }, turn)
    
    def log_sft_sample(self, sample_id: str, player_name: str, agent: Union[str, Dict], prompt: List[Dict], completion: str, metadata: Dict[str, Any]):
        """Log an SFT training sample with prompt/completion pairs."""
        self.sft_samples_logger.info({
            "timestamp": self._get_timestamp(),
            "sample_id": sample_id,
            "player_name": player_name,
            "agent": agent,
            "prompt": prompt,
            "completion": completion,
            "metadata": metadata
        })
    
    def log_inference_complete(self, agent: Union[str, Dict], latency_ms: int, prompt_tokens: int, output_tokens: int):
        """Log inference completion with performance metrics."""
        self.log_inference_trace("INFERENCE_COMPLETE", agent, {
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens
        })
    
    def finalize_player_metrics(self, player, agent):
        """Log final research metrics for a player, linked with agent info."""
        if hasattr(player, 'research_metrics'):
            self.log_research_metrics(player.name, player.research_metrics, agent)
    
    def close(self):
        """Close all loggers."""
        # The JSONLLogger handles file closing automatically
        pass 