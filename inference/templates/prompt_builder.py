from pathlib import Path
import random
from dataclasses import dataclass, field
import jinja2
import json

# Optional – if a real registry module exists it will be used. Otherwise fall back to an empty dict.
try:
    from Simulation.tools.registry import get_tool_registry  # type: ignore
except (ImportError, ModuleNotFoundError):
    def get_tool_registry():  # pragma: no cover
        return {}

from Simulation.enums import RoleName  # For type hints only – avoids heavy Role import
from Simulation.phase_prompt import render_phase_prompt

# Load canonical role and victory condition data at module load
ROLES_JSON_PATH = Path(__file__).parents[2] / "Simulation" / "tools" / "roles.json"
VICTORY_JSON_PATH = Path(__file__).parents[2] / "Simulation" / "tools" / "victory_conditions.json"
with open(ROLES_JSON_PATH, "r", encoding="utf-8") as f:
    ROLES_DATA = json.load(f)
with open(VICTORY_JSON_PATH, "r", encoding="utf-8") as f:
    VICTORY_DATA = json.load(f)

def get_role_metadata(role_enum, game_mode="Classic"):
    """Return merged metadata for a role, using roles.json and victory_conditions.json."""
    # Accept either Enum or string
    role_name = role_enum.value if hasattr(role_enum, "value") else str(role_enum)
    role_info = ROLES_DATA.get(role_name)
    if not role_info:
        return {}
    # Merge in victory condition(s) for this role/faction/game mode
    victory_mode = VICTORY_DATA.get(game_mode, {})
    # Try by role, then by faction, then fallback
    win_conditions = []
    if role_name in victory_mode:
        win_conditions = victory_mode[role_name]
    elif role_info.get("faction") in victory_mode:
        win_conditions = victory_mode[role_info["faction"]]
    elif "Neutrals" in victory_mode and role_info.get("alignment", "").startswith("Neutral"):
        win_conditions = victory_mode["Neutrals"]
    elif "Draw" in victory_mode:
        win_conditions = victory_mode["Draw"]
    # Merge win_condition from role_info and victory_conditions
    merged = dict(role_info)
    merged["win_conditions"] = win_conditions
    return merged

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
_env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR), autoescape=False)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RoleCard:
    """A minimal, serialisable representation of a role's public card.

    This is intentionally lightweight so it can be passed straight into a
    Jinja template without additional pre-processing.
    """

    # Core identity
    name: str
    faction: str
    alignment: str
    goal: str = "Win condition unknown (placeholder)."

    # Combat stats
    attack: str = "None"
    defense: str = "None"
    immunities: list[str] | None = field(default_factory=list)
    is_unique: bool = False

    # Gameplay text – kept short to conserve prompt tokens
    abilities: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    night_action_usage: str = "Use your role-specific night action tool when appropriate."
    wins_with: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mechanics: dict = field(default_factory=dict)
    notifications: list[str] = field(default_factory=list)
    visit_type: str = "Unknown"

    def __post_init__(self):
        # Defensive: ensure all list fields are lists, not None
        for field_name in ["immunities", "abilities", "attributes", "wins_with", "notes", "notifications"]:
            val = getattr(self, field_name)
            if val is None:
                setattr(self, field_name, [])
        if self.mechanics is None:
            self.mechanics = {}

    def to_dict(self) -> dict:
        """Return a plain dict that Jinja can iterate over easily."""
        d = {
            **self.__dict__,
            # Convert booleans/lists to a friendly representation
            "is_unique": "Yes" if self.is_unique else "No",
        }
        # Defensive: ensure all list fields are lists, not None
        for field_name in ["immunities", "abilities", "attributes", "wins_with", "notes", "notifications"]:
            if d.get(field_name) is None:
                d[field_name] = []
        # Render mechanics as readable lines
        if self.mechanics:
            lines = []
            for k, v in self.mechanics.items():
                if isinstance(v, list):
                    for item in v:
                        lines.append(f"{k.title()}: {item}")
                else:
                    lines.append(f"{k.title()}: {v}")
            d["mechanics_lines"] = lines
        else:
            d["mechanics_lines"] = []
        return d

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_DEFAULT_NAMES = [
    "Alice",
    "Bob",
    "Charlie",
    "Daphne",
    "Eve",
    "Mallory",
    "Oscar",
    "Peggy",
    "Sybil",
    "Trent",
    "Victor",
    "Walter",
]


