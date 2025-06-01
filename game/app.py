from flask import Flask, render_template, jsonify, request
import random
import json
import copy
import os
from dataclasses import asdict # For converting dataclasses to dicts for JSON
from typing import Optional, List # For type hinting
import logging

# Import from your game_logic.py
from game_logic import (
    GameConfig, Attributes, PoliticianCard, PlayerState, GameState,
    PlayCardAction, AttackAction, PlayerTurnActions, RoundActions,
    GameEngine, config as game_logic_config # import the global config
)

app = Flask(__name__, template_folder='templates', static_folder='static')

# --- Global Variables ---
all_politician_cards_templates: List[PoliticianCard] = []
game_engine_instance: Optional[GameEngine] = None
current_game_state: Optional[GameState] = None

# Player IDs (P1 is human, P2 is AI)
HUMAN_PLAYER_ID = game_logic_config.PLAYER_IDS[0]
AI_PLAYER_ID = game_logic_config.PLAYER_IDS[1]

# --- Helper Functions ---
def load_politician_cards_templates(filename="politicians.jsonl"):
    """Loads card templates from the JSONL file."""
    cards = []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, filename)
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if line.strip(): # Ensure line is not empty
                    data = json.loads(line)
                    attr_data = data.get("attributes", {})
                    cards.append(PoliticianCard(
                        id=data["id"],
                        name=data["name"],
                        party=data["party"],
                        attributes=Attributes(**attr_data)
                        # Runtime fields like instance_id, hp, etc., are set by __post_init__
                    ))
        app.logger.info(f"Loaded {len(cards)} politician card templates.")
    except FileNotFoundError:
        app.logger.error(f"Error: Card data file '{filename}' not found at '{file_path}'.")
    except json.JSONDecodeError as e:
        app.logger.error(f"Error: Could not decode JSON from '{filename}'. Error: {e}")
    except Exception as e:
        app.logger.error(f"An unexpected error occurred while loading card templates: {e}")
    return cards

# --- AI Logic ---
class RandomPlayerAI:
    def __init__(self, player_id: str):
        self.player_id = player_id

    def generate_actions(self, game_state: GameState) -> PlayerTurnActions:
        ai_actions = []
        if self.player_id not in game_state.players:
            app.logger.warning(f"AI Player {self.player_id} not found in game state. Skipping AI turn.")
            return PlayerTurnActions(player_id=self.player_id, actions=[])
            
        player_state = game_state.players[self.player_id]
        
        # Find opponent
        opponent_id = None
        for pid in game_state.players:
            if pid != self.player_id:
                opponent_id = pid
                break
        
        if not opponent_id or opponent_id not in game_state.players:
            app.logger.warning(f"Opponent for AI Player {self.player_id} not found. Skipping AI attacks.")
            opponent_field_cards = []
        else:
            opponent_field_cards = [
                c for c in game_state.players[opponent_id].field if not c.is_defeated()
            ]

        # 1. Play Cards (try to play one card if possible)
        if player_state.hand and len(player_state.field) < player_state.max_cards_on_field:
            # Play a random card from hand
            card_to_play = random.choice(player_state.hand)
            ai_actions.append(PlayCardAction(player_id=self.player_id, card_instance_id=card_to_play.instance_id))
            app.logger.info(f"AI ({self.player_id}) plans to play {card_to_play.name}")


        # 2. Attack (each card on field attacks a random enemy card if possible)
        for attacker_card in player_state.field:
            if not attacker_card.is_defeated() and opponent_field_cards:
                target_card = random.choice(opponent_field_cards)
                ai_actions.append(AttackAction(
                    player_id=self.player_id,
                    attacker_instance_id=attacker_card.instance_id,
                    target_instance_id=target_card.instance_id
                ))
                app.logger.info(f"AI ({self.player_id}) plans to attack with {attacker_card.name} targeting {target_card.name}")
        
        return PlayerTurnActions(player_id=self.player_id, actions=ai_actions)

