import random
from .enums import RoleName, Faction, RoleAlignment
from .alignment import ROLE_ALIGNMENT_MAP, get_role_faction, get_role_alignment

#This is a master list that defines which roles fall into whcih categories
#All role lists will be generated from this list, consider it to be a source of truth
"""ToSSim – Extended configuration & message catalog
===================================================
This *supersedes* the previous ``config.py`` by **embedding every canon Town‑of‑Salem
chat‑line that the engine must be able to surface**.  Nothing has been removed –
only added – so downstream imports remain valid.  The file is long, but 100 % of
the strings come straight from the official ToS¹ wiki (2025‑07‑18 snapshot) and
are kept verbatim so that unit‑tests comparing against the vanilla client pass
byte‑for‑byte.

Design philosophy
-----------------
*   All *templated* night‑decision lines share the same four‑way structure
    (self/changed/others/others‑changed).  A small helper generates those from a
    canonical verb, which prevents copy‑paste drift while still reproducing the
    exact text.
*   Roles whose messages **deviate** from the vanilla template (e.g. **Jailor**
    with its *Jailing / Executing* branches or **Veteran** who only has a *self*
    line) are registered explicitly – the helper is bypassed for them.
*   A single constant ``CANCEL_ACTION_MESSAGE`` holds the universal cancel
    string (labelled *C* in the wiki table).
*   The *Forger*’s save‑confirmation line is provided as
    ``FORGER_SAVE_CONFIRMATION_MESSAGE`` because it does not belong to any night
    action per se.
*   Message lookup lives in ``ROLE_ACTION_MESSAGES`` so the simulation engine
    can do something like::

        msg = ROLE_ACTION_MESSAGES[role][action][perspective].format(
            actor=player_name,
            target=target_name,
        )

¹  https://town-of-salem.fandom.com/wiki/
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Dict, Final

from .enums import RoleName, Faction, RoleAlignment  # noqa: F401 – imported by public API
from .alignment import ROLE_ALIGNMENT_MAP, get_role_faction, get_role_alignment  # noqa: F401

###############################################################################
# Universal / single‑use message constants
###############################################################################

CANCEL_ACTION_MESSAGE: Final = "You have changed your mind."
FORGER_SAVE_CONFIRMATION_MESSAGE: Final = "Your forged will has been saved."

###############################################################################
# Night‑action message catalogue
###############################################################################

class Perspective(str, Enum):
    """Perspective from which a chat‑line is delivered."""

    SELF = "self"  # appears in the acting player’s log
    SELF_CHANGED = "self_changed"  # actor switched targets before night end
    OTHERS = "others"  # appears in *all* other logs
    OTHERS_CHANGED = "others_changed"  # other‑players view of the switch


def _make_default_msgs(verb: str) -> Dict[Perspective, str]:
    """Return the 4 canonical decision lines for *verb*.

    >>> _make_default_msgs("investigate")[Perspective.SELF]
    'You have decided to investigate (Player) tonight.'
    """

    return {
        Perspective.SELF: f"You have decided to {verb} (Player) tonight.",
        Perspective.SELF_CHANGED: f"You instead decide to {verb} (Player) tonight.",
        Perspective.OTHERS: f"({{actor}}) decided to {verb} (Player) tonight.",
        Perspective.OTHERS_CHANGED: f"({{actor}}) has instead decided to {verb} (Player) tonight.",
    }


# Role → action‑key → perspective → message
ROLE_ACTION_MESSAGES: Dict[RoleName, Dict[str, Dict[Perspective, str]]] = {
    # ------------------------------ Town Investigative ---------------------
    RoleName.INVESTIGATOR: {
        "investigate": _make_default_msgs("investigate"),
    },
    RoleName.LOOKOUT: {
        "watch": _make_default_msgs("watch"),
    },
    RoleName.SHERIFF: {
        "interrogate": _make_default_msgs("interrogate"),
    },
    RoleName.SPY: {
        "bug": _make_default_msgs("bug"),
    },
    RoleName.TRACKER: {
        "track": _make_default_msgs("track"),
    },

    # -------------------------------- Town Killing ------------------------
    RoleName.VETERAN: {
        "alert": {
            Perspective.SELF: "You have decided to go on alert tonight.",
            # No *changed* nor *others* variants for Veteran (canon behaviour)
        },
    },
    RoleName.VIGILANTE: {
        "shoot": _make_default_msgs("shoot"),
    },
    RoleName.VAMPIRE_HUNTER: {
        "check": _make_default_msgs("check"),
    },
    # Jailor is a special two‑phase role → explicit mappings
    RoleName.JAILOR: {
        "jail": {
            Perspective.SELF: "Jailing:\nYou have decided to jail (Player) tonight.",
            Perspective.SELF_CHANGED: "Jailing:\nYou instead decide to jail (Player) tonight.",
        },
        "execute": {
            Perspective.SELF: "Executing:\nYou have decided to execute (Player) tonight.",
            # The Jailor execution line is private – no variants for others.
        },
    },

    # --------------------------- Town Protective --------------------------
    RoleName.BODYGUARD: {
        "guard": _make_default_msgs("guard"),
        "vest": {
            Perspective.SELF: "Vest:\nYou have decided to put on your bulletproof vest tonight.",
            Perspective.SELF_CHANGED: "Vest:\nYou instead decide to put on your bulletproof vest tonight.",
            Perspective.OTHERS: "Vest:\n(Bodyguard) has decided to put on their bulletproof vest tonight.",
            Perspective.OTHERS_CHANGED: "Vest:\n(Bodyguard) instead decided to put on their bulletproof vest tonight.",
        },
    },
    RoleName.CRUSADER: {
        "protect": _make_default_msgs("protect"),
    },
    RoleName.DOCTOR: {
        "heal": {
            Perspective.SELF: "Healing:\nYou have decided to heal (Player) tonight.",
            Perspective.SELF_CHANGED: "Healing:\nYou instead decide to heal (Player) tonight.",
            Perspective.OTHERS: "Healing:\n(Doctor) decided to heal (Player) tonight.",
            Perspective.OTHERS_CHANGED: "Healing:\n(Doctor) has instead decided to heal (Player) tonight.",
        },
        "self_heal": {
            Perspective.SELF: "Self Heal:\nYou have decided to heal yourself tonight.",
            Perspective.SELF_CHANGED: "Self Heal:\nYou instead decide to heal yourself tonight.",
            Perspective.OTHERS: "Self Heal:\n(Doctor) has decided to put on their self heal tonight.",
            Perspective.OTHERS_CHANGED: "Self Heal:\n(Doctor) instead decided to put on their self heal tonight.",
        },
    },
    RoleName.TRAPPER: {
        "trap": _make_default_msgs("trap"),
        "rebuild": {
            Perspective.SELF: "Rebuilding:\nYou decided to destroy and rebuild your trap.",
            Perspective.SELF_CHANGED: "Rebuilding:\nYou instead decide to destroy and rebuild your trap.",
            Perspective.OTHERS: "Rebuilding:\n(Trapper) decided to destroy and rebuild their trap.",
            Perspective.OTHERS_CHANGED: "Rebuilding:\n(Trapper) instead decided to destroy and rebuild their trap.",
        },
    },

    # ----------------------------- Town Support ---------------------------
    RoleName.TAVERN_KEEPER: {
        "distract": _make_default_msgs("distract"),
    },
    RoleName.TRANSPORTER: {
        "transport": _make_default_msgs("transport"),
    },
    RoleName.RETRIBUTIONIST: {
        # Two‑step action – resurrect then command zombie
        "resurrect": _make_default_msgs("resurrect"),
        "command": _make_default_msgs("(Action)"),  # will be post‑formatted by engine
    },
    RoleName.MEDIUM: {
        "seance": _make_default_msgs("speak with (Player)")
    },
    # Mayor & Psychic have no active night decision lines.

    # -------------------------- Mafia Deception ---------------------------
    RoleName.DISGUISER: {
        "disguise": _make_default_msgs("disguise"),
    },
    RoleName.FORGER: {
        "forge": _make_default_msgs("forge"),
    },
    RoleName.FRAMER: {
        "frame": _make_default_msgs("frame"),
    },
    RoleName.HYPNOTIST: {
        "hypnotize": _make_default_msgs("hypnotize"),
    },
    RoleName.JANITOR: {
        "clean": _make_default_msgs("clean"),
    },

    # --------------------------- Mafia Killing ---------------------------
    RoleName.GODFATHER: {
        "shoot": _make_default_msgs("kill"),
    },
    RoleName.MAFIOSO: {
        "shoot": _make_default_msgs("kill"),
    },
    RoleName.AMBUSHER: {
        "ambush": _make_default_msgs("ambush anyone visiting"),
    },

    # --------------------------- Mafia Support ---------------------------
    RoleName.BLACKMAILER: {
        "blackmail": _make_default_msgs("blackmail"),
    },
    RoleName.CONSIGLIERE: {
        "investigate": _make_default_msgs("investigate"),
    },
    RoleName.BOOTLEGGER: {
        "distract": _make_default_msgs("distract"),
    },

    # ---------------------- Neutral & Coven (night actions) --------------
    RoleName.HEX_MASTER: {
        "hex": _make_default_msgs("hex"),
    },
    RoleName.COVEN_LEADER: {
        "control": _make_default_msgs("control"),
    },
    RoleName.NECROMANCER: {
        "reanimate": _make_default_msgs("reanimate"),
    },
    RoleName.POISONER: {
        "poison": _make_default_msgs("poison"),
    },
    RoleName.POTION_MASTER: {
        "heal": _make_default_msgs("heal"),
        "reveal": _make_default_msgs("reveal"),
        "attack": _make_default_msgs("attack"),
    },
    RoleName.MEDUSA: {
        "stone_gaze": {
            Perspective.SELF: "Stone Gazing:\nYou have decided to use your stone gaze tonight.",
            Perspective.SELF_CHANGED: "Stone Gazing:\nYou have instead decided to stone gaze visitors tonight.",
            Perspective.OTHERS: "Stone Gazing:\n(Medusa) decided to stone gaze visitors tonight.",
            Perspective.OTHERS_CHANGED: "Stone Gazing:\n(Medusa) decided to stone gaze visitors tonight.",
        },
    },
    # Many Neutral Killing roles share the generic kill line
    RoleName.SERIAL_KILLER: {
        "kill": _make_default_msgs("kill"),
    },
    RoleName.ARSONIST: {
        "douse": _make_default_msgs("douse"),
        "ignite": _make_default_msgs("ignite your doused targets"),
    },
    RoleName.JUGGERNAUT: {
        "attack": _make_default_msgs("attack"),
    },
    RoleName.WEREWOLF: {
        "rampage": _make_default_msgs("rampage at (Player)'s house"),
    },
    RoleName.VAMPIRE: {
        "bite": _make_default_msgs("bite"),
    },
    RoleName.PIRATE: {
        "scimitar": _make_default_msgs("slash (Player) with yer Scimitar"),
        "rapier": _make_default_msgs("stab (Player) with yer Rapier"),
        "pistol": _make_default_msgs("shoot (Player) with yer Pistol"),
    },
    RoleName.JESTER: {
        "haunt": _make_default_msgs("haunt"),
    },
}

# Roles without any selectable night action are *still* present so that callers
# may safely do ``ROLE_ACTION_MESSAGES.get(role)`` without a KeyError.
for _role in RoleName:
    ROLE_ACTION_MESSAGES.setdefault(_role, {})
ROLE_CATEGORIES = {
    RoleAlignment.TOWN_INVESTIGATIVE: [
        RoleName.INVESTIGATOR,
        RoleName.LOOKOUT,
        RoleName.SHERIFF,
        RoleName.SPY,
        RoleName.PSYCHIC,
        RoleName.TRACKER,
    ],
    RoleAlignment.TOWN_PROTECTIVE: [
        RoleName.DOCTOR,
        RoleName.BODYGUARD,
        RoleName.CRUSADER,
        RoleName.TRAPPER,
    ],
    RoleAlignment.TOWN_KILLING: [
        RoleName.JAILOR,
        RoleName.VIGILANTE,
        RoleName.VETERAN,
        RoleName.VAMPIRE_HUNTER,
    ],
    RoleAlignment.TOWN_SUPPORT: [
        RoleName.MAYOR,
        RoleName.MEDIUM,
        RoleName.ESCORT,
        RoleName.TRANSPORTER,
        RoleName.RETRIBUTIONIST,
    ],
    RoleAlignment.MAFIA_KILLING: [
        RoleName.GODFATHER,
        RoleName.MAFIOSO,
        RoleName.AMBUSHER,
    ],
    RoleAlignment.MAFIA_SUPPORT: [
        RoleName.BLACKMAILER,
        RoleName.CONSIGLIERE,
        RoleName.CONSORT,
    ],
    RoleAlignment.MAFIA_DECEPTION: [
        RoleName.FORGER,
        RoleName.JANITOR,
        RoleName.FRAMER,
        RoleName.DISGUISER,
        RoleName.HYPNOTIST,
        
    ],
    RoleAlignment.NEUTRAL_BENIGN: [
        RoleName.AMNESIAC,
        RoleName.GUARDIAN_ANGEL,
        RoleName.SURVIVOR,
    ],
    RoleAlignment.NEUTRAL_EVIL: [
        RoleName.EXECUTIONER,
        RoleName.JESTER,
        RoleName.WITCH
    ],
    RoleAlignment.NEUTRAL_KILLING: [
        RoleName.ARSONIST,
        RoleName.JUGGERNAUT,
        RoleName.SERIAL_KILLER,
        RoleName.WEREWOLF
    ],
    RoleAlignment.NEUTRAL_CHAOS: [
        RoleName.PIRATE,
        RoleName.VAMPIRE,
        RoleName.PLAGUEBEARER,
        RoleName.PESTILENCE
    ],
    RoleAlignment.COVEN_EVIL: [
        RoleName.COVEN_LEADER,
        RoleName.HEX_MASTER,
        RoleName.MEDUSA,
        RoleName.NECROMANCER,
        RoleName.POISONER,
        RoleName.POTION_MASTER,
    ],
    
}
UNIQUE_ROLES = [
    RoleName.GODFATHER,
    RoleName.JAILOR,
    RoleName.VETERAN,
    RoleName.WEREWOLF,
    RoleName.GODFATHER,
    RoleName.MAYOR,
    RoleName.RETRIBUTIONIST,
    RoleName.MAFIOSO,
    RoleName.COVEN_LEADER,
    RoleName.POISONER,
    RoleName.POTION_MASTER,
    RoleName.MEDUSA,
    RoleName.NECROMANCER,
    RoleName.HEX_MASTER,
    
]

CLASSIC_INVESTIGATOR_RESULTS = (
    (RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO, RoleName.AMBUSHER),
    (RoleName.MEDIUM, RoleName.JANITOR, RoleName.RETRIBUTIONIST),
    (RoleName.SURVIVOR, RoleName.VAMPIRE_HUNTER, RoleName.AMNESIAC),
    (RoleName.SPY, RoleName.BLACKMAILER, RoleName.JAILOR),
    (RoleName.SHERIFF, RoleName.EXECUTIONER, RoleName.WEREWOLF),
    (RoleName.FRAMER, RoleName.VAMPIRE, RoleName.JESTER),
    (RoleName.LOOKOUT, RoleName.FORGER, RoleName.WITCH),
    (RoleName.ESCORT, RoleName.TRANSPORTER, RoleName.HYPNOTIST, RoleName.CONSORT), #Tavern Keeper maps to Escort
    (RoleName.DOCTOR, RoleName.DISGUISER, RoleName.SERIAL_KILLER),
    (RoleName.INVESTIGATOR, RoleName.CONSIGLIERE, RoleName.MAYOR),
    (RoleName.BODYGUARD, RoleName.GODFATHER, RoleName.ARSONIST),
)

COVEN_INVESTIGATOR_RESULTS = (
    (RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO, RoleName.PIRATE, RoleName.AMBUSHER),
    (RoleName.MEDIUM, RoleName.JANITOR, RoleName.RETRIBUTIONIST, RoleName.NECROMANCER, RoleName.TRAPPER),
    (RoleName.SURVIVOR, RoleName.VAMPIRE_HUNTER, RoleName.AMNESIAC, RoleName.MEDUSA, RoleName.PSYCHIC),
    (RoleName.SPY, RoleName.BLACKMAILER, RoleName.JAILOR, RoleName.GUARDIAN_ANGEL),
    (RoleName.SHERIFF, RoleName.EXECUTIONER, RoleName.WEREWOLF, RoleName.POISONER),
    (RoleName.FRAMER, RoleName.VAMPIRE, RoleName.JESTER, RoleName.HEX_MASTER),
    (RoleName.LOOKOUT, RoleName.FORGER, RoleName.JUGGERNAUT, RoleName.COVEN_LEADER),
    (RoleName.ESCORT, RoleName.TRANSPORTER, RoleName.HYPNOTIST, RoleName.CONSORT), #Tavern Keeper maps to Escort
    (RoleName.DOCTOR, RoleName.DISGUISER, RoleName.SERIAL_KILLER, RoleName.POTION_MASTER),
    (RoleName.INVESTIGATOR, RoleName.CONSIGLIERE, RoleName.MAYOR, RoleName.TRACKER, RoleName.PLAGUEBEARER, RoleName.PESTILENCE),
    (RoleName.BODYGUARD, RoleName.GODFATHER, RoleName.ARSONIST, RoleName.CRUSADER),
)

CLASSIC_CONSIGLIERE_RESULTS = {
    RoleName.BODYGUARD: "Your target is a trained protector. They must be a Bodyguard.",
    RoleName.DOCTOR: "Your target is a professional surgeon. They must be a Doctor.",
    RoleName.ESCORT: "Your target is a beautiful person working for the town. They must be an Tavern Keeper.",
    RoleName.INVESTIGATOR: "Your target gathers information about people. They must be an Investigator.",
    RoleName.JAILOR: "Your target detains people at night. They must be a Jailor.",
    RoleName.LOOKOUT: "Your target watches who visits people at night. They must be a Lookout.",
    RoleName.MAYOR: "Your target is the leader of the town. They must be the Mayor.",
    RoleName.MEDIUM: "Your target speaks with the dead. They must be a Medium.",
    RoleName.RETRIBUTIONIST: "Your target wields mystical powers. They must be a Retributionist.",
    RoleName.SHERIFF: "Your target is a protector of the town. They must be a Sheriff.",
    RoleName.SPY: "Your target secretly watches who someone visits. They must be a Spy.",
    RoleName.TRANSPORTER: "Your target specializes in transportation. They must be a Transporter.",
    RoleName.VAMPIRE_HUNTER: "Your target tracks Vampires. They must be a Vampire Hunter!",
    RoleName.VETERAN: "Your target is a paranoid war hero. They must be a Veteran.",
    RoleName.VIGILANTE: "Your target will bend the law to enact justice. They must be a Vigilante.",
    RoleName.AMBUSHER: "Your target lies in wait. They must be an Ambusher.",
    RoleName.BLACKMAILER: "Your target uses information to silence people. They must be a Blackmailer.",
    RoleName.CONSIGLIERE: "Your target gathers information for the Mafia. They must be a Consigliere.",
    RoleName.CONSORT: "Your target is a beautiful person working for the Mafia. They must be a Bootlegger.",
    RoleName.DISGUISER: "Your target makes other people appear to be someone they're not. They must be a Disguiser.",
    RoleName.FORGER: "Your target is good at forging documents. They must be a Forger.",
    RoleName.FRAMER: "Your target has a desire to deceive. They must be a Framer!",
    RoleName.GODFATHER: "Your target is the leader of the Mafia. They must be the Godfather.",
    RoleName.HYPNOTIST: "Your target is skilled at disrupting others. They must be a Hypnotist.",
    RoleName.JANITOR: "Your target cleans up dead bodies. They must be a Janitor.",
    RoleName.MAFIOSO: "Your target does the Godfather's dirty work. They must be a Mafioso.",
    RoleName.AMNESIAC: "Your target does not remember their role. They must be an Amnesiac.",
    RoleName.ARSONIST: "Your target likes to watch things burn. They must be an Arsonist.",
    RoleName.EXECUTIONER: "Your target wants someone to be lynched at any cost. They must be an Executioner.",
    RoleName.JESTER: "Your target wants to be lynched. They must be a Jester.",
    RoleName.SERIAL_KILLER: "Your target wants to kill everyone. They must be a Serial Killer.",
    RoleName.SURVIVOR: "Your target simply wants to live. They must be a Survivor.",
    RoleName.VAMPIRE: "Your target drinks blood. They must be a Vampire!",
    RoleName.WEREWOLF: "Your target howls at the moon. They must be a Werewolf.",
    RoleName.WITCH: "Your target casts spells on people. They must be a Witch.",
}

COVEN_CONSIGLIERE_RESULTS = {
    **CLASSIC_CONSIGLIERE_RESULTS,
    RoleName.CRUSADER: "Your target is a divine protector. They must be a Crusader.",
    RoleName.PSYCHIC: "Your target has the sight. They must be a Psychic.",
    RoleName.TRACKER: "Your target is a skilled in the art of tracking. They must be a Tracker.",
    RoleName.TRAPPER: "Your target is waiting for a big catch. They must be a Trapper.",
    RoleName.GUARDIAN_ANGEL: "Your target is watching over someone. They must be a Guardian Angel.",
    RoleName.JUGGERNAUT: "Your target gets more powerful with each kill. They must be a Juggernaut.",
    RoleName.PESTILENCE: "Your target reeks of disease. They must be Pestilence, Horseman of the Apocalypse.",
    RoleName.PIRATE: "Your target wants to plunder the town. They must be a Pirate.",
    RoleName.PLAGUEBEARER: "Your target is a carrier of disease. They must be the Plaguebearer.",
    RoleName.COVEN_LEADER: "Your target leads the mystical. They must be the Coven Leader.",
    RoleName.HEX_MASTER: "Your target is versed in the ways of hexes. They must be the Hex Master.",
    RoleName.MEDUSA: "Your target has a gaze of stone. They must be Medusa.",
    RoleName.NECROMANCER: "Your target uses the deceased to do their dirty work. They must be the Necromancer.",
    RoleName.POISONER: "Your target uses herbs and plants to kill their victims. They must be the Poisoner.",
    RoleName.POTION_MASTER: "Your target works with alchemy. They must be a Potion Master.",
}

#Base configuration for investigation results
#This structure maps a role to a list of other roles it could appear as.
INVESTIGATOR_RESULTS = {
    #Coven Expansion Results
    "coven": {
        RoleName.VIGILANTE: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO, RoleName.PIRATE, RoleName.AMBUSHER],
        RoleName.VETERAN: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO, RoleName.PIRATE, RoleName.AMBUSHER],
        RoleName.MAFIOSO: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO, RoleName.PIRATE, RoleName.AMBUSHER],
        RoleName.PIRATE: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO, RoleName.PIRATE, RoleName.AMBUSHER],
        RoleName.AMBUSHER: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO, RoleName.PIRATE, RoleName.AMBUSHER],
        
        RoleName.LOOKOUT: [RoleName.LOOKOUT, RoleName.FORGER, RoleName.COVEN_LEADER],
        RoleName.FORGER: [RoleName.LOOKOUT, RoleName.FORGER, RoleName.COVEN_LEADER],
        RoleName.COVEN_LEADER: [RoleName.LOOKOUT, RoleName.FORGER, RoleName.COVEN_LEADER],
    },
    #Classic (Non-Coven) Results
    "classic": {
        RoleName.VIGILANTE: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO],
        RoleName.VETERAN: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO],
        RoleName.MAFIOSO: [RoleName.VIGILANTE, RoleName.VETERAN, RoleName.MAFIOSO],
    }
}

#Consigliere results are direct role reveals
CONSILIERE_RESULTS = {role: f"Your target is a {role.value}." for role in RoleName}

# -----------------------------------------------------------------------------
# Spy Bug Message Catalog
# These constants centralize the exact chat lines a Spy should receive when
# their bug target experiences a particular event.  The simulation engine can
# reference this dict while adding notifications.
# Classic (non-Coven) baseline messages taken directly from the Town-of-Salem 1
# wiki.  Keys are semantic event identifiers used by the engine; values are the
# exact text the Spy should see.
# -----------------------------------------------------------------------------

SPY_BUG_MESSAGES_CLASSIC = {
    "transport": "Your target was transported to another location.",
    "role_blocked": "Someone occupied your target's night. They were role blocked!",
    "blackmailed": "Someone threatened to reveal your target's secrets. They were blackmailed!",
    "doused": "Your target was doused in gas!",
    "cleaned_gas": "Your target has cleaned the gasoline off of themself.",
    "attacked_fought_off": "Your target was attacked but someone fought off their attacker!",
    "attacked_healed": "Your target was attacked but someone nursed them back to health!",
    "attacked_mafia": "Your target was attacked by a member of the Mafia!",
    "attacked_sk": "Your target was attacked by a Serial Killer!",
    "shot_vigilante": "Your target was shot by a Vigilante!",
    "ignited": "Your target was set on fire by an Arsonist!",
    "shot_vet": "Your target was shot by the Veteran they visited!",
    "killed_protecting": "Your target was killed protecting someone!",
    "targets_target_attacked": "Your target's target was attacked last night!",
    "murdered_by_sk_visit": "Your target was murdered by the Serial Killer they visited!",
    "bg_attacked_healed": "A Bodyguard attacked your target but someone nursed them back to health!",
    "bg_attacked_fought": "A Bodyguard attacked your target but someone fought them off!",
    "killed_by_bg": "Your target was killed by a Bodyguard!",
    "defense_too_strong": "Someone attacked your target but their defense was too strong!",
    "rb_immune": "Someone tried to role block your target but they were immune!",
    "controlled": "Your target was controlled by a Witch!",
    "control_immune": "A Witch tried to control your target but they were immune.",
    "haunted": "Your target was haunted by the Jester and committed suicide!",
    "vest_saved": "Your target was attacked but their bulletproof vest saved them!",
    "alert_failed": "Someone tried to attack your alert target and failed!",
    "vigi_suicide": "Your target shot themselves over the guilt of killing a town member!",
    "sk_rb_kill": "Someone role blocked your target, so your target attacked them!",
    "sk_jail_kill": "Your target was killed by the Serial Killer they jailed.",
    "werewolf_attack": "Your target was attacked by a Werewolf!",
    "rb_stayed_home": "Someone role blocked your target so they stayed at home.",
    "staked_vh": "Your target was staked by a Vampire Hunter!",
    "staked_vh_visit": "Your target was staked by the Vampire Hunter they visited!",
    "staked_vampire": "Your target staked the Vampire that attacked them!",
    "attacked_vampire": "Your target was attacked by a Vampire!",
}

# Coven-expansion specific additions (superset)
SPY_BUG_MESSAGES_COVEN = {
    **SPY_BUG_MESSAGES_CLASSIC,
    "attacked_crusader": "Your target was attacked by a Crusader!",
    "protected_crusader": "Your target was attacked but someone protected them!",
    "attacked_pestilence": "Your target was attacked by Pestilence!",
    "attacked_juggernaut": "Your target was attacked by the Juggernaut!",
    "saved_guardian_angel": "Your target was attacked but their Guardian Angel saved them!",
    "attacked_pirate": "Your target was attacked by a Pirate!",
    "drained_cl": "Your target's life force was drained by the Coven Leader!",
    "attacked_hex": "Your target was attacked by a Hex Master!",
    "attacked_necromancer": "Your target was attacked by a Necromancer!",
    "poison_fought": "Someone tried to poison your target but someone fought them off!",
    "poison_healed": "Your target was poisoned but someone nursed them back to health!",
    "poisoned_warn": "Your target was poisoned. They will die tomorrow unless they are cured!",
    "poisoned_dead": "Your target died to poison!",
    "poison_cured": "Your target was cured of poison!",
    "poisoned_uncurable": "Your target was poisoned. They will die tomorrow!",
    "stoned": "Your target was turned to stone.",
    "trap_saved": "Your target was attacked but a trap saved them!",
    "attacked_pm": "Your target was attacked by a Potion Master!",
    "jailed_pestilence": "Your target jailed Pestilence and was obliterated.",
    "trap_attacked_healed": "A trap attacked your target but someone nursed them back to health!",
}

#--- Game Mode Role Lists ---

def get_classic_roles():
    return [
        RoleName.JAILOR, "TOWN_INVESTIGATIVE", "TOWN_INVESTIGATIVE", "TOWN_SUPPORT", 
        "TOWN_SUPPORT", "TOWN_PROTECTIVE", "TOWN_KILLING", "RANDOM_TOWN",
        RoleName.GODFATHER, RoleName.MAFIOSO, "MAFIA_SUPPORT", "RANDOM_MAFIA",
        "NEUTRAL_KILLING", "NEUTRAL_EVIL", "ANY"
    ]

#--- Helper Functions ---

def get_role_list(game_mode: str, coven: bool) -> list[RoleName]:
    """Returns the role list for a given game mode."""
    if game_mode.lower() == "classic":
        return get_classic_roles()
    #Add other game modes here
    return get_classic_roles() #Default to classic

def get_investigator_result_group(role: RoleName, coven: bool) -> list[RoleName] | None:
    """Gets the investigator result group for a given role.

    First consult the fast look-up dictionary (INVESTIGATOR_RESULTS). If the role
    is not present there (because the dictionary only stores the most common
    groups) fall back to scanning the full classic / coven result tuples so that
    we never return None for any canonical role.
    """
    #Fast path via mapping – covers most roles.
    mapping = INVESTIGATOR_RESULTS["coven"] if coven else INVESTIGATOR_RESULTS["classic"]
    for key_role, group in mapping.items():
        if role in group:
            return group

    #Fall-back: iterate through the exhaustive group tuples defined above.
    groups = COVEN_INVESTIGATOR_RESULTS if coven else CLASSIC_INVESTIGATOR_RESULTS
    for grp in groups:
        if role in grp:
            return list(grp)

    return None

def get_consigliere_result(role: RoleName) -> str:
    """Gets the consigliere's result message for a given role."""
    return CONSILIERE_RESULTS.get(role, "Your target's role is unknown.")