def generate_agent_name() -> str:
    """Return a pseudo-random agent display name.

    The simulator will eventually replace this with its own name-source.  Until
    then we draw from a fixed sample list so that unit tests are repeatable.
    """
    return random.choice(_DEFAULT_NAMES)


def _tool_catalogue() -> dict:
    """Return a mapping of available tool-name → lightweight spec.

    The concrete object returned by ``get_tool_registry`` is implementation
    defined.  We only rely on two *optional* attributes per entry so the
    function never crashes if they are missing.
    """
    registry = get_tool_registry() or {}
    catalogue: dict[str, dict[str, str]] = {}

    for name, obj in registry.items():
        catalogue[name] = {
            "signature": getattr(obj, "signature", "<args?>"),
            "help": getattr(obj, "__doc__", ""),
        }
    return catalogue


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_role_card(role, game_mode="Classic") -> RoleCard:
    """Construct a RoleCard from merged canonical metadata."""
    meta = get_role_metadata(role_to_json_key(role), game_mode)
    if not meta:
        # fallback to old logic
        info = role.get_info() if hasattr(role, "get_info") else {}
        abilities = getattr(role, 'abilities', [])
        attributes = getattr(role, 'attributes', [])
        night_action_usage = getattr(role, 'night_action_usage', "Use your role-specific night action tool when appropriate.")
        wins_with = getattr(role, 'wins_with', [])
        notes = getattr(role, 'notes', [])
        return RoleCard(
            name=info.get("name", getattr(role, "name", "Unknown")),
            faction=info.get("faction", getattr(role, "faction", "Unknown")),
            alignment=info.get("alignment", getattr(role, "alignment", "Unknown")),
            attack=info.get("attack", getattr(role, "attack", "None")),
            defense=info.get("defense", getattr(role, "defense", "None")),
            is_unique=info.get("is_unique", getattr(role, "is_unique", False)),
            abilities=abilities,
            attributes=attributes,
            night_action_usage=night_action_usage,
            wins_with=wins_with,
            notes=notes,
        )
    # Use canonical metadata
    return RoleCard(
        name=meta.get("name", "Unknown"),
        faction=meta.get("faction", "Unknown"),
        alignment=meta.get("alignment", "Unknown"),
        goal=meta.get("win_condition", "Win condition unknown (placeholder)."),
        abilities=meta.get("abilities", []),
        attributes=meta.get("attributes", []),
        night_action_usage=meta.get("mechanics", {}).get("night_action_usage", "Use your role-specific night action tool when appropriate."),
        wins_with=meta.get("wins_with", []),
        notes=meta.get("notes", []),
        attack=meta.get("attack", "None"),
        defense=meta.get("defense", "None"),
        is_unique=meta.get("is_unique", False),
        mechanics=meta.get("mechanics", {}),
        notifications=meta.get("notifications", []),
        immunities=meta.get("immunities", []) if meta.get("immunities") else [],
        visit_type=meta.get("visit_type", "Unknown"),
    )


