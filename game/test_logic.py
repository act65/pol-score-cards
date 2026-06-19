import pytest
import math
import random
from typing import List, Optional, Tuple
from unittest.mock import patch # For controlling random outcomes in specific tests

from game_logic import (
    GameConfig,
    Attributes,
    PoliticianCard,
    PlayerState,
    GameState,
    GameEngine,
    PlayCardAction,
    AttackAction,
    PlayerTurnActions,
    RoundActions,
    config
)

# --- MOCK DATA GENERATION ---
MOCK_STAT_MIN = 1
MOCK_STAT_MAX_NORMAL = 5 # Keep stats somewhat low for predictable HP/damage
MOCK_STAT_MAX_HIGH = 10
MOCK_ATTR_MAX = 100 # For percentage-based attributes like specificity, civility etc.

def create_mock_attributes(
    strength: Optional[int] = None,
    divination: Optional[int] = None,
    charisma: Optional[int] = None,
    rigor: Optional[int] = None,
    specificity: Optional[int] = None,
    civility: Optional[int] = None,
    authenticity: Optional[int] = None,
    veracity: Optional[int] = None,
    forthrightness: Optional[int] = None,
) -> Attributes:
    return Attributes(
        strength=strength if strength is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX_NORMAL),
        divination=divination if divination is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX_HIGH),
        charisma=charisma if charisma is not None else random.randint(0, GameConfig().CHARISMA_PER_EXTRA_SLOT * 2), # Range for charisma
        rigor=rigor if rigor is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX_NORMAL),
        specificity=specificity if specificity is not None else random.randint(50, MOCK_ATTR_MAX), # Usually want some specificity
        civility=civility if civility is not None else random.randint(0, MOCK_ATTR_MAX),
        authenticity=authenticity if authenticity is not None else random.randint(50, MOCK_ATTR_MAX),
        veracity=veracity if veracity is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX_NORMAL),
        forthrightness=forthrightness if forthrightness is not None else random.randint(0, MOCK_ATTR_MAX),
    )

def create_mock_politician_card(
    card_id_num: int,
    name_prefix: str = "Mock Politician",
    attributes: Optional[Attributes] = None
) -> PoliticianCard:
    card_id = f"mock_pol_{name_prefix.lower().replace(' ', '_')}_{card_id_num}"
    name = f"{name_prefix} {card_id_num}"
    party = random.choice(["Party Alpha", "Party Beta", "Party Gamma"])
    
    attrs = attributes if attributes else create_mock_attributes()
    
    # PoliticianCard constructor now takes attributes directly
    # owner_id is set when drawn to hand or by player state
    return PoliticianCard(id=card_id, name=name, party=party, attributes=attrs)


def generate_mock_deck(num_cards: int, name_prefix: str = "DeckCard") -> List[PoliticianCard]:
    deck = []
    for i in range(num_cards):
        # owner_id will be set by PlayerState when drawing
        deck.append(create_mock_politician_card(i + 1, name_prefix=name_prefix))
    random.shuffle(deck)
    return deck

# --- RANDOM ACTION PLAYER ---

def generate_random_player_actions(player_id: str, game_state: GameState) -> PlayerTurnActions:
    player_state = game_state.players[player_id]
    opponent_state = game_state.get_opponent(player_id)
    actions = []

    # 1. Decide to play a card (max 1 per turn for simplicity in this random agent)
    if player_state.hand and len(player_state.field) < player_state.max_cards_on_field:
        if random.choice([True, False]): # 50% chance to try playing a card
            card_to_play = random.choice(player_state.hand)
            actions.append(PlayCardAction(player_id=player_id, card_instance_id=card_to_play.instance_id))

    # 2. Decide to attack with cards on field
    # Cards can only attack once per turn (implicitly handled by game engine if we add such a rule)
    # For now, assume all cards on field can attempt an attack if they want
    eligible_attackers = [card for card in player_state.field if not card.is_defeated()]
    
    if eligible_attackers and opponent_state.field:
        eligible_targets = [card for card in opponent_state.field if not card.is_defeated()]
        if eligible_targets:
            num_attacks = random.randint(0, len(eligible_attackers)) # Can choose to attack with 0 to all eligible cards
            
            attackers_for_this_turn = random.sample(eligible_attackers, num_attacks)

            for attacker_card in attackers_for_this_turn:
                if not eligible_targets: # All targets might have been marked for defeat by previous random choices
                    break
                target_card = random.choice(eligible_targets)
                actions.append(AttackAction(
                    player_id=player_id,
                    attacker_instance_id=attacker_card.instance_id,
                    target_instance_id=target_card.instance_id
                ))
                # Optional: remove target from eligible_targets if you don't want multiple attackers on the same target in one planning phase
                # For simplicity, we allow it here, the game engine will resolve.

    return PlayerTurnActions(player_id=player_id, actions=actions)

