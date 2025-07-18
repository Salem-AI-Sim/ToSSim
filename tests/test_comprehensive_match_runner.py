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

STEP_MODE = os.environ.get("TOSSIM_STEP") == "1"

from Simulation.grammar import validate_action
from Simulation.interaction_handler import InteractionHandler
from Simulation.game import Game
from Simulation.player import Player
from Simulation.roles import create_role_from_name
from Simulation.enums import RoleName, Phase
from Simulation.config import GameConfiguration
from Simulation.prompt_builder import build_complete_prompt, build_user_prompt

class ScriptedAgent:
    def __init__(self, script):
        self.script = script
        self.turn = 0

    def respond(self, observation, prompt):
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
    for msg in game.chat.history:
        print(msg)
    print("-----------------------------\n")

def run_scripted_game(scripted_agents, game: Game, phase_label="", args=None, observations=None):
    handler = InteractionHandler(game)
    if observations is None:
        observations = {name: "" for name in scripted_agents}

    for player in game.players:
        if not player.is_alive:
            continue
        agent = scripted_agents[player.name]
        
        is_placeholder = agent.script and "Placeholder for" in agent.script[0]
        if args and args.hardcoded_only and is_placeholder:
            continue

        while True:
            observation = observations.get(player.name, "")
            orig_day = game.day
            if orig_day == 0:
                game.day = 1
            prompt = build_complete_prompt(game, player)
            if observation:
                prompt += f"\n<observation>{observation}</observation>"
            
            if not (args and args.hide_inputs):
                if args and args.obfuscate_prompt:
                    print(f"\n[{player.name}] Prompt (obfuscated).")
                else:
                    print(f"\n[{player.name}] SYSTEM+USER PROMPT:\n{prompt}")

            agent_output = agent.respond(observation, prompt)
            
            # If agent only thinks, append a wait action
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
            game.day = orig_day
            
            # Break loop if a terminal action was taken
            if any(tag in agent_output for tag in handler.interaction_tags):
                break
        
        if STEP_MODE:
            input("Press Enter to continue to the next agent...")

    print_chat_log(game, phase_label)
    print_game_state(game, phase_label)
    if STEP_MODE:
        input(f"Press Enter to continue to the next phase ({phase_label})...")
    return observations

