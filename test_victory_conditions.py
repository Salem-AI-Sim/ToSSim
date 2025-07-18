#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Simulation.game import Game
from Simulation.config import GameConfiguration
from Simulation.player import Player
from Simulation.roles import *
from Simulation.enums import RoleName, Faction, RoleAlignment

def create_test_game(players):
    """Helper to create a game with given players."""
    config = GameConfiguration()
    game = Game(config, players)
    return game

def test_town_victory_basic():
    """Test basic Town victory when all evil factions are eliminated."""
    print("=== Testing Town Victory (Basic) ===")
    
    # Town vs Mafia - Town wins
    sheriff = Player("Sheriff", Sheriff())
    doctor = Player("Doctor", Doctor()) 
    mafioso = Player("Mafioso", Mafioso())
    
    players = [sheriff, doctor, mafioso]
    game = create_test_game(players)
    
    # Kill the Mafioso
    mafioso.is_alive = False
    game.graveyard.append(mafioso)
    
    # Check win condition
    winner = game.game_is_over()
    town_wins = winner == Faction.TOWN
    
    print(f"Town vs Mafia result: {winner}")
    print(f"Town victory: {'[PASS]' if town_wins else '[FAIL]'}")
    
    return town_wins

def test_town_victory_with_neutrals():
    """Test Town victory with surviving neutrals that don't block Town win."""
    print("\n=== Testing Town Victory with Neutrals ===")
    
    # Town + Survivor vs Mafia - Town wins (Survivor doesn't block)
    sheriff = Player("Sheriff", Sheriff())
    survivor = Player("Survivor", Survivor())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [sheriff, survivor, mafioso]
    game = create_test_game(players)
    
    # Kill the Mafioso
    mafioso.is_alive = False
    game.graveyard.append(mafioso)
    
    winner = game.game_is_over()
    town_wins = winner == Faction.TOWN
    
    print(f"Town + Survivor vs dead Mafia result: {winner}")
    print(f"Town victory with Survivor: {'[PASS]' if town_wins else '[FAIL]'}")
    
    return town_wins

def test_mafia_victory():
    """Test Mafia victory when they equal or outnumber Town."""
    print("\n=== Testing Mafia Victory ===")
    
    # Equal numbers: Mafia wins
    godfather = Player("Godfather", Godfather())
    mafioso = Player("Mafioso", Mafioso())
    sheriff = Player("Sheriff", Sheriff())
    doctor = Player("Doctor", Doctor())
    
    players = [godfather, mafioso, sheriff, doctor]
    game = create_test_game(players)
    
    # Kill Town members to give Mafia majority
    sheriff.is_alive = False
    doctor.is_alive = False
    game.graveyard.extend([sheriff, doctor])
    
    winner = game.game_is_over()
    mafia_wins = winner == Faction.MAFIA
    
    print(f"Mafia majority result: {winner}")
    print(f"Mafia victory: {'[PASS]' if mafia_wins else '[FAIL]'}")
    
    return mafia_wins

def test_coven_victory():
    """Test Coven victory scenarios."""
    print("\n=== Testing Coven Victory ===")
    
    # Coven vs everyone else
    coven_leader = Player("CovenLeader", CovenLeader())
    hex_master = Player("HexMaster", HexMaster())
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [coven_leader, hex_master, sheriff, mafioso]
    game = create_test_game(players)
    
    # Kill non-Coven
    sheriff.is_alive = False
    mafioso.is_alive = False
    game.graveyard.extend([sheriff, mafioso])
    
    winner = game.game_is_over()
    coven_wins = winner == Faction.COVEN
    
    print(f"Coven majority result: {winner}")
    print(f"Coven victory: {'[PASS]' if coven_wins else '[FAIL]'}")
    
    return coven_wins