# --- PYTEST FIXTURES ---

@pytest.fixture
def P1_ID() -> str:
    return config.PLAYER_IDS[0]

@pytest.fixture
def P2_ID() -> str:
    return config.PLAYER_IDS[1]

@pytest.fixture
def initial_decks(P1_ID: str, P2_ID: str) -> Tuple[List[PoliticianCard], List[PoliticianCard]]:
    deck1 = generate_mock_deck(10, name_prefix=f"{P1_ID}-Card")
    deck2 = generate_mock_deck(10, name_prefix=f"{P2_ID}-Card")
    return deck1, deck2

@pytest.fixture
def game_engine(initial_decks: Tuple[List[PoliticianCard], List[PoliticianCard]]) -> GameEngine:
    deck1, deck2 = initial_decks
    return GameEngine(player1_deck=deck1, player2_deck=deck2)

@pytest.fixture
def initialized_game_state(game_engine: GameEngine) -> GameState:
    return game_engine.initialize_game_state()

# --- TEST CASES ---

def test_game_initialization(initialized_game_state: GameState, P1_ID: str, P2_ID: str):
    state = initialized_game_state
    assert state.game_phase == "ONGOING"
    assert state.round_number == 1
    assert state.winner is None

    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    assert p1.health_points == config.STARTING_HEALTH_POINTS
    assert p2.health_points == config.STARTING_HEALTH_POINTS

    assert len(p1.hand) == config.INITIAL_HAND_SIZE
    assert len(p2.hand) == config.INITIAL_HAND_SIZE
    assert len(p1.deck) == 10 - config.INITIAL_HAND_SIZE # Assuming 10 cards in mock deck
    assert len(p2.deck) == 10 - config.INITIAL_HAND_SIZE

    assert p1.max_cards_on_field == config.BASE_FIELD_SLOTS # Initially no cards on field
    assert p2.max_cards_on_field == config.BASE_FIELD_SLOTS

    for card in p1.hand:
        assert card.owner_id == P1_ID
    for card in p2.hand:
        assert card.owner_id == P2_ID

