from flask import Flask, render_template, redirect, url_for, session, request
import os # For secret key generation
from dataclasses import asdict # To convert dataclasses to dicts
import math # For civility damage calculation

# Assuming game_logic.py and test_logic.py are in the same directory or accessible in PYTHONPATH
from game_logic import GameEngine, GameState, PlayerState, PoliticianCard, config, Attributes, AttackAction, PlayerTurnActions, RoundActions
from test_logic import generate_mock_deck, generate_random_player_actions # Added generate_random_player_actions

app = Flask(__name__)
app.secret_key = os.urandom(24) # Necessary for session management

def card_to_dict(card):
    if isinstance(card, PoliticianCard):
        return asdict(card)
    return card

def player_state_to_dict(player_state):
    if isinstance(player_state, PlayerState):
        data = asdict(player_state)
        data['deck'] = [card_to_dict(c) for c in player_state.deck]
        data['hand'] = [card_to_dict(c) for c in player_state.hand]
        data['field'] = [card_to_dict(c) for c in player_state.field]
        data['graveyard'] = [card_to_dict(c) for c in player_state.graveyard]
        return data
    return player_state

def game_state_to_session_serializable(game_state: GameState) -> dict:
    """Converts GameState to a JSON-serializable dictionary for session storage."""
    if not isinstance(game_state, GameState):
        return game_state # Or raise error

    serializable_state = {
        'players': {pid: player_state_to_dict(pstate) for pid, pstate in game_state.players.items()},
        'round_number': game_state.round_number,
        'game_phase': game_state.game_phase,
        'winner': game_state.winner,
        'action_log': game_state.action_log # Assuming action_log is already serializable (list of strings)
    }
    return serializable_state

# Placeholder for reconstructing game state from session if needed, though for now we pass dicts to template
# def game_state_from_session(session_data: dict) -> GameState:
#     # This would be more complex, involving reconstructing PoliticianCard and PlayerState objects
#     # For now, we might just pass the dictionary representation to the template
#     return session_data

def card_from_dict(card_dict: dict) -> PoliticianCard:
    if not card_dict: return None
    # Create Attributes object
    attrs = Attributes(**card_dict['attributes'])
    # Create card, but instance_id, max_hp, etc., were set by __post_init__ or gameplay
    # We need to restore them as they were.
    card = PoliticianCard(
        id=card_dict['id'],
        name=card_dict['name'],
        party=card_dict['party'],
        attributes=attrs,
        owner_id=card_dict.get('owner_id') 
    )
    # Restore dynamic/gameplay-affected attributes
    card.instance_id = card_dict['instance_id']
    card.max_hp = card_dict['max_hp']
    card.current_hp = card_dict['current_hp']
    card.attack_damage_base = card_dict['attack_damage_base']
    card.defense_base = card_dict['defense_base']
    return card

def player_state_from_dict(player_dict: dict) -> PlayerState:
    if not player_dict: return None
    
    # Create PlayerState without initializing deck/hand/field/graveyard yet
    player_state = PlayerState(id=player_dict['id']) # health_points and max_cards_on_field will be set by __post_init__ or restored
    
    # Restore lists of cards
    player_state.deck = [card_from_dict(c) for c in player_dict.get('deck', [])]
    player_state.hand = [card_from_dict(c) for c in player_dict.get('hand', [])]
    player_state.field = [card_from_dict(c) for c in player_dict.get('field', [])]
    player_state.graveyard = [card_from_dict(c) for c in player_dict.get('graveyard', [])]
    
    # Restore other attributes
    player_state.health_points = player_dict['health_points']
    player_state.max_cards_on_field = player_dict['max_cards_on_field'] # This is important
    
    return player_state

# game_state_from_session can be more involved if we need full GameState object
# For playing a card, we primarily need the specific player's state.

def game_state_from_dict(serializable_state: dict) -> GameState:
    players = {}
    for p_id, p_data in serializable_state['players'].items():
        players[p_id] = player_state_from_dict(p_data) # Uses existing helper

    # Ensure action_log is present and is a list
    action_log = list(serializable_state.get('action_log', []))

    return GameState(
        players=players,
        round_number=serializable_state['round_number'],
        game_phase=serializable_state['game_phase'],
        winner=serializable_state.get('winner'), # Use .get for optional fields
        action_log=action_log
    )

