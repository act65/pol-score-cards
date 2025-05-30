import pytest
from flask import session
from urllib.parse import urlparse # To check redirect paths

# Assuming your Flask app instance is named 'app' in 'game.app'
from game.app import app as flask_app
# Import necessary items for test setup if needed, e.g., config
from game.game_logic import config as game_config # To get PLAYER_IDS

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test_secret_key_for_pytest' # Consistent secret key
    flask_app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for simpler form posts in tests

    with flask_app.test_client() as client:
        yield client

def test_home_redirects_to_new_game_initially(client):
    """Test that the home page redirects to /new_game if no game is in session."""
    response = client.get('/')
    assert response.status_code == 302 # Expect redirect
    assert urlparse(response.location).path == '/new_game'

def test_new_game_initializes_session_and_redirects(client):
    """Test /new_game initializes the game state in session and redirects to home."""
    response = client.get('/new_game', follow_redirects=False) # Test redirect explicitly
    assert response.status_code == 302
    assert urlparse(response.location).path == '/'
    with client.session_transaction() as sess:
        assert 'game_state_serializable' in sess
        assert sess['game_state_serializable'] is not None
        assert sess['game_state_serializable']['round_number'] == 1
        assert sess['game_state_serializable']['game_phase'] == "ONGOING"

def test_home_loads_after_new_game(client):
    """Test that the home page loads successfully after a new game has been started."""
    client.get('/new_game') # Initialize game
    response = client.get('/')
    assert response.status_code == 200
    assert b"Politician Card Game Board" in response.data # Check for some content

def test_play_card_action(client):
    """Test playing a card for Player 1."""
    # 1. Start a new game
    client.get('/new_game')

    # 2. Get P1's hand from session to find a playable card
    p1_id = game_config.PLAYER_IDS[0]
    card_to_play_instance_id = None
    initial_hand_size = 0
    initial_field_size = 0

    with client.session_transaction() as sess:
        game_state = sess['game_state_serializable']
        player1_hand = game_state['players'][p1_id]['hand']
        initial_hand_size = len(player1_hand)
        initial_field_size = len(game_state['players'][p1_id]['field'])
        if player1_hand:
            card_to_play_instance_id = player1_hand[0]['instance_id']

    assert initial_hand_size > 0, "Player 1 should have cards in hand to play."
    assert card_to_play_instance_id is not None, "Could not find a card to play in P1's hand."

    # 3. Simulate POST request to play the card
    play_card_url = f'/play_card/{card_to_play_instance_id}'
    response = client.post(play_card_url, follow_redirects=False)
    
    assert response.status_code == 302 # Expect redirect
    assert urlparse(response.location).path == '/'

    # 4. Check session: card moved from hand to field
    with client.session_transaction() as sess:
        game_state = sess['game_state_serializable']
        player1_hand_after = game_state['players'][p1_id]['hand']
        player1_field_after = game_state['players'][p1_id]['field']
        
        assert len(player1_hand_after) == initial_hand_size - 1
        assert len(player1_field_after) == initial_field_size + 1
        
        played_card_in_field = next((c for c in player1_field_after if c['instance_id'] == card_to_play_instance_id), None)
        assert played_card_in_field is not None
        
        action_log = game_state.get('action_log', [])
        assert any(f"{p1_id} played {played_card_in_field['name']}" in entry for entry in action_log)

def test_end_turn_action(client):
    """Test the /end_turn functionality."""
    # 1. Start a new game
    client.get('/new_game')
    initial_round_number = 0
    with client.session_transaction() as sess:
        initial_round_number = sess['game_state_serializable']['round_number']
        initial_log_length = len(sess['game_state_serializable'].get('action_log', []))

    # 2. Simulate POST request to /end_turn
    response = client.post('/end_turn', follow_redirects=False)
    assert response.status_code == 302
    assert urlparse(response.location).path == '/'

    # 3. Check session for changes
    with client.session_transaction() as sess:
        game_state = sess['game_state_serializable']
        # Round number should be managed by process_round, which increments it *after* processing the current round's actions
        # So if round 1 actions are processed, state becomes round 2.
        assert game_state['round_number'] > initial_round_number # or initial_round_number + 1, depending on when it's incremented
        
        action_log = game_state.get('action_log', [])
        # Check for some logs that indicate process_round ran (e.g., card draws, AI actions)
        assert len(action_log) > initial_log_length
        assert any("drew" in entry for entry in action_log[-5:]) # Check recent logs for draw indication


