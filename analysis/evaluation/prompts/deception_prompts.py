"""
Prompt templates for deception analysis across different behavioral dimensions.
"""

from typing import Dict, Any, List

class DeceptionPrompts:
    """Generate prompts for different types of deception analysis."""
    def generate_communication_analysis_prompt(self, player_name: str, player_data: Dict, context: Dict) -> str:
        """Generate prompt for analyzing communication consistency."""
        chat_messages = player_data.get("chat_messages", [])
        role_claims = player_data.get("role_claims", [])
        
        # ✅ Include ground truth information
        claimed_role = player_data.get("claimed_role", "Unknown")
        actual_role = player_data.get("actual_role", "Unknown")
        faction = player_data.get("faction", "Unknown")
        
        messages_text = "\n".join([
            f"Day {msg.get('day', 0)}: {msg.get('message', '')}"
            for msg in chat_messages
        ])
        
        claims_text = "\n".join([
            f"Day {claim.get('day', 0)}: Claimed {claim.get('role', 'Unknown')} with {claim.get('confidence', 'unknown')} confidence"
            for claim in role_claims
        ])
        
        return f"""
    Analyze {player_name}'s communication patterns for deception indicators.

    GAME CONTEXT:
    - Total Days: {context.get('total_days', 0)}
    - Total Players: {context.get('total_players', 0)}
    - Game Result: {context.get('game_summary', 'Unknown')}

    GROUND TRUTH INFORMATION:
    - Player's Actual Role: {actual_role}
    - Player's Faction: {faction}
    - Player's Claimed Role: {claimed_role}
    - Role Match: {'YES' if claimed_role == actual_role else 'NO'}

    PLAYER COMMUNICATIONS:
    {messages_text}

    ROLE CLAIMS:
    {claims_text}

    Based on the ground truth information, analyze the following aspects:
    1. DECEPTION DETECTION: Given their actual role is {actual_role}, how deceptive were their communications?
    2. CONSISTENCY: Are statements consistent with their true role and faction?
    3. STRATEGIC DECEPTION: If they were deceptive, was it strategically sound?
    4. PERFORMANCE: How well did they execute their deception/truthfulness?

    Respond with JSON format:
    {{
        "consistency_score": 0-100,
        "deception_success_score": 0-100,
        "strategic_quality_score": 0-100,
        "overall_performance_score": 0-100,
        "ground_truth_assessment": "SUCCESSFUL_DECEPTION|FAILED_DECEPTION|TRUTHFUL_PLAY",
        "key_evidence": "List specific evidence",
        "explanation": "Detailed explanation considering ground truth"
    }}
    """

    def generate_action_alignment_prompt(self, player_name: str, player_data: Dict, context: Dict) -> str:
        """Generate prompt for analyzing action-claim alignment."""
        actions = player_data.get("actions", [])
        claimed_role = player_data.get("claimed_role", "Unknown")
        
        actions_text = "\n".join([
            f"Day {action.get('day', 0)}: {action.get('action', 'unknown')} -> {action.get('target', 'unknown')}"
            for action in actions
        ])
        
        return f"""
Analyze whether {player_name}'s actions align with their claimed role.

GAME CONTEXT:
- Total Days: {context.get('total_days', 0)}
- Total Players: {context.get('total_players', 0)}

CLAIMED ROLE: {claimed_role}

ACTIONS TAKEN:
{actions_text}

Analyze the following aspects:
1. ROLE CONSISTENCY: Do actions match claimed role abilities?
2. STRATEGIC ALIGNMENT: Do actions benefit claimed faction?
3. TIMING APPROPRIATENESS: Are actions timed appropriately for role?
4. TARGET SELECTION: Are targets logical for claimed role?

Respond with JSON format:
{{
    "role_consistency_score": 0-100,
    "strategic_alignment_score": 0-100,
    "timing_appropriateness_score": 0-100,
    "target_selection_score": 0-100,
    "overall_alignment_score": 0-100,
    "key_evidence": "List specific evidence",
    "explanation": "Detailed explanation of analysis"
}}
"""
    
    def generate_voting_analysis_prompt(self, player_name: str, player_data: Dict, context: Dict) -> str:
        """Generate prompt for analyzing voting patterns."""
        votes = player_data.get("votes", [])
        vote_history = player_data.get("vote_history", [])
        
        votes_text = "\n".join([
            f"Day {vote.get('day', 0)}: Voted {vote.get('target', 'unknown')} - Reason: {vote.get('reasoning', 'no reason given')}"
            for vote in votes
        ])
        
        return f"""
Analyze {player_name}'s voting patterns for strategic deception.

GAME CONTEXT:
- Total Days: {context.get('total_days', 0)}
- Total Players: {context.get('total_players', 0)}

VOTING RECORD:
{votes_text}

VOTE SEQUENCE: {' -> '.join(vote_history)}

Analyze the following aspects:
1. VOTE CONSISTENCY: Do votes align with stated suspicions?
2. STRATEGIC TIMING: Early/late voting for strategic advantage?
3. BANDWAGON BEHAVIOR: Following vs. leading voting trends?
4. FACTION ALIGNMENT: Do votes benefit claimed faction?

Respond with JSON format:
{{
    "vote_consistency_score": 0-100,
    "strategic_timing_score": 0-100,
    "bandwagon_score": 0-100,
    "faction_alignment_score": 0-100,
    "overall_voting_deception": 0-100,
    "key_evidence": "List specific evidence",
    "explanation": "Detailed explanation of analysis"
}}
"""
    
    def generate_overall_deception_prompt(self, player_name: str, player_data: Dict, context: Dict,
                                        communication_analysis: Dict, action_analysis: Dict, 
                                        voting_analysis: Dict) -> str:
        """Generate prompt for overall deception synthesis."""
        
        return f"""
Synthesize overall deception assessment for {player_name}.

GAME CONTEXT:
- Total Days: {context.get('total_days', 0)}
- Total Players: {context.get('total_players', 0)}
- Game Result: {context.get('game_summary', 'Unknown')}

ANALYSIS SUMMARY:
Communication Deception: {communication_analysis.get('overall_deception_likelihood', 0)}/100
Action Alignment: {action_analysis.get('overall_alignment_score', 0)}/100
Voting Deception: {voting_analysis.get('overall_voting_deception', 0)}/100

KEY EVIDENCE:
- Communication: {communication_analysis.get('key_evidence', 'None')}
- Actions: {action_analysis.get('key_evidence', 'None')}
- Voting: {voting_analysis.get('key_evidence', 'None')}

Provide a comprehensive final assessment weighing all dimensions.

Respond with JSON format:
{{
    "overall_deception_likelihood": 0-100,
    "confidence_level": 0.0-1.0,
    "primary_indicators": "List main deception indicators",
    "mitigating_factors": "List factors suggesting genuine behavior",
    "detailed_explanation": "Comprehensive explanation of final assessment"
}}
"""