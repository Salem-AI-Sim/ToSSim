from __future__ import annotations

"""Tool registry and simple execution router.

This module is responsible for:
1. Loading every `*.json` file in the same directory and exposing their
   contents via :pyfunc:`get_tool_registry`.
2. Providing a minimal dispatch layer so the game loop (or test harness)
   can execute a tool call given a tag name and raw argument string.

Only the **few** tools required for current prototypes are implemented.  When
new tool JSON files are added you simply need to extend
:pydata:`_TOOL_EXECUTORS` with a callable that accepts the raw argument string
and returns a *string* (what will be placed inside an `<observation>` tag).
"""

from pathlib import Path
import json
from typing import Callable, Dict, Any

TOOLS_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

# Tool registry - replaces JSON file discovery for better maintainability
_TOOL_REGISTRY = {
    # Role information tools (role system integration and JSON data loading)
    "get_role": {"name": "get_role", "class": "environment_static"},
    "roles": {"name": "roles", "class": "environment_static"},  # <- renamed tool
    "role_details": {"name": "role_details", "class": "environment_static"},  # legacy alias
    "attributes": {"name": "attributes", "class": "environment_static"},
    
    # Dynamic game state tools (these query live game state)
    "chat_history": {"name": "chat_history", "class": "environment_static"},
    "graveyard": {"name": "graveyard", "class": "environment_static"},
    "check_will": {"name": "check_will", "class": "environment_static"},
    "view_will": {"name": "view_will", "class": "environment_static"},
    "get_time": {"name": "get_time", "class": "environment_static"},
    "notebook": {"name": "notebook", "class": "environment_terminal"},
    "view_notebook": {"name": "view_notebook", "class": "environment_static"},
    "get_executable_actions": {"name": "get_executable_actions", "class": "environment_static"},
    "action_history": {"name": "action_history", "class": "environment_static"},
    "write_will": {"name": "write_will", "class": "environment_static"},
    "write_death_note": {"name": "write_death_note", "class": "environment_static"},
    "jailor_death_note": {"name": "jailor_death_note", "class": "environment_static"},
    "investigation_results": {"name": "investigation_results", "class": "environment_static"},
    "evil_investigation_results": {"name": "evil_investigation_results", "class": "environment_static"},
    "victory_conditions": {"name": "victory_conditions", "class": "environment_static"},
    "gamemodes": {"name": "gamemodes", "class": "environment_static"},
    "alignments": {"name": "alignments", "class": "environment_static"},
    "phases": {"name": "phases", "class": "environment_static"},
}

def _load_data_json(filename: str) -> dict[str, Any]:
    """Load JSON data files (roles.json, attributes.json) that contain actual game data."""
    path = TOOLS_DIR / filename
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

_TOOL_SPECS = _TOOL_REGISTRY.copy()

# ---------------------------------------------------------------------------
# Concrete executors
# ---------------------------------------------------------------------------


def _exec_get_role(argument: str) -> str:
    """Return public details of a role.

    The implementation instantiates the corresponding Role class (if found)
    and converts it into the lightweight RoleCard representation from
    :pymod:`inference.templates.prompt_builder`.
    """
    from Simulation.enums import RoleName  # imported lazily to avoid circulars
    from Simulation.roles import role_map  # noqa: WPS433
    from inference.templates.prompt_builder import build_role_card  # noqa: WPS433

    role_name_clean = argument.strip()
    try:
        role_enum = RoleName(role_name_clean)
    except ValueError:
        # Try fuzzy match (case-insensitive exact string)
        matches = [e for e in RoleName if e.value.lower() == role_name_clean.lower()]
        if not matches:
            return f"No role named '{role_name_clean}'."
        role_enum = matches[0]

    role_cls = role_map.get(role_enum)
    if role_cls is None:
        return f"Role '{role_name_clean}' not implemented in simulator."

    role_instance = role_cls()
    role_card = build_role_card(role_instance)
    # JSON-encode for a structured observation but keep it human-readable.
    return json.dumps({"role_info": role_card.to_dict()}, indent=2)


