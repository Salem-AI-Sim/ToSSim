"""
Comprehensive prompt building system for ToSSim agents.

This module provides model-specific prompt building with:
1. Static system prompts (role cards, tools, interactions, phase rules)
2. Dynamic user prompts (phase context, roster, graveyard, observations)
3. Model-specific templating (Gemma vs others)
4. Tool categorization (environment_static, environment_dynamic, environment_terminal)
5. Phase-specific UI and voting information

All consumers (training, inference, self-play) should use this module
to ensure consistent prompt formatting across the codebase.
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path
from dataclasses import dataclass, field
import json

from .enums import Time, Phase, RoleName
from .roles import create_role_from_name

if TYPE_CHECKING:
    from .game import Game
    from .player import Player
    from .roles import Role

# Load phase metadata for dynamic phase instructions
PHASES_JSON_PATH = Path(__file__).parent / "tools" / "phases.json"
with open(PHASES_JSON_PATH, "r", encoding="utf-8") as f:
    PHASES_DATA: Dict[str, Any] = json.load(f)

PHASE_NAME_MAP = {
    Phase.DISCUSSION: "Discussion",
    Phase.NOMINATION: "Nomination",
    Phase.DEFENSE: "Defense",
    Phase.JUDGEMENT: "Judgement",
    Phase.LAST_WORDS: "Last Words",
    Phase.PRE_NIGHT: "Pre-Night",
    Phase.NIGHT: "Night",
}


# ---------------------------------------------------------------------------
# Model Configuration System
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    """Configuration for model-specific prompt formatting."""
    name: str
    has_system_prompt: bool = True
    system_token: str = "<|system|>"
    user_token: str = "<|user|>"
    assistant_token: str = "<|assistant|>"
    end_token: str = "</s>"
    
    def format_messages(self, system_prompt: str, user_prompt: str, notebook_observation: str = None, 
                       environment_static_observations: str = None) -> str:
        """Format system and user prompts according to model requirements, appending EOS tokens as needed."""
        # Build observation sections
        observation_section = ""
        if notebook_observation:
            if self.name == "gemma":
                observation_section += f"<start_of_turn>observation\n{notebook_observation}\n{self.end_token}\n\n"
            else:
                observation_section += f"<observation>\n{notebook_observation}\n</observation>\n{self.end_token}\n\n"
        if environment_static_observations:
            if self.name == "gemma":
                observation_section += f"<start_of_turn>observation\n{environment_static_observations}\n\n"
            else:
                observation_section += f"<observation>\n{environment_static_observations}\n</observation>\n\n"
        # Append EOS token after system and user prompt blocks, not after <start_of_turn>model
        if self.has_system_prompt:
            return (
                f"{self.system_token}\n{system_prompt}\n{self.end_token}\n\n"
                f"{observation_section}"
                f"{self.user_token}\n{user_prompt}\n{self.end_token}\n\n"
                f"{self.assistant_token}\n"
            )
        else:
            # Models like Gemma treat system prompt as additional user prompt
            return (
                f"{self.user_token}\n{system_prompt}\n{self.end_token}\n\n"
                f"{observation_section}"
                f"{self.user_token}\n{user_prompt}\n{self.end_token}\n\n"
                f"{self.assistant_token}\n"
            )


# Default model configurations
MODEL_CONFIGS = {
    "gemma": ModelConfig(
        name="gemma",
        has_system_prompt=False,
        system_token="<start_of_turn>user",
        user_token="<start_of_turn>user", 
        assistant_token="<start_of_turn>model",
        end_token="<end_of_turn>"
    ),
    "default": ModelConfig(
        name="default",
        has_system_prompt=True
    )
}


def get_model_config(model_name: str) -> ModelConfig:
    """Get model configuration, falling back to default if not found."""
    # Check for exact match first
    if model_name in MODEL_CONFIGS:
        return MODEL_CONFIGS[model_name]
    
    # Check for partial matches (e.g., "gemma-7b" -> "gemma")
    model_lower = model_name.lower()
    for config_name, config in MODEL_CONFIGS.items():
        if config_name in model_lower:
            return config
    
    return MODEL_CONFIGS["default"]


# ---------------------------------------------------------------------------
# Tool and Interaction System
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    """Structured tool specification for prompt building."""
    name: str
    syntax: str
    description: str
    example_input: str
    example_output: str
    tool_class: str = "environment_static"  # environment_static, environment_dynamic, environment_terminal


@dataclass
class InteractionSpec:
    """Structured interaction specification for prompt building."""
    name: str
    syntax: str
    description: str
    example_input: str
    example_output: str
    phases_allowed: List[str] = field(default_factory=list)


def discover_tools(role: 'Role' = None) -> List[ToolSpec]:
    """Discover and parse all available tools from the tools directory."""
    tools = []
    tools_dir = Path(__file__).parent / "tools"
    
    # Import the tool registry to get actual implementations
    try:
        from .tools.registry import get_tool_registry
        registry = get_tool_registry()
    except ImportError:
        registry = {}
    
    # Load JSON specifications
    for json_file in tools_dir.glob("*.json"):
        if json_file.name == "__init__.py":
            continue
            
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                spec = json.load(f)
                
            tool_name = spec.get("name", json_file.stem)
            tool_class = spec.get("class", "environment_static")
            description = spec.get("description", "")
            
            # Generate syntax based on tool name
            if tool_name in ["view_will", "check_will", "view_notebook"]:
                syntax = f"</{tool_name}>"
            elif tool_name == "notebook":
                syntax = f"<{tool_name}>content</{tool_name}>"
            elif tool_name in ["whisper"]:
                syntax = f'<{tool_name} target="PlayerName">message</{tool_name}>'
            else:
                syntax = f"<{tool_name}>argument</{tool_name}>"
            
            # Extract examples if available
            examples = spec.get("examples", [])
            example_input = f"<{tool_name}>example</{tool_name}>" if not examples else str(examples[0].get("input", ""))
            example_output = "[Tool result]" if not examples else str(examples[0].get("output", ""))
            
            # Format examples better
            if tool_name == "view_will":
                example_input = "</view_will>"
                example_output = '[Your current will: "Investigated Player5 on Night 2, result was Town."]'
            elif tool_name in ["roles", "role_details", "get_role_details"]:
                example_input = "<roles>Bodyguard</roles>"
                example_output = "[Detailed information about the Bodyguard role.]"
            elif tool_name == "write_will":
                example_input = "<write_will>I healed Player3 on Night 2.</write_will>"
                example_output = "[Your will has been updated.]"
            elif tool_name == "chat_history":
                example_input = "<chat_history>Day1</chat_history>"
                example_output = "[Day 1 chat history: ...]"
            elif tool_name == "graveyard":
                example_input = "<graveyard>John</graveyard>"
                example_output = "[John (Mafioso) — died Day 1. Last Will: 'I'm not Mafia.']"
            elif tool_name == "notebook":
                example_input = "<notebook>Player3 seems suspicious</notebook>"
                example_output = "[Note added to notebook. Tokens used: 45/1500]"
            elif tool_name == "write_death_note":
                example_input = "<write_death_note>The Sheriff knows too much. -SK</write_death_note>"
                example_output = "[Death note updated (7/100 tokens).]"
            elif tool_name == "jailor_death_note":
                example_input = "<jailor_death_note>contradictory</jailor_death_note>"
                example_output = "[Execution reason set: Their confession was contradictory.]"
            
            tools.append(ToolSpec(
                name=tool_name,
                syntax=syntax,
                description=description,
                example_input=example_input,
                example_output=example_output,
                tool_class=tool_class
            ))
        except Exception as e:
            print(f"Warning: Could not parse tool {json_file}: {e}")
    
    # Filter tools based on role capabilities
    if role:
        filtered_tools = []
        for tool in tools:
            # Death note filtering
            if tool.name == "write_death_note":
                from .enums import RoleName
                death_note_roles = {
                    RoleName.GODFATHER, RoleName.MAFIOSO, RoleName.SERIAL_KILLER, 
                    RoleName.ARSONIST, RoleName.WEREWOLF, RoleName.JUGGERNAUT,
                    RoleName.COVEN_LEADER, RoleName.HEX_MASTER, RoleName.NECROMANCER,
                    RoleName.MEDUSA, RoleName.POISONER, RoleName.AMBUSHER
                }
                if hasattr(role, 'name') and role.name in death_note_roles:
                    filtered_tools.append(tool)
            elif tool.name == "jailor_death_note":
                from .enums import RoleName
                if hasattr(role, 'name') and role.name == RoleName.JAILOR:
                    filtered_tools.append(tool)
            else:
                # Include all other tools
                filtered_tools.append(tool)
        return filtered_tools
    
    return tools


def get_available_interactions(role: 'Role' = None) -> List[InteractionSpec]:
    """Get the standard interaction types available to agents, filtered by role abilities."""
    
    base_interactions = [
        InteractionSpec(
            name="speak",
            syntax="<speak>message</speak>",
            description="Sends the specified message to the public voice or chat channel. Replace 'message' with the content you wish to say. This message is visible to all players in the game.",
            example_input="<speak>I am not the Mafia, please do not vote for me.</speak>",
            example_output="[Your message has been sent to the public channel.]",
            phases_allowed=["Day Discussion", "Nomination", "Defense (if on trial only)", "Last Words (if being executed only)"]
        ),
        InteractionSpec(
            name="whisper",
            syntax='<whisper target="PlayerName">message</whisper>',
            description="Sends a private message to a specific player. Replace 'PlayerName' with the exact name of the recipient and 'message' with your intended content. Only the target player will receive this message. This is the only tag that uses an attribute for targeting.",
            example_input='<whisper target="Sarah">Trust me, I am on your side.</whisper>',
            example_output="[Your message has been privately delivered to Sarah.]",
            phases_allowed=["Day Discussion", "Nomination", "Defense", "Judgement", "some Night phases (role-dependent)"]
        ),
        InteractionSpec(
            name="vote",
            syntax="<vote>PlayerName</vote>",
            description="During nomination phase, nominates the specified player for trial. During judgement phase, use <vote>guilty</vote>, <vote>innocent</vote>, or <vote>abstain</vote>.",
            example_input="<vote>John</vote> or <vote>guilty</vote>",
            example_output="[Your vote has been recorded.]",
            phases_allowed=["Nomination", "Judgement"]
        ),
        InteractionSpec(
            name="wait",
            syntax="<wait></wait> or </wait>",
            description="Ends your current output without taking any action or sending a message. Can be used to indicate you are waiting or passing on this turn. Both <wait></wait> and </wait> are valid; use either form as appropriate.",
            example_input="</wait>",
            example_output="[No action taken; you are waiting.]",
            phases_allowed=["All phases"]
        )
    ]
    
    # Add role-specific ability interactions
    if role:
        role_interactions = get_role_specific_interactions(role)
        base_interactions.extend(role_interactions)
    
    return base_interactions


def get_role_specific_interactions(role: 'Role') -> List[InteractionSpec]:
    """Canonical role abilities for all ToS roles, using generic placeholders."""
    interactions = []
    if not hasattr(role, 'name'):
        return interactions
    role_name = role.name.value if hasattr(role.name, 'value') else str(role.name)

    # Town Investigative
    if role_name == "Sheriff":
        interactions.append(InteractionSpec(
            name="investigate",
            syntax="<investigate>Target</investigate>",
            description="NIGHT ABILITY: Interrogate a player for suspicious activity. Returns 'Suspicious' or 'Not Suspicious'.",
            example_input="<investigate>Target</investigate>",
            example_output="[You will investigate Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Investigator":
        interactions.append(InteractionSpec(
            name="investigate",
            syntax="<investigate>Target</investigate>",
            description="NIGHT ABILITY: Investigate a player to learn their possible roles.",
            example_input="<investigate>Target</investigate>",
            example_output="[You will investigate Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Lookout":
        interactions.append(InteractionSpec(
            name="watch",
            syntax="<watch>Target</watch>",
            description="NIGHT ABILITY: Watch a player to see who visits them.",
            example_input="<watch>Target</watch>",
            example_output="[You will watch Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Spy":
        interactions.append(InteractionSpec(
            name="bug",
            syntax="<bug>Target</bug>",
            description="NIGHT ABILITY: Bug a player to see who visits them and Mafia/Coven/other visits.",
            example_input="<bug>Target</bug>",
            example_output="[You will bug Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Tracker":
        interactions.append(InteractionSpec(
            name="track",
            syntax="<track>Target</track>",
            description="NIGHT ABILITY: Track a player to see who they visit.",
            example_input="<track>Target</track>",
            example_output="[You will track Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Psychic":
        interactions.append(InteractionSpec(
            name="vision",
            syntax="<vision></vision>",
            description="NIGHT ABILITY: Receive a vision of suspicious players (randomized).",
            example_input="<vision></vision>",
            example_output="[You receive a vision of three players.]",
            phases_allowed=["Night"]
        ))

    # Town Protective
    if role_name == "Doctor":
        interactions.append(InteractionSpec(
            name="heal",
            syntax="<heal>Target</heal>",
            description="NIGHT ABILITY: Heal a player, preventing their death. Self-heal once per game.",
            example_input="<heal>Target</heal>",
            example_output="[You are healing Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Bodyguard":
        interactions.append(InteractionSpec(
            name="protect",
            syntax="<protect>Target</protect>",
            description="NIGHT ABILITY: Protect a player, counterattacking their first attacker. You die in their place.",
            example_input="<protect>Target</protect>",
            example_output="[You are protecting Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Crusader":
        interactions.append(InteractionSpec(
            name="protect",
            syntax="<protect>Target</protect>",
            description="NIGHT ABILITY: Protect a player, killing one non-Town visitor.",
            example_input="<protect>Target</protect>",
            example_output="[You are protecting Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Trapper":
        interactions.append(InteractionSpec(
            name="trap",
            syntax="<trap>Target</trap>",
            description="NIGHT ABILITY: Place a trap on a player's house to protect them.",
            example_input="<trap>Target</trap>",
            example_output="[You are placing a trap at Target's house tonight.]",
            phases_allowed=["Night"]
        ))

    # Town Killing
    if role_name == "Jailor":
        interactions.extend([
            InteractionSpec(
                name="jail",
                syntax="<jail>Target</jail>",
                description="DAY ABILITY: Select a player to jail tonight (if executions remain).",
                example_input="<jail>Target</jail>",
                example_output="[You have jailed Target for tonight.]",
                phases_allowed=["Discussion", "Voting"]
            ),
            InteractionSpec(
                name="execute",
                syntax="<execute></execute>",
                description="NIGHT ABILITY: Execute the jailed target (max 3). Lose all executions if you kill Town.",
                example_input="<execute></execute>",
                example_output="[You will execute the jailed player.]",
                phases_allowed=["Night"]
            )
        ])
    if role_name == "Vigilante":
        interactions.append(InteractionSpec(
            name="shoot",
            syntax="<shoot>Target</shoot>",
            description="NIGHT ABILITY: Shoot a player (Basic Attack). Cannot shoot Night 1. Three bullets max.",
            example_input="<shoot>Target</shoot>",
            example_output="[You will shoot Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Veteran":
        interactions.append(InteractionSpec(
            name="alert",
            syntax="<alert></alert>",
            description="NIGHT ABILITY: Go on alert (Powerful Attack on visitors, Basic Defense). Three alerts total.",
            example_input="<alert></alert>",
            example_output="[You are going on alert tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Vampire Hunter":
        interactions.append(InteractionSpec(
            name="check",
            syntax="<check>Target</check>",
            description="NIGHT ABILITY: Check a player for vampirism. Kills vampires.",
            example_input="<check>Target</check>",
            example_output="[You will check Target tonight.]",
            phases_allowed=["Night"]
        ))

    # Town Support
    if role_name == "Retributionist":
        interactions.append(InteractionSpec(
            name="raise",
            syntax="<raise>Corpse,Target</raise>",
            description="NIGHT ABILITY: Raise a dead Town member to use their ability on a target. Each corpse usable once.",
            example_input="<raise>Corpse,Target</raise>",
            example_output="[You will raise Corpse to act on Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Escort":
        interactions.append(InteractionSpec(
            name="distract",
            syntax="<distract>Target</distract>",
            description="NIGHT ABILITY: Distract a player, role-blocking them for the night.",
            example_input="<distract>Target</distract>",
            example_output="[You will distract Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Transporter":
        interactions.append(InteractionSpec(
            name="transport",
            syntax="<transport>Target1,Target2</transport>",
            description="NIGHT ABILITY: Swap two players' locations for the night.",
            example_input="<transport>Target1,Target2</transport>",
            example_output="[You will transport Target1 and Target2 tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Medium":
        interactions.append(InteractionSpec(
            name="seance",
            syntax="<seance>Target</seance>",
            description="NIGHT ABILITY: Hold a seance to communicate with a dead player.",
            example_input="<seance>Target</seance>",
            example_output="[You will hold a seance with Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Mayor":
        interactions.append(InteractionSpec(
            name="reveal",
            syntax="<reveal></reveal>",
            description="DAY ABILITY: Reveal yourself as Mayor, tripling your vote power.",
            example_input="<reveal></reveal>",
            example_output="[You have revealed as Mayor.]",
            phases_allowed=["Discussion", "Voting"]
        ))

    # Mafia Killing/Support/Deception
    if role_name == "Godfather":
        interactions.append(InteractionSpec(
            name="kill",
            syntax="<kill>Target</kill>",
            description="NIGHT ABILITY: Order a Mafia kill on a player.",
            example_input="<kill>Target</kill>",
            example_output="[You will order a kill on Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Mafioso":
        interactions.append(InteractionSpec(
            name="kill",
            syntax="<kill>Target</kill>",
            description="NIGHT ABILITY: Perform a Mafia kill on a player.",
            example_input="<kill>Target</kill>",
            example_output="[You will kill Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Consort":
        interactions.append(InteractionSpec(
            name="distract",
            syntax="<distract>Target</distract>",
            description="NIGHT ABILITY: Distract a player, role-blocking them for the night.",
            example_input="<distract>Target</distract>",
            example_output="[You will distract Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Blackmailer":
        interactions.append(InteractionSpec(
            name="blackmail",
            syntax="<blackmail>Target</blackmail>",
            description="NIGHT ABILITY: Blackmail a player, preventing them from speaking the next day.",
            example_input="<blackmail>Target</blackmail>",
            example_output="[You will blackmail Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Framer":
        interactions.append(InteractionSpec(
            name="frame",
            syntax="<frame>Target</frame>",
            description="NIGHT ABILITY: Frame a player, making them appear suspicious to investigators.",
            example_input="<frame>Target</frame>",
            example_output="[You will frame Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Janitor":
        interactions.append(InteractionSpec(
            name="clean",
            syntax="<clean>Target</clean>",
            description="NIGHT ABILITY: Clean a player's role and will, hiding them from the Town if killed.",
            example_input="<clean>Target</clean>",
            example_output="[You will clean Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Disguiser":
        interactions.append(InteractionSpec(
            name="disguise",
            syntax="<disguise>Target</disguise>",
            description="NIGHT ABILITY: Disguise yourself as another player if they die tonight.",
            example_input="<disguise>Target</disguise>",
            example_output="[You will disguise as Target if they die tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Hypnotist":
        interactions.append(InteractionSpec(
            name="hypnotize",
            syntax="<hypnotize>Target</hypnotize>",
            description="NIGHT ABILITY: Hypnotize a player, making them see a fake message.",
            example_input="<hypnotize>Target</hypnotize>",
            example_output="[You will hypnotize Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Consigliere":
        interactions.append(InteractionSpec(
            name="investigate",
            syntax="<investigate>Target</investigate>",
            description="NIGHT ABILITY: Investigate a player to learn their exact role.",
            example_input="<investigate>Target</investigate>",
            example_output="[You will investigate Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Ambusher":
        interactions.append(InteractionSpec(
            name="ambush",
            syntax="<ambush>Target</ambush>",
            description="NIGHT ABILITY: Ambush a player, killing one visitor.",
            example_input="<ambush>Target</ambush>",
            example_output="[You will ambush Target tonight.]",
            phases_allowed=["Night"]
        ))

    # Coven roles
    if role_name == "Coven Leader":
        interactions.append(InteractionSpec(
            name="control",
            syntax="<control>Target1,Target2</control>",
            description="NIGHT ABILITY: Control Target1 to target Target2 (forces Target1 to act on Target2).",
            example_input="<control>Target1,Target2</control>",
            example_output="[You will control Target1 to target Target2 tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Hex Master":
        interactions.append(InteractionSpec(
            name="hex",
            syntax="<hex>Target</hex>",
            description="NIGHT ABILITY: Hex a player. If all living non-Coven are hexed, unleash a Hex Bomb.",
            example_input="<hex>Target</hex>",
            example_output="[You will hex Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Poisoner":
        interactions.append(InteractionSpec(
            name="poison",
            syntax="<poison>Target</poison>",
            description="NIGHT ABILITY: Poison a player. They will die the following night unless healed.",
            example_input="<poison>Target</poison>",
            example_output="[You will poison Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Potion Master":
        interactions.append(InteractionSpec(
            name="potion",
            syntax="<potion type>Target</potion>",
            description="NIGHT ABILITY: Use a potion (heal, reveal, attack) on a player. Each potion has a cooldown.",
            example_input="<potion heal>Target</potion>",
            example_output="[You will use a heal potion on Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Medusa":
        interactions.append(InteractionSpec(
            name="stone",
            syntax="<stone></stone>",
            description="NIGHT ABILITY: Turn visitors to stone (kill all who visit you). Only works if not on cooldown.",
            example_input="<stone></stone>",
            example_output="[You will turn visitors to stone tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Necromancer":
        interactions.append(InteractionSpec(
            name="raise",
            syntax="<raise>Corpse,Target</raise>",
            description="NIGHT ABILITY: Use a dead player's ability on a target. Each corpse usable once.",
            example_input="<raise>Corpse,Target</raise>",
            example_output="[You will use Corpse's ability on Target tonight.]",
            phases_allowed=["Night"]
        ))

    # Neutral Killing
    if role_name == "Serial Killer":
        interactions.append(InteractionSpec(
            name="kill",
            syntax="<kill>Target</kill>",
            description="NIGHT ABILITY: Kill a player. Immune to roleblocks unless jailed.",
            example_input="<kill>Target</kill>",
            example_output="[You will kill Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Arsonist":
        interactions.extend([
            InteractionSpec(
                name="douse",
                syntax="<douse>Target</douse>",
                description="NIGHT ABILITY: Douse a player in gasoline. Doused players can be ignited later.",
                example_input="<douse>Target</douse>",
                example_output="[You will douse Target tonight.]",
                phases_allowed=["Night"]
            ),
            InteractionSpec(
                name="ignite",
                syntax="<ignite></ignite>",
                description="NIGHT ABILITY: Ignite all doused players, killing them.",
                example_input="<ignite></ignite>",
                example_output="[You will ignite all doused players tonight.]",
                phases_allowed=["Night"]
            )
        ])
    if role_name == "Werewolf":
        interactions.append(InteractionSpec(
            name="rampage",
            syntax="<rampage>Target</rampage>",
            description="NIGHT ABILITY: Rampage at a player's house, killing all visitors and the target.",
            example_input="<rampage>Target</rampage>",
            example_output="[You will rampage at Target's house tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Juggernaut":
        interactions.append(InteractionSpec(
            name="attack",
            syntax="<attack>Target</attack>",
            description="NIGHT ABILITY: Attack a player. Gains new abilities as you kill more players.",
            example_input="<attack>Target</attack>",
            example_output="[You will attack Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Pestilence":
        interactions.append(InteractionSpec(
            name="attack",
            syntax="<attack>Target</attack>",
            description="NIGHT ABILITY: Unstoppable attack on a player.",
            example_input="<attack>Target</attack>",
            example_output="[You will attack Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Plaguebearer":
        interactions.append(InteractionSpec(
            name="infect",
            syntax="<infect>Target</infect>",
            description="NIGHT ABILITY: Infect a player with the plague. When all are infected, become Pestilence.",
            example_input="<infect>Target</infect>",
            example_output="[You will infect Target tonight.]",
            phases_allowed=["Night"]
        ))

    # Neutral Evil
    if role_name == "Witch":
        interactions.append(InteractionSpec(
            name="control",
            syntax="<control>Target1,Target2</control>",
            description="NIGHT ABILITY: Control Target1 to target Target2 (forces Target1 to act on Target2).",
            example_input="<control>Target1,Target2</control>",
            example_output="[You will control Target1 to target Target2 tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Executioner":
        interactions.append(InteractionSpec(
            name="frame",
            syntax="<frame>Target</frame>",
            description="DAY ABILITY: Frame your target to appear guilty if lynched (custom game modes).",
            example_input="<frame>Target</frame>",
            example_output="[You will frame Target today.]",
            phases_allowed=["Discussion", "Voting"]
        ))
    if role_name == "Jester":
        interactions.append(InteractionSpec(
            name="haunt",
            syntax="<haunt>Target</haunt>",
            description="NIGHT ABILITY: Haunt a player the night after you are lynched.",
            example_input="<haunt>Target</haunt>",
            example_output="[You will haunt Target tonight.]",
            phases_allowed=["Night"]
        ))

    # Neutral Benign
    if role_name == "Survivor":
        interactions.append(InteractionSpec(
            name="vest",
            syntax="<vest></vest>",
            description="NIGHT ABILITY: Put on a bulletproof vest for Basic Defense. Four vests per game.",
            example_input="<vest></vest>",
            example_output="[You will wear a vest tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Guardian Angel":
        interactions.append(InteractionSpec(
            name="protect",
            syntax="<protect>Target</protect>",
            description="NIGHT ABILITY: Protect your target from all attacks for one night.",
            example_input="<protect>Target</protect>",
            example_output="[You will protect Target tonight.]",
            phases_allowed=["Night"]
        ))
    if role_name == "Amnesiac":
        interactions.append(InteractionSpec(
            name="remember",
            syntax="<remember>Role</remember>",
            description="DAY ABILITY: Remember a dead role and become it.",
            example_input="<remember>Role</remember>",
            example_output="[You will remember Role and become it.]",
            phases_allowed=["Discussion", "Voting"]
        ))

    # Neutral Chaos
    if role_name == "Pirate":
        interactions.append(InteractionSpec(
            name="duel",
            syntax="<duel>Target,Weapon</duel>",
            description="NIGHT ABILITY: Duel a player, choosing Scimitar, Rapier, or Pistol.",
            example_input="<duel>Target,Scimitar</duel>",
            example_output="[You will duel Target with a Scimitar tonight.]",
            phases_allowed=["Night"]
        ))

    # Add more as needed for completeness
    return interactions


# ---------------------------------------------------------------------------
# Role Card System
# ---------------------------------------------------------------------------

@dataclass
class RoleCard:
    """Complete role card information for prompt building."""
    name: str
    faction: str
    alignment: str
    win_condition: str
    passive_abilities: List[str] = field(default_factory=list)
    active_abilities: List[str] = field(default_factory=list)
    attack: str = "None"
    defense: str = "None"
    visit_type: str = "Non-harmful"
    immunities: List[str] = field(default_factory=list)
    unique: bool = False


def build_role_card(role: 'Role') -> RoleCard:
    """Return a fully-accurate role card for Town of Salem."""
    info = role.get_info() if hasattr(role, "get_info") else {}
    role_name = info.get("name", str(role.name.value) if hasattr(role, 'name') else "Unknown")

    win_conditions = {
        "TOWN": "Eliminate all threats to the Town.",
        "MAFIA": "Kill anyone that will not submit to the Mafia.",
        "NEUTRAL": "Achieve your specific role objective.",
        "COVEN": "Kill all who would oppose the Coven."
    }

    faction = info.get("faction", getattr(role, "faction", "Unknown"))
    faction_str = faction.name if hasattr(faction, 'name') else str(faction)
    win_condition = win_conditions.get(faction_str, "Achieve your role's specific objective.")

    active_abilities, passive_abilities = [], []

    if role_name == "Doctor":
        active_abilities = ["NIGHT ABILITY: <heal>player</heal> – Heal one person (Powerful Defense). Self-heal once."]
        passive_abilities = ["Defense: None", "Visit Type: Non-harmful"]
    elif role_name == "Sheriff":
        active_abilities = ["NIGHT ABILITY: <investigate>player</investigate> – Returns 'Suspicious' or 'Not Suspicious'."]
        passive_abilities = ["Defense: None", "Visit Type: Non-harmful"]
    elif role_name == "Jailor":
        active_abilities = [
            "DAY ABILITY: <jail>player</jail> – Select a prisoner for the coming night.",
            "NIGHT ABILITY: <execute></execute> – Execute jailed target (3 uses; lose them all if you kill Town)."
        ]
        passive_abilities = ["Defense: None", "Prisoner cannot act or speak publicly"]
    elif role_name == "Bodyguard":
        active_abilities = ["NIGHT ABILITY: <protect>player</protect> – Grant Basic Defense and counterattack with Powerful Attack; you die in their place."]
        passive_abilities = ["Defense: Basic", "Counterattack ignores Basic Defense"]
    elif role_name == "Vigilante":
        active_abilities = ["NIGHT ABILITY: <shoot>player</shoot> – Basic Attack, 3 bullets, cannot shoot Night 1."]
        passive_abilities = ["Attack: Basic", "Defense: None"]
    elif role_name == "Veteran":
        active_abilities = ["NIGHT ABILITY: <alert></alert> – Powerful Attack on visitors, Basic Defense, 3 alerts."]
        passive_abilities = ["Off-alert Defense: None"]

    return RoleCard(
        name=role_name,
        faction=faction,
        alignment=info.get("alignment", getattr(role, "alignment", "Unknown")),
        win_condition=win_condition,
        passive_abilities=passive_abilities,
        active_abilities=active_abilities,
        attack=info.get("attack", getattr(role, "attack", "None")),
        defense=info.get("defense", getattr(role, "defense", "None")),
        visit_type=getattr(role, "visit_type", "Non-harmful"),
        immunities=getattr(role, "immunities", []),
        unique=info.get("is_unique", getattr(role, "is_unique", False)))


# ---------------------------------------------------------------------------
# Phase Information System
# ---------------------------------------------------------------------------
def get_phase_brief(game: 'Game', actor: 'Player') -> str:
    """Return dynamic instructions for the current phase."""
    phase_key = PHASE_NAME_MAP.get(getattr(game, "phase", None))
    if not phase_key:
        return ""
    info = PHASES_DATA.get(phase_key, {})
    lines: List[str] = []

    if description := info.get("description"):
        lines.append(f"{phase_key} – {description}")

    activities = info.get("activities", [])
    if activities:
        lines.append("Activities:")
        lines.extend(f"• {act}" for act in activities)

    mechanics = info.get("mechanics", [])
    if mechanics:
        lines.append("Mechanics:")
        lines.extend(f"• {m}" for m in mechanics)

    # Add explicit voting instructions for Nomination and Judgement phases
    if phase_key == "Nomination":
        lines.append("\nTo nominate a player for trial, use <vote>PlayerName</vote>. A majority vote will send that player to the stand. Choose wisely—nominating the right suspect is key to Town victory, but evils may try to mislead the vote.")
    elif phase_key == "Judgement":
        lines.append("\nVote <vote>guilty</vote>, <vote>innocent</vote>, or <vote>abstain</vote> to decide the fate of the accused. Guilty votes will execute, innocent votes will spare, and abstain means you do not influence the outcome. Your vote can decide the game—read the defense and vote with conviction.")

    role_interactions = get_role_specific_interactions(actor.role)
    allowed: List[str] = []
    phase_norm = phase_key.lower().replace("-", " ")
    for inter in role_interactions:
        for allowed_phase in inter.phases_allowed:
            norm = allowed_phase.lower().replace("-", " ")
            if norm == "all phases" or norm == phase_norm or (
                phase_norm == "night" and "night" in norm
            ):
                allowed.append(inter.syntax)
                break
    if allowed:
        lines.append("Role abilities usable now:")
        lines.extend(f"• {syntax}" for syntax in allowed)

    return "\n".join(lines)

def get_phase_rules() -> str:
    """Canonical Town of Salem phase rules, now including the Pre‑Night chat window."""
    return """PHASE RULES (PLAIN TEXT, XML‑FRIENDLY, ACTION‑DRIVEN)

