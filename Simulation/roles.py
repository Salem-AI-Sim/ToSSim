from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from .enums import RoleName, Faction, RoleAlignment, Attack, Defense, Priority, DisplayName, VisitType, ImmunityType
from .alignment import get_role_alignment, get_role_faction
import random
from .enums import DuelMove, DuelDefense
from .debug_utils import debug_print, debug_exception

if TYPE_CHECKING:
    from .player import Player
    from .game import Game

class Role(ABC):
    def __init__(self):
        self.name: RoleName = None
        self.faction: Faction = None
        self.alignment: RoleAlignment = None
        self.attack: Attack = Attack.NONE
        self.defense: Defense = Defense.NONE
        self.is_unique: bool = False
        self.action_priority = Priority.PRIORITY_3
        self.is_roleblock_immune = False
        self.detection_immune = False
        self.control_immune = False
        #Visit type: default harmful if attacking, else non-harmful
        self.visit_type = VisitType.HARMFUL if self.attack != Attack.NONE else VisitType.NON_HARMFUL
        self.is_coven = False
        self.has_necronomicon = False
        #A message the killer can leave when they successfully kill a victim.
        #This will be displayed the next day alongside the victim's body.
        self.death_note: str = ""
        self.chosen_move = None  # set by InteractionHandler when player specifies weapon

    @abstractmethod
    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        pass

    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        pass

    def get_info(self):
        try:
            name = self.name.value
        except Exception:
            debug_exception(f"Failed to access .value on self.name: {self.name} (type: {type(self.name)})")
            name = str(self.name)
        try:
            faction = self.faction.name
        except Exception:
            debug_exception(f"Failed to access .name on self.faction: {self.faction} (type: {type(self.faction)})")
            faction = str(self.faction)
        try:
            alignment = self.alignment.name
        except Exception:
            debug_exception(f"Failed to access .name on self.alignment: {self.alignment} (type: {type(self.alignment)})")
            alignment = str(self.alignment)
        try:
            attack = self.attack.name
        except Exception:
            debug_exception(f"Failed to access .name on self.attack: {self.attack} (type: {type(self.attack)})")
            attack = str(self.attack)
        try:
            defense = self.defense.name
        except Exception:
            debug_exception(f"Failed to access .name on self.defense: {self.defense} (type: {type(self.defense)})")
            defense = str(self.defense)
        return {
            "name": name,
            "faction": faction,
            "alignment": alignment,
            "attack": attack,
            "defense": defense,
            "is_unique": self.is_unique
        }

#utility

def has_immunity(role: 'Role', immunity: ImmunityType) -> bool:
    if immunity == ImmunityType.ROLE_BLOCK:
        return getattr(role, 'is_roleblock_immune', False)
    if immunity == ImmunityType.CONTROL:
        return getattr(role, 'control_immune', False)
    if immunity == ImmunityType.DETECTION:
        return getattr(role, 'detection_immune', False)
    return False

