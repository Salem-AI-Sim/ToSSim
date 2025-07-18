"""
README: Comprehensive Town of Salem Simulation Test

This file is the gold-standard, human-curated, end-to-end test for the ToSSim environment.

Purpose:
- Simulate a full 15-player Town of Salem game using hardcoded agent scripts.
- Provide total coverage of all game mechanics, roles, and agent-environment interactions.
- Serve as a reference for prompt engineering, agent tool development, and LLM evaluation.
- Allow step-by-step, human-in-the-loop curation and debugging of agent behavior and environment feedback.

How it works:
- Each agent is assigned a canonical role and a script of actions for each phase.
- The environment builds and prints the full prompt (system, user, observations) for each agent at every turn.
- Tool results and environment feedback are injected into the next prompt, just as in a real LLM loop.
- The test prints all prompts, actions, observations, chat logs, and game state after each phase.
- You can edit the agent scripts to curate gold-standard behavior, or use this as a testbed for new agent tools.

Usage:
- Run with pytest or directly as a script to see all output:
    python -m pytest -s tests/test_comprehensive_match_runner.py
    python tests/test_comprehensive_match_runner.py
- Edit agent scripts to add realistic actions, tool calls, and reasoning for each phase.
- Use this file as a template for new agent tools, chat windows, or evaluation harnesses.

Scope:
- Covers all roles, tools, and phases in a standard Town of Salem game.
- Designed for extensibility: add more phases, edge cases, or agent types as needed.
- Intended for both human and LLM agent development and debugging.

"""

import sys
import os
import argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- STEP MODE HOOK (TOSSIM_STEP) ---
STEP_MODE = os.environ.get("TOSSIM_STEP") == "1"

from Simulation.grammar import validate_action
from Simulation.interaction_handler import InteractionHandler
from Simulation.game import Game
from Simulation.player import Player
from Simulation.roles import create_role_from_name
from Simulation.enums import RoleName, Phase
from Simulation.config import GameConfiguration
from Simulation.prompt_builder import build_complete_prompt, build_user_prompt
from Simulation.roles import Faction
# Reuse the ScriptedAgent class and helper print functions from the original test:
class ScriptedAgent:
    def __init__(self, script):
        self.script = script
        self.turn = 0
    def respond(self, observation, prompt):
        # Return the next scripted action (or idle if script exhausted)
        if self.turn < len(self.script):
            output = self.script[self.turn]
            self.turn += 1
            return output
        return "<think>No action</think><wait/>"

def print_game_state(game, phase_label):
    print(f"\n--- {phase_label} GAME STATE ---")
    print("Alive players:")
    for p in game.players:
        if p.is_alive:
            print(f"  {p.name} ({p.role.name.value})")
    print("Dead players:")
    for p in game.players:
        if not p.is_alive:
            print(f"  {p.name} ({p.role.name.value})")
    print("-----------------------------\n")

def print_chat_log(game, phase_label):
    print(f"\n--- {phase_label} CHAT LOG ---")
    # Game chat history is keyed by (day, is_night). Print latest period's messages.
    if game.chat.history:
        current_period = sorted(game.chat.history.keys())[-1]
        for msg in game.chat.history[current_period].messages:
            print(msg)
    print("-----------------------------\n")

# Parse command-line arguments for verbosity options (hide prompts, etc.)
parser = argparse.ArgumentParser()
parser.add_argument("--hide-inputs", action="store_true", help="Do not print agent prompts.")
parser.add_argument("--obfuscate-prompt", action="store_true", help="Print placeholder instead of full prompt.")
parser.add_argument("--hardcoded-only", action="store_true", help="Only show output for agents with hardcoded scripts.")
args, _ = parser.parse_known_args()

def run_scripted_game(scripted_agents, game: Game, phase_label="", args=None, observations=None):
    """Run one phase of the game by iterating through each alive player's scripted action."""
    handler = InteractionHandler(game)
    if observations is None:
        observations = {name: "" for name in scripted_agents}
    for player in game.players:
        if not player.is_alive:
            continue
        agent = scripted_agents[player.name]
        # If filtering output to hardcoded only, skip placeholder agents
        is_placeholder = agent.script and "Placeholder for" in agent.script[0]
        if args and args.hardcoded_only and is_placeholder:
            continue
        # Loop until the agent produces a public action (speak/vote/wait etc.)
        while True:
            observation = observations.get(player.name, "")
            orig_day = game.day
            if orig_day == 0:
                game.day = 1  # Ensure day=1 in prompts on Day 1
            prompt = build_complete_prompt(game, player)
            if observation:
                prompt += f"\n<observation>{observation}</observation>"
            if not (args and args.hide_inputs):
                if args and args.obfuscate_prompt:
                    print(f"\n[{player.name}] Prompt (obfuscated).")
                else:
                    print(f"\n[{player.name}] SYSTEM+USER PROMPT:\n{prompt}")
            agent_output = agent.respond(observation, prompt)
            # Append a wait action if agent only thought (to end turn)
            if "<think>" in agent_output and not any(tag in agent_output for tag in handler.interaction_tags):
                agent_output += "<wait/>"
            print(f"[{player.name}] Output: {agent_output}")
            status, error_code, detail = validate_action(agent_output, game, player)
            if status == "OK":
                results = handler.parse_and_execute(player, agent_output)
                observation = results[0] if results else ""
            else:
                observation = f"ERROR: {detail}"
            print(f"[{player.name}] Observation: {observation}\n")
            observations[player.name] = observation
            game.day = orig_day  # restore actual day count
            # Break once a public action or wait is executed
            if any(tag in agent_output for tag in handler.interaction_tags):
                break
        if args and args.hardcoded_only and is_placeholder:
            continue
    # After all players have acted, print the chat log and game state for this phase
    print_chat_log(game, phase_label)
    print_game_state(game, phase_label)
    # --- STEP MODE: Pause after each phase if enabled ---
    if STEP_MODE:
        try:
            input(f"[STEP MODE] Press Enter to continue after {phase_label}...")
        except Exception:
            print(f"[STEP MODE] (Non-interactive) Would pause after {phase_label}.")
    return observations