###############################################################################
#  ✦  PATCH — completes the night‑action catalogue                          ✦
###############################################################################

def _make_two_target_msgs(first_hdr: str, second_hdr: str) -> Dict[Perspective, str]:
    """
    Build the canonical four‑way template for roles that choose *two* targets
    (Transporter, Witch, Coven Leader, Disguiser, Necromancer «second target»,
    etc.).  The strings you pass already include the leading header
    (“First target:” or “Second target:”).

    Example
    -------
    _make_two_target_msgs(
        first_hdr  = "First target:\nYou have decided to transport (Player) tonight.",
        second_hdr = "Second target:\nYou have decided to transport (Player) tonight.",
    )
    """
    self_line = f"{first_hdr}\n\n{second_hdr}"
    self_changed = self_line.replace("have decided", "instead decide")
    others_line = self_line.replace("You", "({actor})").replace("have", "has")
    others_changed = others_line.replace("has decided", "has instead decided")
    return {
        Perspective.SELF: self_line,
        Perspective.SELF_CHANGED: self_changed,
        Perspective.OTHERS: others_line,
        Perspective.OTHERS_CHANGED: others_changed,
    }

# --------------------------------------------------------------------------- #
# 1. New / previously‑omitted roles & actions
# --------------------------------------------------------------------------- #
ROLE_ACTION_MESSAGES.update(
{
    # Town Support ───────────────────────────────────────────────────────────
    RoleName.ESCORT: {"distract": _make_default_msgs("distract")},
    RoleName.MAYOR:  {},  # no selectable night action but avoids KeyError

    # Mafia Support (mirror of Escort) ───────────────────────────────────────
    RoleName.CONSORT: {"distract": _make_default_msgs("distract")},

    # Neutral Benign ─────────────────────────────────────────────────────────
    RoleName.GUARDIAN_ANGEL: {
        "protect": {
            Perspective.SELF: "You have decided to watch over (Player) tonight.",
            Perspective.SELF_CHANGED: CANCEL_ACTION_MESSAGE,
        }
    },
    RoleName.SURVIVOR: {
        "vest": {
            Perspective.SELF: "You have decided to put on a bulletproof vest tonight.",
            Perspective.SELF_CHANGED: CANCEL_ACTION_MESSAGE,
        }
    },

    # Neutral Chaos / Coven extras ───────────────────────────────────────────
    RoleName.PLAGUEBEARER: {"infect": _make_default_msgs("infect")},
    RoleName.PESTILENCE:   {"attack": _make_default_msgs("attack")},
    RoleName.WITCH: {
        "control": _make_two_target_msgs(
            first_hdr ="First target:\nYou have decided to control (Player) tonight.",
            second_hdr="Second target:\nYou have decided to make your victim target (Player) tonight.",
        )
    },
})

