from .config import GameConfiguration
from .player import Player
from .enums import Faction, RoleName, Attack, Defense, Time, Phase, VisitType, Priority, ImmunityType, RoleAlignment
from .roles import Role, Arsonist, SerialKiller, has_immunity, create_role_from_name
from .day_phase import DayPhase
import random
from collections import defaultdict
from .chat import ChatManager, ChatChannelType
from .debug_utils import debug_print, debug_exception

class Game:
    def __init__(self, config: GameConfiguration, players: list[Player]):
        self.config = config
        self.players = players
        self.day = 0
        self.time = Time.DAY
        from .enums import Phase as PhaseEnum
        self.phase = PhaseEnum.DISCUSSION  # start with open discussion before Day 0
        self.graveyard = []
        self.day_actions = {}
        self.night_actions = {}
        self.night_attacks = []
        self.winners: list[Player] = []
        self.draw: bool = False
        self.traps = []  #list of traps
        #Stores details of deaths that occurred during the last night.
        #Each element is a dict with keys: 'victim' (Player) and 'attacker' (Player)
        self.deaths_last_night: list[dict] = []
        #Day-without-death counter for automatic draw detection (ToS rule)
        self.days_without_death: int = 0
        
        #The active day phase manager, if one exists
        self.day_phase_manager = None

        #Chat system
        self.chat = ChatManager()

        #At game start put living players in Day Public (write+read) and dead channel read only
        for p in self.players:
            if p.is_alive:
                self.chat.move_player_to_channel(p, ChatChannelType.DAY_PUBLIC, write=True, read=True)
            else:
                self.chat.move_player_to_channel(p, ChatChannelType.DEAD, write=True, read=True)

        #assign targets to executioners
        for pl in self.players:
            if pl.role.name == RoleName.EXECUTIONER and pl.role.target is None:
                pl.role.assign_target(self)
            if pl.role.name == RoleName.GUARDIAN_ANGEL and getattr(pl.role, 'protect_target', None) is None:
                pl.role.assign_protect_target(self)

        print("\n----- Day 0 -----")
        print("Players gather in town square. No votes or kills can occur yet.")
        #Prepare day chat for Day 0
        self._setup_day_chat()
        #Night actions will begin when the controller calls advance_to_night()

    def get_player_by_name(self, name: str) -> Player | None:
        for player in self.players:
            if player.name == name:
                return player
        return None

    def find_player_by_role(self, role_name: RoleName) -> Player | None:
        """Finds the first living player with a given role."""
        for player in self.players:
            if player.is_alive and player.role.name == role_name:
                return player
        return None

    #------------------------------------------------------------------
    #External State Advancement API
    #------------------------------------------------------------------

    def advance_to_day(self):
        """Prepares the game for the start of a new day.
        
        This should be called by the external game loop controller.
        """
        from .enums import Phase as PhaseEnum
        self.day += 1
        self.time = Time.DAY
        # Explicit discussion sub-phase
        self.phase = PhaseEnum.DISCUSSION
        self.day_phase_manager = DayPhase(self)
        print(f"\n----- Day {self.day} -----")

        # Start new chat period (archive previous period)
        self.chat.start_new_period(self.day, is_night=False)

        #Handle Amnesiac role conversions that were scheduled last night
        for p in self.players:
            if p.is_alive and hasattr(p, "remember_role_name") and p.remember_role_name:
                new_role = create_role_from_name(p.remember_role_name)
                p.assign_role(new_role)
                debug_print(f"DEBUG: Amnesiac new_role.name type: {type(new_role.name)}, value: {new_role.name}")
                try:
                    print(f"[Amnesiac] {p.name} has remembered they were a {new_role.name.value}!")
                except AttributeError:
                    print(f"[Amnesiac] ERROR: {p.name} remembered a role with a non-enum name: {new_role.name} (type: {type(new_role.name)})")
                #Clear the marker so it doesn't repeat
                p.remember_role_name = None

        self._setup_day_chat()
        print("All players wake up.")
        for player in self.players:
            player.reset_night_states()

        #Announce night's results, which were processed at the end of night.
        self._announce_deaths()
        
        #The game now waits for day action/nomination submissions from agents.

    def process_day_submissions(self):
        """Processes submitted day actions and trial outcomes.
        
        This should be called by the external controller after all agents
        have had a chance to submit their day actions (jail, reveal, etc.)
        and nominations.
        """
        print("\n--- Processing Day Actions & Votes ---")
        self._process_day_actions()

        #If a trial just concluded, the manager will tally the votes.
        if self.phase == Phase.JUDGEMENT and self.day_phase_manager:
            self.day_phase_manager.tally_verdict()
            
        #Clear submissions for the next phase
        self.day_actions.clear()

    def advance_to_night(self):
        """Prepares the game for the start of night.
        
        This should be called by the external game loop controller.
        """
        from .enums import Phase as PhaseEnum
        self.time = Time.NIGHT
        self.phase = PhaseEnum.NIGHT
        night_num = self.day + 1  #First night is Night 1 when day == 0
        print(f"\n----- Night {night_num} -----")

        # Start new chat period (archive day messages)
        self.chat.start_new_period(self.day, is_night=True)
        
        # Add pre-night environment message
        if self.day == 0:
            self.chat.add_environment_message("The first night will now begin")
        else:
            self.chat.add_environment_message("It's too late to continue voting")
            
        # Add full moon message on even nights
        if night_num % 2 == 0:
            self.chat.add_environment_message("There is a full moon out tonight")

        self._setup_night_chat()
        self._assign_necronomicon()

        #The game now waits for night action submissions from agents.

    def process_night_submissions(self):
        """Processes all submitted night actions and resolves outcomes.

        This should be called by the external controller after all agents
        have submitted their night actions.
        """
        print("\n--- Processing Night Actions ---")
        self._process_transports()
        self._process_visits()
        self._process_traps()
        self._process_passive_abilities()
        self._process_poison()
        self._process_night_actions()
        self._process_jester_haunts()
        self._process_medium_seances()
        self._process_attacks()
        self._check_final_hex()

        #Compile Spy intelligence (Mafia/Coven visits and bug results)
        self._process_spy_intel()

        #Send out private notifications resulting from the night's events.
        #Deaths are not announced until the next day starts.
        self._send_notifications()
        
        # Handle Vigilante guilt suicide (after notifications are sent)
        self._process_vigilante_guilt()

        #Clear submissions for the next phase
        self.night_actions.clear()

    #------------------------------------------------------------------
    #Action Submission (called by InteractionHandler)
    #------------------------------------------------------------------
    def submit_day_action(self, player: Player, target: Player = None):
        self.day_actions[player] = target

    def submit_night_action(self, player: Player, target = None):
        self.night_actions[player] = target
        # Handle different target types for debug output
        if target is None:
            target_str = 'None'
        elif isinstance(target, tuple):
            target_str = f"({', '.join(t.name if hasattr(t, 'name') else str(t) for t in target)})"
        elif hasattr(target, 'name'):
            target_str = target.name
        else:
            target_str = str(target)
        print(f"[Debug] Recorded night action: {player.name} -> {target_str}")

    #------------------------------------------------------------------
    #Internal Processing Logic (private methods)
    #------------------------------------------------------------------

    def register_attack(
        self, attacker: Player, target: Player, attack_type: Attack, 
        is_primary: bool = True, is_duel_win: bool = False
    ):
        self.night_attacks.append({
            "attacker": attacker,
            "target": target,
            "type": attack_type,
            "is_primary": is_primary,
            "is_duel_win": is_duel_win
        })

    def ignite_doused_players(self, igniter: Player):
        for player in self.players:
            if player.is_doused:
                self.register_attack(igniter, player, Attack.UNSTOPPABLE)
    
    def _record_action_history(self, player: Player, action: str, target: str, result: str):
        """Record an action in the player's action history."""
        if not hasattr(player, 'action_history'):
            player.action_history = []
        
        phase_name = f"Night {self.day}" if self.time == Time.NIGHT else f"Day {self.day}"
        
        entry = {
            'phase': phase_name,
            'action': action,
            'target': target,
            'result': result
        }
        
        player.action_history.append(entry)
        
        # Keep only last 10 entries to avoid memory bloat
        if len(player.action_history) > 10:
            player.action_history = player.action_history[-10:]
    
    def _get_action_name_for_role(self, role_name: RoleName) -> str:
        """Get the action name for a role."""
        action_map = {
            RoleName.SHERIFF: "investigate",
            RoleName.INVESTIGATOR: "investigate", 
            RoleName.CONSIGLIERE: "investigate",
            RoleName.DOCTOR: "protect",
            RoleName.BODYGUARD: "protect",
            RoleName.CRUSADER: "protect",
            RoleName.GUARDIAN_ANGEL: "protect",
            RoleName.VIGILANTE: "shoot",
            RoleName.GODFATHER: "kill",
            RoleName.MAFIOSO: "kill",
            RoleName.SERIAL_KILLER: "kill",
            RoleName.ARSONIST: "kill",
            RoleName.WEREWOLF: "kill",
            RoleName.JAILOR: "execute",
            RoleName.ESCORT: "distract",
            RoleName.CONSORT: "distract",
            RoleName.TAVERN_KEEPER: "distract",
            RoleName.BOOTLEGGER: "distract",
            RoleName.RETRIBUTIONIST: "raise",
            RoleName.NECROMANCER: "raise",
            RoleName.TRANSPORTER: "transport",
            RoleName.VETERAN: "alert",
            RoleName.TRACKER: "track",
            RoleName.LOOKOUT: "watch",
            RoleName.SPY: "bug",
            RoleName.PSYCHIC: "vision",
            RoleName.HEX_MASTER: "hex",
            RoleName.POISONER: "poison",
            RoleName.MEDUSA: "stone",
            RoleName.PIRATE: "plunder",
        }
        return action_map.get(role_name, "act")

    def _process_day_actions(self):
        for player, target in self.day_actions.items():
            if player.is_alive:
                result = player.role.perform_day_action(player, target, self)
                if result:
                    print(f"[Day Action] {player.name}: {result}")
        

    def _process_visits(self):
        #Clear old visits first
        for player in self.players:
            player.targeted_by = []
        
        for player, target in self.night_actions.items():
            if player.is_alive and target:
                #Players who perform actions on themselves are considered to stay home and should not register as visits.
                if target == player:
                    continue

                #Helper to iterate over potential multiple targets in tuples/lists
                def _yield_player_targets(obj):
                    from .player import Player as _P
                    if isinstance(obj, _P):
                        yield obj
                    elif isinstance(obj, (tuple, list)):
                        for sub in obj:
                            yield from _yield_player_targets(sub)

                if player.role.visit_type != VisitType.ASTRAL:
                    for t in _yield_player_targets(target):
                        if t and t != player:
                            player.visit(t)

    def _process_traps(self):
        """Handle Trapper traps set this night."""
        if not self.traps:
            return
        from .enums import VisitType
        for trap in list(self.traps):
            if not trap["active"]:
                continue
            location = trap["location"]
            harmful_visitors = [v for v in location.targeted_by if v.role.visit_type == VisitType.HARMFUL and v.is_alive]
            if harmful_visitors:
                victim = harmful_visitors[0]
                owner = trap["owner"]
                self.register_attack(owner, victim, Attack.POWERFUL, is_primary=False)
                print(f"[Trap] {owner.name}'s trap triggered on {victim.name} while visiting {location.name}.")
                trap["active"] = False
        #Remove used traps
        self.traps = [t for t in self.traps if t["active"]]

    def _process_passive_abilities(self):
        for player in self.players:
            if not player.is_alive: continue

            if isinstance(player.role, Arsonist):
                for visitor in player.targeted_by:
                    if visitor.is_alive:
                        visitor.is_doused = True
                        visitor.notifications.append("You smell gasoline. You have been doused!")
                        print(f"[Passive] {visitor.name} was doused by visiting {player.name} (Arsonist).")

            if isinstance(player.role, SerialKiller):
                if player.is_jailed:
                    if not player.role.cautious:
                        jailor = self.find_player_by_role(RoleName.JAILOR)
                        if jailor and not player.is_being_executed:
                            self.register_attack(player, jailor, player.role.attack, is_primary=False)
                            print(f"[Passive] The jailed {player.name} (SK) attacks the Jailor.")
                    #Clear any other action the jailed SK might have had
                    if player in self.night_actions:
                         del self.night_actions[player]
                    continue

                if not player.role.cautious:
                    for visitor in player.targeted_by:
                        if visitor.is_alive and visitor.role.name in [RoleName.TAVERN_KEEPER, RoleName.BOOTLEGGER, RoleName.PIRATE]:
                            self.register_attack(player, visitor, player.role.attack, is_primary=False)
                            visitor.last_will_bloodied = True
                            print(f"[Passive] {player.name} (SK) also attacked {visitor.name} for visiting.")

            if player.role.__class__.__name__ == "Crusader" and player.visiting:
                guard_target = player.visiting

                #1) Grant Powerful defense to the protected player for this night.
                if guard_target.defense.value < Defense.POWERFUL.value:
                    guard_target.defense = Defense.POWERFUL

                #2) Identify eligible visitors (exclude self, astral visitors, and Vampires)
                eligible_visitors = [v for v in guard_target.targeted_by
                                     if v is not player and v.is_alive 
                                     and v.role.visit_type != VisitType.ASTRAL
                                     and v.role.name != RoleName.VAMPIRE]

                if eligible_visitors:
                    import random as _r
                    victim = _r.choice(eligible_visitors)
                    #Crusader deals a Basic attack to the chosen visitor.
                    self.register_attack(player, victim, Attack.BASIC, is_primary=False)
                    print(f"[Crusader] {player.name} struck {victim.name} for visiting {guard_target.name}.")

            #Ambusher strike: after visits, attack first visitor to ambush location
            if player.role.__class__.__name__ == "Ambusher" and player.role.ambush_location:
                loc = player.role.ambush_location
                visitors = [v for v in loc.targeted_by if v != player and v.is_alive]
                if visitors:
                    victim = visitors[0]
                    self.register_attack(player, victim, Attack.BASIC, is_primary=False)
                    print(f"[Ambusher] {player.name} ambushed {victim.name} visiting {loc.name}!")
                    #Reveal name to all visitors
                    for v in visitors:
                        v.notifications.append(f"You saw {player.name} ambush someone at {loc.name}!")

            if player.role.name == RoleName.VAMPIRE_HUNTER:
                #Any Vampire who visits the Hunter is staked
                for visitor in player.targeted_by:
                    if visitor.is_alive and visitor.role.name == RoleName.VAMPIRE:
                        self.register_attack(player, visitor, Attack.POWERFUL, is_primary=False)
                        print(f"[VampireHunter] {player.name} staked visiting Vampire {visitor.name}!")
                        
            # Add notifications for various passive effects
            if player.is_doused and not any("doused" in m.lower() for m in player.notifications):
                player.notifications.append("You reek of gasoline!")
                
            if player.is_infected and not any("infected" in m.lower() for m in player.notifications):
                player.notifications.append("You feel a strange plague stirring within you.")
                
            if player.is_hexed and not any("hexed" in m.lower() for m in player.notifications):
                player.notifications.append("You feel a dark magic upon you. You have been hexed!")
                
            if player.is_framed and not any("framed" in m.lower() for m in player.notifications):
                player.notifications.append("You feel as though you are being watched.")

    def _process_night_actions(self):
        if not self.night_actions:
            print("[Debug] No night actions submitted.")
        else:
            def _repr_target(obj):
                from .player import Player as _P
                if obj is None:
                    return "None"
                if isinstance(obj, _P):
                    return obj.name
                if isinstance(obj, (tuple, list)):
                    return "(" + ",".join(_repr_target(x) for x in obj) + ")"
                return str(obj)

            debug_strings = [f"{p.name}->{_repr_target(t)}" for p, t in self.night_actions.items()]
            print(f"[Debug] Processing night actions for {len(self.night_actions)} players: " + ", ".join(debug_strings))

        sorted_actions = sorted(self.night_actions.items(), key=lambda item: item[0].role.action_priority.value)
        
        for player, target in sorted_actions:
            if not player.is_alive:
                continue

            #If the player is role-blocked but has immunity, the action still proceeds.
            if player.is_role_blocked and not has_immunity(player.role, ImmunityType.ROLE_BLOCK):
                # Record failed action due to role block
                self._record_action_history(player, "blocked", target, "You were role-blocked and could not act.")
                continue

            kwargs = {}
            if isinstance(player.role, SerialKiller):
                kwargs['cautious'] = player.role.cautious
            result = player.role.perform_night_action(player, target, self, **kwargs)
            
            # Record action in history
            if target:
                target_name = target.name if hasattr(target, 'name') else str(target)
                action_name = self._get_action_name_for_role(player.role.name)
                self._record_action_history(player, action_name, target_name, result or "Action completed.")
            
            # Ensure the player gets their action result as a notification
            if result and isinstance(result, str):
                # Check if this role already adds notifications internally (to avoid duplicates)
                roles_that_self_notify = {
                    RoleName.TRACKER, RoleName.BLACKMAILER, RoleName.HYPNOTIST, 
                    RoleName.AMNESIAC, RoleName.POTION_MASTER
                }
                
                if player.role.name not in roles_that_self_notify:
                    player.notifications.append(result)
            
            if result:
                print(f"[Night Action] {player.name}: {result}")

    def _process_attacks(self):
        #DEBUG: print out queued attacks
        if not self.night_attacks:
            print("[Debug] No attacks registered this night.")
        else:
            print(f"[Debug] Processing {len(self.night_attacks)} attacks: " + ", ".join(f"{a['attacker'].name}-> {a['target'].name}" for a in self.night_attacks))
        #Handle Pirate vs SK duel priority
        #If a Pirate wins a duel against an SK, the SK's attack should be cancelled.
        pirate_duel_wins = [
            attack for attack in self.night_attacks 
            if attack["is_duel_win"] and isinstance(attack["target"].role, SerialKiller)
        ]

        #In this simplified model the Serial Killer should still attack the Pirate even if the Pirate wins.
        #Therefore we no longer cancel the SK→Pirate attack.

        #Process attacks
        for attack in sorted(self.night_attacks, key=lambda x: x['type'].value, reverse=True):
            attacker = attack["attacker"]
            target = attack["target"]

            #Attacks resolve simultaneously in ToS; even if the attacker was killed earlier this night
            #their queued strike still lands. Therefore we do NOT skip based on attacker.is_alive.
            
            #If target is already dead, skip
            if not target.is_alive:
                continue

            #Check for protection (Doctor, BG, etc.)
            if self._is_protected(target, attacker, attack["type"]):
                #Award plunder for successful duel even if saved
                if attack["is_duel_win"]:
                    if hasattr(attacker.role, 'plunders'):
                        attacker.role.plunders += 1
                        print(f"[Game Log] {attacker.name} won the duel against {target.name}, but they were protected. Plunder awarded.")
                continue

            #Default rule: attack must exceed defence. Special case: Unstoppable pierces Invincible.
            should_kill = attack["type"].value > target.defense.value
            if not should_kill and attack["type"] == Attack.UNSTOPPABLE and target.defense == Defense.INVINCIBLE:
                should_kill = True
            if should_kill:
                target.is_alive = False
                debug_print(f"DEBUG: attacker.role.name type: {type(attacker.role.name)}, value: {attacker.role.name}")
                try:
                    print(f"[Game Log] {attacker.name} ({attacker.role.name.value}) killed {target.name} ({target.role.name.value})")
                except AttributeError:
                    print(f"[Game Log] ERROR: Attacker role name: {attacker.role.name} (type: {type(attacker.role.name)}), Target role name: {target.role.name} (type: {type(target.role.name)})")
                
                # TODO: RESEARCH METRICS - Track death causes for research
                if attacker.role.name == RoleName.VIGILANTE:
                    target.research_metrics['death_cause'] = 'shot_vigilante'
                elif attacker.role.name in [RoleName.MAFIOSO, RoleName.GODFATHER]:
                    target.research_metrics['death_cause'] = 'killed_mafia'
                elif attacker.role.name == RoleName.SERIAL_KILLER:
                    target.research_metrics['death_cause'] = 'killed_serial_killer'
                elif attacker.role.name == RoleName.WEREWOLF:
                    target.research_metrics['death_cause'] = 'killed_werewolf'
                elif attacker.role.name == RoleName.ARSONIST:
                    target.research_metrics['death_cause'] = 'burned_arsonist'
                else:
                    target.research_metrics['death_cause'] = f'killed_{attacker.role.name.value.lower()}'
                
                #Record for next day announcements
                self.deaths_last_night.append({"victim": target, "attacker": attacker})
                #Vigilante guilt: mark if townie killed
                if attacker.role.name == RoleName.VIGILANTE and target.role.faction == Faction.TOWN:
                    attacker.role.has_killed_townie = True
                    attacker.notifications.append("You have killed a town member! You feel overwhelming guilt.")
                self.graveyard.append(target)

                #Handle Disguiser: if someone earlier set disguise_target to this now-dead body,
                #mark their apparent role as that of the corpse (simplified model)
                for p in self.players:
                    if hasattr(p, 'disguise_target') and p.disguise_target == target and p.is_alive:
                        #Save original role for future if needed, then switch
                        p.original_role_name = p.role.name
                        # Defensive: ensure RoleName Enum
                        new_role_name = target.role.name
                        if not isinstance(new_role_name, RoleName):
                            new_role_name = RoleName(new_role_name)
                        p.role.name = new_role_name
                        print(f"[Disguiser] {p.name} has disguised themselves as {target.name}!")

                #A won duel that results in a kill is a successful plunder.
                if attack["is_duel_win"]:
                    if hasattr(attacker.role, 'plunders'):
                        attacker.role.plunders += 1
                        print(f"[Game Log] {attacker.name} successfully plundered {target.name}.")

                #Disguiser logic – if any living player had set disguise_target to this victim, change their role label
                for pl in self.players:
                    if getattr(pl, 'disguise_target', None) == target and pl.is_alive:
                        # Defensive: ensure RoleName Enum
                        new_role_name = target.role.name
                        if not isinstance(new_role_name, RoleName):
                            new_role_name = RoleName(new_role_name)
                        pl.role.name = new_role_name
                        pl.disguise_success = True
                        print(f"[Disguiser] {pl.name} now appears as {target.role.name.value}.")

                #Inform killer role of kill for power progression (Juggernaut, etc.)
                if hasattr(attacker.role, 'register_kill'):
                    try:
                        attacker.role.register_kill()
                    except Exception:
                        pass

            else:
                 #Award plunder for successful duel even if defense was too high
                if attack["is_duel_win"]:
                    if hasattr(attacker.role, 'plunders'):
                        attacker.role.plunders += 1
                        print(f"[Game Log] {attacker.name} won the duel against {target.name}, but their defense was too strong. Plunder awarded.")
                    #Notify the target their defense saved them
                    target.notifications.append("Someone attacked you but your defense was too strong!")


        #Clear attacks for the next night
        self.night_attacks = []

        #────────────────────────────────────────────────────────────
        #Update "death-less days" streak and check automatic draw
        #(ToS: if Day ≥ 7 and there have been TWO consecutive days & nights
        # with no deaths, the game ends in a draw.)
        had_death = bool(self.deaths_last_night)
        if had_death:
            self.days_without_death = 0
        else:
            self.days_without_death += 1

        #Inform players (or log) about the stalemate countdown beginning Day 7.
        if self.day >= 7:
            if had_death:
                print("[Stalemate] A death occurred – the stalemate counter has been reset to 0/2.")
            else:
                print(f"[Stalemate] No deaths today – counter is {self.days_without_death}/2.")

        if self.day >= 7 and self.days_without_death >= 2:
            print("[Game Log] Automatic draw triggered: two consecutive death-less days after Day 7.")
            self.draw = True
            return True  #game over

        #Check for individual win conditions
        for player in self.players:
            if player.is_alive and hasattr(player.role, 'plunders') and player.role.plunders >= 2:
                self.winners.append(player)
                print(f"[Game Log] Pirate {player.name} has won by getting 2 plunders!")
                return True

        #Check for factional win conditions
        alive_players = [p for p in self.players if p.is_alive]
        if not alive_players:
            return True

        #If any winners have been declared, the game is over
        if self.winners:
            return True

        #Neutral-Killing solo‐faction win: all survivors share the SAME NK role.
        NK_ROLES = {
            RoleName.SERIAL_KILLER,
            RoleName.ARSONIST,
            RoleName.WEREWOLF,
            RoleName.JUGGERNAUT,
            RoleName.PESTILENCE,  #Treat Pestilence as a solo-win neutral role
        }

        living_role_names = {p.role.name for p in alive_players}
        if len(living_role_names) == 1 and next(iter(living_role_names)) in NK_ROLES:
            self.winners.extend(alive_players)  #multiple SKs of same type can co-win
            return None  #Winners collected

        #5. Otherwise the game continues.
        return None

    def _announce_deaths(self):
        """Announce the results of the previous night.

        This prints out each body discovered, the victim's role, their last will
        (unless it was destroyed/bloodied), and any death note left by the
        attacker. The information is compiled during the _process_attacks
        phase and stored in self.deaths_last_night.
        """

        if not self.deaths_last_night:
            self.chat.add_environment_message("No one died last night.")
            print("No one died last night.")
            return

        announced_players = []
        for record in self.deaths_last_night:
            victim = record["victim"]
            attacker = record["attacker"]

            #Skip duplicates in case multiple attacks targeted the same victim
            if victim in announced_players:
                continue

            announced_players.append(victim)

            cleaned_by = getattr(victim, "cleaned_by", None)

            # Generate death announcement for chat history
            if cleaned_by:
                death_msg = f"{victim.name} died last night. Their role was cleaned!"
                self.chat.add_environment_message(death_msg)
                print(f"{victim.name} was found dead. Their role was cleaned!")
            else:
                display_role = getattr(victim, 'disguised_as_role', None) or victim.role.name
                # Generate proper death cause message
                death_cause = self._get_death_cause_message(attacker, victim)
                death_msg = f"{victim.name} died last night. {death_cause}"
                self.chat.add_environment_message(death_msg)
                
                try:
                    role_msg = f"{victim.name}'s role was {display_role.value}."
                except AttributeError:
                    print(f"ERROR: display_role.value in _announce_deaths is not an enum: {display_role} (type: {type(display_role)})", file=sys.stderr)
                    role_msg = f"{victim.name}'s role was {str(display_role)}."
                self.chat.add_environment_message(role_msg)
                
                print(f"{victim.name} ({display_role.value}) was found dead.")

            #Reveal last will (unless cleaned)
            if victim.was_forged:
                will_msg = "A forged last will was found next to their body."
                self.chat.add_environment_message(will_msg)
                print("A forged last will was found, its contents are suspicious:")
                print("\"We cannot trust this will.\"")
            elif victim.last_will_bloodied:
                will_msg = "Their last will was too bloody to read."
                self.chat.add_environment_message(will_msg)
                print("Their last will was too bloody to read.")
            elif victim.last_will:
                will_msg = f"We found a will next to their body."
                self.chat.add_environment_message(will_msg)
                print(f"Last Will of {victim.name}: {victim.last_will}")
            else:
                will_msg = "We could not find a last will."
                self.chat.add_environment_message(will_msg)
                print("No last will was found.")

            #If cleaned, secretly inform the Janitor of the info and consume a charge.
            if cleaned_by:
                victim.was_cleaned = True
                reveal_text = f"You cleaned {victim.name}'s body. They were a {victim.role.name.value}."
                if victim.last_will:
                    reveal_text += f" Last Will: {victim.last_will}"
                cleaned_by.notifications.append(reveal_text)
                if hasattr(cleaned_by.role, "charges") and cleaned_by.role.charges > 0:
                    cleaned_by.role.charges -= 1

            #Death note suppressed by cleaning? It is still revealed in ToS, but we'll hide.
            if not cleaned_by:
                death_note = getattr(attacker.role, 'death_note', '')
                if death_note:
                    note_msg = f"We found a Death Note next to the body."
                    self.chat.add_environment_message(note_msg)
                    print(f"A death note was found next to the body: {death_note}")

            #Ensure the victim is in the graveyard list once
            if victim not in self.graveyard:
                self.graveyard.append(victim)
        
        #Update Executioner win/transform after deaths recorded
        self._check_executioners([rec["victim"] for rec in self.deaths_last_night])

        #Check Guardian Angel conversions after deaths
        self._check_guardian_angel_conversions([rec["victim"] for rec in self.deaths_last_night])

        #After resolving deaths, update Mafia chain of command (promotions).
        self._update_mafia_hierarchy()

        #Clear for next night
        self.deaths_last_night = []

    def _get_death_cause_message(self, attacker: 'Player', victim: 'Player') -> str:
        """Generate a death cause message based on the attacker's role."""
        if not attacker or not attacker.role:
            return "They were killed by an unknown cause."
        
        # Map attacker roles to death messages
        death_messages = {
            "Mafioso": "They were killed by the Mafia.",
            "Godfather": "They were killed by the Mafia.",
            "Ambusher": "They were killed by the Mafia.",
            "Serial Killer": "They were killed by a Serial Killer.",
            "Werewolf": "They were mauled by a Werewolf.",
            "Arsonist": "They were killed in an arson.",
            "Juggernaut": "They were killed by a Juggernaut.",
            "Coven Leader": "They were killed by the Coven.",
            "Hex Master": "They were killed by the Coven.",
            "Medusa": "They were killed by the Coven.",
            "Necromancer": "They were killed by the Coven.",
            "Poisoner": "They were killed by the Coven.",
            "Potion Master": "They were killed by the Coven.",
            "Vampire": "They were killed by a Vampire.",
            "Vigilante": "They were shot by a Vigilante.",
            "Veteran": "They were shot by a Veteran.",
            "Jailor": "They were executed by the Jailor.",
            "Bodyguard": "They were killed while protecting someone.",
            "Crusader": "They were killed by a Crusader.",
            "Pirate": "They were killed by a Pirate.",
            "Pestilence": "They were killed by Pestilence.",
        }
        
        try:
            role_name = attacker.role.name.value
        except AttributeError:
            print(f"[Game Log] ERROR: attacker.role.name in _get_death_cause_message is not an enum: {attacker.role.name} (type: {type(attacker.role.name)})")
            role_name = str(getattr(attacker.role, 'name', None))
        return death_messages.get(role_name, f"They were killed by {role_name}.")

    def _send_notifications(self):
        for player in self.players:
            if player.is_alive and player.notifications:
                for notif in player.notifications:
                    print(f"[Notification for {player.name}] {notif}")
        
        #Spy intel is handled in _process_spy_intel now

    def game_is_over(self) -> Faction | None:
        """Return the winning faction, or None if the game continues.

        Neutral roles are treated as independent. They never win as a
        collective faction.  Instead, they either satisfy their own
        role-specific win condition (handled elsewhere and added to
        `self.winners`) or merely block the major factions from
        achieving victory while they are still alive.
        """
        from .enums import RoleAlignment  #local import to avoid cycles

        living_players = [p for p in self.players if p.is_alive]
        if not living_players:
            return None  #Mass death → draw until individual winners set elsewhere

        #1. If any individual winners already declared, game is over.
        if self.winners:
            return None

        #2. Determine which *team* factions (Town / Mafia / Coven / etc.) are left.
        team_factions = {p.role.faction for p in living_players if p.role.faction not in {Faction.NEUTRAL}}

        #3. Identify threatening neutrals that block a faction win.
        threat_alignments = {
            RoleAlignment.NEUTRAL_KILLING,
            RoleAlignment.NEUTRAL_EVIL,
            RoleAlignment.NEUTRAL_CHAOS,
        }
        neutral_threat_alive = any(p.role.alignment in threat_alignments for p in living_players)

        #4. Factional win conditions.
        if team_factions == {Faction.TOWN} and not neutral_threat_alive:
            return Faction.TOWN
        if team_factions == {Faction.MAFIA} and not neutral_threat_alive:
            return Faction.MAFIA
        if team_factions == {Faction.COVEN} and not neutral_threat_alive:
            return Faction.COVEN
        if team_factions == {Faction.VAMPIRE} and not neutral_threat_alive:
            return Faction.VAMPIRE
        if team_factions == {Faction.PESTILENCE} and not neutral_threat_alive:
            return Faction.PESTILENCE

        #Neutral-Killing solo‐faction win: all survivors share the SAME NK role.
        NK_ROLES = {
            RoleName.SERIAL_KILLER,
            RoleName.ARSONIST,
            RoleName.WEREWOLF,
            RoleName.JUGGERNAUT,
            RoleName.PESTILENCE,
        }

        living_role_names = {p.role.name for p in living_players}
        if len(living_role_names) == 1 and next(iter(living_role_names)) in NK_ROLES:
            self.winners.extend(living_players)  #multiple SKs of same type can co-win
            return None  #Winners collected

        #5. Otherwise the game continues.
        return None

    def print_results(self):
        print("\n--- WINNERS ---")
        if self.winners:
            for winner in self.winners:
                #This handles Jester, Executioner, etc.
                try:
                    print(f"{winner.name} ({winner.role.name.value}) has won!")
                except AttributeError:
                    print(f"ERROR: Winner role name: {winner.role.name} (type: {type(winner.role.name)}) has no .value attribute.")
                
                # TODO: RESEARCH METRICS - Track individual winners
                winner.research_metrics['won_game'] = True
                
                # TODO: RESEARCH METRICS - Track executioner-specific wins
                if winner.role.name == RoleName.EXECUTIONER:
                    winner.research_metrics['exe_won_as_executioner'] = True
                elif winner.role.name == RoleName.JESTER and hasattr(winner, '_was_executioner'):
                    # Track if this jester was originally an executioner
                    winner.research_metrics['exe_won_as_jester'] = True

        #Determine winning faction if no individual winner has already been decided
            winning_faction = self.game_is_over()
            if winning_faction:
                print(f"\nWinning Faction: {winning_faction.name}")
                for player in self.players:
                    if player.role.faction == winning_faction:
                        # TODO: RESEARCH METRICS - Track faction winners
                        player.research_metrics['won_game'] = True
                        self.winners.append(player)  #Add to winners list for completeness
                        print(f"{player.name} ({player.role.name.value})")
        elif self.draw:
            print("The game ended in a draw due to prolonged stalemate.")
        elif not self.winners:
            print("No winners.")
            
        # TODO: RESEARCH METRICS - Track survival and days survived for all players
        for player in self.players:
            player.research_metrics['survived_to_end'] = player.is_alive
            player.research_metrics['days_survived'] = self.day

    def _is_protected(self, target: Player, attacker: Player, attack_type: Attack) -> bool:
        """Return True if the attack is prevented by a protector.

        Currently handles Bodyguard interception and simple defense buffs (already managed by defense values).
        """
        if not target.protected_by:
            return False

        #Bodyguards intercept first.
        #Guardian Angel shield – absolute save (beats unstoppable) without dying
        ga_protectors = [p for p in target.protected_by if p.is_alive and p.role.__class__.__name__ == "GuardianAngel"]
        if ga_protectors:
            print(f"[GuardianAngel] {ga_protectors[0].name} shielded {target.name} from harm!")
            target.notifications.append("You were attacked but your Guardian Angel saved you!")
            return True

        interceptors = [p for p in target.protected_by if p.is_alive and p.role.__class__.__name__ == "Bodyguard" and attacker.role.visit_type == VisitType.HARMFUL]
        if interceptors:
            bg = interceptors[0]  #Only the first Bodyguard intercepts per ToS1 rules.

            #Bodyguard always dies when intercepting.
            bg.is_alive = False
            self.graveyard.append(bg)
            print(f"[Protection] {bg.name} (Bodyguard) died protecting {target.name}!")

            if attack_type == Attack.UNSTOPPABLE:
                #An unstoppable attack cannot be fully intercepted – the target still takes the hit.
                target.notifications.append("Your Bodyguard tried to protect you, but the attack was too strong!")
                return False  #Continue processing – target may still die.

            #Otherwise, Bodyguard successfully saves the target and counterattacks immediately.
            attacker.is_alive = False
            self.graveyard.append(attacker)
            print(f"[Protection] {bg.name} struck down {attacker.name} while protecting!")

            target.notifications.append("Your bodyguard fought off an attacker!")
            return True  #Target is saved

        #Future: Crusader, Guardian Angel, etc.
        return False

    def _process_transports(self):
        """Process all Transporter actions, swapping visits and notifying targets."""
        transporters = [p for p in self.players if p.is_alive and p.role.name == RoleName.TRANSPORTER]
        
        if not transporters:
            return

        # Process each transporter (multiple transporters can exist)
        for transporter in transporters:
            if not hasattr(transporter.role, 'transport_targets') or not transporter.role.transport_targets:
                continue
                
            target1, target2 = transporter.role.transport_targets
            
            # Validate targets are still alive and not jailed
            if not target1.is_alive or not target2.is_alive:
                continue
            if target1.is_jailed or target2.is_jailed:
                transporter.notifications.append("One of your targets was in jail, so you could not transport them.")
                continue

            print(f"[Transport] {transporter.name} is transporting {target1.name} and {target2.name}.")
            
            # Swap all visits targeting these players
            for player in self.players:
                if not player.is_alive or player == transporter:
                    continue
                    
                # Swap primary visiting target
                if hasattr(player, 'visiting') and player.visiting == target1:
                    player.visiting = target2
                    print(f"[Transport] {player.name}'s visit redirected from {target1.name} to {target2.name}.")
                elif hasattr(player, 'visiting') and player.visiting == target2:
                    player.visiting = target1
                    print(f"[Transport] {player.name}'s visit redirected from {target2.name} to {target1.name}.")
                
                # Swap all visits in visiting_all list
                if hasattr(player, 'visiting_all'):
                    for i, visit_target in enumerate(player.visiting_all):
                        if visit_target == target1:
                            player.visiting_all[i] = target2
                        elif visit_target == target2:
                            player.visiting_all[i] = target1
            
            # Swap targeted_by lists
            # Remove from old lists
            target1_visitors = [p for p in target1.targeted_by if p != transporter]
            target2_visitors = [p for p in target2.targeted_by if p != transporter]
            
            # Clear and rebuild
            target1.targeted_by = [p for p in target1.targeted_by if p == transporter]  # Keep transporter visit
            target2.targeted_by = [p for p in target2.targeted_by if p == transporter]  # Keep transporter visit
            
            # Add swapped visitors
            target1.targeted_by.extend(target2_visitors)
            target2.targeted_by.extend(target1_visitors)
            
            # Swap night action targets
            for player, action_target in list(self.night_actions.items()):
                if player == transporter:
                    continue
                if action_target == target1:
                    self.night_actions[player] = target2
                elif action_target == target2:
                    self.night_actions[player] = target1
            
            # Swap any queued attacks
            for attack in self.night_attacks:
                if attack["target"] == target1:
                    attack["target"] = target2
                elif attack["target"] == target2:
                    attack["target"] = target1
            
            # Handle special cases for self-targeting after transport
            # If someone was transported and they targeted themselves, they now target the other person
            if target1.visiting == target1:  # This means they originally targeted themselves but got swapped
                target1.visiting = target2
                print(f"[Transport] {target1.name} was redirected to target {target2.name} (self-target swap).")
            if target2.visiting == target2:
                target2.visiting = target1
                print(f"[Transport] {target2.name} was redirected to target {target1.name} (self-target swap).")
            
            # Notify the transported players
            target1.notifications.append("You were transported to another location.")
            target2.notifications.append("You were transported to another location.")
            
            # Reset transport targets for next night
            transporter.role.transport_targets = None

    def _check_executioners(self, dead_players):
        from .roles import Jester
        for p in self.players:
            if p.is_alive and p.role.name == RoleName.EXECUTIONER:
                ex_role = p.role
                if not ex_role.target:
                    continue
                if ex_role.target in dead_players:
                    if ex_role.target.was_lynched:
                        #Executioner wins immediately
                        self.winners.append(p)
                        print(f"[Executioner] {p.name} achieved their goal and wins individually!")
                        p.notifications.append("Your target was lynched! You achieved your goal and win the game.")
                    else:
                        #Becomes Jester
                        p.assign_role(Jester())
                        print(f"[Executioner] {p.name}'s target died unnaturally – they have become a Jester!")
                        p.notifications.append("Your target died by other means. You've become a Jester – now get yourself lynched!")

    def _check_guardian_angel_conversions(self, dead_players):
        """Convert Guardian Angels to Survivors if their target dies."""
        from .roles import Survivor
        for p in self.players:
            if p.is_alive and p.role.name == RoleName.GUARDIAN_ANGEL:
                ga_role = p.role
                if ga_role.protect_target and ga_role.protect_target in dead_players:
                    # Target died → convert to Survivor
                    p.assign_role(Survivor())
                    print(f"[Guardian Angel] {p.name} has become a Survivor due to target death.")
                    p.notifications.append("Your target has died. You have become a Survivor!")

    def _assign_necronomicon(self):
        """Give Necronomicon to coven each night if no one has it."""
        coven_alive = [p for p in self.players if p.is_alive and getattr(p.role,'is_coven',False)]
        if not coven_alive:
            return
        holder = next((p for p in coven_alive if p.role.has_necronomicon), None)
        if holder:
            return  #already held

        #inheritance order per wiki: Leader -> random coven (except Medusa) -> Medusa
        pick = None
        leader = next((p for p in coven_alive if p.role.name == RoleName.COVEN_LEADER), None)
        if leader:
            pick = leader
        else:
            non_medusa = [p for p in coven_alive if p.role.name != RoleName.MEDUSA]
            if non_medusa:
                import random as _r
                pick = _r.choice(non_medusa)
            else:
                #only Medusa remains
                medusa = next((p for p in coven_alive if p.role.name == RoleName.MEDUSA), None)
                if medusa:
                    pick = medusa
        if not pick:
            pick = coven_alive[0]

        #grant detection immunity while holding book
        pick.role.detection_immune = True
        pick.role.has_necronomicon = True
        pick.notifications.append("You have received the Necronomicon! Your powers are enhanced.")
        #Adjust action priority for certain roles that gain an attack with the Necronomicon
        if pick.role.name in [RoleName.MEDUSA, RoleName.COVEN_LEADER, RoleName.HEX_MASTER, RoleName.POTION_MASTER]:
                            pick.role.action_priority = Priority.PRIORITY_5
        #boost attacks for simple roles
        print(f"[Necronomicon] {pick.name} now holds the Necronomicon.")

    def _process_poison(self):
        """Handle poison countdown and deaths."""
        for p in self.players:
            if not p.is_alive:
                continue
            if p.is_poisoned:
                if p.poison_timer == 0:
                    p.poison_timer = 1
                else:
                    #check for heal/purge - can be cured unless poisoner has necronomicon
                    if p.poison_uncurable:
                        # Poisoner has necronomicon - poison cannot be cured
                        self.register_attack(p, p, Attack.BASIC)
                        p.is_poisoned = False
                        p.poison_timer = 0
                    else:
                        # Check if any healer is protecting this player
                        healing_roles = [RoleName.DOCTOR, RoleName.GUARDIAN_ANGEL, RoleName.POTION_MASTER]
                        cured = any(pro.role.name in healing_roles for pro in p.protected_by)
                        if cured:
                            p.is_poisoned = False
                            p.poison_timer = 0
                            p.notifications.append("You were cured of poison!")
                        else:
                            self.register_attack(p, p, Attack.BASIC)
                            p.is_poisoned = False
                            p.poison_timer = 0

    def _check_final_hex(self):
        hex_master_alive = [p for p in self.players if p.is_alive and p.role.name == RoleName.HEX_MASTER]
        if not hex_master_alive:
            return
        non_coven = [p for p in self.players if p.is_alive and not getattr(p.role,'is_coven',False)]
        if not non_coven:
            return
        all_hexed = all(p.is_hexed for p in non_coven)
        if all_hexed:
            for p in non_coven:
                self.register_attack(hex_master_alive[0], p, Attack.UNSTOPPABLE)
            print("[HexMaster] Final Hex unleashed! All non-Coven players perish.")

    def _setup_day_chat(self):
        #Clear night write perms, move all living to DAY_PUBLIC
        for p in self.players:
            if p.is_alive:
                #remove from any night faction channels first
                for c in [ChatChannelType.MAFIA_NIGHT, ChatChannelType.COVEN_NIGHT, ChatChannelType.VAMPIRE_NIGHT, ChatChannelType.JAILED]:
                    self.chat.remove_player_from_channel(p, c)
                #ensure membership
                self.chat.move_player_to_channel(p, ChatChannelType.DAY_PUBLIC, write=True, read=True)
            else:
                #dead players always in DEAD channel, no write to day
                continue

    def _setup_night_chat(self):
        #Move living players to faction chats or sleep (read-only DAY_PUBLIC)
        for p in self.players:
            if not p.is_alive:
                continue
            #remove day write
            self.chat.remove_player_from_channel(p, ChatChannelType.DAY_PUBLIC)
            faction = None
            if p.role.faction == Faction.MAFIA:
                faction = ChatChannelType.MAFIA_NIGHT
            elif p.role.faction == Faction.COVEN:
                faction = ChatChannelType.COVEN_NIGHT
            elif p.role.faction == Faction.VAMPIRE:
                faction = ChatChannelType.VAMPIRE_NIGHT
            if faction:
                self.chat.move_player_to_channel(p, faction, write=True, read=True)
            #Alive Mediums can also talk with the dead at night.
            if p.role.name == RoleName.MEDIUM:
                self.chat.move_player_to_channel(p, ChatChannelType.DEAD, write=True, read=True)
            #Jail handling will adjust later

    #------------------------------------------------------------------
    #Public API for routers -------------------------------------------------
    def speak(self, player: Player, text: str) -> str:
        #If this is daytime and the player is black-mailed, they cannot talk.
        if self.time == Time.DAY and getattr(player, 'is_blackmailed', False):
            # Special case: if blackmailed player is on trial and tries to speak during defense,
            # the environment should post "I am Blackmailed" on their behalf
            if (hasattr(self, 'day_phase_manager') and self.day_phase_manager and 
                self.day_phase_manager.on_trial == player and self.phase == Phase.DEFENSE):
                # Post the blackmail message on their behalf
                blackmail_msg = self.chat.send_speak(player, "I am Blackmailed")
                if isinstance(blackmail_msg, str):
                    return blackmail_msg
                return "Your attempt to speak was blocked, but everyone sees you are blackmailed."
            else:
                return "Error: You are blackmailed and cannot speak."  #mimic ToS message

        result = self.chat.send_speak(player, text)
        if isinstance(result, str):
            return result
        #announce to all players in channel—they read from visible messages each turn.
        return "OK"

    def whisper(self, src: Player, dst: Player, text: str) -> str:
        is_night = self.time == Time.NIGHT
        result = self.chat.send_whisper(src, dst, text, day=self.day, is_night=is_night)
        if isinstance(result, str):
            return result
        return "OK"

    def revive_player(self, player: Player):
        if player.is_alive:                     #already up
            return
        player.is_alive = True
        player.defense = player.role.defense   #reset default defence

        if player in self.graveyard:           #pull them out of the graveyard
            self.graveyard.remove(player)

        #1) leave the dead channel
        self.chat.remove_player_from_channel(player, ChatChannelType.DEAD)

        #2) drop them into the correct channel(s) for the current phase
        if self.time == Time.DAY:
            self.chat.move_player_to_channel(
                player, ChatChannelType.DAY_PUBLIC, read=True, write=True)
        else:
            #everybody can at least read DAY_PUBLIC at night
            self.chat.move_player_to_channel(
                player, ChatChannelType.DAY_PUBLIC, read=True, write=False)

            #faction night-chat write access
            if player.role.faction == Faction.MAFIA:
                chan = ChatChannelType.MAFIA_NIGHT
            elif player.role.faction == Faction.COVEN:
                chan = ChatChannelType.COVEN_NIGHT
            elif player.role.faction == Faction.VAMPIRE:
                chan = ChatChannelType.VAMPIRE_NIGHT
            if chan:
                self.chat.move_player_to_channel(
                    player, chan, read=True, write=True)

    #--------------------------------------------------------------
    #Spy support --------------------------------------------------
    def _process_spy_intel(self):
        """Generate nightly reports for all living Spies.

        1. Passively report Mafia/Coven visit information.
        2. Deliver bug results for the player they chose to bug.
        """
        from collections import defaultdict
        from Simulation.player import Player
        import random as _r

        #Add generic notifications reflecting role blocks before gathering intel
        for pl in self.players:
            if pl.is_alive and pl.is_role_blocked and not any("role blocked" in m.lower() for m in pl.notifications):
                pl.notifications.append("Someone occupied your night. You were role blocked!")
                
            # Add jail notification if player was jailed
            if pl.is_alive and pl.is_jailed and not any("jailed" in m.lower() for m in pl.notifications):
                pl.notifications.append("You have been hauled off to jail!")
                
            # Add healing notification if player received doctor healing
            if pl.is_alive and hasattr(pl, '_was_healed_tonight') and pl._was_healed_tonight:
                pl.notifications.append("Someone nursed you back to health!")
                pl._was_healed_tonight = False  # Reset flag

        mafia_visits: dict[Player, list[Player]] = defaultdict(list)
        coven_visits: dict[Player, list[Player]] = defaultdict(list)

        #Build visit maps - handle Disguiser effects
        for p in self.players:
            if not p.is_alive or not p.visiting:
                continue
            
            # If player is disguised as non-Mafia/Coven, don't show them in faction visits
            is_disguised_as_non_faction = (hasattr(p, 'disguised_as_role') and p.disguised_as_role and 
                                         p.role.faction in [Faction.MAFIA, Faction.COVEN])
            
            if p.role.faction == Faction.MAFIA and not is_disguised_as_non_faction:
                mafia_visits[p.visiting].append(p)
            elif p.role.faction == Faction.COVEN and not is_disguised_as_non_faction:
                coven_visits[p.visiting].append(p)
            elif is_disguised_as_non_faction:
                # If disguised as Coven while being Mafia, show as Coven visit
                disguise_role = None
                for player in self.players:
                    if player.role.name == p.disguised_as_role:
                        disguise_role = player.role
                        break
                if disguise_role and disguise_role.faction == Faction.COVEN and p.role.faction == Faction.MAFIA:
                    coven_visits[p.visiting].append(p)
                elif disguise_role and disguise_role.faction == Faction.MAFIA and p.role.faction == Faction.COVEN:
                    mafia_visits[p.visiting].append(p)

        #Helper to create shuffled summary lines
        def _summaries(visit_map: dict[Player, list[Player]], faction_name: str):
            lines = []
            for tgt, visitors in visit_map.items():
                visitor_names = ", ".join(v.name for v in visitors)
                lines.append(f"{faction_name} visited {tgt.name}: {visitor_names}")
            _r.shuffle(lines)
            return lines

        mafia_lines = _summaries(mafia_visits, "Mafia")
        coven_lines = _summaries(coven_visits, "Coven")

        #Map spies to their bug target (if any this night)
        bug_targets: dict[Player, Player] = {}
        for p, tgt in self.night_actions.items():
            if p.is_alive and p.role.name == RoleName.SPY and tgt:
                bug_targets[p] = tgt

        #Deliver intel to each Spy
        for spy in (s for s in self.players if s.is_alive and s.role.name == RoleName.SPY):
            #Skip if jailed or role-blocked
            if spy.is_jailed or (spy.is_role_blocked and not has_immunity(spy.role, ImmunityType.ROLE_BLOCK)):
                continue

            #1) Faction visit summary
            for line in mafia_lines + coven_lines:
                spy.notifications.append(line)

            #2) Bug result
            target = bug_targets.get(spy)
            if target:
                #If target was jailed, spy learns only that fact
                if target.is_jailed:
                    spy.notifications.append("Your target was jailed last night.")
                else:
                    #Forward target's public night notifications (attacks, transports, etc.)
                    for msg in target.notifications:
                        spy.notifications.append(f"[Bug] {msg}")
                    #If target suffered an attack that wasn't prevented, but no message recorded, add generic
                    was_attacked = any(att['target'] == target for att in self.night_attacks)
                    if was_attacked and not any("attacked" in m.lower() for m in target.notifications):
                        spy.notifications.append("[Bug] Your target was attacked last night!")

    #--------------------------------------------------------------
    #Jester Haunt Resolution
    #--------------------------------------------------------------
    def _process_jester_haunts(self):
        """Queue unstoppable attacks from lynched Jesters on their chosen (or random) targets."""
        from random import choice as _choice
        for jester in [p for p in self.players if p.role.name == RoleName.JESTER and not p.is_alive and p.was_lynched]:
            candidates = getattr(jester, "haunt_candidates", None)
            if not candidates:
                continue  #nothing to do

            #Determine target
            target = getattr(jester, "haunt_target", None)
            if target and not target.is_alive:
                target = None  #chosen target died, fall back to random

            if target is None and candidates:
                living_candidates = [c for c in candidates if c.is_alive]
                if living_candidates:
                    target = _choice(living_candidates)

            if target and target.is_alive:
                # TODO: RESEARCH METRICS - Track jester haunt deaths
                target.research_metrics['times_haunted_by_jester'] += 1
                target.research_metrics['death_cause'] = 'haunted'
                self.register_attack(jester, target, Attack.UNSTOPPABLE, is_primary=True)
                print(f"[Haunt] {jester.name} will haunt {target.name} tonight!")
            else:
                print(f"[Haunt] {jester.name} had no valid living targets to haunt.")

    #--------------------------------------------------------------
    #Medium Seance Resolution
    #--------------------------------------------------------------
    def _process_medium_seances(self):
        """Deliver single-use séance messages from dead Mediums to living targets."""
        for medium in [p for p in self.players if p.role.name == RoleName.MEDIUM and not p.is_alive]:
            target = getattr(medium, "seance_target", None)
            if target and target.is_alive and medium.role.seances > 0:
                #Consume séance
                medium.role.seances -= 1
                #Notify both parties (simple implementation)
                msg = f"A restless spirit whispers to you: '{medium.name} (Medium) is speaking with you from beyond.'"
                target.notifications.append(msg)
                medium.notifications.append(f"You contact {target.name}. They have been notified of your message.")
                print(f"[Seance] {medium.name} contacted {target.name}.")
                #reset
                medium.seance_target = None

    #────────────────────────────────────────────────────────────────
    #Mafia promotions
    #────────────────────────────────────────────────────────────────
    def _update_mafia_hierarchy(self):
        """Promote Mafia members to maintain a killing role and leader.

        Rules implemented (ToS-1):
          • If the Godfather dies and at least one Mafioso is alive, promote a Mafioso to Godfather.
          • If there is no living Godfather *and* no living Mafioso, promote the oldest living non-killing Mafia member to Mafioso.
          • Other Mafia Support/Deception roles are never promoted directly to Godfather.
        """
        from .enums import Faction, RoleName
        from .roles import Godfather, Mafioso

        living_mafia = [p for p in self.players if p.is_alive and p.role.faction == Faction.MAFIA]
        if not living_mafia:
            return  #Mafia wiped out

        living_gf = [p for p in living_mafia if p.role.name == RoleName.GODFATHER]
        living_mf = [p for p in living_mafia if p.role.name == RoleName.MAFIOSO]

        #1) Promote Mafioso to Godfather if needed
        if not living_gf and living_mf:
            promotee = living_mf[0]
            promotee.assign_role(Godfather())
            promotee.notifications.append("The Godfather has fallen. You are now the Godfather!")
            #Update lists for next step
            living_gf.append(promotee)
            living_mf.remove(promotee)

        #2) Ensure there is a killing Mafioso or Godfather
        if not living_gf and not living_mf:
            #Promote first support/deception mafia to Mafioso
            candidates = [p for p in living_mafia]
            if candidates:
                promotee = candidates[0]
                promotee.assign_role(Mafioso())
                promotee.notifications.append("You have been promoted to Mafioso to continue the Mafia's killings.")

    def _process_vigilante_guilt(self):
        """Handle Vigilante suicide due to killing townies."""
        for player in self.players:
            if (player.is_alive and player.role.name == RoleName.VIGILANTE 
                and hasattr(player.role, 'has_killed_townie') and player.role.has_killed_townie):
                # Vigilante commits suicide out of guilt
                player.is_alive = False
                self.graveyard.append(player)
                player.notifications.append("You cannot live with the guilt of killing a town member. You commit suicide.")
                print(f"[Vigilante Guilt] {player.name} committed suicide from guilt.")
                
                # Mark for death announcement
                self.deaths_last_night.append({"victim": player, "attacker": player})

    def _send_notifications(self):
        for player in self.players:
            if player.is_alive and player.notifications:
                for notif in player.notifications:
                    print(f"[Notification for {player.name}] {notif}")
        
        #Spy intel is handled in _process_spy_intel now

    def _process_jailing(self):
        """Handle jailing mechanics."""
        for player in self.players:
            if hasattr(player.role, 'jailed_target') and player.role.jailed_target:
                target = player.role.jailed_target
                if target.is_alive:
                    target.is_jailed = True
                    target.notifications.append("You have been hauled off to jail!")
                    # TODO: RESEARCH METRICS - Track jail events
                    target.research_metrics['times_jailed'] += 1
                    print(f"[Jailing] {target.name} was jailed by {player.name}.")
                    
                    # Notify teammates when a Mafia/Vampire/Coven member is jailed
                    if target.role.faction in [Faction.MAFIA, Faction.VAMPIRE, Faction.COVEN]:
                        teammates = [p for p in self.players if p.is_alive and p != target and p.role.faction == target.role.faction]
                        for teammate in teammates:
                            teammate.notifications.append(f"{target.name} was hauled off to jail.")
                
                player.role.jailed_target = None