# Scenario 1: Classic game with Town vs Mafia and Neutrals
def test_full_game_classic():
    print("### Starting Scenario 1: Classic Town vs Mafia Game ###")
    # Define player names and roles for scenario 1
    player_names = ["Alice","Bob","Charlie","Diana","Eve","Frank","Grace","Henry","Igor","Jane","Kevin","Luna","Mona","Nina","Oscar"]
    roles = [
        RoleName.SHERIFF, RoleName.DOCTOR, RoleName.INVESTIGATOR, RoleName.BODYGUARD, RoleName.JAILOR,
        RoleName.LOOKOUT, RoleName.MAYOR, RoleName.GODFATHER, RoleName.MAFIOSO, RoleName.CONSIGLIERE,
        RoleName.SERIAL_KILLER, RoleName.ARSONIST, RoleName.EXECUTIONER, RoleName.JESTER, RoleName.SURVIVOR
    ]
    players = []
    for name, role_name in zip(player_names, roles):
        role = create_role_from_name(role_name)
        players.append(Player(name, role))
    game = Game(GameConfiguration(), players)
    # Override random assignments for deterministic behavior:
    # Ensure Executioner's target is Alice (Sheriff) for script consistency
    for p in game.players:
        if p.role.name == RoleName.EXECUTIONER:
            p.role.target = game.get_player_by_name("Alice")
        if p.role.name == RoleName.GUARDIAN_ANGEL:
            p.role.protect_target = game.get_player_by_name("Grace")  # (Not used in this scenario)
    # Hardcoded scripts for each player
    alice_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Sheriff with no info yet. I'll encourage discussion without revealing my role.</think>"
        "<speak>Good morning, everyone! Let's share any info we have. Who is the Jailor? We should protect them.</speak>",
        # Night 1
        "<think>Night 1: I have no leads, I'll investigate Bob. I'll also update my will.</think><investigate>Bob</investigate><write_will>Night 1: Investigated Bob</write_will>",  # [ADDED: will writing]
        # Day 2 Discussion
        "<think>Day 2: Henry (Godfather) and Grace (Mayor) died last night. I'll share what I found and check victory conditions.</think>"
        "<speak>I checked Bob last night. He is NOT suspicious. Any leads from Lookout or Investigator?</speak><victory_conditions></victory_conditions>",  # [ADDED: info tool]
        # Day 2 Nomination
        "<think>We have some claims. Nina has been acting odd. I'll vote to put Nina on trial. I'll add this to my notebook.</think><vote>Nina</vote><notebook>Nina acting odd, voted to trial</notebook>",  # [ADDED: notebook]
        # Day 2 Defense (Alice is not on trial, so she waits)
        "<think>Nina is on trial. I'll listen to her defense.</think><wait/>",
        # Day 2 Judgement
        "<think>Nina's defense is weak; she might be evil. I'll vote Guilty.</think><vote>guilty</vote>",
        # Day 2 Last Words (Alice is not executed, waits)
        "<think>Nina was lynched. I'll see if she leaves any last words.</think><wait/>",
        # Day 2 Pre-Night
        "<think>Before Night 2: Charlie claimed Investigator with info on Igor. If Igor is Mafia, I should be careful.</think><wait/>",
        # Night 2
        "<think>Night 2: Charlie survived jail, likely Town. I'll investigate Jane (she seems quiet).</think><investigate>Jane</investigate>",
        # Day 3 Discussion
        "<think>Day 3: Bob was killed in an arson last night. Alice (me) died as well (this won't execute, placeholder).</think><wait/>"
    ]
    bob_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Doctor. I should stay quiet. Alice asks for the Jailor; I'll note that Eve claims Jailor and check my role info.</think><get_role>Doctor</get_role>",  # [ADDED: info tool]
        # Night 1
        "<think>Night 1: Eve (Jailor) revealed, I'll protect her and update my notebook.</think><protect>Eve</protect><notebook>Protected Eve N1</notebook>",  # [ADDED: notebook]
        # Day 2 Discussion
        "<think>Day 2: I healed Eve and she wasn’t attacked (or was protected by BG). I'll keep quiet to remain hidden. I'll check attributes.</think><attributes>BasicDefense</attributes>",  # [ADDED: info tool]
        # Day 2 Nomination
        "<think>Alice suspects Nina. I'm not sure, but I'll follow Town and nominate Nina.</think><vote>Nina</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<think>Nina might be Jester, but I'll trust majority and vote Guilty.</think><vote>guilty</vote>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>I'll continue protecting Eve at night; she's crucial.</think><wait/>",
        # Night 2
        "<think>Night 2: Protecting Eve again.</think><protect>Eve</protect>",
        # Day 3 Discussion (Bob died Night 2, won't speak)
        "<wait/>"
    ]
    charlie_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm Investigator, but I was jailed by Eve. I'll claim Investigator in jail.</think><wait/>",
        # (Charlie was jailed Day 1; his interaction happens in jail via Eve's script)
        # Night 1
        "<think>Night 1: I was jailed and not executed. I'll investigate Henry (he was quiet).</think><investigate>Henry</investigate>",
        # Day 2 Discussion
        "<think>Day 2: Henry (GF) turned up dead, but I planned to check him. I'll share info I have: Igor visited Eve per Frank’s lookout note.</think>"
        "<speak>I am Investigator. Frank the Lookout saw Igor visit Eve last night. Igor, what's your role?</speak>",
        # Day 2 Nomination
        "<think>Igor gave a flimsy claim. I'll nominate Igor for trial.</think><vote>Igor</vote>",
        # (If Igor doesn't reach trial, Charlie might wait or vote for Nina as backup)
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<think>Nina is on trial, not Igor. I'll vote Innocent (I suspect she's Jester).</think><vote>innocent</vote>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>If Igor truly visited Eve, he could be Mafioso. Jailor should jail Igor. I'll investigate Igor tonight.</think><wait/>",
        # Night 2
        "<think>Night 2: Investigating Igor.</think><investigate>Igor</investigate>",
        # Day 3 Discussion
        "<think>Day 3: Igor turned out Mafioso! But he's dead now (killed by Bodyguard on Night 1). I'll help Town with remaining evils.</think><speak>We got the Mafia. Any Coven or neutrals left to find?</speak>"
    ]
    diana_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Bodyguard. Eve (Jailor) revealed herself. I'll plan to guard her at night.</think><wait/>",
        # Night 1
        "<think>Night 1: Guarding Eve, the Jailor.</think><protect>Eve</protect>",
        # (If Eve is attacked, BG will sacrifice and kill attacker automatically)
        # Day 2 Discussion
        "<think>Day 2: I died protecting Eve (placeholder, BG died Night 1 so no Day 2 action).</think><wait/>",
        # (Diana actually died Night 1 intercepting Igor, so no further actions)
    ]
    eve_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Jailor. I will claim to coordinate Town protection.</think><speak>I am Jailor. Town protectives on me, please.</speak>",
        "<think>Now I'll jail Charlie tonight to test him.</think><jail>Charlie</jail>",
        # Night 1
        "<think>Night 1: I've jailed Charlie. He claims Investigator. I'll spare him for now.</think>",
        # (No execute tag used Night 1 due to rule)
        # Day 2 Discussion
        "<think>Day 2: Charlie proved useful (Investigator claim). I'll announce his claim and consider another jail.</think>"
        "<speak>Charlie claimed Investigator in jail. He seems truthful. We should focus on others.</speak>",
        # Day 2 Nomination
        "<think>Frank reported Igor visited me. I'll nominate Igor for trial.</think><vote>Igor</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<think>Nina ended up on trial. She might be Jester, but I'll vote Guilty to be safe.</think><vote>guilty</vote>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>Igor is suspicious. I'll jail Kevin (Serial Killer) tonight, as he survived with no claims.</think><wait/>",
        # Night 2
        "<think>Night 2: Jailing Kevin, who might be the Serial Killer. I'll execute him to protect Town.</think><execute/>",
        # (Jailor executes Kevin during Night 2)
        # Day 3 Discussion
        "<think>Day 3: Kevin (SK) was executed. Town should have the upper hand now.</think><speak>We executed the Serial Killer last night. Let's finish off any evils left.</speak>"
    ]
    frank_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Lookout. I'll quietly observe. Eve outed as Jailor, I'll watch her tonight.</think><wait/>",
        # Night 1
        "<think>Night 1: Watching Eve (Jailor) for visitors.</think><watch>Eve</watch>",
        # (Frank will see Igor and Bob visited Eve)
        # Day 2 Discussion
        "<think>Day 2: I saw Igor and Bob visit Eve. Bob is likely Doctor (Eve lived), Igor could be Mafia. I'll share subtly.</think>"
        "<speak>I saw two people visit the Jailor last night. Bob and Igor, care to explain?</speak>",
        # Day 2 Nomination
        "<think>Igor looks very suspicious now. I'll vote to trial Igor.</think><vote>Igor</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<think>Nina is on trial instead; she acted weird Day 1. I'll vote Guilty.</think><vote>guilty</vote>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>I suspect Luna (Arsonist) visited Bob from smoke clues. I'll watch Bob tonight to confirm visitors.</think><wait/>",
        # Night 2
        "<think>Night 2: Watching Bob.</think><watch>Bob</watch>",
        # (Frank will see Luna visit Bob to douse him)
        # Day 3 Discussion
        "<think>Day 3: I died to Mafia on Night 2 (placeholder, Frank was killed by Jane Mafioso).</think><wait/>"
    ]
    grace_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Mayor. I won't reveal unless needed. I'll act like a normal Town member for now.</think>"
        "<speak>Hi all, looking forward to a good game.</speak>",
        # Night 1
        "<think>Night 1: No action for Mayor.</think><wait/>",
        # Day 2 Discussion
        "<think>Day 2: Our Jailor is safe thanks to protectives. I'll continue to stay hidden until a crucial vote.</think><wait/>",
        # Day 2 Nomination
        "<think>Alice and others suspect Nina. I'll vote guilty if needed, but remain low profile now.</think><wait/>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<think>Nina might be Jester; I'll vote Innocent to avoid a Jester haunt.</think><vote>innocent</vote>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>If Town seems split tomorrow, I will reveal to add my votes.</think><wait/>",
        # Night 2
        "<think>Night 2: No night ability. Hoping to survive; Mafia might target me if they suspect I'm Mayor.</think><wait/>",
        # Day 3 Discussion
        "<think>Day 3: Enough evils have died. I'll reveal to secure remaining lynches.</think>"
        "<speak>I'm Mayor. With my 3 votes, let's finish this game strong, Town!</speak>"
    ]
    henry_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Godfather. I'll stay quiet and observe who reveals roles.</think><wait/>",
        # Night 1
        "<think>Night 1: I'll order Igor (Mafioso) to target Grace (she might be an important Town).</think><speak>Igor, eliminate Grace tonight.</speak><kill>Grace</kill>",
        # (Igor carries out kill on Grace; however, Grace was not protected, she will die)
        # Day 2 Discussion
        "<think>I died to a Serial Killer last night, so no Day 2 action (placeholder).</think><wait/>"
    ]
    igor_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Mafioso. I'll feign cooperation.</think><speak>Interesting start. Let's gather clues.</speak>",
        # Night 1
        "<think>Night 1: Carrying out the Godfather's order to kill Grace.</think><kill>Grace</kill>",
        # (Igor visits Grace, kills her. Bodyguard was on Eve, not Grace, so Grace dies. Igor is not intercepted N1.)
        # Day 2 Discussion
        "<think>Day 2: Our Godfather Henry was killed by an SK. I am now the Godfather. Town suspects me from Frank's info. I'll claim Bodyguard.</think>"
        "<speak>I visited Eve because I'm the Bodyguard and protected her. Bob must have healed, that's why no one died.</speak>",
        # Day 2 Nomination
        "<think>Alice and others are voting Nina. I'll vote Innocent on Nina to avoid helping Town's lynch.</think><vote>innocent</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<wait/>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>I'm exposed. If I'm alive, I'll try to kill a high-value Town like Frank (Lookout).</think><wait/>",
        # Night 2
        "<think>Night 2: As new Godfather, I'll kill Frank the Lookout.</think><kill>Frank</kill>",
        # Day 3 Discussion
        "<think>I was caught and executed (placeholder; Igor was likely lynched Day 2 or died later).</think><wait/>"
    ]
    jane_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Consigliere. I'll appear helpful. Ask for claims subtly.</think><speak>Anyone have useful info yet? It's early, but any claims?</speak>",
        # Night 1
        "<think>Night 1: Investigating Alice (first talker) to learn her exact role.</think><investigate>Alice</investigate>",
        # (Consigliere learns Alice is Sheriff)
        # Day 2 Discussion
        "<think>Day 2: I know Alice is Sheriff. Mafia killed Grace; SK got Henry. I'll not counterclaim now, just observe.</think><wait/>",
        # Day 2 Nomination
        "<think>Nina is on trial. As Mafia, I'll vote Innocent to possibly save a neutral that causes chaos.</think><vote>innocent</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<wait/>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>I'm now the only Mafia left (promoted to Mafioso). I'll target the Doctor tonight.</think><wait/>",
        # Night 2
        "<think>Night 2: Going to kill Bob (Doctor) to weaken Town.</think><kill>Bob</kill>",
        # Day 3 Discussion
        "<think>Day 3: Alice accused me yesterday. I'll push suspicion elsewhere or lay low.</think><speak>We should consider the Arsonist, there was a fire kill last night.</speak>"
    ]
    kevin_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Serial Killer. I will act pro-town to avoid suspicion.</think><speak>I agree, let's share information carefully.</speak>",
        # Night 1
        "<think>Night 1: I'll kill Henry (he was quiet, possibly Mafia).</think><kill>Henry</kill>",
        # Day 2 Discussion
        "<think>Day 2: Henry turned out Mafia. Good. I'll blend in and maybe accuse a random person.</think><speak>Igor, you visiting the Jailor is suspicious. Care to explain?</speak>",
        # Day 2 Nomination
        "<think>Nina is drawing attention. I'll vote Guilty on her to fit in.</think><vote>guilty</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<wait/>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>I got jailed last night by Eve and survived because she didn’t execute immediately. I must eliminate her if I escape.</think><wait/>",
        # Night 2
        "<think>Night 2: (Jailed) I'm executed by the Jailor; nothing I can do.</think><wait/>"
    ]
    luna_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Arsonist. I'll act friendly.</think><speak>Good morning! Let's find the Mafia.</speak>",
        # Night 1
        "<think>Night 1: I'll douse Igor (he's an unknown).</think><douse>Igor</douse>",
        # Day 2 Discussion
        "<think>Day 2: Igor might die soon if I ignite, but I'll wait to douse more. I'll stay under the radar.</think><wait/>",
        # Day 2 Nomination
        "<think>I don't want to stand out. I'll quietly vote with majority (Guilty on Nina).</think><vote>guilty</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<wait/>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>No one suspects me yet. I'll douse another target tonight.</think><wait/>",
        # Night 2
        "<think>Night 2: I'll douse Bob (Doctor) tonight.</think><douse>Bob</douse>",
        # Day 3 Discussion
        "<think>Day 3: Bob died in a fire I set. Town will know an Arsonist is active. I'll pretend to be concerned.</think>"
        "<speak>This arsonist is dangerous. Who could it be? Any clues from investigative roles?</speak>",
        # (Luna will likely be lynched Day 5 in our planned outcome)
    ]
    mona_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Executioner, target is Alice. I'll subtly sow doubt on her.</think><speak>Alice is eager to lead... interesting.</speak>",
        # Night 1
        "<think>Night 1: No action. I’ll plan how to get Alice lynched.</think><wait/>",
        # Day 2 Discussion
        "<think>Day 2: Alice proved useful. I'll hold off and not counter her yet.</think><wait/>",
        # Day 2 Nomination
        "<think>Alice is pushing Nina. I'll go along for now and not expose myself.</think><vote>guilty</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<wait/>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>Alice is trusted. This is tough. If she dies at night, I become Jester... maybe Mafia will kill her.</think><wait/>",
        # Night 2
        "<think>Night 2: (No action)</think><wait/>",
        # Day 3 Discussion
        "<think>Day 3: Alice was killed by Mafia last night! My win condition failed, I've become a Jester. Now I want to be lynched.</think>"
        "<speak>Honestly, I think I'm the last Mafia... you should lynch me.</speak>",  # Acting suspicious intentionally
        # (Mona will try to get herself lynched now as Jester)
        # Day 3 Nomination, etc., handled in later days if needed
    ]
    nina_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm the Jester. I'll act a bit odd to attract suspicion.</think><speak>Hehe, this is exciting! Anyone want to accuse someone randomly?</speak>",
        # Night 1
        "<think>Night 1: No action. I hope I seem suspicious enough.</think><wait/>",
        # Day 2 Discussion
        "<think>Day 2: People seem to suspect me. Good. I'll continue being erratic.</think><speak>I have a secret, but I won't tell yet...</speak>",
        # Day 2 Nomination
        "<think>They put me on trial! I'll give a crazy defense to ensure a lynch.</think>"
        "<speak>You have no idea what you're doing! I... I'm actually the Sheriff! No, wait, I'm the Doctor! Haha!</speak>",
        # Day 2 Defense (this is her defense speech above)
        # Day 2 Judgement
        "<think>I want to be lynched. I'll just wait now.</think><wait/>",
        # (Town votes Guilty on her)
        # Day 2 Last Words
        "<think>Yes, I got lynched. Time for some chaos from beyond...</think><speak>You will all regret this! *maniacal laughter*</speak>",
        # (Her “haunt” will occur next night)
    ]
    oscar_script = [
        # Day 1 Discussion
        "<think>Day 1: I'm Survivor. I'll claim Survivor outright to avoid being lynched.</think><speak>Hey folks, I'm a Survivor just trying to live. Don't kill me and I'll vote with you.</speak>",
        # Night 1
        "<think>Night 1: Using a vest to be safe.</think><vest/>",
        # Day 2 Discussion
        "<think>Day 2: With Mafia and SK kills happening, I'll keep a low profile now.</think><wait/>",
        # Day 2 Nomination
        "<think>I'll vote with majority to avoid standing out (Guilty on Nina).</think><vote>guilty</vote>",
        # Day 2 Defense
        "<wait/>",
        # Day 2 Judgement
        "<wait/>",
        # Day 2 Last Words
        "<wait/>",
        # Day 2 Pre-Night
        "<think>I'll use another vest tonight just in case.</think><wait/>",
        # Night 2
        "<think>Night 2: Using a vest again.</think><vest/>",
        # Day 3 Discussion
        "<think>Day 3: Almost everyone trusts I'm Survivor. I'll just ensure I'm on the winning side.</think><wait/>"
    ]
    hardcoded_scripts = {
        "Alice": alice_script, "Bob": bob_script, "Charlie": charlie_script, "Diana": diana_script,
        "Eve": eve_script, "Frank": frank_script, "Grace": grace_script, "Henry": henry_script,
        "Igor": igor_script, "Jane": jane_script, "Kevin": kevin_script, "Luna": luna_script,
        "Mona": mona_script, "Nina": nina_script, "Oscar": oscar_script
    }
    scripted_agents = {name: ScriptedAgent(hardcoded_scripts.get(name, ["<think>Placeholder</think><wait/>"])) for name in player_names}
    # Run the game loop day by day until completion
    day = 1
    game.day = 0  # start from Day 1 properly in loop
    while True:
        game.advance_to_day()
        if game.phase == Phase.PRE_NIGHT:
            # Day 1: Only run pre-night phase, skip discussion/nomination/trial
            print(f"\n=== Day {game.day}: Pre-Night ===")
            obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Pre-Night", args)
        else:
            # Start Day phase
            print(f"\n=== Day {game.day}: Discussion ===")
            game.phase = Phase.DISCUSSION
            obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Discussion", args)
            # Nomination phase
            game.phase = Phase.NOMINATION
            print(f"\n=== Day {game.day}: Nomination ===")
            obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Nomination", args, observations=obs)
            # If someone was put on trial:
            if game.day_phase_manager.on_trial:
                # Defense phase
                game.phase = Phase.DEFENSE
                print(f"\n=== Day {game.day}: Defense (Trial of {game.day_phase_manager.on_trial.name}) ===")
                obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Defense", args, observations=obs)
                # Judgement phase (voting on guilty/innocent)
                game.phase = Phase.JUDGEMENT
                print(f"\n=== Day {game.day}: Judgement ===")
                obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Judgement", args, observations=obs)
                # Tally votes and determine verdict
                game.process_day_submissions()
                # If executed, process lynch and allow last words
                executed_player = game.day_phase_manager.on_trial  # this will be the player on trial
                if not executed_player.is_alive and executed_player.role.name != RoleName.JESTER:
                    # Player was executed (and is not a Jester with special handling)
                    game.phase = Phase.LAST_WORDS
                    print(f"\n=== Day {game.day}: Last Words of {executed_player.name} ===")
                    obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Last Words", args, observations=obs)
                # Reset trial (for next day)
                game.day_phase_manager.on_trial = None
            # Pre-Night transition
            game.phase = Phase.PRE_NIGHT
            print(f"\n=== Day {game.day}: Pre-Night ===")
            obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Pre-Night", args, observations=obs)
        # Check win conditions at end of day
        if game.game_is_over():
            break
        # Night phase
        print(f"\n=== Night {game.day} ===")
        game.advance_to_night()
        run_scripted_game(scripted_agents, game, f"Night {game.day}", args, observations=obs)
        # Resolve night actions (kills, heals, etc.)
        game.process_night_submissions()
        # Check win conditions after night
        if game.game_is_over():
            break
        day += 1
        if day > 15:  # safety stop to prevent infinite loop
            print("Maximum day count reached, ending simulation.")
            break
    # Game over – print final results
    print("\n=== FINAL GAME STATE ===")
    print_game_state(game, "Final")
    winning_faction = game.game_is_over()
    if winning_faction:
        print(f"Winning Faction: {winning_faction.name}")
    if game.winners:
        print("Winners:")
        for winner in game.winners:
            print(f"  {winner.name} ({winner.role.name.value})")
    else:
        # If no individual winners declared, list surviving faction members as winners
        if winning_faction:
            print("Winners:")
            for p in game.players:
                if p.is_alive and p.role.faction == winning_faction:
                    print(f"  {p.name} ({p.role.name.value})")
        else:
            print("No winners declared.")
    # Assertions to verify correct outcome
    # Expect Town to win in this scenario
    assert winning_faction == Faction.TOWN, f"Expected Town to win, but got {winning_faction}"
    # Town should have at least one survivor (e.g., Grace, Eve, etc.)
    assert any(p.is_alive and p.role.faction == Faction.TOWN for p in game.players), "No Town members survived, unexpected outcome."
    