@app.route('/')
def home():
    game_data_for_template = session.get('game_state_serializable')
    if not game_data_for_template:
        return redirect(url_for('new_game'))
    
    return render_template('game_board.html', 
                           game_data=game_data_for_template, 
                           p1_id=config.PLAYER_IDS[0], 
                           p2_id=config.PLAYER_IDS[1])

@app.route('/attack', methods=['POST'])
def attack():
    game_state_serializable = session.get('game_state_serializable')
    if not game_state_serializable:
        return redirect(url_for('new_game'))

    p1_id = config.PLAYER_IDS[0]
    p2_id = config.PLAYER_IDS[1]

    attacker_instance_id = request.form.get('attacker_instance_id')
    target_instance_id = request.form.get('target_instance_id')

    if not attacker_instance_id or not target_instance_id:
        # Should set a flash message here for user feedback
        return redirect(url_for('home'))

    # Reconstruct P1 and P2 states
    p1_data_dict = game_state_serializable['players'].get(p1_id, {})
    p2_data_dict = game_state_serializable['players'].get(p2_id, {})
    player1_state = player_state_from_dict(p1_data_dict)
    player2_state = player_state_from_dict(p2_data_dict)

    attacker_card_obj = next((c for c in player1_state.field if c.instance_id == attacker_instance_id), None)
    target_card_obj = next((c for c in player2_state.field if c.instance_id == target_instance_id), None)

    log_entry_prefix = f"R{game_state_serializable['round_number']}: "
    action_log = game_state_serializable.get('action_log', [])

    if attacker_card_obj and target_card_obj and not attacker_card_obj.is_defeated():
        action_log.append(f"{log_entry_prefix}{player1_state.id}'s {attacker_card_obj.name} attacks {player2_state.id}'s {target_card_obj.name}.")

        # Simplified damage calculation (no specificity, forthrightness, authenticity checks here)
        damage = max(0, attacker_card_obj.attack_damage_base - target_card_obj.defense_base)
        target_card_obj.take_damage(damage)
        action_log.append(f"{log_entry_prefix}  {attacker_card_obj.name} deals {damage} damage to {target_card_obj.name}. ({target_card_obj.name} HP: {target_card_obj.current_hp}/{target_card_obj.max_hp})")

        # Civility pierce damage
        if config.CIVILITY_PIERCE_DIVISOR > 0:
            civility_damage = math.floor(attacker_card_obj.attributes.civility / config.CIVILITY_PIERCE_DIVISOR)
            if civility_damage > 0:
                player2_state.take_direct_damage(civility_damage) # This updates player2_state.health_points
                action_log.append(f"{log_entry_prefix}  Civility: {attacker_card_obj.name} deals {civility_damage} direct damage to Player {player2_state.id} (HP: {player2_state.health_points}).")

        if target_card_obj.is_defeated():
            player2_state.remove_card_from_field(target_card_obj.instance_id, to_graveyard=True) # This updates field, graveyard, and max_cards_on_field for player2_state
            action_log.append(f"{log_entry_prefix}  {target_card_obj.name} has been defeated and moved to {player2_state.id}'s graveyard.")
        
        # Check for game over due to player health (from civility damage)
        # This is a simplified check; full game over logic is in GameEngine._check_game_over
        if player2_state.health_points <= 0:
            game_state_serializable['winner'] = player1_state.id
            game_state_serializable['game_phase'] = "GAME_OVER"
            action_log.append(f"{log_entry_prefix}Player {player2_state.id} has been defeated! Winner: {player1_state.id}")

        # Update the serializable state
        game_state_serializable['players'][p1_id] = player_state_to_dict(player1_state) # P1 state might not change, but good practice
        game_state_serializable['players'][p2_id] = player_state_to_dict(player2_state)
        game_state_serializable['action_log'] = action_log
        session['game_state_serializable'] = game_state_serializable

    else:
        if not attacker_card_obj:
            action_log.append(f"{log_entry_prefix}Attack failed: Attacker card {attacker_instance_id} not found for {p1_id}.")
        elif attacker_card_obj.is_defeated():
            action_log.append(f"{log_entry_prefix}Attack failed: Attacker card {attacker_card_obj.name} is already defeated.")
        elif not target_card_obj:
            action_log.append(f"{log_entry_prefix}Attack failed: Target card {target_instance_id} not found for {p2_id}.")
        game_state_serializable['action_log'] = action_log
        session['game_state_serializable'] = game_state_serializable
        
    return redirect(url_for('home'))