def _exec_chat_history(argument: str, *, game=None, player=None) -> str:
    """Return chat history for a specific day or night.
    
    Usage: <chat_history>Day1</chat_history> or <chat_history>Night2</chat_history>
    """
    if not game or not player:
        return "Error: chat history lookup requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    arg_clean = argument.strip().replace(" ", "").replace("_", "").lower()
    
    # Parse the day/night number
    if arg_clean.startswith("day"):
        try:
            day_num = int(arg_clean[3:])
            is_night = False
        except ValueError:
            return "Error: Invalid day format. Use 'Day1', 'Day2', etc."
    elif arg_clean.startswith("night"):
        try:
            night_num = int(arg_clean[5:])
            is_night = True
            # Night N corresponds to game.day = N (not N-1)
            # Night 1 happens during game.day=1, Night 2 during game.day=2, etc.
            day_num = night_num
        except ValueError:
            return "Error: Invalid night format. Use 'Night1', 'Night2', etc."
    else:
        return "Error: Format must be 'Day1', 'Day2', 'Night1', 'Night2', etc."
    
    # Check if the requested period is before current day - 1 (history only)
    if game.day <= 1:
        return "Error: No previous chat history available yet."
    
    if day_num >= game.day:
        return "Error: Cannot view chat history from current or future periods."
    
    # Get chat history from the ChatManager
    return game.chat.get_chat_history(player, day_num, is_night)


def _exec_graveyard(argument: str, *, game=None, player=None) -> str:
    """Return detailed information about a dead player.
    
    Usage: <graveyard>PlayerName</graveyard>
    """
    if not game or not player:
        return "Error: graveyard lookup requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    player_name = argument.strip()
    if not player_name:
        return "Error: You must specify a player name."
    
    # Find the dead player
    dead_player = None
    for p in game.graveyard:
        if p.name.lower() == player_name.lower():
            dead_player = p
            break
    
    if not dead_player:
        return f"Error: No dead player named '{player_name}' found in the graveyard."
    
    # Build detailed death information
    result = f"{dead_player.name} was found dead.\n"
    result += f"They were a {dead_player.role.name.value}.\n\n"
    
    # Add cause of death information
    if dead_player.was_lynched:
        result += "Cause of Death: Lynched by the Town.\n\n"
    elif dead_player.killed_by:
        # Get a human-readable death cause
        killer = dead_player.killed_by
        death_messages = {
            "Mafioso": "Killed by the Mafia",
            "Godfather": "Killed by the Mafia", 
            "Ambusher": "Killed by the Mafia",
            "Serial Killer": "Killed by a Serial Killer",
            "Werewolf": "Mauled by a Werewolf",
            "Arsonist": "Killed in an arson",
            "Juggernaut": "Killed by a Juggernaut",
            "Coven Leader": "Killed by the Coven",
            "Hex Master": "Killed by the Coven",
            "Medusa": "Killed by the Coven", 
            "Necromancer": "Killed by the Coven",
            "Poisoner": "Killed by the Coven",
            "Potion Master": "Killed by the Coven",
            "Vampire": "Killed by a Vampire",
            "Vigilante": "Shot by a Vigilante",
            "Veteran": "Shot by a Veteran",
            "Jailor": "Executed by the Jailor",
            "Bodyguard": "Killed while protecting someone",
            "Crusader": "Killed by a Crusader",
            "Pirate": "Killed by a Pirate",
            "Pestilence": "Killed by Pestilence",
        }
        cause = death_messages.get(killer.role.name.value, f"Killed by {killer.role.name.value}")
        result += f"Cause of Death: {cause}.\n\n"
    else:
        # Check research metrics for death cause
        death_cause = dead_player.research_metrics.get('death_cause', 'unknown')
        if death_cause == 'executed':
            result += "Cause of Death: Executed by the Jailor.\n\n"
        elif death_cause == 'haunted':
            result += "Cause of Death: Haunted by a Jester.\n\n"
        else:
            result += "Cause of Death: Unknown.\n\n"
    
    # Add death note if available
    if dead_player.killer_death_note:
        result += f"Death Note: {dead_player.killer_death_note}\n\n"
    
    # Add will information if available
    if hasattr(dead_player, 'was_cleaned') and dead_player.was_cleaned:
        result += "Will: Their will was cleaned and could not be found."
    elif hasattr(dead_player, 'was_forged') and dead_player.was_forged:
        result += "Will: Their will was forged by a member of the Mafia."
    elif hasattr(dead_player, 'last_will_bloodied') and dead_player.last_will_bloodied:
        result += "Will: Their will was too bloody to read."
    elif dead_player.last_will:
        result += f"Will: {dead_player.last_will}"
    else:
        result += "Will: No will was found."
    
    return result