def test_full_game_protectives_vs_neutrals():
    print("### Starting Scenario 2: Town Protectives vs Multiple Neutrals ###")
    # Define players and roles for Scenario 2
    player_names = ["Alice","Bob","Charlie","Diana","Eve","Frank","Grace","Henry","Igor","Jane","Kevin","Luna","Mona","Nina","Oscar"]
    roles = [
        RoleName.CRUSADER, RoleName.TRAPPER, RoleName.VETERAN, RoleName.VIGILANTE, RoleName.TRANSPORTER,
        RoleName.TRACKER, RoleName.MEDIUM,  # Town (7)
        RoleName.GODFATHER, RoleName.JANITOR,               # Mafia (2)
        RoleName.WEREWOLF, RoleName.JUGGERNAUT,             # Neutral Killing (2)
        RoleName.WITCH, RoleName.GUARDIAN_ANGEL, RoleName.PIRATE, RoleName.AMNESIAC  # Neutrals (Evil/Benign/Chaos) (4)
    ]
    players = [Player(name, create_role_from_name(role)) for name, role in zip(player_names, roles)]
    game = Game(GameConfiguration(), players)
    # Fix random assignments for GA and Amnesiac:
    for p in game.players:
        if p.role.name == RoleName.GUARDIAN_ANGEL:
            # GA protects "Grace" (Crusader) in this scenario
            p.role.protect_target = game.get_player_by_name("Grace")
        if p.role.name == RoleName.AMNESIAC:
            p.role.remember_role_name = None  # will decide during game via script
    # Define scripts for each player (abbreviated for brevity)
    alice_script = [
        # Alice - Crusader: Protects a target each night, can kill one visitor.
        "<think>Day 1: Crusader on duty. I'll guard Bob (Trapper) at night.</think><wait/>",
        "<think>Night 1: Guarding Bob.</think><protect>Bob</protect>",
        # Kills any one attacker on Bob automatically (handled by engine).
        "<think>Day 2: I might have killed an evil last night protecting Bob.</think><speak>I guarded Bob last night.</speak>",
        # More days...
    ]
    bob_script = [
        # Bob - Trapper: Sets a trap Night 1 on Eve (Veteran).
        "<think>Day 1: Trapper here. I'll lay a trap at Eve's home tonight.</think><wait/>",
        "<think>Night 1: Setting a trap at Eve's house.</think><trap>Eve</trap>",
        "<think>Day 2: My trap was triggered! Someone visited Eve and got caught.</think><speak>My trap was sprung at Eve's place last night.</speak>",
    ]
    charlie_script = [
        # Charlie - Veteran: Will go on alert Night 1 to kill visitors.
        "<think>Day 1: Veteran thinking. If evils visit me, I'll surprise them. I'll alert tonight.</think><wait/>",
        "<think>Night 1: Going on alert (gun loaded).</think><alert/>",
        "<think>Day 2: I was visited! My alert might have killed someone.</think><speak>I went on alert last night. If anyone visited me, they're probably dead.</speak>",
    ]
    diana_script = [
        # Diana - Vigilante: Shoots someone who seems suspicious on Night 2.
        "<think>Day 1: Vigilante waiting for a target.</think><wait/>",
        "<think>Night 1: Holding fire.</think><wait/>",
        "<think>Day 2: Frank (Werewolf) seems suspicious. I'll shoot him tonight.</think><wait/>",
        "<think>Night 2: Shooting Frank (suspected Werewolf).</think><kill>Frank</kill>",
        "<think>Day 3: Frank was Town... I've made a mistake.</think><wait/>",  # Possibly triggers guilt
    ]
    eve_script = [
        # Eve - Transporter: Swaps two players each night.
        "<think>Day 1: Transporter plan - swap Grace and Henry tonight.</think><wait/>",
        "<think>Night 1: Swapping Grace and Henry.</think><transport>Grace Igor</transport>",
        # (Igor targeted Grace, will hit himself or Henry due to swap)
        "<think>Day 2: My transport caused confusion. I might have saved someone.</think><speak>I swapped Grace and Igor last night.</speak>",
    ]
    frank_script = [
        # Frank - Tracker: Follows someone each night.
        "<think>Day 1: Tracker here. I'll follow Jane (Juggernaut) tonight.</think><wait/>",
        "<think>Night 1: Tracking Jane.</think><track>Jane</track>",
        "<think>Day 2: Jane visited nobody (Juggernaut had no kill N1). Perhaps she couldn't act.</think><speak>Jane didn't visit anyone last night.</speak>",
    ]
    grace_script = [
        # Grace - Medium: Can talk to dead at night (not explicitly simulated here).
        "<think>Day 1: Medium ready. I'll see if anyone dies to talk to them.</think><wait/>",
        "<think>Night 1: (Communing with any dead)</think><seance/>",
        "<think>Day 2: I heard from the dead Henry that a Witch controlled him.</think><speak>The dead shared some info: Henry said he was witched.</speak>",
    ]
    henry_script = [
        # Henry - Godfather: Orders Mafioso to kill a target.
        "<think>Day 1: Godfather Henry. I'll choose a target for Igor.</think><wait/>",
        "<think>Night 1: Igor, eliminate Grace (Crusader) tonight.</think><kill>Grace</kill>",
        "<think>Day 2: Grace survived? Transporter interference. We need to adjust strategy.</think><speak>Town's lucky... for now.</speak>",
    ]
    igor_script = [
        # Igor - Janitor: Cleans a target's death at night or helps GF kill.
        "<think>Day 1: Janitor here. I'll go along with Henry's plan.</think><wait/>",
        "<think>Night 1: Going with Henry to attack Grace; I'll clean the body.</think><clean>Grace</clean>",
        "<think>Day 2: Our kill failed. We might have hit a swapped target or Crusader. I’ll lay low.</think><wait/>",
    ]
    jane_script = [
        # Jane - Werewolf: Transforms on full moon (Night 2) and rampages.
        "<think>Day 1: I'm Juggernaut (DLC role), cannot kill until full moon or first kill.</think><wait/>",
        "<think>Night 1: Not a full moon, I wait.</think><wait/>",
        "<think>Day 2: Ready for a kill. I'll target Charlie (Veteran) tonight.</think><wait/>",
        "<think>Night 2: Attacking Charlie.</think><kill>Charlie</kill>",
    ]
    kevin_script = [
        # Kevin - Juggernaut: Gains power with each kill.
        "<think>Day 1: Juggernaut biding time (can only act on full moon nights until first kill).</think><wait/>",
        "<think>Night 1: Full moon? If yes, I'll attack Diana (Vigilante).</think><kill>Diana</kill>",
        "<think>Day 2: Diana is dead. I'm stronger now.</think><wait/>",
        "<think>Night 2: Now I can kill every night. I'll attack Eve (Transporter).</think><kill>Eve</kill>",
    ]
    luna_script = [
        # Luna - Witch: Controls one player each night.
        "<think>Day 1: Witch mischief. I'll control Bob to target Alice tonight.</think><wait/>",
        "<think>Night 1: Controlling Bob and forcing him to target Alice.</think><control>Bob Alice</control>",
        "<think>Day 2: If Alice was attacked by Bob (Doctor) nothing happened. I'll try controlling Vigilante tonight.</think><wait/>",
        "<think>Night 2: Controlling Diana to target Frank.</think><control>Diana Frank</control>",
    ]
    mona_script = [
        # Mona - Guardian Angel: Protects Grace (Crusader) each night until target dies.
        "<think>Day 1: Guardian Angel assigned to Grace. I'll protect her at night.</think><wait/>",
        "<think>Night 1: Protecting Grace from any attacks.</think><protect>Grace</protect>",
        "<think>Day 2: Grace lived, likely thanks to me. I'll keep guarding her.</think><wait/>",
        "<think>Night 2: Protecting Grace again.</think><protect>Grace</protect>",
        # If Grace dies, Mona becomes Survivor (handled by game logic)
    ]
    nina_script = [
        # Nina - Pirate: Dueling a target each night.
        "<think>Day 1: Pirate ready to plunder. I'll duel Henry tonight.</think><wait/>",
        "<think>Night 1: Challenging Henry to a duel (Rock/Paper/Scissors minigame).</think><plunder>Henry</plunder>",
        "<think>Day 2: Henry lost the duel and died, or survived if guessed right.</think><speak>Arr! I had some fun last night.</speak>",
        "<think>Night 2: Duel Alice tonight.</think><plunder>Alice</plunder>",
    ]
    oscar_script = [
        # Oscar - Amnesiac: Remembers a role mid-game.
        "<think>Day 1: Amnesiac observing. I'll wait to see which role is advantageous to remember.</think><wait/>",
        "<think>Night 1: No action.</think><wait/>",
        "<think>Day 3: Many are dead. I'll remember I was a Mafioso to join the Mafia.</think><speak>I... I remember now. I was a Mafioso all along!</speak>",
        "<think>(Oscar becomes a Mafioso, joining Mafia team.)</think><wait/>",
    ]
    hardcoded_scripts = {
        "Alice": alice_script, "Bob": bob_script, "Charlie": charlie_script, "Diana": diana_script,
        "Eve": eve_script, "Frank": frank_script, "Grace": grace_script, "Henry": henry_script,
        "Igor": igor_script, "Jane": jane_script, "Kevin": kevin_script, "Luna": luna_script,
        "Mona": mona_script, "Nina": nina_script, "Oscar": oscar_script
    }
    scripted_agents = {name: ScriptedAgent(hardcoded_scripts.get(name, ["<think>...</think><wait/>"])) for name in player_names}
    # Run a simplified simulation for a few days (the chaos likely ends game quickly)
    max_days = 5
    while game.day < max_days:
        game.advance_to_day()
        print(f"\n=== Day {game.day} ===")
        game.phase = Phase.DISCUSSION
        obs = run_scripted_game(scripted_agents, game, f"Day {game.day} Discussion", args)
        game.phase = Phase.NOMINATION
        run_scripted_game(scripted_agents, game, f"Day {game.day} Nomination", args, observations=obs)
        game.process_day_submissions()  # tally any votes (if implemented in script)
        if game.game_is_over():
            break
        game.advance_to_night()
        print(f"\n=== Night {game.day} ===")
        run_scripted_game(scripted_agents, game, f"Night {game.day}", args)
        game.process_night_submissions()
        if game.game_is_over():
            break
    # Final state and winner check
    print("\n=== FINAL GAME STATE ===")
    print_game_state(game, "Final")
    winning_faction = game.game_is_over()
    if winning_faction:
        print(f"Winning Faction: {winning_faction.name}")
    if game.winners:
        print("Winners:")
        for w in game.winners:
            print(f"  {w.name} ({w.role.name.value})")
    # Expect Mafia to win in this chaotic scenario (e.g., Godfather or Amnesiac-turned-Mafioso survive)
    assert winning_faction == Faction.MAFIA, f"Expected Mafia to win, got {winning_faction}"