def test_play_card_action(initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    state = initialized_game_state
    p1 = state.players[P1_ID]

    assert len(p1.hand) > 0, "Player 1 should have cards in hand to test playing."
    card_to_play = p1.hand[0]
    
    play_action = PlayCardAction(player_id=P1_ID, card_instance_id=card_to_play.instance_id)
    round_actions = RoundActions(
        player1_actions=PlayerTurnActions(player_id=P1_ID, actions=[play_action]),
        player2_actions=PlayerTurnActions(player_id=P2_ID, actions=[])
    )
    
    # Simulate just the play card part of process_round for focused test
    # In a real test of process_round, it would handle this.
    # Here, we manually call the player's method for simplicity of this unit test.
    original_hand_size = len(p1.hand)
    original_field_size = len(p1.field)

    success = p1.play_card_to_field(card_to_play.instance_id)
    assert success
    
    assert card_to_play not in p1.hand
    assert card_to_play in p1.field
    assert len(p1.hand) == original_hand_size - 1
    assert len(p1.field) == original_field_size + 1
    
    # Test playing when field is full
    p1.max_cards_on_field = 1 # Artificially limit
    assert len(p1.field) == 1
    if p1.hand: # If there's another card to try and play
        another_card = p1.hand[0]
        success_field_full = p1.play_card_to_field(another_card.instance_id)
        assert not success_field_full
        assert another_card in p1.hand
        assert len(p1.field) == 1 # Still 1 card on field

def test_charisma_updates_max_field_cards(P1_ID: str):
    player = PlayerState(id=P1_ID, deck=[])
    assert player.max_cards_on_field == config.BASE_FIELD_SLOTS

    # Add a card with high charisma
    high_charisma_attrs = create_mock_attributes(charisma=config.CHARISMA_PER_EXTRA_SLOT)
    card1 = create_mock_politician_card(1, attributes=high_charisma_attrs)
    player.field.append(card1)
    player.update_max_field_cards()
    assert player.max_cards_on_field == config.BASE_FIELD_SLOTS + 1

    # Add another card, charisma should stack
    another_high_charisma_attrs = create_mock_attributes(charisma=config.CHARISMA_PER_EXTRA_SLOT)
    card2 = create_mock_politician_card(2, attributes=another_high_charisma_attrs)
    player.field.append(card2)
    player.update_max_field_cards()
    assert player.max_cards_on_field == config.BASE_FIELD_SLOTS + 2
    
    # Remove a card
    player.field.remove(card1)
    player.update_max_field_cards()
    assert player.max_cards_on_field == config.BASE_FIELD_SLOTS + 1


def test_attack_action_basic_damage(initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    state = initialized_game_state
    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    # Setup: P1 has an attacker, P2 has a target
    # Attacker: High Strength, High Rigor
    # Target: Low Strength, Low Veracity (to ensure damage)
    attacker_attrs = create_mock_attributes(strength=5, rigor=3, specificity=100, authenticity=100, civility=0) # No miss, no retarget, no civility
    target_attrs = create_mock_attributes(strength=2, veracity=1, forthrightness=0) # No block

    attacker_card = create_mock_politician_card(1, name_prefix="Attacker", attributes=attacker_attrs)
    target_card = create_mock_politician_card(1, name_prefix="Target", attributes=target_attrs)
    
    attacker_card.owner_id = P1_ID
    target_card.owner_id = P2_ID

    p1.field.append(attacker_card)
    p2.field.append(target_card)
    
    # Manually update owner_id for cards on field if not set by play_card
    attacker_card.owner_id = P1_ID
    target_card.owner_id = P2_ID
    state.players[P1_ID].field = [attacker_card]
    state.players[P2_ID].field = [target_card]


    expected_attack_power = attacker_attrs.strength * attacker_attrs.rigor # 5 * 3 = 15
    expected_defense_power = target_attrs.strength * target_attrs.veracity # 2 * 1 = 2
    expected_damage = expected_attack_power - expected_defense_power # 15 - 2 = 13
    
    initial_target_hp = target_card.current_hp

    attack_action = AttackAction(
        player_id=P1_ID,
        attacker_instance_id=attacker_card.instance_id,
        target_instance_id=target_card.instance_id
    )
    round_actions = RoundActions(
        player1_actions=PlayerTurnActions(player_id=P1_ID, actions=[attack_action]),
        player2_actions=PlayerTurnActions(player_id=P2_ID, actions=[])
    )

    new_state = game_engine.process_round(state, round_actions) # Process round will also draw cards

    # Find the cards in the new state as they are copies
    processed_target_card, _ = new_state.find_card_on_field(target_card.instance_id)
    assert processed_target_card is not None
    assert processed_target_card.current_hp == initial_target_hp - expected_damage
    assert not processed_target_card.is_defeated() # Assuming MAX_HP_CARD * strength is high enough

def test_card_defeat(initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    state = initialized_game_state
    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    # Attacker strong enough to defeat target in one hit
    attacker_attrs = create_mock_attributes(strength=100, rigor=100, specificity=100, authenticity=100, civility=0)
    target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0) # Very weak target

    attacker_card = create_mock_politician_card(1, name_prefix="StrongAttacker", attributes=attacker_attrs)
    # Target card will have max_hp = MAX_HP_CARD * 1
    target_card = create_mock_politician_card(1, name_prefix="WeakTarget", attributes=target_attrs)
    
    attacker_card.owner_id = P1_ID
    target_card.owner_id = P2_ID
    p1.field.append(attacker_card)
    p2.field.append(target_card)
    state.players[P1_ID].field = [attacker_card] # Ensure state is updated
    state.players[P2_ID].field = [target_card]

    attack_action = AttackAction(
        player_id=P1_ID,
        attacker_instance_id=attacker_card.instance_id,
        target_instance_id=target_card.instance_id
    )
    round_actions = RoundActions(
        player1_actions=PlayerTurnActions(player_id=P1_ID, actions=[attack_action]),
        player2_actions=PlayerTurnActions(player_id=P2_ID, actions=[])
    )
    
    new_state = game_engine.process_round(state, round_actions)
    
    defeated_card_info = new_state.find_card_on_field(target_card.instance_id)
    assert defeated_card_info is None # Card should be removed from field
    assert target_card in new_state.players[P2_ID].graveyard
    assert any(log_entry.startswith(f"R1:   {target_card.name} has been defeated") for log_entry in new_state.action_log)


# --- Tests for Specific Mechanics (using mock.patch) ---

@patch('random.random') # Mocks random.random() calls within the patched scope
def test_specificity_miss(mock_random, initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    # Force a miss: specificity < 100, and random.random() < miss_chance
    # miss_chance = (100 - specificity) / 100.0
    # If specificity = 50, miss_chance = 0.5. We need random.random() to be < 0.5
    mock_random.return_value = 0.4 

    state = initialized_game_state
    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    attacker_attrs = create_mock_attributes(strength=3, rigor=2, specificity=50, authenticity=100, civility=0)
    target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0)
    attacker_card = create_mock_politician_card(1, "MissAttacker", attributes=attacker_attrs)
    target_card = create_mock_politician_card(1, "Target", attributes=target_attrs)
    
    attacker_card.owner_id = P1_ID
    target_card.owner_id = P2_ID
    p1.field.append(attacker_card)
    p2.field.append(target_card)
    state.players[P1_ID].field = [attacker_card]
    state.players[P2_ID].field = [target_card]
    initial_target_hp = target_card.current_hp

    attack_action = AttackAction(P1_ID, attacker_card.instance_id, target_card.instance_id)
    round_actions = RoundActions(PlayerTurnActions(P1_ID, [attack_action]), PlayerTurnActions(P2_ID, []))
    
    new_state = game_engine.process_round(state, round_actions)
    
    processed_target_card, _ = new_state.find_card_on_field(target_card.instance_id)
    assert processed_target_card.current_hp == initial_target_hp # HP Unchanged due to miss
    assert any(f"MISSED {target_card.name}" in log for log in new_state.action_log)

def test_forthrightness_reflect(initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    # Forthrightness reflects damage back to the attacker; it does NOT block
    # damage to the target. With forthrightness=60, the attacker takes
    # calculated_attack * 60 // 100 in reflected damage, while the target still
    # takes the full hit. (See rules.md and game_logic.py.)
    state = initialized_game_state

    # specificity=100 (no miss), authenticity=100 (no retarget) keep the attack deterministic.
    attacker_attrs = create_mock_attributes(strength=3, rigor=2, specificity=100, authenticity=100, civility=0)
    target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=60)
    attacker_card = create_mock_politician_card(1, "Attacker", attributes=attacker_attrs)
    target_card = create_mock_politician_card(1, "ReflectTarget", attributes=target_attrs)

    attacker_card.owner_id = P1_ID
    target_card.owner_id = P2_ID
    state.players[P1_ID].field = [attacker_card]
    state.players[P2_ID].field = [target_card]
    initial_target_hp = target_card.current_hp
    initial_attacker_hp = attacker_card.current_hp

    # calculated_attack = strength*rigor = 6, defense = strength*veracity = 1.
    calculated_attack = attacker_card.attack_damage_base
    expected_target_damage = max(0, calculated_attack - target_card.defense_base)
    expected_reflected = calculated_attack * target_attrs.forthrightness // 100

    attack_action = AttackAction(P1_ID, attacker_card.instance_id, target_card.instance_id)
    round_actions = RoundActions(PlayerTurnActions(P1_ID, [attack_action]), PlayerTurnActions(P2_ID, []))

    new_state = game_engine.process_round(state, round_actions)

    processed_target_card, _ = new_state.find_card_on_field(target_card.instance_id)
    processed_attacker_card, _ = new_state.find_card_on_field(attacker_card.instance_id)

    # Target takes full damage (reflection does not block it)
    assert processed_target_card.current_hp == initial_target_hp - expected_target_damage
    # Attacker takes the reflected damage
    assert processed_attacker_card.current_hp == initial_attacker_hp - expected_reflected
    assert expected_reflected > 0
    assert any("reflected" in log for log in new_state.action_log)

@patch('random.random')
@patch('random.choice') # Also mock random.choice for retargeting
def test_authenticity_retarget(mock_random_choice, mock_random_roll, initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    # Force retarget: random.random() < (100 - authenticity) / 100.0
    # If authenticity = 30, retarget_chance = 0.7. We need random.random() < 0.7
    mock_random_roll.return_value = 0.6 

    state = initialized_game_state
    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    attacker_attrs = create_mock_attributes(strength=3, rigor=2, specificity=100, authenticity=30, civility=0) # Low authenticity
    original_target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0)
    new_target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0)

    attacker_card = create_mock_politician_card(1, "RetargetAttacker", attributes=attacker_attrs)
    original_target_card = create_mock_politician_card(1, "OriginalTarget", attributes=original_target_attrs)
    new_actual_target_card = create_mock_politician_card(2, "NewActualTarget", attributes=new_target_attrs)

    attacker_card.owner_id = P1_ID
    original_target_card.owner_id = P2_ID
    new_actual_target_card.owner_id = P2_ID

    p1.field.append(attacker_card)
    p2.field.extend([original_target_card, new_actual_target_card])
    state.players[P1_ID].field = [attacker_card]
    state.players[P2_ID].field = [original_target_card, new_actual_target_card]
    
    # Make random.choice return the new_actual_target_card when retargeting
    # The list passed to random.choice will be opponent_cards_on_field excluding the original target.
    # In this case, it will be [new_actual_target_card].
    mock_random_choice.return_value = new_actual_target_card 

    initial_original_target_hp = original_target_card.current_hp
    initial_new_target_hp = new_actual_target_card.current_hp
    expected_damage = (attacker_attrs.strength * attacker_attrs.rigor) - (new_target_attrs.strength * new_target_attrs.veracity)


    attack_action = AttackAction(P1_ID, attacker_card.instance_id, original_target_card.instance_id) # Intends to attack original
    round_actions = RoundActions(PlayerTurnActions(P1_ID, [attack_action]), PlayerTurnActions(P2_ID, []))
    
    new_state = game_engine.process_round(state, round_actions)
    
    processed_original_target, _ = new_state.find_card_on_field(original_target_card.instance_id)
    processed_new_target, _ = new_state.find_card_on_field(new_actual_target_card.instance_id)

    assert processed_original_target.current_hp == initial_original_target_hp # Original target not hit
    assert processed_new_target.current_hp == initial_new_target_hp - expected_damage # New target hit
    assert any(f"retargeted from {original_target_card.name} to {new_actual_target_card.name}" in log for log in new_state.action_log)


def test_civility_pierce_damage(initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    state = initialized_game_state
    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    # Attacker with high civility
    attacker_attrs = create_mock_attributes(strength=3, rigor=2, specificity=100, authenticity=100, civility=config.CIVILITY_PIERCE_DIVISOR * 5) # Civility = 50 if divisor is 10
    target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0) # No block

    attacker_card = create_mock_politician_card(1, "CivilAttacker", attributes=attacker_attrs)
    target_card = create_mock_politician_card(1, "Target", attributes=target_attrs)
    
    attacker_card.owner_id = P1_ID
    target_card.owner_id = P2_ID
    p1.field.append(attacker_card)
    p2.field.append(target_card)
    state.players[P1_ID].field = [attacker_card]
    state.players[P2_ID].field = [target_card]

    initial_p2_hp = p2.health_points
    expected_civility_damage = math.floor(attacker_attrs.civility / config.CIVILITY_PIERCE_DIVISOR) # 5

    attack_action = AttackAction(P1_ID, attacker_card.instance_id, target_card.instance_id)
    round_actions = RoundActions(PlayerTurnActions(P1_ID, [attack_action]), PlayerTurnActions(P2_ID, []))
    
    new_state = game_engine.process_round(state, round_actions)
    
    final_p2_hp = new_state.players[P2_ID].health_points
    assert final_p2_hp == initial_p2_hp - expected_civility_damage
    assert any(f"deals {expected_civility_damage} direct damage to Player {P2_ID}" in log for log in new_state.action_log)


def test_game_over_by_player_health(initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    state = initialized_game_state
    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    # Setup: P1 has a very strong attacker, P2 has a target, P2's health is low
    # Attacker will deal massive civility damage
    attacker_attrs = create_mock_attributes(
        strength=1, rigor=1, specificity=100, authenticity=100, 
        civility=config.CIVILITY_PIERCE_DIVISOR * (config.STARTING_HEALTH_POINTS + 10) # Civility damage > P2 HP
    )
    target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0) # No block

    attacker_card = create_mock_politician_card(1, "Finisher", attributes=attacker_attrs)
    target_card = create_mock_politician_card(1, "Victim", attributes=target_attrs)
    
    attacker_card.owner_id = P1_ID
    target_card.owner_id = P2_ID
    p1.field.append(attacker_card)
    p2.field.append(target_card)
    state.players[P1_ID].field = [attacker_card]
    state.players[P2_ID].field = [target_card]

    attack_action = AttackAction(P1_ID, attacker_card.instance_id, target_card.instance_id)
    round_actions = RoundActions(PlayerTurnActions(P1_ID, [attack_action]), PlayerTurnActions(P2_ID, []))
    
    new_state = game_engine.process_round(state, round_actions)
    
    assert new_state.game_phase == "GAME_OVER"
    assert new_state.winner == P1_ID
    assert new_state.players[P2_ID].health_points <= 0
    assert any(f"Game Over! Winner: {P1_ID}" in log for log in new_state.action_log)

def test_divination_attack_order(initialized_game_state: GameState, game_engine: GameEngine, P1_ID: str, P2_ID: str):
    state = initialized_game_state
    p1 = state.players[P1_ID]
    p2 = state.players[P2_ID]

    # P1_Attacker: Low Divination, will defeat P2_Target1
    # P2_Attacker: High Divination, will defeat P1_Target1
    # If P2 attacks first, P1_Target1 is defeated. P1_Attacker can still attack P2_Target1.
    # If P1 attacks first, P2_Target1 is defeated. P2_Attacker can still attack P1_Target1.
    # The key is to check the log order or ensure the high divination attacker's effect happens "before" the low one in terms of consequences if one could prevent the other.
    # For this test, we'll check that the high divination attack is logged as processing before the low one.

    p1_attacker_attrs = create_mock_attributes(strength=10, rigor=10, specificity=100, authenticity=100, civility=0, divination=1)
    p1_target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0, divination=0) # Target for P2

    p2_attacker_attrs = create_mock_attributes(strength=10, rigor=10, specificity=100, authenticity=100, civility=0, divination=10) # High Div
    p2_target_attrs = create_mock_attributes(strength=1, veracity=1, forthrightness=0, divination=0) # Target for P1

    p1_attacker = create_mock_politician_card(1, "P1_LowDiv_Attacker", attributes=p1_attacker_attrs)
    p1_target = create_mock_politician_card(2, "P1_Target", attributes=p1_target_attrs)

    p2_attacker = create_mock_politician_card(1, "P2_HighDiv_Attacker", attributes=p2_attacker_attrs)
    p2_target = create_mock_politician_card(2, "P2_Target", attributes=p2_target_attrs)

    p1_attacker.owner_id, p1_target.owner_id = P1_ID, P1_ID
    p2_attacker.owner_id, p2_target.owner_id = P2_ID, P2_ID

    p1.field.extend([p1_attacker, p1_target])
    p2.field.extend([p2_attacker, p2_target])
    state.players[P1_ID].field = [p1_attacker, p1_target]
    state.players[P2_ID].field = [p2_attacker, p2_target]


    p1_attack = AttackAction(P1_ID, p1_attacker.instance_id, p2_target.instance_id)
    p2_attack = AttackAction(P2_ID, p2_attacker.instance_id, p1_target.instance_id)

    round_actions = RoundActions(
        PlayerTurnActions(P1_ID, [p1_attack]),
        PlayerTurnActions(P2_ID, [p2_attack])
    )
    
    new_state = game_engine.process_round(state, round_actions)

    attack_logs = [log for log in new_state.action_log if "Attack: " in log]
    
    assert len(attack_logs) >= 2, "Expected at least two attack logs"

    # Find the index of P2's (high div) attack log and P1's (low div) attack log
    p2_attack_log_index = -1
    p1_attack_log_index = -1

    for i, log_entry in enumerate(new_state.action_log):
        if f"Attack: {p2_attacker.name}" in log_entry:
            p2_attack_log_index = i
        elif f"Attack: {p1_attacker.name}" in log_entry:
            p1_attack_log_index = i
            
    assert p2_attack_log_index != -1, "P2's attack log not found"
    assert p1_attack_log_index != -1, "P1's attack log not found"
    assert p2_attack_log_index < p1_attack_log_index, "P2's high divination attack should be processed (logged) before P1's low divination attack."

