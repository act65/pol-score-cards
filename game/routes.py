from flask import Blueprint, render_template, session, redirect, url_for, current_app, g, request # Ensure 'request' is imported
from .game_logic import Game, load_master_card_definitions, MASTER_CARD_DEFINITIONS 

game_bp = Blueprint(
    'game', 
    __name__, 
    template_folder='templates', 
    url_prefix='/game'
)

def ensure_master_definitions_loaded():
    # This function tries to load master definitions if they are not already loaded.
    # It's important that MASTER_CARD_DEFINITIONS is populated for the game to work.
    if not MASTER_CARD_DEFINITIONS:
        # current_app.logger.info("MASTER_CARD_DEFINITIONS not loaded, attempting to load now.") # Using print for now
        load_master_card_definitions() # This function handles its own logging for file errors etc.
    
    if not MASTER_CARD_DEFINITIONS:
        # Log an error if still not loaded after attempting.
        if current_app: # Check if current_app context is available
            current_app.logger.error("CRITICAL: MASTER_CARD_DEFINITIONS could not be loaded for game blueprint.")
        else: # Fallback to print if logger or app context is not available (e.g. during setup)
            print("CRITICAL: MASTER_CARD_DEFINITIONS could not be loaded for game blueprint.")


@game_bp.route('/', methods=['GET'])
def game_board():
    ensure_master_definitions_loaded() 
    if not MASTER_CARD_DEFINITIONS:
         return "Error: Critical game data (MASTER_CARD_DEFINITIONS) could not be loaded. Please check server logs.", 500

    game_data_from_session = session.get('game_state')
    game = None

    if game_data_from_session:
        try:
            # When reconstructing, Game.from_dict will use MASTER_CARD_DEFINITIONS
            game = Game.from_dict(game_data_from_session)
            if current_app: current_app.logger.info("Game state reconstructed from session.")
        except Exception as e:
            if current_app: current_app.logger.error(f"Error reconstructing game from session: {e}", exc_info=True)
            else: print(f"Error reconstructing game from session: {e}")
            session.pop('game_state', None) # Clear corrupted/invalid session state

    if game is None: 
        try:
            game = Game() # Creates a new game, relies on MASTER_CARD_DEFINITIONS being loaded
            if current_app: current_app.logger.info("New game instance created.")
        except Exception as e:
            if current_app: current_app.logger.error(f"Error creating new game instance: {e}", exc_info=True)
            else: print(f"Error creating new game instance: {e}")
            return "Error: Could not initialize a new game. Please check server logs.", 500
    
    session['game_state'] = game.to_dict() # Save current game state
    
    return render_template('game/game_board.html', 
                           game=game, 
                           current_player_obj=game.get_player(game.current_player_id),
                           opponent_obj=game.get_player(game.get_opponent_id(game.current_player_id)),
                           player1=game.get_player(Game.PLAYER1_ID), 
                           player2=game.get_player(Game.PLAYER2_ID)
                           )

@game_bp.route('/new', methods=['GET'])
def new_game():
    session.pop('game_state', None)
    # Ensure definitions are loaded before redirecting, as new game creation relies on them.
    ensure_master_definitions_loaded()
    if not MASTER_CARD_DEFINITIONS:
        # This is a critical failure state if definitions can't be loaded for a new game.
        if current_app: current_app.logger.error("CRITICAL: Cannot start new game, MASTER_CARD_DEFINITIONS failed to load.")
        return "Error: Critical game data could not be loaded for new game. Please check server logs.", 500
    return redirect(url_for('game.game_board'))

# --- Added POST routes ---

@game_bp.route('/play_card', methods=['POST'])
def play_card_action():
    ensure_master_definitions_loaded()
    if not MASTER_CARD_DEFINITIONS: 
        if current_app: current_app.logger.error("Play card action denied: MASTER_CARD_DEFINITIONS not loaded.")
        else: print("Play card action denied: MASTER_CARD_DEFINITIONS not loaded.")
        return "Error: Critical game data not loaded. Cannot play card.", 500
    
    game_data = session.get('game_state')
    if not game_data: 
        if current_app: current_app.logger.warn("No game state in session for play_card. Redirecting to new game.")
        else: print("No game state in session for play_card. Redirecting to new game.")
        return redirect(url_for('game.new_game'))

    game = Game.from_dict(game_data)
    
    player_id = game.current_player_id 
    card_instance_id = request.form.get('card_instance_id')

    if not card_instance_id:
        if current_app: current_app.logger.warn(f"Play card attempt by {player_id} without card_instance_id.")
        else: print(f"Play card attempt by {player_id} without card_instance_id.")
        return redirect(url_for('game.game_board'))

    game.player_play_card_action(player_id, card_instance_id)

    session['game_state'] = game.to_dict()
    return redirect(url_for('game.game_board'))

@game_bp.route('/attack', methods=['POST'])
def attack_action():
    ensure_master_definitions_loaded()
    if not MASTER_CARD_DEFINITIONS: 
        if current_app: current_app.logger.error("Attack action denied: MASTER_CARD_DEFINITIONS not loaded.")
        else: print("Attack action denied: MASTER_CARD_DEFINITIONS not loaded.")
        return "Error: Critical game data not loaded. Cannot process attack.", 500

    game_data = session.get('game_state')
    if not game_data: 
        if current_app: current_app.logger.warn("No game state in session for attack. Redirecting to new game.")
        else: print("No game state in session for attack. Redirecting to new game.")
        return redirect(url_for('game.new_game'))

    game = Game.from_dict(game_data)

    attacking_player_id = game.current_player_id 
    attacker_instance_id = request.form.get('attacker_instance_id')
    target_instance_id = request.form.get('target_instance_id')

    if not attacker_instance_id or not target_instance_id:
        if current_app: current_app.logger.warn(f"Attack attempt by {attacking_player_id} with missing attacker/target ID.")
        else: print(f"Attack attempt by {attacking_player_id} with missing attacker/target ID.")
        return redirect(url_for('game.game_board'))

    game.process_card_attack(attacking_player_id, attacker_instance_id, target_instance_id)

    session['game_state'] = game.to_dict()
    return redirect(url_for('game.game_board'))

@game_bp.route('/next_phase', methods=['POST'])
def next_phase_action():
    ensure_master_definitions_loaded()
    if not MASTER_CARD_DEFINITIONS: 
        if current_app: current_app.logger.error("Next phase action denied: MASTER_CARD_DEFINITIONS not loaded.")
        else: print("Next phase action denied: MASTER_CARD_DEFINITIONS not loaded.")
        return "Error: Critical game data not loaded. Cannot advance phase.", 500
    
    game_data = session.get('game_state')
    if not game_data: 
        if current_app: current_app.logger.warn("No game state in session for next_phase. Redirecting to new game.")
        else: print("No game state in session for next_phase. Redirecting to new game.")
        return redirect(url_for('game.new_game'))

    game = Game.from_dict(game_data)
    
    game.advance_game_state()

    session['game_state'] = game.to_dict()
    return redirect(url_for('game.game_board'))