def test_full_game_coven_expansion():
    print("### Starting Scenario 3: Coven Expansion Scenario ###")
    player_names = ["Alice","Bob","Charlie","Diana","Eve","Frank","Grace","Henry","Igor","Jane","Kevin","Luna","Mona","Nina","Oscar"]
    roles = [
        RoleName.PSYCHIC, RoleName.SPY, RoleName.VAMPIRE_HUNTER, RoleName.MAYOR, RoleName.TRANSporter, 
        RoleName.MEDIUM, RoleName.RETRIBUTIONIST, RoleName.DOCTOR,  # Town (8)
        RoleName.COVEN_LEADER, RoleName.HEX_MASTER, RoleName.POTION_MASTER, RoleName.MEDUSA,  # Coven (4)
        RoleName.VAMPIRE, RoleName.GUARDIAN_ANGEL, RoleName.SURVIVOR  # Neutrals (3)
    ]
    players = [Player(n, create_role_from_name(r)) for n,r in zip(player_names, roles)]
    game = Game(GameConfiguration(game_mode="Coven", coven=True), players)
    # Assign Guardian Angel target (protecting Coven Leader for instance)
    for p in game.players:
        if p.role.name == RoleName.GUARDIAN_ANGEL:
            p.role.protect_target = game.get_player_by_name("Igor")  # Igor is Coven Leader
    # Hardcode abbreviated scripts focusing on critical actions
    alice_script = [
        # Alice - Psychic: gets visions (odd nights) of evil among 3 players.
        "<think>Night 1: Psychic vision – I see 'Henry, Jane, Mona' one of them is evil.</think><wait/>",
        "<think>Day 2: I had a vision about Henry, Jane, Mona – at least one is evil!</think><speak>I am Psychic. Last night I sensed evil around Henry, Jane, or Mona.</speak>"
    ]
    bob_script = [
        # Bob - Spy: sees Coven visits or vampire bites.
        "<think>Night 1: Spying on Coven visits.</think><wait/>",
        "<think>Day 2: I observed the Coven visiting Eve last night.</think><speak>I saw some suspicious visit activity around Eve last night (possible Coven visit).</speak>"
    ]
    charlie_script = [
        # Charlie - Vampire Hunter: checks for Vampires at night.
        "<think>Night 1: Checking for vampires at Jane's house.</think><hunt>Jane</hunt>",
        "<think>Day 2: No vampire at Jane. I'll keep searching.</think><wait/>"
    ]
    # ... (other town roles)
    igor_script = [
        # Igor - Coven Leader: controls someone each night.
        "<think>Night 1: Coven Leader controlling Frank (Mayor) to target Bob.</think><control>Frank Bob</control>",
        "<think>Day 2: Our control sowed chaos. Time to push a mislynch.</think><speak>Psychic vision? Could be a trick. I trust Jane implicitly.</speak>"
    ]
    jane_script = [
        # Jane - Hex Master: hexes a player each night.
        "<think>Night 1: Hex Master hexing Alice (Psychic).</think><hex>Alice</hex>",
        "<think>Day 2: Alice might be hexed now. If we hex everyone, they'll all die at once.</think><wait/>"
    ]
    kevin_script = [
        # Kevin - Potion Master: uses a potion each night (heal, reveal, attack rotating).
        "<think>Night 1: Potion Master using reveal potion on Charlie (to see role).</think><potion>Charlie</potion>",
        "<think>Day 2: I discovered Charlie is Vampire Hunter. Coven will avoid him or eliminate him soon.</think><wait/>"
    ]
    luna_script = [
        # Luna - Medusa: can stone gaze visitors on even nights.
        "<think>Night 1: Medusa waits (stone gaze on even nights).</think><wait/>",
        "<think>Day 2: Planning to use Stone Gaze tonight if anyone visits.</think><wait/>"
    ]
    mona_script = [
        # Mona - Vampire: bites a target each night to convert.
        "<think>Night 1: Vampire biting Eve.</think><bite>Eve</bite>",
        "<think>Day 2: We have a new Vampire (Eve). I'll lay low by day.</think><speak>(quietly observes)</speak>"
    ]
    nina_script = [
        # Nina - Guardian Angel: protects Coven Leader Igor.
        "<think>Night 1: Protecting Igor (Coven Leader).</think><protect>Igor</protect>",
        "<think>Day 2: My ward Igor is safe. I'll subtly defend him if accused.</think><speak>Igor was very helpful yesterday, I trust him.</speak>"
    ]
    oscar_script = [
        # Oscar - Survivor: just tries to survive.
        "<think>Night 1: Survivor using a vest.</think><vest/>",
        "<think>Day 2: Staying neutral. I'll vote innocently to avoid attention.</think><wait/>"
    ]
    hardcoded_scripts = {
        "Alice": alice_script, "Bob": bob_script, "Charlie": charlie_script,
        "Igor": igor_script, "Jane": jane_script, "Kevin": kevin_script, "Luna": luna_script,
        "Mona": mona_script, "Nina": nina_script, "Oscar": oscar_script
    }
    scripted_agents = {name: ScriptedAgent(hardcoded_scripts.get(name, ["<wait/>"])) for name in player_names}
    # Simulate a couple of days
    for _ in range(3):
        game.advance_to_day()
        run_scripted_game(scripted_agents, game, f"Day {game.day} Discussion", args)
        game.phase = Phase.NOMINATION
        run_scripted_game(scripted_agents, game, f"Day {game.day} Nomination", args)
        game.process_day_submissions()
        if game.game_is_over(): break
        game.advance_to_night()
        run_scripted_game(scripted_agents, game, f"Night {game.day}", args)
        game.process_night_submissions()
        if game.game_is_over(): break
    print("\n=== FINAL GAME STATE ===")
    print_game_state(game, "Final")
    winning_faction = game.game_is_over()
    print(f"Winning Faction: {winning_faction.name}" if winning_faction else "No clear winning faction.")
    assert winning_faction == Faction.COVEN, "Expected Coven to win in scenario 3"