# --- Test with Random Player (Smoke Test) ---
def test_game_run_with_random_players(game_engine: GameEngine, P1_ID: str, P2_ID: str):
    state = game_engine.initialize_game_state()
    max_rounds = 5 # Run a few rounds

    for i in range(max_rounds):
        if state.game_phase == "GAME_OVER":
            print(f"Game ended early in smoke test at round {i+1}. Winner: {state.winner}")
            break

        p1_turn_actions = generate_random_player_actions(P1_ID, state)
        p2_turn_actions = generate_random_player_actions(P2_ID, state)
        
        round_actions = RoundActions(
            player1_actions=p1_turn_actions,
            player2_actions=p2_turn_actions
        )
        
        print(f"\n--- Round {state.round_number} Actions ---")
        print(f"P1 Actions: {[a.__class__.__name__ for a in p1_turn_actions.actions]}")
        print(f"P2 Actions: {[a.__class__.__name__ for a in p2_turn_actions.actions]}")

        state = game_engine.process_round(state, round_actions)
        
        print(f"\n--- State after Round {state.round_number-1 if state.game_phase != 'ONGOING' else state.round_number-1} ---") # Adjust round number for log
        print(state.players[P1_ID])
        print(state.players[P2_ID])
        assert state.players[P1_ID].health_points >= 0 or state.game_phase == "GAME_OVER"
        assert state.players[P2_ID].health_points >= 0 or state.game_phase == "GAME_OVER"
    
    if state.game_phase == "ONGOING":
        print(f"Game still ongoing after {max_rounds} rounds in smoke test.")

    assert state is not None # Basic check that the game ran


