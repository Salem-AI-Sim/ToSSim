from pathlib import Path
import json
import argparse
from datetime import datetime

RAW_STREAMS = [
    "game_events.jsonl",
    "chat.jsonl",
    "agent_actions.jsonl",
    "agent_reasoning.jsonl",
    "inference_trace.jsonl",
    "research_metrics.jsonl",
]

def parse_jsonl(file_path: Path) -> list:
    """Parse a JSONL file into a list of Python dictionaries."""
    with file_path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def build_game_summary(game_events: list, chat_logs: list, agent_actions: list) -> dict:
    """Build a high-level summary of the game."""
    summary = {
        "total_days": sum(1 for event in game_events if event.get("event_type") == "DAY_START"),
        "total_nights": sum(1 for event in game_events if event.get("event_type") == "NIGHT_START"),
        "winner_factions": set(event["payload"]["winning_faction"] for event in game_events if event.get("event_type") == "GAME_END"),
        "total_messages": len(chat_logs),
        "total_actions": len(agent_actions),
    }
    return summary

def analyze_agents(agent_actions: list, agent_reasoning: list, chat_logs: list, research_metrics: list) -> list:
    """Analyze each agent's performance and behavior."""
    agent_metrics = {}

    # Initialize metrics for each agent
    for action in agent_actions:
        agent_name = action["agent"]
        if agent_name not in agent_metrics:
            agent_metrics[agent_name] = {
                "votes_cast": 0,
                "messages_sent": 0,
                "actions_taken": 0,
                "reasoning_entries": 0,
                "successful_tool_uses": 0,
                "unsuccessful_tool_uses": 0,
            }

        # Increment action-related metrics
        agent_metrics[agent_name]["actions_taken"] += 1
        if action.get("action_type") == "VOTE":
            agent_metrics[agent_name]["votes_cast"] += 1

    # Count chat messages
    for message in chat_logs:
        agent_name = message["speaker"]
        if agent_name in agent_metrics:
            agent_metrics[agent_name]["messages_sent"] += 1

    # Count reasoning entries
    for reasoning in agent_reasoning:
        agent_name = reasoning["agent"]
        if agent_name in agent_metrics:
            agent_metrics[agent_name]["reasoning_entries"] += 1

    # Incorporate research metrics
    for metric in research_metrics:
        agent_name = metric["agent_name"]
        if agent_name in agent_metrics:
            agent_metrics[agent_name].update(metric["metrics"])

    # Convert metrics to JSONL format
    return [{"agent": agent, **metrics} for agent, metrics in agent_metrics.items()]

def build_sft_dataset(agent_reasoning: list) -> list:
    """Build a dataset of prompt-completion pairs for supervised fine-tuning."""
    sft_data = []

    for entry in agent_reasoning:
        sft_data.append({
            "prompt": entry["thinking_process"],
            "completion": entry["payload"].get("completion", ""),
            "metadata": {
                "turn": entry["turn"],
                "agent": entry["agent"],
            }
        })

    return sft_data