def _exec_check_will(argument: str, *, game=None, player=None) -> str:
    """Return the current player's last will.
    
    Usage: <check_will></check_will> or <check_will>self</check_will>
    """
    if not game or not player:
        return "Error: will check requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    if player.last_will:
        return f"Your current last will:\n{player.last_will}"
    else:
        return "You have not written a last will yet."


def _exec_view_will(argument: str, *, game=None, player=None) -> str:
    """Return a dead player's last will.
    
    Usage: <view_will>DeadPlayerName</view_will>
    """
    if not game or not player:
        return "Error: will viewing requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    player_name = argument.strip()
    if not player_name:
        return "Error: You must specify a player name."
    
    # Find the dead player
    dead_player = None
    for p in game.graveyard:
        if p.name.lower() == player_name.lower():
            dead_player = p
            break
    
    if not dead_player:
        return f"Error: No dead player named '{player_name}' found."
    
    # Check if will is viewable
    if hasattr(dead_player, 'was_cleaned') and dead_player.was_cleaned:
        return f"{dead_player.name}'s will was cleaned and cannot be read."
    elif hasattr(dead_player, 'was_forged') and dead_player.was_forged:
        return f"{dead_player.name}'s will was forged by a member of the Mafia."
    elif hasattr(dead_player, 'last_will_bloodied') and dead_player.last_will_bloodied:
        return f"{dead_player.name}'s will was too bloody to read."
    elif dead_player.last_will:
        return f"{dead_player.name}'s last will:\n{dead_player.last_will}"
    else:
        return f"{dead_player.name} did not leave a will."


def _exec_get_time(argument: str, *, game=None, player=None) -> str:
    """Return remaining tokens in the current phase.
    
    Usage: <get_time></get_time>
    """
    if not game or not player:
        return "Error: time lookup requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    # TODO: Implement actual token tracking
    # For now, return a placeholder value
    remaining_tokens = 250  # Placeholder
    phase_name = f"{game.time.name} {game.phase.name}" if hasattr(game, 'phase') else game.time.name
    
    return f"{remaining_tokens} tokens remaining in {phase_name} phase."


def _exec_notebook(argument: str, *, game=None, player=None) -> str:
    """Write to the player's private notebook.
    
    Usage: <notebook>Note content here</notebook>
    """
    if not game or not player:
        return "Error: notebook requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    content = argument.strip()
    if not content:
        return "Error: Cannot write empty note to notebook."
    
    from Simulation.tokenizer_utils import count_tokens, remove_tokens_from_start
    
    # Count tokens in new content
    new_tokens = count_tokens(content)
    
    # Check if adding would exceed limit
    NOTEBOOK_LIMIT = 1500
    total_after_addition = player.notebook_tokens + new_tokens
    
    if total_after_addition > NOTEBOOK_LIMIT:
        # FIFO sliding window - remove excess tokens from the beginning
        tokens_to_remove = total_after_addition - NOTEBOOK_LIMIT
        player.notebook, removed_tokens = remove_tokens_from_start(player.notebook, tokens_to_remove)
        player.notebook_tokens -= removed_tokens
    
    # Add new content
    if player.notebook:
        player.notebook += "\n" + content
    else:
        player.notebook = content
    player.notebook_tokens += new_tokens
    
    # Recalculate actual tokens in case of encoding differences
    actual_tokens = count_tokens(player.notebook)
    player.notebook_tokens = actual_tokens
    
    # Warning message at 85% full
    warning = ""
    if player.notebook_tokens >= int(NOTEBOOK_LIMIT * 0.85):
        warning = "\nWarning: Notebook is 85% full. Consider summarizing old notes as they will be forgotten gradually when the limit is reached."
    
    return f"Note added to notebook. Tokens used: {player.notebook_tokens}/{NOTEBOOK_LIMIT}{warning}"


def _exec_view_notebook(argument: str, *, game=None, player=None) -> str:
    """View the player's private notebook.
    
    Usage: <view_notebook></view_notebook>
    """
    if not game or not player:
        return "Error: notebook viewing requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    from Simulation.tokenizer_utils import count_tokens
    
    NOTEBOOK_LIMIT = 1500
    
    # Ensure token count is accurate
    if player.notebook:
        player.notebook_tokens = count_tokens(player.notebook)
    
    if not player.notebook:
        return f"Notebook (0/{NOTEBOOK_LIMIT} tokens):\n\n(Empty)"
    
    return f"Notebook ({player.notebook_tokens}/{NOTEBOOK_LIMIT} tokens):\n\n{player.notebook}"