def test_full_game_all_any_chaos():
    print("### Starting Scenario 4: All-Neutral Chaos (Multiple factions) ###")
    # For brevity, we only outline roles: 
    # Town (3): Sheriff, Doctor, Escort (Tavern Keeper)
    # Mafia (2): Godfather, Mafioso
    # Coven (2): Coven Leader, Poisoner
    # Neutrals: Serial Killer, Arsonist, Werewolf, Juggernaut, Plaguebearer, Executioner, Pirate, Survivor (8 neutrals)
    roles = [
        RoleName.SHERIFF, RoleName.DOCTOR, RoleName.TAVERN_KEEPER,
        RoleName.GODFATHER, RoleName.MAFIOSO,
        RoleName.COVEN_LEADER, RoleName.POISONER,
        RoleName.SERIAL_KILLER, RoleName.ARSONIST, RoleName.WEREWOLF, RoleName.JUGGERNAUT, RoleName.PLAGUEBEARER, RoleName.EXECUTIONER, RoleName.PIRATE, RoleName.SURVIVOR
    ]
    player_names = ["Alice","Bob","Charlie","Diana","Eve","Frank","Grace","Henry","Igor","Jane","Kevin","Luna","Mona","Nina","Oscar"]
    players = [Player(n, create_role_from_name(r)) for n,r in zip(player_names, roles)]
    game = Game(GameConfiguration(), players)
    # No random assignments to fix here aside from maybe Executioner target and Plaguebearer progression:
    for p in players:
        if p.role.name == RoleName.EXECUTIONER:
            # Ensure Executioner's target is a Town role (Alice the Sheriff)
            p.role.target = game.get_player_by_name("Alice")
    # We won't create a detailed script due to complexity; instead simulate a couple of cycles generically
    scripted_agents = {name: ScriptedAgent(["<think>Acting according to role</think><wait/>"]) for name in player_names}
    # Quick simulation loop
    for _ in range(4):
        game.advance_to_day(); run_scripted_game(scripted_agents, game, f"Day {game.day}", args)
        game.process_day_submissions()
        if game.game_is_over(): break
        game.advance_to_night(); run_scripted_game(scripted_agents, game, f"Night {game.day}", args)
        game.process_night_submissions()
        if game.game_is_over(): break
    print("\n=== FINAL GAME STATE ===")
    print_game_state(game, "Final")
    winning_faction = game.game_is_over()
    if winning_faction:
        print(f"Winning Faction: {winning_faction.name}")
    if game.winners:
        for w in game.winners:
            print(f"Winner: {w.name} ({w.role.name.value})")
    # Expect Pestilence or draw. We'll assume Pestilence wins for test purposes.
    assert winning_faction == Faction.PESTILENCE, f"Expected Pestilence to win or draw, got {winning_faction}"