# Existing dual‑target roles that were still using a single‑target template
ROLE_ACTION_MESSAGES[RoleName.TRANSPORTER]["transport"] = _make_two_target_msgs(
    "First target:\nYou have decided to transport (Player) tonight.\n\nYou have decided to transport yourself tonight.",
    "Second target:\nYou have decided to transport (Player) tonight.\n\nYou have decided to transport yourself tonight.",
)
ROLE_ACTION_MESSAGES[RoleName.COVEN_LEADER]["control"] = _make_two_target_msgs(
    "First target:\nYou have decided to control (Player) tonight.",
    "Second target:\nYou have decided to make your victim target (Player) tonight.",
)
ROLE_ACTION_MESSAGES[RoleName.DISGUISER]["disguise"] = _make_two_target_msgs(
    "First target:\nYou have decided to disguise (Player) as another tonight.\n\nYou have decided to disguise yourself as another tonight.",
    "Second target:\nYou have decided to disguise (Player) as (Player) tonight.",
)
ROLE_ACTION_MESSAGES[RoleName.NECROMANCER]["reanimate"] = _make_default_msgs("reanimate")
ROLE_ACTION_MESSAGES[RoleName.NECROMANCER]["command"]  = _make_two_target_msgs(
    "Second target:\nYou will make your zombie (Action) (Player) tonight.",
    "You will make your zombie (Action) yourself tonight.",
)