# --- Regression tests for the card-removal + base-attack fixes -------------

def _one_attack(P1_ID, P2_ID, attacker, target_id):
    """Build a RoundActions with a single P1 attack and no P2 actions."""
    return RoundActions(
        PlayerTurnActions(P1_ID, [AttackAction(P1_ID, attacker.instance_id, target_id)]),
        PlayerTurnActions(P2_ID, []),
    )


def test_attacker_removed_when_killed_by_reflect(initialized_game_state, game_engine, P1_ID, P2_ID):
    # Attacker dies to reflected (forthrightness) damage and must leave the field.
    state = initialized_game_state
    attacker_attrs = create_mock_attributes(strength=2, rigor=100, specificity=100, authenticity=100, civility=0)
    # High-veracity, high-forthrightness target: takes ~no damage, reflects a lot.
    target_attrs = create_mock_attributes(strength=5, veracity=100, forthrightness=100, specificity=100, authenticity=100)
    attacker = create_mock_politician_card(1, "Glasscannon", attributes=attacker_attrs)
    target = create_mock_politician_card(1, "Wall", attributes=target_attrs)
    attacker.owner_id, target.owner_id = P1_ID, P2_ID
    state.players[P1_ID].field = [attacker]
    state.players[P2_ID].field = [target]

    new_state = game_engine.process_round(state, _one_attack(P1_ID, P2_ID, attacker, target.instance_id))

    # Attacker died to reflect and is gone from the field, in its owner's graveyard.
    assert new_state.find_card_on_field(attacker.instance_id) is None
    assert any(c.instance_id == attacker.instance_id for c in new_state.players[P1_ID].graveyard)
    # Target (the wall) survived.
    survivor, _ = new_state.find_card_on_field(target.instance_id)
    assert survivor is not None and survivor.current_hp > 0