def _exec_get_executable_actions(argument: str, *, game=None, player=None) -> str:
    """Return valid terminal actions for the current phase.
    
    Usage: <get_executable_actions></get_executable_actions>
    """
    if not game or not player:
        return "Error: action lookup requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    from Simulation.enums import Time, Phase
    
    # Day actions
    if game.time == Time.DAY:
        day_actions = ["speak", "wait"]
        
        # Add voting actions if not in defense/judgement
        if game.phase != Phase.DEFENSE and game.phase != Phase.JUDGEMENT:
            day_actions.extend(["vote", "nominate", "whisper"])
        
        # Role-specific day actions
        if player.role.name.value == "Mayor" and not getattr(player.role, 'revealed', False):
            day_actions.append("reveal")
        if player.role.name.value == "Jailor":
            day_actions.append("jail")
        
        phase_name = f"Day {game.phase.name.title()}"
        return f"Valid actions for {phase_name}: {', '.join(day_actions)}"
    
    # Night actions
    elif game.time == Time.NIGHT:
        night_actions = ["skip", "pass"]
        
        # Role-specific night actions
        role_name = player.role.name.value
        if role_name in ["Sheriff", "Investigator", "Consigliere"]:
            night_actions.append("investigate")
        if role_name in ["Doctor", "Bodyguard", "Crusader", "Guardian Angel"]:
            night_actions.append("protect")
        if role_name == "Vigilante":
            night_actions.append("shoot")
        if role_name in ["Godfather", "Mafioso", "Serial Killer", "Arsonist", "Werewolf"]:
            night_actions.append("kill")
        if role_name == "Jailor" and getattr(player.role, 'jailed_target', None):
            night_actions.append("execute")
        if role_name in ["Escort", "Consort", "Tavern Keeper", "Bootlegger"]:
            night_actions.append("distract")
        if role_name in ["Retributionist", "Necromancer"]:
            night_actions.append("raise")
        if role_name == "Transporter":
            night_actions.append("transport")
        if role_name == "Veteran":
            night_actions.append("alert")
        if role_name == "Tracker":
            night_actions.append("track")
        if role_name == "Lookout":
            night_actions.append("watch")
        if role_name == "Spy":
            night_actions.append("bug")
        if role_name == "Psychic":
            night_actions.append("vision")
        if role_name == "Hex Master":
            night_actions.append("hex")
        if role_name == "Poisoner":
            night_actions.append("poison")
        if role_name == "Medusa":
            night_actions.append("stone")
        if role_name == "Pirate":
            night_actions.append("plunder")
        
        return f"Valid actions for Night (as {role_name}): {', '.join(night_actions)}"
    
    return "Error: Unknown game phase."


def _exec_action_history(argument: str, *, game=None, player=None) -> str:
    """Return the player's action history with results.
    
    Usage: <action_history></action_history>
    """
    if not game or not player:
        return "Error: action history requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    # Initialize action history if it doesn't exist
    if not hasattr(player, 'action_history'):
        player.action_history = []
    
    if not player.action_history:
        return "No action history available yet."
    
    history_text = "Action History:\n"
    for entry in player.action_history:
        phase = entry.get('phase', 'Unknown')
        action = entry.get('action', 'Unknown')
        target = entry.get('target', 'None')
        result = entry.get('result', 'No result recorded')
        
        if target and target != 'None':
            history_text += f"{phase}: {action} {target} - {result}\n"
        else:
            history_text += f"{phase}: {action} - {result}\n"
    
    return history_text.strip()

    return json.dumps({
        "tool_name": "get_role",
        "class": "environment_static",
        "observation": {"role_info": role_card.to_dict()}
    }, indent=2)