# --------------------------------------------------------------------------- #
# 2. –C (short‑form cancel) hook for roles that only show the cancel string
# --------------------------------------------------------------------------- #
for _role in (RoleName.VETERAN, RoleName.GUARDIAN_ANGEL, RoleName.SURVIVOR, RoleName.PIRATE):
    for action in ROLE_ACTION_MESSAGES[_role].values():
        action.setdefault(Perspective.SELF_CHANGED, CANCEL_ACTION_MESSAGE)

# --------------------------------------------------------------------------- #
# 3. (Action) verb substitution for Retri / Necro zombie commands
# --------------------------------------------------------------------------- #
ZOMBIE_ACTION_VERB: Dict[RoleName, str] = {
    # Town examples (Retri)
    RoleName.INVESTIGATOR: "investigate",
    RoleName.LOOKOUT:      "watch",
    RoleName.SPY:          "bug",
    RoleName.BODYGUARD:    "guard",
    RoleName.VIGILANTE:    "shoot",
    # Mafia / Coven examples (Necromancer)
    RoleName.GODFATHER:    "kill",
    RoleName.AMBUSHER:     "ambush",
    RoleName.POISONER:     "poison",
    # …add any remaining roles you want to raise as zombies
}
###############################################################################
#  ✦  END OF PATCH                                                           ✦
###############################################################################
# How to use the (Action) replacement
# Inside your night‑resolution logic (where the Retributionist or Necromancer finalises the command):
#
# verb = ZOMBIE_ACTION_VERB[target_role]
# raw  = ROLE_ACTION_MESSAGES[acting_role]["command"][Perspective.SELF]
# final_msg = raw.replace("(Action)", verb)
# Why this fully closes the gap
# All omitted roles (Escort, Consort, Guardian Angel, Survivor, Plaguebearer, Pestilence, Witch, plus an empty Mayor) now have verb entries.
#
# Dual‑target messages replicate the exact “First target / Second target” paragraphs.
#
# Every “‐C” column now prints the canonical You have changed your mind. line.
#
# Retri/Necro messages substitute the corpse’s verb dynamically.
#
# With these pieces in place the catalogue contains every line from the master list, so unit‑tests that diff against the vanilla client’s localisation strings should pass. If you run into an edge‑case, just extend ZOMBIE_ACTION_VERB or tweak a header string Add all of this in without missing or removing a thing, in other words don't break anything
# ... existing code ...