Day phases:

• Discussion
  – All living players may <speak>, <whisper target="Player">, or </wait>.
  – No voting yet; wills and notebooks may be viewed or edited.
  – Dead chat is hidden from the living.

• Nomination
  – Use <vote>Player</vote> to place an up‑vote. A simple majority sends that player to trial.
  – Public chat and whispers stay open; <vote>guilty</vote> / <vote>innocent</vote> *not* allowed here.

• Defense
  – Only the accused may <speak>. Others may still <whisper> or </wait>.
  – No further votes or tool use unless the tool is explicitly Day‑unrestricted.

• Judgement
  – All living players except the accused must cast <vote>guilty</vote>,
    <vote>innocent</vote>, or <vote>abstain</vote>.
  - You can change your vote by selecting another option.
  – Public <speak> disabled; whispers (day‑only) remain legal; wills still editable.

• Last Words
  – The condemned alone may <speak> a single closing message.
  – No other public messages or whispers. Wills cannot be changed in this window.

• Pre‑Night  
  – A brief twilight (small token budget) before Night begins.  
  – **All living players** may <speak>, <whisper target="Player">, or </wait>.  
  – No voting, no night abilities, but wills/notes can still be viewed or edited.  
  – Use this window to coordinate last‑second plans before actions lock in.

