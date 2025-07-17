"""
SFT dataset generator

Features
========
- Converts game trace logs into supervised fine-tuning (SFT) training samples
- Generates prompt/completion pairs for every agent turn in a chat-style format
- Adds metadata (e.g., agent ID, turn number, role, game ID) for filtering and analysis
- Supports both single and multi-game JSON input formats
- Outputs Hugging Face-compatible JSONL for use with SFT trainers (e.g., TRL or LoRA fine-tuning)

Usage
=====
    python generate_sft_dataset.py input_traces.json output_dataset.jsonl
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict

def generate_prompt(turn: Dict) -> str:
    """Constructs a user prompt from a single turn."""
    return (
        f"Turn {turn['turn']}.\n"
        f"You are the {turn['role']}.\n"
        f"Observation: {turn['obs']}\n"
        f"What is your next action?"
    )


def convert_trace_to_sft(trace: Dict) -> List[Dict]:
    """Converts a single game trace into SFT-style prompt/completion pairs."""
    sft_samples = []
    game_id = trace.get("game_id", "unknown")

    for turn in trace["turns"]:
        prompt = generate_prompt(turn)
        completion = turn["action"]

        sft_sample = {
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "model", "content": completion}
            ],
            "metadata": {
                "game_id": game_id,
                "agent_id": turn["agent_id"],
                "turn": turn["turn"],
                "role": turn.get("role", "unknown")
            }
        }

        sft_samples.append(sft_sample)

    return sft_samples


def process_input_file(input_path: Path) -> List[Dict]:
    with input_path.open("r", encoding="utf-8") as f:
        traces = json.load(f)

    # Handle single-trace or list-of-traces format
    if isinstance(traces, dict) and "turns" in traces:
        traces = [traces]

    all_samples = []
    for trace in traces:
        all_samples.extend(convert_trace_to_sft(trace))

    return all_samples


def write_jsonl(output_path: Path, data: List[Dict]):
    with output_path.open("w", encoding="utf-8") as f:
        for sample in data:
            f.write(json.dumps(sample) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Path to input trace JSON file")
    parser.add_argument("output", type=Path, help="Path to output JSONL file")
    args = parser.parse_args()

    samples = process_input_file(args.input)
    write_jsonl(args.output, samples)
    print(f"Wrote {len(samples)} SFT samples to {args.output}")


if __name__ == "__main__":
    main()