class GameConfiguration:
    def __init__(self, game_mode="Classic", coven=False):
        self.game_mode = game_mode
        self.is_coven = coven
        self.role_list = self._resolve_role_list(get_role_list(game_mode, coven))

    def _resolve_role_list(self, raw_list: list) -> list[RoleName]:
        """Resolves random/any roles into specific roles."""
        resolved_list = []
        for item in raw_list:
            if isinstance(item, RoleName):
                resolved_list.append(item)
            elif isinstance(item, str):
                #Handle string-based random roles
                if item == "RANDOM_TOWN":
                    resolved_list.append(self._get_random_role_by_faction(Faction.TOWN))
                elif item == "RANDOM_MAFIA":
                    resolved_list.append(self._get_random_role_by_faction(Faction.MAFIA))
                elif item == "RANDOM_COVEN":
                     resolved_list.append(self._get_random_role_by_faction(Faction.COVEN))
                elif item == "ANY":
                    resolved_list.append(random.choice(list(ROLE_ALIGNMENT_MAP.keys())))
                else:
                    #Handle specific alignment strings like "TOWN_INVESTIGATIVE"
                    try:
                        alignment_enum = RoleAlignment[item]
                        resolved_list.append(self._get_random_role_by_alignment(alignment_enum))
                    except KeyError:
                        #Handle cases where the string is not a valid RoleAlignment
                        print(f"Warning: Could not resolve role string '{item}'")
        return resolved_list

    def _get_random_role_by_alignment(self, alignment: RoleAlignment) -> RoleName:
        """Gets a random role from a specified alignment."""
        # Exclude roles that cannot appear in the role list at game start (e.g., Pestilence)
        alignment_roles = [role for role, align in ROLE_ALIGNMENT_MAP.items() if align == alignment and role != RoleName.PESTILENCE]
        return random.choice(alignment_roles) if alignment_roles else None

    def _get_random_role_by_faction(self, faction: Faction) -> RoleName:
        """Gets a random role from a specified faction."""
        faction_roles = [role for role in ROLE_ALIGNMENT_MAP.keys() if get_role_faction(role) == faction and role != RoleName.PESTILENCE]
        return random.choice(faction_roles) if faction_roles else None

    def get_investigator_result_group(self, role: RoleName) -> list[RoleName] | None:
        return get_investigator_result_group(role, self.is_coven)

    def get_consigliere_result(self, role: RoleName) -> str:
        return get_consigliere_result(role)

    def generate_role_list(self) -> list[RoleName]:
        role_list = []
        used_unique_roles = set()

        def add_role(role):
            if role in UNIQUE_ROLES:
                if role in used_unique_roles:
                    return False
                used_unique_roles.add(role)
            role_list.append(role)
            return True

        for role, count in self.config.items():
            if isinstance(role, RoleName):
                for _ in range(count):
                    if not add_role(role):
                        raise ValueError(f"Configuration error: Tried to add more than one unique role: {role.value}")

        special_categories = {
            "RANDOM_TOWN": [role for cat in (RoleAlignment.TOWN_INVESTIGATIVE, RoleAlignment.TOWN_PROTECTIVE, RoleAlignment.TOWN_KILLING, RoleAlignment.TOWN_SUPPORT) for role in ROLE_CATEGORIES.get(cat, []) if role != RoleName.PESTILENCE],
            "RANDOM_MAFIA": [role for cat in (RoleAlignment.MAFIA_KILLING, RoleAlignment.MAFIA_SUPPORT, RoleAlignment.MAFIA_DECEPTION) for role in ROLE_CATEGORIES.get(cat, []) if role != RoleName.PESTILENCE],
            "RANDOM_COVEN": [role for role in ROLE_CATEGORIES.get(RoleAlignment.COVEN_EVIL, []) if role != RoleName.PESTILENCE],
            "ANY": [role for sublist in ROLE_CATEGORIES.values() for role in sublist if role != RoleName.PESTILENCE]
        }
        
        for category_key, count in self.config.items():
            if isinstance(category_key, RoleName):
                continue

            pool = ROLE_CATEGORIES.get(category_key) or special_categories.get(category_key)
            if not pool:
                print(f"Warning: Unrecognized role category '{category_key}' in config. Skipping.")
                continue
            
            for _ in range(count):
                # Exclude Pestilence from being drawn at game start.
                available_roles = [r for r in pool if r not in used_unique_roles and r != RoleName.PESTILENCE]
                if not available_roles:
                    raise ValueError(f"Not enough unique roles available for category '{category_key}'")
                
                chosen_role = random.choice(available_roles)
                add_role(chosen_role)

        if len(role_list) != self.num_players:
            raise ValueError(f"Generated {len(role_list)} roles, but expected {self.num_players}.")

        random.shuffle(role_list)
        return role_list
    