Night phase:

• Night
  – Roles with night abilities may act (e.g., <heal>, <protect>, <shoot>).
  – Public <speak> disabled. Only faction chats (Mafia, Coven, etc.) and the Jailor’s cell allow talking.
  – <whisper> is **not** available at night.
  – Living players may still view or update their will/notebook before committing an action.

Game end
--------

• Victory screen follows when one faction fulfils its win condition.
• No further actions are accepted once the result is displayed.
"""


def get_real_time_warning() -> str:
    """Get the real-time play warning text."""
    return """Real-Time Play:
The game operates in real-time. This means that as you spend time thinking or generating your response, the game continues and other players may act, send messages, or perform actions during this period.

Each time you generate output, any events or changes in the environment that occurred while you were thinking will be injected into your context as new information. The longer your <think> block or your reasoning, the more time will pass in the game, and the more the environment may have changed by the time you are ready to act.

Therefore, you should balance the thoroughness of your reasoning with the need to respond in a timely manner, as excessive delays may cause you to miss important developments or opportunities. This applies to your entire generation time, not just thinking but also speaking for long amounts of time."""


# ---------------------------------------------------------------------------
# System Prompt Builder
# ---------------------------------------------------------------------------

def get_ordered_system_prompt_sections(agent_name, role_card, game, tools, interactions, reasoning_protocol):
    sections = []
    # 0. Explicit phase, day, and time info
    phase = getattr(game, 'phase', None)
    phase_name = phase.name if phase and hasattr(phase, 'name') else str(phase)
    day_num = getattr(game, 'day', 1)
    time_name = getattr(game, 'time', None)
    time_str = time_name.name if time_name and hasattr(time_name, 'name') else str(time_name)
    sections.append(f"Current Phase: {phase_name} | Day: {day_num} | Time: {time_str}")
    # 0.1 Game mode and role list
    game_mode = getattr(getattr(game, 'config', None), 'game_mode', None)
    if not game_mode and hasattr(game, 'config'):
        game_mode = getattr(game.config, 'mode', None)
    role_list = getattr(getattr(game, 'config', None), 'role_list', None)
    sections.append(f"Game Mode: {game_mode if game_mode else 'Unknown'}")
    if role_list:
        sections.append("Role List:\n" + "\n".join(f"- {r}" for r in role_list))
    # 1. Header
    sections.append(f"Your name is {agent_name}. You are a {role_card.name}.")
    # 2. Role Card
    sections.append(f"""Role: {role_card.name}