#Town Roles
class Sheriff(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.SHERIFF
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_4

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game'):
        # Handle Disguiser effect: examine displayed role
        eff_role = target.role
        if getattr(target, 'disguised_as_role', None):
            eff_role = create_role_from_name(target.disguised_as_role)

        # Being framed or hexed makes a Townie appear suspicious.
        if target.is_framed or target.is_hexed:
            return f"{target.name} is suspicious!"
        if eff_role.detection_immune:
            return f"{target.name} is not suspicious."
        if eff_role.name == RoleName.SERIAL_KILLER:
            return f"{target.name} is suspicious!"
        if eff_role.faction == Faction.MAFIA and eff_role.name != RoleName.GODFATHER:
            return f"{target.name} is suspicious!"
        return f"{target.name} is not suspicious."

class Investigator(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.INVESTIGATOR
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_4

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game'):
        if not game or not target:
            return "You must select a target."
        investigated_role = target.disguised_as_role if getattr(target,'disguised_as_role',None) else target.role.name
        if target.is_framed or (hasattr(game, 'config') and game.config.is_coven and target.is_hexed):
            investigated_role = RoleName.HEX_MASTER if game.config.is_coven else RoleName.FRAMER
        elif target.is_doused:
            investigated_role = RoleName.ARSONIST
        
        if hasattr(game, 'config'):
            result_group = game.config.get_investigator_result_group(investigated_role)
            if not result_group:
                return f"Your target, {target.name}, has a role that is mysterious and unknown."
            role_names = [role.value for role in result_group]
            if len(role_names) == 1:
                return f"Your target is a {role_names[0]}."
            result_string = ", ".join(role_names[:-1]) + ", or " + role_names[-1]
            return f"Your target could be a {result_string}."
        
        #Fallback if no config is present
        return f"Your target is a {investigated_role.value}."

class Lookout(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.LOOKOUT
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_4

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game'):
        from .enums import VisitType
        visitor_names = []
        
        for visitor in target.targeted_by:
            if visitor.role.visit_type == VisitType.ASTRAL:
                continue  # Astral visits are invisible to Lookout
                
            # Handle Disguiser effect: show disguised role name instead of actual visitor
            visitor_name = visitor.name
            if hasattr(visitor, 'disguised_as_role') and visitor.disguised_as_role:
                # Find the player whose role the visitor is disguised as
                disguise_source = None
                for p in game.players:
                    if p.role.name == visitor.disguised_as_role:
                        disguise_source = p
                        break
                if disguise_source:
                    visitor_name = disguise_source.name
                    
            visitor_names.append(visitor_name)
            
        if not visitor_names:
            return f"No one visited {target.name}."
        return f"These players visited {target.name}: {', '.join(visitor_names)}"

class Doctor(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.DOCTOR
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.self_heals = 1

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not target:
            return None
        if hasattr(target.role, 'revealed') and getattr(target.role, 'revealed', False):
            return "You cannot heal a revealed Mayor."
        if player == target:
            if self.self_heals > 0:
                self.self_heals -= 1
                target.defense = Defense.POWERFUL
                target._was_healed_tonight = True  # Mark for notification
                return f"You are using a self-heal. You have {self.self_heals} left."
            else:
                return "You are out of self-heals."
        target.defense = Defense.POWERFUL
        target._was_healed_tonight = True  # Mark for notification
        return f"You are healing {target.name} tonight."

class Bodyguard(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.BODYGUARD
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.vests = 1

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game'):
        if player == target:
            if self.vests > 0:
                self.vests -= 1
                player.defense = Defense.BASIC
                return f"You are guarding yourself tonight. You have {self.vests} vests remaining."
            else:
                return "You are out of vests."
        if target:
            target.protected_by.append(player)
            return f"You are guarding {target.name} tonight."
        return None

class Vigilante(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.VIGILANTE
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.attack = Attack.BASIC
        self.action_priority = Priority.PRIORITY_5
        self.bullets = 3
        self.has_killed_townie = False
        self.put_gun_down = False
        self.visit_type = VisitType.HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not target or not game:
            return None
        
        if self.bullets > 0:
            self.bullets -= 1
            game.register_attack(player, target, self.attack)
            return f"You are shooting {target.name} tonight. You have {self.bullets} bullets remaining."
        else:
            return "You are out of bullets."

class Mayor(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.MAYOR
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_unique = True
        self.revealed = False

    def reveal(self, player):
        if not self.revealed:
            self.revealed = True
            player.vote_weight = 3
            # Add notification to the Mayor
            player.notifications.append("You have revealed yourself as the Mayor! Your vote now counts as 3.")
            print(f"{player.name} has revealed themselves as the Mayor!")
            return True
        return False
    
    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        return None

    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        #Mayor can click a reveal button during the day; no target needed.
        if not self.revealed:
            success = self.reveal(player)
            if success:
                #Update player's vote weight
                player.vote_weight = 3
                return f"You have revealed yourself as the Mayor! Your vote now counts as 3."
        return None

class Medium(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.MEDIUM
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.HIGHEST
        self.seances = 1
        self.can_seance_from_grave = True

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if target and self.seances > 0:
            return self.seance(player, target, game)
        return "You are speaking with the dead."
    
    def seance(self, medium_player: 'Player', target: 'Player', game: 'Game'):
        """Create a private seance channel between Medium and target."""
        if self.seances <= 0:
            return "You have already used your seance ability."
        
        if not target or not target.is_alive:
            return "You can only seance living players."
        
        if medium_player == target:
            return "You cannot seance yourself."
        
        # Use the seance
        self.seances -= 1
        
        # Create the seance channel through the chat system
        if hasattr(game, 'chat'):
            game.chat.create_seance_channel(medium_player, target)
            return f"You have established a seance with {target.name}. You can now communicate privately."
        
        return f"You are attempting to seance {target.name}."

class TavernKeeper(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.TAVERN_KEEPER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_roleblock_immune = True
        self.action_priority = Priority.PRIORITY_2_HIGHEST

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not target:
            return None
        if target.role.name == RoleName.SERIAL_KILLER and not target.role.cautious:
            return None
        if has_immunity(target.role, ImmunityType.ROLE_BLOCK):
            if isinstance(target.role, SerialKiller) and target.role.cautious:
                 target.notifications.append("Someone tried to role block you, but you are immune!")
            return f"{target.name} could not be role-blocked."
        target.is_role_blocked = True
        return f"You are distracting {target.name} tonight."

class Godfather(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.GODFATHER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.defense = Defense.BASIC
        self.is_unique = True
        self.detection_immune = True
        self.action_priority = Priority.PRIORITY_5
        self.is_roleblock_immune = False 
        self.visit_type = VisitType.HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        mafioso = game.find_player_by_role(RoleName.MAFIOSO)
        if not mafioso or not mafioso.is_alive:
            if target:
                game.register_attack(player, target, Attack.BASIC)
                return f"{player.name} is attacking {target.name}."
        return "You have sent the Mafioso to kill."

class Mafioso(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.MAFIOSO
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.attack = Attack.BASIC
        self.is_unique = True
        self.control_immune = True
        self.action_priority = Priority.PRIORITY_5
        self.is_roleblock_immune = False
        self.visit_type = VisitType.HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not target:
             return f"{player.name} is not attacking anyone."
        game.register_attack(player, target, self.attack)
        return f"{player.name} is attacking {target.name}."

class SerialKiller(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.SERIAL_KILLER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.attack = Attack.UNSTOPPABLE
        self.defense = Defense.BASIC
        self.cautious = False
        self.is_roleblock_immune = True
        self.detection_immune = True
        self.action_priority = Priority.PRIORITY_5
        self.visit_type = VisitType.HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None, cautious: bool = False):
        self.cautious = cautious
        
        # Check if any role blockers are visiting
        role_blocker_visitors = [p for p in player.targeted_by if p.is_alive and p.role.name in [RoleName.TAVERN_KEEPER, RoleName.BOOTLEGGER, RoleName.PIRATE]]
        
        if role_blocker_visitors:
            if self.cautious:
                # Cautious SK refuses to attack if role blockers visit (stays home to avoid detection)
                return f"{player.name} is staying home cautiously."
            else:
                # Normal SK attacks the role blocker(s) who visit
                for rb_visitor in role_blocker_visitors:
                    game.register_attack(player, rb_visitor, self.attack)
                    rb_visitor.last_will_bloodied = True
                # Normal SK also attacks their intended target if not jailed
                if target and not player.is_jailed:
                    game.register_attack(player, target, self.attack)
                    return f"{player.name} is attacking {target.name} and killed visiting role blockers."
                else:
                    return f"{player.name} killed visiting role blockers."
        
        # No role blockers visiting - proceed with normal attack
        if target and not player.is_jailed:
            game.register_attack(player, target, self.attack)
            return f"{player.name} is attacking {target.name}."
        return f"{player.name} is staying home."

class Jailor(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.JAILOR
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_unique = True
        self.action_priority = Priority.PRIORITY_5
        self.executes = 3
        self.jailed_target = None
        self.is_roleblock_immune = False  # Jailor can be roleblocked

    def perform_day_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if target:
            self.jailed_target = target
            target.is_jailed = True
            return f"You have decided to jail {target.name} tonight."
        return None

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if game.day == 0:
            return "You cannot execute on the first night."
        if not self.jailed_target:
            return "You did not jail anyone."
        
        # Check if Jailor is role-blocked
        if player.is_role_blocked:
            return "You were role-blocked and cannot execute tonight."
            
        if self.executes > 0:
            # Check if target cannot be executed
            if self.jailed_target.role.name == RoleName.PESTILENCE:
                return "Your target is immune to execution! You cannot execute Pestilence."
            
            # Check if Guardian Angel is protecting the target
            if hasattr(self.jailed_target, 'protected_by') and self.jailed_target.protected_by:
                for protector in self.jailed_target.protected_by:
                    if protector.role.name == RoleName.GUARDIAN_ANGEL:
                        return "A Guardian Angel protected your target from execution!"
            
            self.executes -= 1
            self.jailed_target.is_being_executed = True
            # TODO: RESEARCH METRICS - Track execution events
            self.jailed_target.research_metrics['times_executed'] += 1
            self.jailed_target.research_metrics['death_cause'] = 'executed'
            game.register_attack(player, self.jailed_target, Attack.UNSTOPPABLE)
            return f"You are executing {self.jailed_target.name}. You have {self.executes} executes left."
        return "You are out of executes."

class Consigliere(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.CONSIGLIERE
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_4

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not game or not target:
            return "You must select a target."
        return f"Your target, {target.name}, is a {target.role.name.value}."

class Bootlegger(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.BOOTLEGGER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        # Bootlegger has roleblock immunity like Escort/Consort
        self.is_roleblock_immune = True
        self.action_priority = Priority.PRIORITY_2_HIGHEST

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not target:
            return None
        if target.role.name == RoleName.SERIAL_KILLER and not target.role.cautious:
            return None
        if has_immunity(target.role, ImmunityType.ROLE_BLOCK):
            return f"{target.name} could not be role-blocked."
        target.is_role_blocked = True
        return f"You are distracting {target.name} tonight."

class Arsonist(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.ARSONIST
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.attack = Attack.UNSTOPPABLE
        self.defense = Defense.BASIC
        self.detection_immune = True
        self.action_priority = Priority.PRIORITY_3  # Dousing is Priority 3, igniting is Priority 5
        # Arsonist only performs an astral (non-visiting) action when igniting; dousing is a regular, non-harmful visit.
        self.visit_type = VisitType.NON_HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game:
            return "Game state not available."

        # Default to NON_HARMFUL each night; we will override to ASTRAL for ignite/clean actions.
        self.visit_type = VisitType.NON_HARMFUL

        # Cleaning self (no target provided)
        if target is None:
            self.visit_type = VisitType.ASTRAL  # stay home
            if player.is_doused:
                player.is_doused = False
                return "You have cleaned the gasoline off of yourself."
            return "You cleaned yourself of gasoline, though you weren't doused."

        # Ignition (self-target)
        if target == player:
            self.visit_type = VisitType.ASTRAL  # does not visit anyone
            game.ignite_doused_players(player)
            return "You have ignited all doused targets!"

        # Dousing another player
        if not target.is_doused:
            target.is_doused = True
            return f"You have doused {target.name}."
        else:
            return f"{target.name} is already doused."
    
    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None): pass

class Pirate(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.PIRATE
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.attack = Attack.POWERFUL
        self.defense = Defense.NONE
        self.plunders = 0  # Need 2 successful plunders to win
        self.is_roleblock_immune = True
        self.control_immune = True
        self.detection_immune = True
        self.action_priority = Priority.PRIORITY_1
        self.duel_target = None
        self.last_dueled_target = None
        self.chosen_move = None  # Player's chosen duel move
        self.visit_type = VisitType.HARMFUL

    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if target and target != self.last_dueled_target:
            self.duel_target = target
            return f"{player.name} has decided to duel {target.name} tonight."
        elif target == self.last_dueled_target:
            return "You cannot duel the same player two nights in a row."
        return None

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        actual_target = self.duel_target
        if not actual_target:
            return "You stay on your ship tonight, searching for a target to plunder."
            
        self.last_dueled_target = actual_target
        self.duel_target = None
        
        # Check if either player is jailed
        if player.is_jailed:
            return "You were hauled off to Jail so you couldn't Duel your target."
        if actual_target.is_jailed:
            return "Your target was hauled off to jail so you couldn't Duel them."
            
        # Resolve the duel
        duel_won, pirate_move, target_defense = self.resolve_duel()
        
        # Target is always role-blocked by the duel (win or lose)
        actual_target.is_role_blocked = True
        
        if duel_won:
            # Pirate wins - kill the target (plunder will be awarded by game engine)
            game.register_attack(player, actual_target, self.attack, is_duel_win=True)
                
            return f"You chose {pirate_move.value} and defeated {actual_target.name}'s {target_defense.value}. You won the Duel! Plunders: {self.plunders + 1}/2"
        else:
            # Pirate loses - check for Serial Killer cautious interaction
            if isinstance(actual_target.role, SerialKiller) and not actual_target.role.cautious:
                # Non-cautious SK kills the Pirate for visiting
                game.register_attack(actual_target, player, actual_target.role.attack, is_primary=False)
                player.last_will_bloodied = True
                return f"You chose {pirate_move.value} but were bested by {actual_target.name}'s {target_defense.value}. You lost the Duel and were killed by the Serial Killer!"
            
            return f"You chose {pirate_move.value} but were bested by {actual_target.name}'s {target_defense.value}. You lost the Duel!"

    def resolve_duel(self):
        """Resolve the pirate duel using rock-paper-scissors style mechanics.
        
        Pirate wins if:
        - Scimitar beats Sidestep (slashing beats dodging)
        - Rapier beats Chainmail (piercing beats armor) 
        - Pistol beats Backpedal (ranged beats retreat)
        """
        import random
        from .enums import DuelMove, DuelDefense
        
        # Pirate chooses move (random if not specified by player)
        pirate_move = self.chosen_move if self.chosen_move else random.choice(list(DuelMove))
        
        # Target randomly chooses defense
        target_defense = random.choice(list(DuelDefense))
        
        # Define win conditions (pirate perspective)
        win_conditions = {
            (DuelMove.SCIMITAR, DuelDefense.SIDESTEP),
            (DuelMove.RAPIER, DuelDefense.CHAINMAIL),
            (DuelMove.PISTOL, DuelDefense.BACKPEDAL)
        }
        
        pirate_wins = (pirate_move, target_defense) in win_conditions
        
        # Reset chosen move after use so next duel defaults to random unless specified
        self.chosen_move = None
        
        return pirate_wins, pirate_move, target_defense

#--- Placeholder Classes for Roles on the List Without Full Implementation ---

class PlaceholderRole(Role):
    def __init__(self, role_name: RoleName):
        super().__init__()
        # Ensure self.name is always a RoleName enum member
        if isinstance(role_name, RoleName):
            self.name = role_name
        else:
            try:
                self.name = RoleName(role_name)
            except ValueError:
                # Fallback if string cannot be converted to RoleName enum
                self.name = RoleName.INVESTIGATOR # Assign a safe default
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None): pass
    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None): pass

class Veteran(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.VETERAN
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_unique = True
        self.attack = Attack.POWERFUL
        # In ToS-1 a Veteran has NO defense by default and gains BASIC defense only on alert.
        self.defense = Defense.NONE
        self.is_roleblock_immune = True
        self.control_immune = True
        self.action_priority = Priority.PRIORITY_1_HIGHEST
        self.alerts = 3
        self.is_on_alert = False

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        #The decision to alert is made by targeting self.
        if target == player:
            if self.alerts > 0:
                self.alerts -= 1
                self.is_on_alert = True
                player.defense = Defense.BASIC  # On alert the Vet gains BASIC defense
                return f"You have decided to go on alert. You have {self.alerts} alerts remaining."
            else:
                return "You have no alerts left."
        return "You have decided not to go on alert."

    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        #Reset alert status at the beginning of the day
        self.is_on_alert = False
        #player.defense is reset in player.reset_night_states()

#────────────────────────────────────────────────
#Town Investigative – Psychic
#Astral investigative that alternates Good/Evil visions
class Psychic(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.PSYCHIC
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.visit_type = VisitType.ASTRAL  #does not leave home / cannot be seen
        self.action_priority = Priority.PRIORITY_4

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        """Psychic receives a vision – implemented as a notification added during the night.

        Odd-numbered nights (N1, N3 …) – 3 names, one is Evil
        Even nights – 2 names, one is Good
        We simply sample living players (excluding self) and reveal the list.
        """
        if not game:
            return None

        import random
        candidates = [p for p in game.players if p.is_alive and p != player]
        if len(candidates) < 2:
            return None

        #night index == game.day (day counter increments before night)
        if game.day % 2 == 1:  #Odd night → Evil vision
            sample_size = min(3, len(candidates))
            chosen = random.sample(candidates, sample_size)
            evil = random.choice(chosen)
            msg = f"Your vision: {', '.join(p.name for p in chosen)}. One of them is evil."
            player.notifications.append(msg)
            return "You focus on your crystal ball… a dark presence emerges."
        else:  #Even night → Good vision
            sample_size = min(2, len(candidates))
            chosen = random.sample(candidates, sample_size)
            good = random.choice(chosen)
            msg = f"Your vision: {', '.join(p.name for p in chosen)}. One of them is good."
            player.notifications.append(msg)
            return "Your divination reveals a glimpse of hope."

class Spy(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.SPY
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_6

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        # The Spy's passive intel is processed in Game._process_spy_intel.
        # Here we simply confirm the bug choice for player feedback.
        if target:
            return f"You have decided to bug {target.name}'s house.";
        return "You are listening for whispers and watching the villains."

class Tracker(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.TRACKER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.visit_type = VisitType.NON_HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game or not target:
            return "You must select a target."
        
        # Get all non-astral visits made by the target
        from .enums import VisitType
        non_astral_visits = []
        
        # Check each visit to see if it should be visible to Tracker
        for visit_target in getattr(target, 'visiting_all', []):
            # Find the role's visit type by looking up the night action
            if target in game.night_actions:
                # Tracker can see all visits except astral ones
                if target.role.visit_type != VisitType.ASTRAL:
                    non_astral_visits.append(visit_target)
        
        if non_astral_visits:
            if len(non_astral_visits) == 1:
                result = f"Your target visited {non_astral_visits[0].name} tonight."
            else:
                names = [v.name for v in non_astral_visits]
                result = f"Your target visited {', '.join(names)} tonight."
        else:
            result = "Your target did not visit anyone."
        
        player.notifications.append(result)
        return result

class Crusader(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.CRUSADER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not target:
            return None
        target.protected_by.append(player)
        return f"You are protecting {target.name} tonight."

class Trapper(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.TRAPPER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_1
        # Internal state
        self.building = False        # trap under construction (will arm next night)
        self.active = False          # trap is armed and added to game.traps
        self.trap_location = None    # Player where trap is/will be located

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        """Handles building, arming, and dismantling a trap.

        • Choose another player ⇒ begin building a trap there (takes one night).
        • Choose self ⇒ dismantle current (building or active) trap.
        """
        if not game:
            return None

        # Arm trap if construction finished (this happens at start of the *second* night)
        if self.building and not self.active:
            self.active = True
            self.building = False
            game.traps.append({"owner": player, "location": self.trap_location, "active": True})

        # --- Handle tonight's order ---
        if target == player:  # Attempt to dismantle
            if self.building:
                self.building = False
                self.trap_location = None
                return "You stop working on your unfinished trap."
            if self.active:
                # deactivate trap in game.traps
                for tr in game.traps:
                    if tr["owner"] == player and tr["active"]:
                        tr["active"] = False
                        break
                self.active = False
                self.trap_location = None
                return "You dismantle your trap.";
            return "You have no trap to dismantle.";

        # Building new trap
        if self.building or self.active:
            return "You already have a trap; dismantle it first.";

        if not target:
            return "You must select someone to set a trap on.";

        self.building = True
        self.trap_location = target
        return f"You begin constructing a trap at {target.name}'s house. It will be ready tomorrow night."

#────────────────────────────────────────────────
#Town Killing – Vampire Hunter
class VampireHunter(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.VAMPIRE_HUNTER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.KILLING
        self.visit_type = VisitType.HARMFUL
        self.attack_vs_vamp = Attack.POWERFUL
        self.attack = Attack.BASIC
        self.shots = None  #unlimited
        self.defense = Defense.BASIC  # Basic defense against Vampires
        self.detection_immune = True

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game:
            return None

        # Auto-promote to Vigilante once all Vampires are dead.
        if not any(p.is_alive and p.role.name == RoleName.VAMPIRE for p in game.players):
            if self.name != RoleName.VIGILANTE:  # Prevent multiple promotions
                new_role = Vigilante()
                new_role.bullets = 1
                player.assign_role(new_role)
                player.notifications.append("With every Vampire destroyed you take up a gun – you are now a Vigilante (1 bullet)!")
            return "You have become a Vigilante."  # No further action tonight.

        # If no target supplied just wait / listen to chat.
        if not target:
            return "You spend the night listening for the undead."

        if target.role.name == RoleName.VAMPIRE:
            # Stake the Vampire with Powerful attack
            game.register_attack(player, target, Attack.POWERFUL)
            return f"You stake {target.name} – a foul Vampire!"
        else:
            return f"You inspected {target.name} – they do not appear to be a Vampire."

#────────────────────────────────────────────────
#Town Support – Raises a dead Town corpse each night to use its ability once.
#
# Mechanics implemented per ToS 1 / ToS 2 wiki:
#   • Unique role (only one at a time).
#   • Unlimited uses; each corpse can only be used once (rots afterwards).
#   • Role-block & Control immune.
#   • Cannot raise certain roles (Psychic, Trapper, Transporter, Mayor, Medium, Jailor, Veteran, another Retributionist, unique roles).
class Retributionist(Role):
    """Town Support – Raises a dead Town corpse each night to use its ability once.

    Mechanics implemented per ToS 1 / ToS 2 wiki:
      • Unique role (only one at a time).
      • Unlimited uses; each corpse can only be used once (rots afterwards).
      • Role-block & Control immune.
      • Cannot raise certain roles (Psychic, Trapper, Transporter, Mayor, Medium, Jailor, Veteran, another Retributionist, unique roles).
    """

    _UNUSABLE_ROLES = {
        RoleName.PSYCHIC,
        RoleName.TRAPPER,
        RoleName.TRANSPORTER,
        RoleName.MAYOR,
        RoleName.MEDIUM,
        RoleName.JAILOR,
        RoleName.VETERAN,
        RoleName.RETRIBUTIONIST,
    }

    def __init__(self):
        super().__init__()
        self.name = RoleName.RETRIBUTIONIST
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_unique = True
        self.is_roleblock_immune = True
        self.control_immune = True
        # Track corpses already used so they "rot" and cannot be reused.
        self._used_corpses: set['Player'] = set()

    # Retributionist no longer has a day action; all logic happens at night.
    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        return None

    def perform_night_action(self, player: 'Player', target: 'tuple[Player, Player]' = None, game: 'Game' = None):
        """Expect *target* to be a tuple (corpse, second_target)."""
        if not game or not target or not isinstance(target, tuple) or len(target) != 2:
            return "You must choose a corpse and a target (corpse,target)."

        corpse, second_target = target

        # Validate corpse eligibility
        if corpse.is_alive:
            return f"{corpse.name} is still alive – you can only use dead Town members."
        if corpse in self._used_corpses:
            return f"{corpse.name}'s corpse has already rotted and cannot be used again."
        if corpse.role.faction != Faction.TOWN:
            return f"{corpse.name} was not aligned with the Town."
        if corpse.role.is_unique or corpse.role.name in self._UNUSABLE_ROLES:
            return f"You cannot raise a {corpse.role.name.value}."

        # Temporarily re-animate the corpse to perform its ability.
        original_state = corpse.is_alive
        corpse.is_alive = True  # allow ability code to run
        
        # Add notification to the corpse about being raised
        corpse.notifications.append("You have been risen from the dead and compelled into action.")

        try:
            result = corpse.role.perform_night_action(corpse, second_target, game)
        finally:
            # Ensure corpse returns to dead state regardless of errors.
            corpse.is_alive = original_state

        # Mark corpse as used so it "rots".
        self._used_corpses.add(corpse)

        # Tracker/Lookout visibility (simplified): record visits for corpse
        corpse.visit(second_target)

        return f"You raised {corpse.name}'s corpse – {result}"

class Transporter(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.TRANSPORTER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_roleblock_immune = True
        self.control_immune = True
        self.action_priority = Priority.HIGHEST
        self.visit_type = VisitType.NON_HARMFUL
        self.transport_targets = None  # Tuple of (player1, player2) to transport

    def perform_night_action(self, player: 'Player', target: 'tuple[Player, Player]' = None, game: 'Game' = None):
        if not game or not target or not isinstance(target, tuple) or len(target) != 2:
            return "You must choose two people to transport."

        a, b = target
        
        # Cannot transport same person with themselves
        if a == b:
            return "You cannot transport someone with themselves."
        
        # Cannot transport jailed players
        if a.is_jailed or b.is_jailed:
            return "One of your targets was in jail, so you could not transport them."
        
        # Store transport targets for processing in game
        self.transport_targets = (a, b)
        
        # Visit both targets
        player.visit(a)
        player.visit(b)
        
        return f"You will transport {a.name} with {b.name}."

#────────────────────────────────────────────────
#Mafia Deception – Disguiser
class Disguiser(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.DISGUISER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.visit_type = VisitType.NON_HARMFUL  # Disguiser doesn't trigger BG/Trap
        self.disguise_target = None  # Target to disguise as
        self.mafia_target = None     # Mafia member to disguise

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game or not target:
            return "You must select a target to disguise a Mafia member as."

        if target.role.faction == Faction.MAFIA:
            return "You cannot disguise as another Mafia member."
        
        if target.is_jailed:
            return "You cannot disguise as someone who is jailed."

        # Find a living Mafia member to disguise (prioritize non-Disguiser)
        mafia_members = [p for p in game.players if p.is_alive and p.role.faction == Faction.MAFIA and p != player]
        if not mafia_members:
            return "There are no other living Mafia members to disguise."
        
        # Choose the first available Mafia member (could be randomized)
        mafia_member = mafia_members[0]
        
        # Set up the disguise - it will take effect when investigations happen
        # Ensure disguised_role_name is always a RoleName enum member
        disguised_role_name = target.role.name
        if not isinstance(disguised_role_name, RoleName):
            try:
                disguised_role_name = RoleName(disguised_role_name)
            except ValueError:
                # Fallback if string cannot be converted to RoleName enum
                # This should ideally not happen if target.role.name is always a RoleName enum
                disguised_role_name = RoleName.INVESTIGATOR # Assign a safe default
        mafia_member.disguised_as_role = disguised_role_name
        self.disguise_target = target
        self.mafia_target = mafia_member
        
        return f"You have disguised {mafia_member.name} as a {target.role.name.value}."

#Mafia Deception – Forger
class Forger(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.FORGER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.visit_type = VisitType.ASTRAL
        self.charges = 2

    def perform_night_action(self, player:'Player', target:'Player'=None, game:'Game'=None):
        if self.charges <= 0:
            return "You have no forging ink left."
        if not game or not target:
            return "You must choose someone to forge."

        target.was_forged = True
        self.charges -= 1
        return f"You forged {target.name}'s last will. ({self.charges} charges left)"

#Mafia Deception – Framer
class Framer(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.FRAMER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.visit_type = VisitType.NON_HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game or not target:
            return None
        target.is_framed = True
        return f"You framed {target.name} tonight."

#────────────────────────────────────────────────
#Mafia Deception – Hypnotist
class Hypnotist(Role):
    _messages = [
        "You were healed last night!",
        "Someone tried to role block you but failed!",
        "You were transported to another location!",
        "You were visited by a vampire but fought them off!",
        "A bodyguard protected you last night!",
    ]

    def __init__(self):
        super().__init__()
        self.name = RoleName.HYPNOTIST
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.visit_type = VisitType.NON_HARMFUL

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game or not target:
            return None
        import random
        msg = random.choice(self._messages)
        target.notifications.append(msg)
        return f"You hypnotized {target.name} – they will see: '{msg}'"

#Mafia Deception – Janitor
class Janitor(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.JANITOR
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3
        self.visit_type = VisitType.HARMFUL
        self.charges = 3

    def perform_night_action(self, player:'Player', target:'Player'=None, game:'Game'=None):
        if not game or not target:
            return "You must select a target to clean."

        if self.charges <= 0:
            return "You are out of cleaning supplies."  # no charges

        # Mark the target for potential cleaning if they die.
        target.cleaned_by = player

        # We will only consume a charge if the clean actually triggers (handled in Game._announce_deaths).
        return f"You will attempt to clean {target.name}'s body tonight."

#────────────────────────────────────────────────
#Neutral Benign – Amnesiac
class Amnesiac(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.AMNESIAC
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.detection_immune = True
        self.visit_type = VisitType.ASTRAL  # assumed astral per wiki
        self.action_priority = Priority.FINALIZATION  # very low priority
        self.remembered = False

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game or not target:
            return "You must select a corpse to remember."

        if target.is_alive:
            return "You may only remember roles from the graveyard."

        # Prevent duplicate remembers of unique roles
        if target.role.is_unique:
            # If any living player already has that role, fail.
            if any(p.is_alive and p.role.name == target.role.name for p in game.players):
                return f"Someone already occupies the unique role {target.role.name.value}. Your memory fails."

        # Edge-cases: Godfather / Coven Leader / Pestilence special downgrades
        remembered_role_name = target.role.name
        if remembered_role_name == RoleName.GODFATHER:
            mafia_alive = any(p.is_alive and p.role.faction == Faction.MAFIA and p.role.name != RoleName.GODFATHER for p in game.players)
            if not mafia_alive:
                remembered_role_name = RoleName.MAFIOSO
        elif remembered_role_name == RoleName.COVEN_LEADER:
            coven_alive = any(p.is_alive and p.role.faction == Faction.COVEN for p in game.players)
            if coven_alive:
                # Guaranteed Necronomicon later – handled by existing nighttime allocation
                pass
        elif remembered_role_name == RoleName.PESTILENCE:
            remembered_role_name = RoleName.PLAGUEBEARER

        # Mark the intention – actual switch happens at dawn so defense doesn't apply tonight
        player.remember_role_name = remembered_role_name
        player.notifications.append(f"You will remember being a {remembered_role_name.value} tomorrow.")
        return f"You focus on memories of being a {remembered_role_name.value}."

class Ambusher(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.AMBUSHER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.HIGHEST  #pick ambush location
        self.attack = Attack.BASIC
        self.visit_type = VisitType.HARMFUL
        self.ambush_location: 'Player' | None = None

    def perform_night_action(self, player: 'Player', target: 'Player', game: 'Game' = None):
        if not target or not game:
            return "You must select a target to ambush."
        self.ambush_location = target
        return f"You are waiting outside {target.name}'s house to ambush visitors."

class Blackmailer(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.BLACKMAILER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_3

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game or not target:
            return "You must select a target to blackmail."

        target.is_blackmailed = True
        target.notifications.append("You felt a sinister presence last night. You are being blackmailed and cannot speak today!")
        return f"You have decided to blackmail {target.name}."

    def get_info(self):
        #In a real game, this would allow reading whispers.
        #We can simulate this by giving the Blackmailer access to a whisper channel.
        return {"can_read_whispers": True}

class GuardianAngel(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.GUARDIAN_ANGEL
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_2
        self.visit_type = VisitType.ASTRAL
        self.protect_target: 'Player' | None = None
        self.control_immune = True
        self.detection_immune = True

    def assign_protect_target(self, game: 'Game'):
        choices = [p for p in game.players if p != game.get_player_by_name(self.name)]
        if choices:
            self.protect_target = random.choice(choices)

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        #Guardian angel always protects their assigned target, ignoring provided target.
        if not self.protect_target:
            return "No assigned target to protect."
        self.protect_target.protected_by.append(player)
        return f"You are shielding {self.protect_target.name} tonight."

class Survivor(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.SURVIVOR
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.vests = 4
        self.visit_type = VisitType.ASTRAL
        self.action_priority = Priority.PRIORITY_3

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if self.vests > 0:
            self.vests -= 1
            player.defense = Defense.BASIC
            return f"You used a bulletproof vest tonight. Vests left: {self.vests}."
        return "You have no vests remaining."

class Executioner(Role):
    """Neutral Evil role whose sole goal is to get their randomly-assigned Town target lynched."""

    def __init__(self):
        super().__init__()
        self.name = RoleName.EXECUTIONER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_6  # very low – no real night action
        self.defense = Defense.BASIC
        self.detection_immune = True
        self.visit_type = VisitType.NON_HARMFUL

        # The Town player the Executioner wants lynched. Chosen at game start.
        self.target: 'Player' | None = None

    def assign_target(self, game: 'Game'):
        """Pick a random Town player other than self. Called by Game at init."""
        town_candidates = [p for p in game.players
                           if p.role.faction == Faction.TOWN
                           and p.name != self.name
                           and p.role.name not in [RoleName.MAYOR, RoleName.JAILOR]]
        if town_candidates:
            self.target = random.choice(town_candidates)

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        """Executioner has no night power; return a flavour string for logs."""
        return "You obsess over getting your target lynched…"

class Jester(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.JESTER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_roleblock_immune = False
        self.detection_immune = True
        self.action_priority = Priority.DAY_ACTION #Haunting is a result of a day lynch
        self.astral_immune = True  # simple flag for future use

    def perform_day_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        #This is for haunting. It should only be called if the jester is lynched.
        if not target:
            return "You must select a target to haunt."
        if not game:
            return
        
        #Jester's haunt is an unstoppable attack
        game.register_attack(player, target, Attack.UNSTOPPABLE, is_haunt=True)
        return f"You have chosen to haunt {target.name}. Their death will be a spectacle!"

    def on_lynch(self, game: 'Game'):
        #In a real game, this would trigger the haunting ability.
        #The player would then choose a target from the players who voted guilty.
        #Here we'll simply log the event.
        print(f"JESTER WIN: {self.name} has been lynched and will haunt someone!")

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        pass

class Witch(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.WITCH
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.attack = Attack.BASIC
        self.defense = Defense.NONE
        self.is_roleblock_immune = True
        self.detection_immune = True
        self.control_immune = True
        self.action_priority = Priority.PRIORITY_2
        self.has_been_attacked = False

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game:
            return

        # Expect the player to have submitted a tuple (control_target, force_target)
        # through the InteractionHandler stored in game.night_actions.
        try:
            control_target, force_target = game.night_actions[player]
        except (KeyError, TypeError, ValueError):
            return "You must select two targets to perform your dark magic."

        if not control_target or not force_target:
            return "You must select two targets."

        if control_target.role.control_immune:
            control_target.notifications.append("Someone tried to control you but you were immune!")
            return "Your target was immune to control!"

        # Apply control – replace their submitted action with the forced one
        game.night_actions[control_target] = force_target
        control_target.is_controlled = True
        control_target.notifications.append(f"You were controlled by a Witch! You were forced to target {force_target.name}.")

        return f"You have controlled {control_target.name} and forced them to target {force_target.name}."

    def on_attacked(self, attacker):
        if not self.has_been_attacked:
            self.has_been_attacked = True
            print(f"[Witch] The witch was attacked by {attacker.name} and can now curse them.")

#────────────────────────────────────────────────
#Neutral Killing – Juggernaut
class Juggernaut(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.JUGGERNAUT
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.kills = 0
        self.attack = Attack.BASIC
        self.defense = Defense.NONE
        self.action_priority = Priority.PRIORITY_5
        self.visit_type = VisitType.HARMFUL

    def _update_power(self):
        if self.kills >= 4:
            self.attack = Attack.UNSTOPPABLE
            self.defense = Defense.INVINCIBLE
        elif self.kills >= 2:
            self.attack = Attack.POWERFUL
            self.defense = Defense.POWERFUL
        elif self.kills >= 1:
            self.attack = Attack.POWERFUL
            self.defense = Defense.BASIC

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        if not game:
            return None

        # Before first kill: only act on full-moon (even) nights
        if self.kills == 0 and game.day % 2 != 0:
            return "It is not a full moon. You wait to build your strength."

        # If no target chosen, stay home (no effect)
        if not target:
            return "You chose no target tonight."

        self._update_power()

        if self.kills >= 2:
            # Rampage at location – hit target and visitors
            game.register_attack(player, target, self.attack)
            for v in target.targeted_by:
                if v.is_alive:
                    game.register_attack(player, v, self.attack, is_primary=False)
            return f"You rampage at {target.name}'s house with {self.attack.name.lower()} force!"
        else:
            game.register_attack(player, target, self.attack)
            return f"You strike {target.name} with {self.attack.name.lower()} force."

    #Called by game when a kill is confirmed (hook not yet wired; simple public method)
    def register_kill(self):
        self.kills += 1
        self._update_power()

#────────────────────────────────────────────────
#Neutral Killing – Werewolf
class Werewolf(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.WEREWOLF
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_5
        self.attack = Attack.POWERFUL
        self.visit_type = VisitType.HARMFUL  #Rampage at location
        self.full_moon_cycle = 2  #every 2nd night starting N2
        self.is_roleblock_immune = False  # Werewolf is not roleblock immune

    def _is_full_moon(self, game: 'Game'):
        #Night number is game.day; full moon nights are even-numbered nights (N2,4…)
        return game.day % self.full_moon_cycle == 0

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        """Implements full-moon rampage logic.

        • Full-moon check – only acts on even night numbers (N2, N4 …).
        • If jailed (but not executed) attack Jailor inside cell.
        • If no target or target is self ⇒ rampage at home.
        • Otherwise rampage at target's house, also hitting their visitors.
        • If the chosen target is jailed: rampage hits *visitors* to the jailed player instead.
        • If trying to skip on full moon, forced to rampage at home.
        """
        if not game:
            return None

        # Full moon gating
        if not self._is_full_moon(game):
            return "It is not a full moon. You stay home snarling."

        # In jail – Jailor did not execute ⇒ strike Jailor
        if player.is_jailed:
            jailor = game.find_player_by_role(RoleName.JAILOR)
            if jailor and jailor.is_alive and not getattr(jailor.role, 'executing', False):
                game.register_attack(player, jailor, self.attack)
                return "You transform inside the jail and maul the Jailor!"
            return "You were executed in jail."  # handled elsewhere

        # Check if trying to skip - on full moon, forced to rampage at home
        if target is None:
            # Stay home – attack all visitors (but not self)
            victims = [v for v in player.targeted_by if v.is_alive and v != player]
            for v in victims:
                game.register_attack(player, v, self.attack, is_primary=False)
            if victims:
                return f"You cannot control your bloodlust on a full moon! You rampage at home and tear apart: {', '.join(v.name for v in victims)}."
            return "You cannot control your bloodlust on a full moon! You rampage at home but no one came."

        # Determine rampage location
        if target == player:
            # Stay home – attack all visitors (but not self)
            victims = [v for v in player.targeted_by if v.is_alive and v != player]
            for v in victims:
                game.register_attack(player, v, self.attack, is_primary=False)
            if victims:
                return f"You rampage at home and tear apart: {', '.join(v.name for v in victims)}."
            return "You rampage at home but no one came."

        # If target jailed, hit visitors only (not Jailor or prisoner)
        if target.is_jailed:
            visitors = [v for v in target.targeted_by if v.is_alive and v != player]
            for v in visitors:
                game.register_attack(player, v, self.attack, is_primary=False)
            return f"Your prey was in jail; you ravaged their would-be visitors instead!"

        # Normal rampage at target's house - attack target and ALL visitors
        game.register_attack(player, target, self.attack)
        for v in target.targeted_by:
            if v.is_alive and v != player:  # Don't attack self
                game.register_attack(player, v, self.attack, is_primary=False)
        return f"You rampage at {target.name}'s house, mauling everyone inside!"

#Neutral Chaos – Plaguebearer / Pestilence
class Plaguebearer(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.PLAGUEBEARER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.infected = set()
        self.action_priority = Priority.PRIORITY_3

    def perform_night_action(self, player:'Player', target:'Player'=None, game:'Game'=None):
        if not game:
            return "You must select a target."

        # If targeting self or no target, stay home and infect visitors
        if not target or target == player:
            for visitor in player.targeted_by:
                if visitor.is_alive and not visitor.is_infected:
                    visitor.is_infected = True
                    visitor.notifications.append("You feel a strange plague stirring within you.")
                    print(f"[Plaguebearer] {visitor.name} was infected by visiting {player.name}.")
            result = "You spread your plague to anyone who visits you."
        else:
            # Visit target and infect them + their visitors
            if not target.is_infected:
                target.is_infected = True
                target.notifications.append("You feel a strange plague stirring within you.")
                print(f"[Plaguebearer] {player.name} infected {target.name}.")
            
            # Also infect anyone visiting the target
            for visitor in target.targeted_by:
                if visitor.is_alive and not visitor.is_infected:
                    visitor.is_infected = True
                    visitor.notifications.append("You feel a strange plague stirring within you.")
                    print(f"[Plaguebearer] {visitor.name} was infected by visiting {target.name}.")
            
            result = f"You infected {target.name} and anyone who visited them."

        # Check if all others are infected (transformation condition)
        others = [p for p in game.players if p != player and p.is_alive]
        if others and all(p.is_infected for p in others):
            player.assign_role(Pestilence())
            player.notifications.append("You have become Pestilence, Horseman of the Apocalypse!")
            return "The plague has consumed the town! You transform into Pestilence."

        # Message feedback
        if target and target != player:
            return f"You infected {target.name} and anyone who visited them."
        else:
            return "You linger at home, ready to infect any visitor."

class Pestilence(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.PESTILENCE
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.attack = Attack.UNSTOPPABLE
        self.defense = Defense.INVINCIBLE
        self.action_priority = Priority.KILLING
        self.visit_type = VisitType.HARMFUL

    def perform_night_action(self, player:'Player', target:'Player'=None, game:'Game'=None):
        if not game or not target:
            return None
        #Rampage like Werewolf every night – attack target and everyone who visits them.
        #Pestilence should NEVER damage itself, even if it chooses to remain at home.
        
        # If the selected target is the Pestilence itself (stay-home rampage), only strike visitors.
        if target == player:
            for v in player.targeted_by:
                if v.is_alive and v != player:
                    game.register_attack(player, v, self.attack, is_primary=False)
            return "You rampage at home, striking all who dared approach you."

        # Normal rampage on another player
        game.register_attack(player, target, self.attack)
        for v in target.targeted_by:
            if v.is_alive and v != player:  # exclude self to avoid suicide
                game.register_attack(player, v, self.attack, is_primary=False)
        return f"You rampage at {target.name}."

#Neutral Chaos – Vampire
class Vampire(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.VAMPIRE
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.action_priority = Priority.PRIORITY_5
        self.visit_type = VisitType.NON_HARMFUL
        self.detection_immune = True
        self.attack = Attack.BASIC  # Attack strength when biting non-convertible target or >4 vamps
        self.bite_cooldown = 0  # Must wait a night after successful conversion
        self.youngest_vampire = False  # Track if this is the youngest vampire

    def perform_night_action(self, player:'Player', target:'Player'=None, game:'Game'=None):
        if not game:
            return "You decided not to bite tonight."
        
        # Check if on cooldown
        if self.bite_cooldown > 0:
            self.bite_cooldown -= 1
            return "You must wait another night before biting again."
        
        # Vampire voting system - collect all vampire votes
        vampires = [p for p in game.players if p.is_alive and p.role.name == RoleName.VAMPIRE]
        vampire_votes = {}
        
        # Collect votes from all vampires
        for vamp in vampires:
            vamp_target = game.night_actions.get(vamp)
            if vamp_target and vamp_target != player:  # Don't count self-votes
                if vamp_target not in vampire_votes:
                    vampire_votes[vamp_target] = 0
                vampire_votes[vamp_target] += 1
        
        if not vampire_votes:
            return "No vampires voted to bite anyone tonight."
        
        # Determine target based on weighted random selection
        import random
        total_votes = sum(vampire_votes.values())
        targets_and_weights = [(target, votes/total_votes) for target, votes in vampire_votes.items()]
        
        # Weighted random selection
        rand = random.random()
        cumulative = 0
        selected_target = None
        for target, weight in targets_and_weights:
            cumulative += weight
            if rand <= cumulative:
                selected_target = target
                break
        
        if not selected_target:
            selected_target = random.choice(list(vampire_votes.keys()))
        
        # Find youngest vampire to perform the bite
        youngest = min(vampires, key=lambda v: getattr(v, 'vampire_age', 0))
        
        # Only the youngest vampire actually performs the visit
        if player != youngest:
            return f"The vampires voted to bite {selected_target.name}. {youngest.name} will perform the bite."
        
        # Youngest vampire performs the bite
        return self._perform_bite(player, selected_target, game, vampires)
    
    def _perform_bite(self, player, target, game, vampires):
        """Perform the actual bite attempt."""
        vampire_count = len(vampires)
        
        # Check target's role and defense
        if target.role.name == RoleName.VAMPIRE_HUNTER:
            # Vampire Hunter kills the biting vampire
            game.register_attack(target, player, Attack.BASIC)
            return f"You tried to bite {target.name}, but they were a Vampire Hunter and killed you!"
        
        if target.role.name == RoleName.VAMPIRE:
            return f"{target.name} is already a vampire."
        
        # Check if target has defense
        if target.defense != Defense.NONE:
            return f"You tried to bite {target.name}, but their defense was too strong!"
        
        # Check vampire count - if 4+ vampires, kill instead of convert
        if vampire_count >= 4:
            # Kill non-convertible targets or when at max capacity
            convertible_roles = {
                RoleName.INVESTIGATOR, RoleName.LOOKOUT, RoleName.SHERIFF, RoleName.SPY, RoleName.PSYCHIC, RoleName.TRACKER,
                RoleName.BODYGUARD, RoleName.CRUSADER, RoleName.DOCTOR, RoleName.TRAPPER,
                RoleName.VIGILANTE, RoleName.VETERAN, RoleName.VAMPIRE_HUNTER,
                RoleName.MAYOR, RoleName.MEDIUM, RoleName.RETRIBUTIONIST, RoleName.TAVERN_KEEPER, RoleName.TRANSPORTER,
                RoleName.SURVIVOR, RoleName.AMNESIAC, RoleName.JESTER
            }
            
            if target.role.name not in convertible_roles or target.role.faction in [Faction.MAFIA, Faction.COVEN]:
                game.register_attack(player, target, self.attack)
                # Reset cooldown for all vampires since they killed
                for vamp in vampires:
                    vamp.role.bite_cooldown = 0
                return f"You bit {target.name} and killed them (4+ vampires or non-convertible target)."
            else:
                game.register_attack(player, target, self.attack)
                for vamp in vampires:
                    vamp.role.bite_cooldown = 0
                return f"You bit {target.name} and killed them (vampire capacity reached)."
        
        # Check if target is convertible
        convertible_roles = {
            RoleName.INVESTIGATOR, RoleName.LOOKOUT, RoleName.SHERIFF, RoleName.SPY, RoleName.PSYCHIC, RoleName.TRACKER,
            RoleName.BODYGUARD, RoleName.CRUSADER, RoleName.DOCTOR, RoleName.TRAPPER,
            RoleName.VIGILANTE, RoleName.VETERAN, RoleName.VAMPIRE_HUNTER,
            RoleName.MAYOR, RoleName.MEDIUM, RoleName.RETRIBUTIONIST, RoleName.TAVERN_KEEPER, RoleName.TRANSPORTER,
            RoleName.SURVIVOR, RoleName.AMNESIAC, RoleName.JESTER
        }
        
        # Non-convertible roles get killed
        if target.role.name not in convertible_roles or target.role.faction in [Faction.MAFIA, Faction.COVEN]:
            game.register_attack(player, target, self.attack)
            # Reset cooldown for all vampires since they killed
            for vamp in vampires:
                vamp.role.bite_cooldown = 0
            return f"You bit {target.name} and killed them (non-convertible role)."
        
        # Success - convert to vampire
        target.assign_role(Vampire())
        target.role.vampire_age = max(getattr(v.role, 'vampire_age', 0) for v in vampires) + 1
        target.notifications.append("Cold fangs pierce your neck – you have become a Vampire! Embrace the night.")
        
        # Set cooldown for all vampires
        for vamp in vampires + [target]:
            vamp.role.bite_cooldown = 1
        
        # Notify all vampires of the bite
        bite_msg = f"The Vampires visited {target.name} last night."
        for vamp in vampires + [target]:
            vamp.notifications.append(bite_msg)
        
        print(f"[Vampire] {target.name} has been converted to a Vampire!")
        return f"You successfully converted {target.name} into a vampire."

class CovenLeader(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.COVEN_LEADER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_coven = True
        self.action_priority = Priority.CONTROL_PROTECTION
        self.is_roleblock_immune = True
        self.control_immune = True
        self.visit_type = VisitType.HARMFUL

    def perform_night_action(self, player:'Player', target:'Player'=None, game:'Game'=None):
        if not game:
            return None

        # InteractionHandler always stores tuple (puppet, victim)
        try:
            puppet, victim = game.night_actions[player]
        except (KeyError, TypeError, ValueError):
            return "You must select two targets to direct your magic."

        if not puppet or not victim:
            return "You must select two targets."

        # Handle control immunity
        if puppet.role.control_immune:
            puppet.notifications.append("Someone tried to control you but you were immune!")
            return "Your puppet resisted your control!"

        # Apply control – overwrite puppet's submitted action (or add one) with forced victim
        game.night_actions[puppet] = victim
        puppet.is_controlled = True
        puppet.notifications.append(f"You were controlled by dark magic! You were forced to target {victim.name}.")

        msg = f"You controlled {puppet.name} to target {victim.name}."

        # Necronomicon bonus attack (Powerful) on the victim
        if self.has_necronomicon:
            game.register_attack(player, victim, Attack.POWERFUL)
            msg += f" Using the Necronomicon, you also attack {victim.name}."

        return msg

class Medusa(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.MEDUSA
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_coven = True
        self.visit_type = VisitType.ASTRAL
        self.action_priority = Priority.SUPPORT_DECEPTION  #stone gaze before investigator
        self.stone_charges = 3

    def perform_night_action(self, player, target=None, game=None):
        if not game:
            return None

        #With book: can actively visit & attack
        if self.has_necronomicon and target and target != player:
            game.register_attack(player, target, Attack.POWERFUL)
            target.was_stoned = True
            return f"You visited and stoned {target.name}."

        #Without book or self target: use stone gaze on visitors
        if self.stone_charges <= 0:
            return "You are out of stone-gaze charges."
        self.stone_charges -= 1
        victims = [v for v in player.targeted_by if v.is_alive and v != player]
        for v in victims:
            game.register_attack(player, v, Attack.POWERFUL, is_primary=False)
            v.was_stoned = True
        return f"You used stone gaze. Visitors petrified: {', '.join([v.name for v in victims]) if victims else 'none'}. Charges left {self.stone_charges}."

class HexMaster(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.HEX_MASTER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_coven = True
        self.action_priority = Priority.INVESTIGATION
        self.visit_type = VisitType.ASTRAL

    def perform_night_action(self, player, target=None, game=None):
        if not game or not target:
            return "You must choose a target."
        #mark hexed
        target.is_hexed = True
        if self.has_necronomicon:
            game.register_attack(player, target, Attack.BASIC)
            return f"You hexed and attacked {target.name}."
        return f"You hexed {target.name}."

class PotionMaster(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.POTION_MASTER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_coven = True
        self.action_priority = Priority.PRIORITY_3
        # Track individual potion cooldowns (heal/reveal/attack)
        self._cooldowns = {"heal": 0, "reveal": 0, "attack": 0}
        self._last_used = None  # last potion used

    def perform_night_action(self, player: 'Player', target: 'Player' = None, game: 'Game' = None):
        """Rotate through Heal → Reveal → Attack, each on a 3-night cooldown.

        With the Necronomicon, cooldowns are ignored.
        """
        if not game or not target:
            return "You chose not to use a potion."

        # Select next potion type respecting cooldowns
        order = ["heal", "reveal", "attack"]
        choice = None

        # If Necronomicon held, never any cooldown – just cycle
        if self.has_necronomicon:
            idx = 0 if self._last_used is None else (order.index(self._last_used) + 1) % 3
            choice = order[idx]
        else:
            # Find first potion whose cooldown is 0, in order heal->reveal->attack
            for pot in order:
                if self._cooldowns[pot] == 0:
                    choice = pot
                    break
            if choice is None:
                return "All of your potions are re-charging."  # edge case

        # Apply potion effect
        if choice == "attack":
            atk = Attack.BASIC if not self.has_necronomicon else Attack.POWERFUL
            game.register_attack(player, target, atk)
            result = f"You hurled a harmful potion at {target.name}."
        elif choice == "heal":
            target.defense = Defense.POWERFUL if self.has_necronomicon else Defense.BASIC
            target.notifications.append("You feel rejuvenated by powerful alchemical energies!")
            result = f"You healed {target.name}."
        else:  # reveal
            role_name = target.role.name.value
            for coven_member in [p for p in game.players if p.role.is_coven]:
                coven_member.notifications.append(f"Potion vision: {target.name} is a {role_name}.")
            result = f"You revealed {target.name}'s role to the Coven."

        # Update cooldowns (skip if Necronomicon)
        if not self.has_necronomicon:
            # Set chosen potion to cooldown 3, decrement others if >0
            for pot in order:
                if self._cooldowns[pot] > 0:
                    self._cooldowns[pot] -= 1
            self._cooldowns[choice] = 3

        self._last_used = choice
        return result

class Poisoner(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.POISONER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_coven = True
        self.action_priority = Priority.KILLING

    def perform_night_action(self, player,target=None,game=None):
        if not game or not target:
            return "You must pick someone to poison."
        #Can't poison same person twice
        if target.is_poisoned:
            return f"{target.name} is already poisoned."
        target.is_poisoned = True
        target.poison_timer = 0
        target.poison_uncurable = self.has_necronomicon
        return f"You have poisoned {target.name}."

class Necromancer(Role):
    def __init__(self):
        super().__init__()
        self.name = RoleName.NECROMANCER
        self.alignment = get_role_alignment(self.name)
        self.faction = get_role_faction(self.name)
        self.is_coven = True
        self.is_unique = True
        self.is_roleblock_immune = True
        self.control_immune = True
        self.detection_immune = False
        self.action_priority = Priority.INVESTIGATION
        # Track used corpses so they "rot" after one night
        self._used_corpses: set['Player'] = set()
        from .enums import VisitType
        self.visit_type = VisitType.ASTRAL

    def perform_night_action(self, player: 'Player', target: 'tuple[Player, Player]' = None, game: 'Game' = None):
        """Expect *target* to be a tuple (corpse, victim).

        The selected corpse is temporarily re-animated to perform its own ability
        on the second target. Each corpse can only be used once.
        """
        if not game or not isinstance(target, tuple) or len(target) != 2:
            return "You must choose a corpse and a target (corpse,target)."

        corpse, victim = target

        if corpse.is_alive:
            return f"{corpse.name} is still alive – you can only reanimate the dead."
        if corpse in self._used_corpses:
            return f"{corpse.name}'s corpse has already rotted and cannot be used again."
        if corpse.was_cleaned:
            return f"{corpse.name}'s identity was hidden. You cannot reanimate this corpse."

        # Temporarily bring corpse to life to run its ability
        original_state = corpse.is_alive
        corpse.is_alive = True
        try:
            result = corpse.role.perform_night_action(corpse, victim, game)
        finally:
            corpse.is_alive = original_state

        self._used_corpses.add(corpse)

        # Register visit for lookout / tracker purposes
        corpse.visit(victim)

        return f"You reanimated {corpse.name}'s corpse – {result}"

#The canonical map of all roles in the game
role_map = {
    RoleName.INVESTIGATOR: Investigator,
    RoleName.LOOKOUT: Lookout,
    RoleName.PSYCHIC: Psychic,
    RoleName.SHERIFF: Sheriff,
    RoleName.SPY: Spy,
    RoleName.TRACKER: Tracker,
    RoleName.BODYGUARD: Bodyguard,
    RoleName.CRUSADER: Crusader,
    RoleName.DOCTOR: Doctor,
    RoleName.TRAPPER: Trapper,
    RoleName.JAILOR: Jailor,
    RoleName.VAMPIRE_HUNTER: VampireHunter,
    RoleName.VETERAN: Veteran,
    RoleName.VIGILANTE: Vigilante,
    RoleName.MAYOR: Mayor,
    RoleName.MEDIUM: Medium,
    RoleName.RETRIBUTIONIST: Retributionist,
    RoleName.TAVERN_KEEPER: TavernKeeper,
    RoleName.TRANSPORTER: Transporter,
    RoleName.DISGUISER: Disguiser,
    RoleName.FORGER: Forger,
    RoleName.FRAMER: Framer,
    RoleName.HYPNOTIST: Hypnotist,
    RoleName.JANITOR: Janitor,
    RoleName.AMNESIAC: Amnesiac,
    RoleName.AMBUSHER: Ambusher,
    RoleName.BLACKMAILER: Blackmailer,
    RoleName.GUARDIAN_ANGEL: GuardianAngel,
    RoleName.SURVIVOR: Survivor,
    RoleName.EXECUTIONER: Executioner,
    RoleName.JESTER: Jester,
    RoleName.WITCH: Witch,
    RoleName.ARSONIST: Arsonist,
    RoleName.PESTILENCE: Pestilence,
    RoleName.PLAGUEBEARER: Plaguebearer,
    RoleName.VAMPIRE: Vampire,
    RoleName.COVEN_LEADER: CovenLeader,
    RoleName.MEDUSA: Medusa,
    RoleName.HEX_MASTER: HexMaster,
    RoleName.POTION_MASTER: PotionMaster,
    RoleName.POISONER: Poisoner,
    RoleName.NECROMANCER: Necromancer,
    #Compatibility for old names, pointing to the new classes
    RoleName.ESCORT: TavernKeeper,
    RoleName.CONSORT: Bootlegger,
    RoleName.SERIAL_KILLER: SerialKiller,
    RoleName.PIRATE: Pirate,
    RoleName.JUGGERNAUT: Juggernaut,
    RoleName.WEREWOLF: Werewolf,
    RoleName.BOOTLEGGER: Bootlegger,
} 

def create_role_from_name(role_name: RoleName) -> 'Role':
    """Factory function to create a role instance from a RoleName enum."""
    role_class_map = {
        RoleName.SHERIFF: Sheriff,
        RoleName.INVESTIGATOR: Investigator,
        RoleName.LOOKOUT: Lookout,
        RoleName.DOCTOR: Doctor,
        RoleName.BODYGUARD: Bodyguard,
        RoleName.CRUSADER: Crusader,
        RoleName.VIGILANTE: Vigilante,
        RoleName.MAYOR: Mayor,
        RoleName.MEDIUM: Medium,
        RoleName.TAVERN_KEEPER: TavernKeeper,
        RoleName.GODFATHER: Godfather,
        RoleName.MAFIOSO: Mafioso,
        RoleName.SERIAL_KILLER: SerialKiller,
        RoleName.JAILOR: Jailor,
        RoleName.CONSIGLIERE: Consigliere,
        RoleName.BOOTLEGGER: Bootlegger,
        RoleName.ARSONIST: Arsonist,
        RoleName.PIRATE: Pirate,
        RoleName.VETERAN: Veteran,
        RoleName.PSYCHIC: Psychic,
        RoleName.SPY: Spy,
        RoleName.TRACKER: Tracker,
        RoleName.TRAPPER: Trapper,
        RoleName.VAMPIRE_HUNTER: VampireHunter,
        RoleName.RETRIBUTIONIST: Retributionist,
        RoleName.TRANSPORTER: Transporter,
        RoleName.DISGUISER: Disguiser,
        RoleName.FORGER: Forger,
        RoleName.FRAMER: Framer,
        RoleName.HYPNOTIST: Hypnotist,
        RoleName.JANITOR: Janitor,
        RoleName.AMNESIAC: Amnesiac,
        RoleName.AMBUSHER: Ambusher,
        RoleName.BLACKMAILER: Blackmailer,
        RoleName.GUARDIAN_ANGEL: GuardianAngel,
        RoleName.SURVIVOR: Survivor,
        RoleName.EXECUTIONER: Executioner,
        RoleName.JESTER: Jester,
        RoleName.WITCH: Witch,
        RoleName.JUGGERNAUT: Juggernaut,
        RoleName.WEREWOLF: Werewolf,
        RoleName.PLAGUEBEARER: Plaguebearer,
        RoleName.PESTILENCE: Pestilence,
        RoleName.VAMPIRE: Vampire,
        RoleName.COVEN_LEADER: CovenLeader,
        RoleName.MEDUSA: Medusa,
        RoleName.POTION_MASTER: PotionMaster,
        RoleName.POISONER: Poisoner,
        RoleName.NECROMANCER: Necromancer,
        RoleName.HEX_MASTER: HexMaster,
    }
    # Handle aliases
    if role_name == RoleName.ESCORT:
        role_name = RoleName.TAVERN_KEEPER
    if role_name == RoleName.CONSORT:
        role_name = RoleName.BOOTLEGGER
        
    role_class = role_class_map.get(role_name)
    if role_class:
        return role_class()
    
    # Fallback for roles not fully implemented yet
    return PlaceholderRole(role_name) 
