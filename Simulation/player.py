from __future__ import annotations
from typing import TYPE_CHECKING
from .debug_utils import debug_print, debug_exception

if TYPE_CHECKING:
    from .roles import Role
    from .enums import Defense

class Player:
    _id_counter = 0

    def __init__(self, name: str, role: 'Role'):
        self.id: int = Player._id_counter
        Player._id_counter += 1
        self.name: str = name
        self.role: Role = role
        debug_print(f"DEBUG: Player {self.name} initialized with role.name type: {type(self.role.name)}, value: {self.role.name}")
        self.is_alive: bool = True
        self.chat_channels = [] #To be implemented with the chat system
        self.votes_on = 0
        self.voted_for = None
        self.is_on_trial = False
        self.visiting: 'Player' = None  # Primary visit target
        self.visiting_all: list['Player'] = []  # All visit targets this night
        self.targeted_by: list['Player'] = []
        self.protected_by: list['Player'] = []
        
        #Attributes that can be modified by game mechanics
        self.defense: Defense = role.defense
        self.is_role_blocked = False
        self.is_doused = False
        self.is_hexed = False
        self.is_framed = False
        self.is_disguised = False
        self.last_will_bloodied = False
        self.is_jailed = False
        self.is_being_executed = False
        self.is_poisoned = False
        self.poison_timer = 0  #nights until poison kills
        self.notifications = []
        self.is_blackmailed = False
        self.is_controlled = False
        self.is_protected = False
        self.is_healed = False
        self.was_lynched = False
        self.was_stoned = False
        self.poison_uncurable = False
        self.is_infected = False  #Plaguebearer infection
        self.last_will: str = ""  #Player can optionally set a last will.
        self.death_note: str = ""  #Player's death note (for certain roles)
        
        # Death information (set when player dies)
        self.killed_by: 'Player' = None  # The player who killed this player
        self.killer_death_note: str = ""  # Death note left by the killer
        #Vote weight for verdict voting (Mayor becomes 3 when revealed)
        self.vote_weight: int = 1

        # Environment tool tracking for prompt building
        self.environment_static_tools_used: set = set()  # Track which environment_static tools have been used

        # Notebook system
        self.notebook: str = ""
        self.notebook_tokens: int = 0

        # Amnesiac – pending role to remember at dawn
        self.remember_role_name = None

        self.was_cleaned = False  # Janitor cleaned corpse flag
        self.was_forged = False   # Forger forged will flag

        # Janitor who cleaned this player (set at night before death resolution)
        self.cleaned_by: 'Player' | None = None

        # Disguiser mechanics
        self.disguised_as_role: 'RoleName' | None = None

        # Jester haunt mechanics
        self.haunt_candidates: list['Player'] | None = None  # set when lynched if Jester
        self.haunt_target: 'Player' | None = None  # chosen target for haunt (night after lynch)

        # Medium séance target (once, when the medium is dead)
        self.seance_target: 'Player' | None = None

        # TODO: RESEARCH METRICS TRACKING FOR "Are Misaligned Agents Better at Social Deception Games?"
        # Player-specific metrics for social deception research
        self.research_metrics = {
            # Core game outcomes
            'won_game': False,
            'survived_to_end': False,
            'days_survived': 0,
            'death_cause': None,  # 'lynched', 'shot_vigilante', 'executed', 'haunted', 'killed_mafia', etc.
            
            # Trial and voting metrics
            'times_nominated': 0,
            'times_lynched': 0,
            'times_defended_successfully': 0,  # got off innocent
            'times_voted_guilty': 0,
            'times_voted_innocent': 0,
            'times_voted_abstain': 0,
            
            # Communication metrics
            'times_spoken': 0,
            'times_whispered': 0,
            'total_tokens_spoken': 0,
            'total_tokens_whispered': 0,
            'average_tokens_per_message': 0,
            
            # Jail and execution metrics
            'times_jailed': 0,
            'times_executed': 0,
            
            # Jester-specific metrics
            'times_haunted_by_jester': 0,
            
            # Tool usage metrics
            'successful_tool_uses': 0,
            'unsuccessful_tool_uses': 0,
            'total_tool_calls': 0,
            'invalid_phase_tool_attempts': 0,  # trying to kill during day
            'wrong_role_tool_attempts': 0,    # trying to hex as jester
            'times_used_notebook': 0,
            
            # Agent metadata
            'is_misaligned_model': False,
            'model_name': '',
            'faction': '',  # 'Town', 'Mafia', 'Neutral', etc.
            'role_alignment': '',  # 'Town Investigative', 'Mafia Deception', etc.
            
            # Executioner-specific win tracking
            'exe_won_as_executioner': False,  # won by getting target lynched
            'exe_won_as_jester': False,       # target died other way, converted to jester and won
        }

    def __repr__(self):
        try:
            role_name = self.role.name.value
        except Exception:
            debug_exception(f"Failed to access .value on self.role.name: {getattr(self.role, 'name', None)} (type: {type(getattr(self.role, 'name', None))})")
            role_name = str(getattr(self.role, 'name', None))
        return f"Player({self.name}, {role_name})"

    def assign_role(self, role: 'Role'):
        self.role = role
        # Ensure role.name is always a RoleName enum member
        from .enums import RoleName
        if not isinstance(self.role.name, RoleName):
            try:
                self.role.name = RoleName(self.role.name)
            except ValueError:
                # Fallback if string cannot be converted to RoleName enum
                print(f"ERROR: Attempted to assign non-RoleName to player.role.name: {self.role.name} (type: {type(self.role.name)}). Assigning default.")
                self.role.name = RoleName.INVESTIGATOR # Assign a safe default
        self.defense = role.defense

    def visit(self, target_player: 'Player'):
        self.visiting = target_player  # Keep primary target
        if target_player not in self.visiting_all:
            self.visiting_all.append(target_player)  # Track all targets
        target_player.targeted_by.append(self)

    def clear_night_actions(self):
        self.visiting = None
        self.visiting_all = []
        self.targeted_by = []
        self.protected_by = []
        self.is_role_blocked = False
        if self.role:
            self.defense = self.role.defense #Reset to default defense
        self.is_jailed = False
        self.is_being_executed = False
        self.cleaned_by = None

    def clear_day_states(self):
        self.votes_on = 0
        self.voted_for = None
        self.is_on_trial = False 

    def get_role_name(self) -> str:
        return self.role.name.value

    def can_be_targeted(self, attacker: 'Player') -> bool:
        #This can be expanded with immunities, etc.
        return True

    def reset_night_states(self):
        self.targeted_by = []
        self.visiting = None
        self.visiting_all = []
        self.protected_by = []
        self.is_role_blocked = False
        self.is_jailed = False
        self.is_being_executed = False
        self.notifications = []
        self.is_blackmailed = False
        self.is_controlled = False
        self.is_poisoned = False
        self.is_doused = False
        self.is_hexed = False
        # Restore default defense (e.g., Veteran loses INVINCIBLE after alert)
        if self.role:
            self.defense = self.role.defense
        #lynch status persists

    def get_public_info(self):
        return {
            "name": self.name,
            "is_alive": self.is_alive
        }