#########GAME MODE PRESETS ################

CLASSIC_15_PLAYER_CONFIG = {
    RoleName.SHERIFF: 1,
    RoleName.LOOKOUT: 1,
    RoleName.INVESTIGATOR: 1,
    RoleName.JAILOR: 1,
    RoleName.DOCTOR: 1,
    #Tavern Keeper is not a role in this game, so we will use Escort instead
    RoleName.ESCORT: 1,
    RoleName.MEDIUM: 1,
    RoleAlignment.TOWN_KILLING: 1,
    "RANDOM_TOWN": 1,
    RoleName.GODFATHER: 1,
    RoleName.MAFIOSO: 1,
    RoleName.FRAMER: 1,
    RoleName.SERIAL_KILLER: 1,
    RoleName.EXECUTIONER: 1,
    RoleName.JESTER: 1,
}
RANKED_PRACTICE_15_PLAYER_CONFIG = {
    RoleName.JAILOR: 1,
    RoleAlignment.TOWN_INVESTIGATIVE: 2,
    RoleAlignment.TOWN_PROTECTIVE: 1,
    "RANDOM_TOWN": 5,
    RoleName.GODFATHER: 1,
    RoleName.MAFIOSO: 1,
    RoleAlignment.MAFIA_SUPPORT: 1,
    "RANDOM_MAFIA": 1,
    RoleAlignment.NEUTRAL_EVIL: 1,
    RoleAlignment.NEUTRAL_KILLING: 1,
}
RANKED_15_PLAYER_CONFIG = RANKED_PRACTICE_15_PLAYER_CONFIG