# ---------------------------------------------------------------------------
def _exec_role_details(argument: str) -> str:
    """Return detailed information about a role from roles.json."""
    
    try:
        data = _load_data_json("roles.json")
    except FileNotFoundError:
        return "Role details file not found"
    except json.JSONDecodeError as e:
        return f"Error parsing role details JSON: {e}"

    role_name_clean = argument.strip()
    
    # Handle search functionality
    if role_name_clean.lower() == "search":
        role_names = list(data.keys())
        search_result = {
            "available_roles": role_names,
            "usage": "Use <role_details>RoleName</role_details> to get specific role details",
            "examples": ["Bodyguard", "Doctor", "Sheriff", "Mafioso", "Jester"]
        }
        return json.dumps({
            "tool_name": "roles",
            "class": "environment_static",
            "observation": {"search_result": search_result}
        }, indent=2)
    
    # If no specific role requested, return available roles
    if not role_name_clean:
        role_names = list(data.keys())
        return json.dumps({
            "tool_name": "roles",
            "class": "environment_static",
            "observation": {
                "available_roles": role_names,
                "message": "Specify a role name to get detailed information"
            }
        }, indent=2)
    
    # Direct lookup first (case-sensitive)
    if role_name_clean in data:
        role_details = data[role_name_clean]
    else:
        # Try case-insensitive match
        matches = [k for k in data.keys() if k.lower() == role_name_clean.lower()]
        if matches:
            role_details = data[matches[0]]
        else:
            return f"No role named '{role_name_clean}' found in role details."
    
    return json.dumps({
        "tool_name": "roles",
        "class": "environment_static", 
        "observation": {"role_details": role_details}
    }, indent=2)



def _exec_attributes(argument: str) -> str:
    """Return information about game attributes.
    
    If no argument is provided, returns all attributes.
    If a specific attribute is provided, returns only that attribute.
    If 'search' is provided, returns searchable attribute names.
    If an invalid attribute is provided, returns an error message.
    """    
    try:
        attributes_data = _load_data_json("attributes.json")
    except FileNotFoundError:
        return "Attributes data file not found"
    except json.JSONDecodeError as e:
        return f"Error parsing attributes JSON: {e}"
    
    attribute_name = argument.strip()
    
    # Handle search functionality
    if attribute_name.lower() == "search":
        attribute_names = list(attributes_data.keys())
        search_result = {
            "available_attributes": attribute_names,
            "usage": "Use <attributes>AttributeName</attributes> to get specific attribute details",
            "examples": ["BasicDefense", "PowerfulAttack", "UnstoppableAttack", "RoleBlockImmunity"]
        }
        return json.dumps({
            "tool_name": "attributes",
            "class": "environment_static",
            "observation": {"search_result": search_result}
        }, indent=2)
    
    # If no specific attribute requested, return all attributes
    if not attribute_name:
        return json.dumps({
            "tool_name": "attributes",
            "class": "environment_static", 
            "observation": {"attribute_info": attributes_data}
        }, indent=2)
    
    # Look for the specific attribute (case-sensitive first, then case-insensitive)
    if attribute_name in attributes_data:
        attribute_info = {attribute_name: attributes_data[attribute_name]}
    else:
        # Try case-insensitive match
        matches = [k for k in attributes_data.keys() if k.lower() == attribute_name.lower()]
        if matches:
            matched_key = matches[0]
            attribute_info = {matched_key: attributes_data[matched_key]}
        else:
            return f"No attribute with the name '{attribute_name}' found."
    
    return json.dumps({
        "tool_name": "attributes",
        "class": "environment_static",
        "observation": {"attribute_info": attribute_info}
    }, indent=2)


def _exec_write_will(argument: str, *, game=None, player=None) -> str:
    """Write or update the player's last will.
    
    Usage: <write_will>My will content here</write_will>
    """
    if not game or not player:
        return "Error: will writing requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot write a will while dead."
    
    will_content = argument.strip()
    if not will_content:
        return "Error: Cannot write an empty will."
    
    from Simulation.tokenizer_utils import count_tokens, truncate_to_token_limit
    
    # Enforce 100-token limit for wills
    WILL_TOKEN_LIMIT = 100
    will_tokens = count_tokens(will_content)
    
    if will_tokens > WILL_TOKEN_LIMIT:
        # Truncate to fit limit
        truncated_will, actual_tokens = truncate_to_token_limit(will_content, WILL_TOKEN_LIMIT)
        player.last_will = truncated_will
        return f"Your last will has been updated (truncated to {actual_tokens}/{WILL_TOKEN_LIMIT} tokens due to length limit)."
    else:
        # Update the player's last will
        player.last_will = will_content
        return f"Your last will has been updated ({will_tokens}/{WILL_TOKEN_LIMIT} tokens)."