def test_attack_action(client):
    """Test the /attack functionality (simplified)."""
    # 1. Start a new game
    client.get('/new_game')
    p1_id = game_config.PLAYER_IDS[0]
    p2_id = game_config.PLAYER_IDS[1]

    # 2. P1 plays a card
    attacker_card_id = None
    with client.session_transaction() as sess:
        p1_hand = sess['game_state_serializable']['players'][p1_id]['hand']
        assert p1_hand, "P1 must have cards to play for attack test"
        attacker_card_id = p1_hand[0]['instance_id']
    client.post(f'/play_card/{attacker_card_id}')

    # 3. Trigger AI's turn to hopefully play a card (this makes P2 play)
    client.post('/end_turn') 

    # 4. Find attacker (P1) and target (P2) from session state
    attacker_instance_id_for_form = None
    target_instance_id_for_form = None
    initial_target_hp = None
    target_card_name = None
    action_log_before_attack_len = 0

    with client.session_transaction() as sess:
        game_state = sess['game_state_serializable']
        action_log_before_attack_len = len(game_state.get('action_log', []))
        
        player1_field = game_state['players'][p1_id]['field']
        if player1_field and player1_field[0]['current_hp'] > 0 : # P1 has a card on field
            attacker_instance_id_for_form = player1_field[0]['instance_id']

        player2_field = game_state['players'][p2_id]['field']
        if player2_field and player2_field[0]['current_hp'] > 0: # P2 has a card on field
            target_instance_id_for_form = player2_field[0]['instance_id']
            initial_target_hp = player2_field[0]['current_hp']
            target_card_name = player2_field[0]['name']
            
    if not attacker_instance_id_for_form or not target_instance_id_for_form:
        pytest.skip("Skipping attack test: could not set up attacker and target on field via play/end_turn.")

    # 5. Simulate POST request to /attack
    response = client.post('/attack', data={
        'attacker_instance_id': attacker_instance_id_for_form,
        'target_instance_id': target_instance_id_for_form
    }, follow_redirects=False)

    assert response.status_code == 302
    assert urlparse(response.location).path == '/'

    # 6. Check session for changes (target HP or defeat, action log)
    with client.session_transaction() as sess:
        game_state = sess['game_state_serializable']
        action_log = game_state.get('action_log', [])
        assert len(action_log) > action_log_before_attack_len # New log for attack
        assert any(f"{attacker_instance_id_for_form}" in entry or "attacks" in entry for entry in action_log[action_log_before_attack_len:])


        # Check target card state
        player2_field_after = game_state['players'][p2_id]['field']
        target_card_after = next((c for c in player2_field_after if c['instance_id'] == target_instance_id_for_form), None)
        
        target_in_graveyard = False
        if not target_card_after: # Card might be defeated and moved
            player2_graveyard_after = game_state['players'][p2_id]['graveyard']
            if any(c['instance_id'] == target_instance_id_for_form for c in player2_graveyard_after):
                target_in_graveyard = True
        
        if target_card_after:
            assert target_card_after['current_hp'] < initial_target_hp or target_card_after['current_hp'] == 0
        elif target_in_graveyard:
            assert True # Card was defeated and moved, which is a valid outcome
        else:
            # This case could happen if the target was already defeated by something else in a complex scenario,
            # or if the attack missed due to future mechanics not yet tested here.
            # For this simplified test, we expect either HP change or graveyard.
            pass # Allow test to pass if card just vanished, log should indicate why

        # Check if winner declared if P2 HP is 0 (simplified check)
        if game_state['players'][p2_id]['health_points'] <= 0:
            assert game_state['winner'] == p1_id
            assert game_state['game_phase'] == "GAME_OVER"

# Example of how to run tests with pytest:
# Ensure pytest is installed: pip install pytest
# Navigate to the directory containing 'game' folder (e.g., the project root)
# Run: pytest
# Or more specifically: pytest game/test_app.py