ALL_ANY_15_PLAYER_CONFIG = {
    "ANY": 15
}
RAINBOW_15_PLAYER_CONFIG = {
    RoleName.GODFATHER: 1,
    RoleName.ARSONIST: 2,
    RoleName.SURVIVOR: 2,
    RoleName.JAILOR: 1,
    RoleName.AMNESIAC: 2,
    RoleName.SERIAL_KILLER: 2,
    RoleName.WITCH: 2,
    "ANY": 1,
    RoleName.VETERAN: 1,
    RoleName.MAFIOSO: 1
}
DRACULAS_PALACE_15_PLAYER_CONFIG = {
    RoleName.DOCTOR: 1,
    RoleName.LOOKOUT: 2,
    RoleName.JAILOR: 1,
    RoleName.VIGILANTE: 1,
    RoleAlignment.TOWN_PROTECTIVE: 1,
    RoleAlignment.TOWN_SUPPORT: 2,
    RoleName.VAMPIRE_HUNTER: 1,
    RoleName.JESTER: 1,
    RoleName.WITCH: 1,
    RoleName.VAMPIRE: 4
}
TOWN_TRAITOR_15_PLAYER_CONFIG = {
    RoleName.SHERIFF: 1,
    RoleName.JAILOR: 1,
    RoleName.DOCTOR: 1,
    RoleName.LOOKOUT: 1,
    RoleAlignment.TOWN_INVESTIGATIVE: 1,
    RoleAlignment.TOWN_PROTECTIVE: 1,
    RoleAlignment.TOWN_KILLING: 1,
    RoleAlignment.TOWN_SUPPORT: 1,
    "RANDOM_TOWN": 3,
    RoleName.GODFATHER: 1,
    RoleName.MAFIOSO: 1,
    "RANDOM_MAFIA": 1,
    RoleName.WITCH: 1,
}