def test_base_attack_when_opponent_field_empty(initialized_game_state, game_engine, P1_ID, P2_ID):
    # With no enemy cards, an attack targeting the opponent player hits their base HP.
    state = initialized_game_state
    attrs = create_mock_attributes(strength=3, rigor=2, specificity=100, authenticity=100, civility=0)
    attacker = create_mock_politician_card(1, "Striker", attributes=attrs)
    attacker.owner_id = P1_ID
    state.players[P1_ID].field = [attacker]
    state.players[P2_ID].field = []  # empty opposing field
    start_hp = state.players[P2_ID].health_points

    new_state = game_engine.process_round(state, _one_attack(P1_ID, P2_ID, attacker, P2_ID))

    assert new_state.players[P2_ID].health_points == start_hp - attacker.attack_damage_base
    assert any(e["type"] == "base_attack" for e in new_state.events)


def test_base_attack_falls_back_when_target_card_gone(initialized_game_state, game_engine, P1_ID, P2_ID):
    # Targeting a non-existent card while the opposing field is empty redirects to the base.
    state = initialized_game_state
    attrs = create_mock_attributes(strength=3, rigor=2, specificity=100, authenticity=100, civility=0)
    attacker = create_mock_politician_card(1, "Striker", attributes=attrs)
    attacker.owner_id = P1_ID
    state.players[P1_ID].field = [attacker]
    state.players[P2_ID].field = []
    start_hp = state.players[P2_ID].health_points

    new_state = game_engine.process_round(state, _one_attack(P1_ID, P2_ID, attacker, "no_such_card"))
    assert new_state.players[P2_ID].health_points == start_hp - attacker.attack_damage_base