ai_player = RandomPlayerAI(AI_PLAYER_ID)

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start_game', methods=['GET'])
def start_game():
    global game_engine_instance, current_game_state, all_politician_cards_templates

    if not all_politician_cards_templates:
        all_politician_cards_templates = load_politician_cards_templates()
        if not all_politician_cards_templates:
             return jsonify({"error": "Failed to load card data. Game cannot start."}), 500

    if len(all_politician_cards_templates) < game_logic_config.INITIAL_HAND_SIZE * 2:
        return jsonify({"error": "Not enough unique card templates to start the game."}), 500

    # Shuffle templates and create deep copies for decks to ensure fresh instances for each game
    shuffled_templates = random.sample(all_politician_cards_templates, len(all_politician_cards_templates))
    
    midpoint = len(shuffled_templates) // 2
    deck1_templates = shuffled_templates[:midpoint]
    deck2_templates = shuffled_templates[midpoint:]

    # Ensure each card in the deck is a new instance
    deck1 = [copy.deepcopy(card_template) for card_template in deck1_templates]
    deck2 = [copy.deepcopy(card_template) for card_template in deck2_templates]
    
    # Re-initialize PoliticianCard instances to get new instance_ids, HP, etc.
    # This happens automatically if PoliticianCard's __post_init__ is correctly called.
    # Deepcopy should preserve the state before __post_init__ if it was already called,
    # but it's safer to ensure fresh objects from base data.
    # The current load_politician_cards_templates creates PoliticianCard objects,
    # so deepcopying them is fine as __post_init__ will run on the copies if they are re-instantiated,
    # or their copied state will be used. The current PoliticianCard __post_init__ generates random instance_id,
    # so deepcopying an already instantiated card will give it a new instance_id if __post_init__ is called again.
    # Let's ensure __post_init__ is effectively run for each card in the deck.
    # The current setup: PoliticianCard objects are created by load_politician_cards_templates.
    # Then they are deepcopied. The __post_init__ of PoliticianCard generates a random instance_id.
    # So, each deepcopy will have its own unique instance_id from its own __post_init__ call. This is fine.

    game_engine_instance = GameEngine(player1_deck=deck1, player2_deck=deck2)
    current_game_state = game_engine_instance.initialize_game_state()
    
    app.logger.info("Game started successfully.")
    # Use asdict to convert dataclasses (and nested ones) to dicts for jsonify
    return jsonify(asdict(current_game_state))


@app.route('/api/submit_round_actions', methods=['POST'])
def submit_round_actions():
    global current_game_state, game_engine_instance

    if not game_engine_instance or not current_game_state:
        app.logger.warning("Submit actions called but game not initialized.")
        return jsonify({"error": "Game not initialized."}), 400
    
    if current_game_state.game_phase == "GAME_OVER":
        app.logger.info("Submit actions called but game is over.")
        return jsonify({"error": "Game is over.", "game_state": asdict(current_game_state)}), 400

    data = request.get_json()
    if not data or 'actions' not in data:
        app.logger.warning("Invalid action submission data.")
        return jsonify({"error": "Invalid submission data."}), 400
        
    human_player_actions_raw = data.get('actions', [])
    parsed_human_actions = []

    for action_data in human_player_actions_raw:
        action_type = action_data.get("type") # Frontend should send this
        if action_type == "PLAY_CARD" and "card_instance_id" in action_data:
            parsed_human_actions.append(PlayCardAction(player_id=HUMAN_PLAYER_ID, card_instance_id=action_data["card_instance_id"]))
        elif action_type == "ATTACK" and "attacker_instance_id" in action_data and "target_instance_id" in action_data:
            parsed_human_actions.append(AttackAction(player_id=HUMAN_PLAYER_ID, 
                                                     attacker_instance_id=action_data["attacker_instance_id"],
                                                     target_instance_id=action_data["target_instance_id"]))
        else:
            app.logger.warning(f"Unknown or malformed action received: {action_data}")

    human_turn_actions = PlayerTurnActions(player_id=HUMAN_PLAYER_ID, actions=parsed_human_actions)
    
    # AI generates its actions based on the current state (before human plays are applied to state for this turn)
    ai_turn_actions = ai_player.generate_actions(current_game_state)

    # The GameEngine expects P1 and P2 actions based on game_logic_config.PLAYER_IDS
    # Since HUMAN_PLAYER_ID is P1 and AI_PLAYER_ID is P2 by convention:
    round_actions = RoundActions(player1_actions=human_turn_actions, player2_actions=ai_turn_actions)

    current_game_state = game_engine_instance.process_round(current_game_state, round_actions)
    
    app.logger.info(f"Round {current_game_state.round_number-1} processed. Current phase: {current_game_state.game_phase}")
    return jsonify(asdict(current_game_state))

# --- Main Execution ---
if __name__ == '__main__':
    # Configure Flask logger
    app.logger.setLevel(logging.INFO)
    # Load card templates at startup
    all_politician_cards_templates = load_politician_cards_templates()
    if not all_politician_cards_templates:
        app.logger.critical("CRITICAL: No card templates loaded. The application might not function correctly.")
    
    app.run(debug=True, host='0.0.0.0')