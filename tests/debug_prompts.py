#!/usr/bin/env python3
"""
Debug script to understand DeceptionPrompts method signatures.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from analysis.evaluation.prompts.deception_prompts import DeceptionPrompts
import inspect

def debug_prompt_methods():
    """Debug the DeceptionPrompts methods to understand their signatures."""
    
    prompts = DeceptionPrompts()
    
    print("🔍 Debugging DeceptionPrompts methods...")
    
    # Create sample data that matches the expected structure
    sample_player_data = {
        "claimed_role": "Doctor",
        "actual_role": "Citizen",
        "faction": "Town",
        "survival_status": "alive",
        "chat_messages": [
            {"day": 1, "message": "I'm the doctor, trust me!"},
            {"day": 2, "message": "I can heal people"}
        ],
        "actions": [
            {"day": 1, "action": "heal", "target": "Alice"},
            {"day": 2, "action": "heal", "target": "Bob"}
        ],
        "votes": [
            {"day": 1, "target": "Charlie"},
            {"day": 2, "target": "Diana"}
        ],
        "role_claims": [
            {"day": 1, "role": "Doctor", "confidence": "certain"}
        ]
    }
    
    sample_context = {
        "total_days": 3,
        "total_players": 10,
        "game_summary": "Test game",
        "final_state": "in_progress"
    }
    
    sample_communication_analysis = {
        "consistency_score": 65,
        "contradiction_score": 30,
        "deflection_score": 45,
        "withholding_score": 20,
        "overall_deception_likelihood": 55,
        "key_evidence": "Some contradictions in statements",
        "explanation": "Player shows mixed signals",
        "confidence_level": 70
    }
    
    sample_action_analysis = {
        "role_consistency_score": 80,
        "strategic_alignment_score": 60,
        "timing_appropriateness_score": 70,
        "target_selection_score": 75,
        "overall_alignment_score": 71,
        "key_evidence": "Actions mostly align with claimed role",
        "explanation": "Good alignment with doctor role",
        "confidence_level": 80
    }
    
    sample_voting_analysis = {
        "vote_consistency_score": 50,
        "strategic_timing_score": 40,
        "bandwagon_score": 60,
        "faction_alignment_score": 55,
        "overall_voting_deception": 51,
        "key_evidence": "Some questionable voting patterns",
        "explanation": "Mixed voting behavior",
        "confidence_level": 60
    }
    
    methods = [
        ('generate_communication_analysis_prompt', 
         ("TestPlayer", sample_player_data, sample_context)),
        ('generate_voting_analysis_prompt', 
         ("TestPlayer", sample_player_data, sample_context)),
        ('generate_action_alignment_prompt', 
         ("TestPlayer", sample_player_data, sample_context)),
        ('generate_overall_deception_prompt', 
         ("TestPlayer", sample_player_data, sample_context, 
          sample_communication_analysis, sample_action_analysis, sample_voting_analysis))
    ]
    
    for method_name, args in methods:
        if hasattr(prompts, method_name):
            method = getattr(prompts, method_name)
            sig = inspect.signature(method)
            print(f"\n📋 {method_name}:")
            print(f"   Signature: {sig}")
            print(f"   Parameters: {list(sig.parameters.keys())}")
            
            try:
                result = method(*args)
                if result and isinstance(result, str):
                    print(f"   ✅ SUCCESS: Generated prompt with {len(result)} characters")
                    print(f"   📝 Preview: {result[:150]}...")
                else:
                    print(f"   ⚠️  Returned non-string result: {type(result)}")
            except Exception as e:
                print(f"   ❌ FAILED: {e}")
        else:
            print(f"\n❌ {method_name} does not exist")

if __name__ == "__main__":
    debug_prompt_methods()