def _exec_investigation_results(argument: str, *, game=None, player=None) -> str:
    """Return the investigator results chart.
    
    Usage: <investigation_results></investigation_results>
    """
    if not game or not player:
        return "Error: investigation results require game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    # Check if Coven expansion is enabled for different results
    is_coven = getattr(game.config, 'is_coven', False)
    
    if is_coven:
        # Coven expansion investigation results
        results = """Investigator Results (Coven Expansion):
- Investigator, Consigliere, Mayor, Tracker, Plaguebearer
- Lookout, Forger, Witch, Coven Leader
- Sheriff, Executioner, Werewolf, Poisoner
- Framer, Vampire, Jester, Hex Master
- Medium, Janitor, Retributionist, Necromancer, Trapper
- Survivor, Vampire Hunter, Amnesiac, Medusa
- Spy, Blackmailer, Jailor, Guardian Angel
- Escort, Transporter, Consort, Hypnotist
- Doctor, Disguiser, Serial Killer, Potion Master
- Bodyguard, Godfather, Arsonist, Crusader
- Vigilante, Veteran, Mafioso, Pirate, Ambusher
- (No one else)"""
    else:
        # Classic investigation results
        results = """Investigator Results (Classic):
- Investigator, Consigliere, Mayor, Tracker
- Lookout, Forger, Witch
- Sheriff, Executioner, Werewolf
- Framer, Vampire, Jester
- Medium, Janitor, Retributionist
- Survivor, Vampire Hunter, Amnesiac
- Spy, Blackmailer, Jailor
- Escort, Transporter, Consort
- Doctor, Disguiser, Serial Killer
- Bodyguard, Godfather, Arsonist
- Vigilante, Veteran, Mafioso
- (No one else)"""
    
    return results


def _exec_evil_investigation_results(argument: str, *, game=None, player=None) -> str:
    """Return information about consigliere and spy results.
    
    Usage: <evil_investigation_results></evil_investigation_results>
    """
    if not game or not player:
        return "Error: evil investigation results require game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot use tools while dead."
    
    results = """Evil Investigation Results:

CONSIGLIERE:
- Sees exact role of target
- Coven members with Necronomicon are detection immune
- Hexed players show as "Hex Master"
- Doused players show as "Arsonist"

SPY INTELLIGENCE:
- Sees all Mafia visits: "A member of the mafia visited X last night"
- Sees all Coven visits: "A member of the coven visited X last night"
- Bug results show detailed target information

SPECIAL COVEN MECHANICS:
- Witch, Coven Leader, Potion Master see investigation results of their first target
- Multiple Witches: random one succeeds if targeting same player
- All Coven members gain detection immunity with Necronomicon

INVESTIGATION GROUPS (for Coven roles):
- Witch, Coven Leader, Hex Master, Poisoner all show same investigator result"""
    
    return results


def _exec_victory_conditions(argument: str, *, game=None, player=None) -> str:
    """Return victory condition information.

    Usage examples:
    • <victory_conditions></victory_conditions>              – contextual (in-game) lookup for *your* alignment
    • <victory_conditions>Town</victory_conditions>         – lookup Town victory conditions (any context)
    • <victory_conditions>Mafia</victory_conditions>        – lookup Mafia victory conditions, etc.
    """

    # Load static data once
    try:
        victory_data = _load_data_json("victory_conditions.json")
    except FileNotFoundError:
        return "Victory conditions data file not found."
    except json.JSONDecodeError as e:
        return f"Error parsing victory conditions JSON: {e}"

    arg = argument.strip()

    # ────────────────────────────────────────────────────────────
    # 1. Explicit argument lookup (works even outside a running game)
    # ────────────────────────────────────────────────────────────
    if arg:
        matches: dict[str, list[str]] = {}
        for mode, align_map in victory_data.items():
            for align_name, conditions in align_map.items():
                if align_name.lower() == arg.lower():
                    matches.setdefault(mode, conditions)

        if not matches:
            return f"No victory conditions found for '{arg}'."

        # If only one game mode provides data, return a simple list
        if len(matches) == 1:
            sole_mode = next(iter(matches))
            result = f"{arg.title()} – {sole_mode} Mode:\n\n"
            for cond in matches[sole_mode]:
                result += f"- {cond}\n"
            return result.strip()

        # Otherwise, show a JSON mapping of mode → conditions
        return json.dumps(matches, indent=2)

    # ────────────────────────────────────────────────────────────
    # 2. In-game contextual lookup (original behaviour)
    # ────────────────────────────────────────────────────────────
    if game and player:
        if not player.is_alive:
            return "Error: You cannot use tools while dead."

        game_mode = getattr(game.config, 'game_mode', 'Classic')
        alignment = getattr(game.config, 'alignment', None)

        if not alignment:
            return "Error: Player alignment unavailable in game context."

        conditions = victory_data.get(game_mode, {}).get(alignment, [])
        if not conditions:
            return f"No victory conditions found for {alignment} in {game_mode} mode."

        result = f"Victory Conditions for {alignment} – {game_mode} Mode:\n\n"
        for cond in conditions:
            result += f"- {cond}\n"
        return result.strip()

    # ────────────────────────────────────────────────────────────
    # 3. Fallback – list available alignments for Classic mode
    # ────────────────────────────────────────────────────────────
    classic_aligns = list(victory_data.get("Classic", {}).keys())
    return (
        "Usage: <victory_conditions>[Alignment]</victory_conditions>. "
        "Available alignments in Classic mode: " + ", ".join(classic_aligns)
    )