Alignment: {role_card.alignment}
Faction: {role_card.faction}
Win Condition: {role_card.win_condition}""")
    if role_card.passive_abilities:
        sections.append("Passive Abilities:\n" + "\n".join(f"• {ability}" for ability in role_card.passive_abilities))
    if role_card.active_abilities:
        sections.append("Active Abilities:\n" + "\n".join(f"• {ability}" for ability in role_card.active_abilities))
    # 3. Game Overview
    game_overview = f"""You are a highly competitive agent playing a game called Town of Salem. Town of Salem is an online social deduction game played between multiple participants, each of whom is randomly assigned a secret role belonging to a particular faction (e.g, Town, Mafia, Neutral, Coven). The game is structured in alternating night and day phases. During the day, players communicate publicly and vote to lynch others. During the night, some roles may perform actions. Your role and win condition are defined below. The rules, possible actions, and public information are available to you. Players may communicate, collaborate, deceive, or withhold information as they choose, according to their individual strategies and goals. Engage with the game as an ordinary player, utilizing your knowledge of the rules, your observations and your reasoning to make decisions. Do not reference being an AI or model. You are a player. When reasoning, planning, or gathering your internal thoughts, you must use the <think> and </think> tags. Everything inside <think> and </think> is private, internal reasoning and must never be revealed to other players. Use this space to analyze the situation, consider possibilities, or plan your next actions. You must complete your internal thought and close with </think> before using any tools or taking any action.\n\nAfter finishing your internal reasoning with </think>, you may interact with the environment. This can include issuing public statements, casting votes, or using one of the tools available to you. You may only use tools after you have finished your internal thought. Never use a tool or act while inside a <think> block. Always separate your reasoning and your actions in this way. Your only objective is to win the game. You are playing to win."""
    sections.append(game_overview)
    # 4. COMPRESSED STRATEGY SECTIONS
    sections.append("""