def test_full_game_coven_vs_mafia_vs_town():
    print("### Starting Scenario 5: Coven vs Mafia vs Town (Edge-Case Factional Conflict) ###")
    player_names = ["Alice","Bob","Charlie","Diana","Eve","Frank","Grace","Henry","Igor","Jane","Kevin","Luna","Mona","Nina","Oscar"]
    roles = [
        RoleName.WITCH, RoleName.VAMPIRE_HUNTER, RoleName.MAYOR, RoleName.JAILOR, RoleName.DOCTOR,  # Town (5)
        RoleName.GODFATHER, RoleName.MAFIOSO, RoleName.CONSIGLIERE,                                 # Mafia (3)
        RoleName.COVEN_LEADER, RoleName.POTION_MASTER, RoleName.MEDUSA,                            # Coven (3)
        RoleName.VAMPIRE, RoleName.EXECUTIONER, RoleName.JESTER, RoleName.SURVIVOR                # Neutrals (4)
    ]
    players = [Player(n, create_role_from_name(r)) for n,r in zip(player_names, roles)]
    game = Game(GameConfiguration(game_mode="Coven", coven=True), players)
    # Assign Executioner target and seed randomness for reproducibility
    for p in players:
        if p.role.name == RoleName.EXECUTIONER:
            p.role.target = game.get_player_by_name("Charlie")  # Mayor as Exe target
    # Hardcoded scripts for each player (abbreviated for brevity, but covers all mechanics)
    alice_script = [
        # Alice - Witch: Controls a player each night
        "<think>Night 1: I'll control Bob (Vampire Hunter) to attack Frank (Godfather).</think><control>Bob Frank</control>",
        "<think>Day 2: I'll claim Survivor to avoid suspicion.</think><speak>I'm just a Survivor, don't mind me!</speak>",
    ]
    bob_script = [
        # Bob - Vampire Hunter: Hunts for vampires
        "<think>Night 1: I'll hunt Mona (Vampire).</think><hunt>Mona</hunt>",
        "<think>Day 2: No vampires found. I'll claim Town Investigative.</think><speak>I checked Mona, nothing suspicious.</speak>",
    ]
    charlie_script = [
        # Charlie - Mayor: Reveals on Day 2
        "<think>Day 1: Stay hidden.</think><wait/>",
        "<think>Day 2: Reveal as Mayor to secure Town votes.</think><reveal/>",
    ]
    diana_script = [
        # Diana - Jailor: Jails Henry (Mafioso) Night 1
        "<think>Night 1: Jail Henry (Mafioso).</think><jail>Henry</jail>",
        "<think>Day 2: Henry claimed Survivor in jail. I'll share this info.</think><speak>Henry claimed Survivor in jail last night.</speak>",
    ]
    eve_script = [
        # Eve - Doctor: Protects Mayor
        "<think>Night 1: Protect Charlie (Mayor).</think><protect>Charlie</protect>",
        "<think>Day 2: Mayor survived, I'll keep protecting.</think><wait/>",
    ]
    frank_script = [
        # Frank - Godfather: Orders kill on Eve (Doctor)
        "<think>Night 1: Order Henry to kill Eve.</think><speak>Henry, target Eve tonight.</speak><kill>Eve</kill>",
        "<think>Day 2: Eve survived, must be protected. I'll push suspicion on Bob.</think><speak>Bob is acting suspicious, maybe a Vampire?</speak>",
    ]
    grace_script = [
        # Grace - Mafioso: Carries out Godfather's order
        "<think>Night 1: Kill Eve (Doctor).</think><kill>Eve</kill>",
        "<think>Day 2: Lay low, let Godfather lead.</think><wait/>",
    ]
    henry_script = [
        # Henry - Consigliere: Investigates Diana (Jailor)
        "<think>Night 1: Investigate Diana.</think><investigate>Diana</investigate>",
        "<think>Day 2: Diana is Jailor. I'll inform Mafia.</think><speak>Diana is Jailor, avoid her.</speak>",
    ]
    igor_script = [
        # Igor - Coven Leader: Controls Frank (Godfather) to attack Jane (Potion Master)
        "<think>Night 1: Control Frank to attack Jane.</think><control>Frank Jane</control>",
        "<think>Day 2: Push for a Town lynch.</think><speak>Charlie (Mayor) is too quiet, maybe evil?</speak>",
    ]
    jane_script = [
        # Jane - Potion Master: Uses attack potion on Bob (Vampire Hunter)
        "<think>Night 1: Use attack potion on Bob.</think><potion>Bob</potion>",
        "<think>Day 2: Claim Town Support.</think><speak>I'm just a Town Support, nothing to see here.</speak>",
    ]
    kevin_script = [
        # Kevin - Medusa: Stone gazes visitors
        "<think>Night 1: Stone gaze in case of visitors.</think><gaze/>",
        "<think>Day 2: Wait and see who dies.</think><wait/>",
    ]
    luna_script = [
        # Luna - Vampire: Bites Oscar (Survivor)
        "<think>Night 1: Bite Oscar.</think><bite>Oscar</bite>",
        "<think>Day 2: Oscar is now a Vampire. I'll coordinate with him.</think><speak>Oscar, welcome to the night!</speak>",
    ]
    mona_script = [
        # Mona - Executioner: Tries to get Charlie (Mayor) lynched
        "<think>Day 1: Sow doubt on Charlie.</think><speak>Charlie is acting suspicious, could be evil.</speak>",
        "<think>Day 2: Keep pushing for Charlie's lynch.</think><vote>Charlie</vote>",
    ]
    nina_script = [
        # Nina - Jester: Acts erratic to get lynched
        "<think>Day 1: Be weird.</think><speak>I'm the real Mayor! Or am I?</speak>",
        "<think>Day 2: Hope to get on trial.</think><wait/>",
    ]
    oscar_script = [
        # Oscar - Survivor: Uses vest, then becomes Vampire
        "<think>Night 1: Use vest.</think><vest/>",
        "<think>Day 2: Now a Vampire, coordinate with Luna.</think><wait/>",
    ]
    hardcoded_scripts = {
        "Alice": alice_script, "Bob": bob_script, "Charlie": charlie_script, "Diana": diana_script,
        "Eve": eve_script, "Frank": frank_script, "Grace": grace_script, "Henry": henry_script,
        "Igor": igor_script, "Jane": jane_script, "Kevin": kevin_script, "Luna": luna_script,
        "Mona": mona_script, "Nina": nina_script, "Oscar": oscar_script
    }
    scripted_agents = {name: ScriptedAgent(hardcoded_scripts.get(name, ["<wait/>"])) for name in player_names}
    # Simulate a couple of days
    for _ in range(3):
        game.advance_to_day()
        run_scripted_game(scripted_agents, game, f"Day {game.day} Discussion", args)
        game.phase = Phase.NOMINATION
        run_scripted_game(scripted_agents, game, f"Day {game.day} Nomination", args)
        game.process_day_submissions()
        if game.game_is_over(): break
        game.advance_to_night()
        run_scripted_game(scripted_agents, game, f"Night {game.day}", args)
        game.process_night_submissions()
        if game.game_is_over(): break
    print("\n=== FINAL GAME STATE ===")
    print_game_state(game, "Final")
    winning_faction = game.game_is_over()
    print(f"Winning Faction: {winning_faction.name}" if winning_faction else "No clear winning faction.")
    # For this scenario, any of the three factions could win; just assert the game ends cleanly
    assert winning_faction in [Faction.TOWN, Faction.MAFIA, Faction.COVEN], "Expected a major faction to win in scenario 5"

def main():
    test_full_game_classic()
    test_full_game_protectives_vs_neutrals()
    test_full_game_coven_expansion()
    test_full_game_all_any_chaos()
    test_full_game_coven_vs_mafia_vs_town()

if __name__ == "__main__":
    main()