def _exec_write_death_note(argument: str, *, game=None, player=None) -> str:
    """Write death note for killing roles.
    
    Usage: <write_death_note>Death note content here</write_death_note>
    """
    if not game or not player:
        return "Error: death note writing requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot write a death note while dead."
    
    # Check if role can use death notes
    from Simulation.enums import RoleName
    death_note_roles = {
        RoleName.GODFATHER, RoleName.MAFIOSO, RoleName.SERIAL_KILLER, 
        RoleName.ARSONIST, RoleName.WEREWOLF, RoleName.JUGGERNAUT,
        RoleName.COVEN_LEADER, RoleName.HEX_MASTER, RoleName.NECROMANCER,
        RoleName.MEDUSA, RoleName.POISONER, RoleName.AMBUSHER
    }
    
    if player.role.name not in death_note_roles:
        return "Error: Your role cannot write death notes."
    
    death_note_content = argument.strip()
    if not death_note_content:
        return "Error: Cannot write an empty death note."
    
    from Simulation.tokenizer_utils import count_tokens, truncate_to_token_limit
    
    # Enforce 100-token limit for death notes
    DEATH_NOTE_TOKEN_LIMIT = 100
    death_note_tokens = count_tokens(death_note_content)
    
    if death_note_tokens > DEATH_NOTE_TOKEN_LIMIT:
        # Truncate to fit limit
        truncated_note, actual_tokens = truncate_to_token_limit(death_note_content, DEATH_NOTE_TOKEN_LIMIT)
        player.role.death_note = truncated_note
        return f"Death note updated (truncated to {actual_tokens}/{DEATH_NOTE_TOKEN_LIMIT} tokens due to length limit)."
    else:
        # Update the death note
        player.role.death_note = death_note_content
        return f"Death note updated ({death_note_tokens}/{DEATH_NOTE_TOKEN_LIMIT} tokens)."


def _exec_jailor_death_note(argument: str, *, game=None, player=None) -> str:
    """Set Jailor execution reason.
    
    Usage: <jailor_death_note>reason</jailor_death_note>
    """
    if not game or not player:
        return "Error: jailor death note requires game context."
    
    # Restrict to living players only
    if not player.is_alive:
        return "Error: You cannot set execution reason while dead."
    
    # Check if player is Jailor
    from Simulation.enums import RoleName
    if player.role.name != RoleName.JAILOR:
        return "Error: Only the Jailor can set execution reasons."
    
    reason = argument.strip().lower()
    
    reason_map = {
        'no_reason': 'No reason specified.',
        'evildoer': 'They are known to be an evildoer.',
        'contradictory': 'Their confession was contradictory.',
        'possessed': 'They are possessed and talking nonsense.',
        'quiet': 'They are too quiet or won\'t respond to questioning.',
        'outsider': 'They are an outsider that might turn against us.',
        'discretion': 'I\'m using my own discretion.'
    }
    
    if reason not in reason_map:
        valid_reasons = ', '.join(reason_map.keys())
        return f"Error: Invalid reason. Valid options: {valid_reasons}"
    
    # Set the death note to the selected reason
    player.role.death_note = reason_map[reason]
    return f"Execution reason set: {reason_map[reason]}"