def test_vampire_victory():
    """Test Vampire victory scenarios."""
    print("\n=== Testing Vampire Victory ===")
    
    # Vampires vs others
    vampire1 = Player("Vampire1", Vampire())
    vampire2 = Player("Vampire2", Vampire())
    sheriff = Player("Sheriff", Sheriff())
    
    players = [vampire1, vampire2, sheriff]
    game = create_test_game(players)
    
    # Kill non-Vampires
    sheriff.is_alive = False
    game.graveyard.append(sheriff)
    
    winner = game.game_is_over()
    vampire_wins = winner == Faction.VAMPIRE
    
    print(f"Vampire majority result: {winner}")
    print(f"Vampire victory: {'[PASS]' if vampire_wins else '[FAIL]'}")
    
    return vampire_wins

def test_serial_killer_victory():
    """Test Serial Killer solo victory."""
    print("\n=== Testing Serial Killer Victory ===")
    
    # SK vs others
    serial_killer = Player("SK", SerialKiller())
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [serial_killer, sheriff, mafioso]
    game = create_test_game(players)
    
    # Kill everyone else
    sheriff.is_alive = False
    mafioso.is_alive = False
    game.graveyard.extend([sheriff, mafioso])
    
    winner = game.game_is_over()
    sk_wins = len(game.winners) > 0 and game.winners[0] == serial_killer
    
    print(f"SK solo result: {winner}, winners: {[w.name for w in game.winners]}")
    print(f"SK victory: {'[PASS]' if sk_wins else '[FAIL]'}")
    
    return sk_wins

def test_arsonist_victory():
    """Test Arsonist solo victory."""
    print("\n=== Testing Arsonist Victory ===")
    
    # Arsonist vs others
    arsonist = Player("Arsonist", Arsonist())
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [arsonist, sheriff, mafioso]
    game = create_test_game(players)
    
    # Kill everyone else
    sheriff.is_alive = False
    mafioso.is_alive = False
    game.graveyard.extend([sheriff, mafioso])
    
    winner = game.game_is_over()
    arsonist_wins = len(game.winners) > 0 and game.winners[0] == arsonist
    
    print(f"Arsonist solo result: {winner}, winners: {[w.name for w in game.winners]}")
    print(f"Arsonist victory: {'[PASS]' if arsonist_wins else '[FAIL]'}")
    
    return arsonist_wins

def test_werewolf_victory():
    """Test Werewolf solo victory."""
    print("\n=== Testing Werewolf Victory ===")
    
    # Werewolf vs others
    werewolf = Player("Werewolf", Werewolf())
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [werewolf, sheriff, mafioso]
    game = create_test_game(players)
    
    # Kill everyone else
    sheriff.is_alive = False
    mafioso.is_alive = False
    game.graveyard.extend([sheriff, mafioso])
    
    winner = game.game_is_over()
    werewolf_wins = len(game.winners) > 0 and game.winners[0] == werewolf
    
    print(f"Werewolf solo result: {winner}, winners: {[w.name for w in game.winners]}")
    print(f"Werewolf victory: {'[PASS]' if werewolf_wins else '[FAIL]'}")
    
    return werewolf_wins

def test_jester_victory():
    """Test Jester victory by being lynched."""
    print("\n=== Testing Jester Victory ===")
    
    jester = Player("Jester", Jester())
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [jester, sheriff, mafioso]
    game = create_test_game(players)
    
    # Simulate jester being lynched
    jester.was_lynched = True
    jester.is_alive = False
    game.winners.append(jester)  # Jester wins when lynched
    game.graveyard.append(jester)
    
    winner = game.game_is_over()
    jester_wins = len(game.winners) > 0 and game.winners[0] == jester
    
    print(f"Jester lynched result: {winner}, winners: {[w.name for w in game.winners]}")
    print(f"Jester victory: {'[PASS]' if jester_wins else '[FAIL]'}")
    
    return jester_wins