def aggregate_logs(raw_dir: Path, output_dir: Path) -> None:
    """Aggregate raw logs into structured datasets."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse raw logs
    game_events = parse_jsonl(raw_dir / "game_events.jsonl")
    chat_logs = parse_jsonl(raw_dir / "chat.jsonl")
    agent_actions = parse_jsonl(raw_dir / "agent_actions.jsonl")
    agent_reasoning = parse_jsonl(raw_dir / "agent_reasoning.jsonl")
    research_metrics = parse_jsonl(raw_dir / "research_metrics.jsonl")

    # Build game summary
    game_summary = build_game_summary(game_events, chat_logs, agent_actions)
    (output_dir / "game_summary.json").write_text(json.dumps(game_summary, indent=2))

    # Build agent analysis
    agent_analysis = analyze_agents(agent_actions, agent_reasoning, chat_logs, research_metrics)
    with (output_dir / "agent_analysis.jsonl").open("w") as f:
        for analysis in agent_analysis:
            f.write(json.dumps(analysis) + "\n")

    # Build SFT dataset
    sft_dataset = build_sft_dataset(agent_reasoning)
    with (output_dir / "sft_dataset.jsonl").open("w") as f:
        for entry in sft_dataset:
            f.write(json.dumps(entry) + "\n")

# Add this function to the existing file

def build_history_for_analysis(game_events: list, chat_logs: list, agent_actions: list, agent_reasoning: list) -> dict:
    """Build history_for_analysis.json format for blind judge analysis."""
    
    # Extract game context
    game_end_events = [e for e in game_events if e.get("event_type") == "GAME_END"]
    winning_faction = game_end_events[0]["payload"]["winning_faction"] if game_end_events else "Unknown"
    
    total_days = sum(1 for event in game_events if event.get("event_type") == "DAY_START")
    
    # Group data by agent
    agents = set(action["agent"] for action in agent_actions)
    players = {}
    
    for agent in agents:
        # Extract agent-specific data
        agent_messages = [msg for msg in chat_logs if msg["speaker"] == agent]
        agent_actions_list = [action for action in agent_actions if action["agent"] == agent]
        agent_reasoning_list = [reasoning for reasoning in agent_reasoning if reasoning["agent"] == agent]
        
        # Convert to analysis format
        chat_messages = [
            {
                "day": msg.get("turn", 0),
                "message": msg["message"],
                "timestamp": msg.get("timestamp", "")
            }
            for msg in agent_messages
        ]
        
        actions = [
            {
                "action": action.get("action_type", "unknown"),
                "target": action.get("target", ""),
                "day": action.get("turn", 0),
                "details": action.get("payload", {})
            }
            for action in agent_actions_list
        ]
        
        # Extract role claims from chat or actions
        role_claims = []
        for msg in agent_messages:
            # Simple heuristic to detect role claims
            message_text = msg["message"].lower()
            if any(role in message_text for role in ["sheriff", "doctor", "investigator", "mayor", "medium"]):
                role_claims.append({
                    "role": "Unknown",  # Would need better parsing
                    "day": msg.get("turn", 0),
                    "confidence": "unknown"
                })
        
        # Extract votes
        votes = [
            {
                "target": action.get("target", ""),
                "day": action.get("turn", 0),
                "reasoning": "Unknown"  # Would need to extract from reasoning
            }
            for action in agent_actions_list
            if action.get("action_type") == "VOTE"
        ]
        
        players[agent] = {
            "chat_messages": chat_messages,
            "actions": actions,
            "role_claims": role_claims,
            "votes": votes,
            "claimed_role": "Unknown",  # Would need extraction logic
            "vote_history": [vote["target"] for vote in votes],
            "vote_reasons": [vote["reasoning"] for vote in votes]
        }
    
    return {
        "game_id": f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "context": {
            "game_summary": f"Game ended with {winning_faction} victory",
            "total_days": total_days,
            "total_players": len(players),
            "winning_faction": winning_faction
        },
        "players": players
    }

# Update the aggregate_logs function
def aggregate_logs(raw_dir: Path, output_dir: Path, include_blind_judge: bool = True) -> None:
    """Aggregate raw logs into structured datasets."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse raw logs
    game_events = parse_jsonl(raw_dir / "game_events.jsonl")
    chat_logs = parse_jsonl(raw_dir / "chat.jsonl")
    agent_actions = parse_jsonl(raw_dir / "agent_actions.jsonl")
    agent_reasoning = parse_jsonl(raw_dir / "agent_reasoning.jsonl")
    research_metrics = parse_jsonl(raw_dir / "research_metrics.jsonl")

    # Build game summary
    game_summary = build_game_summary(game_events, chat_logs, agent_actions)
    (output_dir / "game_summary.json").write_text(json.dumps(game_summary, indent=2))

    # Build agent analysis
    agent_analysis = analyze_agents(agent_actions, agent_reasoning, chat_logs, research_metrics)
    with (output_dir / "agent_analysis.jsonl").open("w") as f:
        for analysis in agent_analysis:
            f.write(json.dumps(analysis) + "\n")

    # Build SFT dataset
    sft_dataset = build_sft_dataset(agent_reasoning)
    with (output_dir / "sft_dataset.jsonl").open("w") as f:
        for entry in sft_dataset:
            f.write(json.dumps(entry) + "\n")

    # NEW: Build history for analysis (blind judge format)
    if include_blind_judge:
        history_data = build_history_for_analysis(game_events, chat_logs, agent_actions, agent_reasoning)
        (output_dir / "history_for_analysis.json").write_text(json.dumps(history_data, indent=2))

# Update CLI to include blind judge option
def _cli():
    p = argparse.ArgumentParser(description="Aggregate raw game logs into analysis datasets.")
    p.add_argument("--raw-dir", type=Path, required=True, help="Directory containing raw JSONL logs.")
    p.add_argument("--output-dir", type=Path, required=True, help="Directory to write aggregated outputs.")
    p.add_argument("--include-blind-judge", action="store_true", help="Include history_for_analysis.json for blind judge")
    args = p.parse_args()

    aggregate_logs(args.raw_dir, args.output_dir, args.include_blind_judge)
    
if __name__ == "__main__":
    _cli()