@app.route('/end_turn', methods=['POST'])
def end_turn():
    game_state_serializable = session.get('game_state_serializable')
    if not game_state_serializable:
        return redirect(url_for('new_game'))

    # Reconstruct the full GameState object
    current_game_state_object = game_state_from_dict(game_state_serializable)

    if current_game_state_object.game_phase != "ONGOING": # Don't process if game is over
        return redirect(url_for('home'))

    p1_id = config.PLAYER_IDS[0]
    p2_id = config.PLAYER_IDS[1]

    # Player 1's actions for this round are considered done (atomically handled by other routes)
    p1_player_actions = PlayerTurnActions(player_id=p1_id, actions=[])

    # Generate Player 2's (AI) actions
    # Ensure generate_random_player_actions gets a fully fleshed out GameState
    p2_player_actions = generate_random_player_actions(p2_id, current_game_state_object)
    
    current_round_actions = RoundActions(player1_actions=p1_player_actions, player2_actions=p2_player_actions)

    # Instantiate GameEngine
    # Pass current decks from the reconstructed game state to the engine
    engine = GameEngine(
        player1_deck=list(current_game_state_object.players[p1_id].deck), # Pass copies
        player2_deck=list(current_game_state_object.players[p2_id].deck)
    )
    
    # Process the round
    # The GameState object (current_game_state_object) is modified in place by process_round
    updated_game_state_object = engine.process_round(current_game_state_object, current_round_actions)

    # Serialize the updated game state back to session
    session['game_state_serializable'] = game_state_to_session_serializable(updated_game_state_object)

    return redirect(url_for('home'))

@app.route('/play_card/<string:card_instance_id_str>', methods=['POST'])
def play_card(card_instance_id_str: str):
    game_state_serializable = session.get('game_state_serializable')
    if not game_state_serializable:
        return redirect(url_for('new_game'))

    p1_id = config.PLAYER_IDS[0]
    
    # Reconstruct Player 1's state
    p1_data_dict = game_state_serializable['players'].get(p1_id)
    if not p1_data_dict:
        # Should not happen if game is initialized properly
        return redirect(url_for('home')) 
        
    player1_state = player_state_from_dict(p1_data_dict)
    
    card_played_successfully = False
    played_card_name = "Unknown Card"

    # Find the card name for logging before attempting to play (it moves from hand)
    card_to_log = next((c for c in player1_state.hand if c.instance_id == card_instance_id_str), None)
    if card_to_log:
        played_card_name = card_to_log.name

    if player1_state.play_card_to_field(card_instance_id_str):
        card_played_successfully = True
        # The play_card_to_field method already updated player1_state.hand, player1_state.field,
        # and player1_state.max_cards_on_field via update_max_field_cards().
        
        # Update the serializable state for P1
        game_state_serializable['players'][p1_id] = player_state_to_dict(player1_state)
        
        # Add to game log
        log_message = f"R{game_state_serializable['round_number']}: {p1_id} played {played_card_name}."
        if 'action_log' not in game_state_serializable:
            game_state_serializable['action_log'] = []
        game_state_serializable['action_log'].append(log_message)
        
        session['game_state_serializable'] = game_state_serializable
    else:
        # Optionally, add a message to Flask's flash messaging system if card play failed
        # For now, just redirect. The state on the board won't change.
        log_message = f"R{game_state_serializable['round_number']}: {p1_id} failed to play {played_card_name} (Instance ID: {card_instance_id_str}). Field likely full or card not found."
        if 'action_log' not in game_state_serializable:
            game_state_serializable['action_log'] = []
        game_state_serializable['action_log'].append(log_message)
        session['game_state_serializable'] = game_state_serializable


    return redirect(url_for('home'))

@app.route('/new_game')
def new_game():
    # Generate decks
    deck1 = generate_mock_deck(10, name_prefix=f"{config.PLAYER_IDS[0]}-Card")
    deck2 = generate_mock_deck(10, name_prefix=f"{config.PLAYER_IDS[1]}-Card")

    # Create game engine and initialize state
    game_engine = GameEngine(player1_deck=deck1, player2_deck=deck2)
    current_game_state = game_engine.initialize_game_state()

    # Store serializable version in session
    session['game_state_serializable'] = game_state_to_session_serializable(current_game_state)
    
    # For debugging or direct use if not redirecting immediately
    # game_data_for_template = session['game_state_serializable']

    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