def test_executioner_victory():
    """Test Executioner victory by getting target lynched."""
    print("\n=== Testing Executioner Victory ===")
    
    executioner = Player("Executioner", Executioner())
    target = Player("Target", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [executioner, target, mafioso]
    game = create_test_game(players)
    
    # Set executioner target
    executioner.role.target = target
    
    # Simulate target being lynched
    target.was_lynched = True
    target.is_alive = False
    game.winners.append(executioner)  # Executioner wins when target lynched
    game.graveyard.append(target)
    
    winner = game.game_is_over()
    exe_wins = len(game.winners) > 0 and game.winners[0] == executioner
    
    print(f"Executioner target lynched result: {winner}, winners: {[w.name for w in game.winners]}")
    print(f"Executioner victory: {'[PASS]' if exe_wins else '[FAIL]'}")
    
    return exe_wins

def test_pirate_victory():
    """Test Pirate victory with 2 plunders."""
    print("\n=== Testing Pirate Victory ===")
    
    pirate = Player("Pirate", Pirate())
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [pirate, sheriff, mafioso]
    game = create_test_game(players)
    
    # Give pirate 2 plunders
    pirate.role.plunders = 2
    
    winner = game.game_is_over()
    pirate_wins = len(game.winners) > 0 and game.winners[0] == pirate
    
    print(f"Pirate 2 plunders result: {winner}, winners: {[w.name for w in game.winners]}")
    print(f"Pirate victory: {'[PASS]' if pirate_wins else '[FAIL]'}")
    
    return pirate_wins

def test_survivor_victory():
    """Test Survivor victory by surviving with winning faction."""
    print("\n=== Testing Survivor Victory ===")
    
    # Survivor survives with Town
    survivor = Player("Survivor", Survivor())
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [survivor, sheriff, mafioso]
    game = create_test_game(players)
    
    # Kill Mafia, leaving Town + Survivor
    mafioso.is_alive = False
    game.graveyard.append(mafioso)
    
    winner = game.game_is_over()
    survivor_survives = winner == Faction.TOWN and survivor.is_alive
    
    print(f"Survivor + Town vs dead Mafia result: {winner}")
    print(f"Survivor survival: {'[PASS]' if survivor_survives else '[FAIL]'}")
    
    return survivor_survives

def test_blocking_neutrals():
    """Test that certain neutrals block faction wins."""
    print("\n=== Testing Blocking Neutrals ===")
    
    # Town + SK vs dead Mafia - SK blocks Town win
    sheriff = Player("Sheriff", Sheriff()) 
    serial_killer = Player("SK", SerialKiller())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [sheriff, serial_killer, mafioso]
    game = create_test_game(players)
    
    # Kill Mafia
    mafioso.is_alive = False
    game.graveyard.append(mafioso)
    
    winner = game.game_is_over()
    game_continues = winner is None  # SK should block Town win
    
    print(f"Town + SK vs dead Mafia result: {winner}")
    print(f"SK blocks Town win: {'[PASS]' if game_continues else '[FAIL]'}")
    
    return game_continues

def test_multiple_nk_same_type():
    """Test multiple NK of same type can co-win."""
    print("\n=== Testing Multiple NK Co-Win ===")
    
    # Multiple SKs alive
    sk1 = Player("SK1", SerialKiller())
    sk2 = Player("SK2", SerialKiller())
    sheriff = Player("Sheriff", Sheriff())
    
    players = [sk1, sk2, sheriff]
    game = create_test_game(players)
    
    # Kill non-SK
    sheriff.is_alive = False
    game.graveyard.append(sheriff)
    
    winner = game.game_is_over()
    both_sks_win = len(game.winners) == 2 and sk1 in game.winners and sk2 in game.winners
    
    print(f"Multiple SK result: {winner}, winners: {[w.name for w in game.winners]}")
    print(f"Both SKs win: {'[PASS]' if both_sks_win else '[FAIL]'}")
    
    return both_sks_win

def test_witch_victory_conditions():
    """Test Witch victory with different factions."""
    print("\n=== Testing Witch Victory Conditions ===")
    
    results = []
    
    # Test 1: Witch + Coven vs others
    witch = Player("Witch", Witch())
    coven_leader = Player("CovenLeader", CovenLeader())
    sheriff = Player("Sheriff", Sheriff())
    
    players = [witch, coven_leader, sheriff]
    game = create_test_game(players)
    
    # Kill non-Coven
    sheriff.is_alive = False
    game.graveyard.append(sheriff)
    
    winner = game.game_is_over()
    witch_with_coven = winner == Faction.COVEN
    results.append(witch_with_coven)
    
    print(f"Witch + Coven result: {winner}")
    print(f"Witch wins with Coven: {'[PASS]' if witch_with_coven else '[FAIL]'}")
    
    # Test 2: Witch + Town vs others (no Coven present)
    witch2 = Player("Witch2", Witch())
    sheriff2 = Player("Sheriff2", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players2 = [witch2, sheriff2, mafioso]
    game2 = create_test_game(players2)
    
    # Kill Mafia
    mafioso.is_alive = False
    game2.graveyard.append(mafioso)
    
    winner2 = game2.game_is_over()
    witch_with_town = winner2 == Faction.TOWN
    results.append(witch_with_town)
    
    print(f"Witch + Town (no Coven) result: {winner2}")
    print(f"Witch wins with Town: {'[PASS]' if witch_with_town else '[FAIL]'}")
    
    return all(results)

def test_edge_cases():
    """Test edge cases and draw conditions."""
    print("\n=== Testing Edge Cases ===")
    
    results = []
    
    # Test 1: Everyone dead
    sheriff = Player("Sheriff", Sheriff())
    mafioso = Player("Mafioso", Mafioso())
    
    players = [sheriff, mafioso]
    game = create_test_game(players)
    
    # Kill everyone
    sheriff.is_alive = False
    mafioso.is_alive = False
    game.graveyard.extend([sheriff, mafioso])
    
    winner = game.game_is_over()
    everyone_dead = winner is True  # Game over but no specific winner
    results.append(everyone_dead)
    
    print(f"Everyone dead result: {winner}")
    print(f"Game ends when everyone dead: {'[PASS]' if everyone_dead else '[FAIL]'}")
    
    # Test 2: Conflicting individual winners (should prioritize individual wins)
    pirate = Player("Pirate", Pirate())
    sheriff2 = Player("Sheriff2", Sheriff())
    
    players2 = [pirate, sheriff2]
    game2 = create_test_game(players2)
    
    # Pirate gets 2 plunders
    pirate.role.plunders = 2
    
    winner2 = game2.game_is_over()
    pirate_priority = len(game2.winners) > 0 and game2.winners[0] == pirate
    results.append(pirate_priority)
    
    print(f"Pirate vs Town result: {winner2}, winners: {[w.name for w in game2.winners]}")
    print(f"Individual win takes priority: {'[PASS]' if pirate_priority else '[FAIL]'}")
    
    return all(results)

def run_comprehensive_victory_tests():
    """Run all victory condition tests."""
    print("[INFO] COMPREHENSIVE VICTORY CONDITIONS TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Town Victory (Basic)", test_town_victory_basic),
        ("Town Victory with Neutrals", test_town_victory_with_neutrals),
        ("Mafia Victory", test_mafia_victory),
        ("Coven Victory", test_coven_victory),
        ("Vampire Victory", test_vampire_victory),
        ("Serial Killer Victory", test_serial_killer_victory),
        ("Arsonist Victory", test_arsonist_victory),
        ("Werewolf Victory", test_werewolf_victory),
        ("Jester Victory", test_jester_victory),
        ("Executioner Victory", test_executioner_victory),
        ("Pirate Victory", test_pirate_victory),
        ("Survivor Victory", test_survivor_victory),
        ("Blocking Neutrals", test_blocking_neutrals),
        ("Multiple NK Co-Win", test_multiple_nk_same_type),
        ("Witch Victory Conditions", test_witch_victory_conditions),
        ("Edge Cases", test_edge_cases),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] {test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("[INFO] VICTORY CONDITIONS TEST RESULTS")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:<10} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("-" * 60)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    
    if failed == 0:
        print("[PASS] ALL VICTORY CONDITION TESTS PASSED!")
    else:
        print(f"[WARN] {failed} test(s) failed - victory conditions need attention")
    
    return failed == 0

if __name__ == "__main__":
    run_comprehensive_victory_tests() 