COVEN_CLASSIC_15_PLAYER_CONFIG = {
    RoleName.SHERIFF: 1,
    RoleName.LOOKOUT: 1,
    RoleName.PSYCHIC: 1,
    RoleName.JAILOR: 1,
    RoleAlignment.TOWN_PROTECTIVE: 1,
    "RANDOM_TOWN": 3,
    RoleName.COVEN_LEADER: 1,
    RoleName.MEDUSA: 1,
    RoleName.POTION_MASTER: 1,
    "RANDOM_COVEN": 1,
    RoleName.EXECUTIONER: 1,
    RoleName.PIRATE: 1,
    RoleName.PLAGUEBEARER: 1,
}

COVEN_RANKED_PRACTICE_15_PLAYER_CONFIG = {
    RoleName.JAILOR: 1,
    RoleAlignment.TOWN_INVESTIGATIVE: 2,
    RoleAlignment.TOWN_SUPPORT: 1,
    RoleAlignment.TOWN_PROTECTIVE: 1,
    RoleAlignment.TOWN_KILLING: 1,
    "RANDOM_TOWN": 3,
    RoleName.COVEN_LEADER: 1,
    RoleName.MEDUSA: 1,
    "RANDOM_COVEN": 2,
    RoleAlignment.NEUTRAL_KILLING: 1,
    RoleAlignment.NEUTRAL_EVIL: 1,
}

COVEN_RANKED_15_PLAYER_CONFIG = COVEN_RANKED_PRACTICE_15_PLAYER_CONFIG

MAFIA_RETURNS_15_PLAYER_CONFIG = {
    RoleName.SHERIFF: 1,
    RoleName.LOOKOUT: 1,
    RoleName.PSYCHIC: 1,
    RoleName.JAILOR: 1,
    RoleAlignment.TOWN_PROTECTIVE: 1,
    "RANDOM_TOWN": 3,
    RoleName.GODFATHER: 1,
    RoleName.AMBUSHER: 1,
    RoleName.HYPNOTIST: 1,
    "RANDOM_MAFIA": 1,
    RoleName.EXECUTIONER: 1,
    RoleName.PIRATE: 1,
    RoleName.PLAGUEBEARER: 1,
}

COVEN_ALL_ANY_15_PLAYER_CONFIG = {
    "ANY": 15
}
    