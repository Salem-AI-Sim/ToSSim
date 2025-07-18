from enum import Enum, auto

#Factions
class Faction(Enum):
    TOWN = auto()
    MAFIA = auto()
    COVEN = auto()
    NEUTRAL = auto()
    VAMPIRE = auto()
    PESTILENCE = auto()

#The 12 Official Alignments
class RoleAlignment(Enum):
    #Town
    TOWN_INVESTIGATIVE = auto()
    TOWN_PROTECTIVE = auto()
    TOWN_KILLING = auto()
    TOWN_SUPPORT = auto()
    #Mafia
    MAFIA_DECEPTION = auto()
    MAFIA_KILLING = auto()
    MAFIA_SUPPORT = auto()
    #Neutral
    NEUTRAL_BENIGN = auto()
    NEUTRAL_EVIL = auto()
    NEUTRAL_KILLING = auto()
    NEUTRAL_CHAOS = auto()
    #Coven
    COVEN_EVIL = auto()

#Canon Role Names
class RoleName(Enum):
     #Town Investigative
    INVESTIGATOR = "Investigator"
    LOOKOUT = "Lookout"
    PSYCHIC = "Psychic"
    SHERIFF = "Sheriff"
    SPY = "Spy"
    TRACKER = "Tracker"
    #Town Protective
    BODYGUARD = "Bodyguard"
    CRUSADER = "Crusader"
    DOCTOR = "Doctor"
    TRAPPER = "Trapper"
    #Town Killing
    JAILOR = "Jailor"
    VAMPIRE_HUNTER = "Vampire Hunter"
    VETERAN = "Veteran"
    VIGILANTE = "Vigilante"
    #Town Support
    MAYOR = "Mayor"
    MEDIUM = "Medium"
    RETRIBUTIONIST = "Retributionist"
    TAVERN_KEEPER = "Tavern Keeper" #Formerly Escort
    ESCORT = "Tavern Keeper"
    TRANSPORTER = "Transporter"
    #Mafia Deception
    DISGUISER = "Disguiser"
    FORGER = "Forger"
    FRAMER = "Framer"
    HYPNOTIST = "Hypnotist"
    JANITOR = "Janitor"
    #Mafia Killing
    AMBUSHER = "Ambusher"
    GODFATHER = "Godfather"
    MAFIOSO = "Mafioso"
    #Mafia Support
    BLACKMAILER = "Blackmailer"
    BOOTLEGGER = "Bootlegger" #Formerly Consort
    CONSORT = "Bootlegger"
    CONSIGLIERE = "Consigliere"
    #Neutral Benign
    AMNESIAC = "Amnesiac"
    GUARDIAN_ANGEL = "Guardian Angel"
    SURVIVOR = "Survivor"
    #Neutral Evil
    EXECUTIONER = "Executioner"
    JESTER = "Jester"
    WITCH = "Witch"
    #Neutral Killing
    ARSONIST = "Arsonist"
    JUGGERNAUT = "Juggernaut"
    SERIAL_KILLER = "Serial Killer"
    WEREWOLF = "Werewolf"
    #Neutral Chaos
    PIRATE = "Pirate"
    PESTILENCE = "Pestilence"
    PLAGUEBEARER = "Plaguebearer"
    VAMPIRE = "Vampire"
    #Coven Evil
    COVEN_LEADER = "Coven Leader"
    MEDUSA = "Medusa"
    HEX_MASTER = "Hex Master"
    POISONER = "Poisoner"
    POTION_MASTER = "Potion Master"
    NECROMANCER = "Necromancer"