def _exec_gamemodes(argument: str) -> str:
    """Return information about game modes.
    If no argument: list all modes. Else, details about the requested mode.
    """
    try:
        gm_data = _load_data_json("gamemodes.json")
    except FileNotFoundError:
        return "Game modes data file not found."
    except json.JSONDecodeError as e:
        return f"Error parsing gamemodes JSON: {e}"

    mode = argument.strip()
    if not mode:
        return json.dumps({"available_gamemodes": list(gm_data.keys())}, indent=2)
    # Case-insensitive lookup
    for key in gm_data:
        if key.lower() == mode.lower():
            return json.dumps({mode: gm_data[key]}, indent=2)
    return f"No game mode named '{mode}' found."


def _exec_alignments(argument: str) -> str:
    """Return information about alignments and their roles.
    Argument can be empty (list alignments) or specific alignment.
    """
    try:
        al_data = _load_data_json("alignment.json")
    except FileNotFoundError:
        return "Alignment data file not found."
    except json.JSONDecodeError as e:
        return f"Error parsing alignment JSON: {e}"

    align = argument.strip()
    if not align:
        return json.dumps({"available_alignments": list(al_data.keys())}, indent=2)

    # Case-insensitive lookup
    for key in al_data:
        if key.lower() == align.lower():
            return json.dumps({key: al_data[key]}, indent=2)
    return f"No alignment named '{align}' found."

def _exec_phases(argument: str) -> str:
    """Return information about game phases and their mechanics.
    Argument can be empty (list all phases) or specific phase name.
    """
    try:
        phases_data = _load_data_json("phases.json")
    except FileNotFoundError:
        return "Phases data file not found."
    except json.JSONDecodeError as e:
        return f"Error parsing phases JSON: {e}"

    phase = argument.strip()
    if not phase:
        return json.dumps({"available_phases": list(phases_data.keys())}, indent=2)

    # Case-insensitive lookup
    for key in phases_data:
        if key.lower() == phase.lower():
            return json.dumps({key: phases_data[key]}, indent=2)
    return f"No phase named '{phase}' found."

# Mapping: tool name -> executor
_TOOL_EXECUTORS: Dict[str, Callable[[str], str]] = {
    "get_role": _exec_get_role,
    "roles": _exec_role_details,  
    "role_details": _exec_role_details,
    "attributes": _exec_attributes,
    "gamemodes": _exec_gamemodes,
    "alignments": _exec_alignments,
    "phases": _exec_phases,
    
    "chat_history": _exec_chat_history,
    "graveyard": _exec_graveyard,
    "check_will": _exec_check_will,
    "view_will": _exec_view_will,
    "get_time": _exec_get_time,
    "notebook": _exec_notebook,
    "view_notebook": _exec_view_notebook,
    "get_executable_actions": _exec_get_executable_actions,
    "action_history": _exec_action_history,
    "write_will": _exec_write_will,
    "write_death_note": _exec_write_death_note,
    "jailor_death_note": _exec_jailor_death_note,
    "investigation_results": _exec_investigation_results,
    "evil_investigation_results": _exec_evil_investigation_results,
    "victory_conditions": _exec_victory_conditions,
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_tool_registry() -> Dict[str, dict[str, Any]]:
    """Return *copy* of the registry dict so callers cannot mutate internals."""
    return {k: v.copy() for k, v in _TOOL_SPECS.items()}


def execute_tool(tool_name: str, raw_argument: str, *, game=None, player=None) -> str:
    """Execute *tool_name* with *raw_argument* and return observation text.

    If the tool is unknown or lacks an executor, a friendly error string is
    returned instead of raising to avoid crashing the simulation.
    
    Parameters:
    • *game* and *player* provide context for tools that need access to game state.
    """
    exec_fn = _TOOL_EXECUTORS.get(tool_name)
    if exec_fn is None:
        return f"Tool '{tool_name}' is not recognised or not yet implemented."
    try:
        # Check if the executor accepts game context
        import inspect
        sig = inspect.signature(exec_fn)
        if 'game' in sig.parameters:
            return exec_fn(raw_argument, game=game, player=player)
        else:
            return exec_fn(raw_argument)
    except Exception as exc:  # noqa: BLE001
        # Never propagate, tool errors should be safe for the agent to read.
        return f"Error executing {tool_name}: {exc}" 