[GENERAL RULES]
# Add compressed general rules and tool usage instructions here.

[TOWN STRATEGY]
# Add compressed Town strategy and behavior here.

[EVIL STRATEGY]
# Add compressed Mafia/Coven/Vampire strategy and behavior here.

[NEUTRAL STRATEGY]
# Add compressed Neutral role strategy and behavior here.

[PLAY HUMAN]
# Add compressed persona/human-like play instructions here.
""")
    # 5. Internal Reasoning Protocol
    sections.append(reasoning_protocol)
    # 6. Tools Section
    tools_text = "The tools available to you are:\n"
    for tool in tools:
        if tool.name == "alignment":
            tool.description = "Returns the alignment (Town, Mafia, Neutral, etc.) for a given ROLE NAME, not a player. Example: <alignment>Investigator</alignment>. Use <help>alignment</help> to see all valid alignments."
            tool.example_input = "<alignment>Investigator</alignment>"
            tool.example_output = "[Alignment: Town Investigative]"
        elif tool.name == "attributes":
            tool.description = "Returns the attributes (attack, defense, immunities, etc.) for a given ROLE NAME, not a player. Example: <attributes>Bodyguard</attributes>. Use <help>attributes</help> to see all valid attributes."
            tool.example_input = "<attributes>Bodyguard</attributes>"
            tool.example_output = "[Attributes: Basic Defense, Non-harmful Visit, etc.]"
        tools_text += f"\nTool: {tool.syntax}\n"
        tools_text += f"Description: {tool.description}\n"
        tools_text += f"Example input: {tool.example_input}\n"
        tools_text += f"Example output: {tool.example_output}\n"
    tools_text += "\nTool: <help>ToolName</help>\nDescription: Returns all valid arguments for the specified tool. Example: <help>attributes</help> or <help>alignment</help>.\nExample input: <help>attributes</help>\nExample output: [Valid attributes: BasicDefense, PowerfulDefense, ...]"
    sections.append(tools_text)
    # 7. Interactions Section
    interactions_text = "The interactions available to you are:\n"
    for interaction in interactions:
        interactions_text += f"\nInteraction: {interaction.syntax}\n"
        interactions_text += f"Description: {interaction.description}\n"
        interactions_text += f"Example input: {interaction.example_input}\n"
        interactions_text += f"Example output: {interaction.example_output}\n"
    sections.append(interactions_text)
    # 8. Phase Rules
    sections.append(get_phase_rules())
    # 9. Real-Time Warning
    sections.append(get_real_time_warning())
    return sections


def build_system_prompt(agent_name: str, role: 'Role', game: 'Game') -> str:
    """Build the complete static system prompt."""
    role_card = build_role_card(role)
    tools = discover_tools(role)
    interactions = get_available_interactions(role)
    reasoning_protocol = """The following tools are available to you. Each tool must be invoked in the format provided, outside of the <think> block, and only after you have finished your thought. After you finish a <think> block and use a tool, the result of the tool will be provided to you as new information. Each time you receive new information from a tool or from the environment, you must start a new <think> block to process and reflect on the information you have just received. Only after reasoning in this way should you decide whether to use another tool, interact with the environment, or take no action. You must always alternate between thinking in <think> and </think> and then acting, never chaining together multiple tool uses or environment interactions in a single step. After each action, always wait for the outcome before thinking again and choosing your next move."""
    sections = get_ordered_system_prompt_sections(agent_name, role_card, game, tools, interactions, reasoning_protocol)
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# User Prompt Builder
# ---------------------------------------------------------------------------

def build_user_prompt(game: 'Game', actor: 'Player', tokens_remaining: int | None = None) -> str:
    """Build the dynamic user prompt for the current turn."""
    
    sections = []
    
    # Death status (for dead players)
    if not actor.is_alive:
        sections.append("🪦 YOU HAVE DIED 🪦\nYou are now a ghost observer. You cannot use most tools or interact with living players, but you can still observe the game.")
    
    # Phase and day information
    phase_name = game.phase.name.title() if hasattr(game, 'phase') else "Unknown"
    day_num = getattr(game, 'day', 1)
    token_str = f"Unlimited" if tokens_remaining is None else str(tokens_remaining)
    sections.append(f"Phase: {game.time.name.title()} {day_num} - {phase_name} (Tokens remaining: {token_str})")
    phase_brief = get_phase_brief(game, actor)
    if phase_brief:
        sections.append(phase_brief)
    # Verdict Tally (only during Judgement)
    if game.phase == Phase.JUDGEMENT and game.current_trial():
        guilty_votes, innocent_votes = game.verdict_tally()
        sections.append(f"Player on Trial: {game.current_trial().name} | Guilty: {guilty_votes} | Innocent: {innocent_votes}")

    # Alive roster
    from .enums import Faction
    actor_faction = getattr(actor.role, 'faction', None)
    show_roles = actor_faction in [Faction.MAFIA, Faction.COVEN]

    alive_player_lines = []
    for p in sorted(game.players, key=lambda x: x.id):
        if p.is_alive:
            player_line = f"- {p.name}"
            
            # Show faction roles
            if show_roles and getattr(p.role, 'faction', None) == actor_faction:
                role_name = p.role.name.value if hasattr(p.role.name, 'value') else str(p.role.name)
                player_line += f" ({role_name})"

            # Show nomination counts
            if game.phase == Phase.NOMINATION:
                count = game.nomination_counts().get(p, 0)
                if count > 0:
                    player_line += f" [{count}]"
            
            alive_player_lines.append(player_line)
    
    sections.append("Alive Roster\n" + "\n".join(alive_player_lines))
    
    # Graveyard
    if hasattr(game, 'graveyard') and game.graveyard:
        graveyard_text = "Graveyard\n"
        for dead_player in game.graveyard:
            role_name = dead_player.role.name.value if hasattr(dead_player.role.name, 'value') else str(dead_player.role.name)
            
            # Determine display text
            display_info = f"({role_name})"
            if getattr(dead_player, 'was_cleaned', False) and dead_player.cleaned_by != actor:
                display_info = "(Cleaned)"
            elif getattr(dead_player, 'was_stoned', False):
                display_info = "(Stoned)"

            graveyard_text += f"- {dead_player.name} {display_info}\n"
        sections.append(graveyard_text.rstrip())
    
    # Visible chat messages
    visible_messages = game.chat.get_visible_messages(actor)
    if visible_messages:
        chat_text = "Chat Log\n"
        for msg in visible_messages:
            chat_text += f"{msg}\n"
        sections.append(chat_text.rstrip())

    # Jailed status
    if actor.is_jailed:
        sections.append("You have been hauled off to jail!")

    # Agent's own recent history
    if hasattr(actor, 'thought_and_action_history') and actor.thought_and_action_history:
        history_text = "--- Your Recent Thoughts and Actions ---\n"
        # Show the last 3 entries for brevity
        for entry in actor.thought_and_action_history[-3:]:
            history_text += f"{entry}\n"
        sections.append(history_text.rstrip())
    
    return "\n\n".join(sections)


def build_notebook_observation(actor: 'Player') -> str:
    """Build notebook observation section."""
    if hasattr(actor, 'notebook') and actor.notebook:
        notebook_tokens = getattr(actor, 'notebook_tokens', 0)
        return f"----------Notebook {notebook_tokens}/1500 tokens used-------------\n{actor.notebook}"
    else:
        return "----------Notebook 0/1500 tokens used-------------\n(Empty)"


def build_environment_static_observations(actor: 'Player', tools_used: List[str] = None) -> str:
    """Build combined environment_static tool observations."""
    if not tools_used:
        return ""
    
    # This would be populated with actual tool results in a real implementation
    # For now, return a placeholder that shows which tools were used
    observations = []
    for tool_name in tools_used:
        observations.append(f"[Previous {tool_name} result cached]")
    
    return "\n".join(observations)


# ---------------------------------------------------------------------------
# Main Prompt Building Function
# ---------------------------------------------------------------------------

def build_complete_prompt(game: 'Game', actor: 'Player', model_name: str = "default", tokens_remaining: int | None = None) -> str:
    """Build the complete prompt for an agent using model-specific formatting."""
    
    # Get model configuration
    model_config = get_model_config(model_name)
    
    # Build system and user prompts
    system_prompt = build_system_prompt(actor.name, actor.role, game)
    user_prompt = build_user_prompt(game, actor, tokens_remaining)
    
    # Build observation sections
    notebook_obs = build_notebook_observation(actor)
    
    # Build environment_static observations if any tools have been used
    env_static_obs = None
    if hasattr(actor, 'environment_static_tools_used') and actor.environment_static_tools_used:
        env_static_obs = build_environment_static_observations(actor, list(actor.environment_static_tools_used))
    
    # Format according to model requirements
    return model_config.format_messages(system_prompt, user_prompt, notebook_obs, env_static_obs)


# ---------------------------------------------------------------------------
# Legacy Compatibility Functions
# ---------------------------------------------------------------------------

def build_game_prompt(game: 'Game', actor: 'Player', observation: Optional[str] = None) -> str:
    """Legacy compatibility function."""
    return build_complete_prompt(game, actor)


def build_prompt(game: 'Game', actor: 'Player', observation: Optional[str] = None) -> str:
    """Legacy function - use build_complete_prompt instead."""
    return build_complete_prompt(game, actor, "default")


def build_training_prompt(game: 'Game', actor: 'Player', model_name: str = "default") -> str:
    """
    Build a training prompt for GRPO training.
    
    Uses the same comprehensive prompt as the actual game since:
    - TurnBatcher handles batching and token management
    - 15 agents act at a time in batches
    - Token limits still determine phase transitions
    - No need to simplify prompts for training
    """
    return build_complete_prompt(game, actor, model_name) 