def build_system_prompt(agent_name: str, role_card: RoleCard, *, tools: dict | None = None, game=None, game_mode="Classic") -> str:
    """Render the system prompt string given an agent name and RoleCard."""

    # Extract game context if available
    game_mode_val = game_mode
    is_coven = False
    roster = []
    role_list = []
    if game:
        game_mode_val = getattr(game.config, 'game_mode', 'Unknown')
        is_coven = getattr(game.config, 'is_coven', False)
        roster = [p.name for p in game.players]
        if hasattr(game.config, 'role_list'):
            role_list = [role.value for role in game.config.role_list]

    # Build tool catalogue for template
    tool_catalogue = tools or _tool_catalogue()
    tools_list = []
    for tag, spec in tool_catalogue.items():
        desc = spec.get('help', '').strip().split('\n')[0] or 'No description.'
        # Synthesize a simple example
        example = f"<{tag}>{'...' if 'args' in spec.get('signature','') else ''}</{tag}>"
        tools_list.append({
            'tag': tag,
            'description': desc,
            'example': example
        })

    # Define terminal actions (interactions)
    interactions_list = [
        {'tag': 'speak', 'description': 'Speak publicly in chat.', 'example': '<speak>Hello everyone.</speak>'},
        {'tag': 'vote', 'description': 'Vote to nominate or judge a player.', 'example': '<vote>Player7</vote> or <vote>GUILTY</vote>'},
        {'tag': 'nominate', 'description': 'Nominate a player for trial.', 'example': '<nominate>Player3</nominate>'},
        {'tag': 'whisper', 'description': 'Send a private message to another player.', 'example': '<whisper target="Player4">psst</whisper>'},
        {'tag': 'notebook', 'description': 'Write a private note.', 'example': '<notebook>Remember to check Bob</notebook>'},
        {'tag': 'wait', 'description': 'Do nothing this turn.', 'example': '<wait/>'},
    ]

    template_name = "system_prompt.jinja"
    if (TEMPLATE_DIR / template_name).exists():
        template = _env.get_template(template_name)
        return template.render(
            agent_name=agent_name,
            rc=role_card.to_dict(),
            tools=tool_catalogue,
            tools_list=tools_list,
            interactions_list=interactions_list,
            game_mode=game_mode_val,
            is_coven=is_coven,
            roster=roster,
            role_list=role_list,
        )

    # Inline minimal template (used during initial bootstrapping).
    inline_tpl = (
        """
<system>
You are {{agent_name}}, the {{rc.name}}.

Alignment: {{rc.alignment}}
Goal: {{rc.goal}}
Faction: {{rc.faction}}
Attack: {{rc.attack}}
Defense: {{rc.defense}}
Immunities: {{rc.immunities | join(', ') if rc.immunities else 'None'}}
Visit Type: {{rc.visit_type}}
Unique: {{rc.is_unique}}

Abilities:{% for abl in rc.abilities %}
• {{abl}}{% endfor %}{% if not rc.abilities %}
• (None listed yet){% endif %}

Attributes:{% for attr in rc.attributes %}
• {{attr}}{% endfor %}{% if not rc.attributes %}
• (None listed yet){% endif %}

Mechanics:{% for line in rc.mechanics_lines %}
• {{line}}{% endfor %}{% if not rc.mechanics_lines %}
• (None listed yet){% endif %}

Notifications:{% for note in rc.notifications %}
• {{note}}{% endfor %}{% if not rc.notifications %}
• (None listed yet){% endif %}

Night Action:
{{rc.night_action_usage}}

Wins With: {{rc.wins_with | join(', ') if rc.wins_with else 'Unknown'}}
Notes:{% for note in rc.notes %}
• {{note}}{% endfor %}{% if not rc.notes %}
• (None listed yet){% endif %}

Guidelines:
• Think privately inside <think>…</think>.
• Call tools with a single XML tag (e.g., <get_role>Doctor</get_role>).
• End your turn with one of <speak>, <whisper>, <vote>, or <wait>.
</system>
"""
    )
    return jinja2.Template(inline_tpl).render(
        agent_name=agent_name, rc=role_card.to_dict(), tools=tools or {}
    )


# ---------------------------------------------------------------------------
# High-level chat assembly
# ---------------------------------------------------------------------------

# Utility to translate Role/RoleName to roles.json key

def role_to_json_key(role):
    # If passed a Role object, get .name
    if hasattr(role, 'name'):
        name = role.name
    else:
        name = role
    # If it's an Enum, get .value
    if hasattr(name, 'value'):
        return name.value
    # If it's already a string, return as is
    return str(name)

def build_chat_messages(
    role: "Role",  # type: ignore
    public_state: dict,
    observation: str | None,
    history: list[dict],
    *,
    observation_role: str = "user",
    game=None,
    agent_name=None,  # <-- Add this parameter
) -> list[dict]:
    """Return the message list (system+user+history) ready for vLLM."""

    # Use provided agent_name, or fallback to history or random
    agent_name = agent_name or (history[0].get("agent_name") if history else generate_agent_name())
    # Extract game_mode from game if available
    game_mode = getattr(game.config, 'game_mode', 'Classic') if game and hasattr(game, 'config') else 'Classic'
    # Use translator for roles.json key
    role_key = role_to_json_key(role)
    role_card = build_role_card(role_key, game_mode=game_mode)

    system_msg = {
        "role": "system",
        "content": build_system_prompt(agent_name, role_card, tools=_tool_catalogue(), game=game, game_mode=game_mode),
    }

    user_msg = {"role": "user", "content": render_phase_prompt(public_state)}

    msgs: list[dict] = [system_msg, user_msg] + history

    if observation:
        msgs.append({"role": observation_role, "content": observation})

    return msgs