def test_hardcoded_town_of_salem_game():
    parser = argparse.ArgumentParser(description="Run a scripted Town of Salem game with verbosity options.")
    parser.add_argument("--hide-inputs", action="store_true", help="Do not print agent prompts (inputs).")
    parser.add_argument("--obfuscate-prompt", action="store_true", help="Print a placeholder instead of the full prompt.")
    parser.add_argument("--hardcoded-only", action="store_true", help="Only show output for agents with hardcoded scripts.")
    args, _ = parser.parse_known_args()

    # --- Define scripts for Day 1 Discussion and Night 1 ---
    alice_script = [
        # Day 1 Discussion
        "<think>It's day 1 and no one has spoken yet. As the Sheriff my goal is to help the Town find threats, but I have no information yet. It's usually good to encourage discussion to get people talking, which can help spot suspicious behavior later, I should not reveal my role yet, but I can break the ice with a friendly message.</think><speak>Good Morning, everyone! Let's have a productive discussion, who is the Jailor so we can get bg/doc/spy on them?</speak>",
        # Night 1
        "<think>I will investigate Bob tonight.</think><investigate>Bob</investigate>",
    ]
    bob_script = [
        # Day 1 Discussion
        "<think>It's Day 1. Alice just encouraged discussion and asked for the Jailor to claim so Town Protectives and Lookouts can coordinate. As the Doctor, my best move is to stay silent and not draw any attention to myself. If the Jailor claims, I will heal him at night. For now, I will wait and observe.</think><wait/>",
        # Night 1
        "<think>I will guard Eve tonight, since she claimed Jailor.</think><protect>Eve</protect>",
    ]
    charlie_script = [
        # Day 1 Discussion
        "<think>It's Day 1. Only Alice has spoken so far, encouraging discussion and asking for the Jailor to claim.</think><wait/>",
        # Night 1
        "<think>I'm in jail. I need to convince the Jailor I'm a town member. I'll claim my role.</think><speak>Hey Jailor, I'm the Investigator. I can help the town.</speak>",
    ]
    diana_script = [
        # Day 1 Discussion
        "<think>Alice is encouraging the Jailor to reveal. I want to remind myself of the Jailor's abilities and importance, so I will look up the Jailor's role details</think><roles>Jailor</roles>",
        "<think>The Jailor is a powerful town role and a key target for protection. Alice is correct if Jailor reveals, I should protect them tonight to keep them safe from evil roles. I will wait for now and watch for the Jailor's claim</think><wait/>",
        # Night 1
        "<think>I will guard Eve tonight, since she claimed Jailor.</think><protect>Eve</protect>",
    ]
    eve_script = [
        # Day 1 Discussion
        "<think>Alice has requested that the Jailor come out to the town to recieve protection I will do so.</think><speak>I am Jailor TP/LO on me</speak>",
        "<think>Now that I have revealed, I will jail Charlie to interrogate him.</think><jail>Charlie</jail>",
        # Night 1
        "<think>Charlie is claiming Investigator in jail. It's a common claim, but I can't risk executing a town member on Night 1. I'll let him live for now.</think>",
    ]
    frank_script = [
        # Day 1
        "<think>Alice is encouraging the Jailor to reveal. Eve has now claimed Jailor. This is a key piece of information. I should record Eve's claim in my notebook.</think><notebook>Eve claimed Jailor D1 after Alice's request. I should watch Eve tonight to confirm if she is the real Jailor by seeing who visits her.</notebook>",
        # Night 1
        "<think>Now it is night. I will watch Eve, who claimed Jailor, to see who visits her. This will help confirm if she is the Jailor and who the Town Protective roles are, or if any evil roles target her.</think><watch>Eve</watch>",
    ]
    grace_script = [
        # Day 1 Discussion
        "<think>The Jailor has revealed themselves, which is a bold move. As Mayor, I am also a very important town role. Revealing now would split the town's protective roles and draw a lot of attention. It's better to stay quiet for now and let the Jailor be the focus.</think><speak>A Jailor claim on Day 1! Interesting. Town, let's make sure to protect them.</speak>",
        # Night 1
        "<think>I have no night action.</think>",
    ]
    henry_script = [
        # Day 1 Discussion
        "<think>It is Day 1. The game has just begun, and players are starting to talk. As the Godfather, my priority is to remain unnoticed and observe the town's initial reactions. I should avoid any actions that might draw attention or reveal my alignment. My best strategy is to stay quiet, listen to the discussions, and gather information about potential threats or allies.</think><wait/>",
        # Night 1
        "<think>It's the first night. I need to establish control of the Mafia and choose a target. Grace has been quiet and could be a high-value town role.</think><speak>Alright team, let's get to work. I think we should target Grace.</speak>",
        "<think>Igor and Jane have agreed. I will now issue the kill order.</think><kill>Grace</kill>",
    ]
    igor_script = [
        # Day 1 Discussion
        "<think>It is Day 1. Alice has started the discussion, and Eve has claimed Jailor. The chat has been quiet for a bit. As a Mafioso, I need to blend in and avoid suspicion. I will say something random to appear active and cooperative, without revealing anything or making strong accusations. This helps me seem like a normal Town member.</think><speak>Interesting start! Let's try to figure out who's who.</speak>",
        # Night 1
        "<think>The Godfather has spoken. I will follow his lead.</think><speak>Sounds good to me, boss.</speak>",
    ]
    jane_script = [
        # Day 1 Discussion
        "<think>It is Day 1. Alice has initiated discussion, Eve has claimed Jailor, and Igor has made a general comment. As the Consigliere, my role is to gather information for the Mafia. I need to appear as a cooperative Town member. I will ask a general question to encourage more players to speak, which might reveal useful information or roles.</think><speak>Good points so far. Any survivor claims?</speak>",
        # Night 1
        "<think>I agree with the Godfather's plan. I'll investigate Alice to see what her role is, since she was the first to speak.</think><speak>I'm on board. I'll check out Alice.</speak><investigate>Alice</investigate>",
    ]
    kevin_script = [
        # Day 1 Discussion
        "<think>It is Day 1. The discussion has started, and Eve has claimed Jailor. As a Serial Killer, my goal is to eliminate all who would oppose me. I need to appear as a normal Town member to avoid suspicion. I will make a general, non-committal statement to participate without revealing anything. This helps me blend in.</think><speak>Alright, let's get this discussion going and find some evil!</speak>",
        # Night 1
        "<think>Time to get my hands dirty. Henry has been quiet. He's my target.</think><kill>Henry</kill>",
    ]
    luna_script = [
        # Day 1 Discussion
        "<think>It is Day 1. The discussion has started. As an Arsonist, my goal is to douse and eventually ignite the town. I need to appear as a harmless Town member. I will make a simple, friendly statement to participate without drawing suspicion. This helps me blend in and observe.</think><speak>Good morning! Hope we can work together to find the bad guys.</speak>",
        # Night 1
        "<think>I'll start by dousing Igor. He'll never see it coming.</think><douse>Igor</douse>",
    ]
    mona_script = [
        # Day 1 Discussion
        "<think>It is Day 1. The discussion has begun, and Eve has claimed Jailor. As an Executioner, my goal is to get my target lynched. I need to appear as a helpful Town member, but also subtly encourage lynching. I will make a general statement to push for action, without revealing my true intentions.</think><speak>Alright Town, let's not waste time. Who are we looking at today?</speak>",
        # Night 1
        "<think>My target is Alice. I need to find a way to get the town to lynch her. I have no night action, so I'll just wait and see what happens.</think>",
    ]
    nina_script = [
        # Day 1 Discussion
        "<think>It is Day 1. The discussion is underway. As a Jester, my goal is to get lynched by the Town. I need to draw attention to myself, but not in an overtly evil way. I will make a slightly quirky or random comment to stand out and encourage people to look at me.</think><speak>Wow, this is exciting! Who's everyone's top suspect so far? I'm just here for the drama!</speak>",
        # Night 1
        "<think>I need to act suspicious to get lynched. But I have no night action. I'll just wait for now.</think>",
    ]
    oscar_script = [
        # Day 1 Discussion
        "<think>It is Day 1. The discussion has started. As a Survivor, my goal is to stay alive until the end of the game. I need to appear neutral and non-threatening to all factions. I will state my role's objective clearly to avoid being targeted by anyone.</think><speak>Hey everyone, I'm just a simple Survivor. I'm not here to cause trouble, just trying to make it to the end.</speak>",
        # Night 1
        "<think>Night 1 is always dangerous. I'll use a vest to be safe.</think><vest/>",
    ]

    # Append Day 2 and Night 2 phases for each agent
    alice_script += [
        # Day 2 Discussion
        "<think>It's Day 2. No one was put on trial yesterday. I'll encourage more discussion to see if anyone slips up.</think><speak>We need more info. Did anyone see anything suspicious last night?</speak>",
        # Day 2 Nomination
        "<think>Still not enough info. I'll wait to see who gets nominated.</think><wait/>",
        # Day 2 Defense
        "<think>I'm not on trial, so I'll observe the defense.</think><wait/>",
        # Day 2 Judgement
        "<think>I don't have enough info to vote guilty. I'll vote innocent.</think><vote>innocent</vote>",
        # Day 2 Last Words
        "<think>I'm not on trial, so nothing to say.</think><wait/>",
        # Day 2 Pre-Night
        "<think>Preparing for night. I'll review my notes.</think><wait/>",
        # Night 2
        "<think>I will investigate Grace tonight.</think><investigate>Grace</investigate>",
    ]
    bob_script += [
        "<think>Day 2. Eve survived the night, so my heal was successful or she wasn't attacked. I'll keep quiet and see if anyone claims attacked.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent unless there's strong evidence.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to heal again.</think><wait/>",
        "<think>Night 2. I'll heal Eve again to keep the Jailor safe.</think><protect>Eve</protect>",
    ]
    charlie_script += [
        "<think>Day 2. I survived jail. I'll keep quiet and see if the Jailor trusts me.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent unless there's strong evidence.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to investigate.</think><wait/>",
        "<think>Night 2. I'll investigate Henry tonight.</think><investigate>Henry</investigate>",
    ]
    diana_script += [
        "<think>Day 2. Eve survived, so my protection may have helped. I'll keep quiet and see if anyone claims attacked.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent unless there's strong evidence.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to protect again.</think><wait/>",
        "<think>Night 2. I'll protect Eve again to keep the Jailor safe.</think><protect>Eve</protect>",
    ]
    eve_script += [
        "<think>Day 2. Charlie claimed Investigator in jail. I'll keep an eye on him but won't execute yet. I'll announce that he claimed Investigator.</think><speak>Charlie claimed Investigator in jail last night. Town, keep an eye on him.</speak>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent unless there's strong evidence.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to jail again.</think><wait/>",
        "<think>Night 2. I'll jail Kevin tonight to question him.</think><jail>Kevin</jail>",
    ]
    frank_script += [
        "<think>Day 2. I saw who visited Eve last night. I'll keep this info in my notebook.</think><notebook>Recorded visits to Eve N1.</notebook>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent unless there's strong evidence.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to watch again.</think><wait/>",
        "<think>Night 2. I'll watch Bob tonight.</think><watch>Bob</watch>",
    ]
    grace_script += [
        "<think>Day 2. Jailor survived, so the town protectives did their job. I'll stay quiet for now.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent unless there's strong evidence.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare for the next day.</think><wait/>",
        "<think>Night 2. No action for Mayor at night.</think><wait/>",
    ]
    henry_script += [
        "<think>Day 2. Grace was targeted last night. I'll try to steer suspicion away from Mafia.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated and push suspicion if possible.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote guilty if a Townie is on trial.</think><vote>guilty</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll coordinate with Mafia.</think><wait/>",
        "<think>Night 2. I'll order a kill on Bob.</think><kill>Bob</kill>",
    ]
    igor_script += [
        "<think>Day 2. I'll support the Godfather's plan and stay quiet.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote guilty if a Townie is on trial.</think><vote>guilty</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll coordinate with Mafia.</think><wait/>",
        "<think>Night 2. Awaiting Godfather's orders.</think><wait/>",
    ]
    jane_script += [
        "<think>Day 2. I'll share my investigation results with Mafia privately.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote guilty if a Townie is on trial.</think><vote>guilty</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to investigate again.</think><wait/>",
        "<think>Night 2. I'll investigate Diana tonight.</think><investigate>Diana</investigate>",
    ]
    kevin_script += [
        "<think>Day 2. I'll act like a townie and avoid suspicion.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent to blend in.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to kill again.</think><wait/>",
        "<think>Night 2. I'll kill Grace tonight.</think><kill>Grace</kill>",
    ]
    luna_script += [
        "<think>Day 2. I'll stay quiet and avoid suspicion.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent to blend in.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to douse again.</think><wait/>",
        "<think>Night 2. I'll douse Henry tonight.</think><douse>Henry</douse>",
    ]
    mona_script += [
        "<think>Day 2. I'll try to get my target lynched by sowing suspicion.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent to blend in.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to push my target again.</think><wait/>",
        "<think>Night 2. No action for Executioner at night.</think><wait/>",
    ]
    nina_script += [
        "<think>Day 2. I'll act suspicious to try to get lynched.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent to blend in.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to act suspicious again.</think><wait/>",
        "<think>Night 2. No action for Jester at night.</think><wait/>",
    ]
    oscar_script += [
        "<think>Day 2. I'll stay quiet and try to survive.</think><wait/>",
        "<think>Nomination phase. I'll wait to see who gets nominated.</think><wait/>",
        "<think>Defense phase. I'm not on trial, so I'll observe.</think><wait/>",
        "<think>Judgement phase. I'll vote innocent to blend in.</think><vote>innocent</vote>",
        "<think>Last Words. Not on trial.</think><wait/>",
        "<think>Pre-Night. I'll prepare to use a vest again.</think><wait/>",
        "<think>Night 2. I'll use a vest tonight.</think><vest/>",
    ]

    # --- Set up the game and assign roles ---
    player_names = [
        "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry", "Igor", "Jane", "Kevin", "Luna", "Mona", "Nina", "Oscar"
    ]
    roles = [
        RoleName.SHERIFF, RoleName.DOCTOR, RoleName.INVESTIGATOR, RoleName.BODYGUARD, RoleName.JAILOR,
        RoleName.LOOKOUT, RoleName.MAYOR, RoleName.GODFATHER, RoleName.MAFIOSO, RoleName.CONSIGLIERE,
        RoleName.SERIAL_KILLER, RoleName.ARSONIST, RoleName.EXECUTIONER, RoleName.JESTER, RoleName.SURVIVOR
    ]
    players = []
    for name, role_name in zip(player_names, roles):
        role = create_role_from_name(role_name)
        player = Player(name, role)
        players.append(player)

    config = GameConfiguration()
    game = Game(config, players)

    # --- Map agents ---
    hardcoded_scripts = {
        "Alice": alice_script,
        "Bob": bob_script,
        "Charlie": charlie_script,
        "Diana": diana_script,
        "Eve": eve_script,
        "Frank": frank_script,
        "Grace": grace_script,
        "Henry": henry_script,
        "Igor": igor_script,
        "Jane": jane_script,
        "Kevin": kevin_script,
        "Luna": luna_script,
        "Mona": mona_script,
        "Nina": nina_script,
        "Oscar": oscar_script,
    }
    placeholder = lambda name, role_name: [f"<think>Placeholder for {name} as {role_name.value}</think><wait/>", f"<think>Placeholder N1 for {name}</think><wait/>"]
    scripted_agents = {}
    for name, role_name in zip(player_names, roles):
        if name in hardcoded_scripts:
            scripted_agents[name] = ScriptedAgent(hardcoded_scripts[name])
        else:
            scripted_agents[name] = ScriptedAgent(placeholder(name, role_name))

    # --- Run Day 1 Discussion ---
    print("\n=== Day 1: Discussion ===\n")
    game.time = game.time.DAY
    game.phase = Phase.DISCUSSION
    observations = run_scripted_game(scripted_agents, game, "Day 1 Discussion", args)

    # --- Advance to Night 1 ---
    print("\n=== Night 1 ===\n")
    game.advance_to_night()
    run_scripted_game(scripted_agents, game, "Night 1", args, observations=observations)

    # --- Print final results ---
    print("\n=== FINAL GAME STATE ===\n")
    print_game_state(game, "Final")
    print("Winners:")
    if game.winners:
        for winner in game.winners:
            print(f"  {winner.name} ({winner.role.name.value})")
    else:
        print("  No winners yet.")
    print("Deaths:")
    for p in game.players:
        if not p.is_alive:
            print(f"  {p.name} ({p.role.name.value})")
    print("\n--- END OF TEST ---\n")

if __name__ == "__main__":
    test_hardcoded_town_of_salem_game()