#Display Names (can be the same as RoleName)
class DisplayName(Enum):
    INVESTIGATOR = "Investigator"
    LOOKOUT = "Lookout"
    PSYCHIC = "Psychic"
    SHERIFF = "Sheriff"
    SPY = "Spy"
    TRACKER = "Tracker"
    BODYGUARD = "Bodyguard"
    CRUSADER = "Crusader"
    DOCTOR = "Doctor"
    TRAPPER = "Trapper"
    JAILOR = "Jailor"
    VAMPIRE_HUNTER = "Vampire Hunter"
    VETERAN = "Veteran"
    VIGILANTE = "Vigilante"
    MAYOR = "Mayor"
    MEDIUM = "Medium"
    RETRIBUTIONIST = "Retributionist"
    TAVERN_KEEPER = "Tavern Keeper"
    TRANSPORTER = "Transporter"
    DISGUISER = "Disguiser"
    FORGER = "Forger"
    FRAMER = "Framer"
    HYPNOTIST = "Hypnotist"
    JANITOR = "Janitor"
    AMBUSHER = "Ambusher"
    GODFATHER = "Godfather"
    MAFIOSO = "Mafioso"
    BLACKMAILER = "Blackmailer"
    BOOTLEGGER = "Bootlegger"
    CONSIGLIERE = "Consigliere"
    AMNESIAC = "Amnesiac"
    GUARDIAN_ANGEL = "Guardian Angel"
    SURVIVOR = "Survivor"
    EXECUTIONER = "Executioner"
    JESTER = "Jester"
    WITCH = "Witch"
    ARSONIST = "Arsonist"
    JUGGERNAUT = "Juggernaut"
    SERIAL_KILLER = "Serial Killer"
    WEREWOLF = "Werewolf"
    PIRATE = "Pirate"
    PESTILENCE = "Pestilence"
    PLAGUEBEARER = "Plaguebearer"
    VAMPIRE = "Vampire"
    COVEN_LEADER = "Coven Leader"
    MEDUSA = "Medusa"
    HEX_MASTER = "Hex Master"
    POISONER = "Poisoner"
    POTION_MASTER = "Potion Master"
    NECROMANCER = "Necromancer"
    
    #Old names for compatibility if needed, but the primary name is updated.
    ESCORT = "Tavern Keeper"
    CONSORT = "Bootlegger"


#Attack and Defense Levels
class Attack(Enum):
    NONE = 0
    BASIC = 1
    POWERFUL = 2
    UNSTOPPABLE = 3

class Defense(Enum):
    NONE = 0
    BASIC = 1
    POWERFUL = 2
    INVINCIBLE = 3

#Visit types for night actions
class VisitType(Enum):
    NON_HARMFUL = 0  #Standard investigative/support visit
    HARMFUL = 1      #Triggers BG/Trap; visible to LO/Tracker
    ASTRAL = 2       #Does not leave home; invisible to LO/Tracker and cannot be intercepted

#Night Action Priority Order - Based on official ToS 1 priority system
class Priority(Enum):
    #Day abilities have higher priority than priority 1
    DAY_ACTION = 0
    
    #PRIORITY 1 (Highest) - Transport, Alert, Haunt, etc.
    PRIORITY_1_HIGHEST = 1
    PRIORITY_1 = 2
    
    #PRIORITY 2 - Role blocking, control
    PRIORITY_2_HIGHEST = 3
    PRIORITY_2 = 4
    
    #PRIORITY 3 - Protection, tracking, deception
    PRIORITY_3 = 5
    
    #PRIORITY 4 - Investigation  
    PRIORITY_4 = 6
    
    #PRIORITY 5 - Killing Actions
    PRIORITY_5 = 7
    
    #PRIORITY 6 - Spy, Amnesiac, conversions
    PRIORITY_6 = 8

#Pirate Duel Enums
class DuelMove(Enum):
    SCIMITAR = "Scimitar"
    RAPIER = "Rapier"
    PISTOL = "Pistol"

class DuelDefense(Enum):
    SIDESTEP = "Sidestep"
    CHAINMAIL = "Chainmail"
    BACKPEDAL = "Backpedal"

#Game Simulation Phases
class Time(Enum):
    DAY = auto()
    NIGHT = auto()

class Phase(Enum):
    # --- Refined agent-facing phases (used by MatchRunner FSM) ---
    DISCUSSION = auto()   # open chat, no nominations yet
    NOMINATION = auto()   # players cast votes to put someone on trial
    DEFENSE = auto()      # accused player defends themselves  
    JUDGEMENT = auto()    # guilty / innocent / abstain voting
    LAST_WORDS = auto()   # lynched player speaks
    PRE_NIGHT = auto()    # short filler before night
    NIGHT = auto()

#Immunity types
class ImmunityType(Enum):
    ROLE_BLOCK = auto()
    CONTROL = auto()
    DETECTION = auto() 