def test_base_attack_can_win_game(initialized_game_state, game_engine, P1_ID, P2_ID):
    state = initialized_game_state
    attrs = create_mock_attributes(strength=3, rigor=2, specificity=100, authenticity=100, civility=0)
    attacker = create_mock_politician_card(1, "Finisher", attributes=attrs)
    attacker.owner_id = P1_ID
    state.players[P1_ID].field = [attacker]
    state.players[P2_ID].field = []
    state.players[P2_ID].health_points = 3  # less than attack_damage_base (6)

    new_state = game_engine.process_round(state, _one_attack(P1_ID, P2_ID, attacker, P2_ID))

    assert new_state.players[P2_ID].health_points == 0
    assert new_state.game_phase == "GAME_OVER"
    assert new_state.winner == P1_ID
    assert any(e["type"] == "game_over" for e in new_state.events)


def test_end_of_round_sweep_removes_defeated(initialized_game_state, game_engine, P1_ID, P2_ID):
    # A card already at 0 HP that isn't involved in any attack is swept at end of round.
    state = initialized_game_state
    ghost = create_mock_politician_card(1, "Ghost", attributes=create_mock_attributes())
    ghost.owner_id = P1_ID
    ghost.current_hp = 0  # already defeated
    state.players[P1_ID].field = [ghost]
    state.players[P2_ID].field = []

    new_state = game_engine.process_round(
        state, RoundActions(PlayerTurnActions(P1_ID, []), PlayerTurnActions(P2_ID, []))
    )
    assert new_state.find_card_on_field(ghost.instance_id) is None
    assert any(c.instance_id == ghost.instance_id for c in new_state.players[P1_ID].graveyard)


def test_round_emits_structured_events(initialized_game_state, game_engine, P1_ID, P2_ID):
    state = initialized_game_state
    attrs = create_mock_attributes(strength=3, rigor=2, specificity=100, authenticity=100, civility=0)
    attacker = create_mock_politician_card(1, "Striker", attributes=attrs)
    attacker.owner_id = P1_ID
    state.players[P1_ID].field = [attacker]
    state.players[P2_ID].field = []

    new_state = game_engine.process_round(state, _one_attack(P1_ID, P2_ID, attacker, P2_ID))
    types = {e["type"] for e in new_state.events}
    assert "round_start" in types
    assert "attack_order" in types
    assert "base_attack" in types