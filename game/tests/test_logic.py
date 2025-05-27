
# Example Usage (Illustrative - you'll need to create card data)
if __name__ == '__main__':
    # Sample Card Data (replace with your actual card definitions)
    def load_politicians_from_json(filepath="politicians.json") -> List[PoliticianCard]:
        # Create a dummy politicians.json if it doesn't exist for testing
        if not os.path.exists(filepath):
            dummy_data = [
                {"id": "pol001", "name": "Senator Strong", "party": "Alpha", "attributes": {"strength": 3, "divination": 5, "charisma": 10, "rigor": 2, "specificity": 80, "civility": 50, "authenticity": 90, "veracity": 2, "forthrightness": 60}},
                {"id": "pol002", "name": "Governor Quickwit", "party": "Beta", "attributes": {"strength": 2, "divination": 8, "charisma": 20, "rigor": 1, "specificity": 90, "civility": 70, "authenticity": 70, "veracity": 1, "forthrightness": 40}},
                {"id": "pol003", "name": "Mayor Steadfast", "party": "Alpha", "attributes": {"strength": 4, "divination": 3, "charisma": 5, "rigor": 3, "specificity": 70, "civility": 30, "authenticity": 95, "veracity": 3, "forthrightness": 80}},
                {"id": "pol004", "name": "Chancellor Cunning", "party": "Beta", "attributes": {"strength": 1, "divination": 9, "charisma": 15, "rigor": 1, "specificity": 95, "civility": 80, "authenticity": 60, "veracity": 1, "forthrightness": 30}},
            ]
            # Add more cards to make decks larger
            for i in range(5, 16):
                 dummy_data.append({"id": f"pol{i:03d}", "name": f"Rep Generic {i-4}", "party": "Independent", "attributes": {"strength": random.randint(1,3), "divination": random.randint(1,10), "charisma": random.randint(5,25), "rigor": random.randint(1,3), "specificity": random.randint(50,100), "civility": random.randint(20,100), "authenticity": random.randint(50,100), "veracity": random.randint(1,3), "forthrightness": random.randint(20,100)}})

            with open(filepath, 'w') as f:
                json.dump(dummy_data, f, indent=2)

        with open(filepath, 'r') as f:
            data = json.load(f)
        cards = []
        for card_data in data:
            attrs = Attributes(**card_data['attributes'])
            cards.append(PoliticianCard(card_id=card_data['id'], name=card_data['name'], party=card_data['party'], attributes=attrs))
        return cards

    all_cards = load_politicians_from_json()
    if len(all_cards) < 10: # Need enough for two decks of 5 for initial draw
        print("Not enough cards to run example. Need at least 10.")
        exit()

    random.shuffle(all_cards)
    deck1_cards = all_cards[:len(all_cards)//2]
    deck2_cards = all_cards[len(all_cards)//2:]

    config = GameConfig()
    game_engine = GameEngine(config, deck1_cards, deck2_cards)
    game_state = game_engine.initialize_game_state()

    print("\nInitial State:")
    print(game_state.players["P1"])
    print(game_state.players["P2"])

    # --- Example Round 1 ---
    if game_state.game_phase == "ONGOING":
        p1_actions_round1 = []
        p2_actions_round1 = []

        # P1 plays a card (if hand is not empty)
        if game_state.players["P1"].hand:
            card_to_play_p1 = game_state.players["P1"].hand[0]
            p1_actions_round1.append(PlayCardAction(player_id="P1", card_instance_id=card_to_play_p1.instance_id))
        
        # P2 plays a card (if hand is not empty)
        if game_state.players["P2"].hand:
            card_to_play_p2 = game_state.players["P2"].hand[0]
            p2_actions_round1.append(PlayCardAction(player_id="P2", card_instance_id=card_to_play_p2.instance_id))

        round1_player_actions = RoundActions(
            player1_actions=PlayerTurnActions(player_id="P1", actions=p1_actions_round1),
            player2_actions=PlayerTurnActions(player_id="P2", actions=p2_actions_round1)
        )
        game_state = game_engine.process_round(game_state, round1_player_actions)
        
        print("\nState after Round 1 Card Plays:")
        print(game_state.players["P1"])
        print(game_state.players["P2"])

    # --- Example Round 2 (with attacks) ---
    if game_state.game_phase == "ONGOING":
        p1_actions_round2 = []
        p2_actions_round2 = []

        # P1 plays another card
        if len(game_state.players["P1"].hand) > 0:
             p1_actions_round2.append(PlayCardAction(player_id="P1", card_instance_id=game_state.players["P1"].hand[0].instance_id))

        # P2 plays another card
        if len(game_state.players["P2"].hand) > 0:
             p2_actions_round2.append(PlayCardAction(player_id="P2", card_instance_id=game_state.players["P2"].hand[0].instance_id))


        # P1 attacks with first card on field, P2's first card on field (if they exist)
        if game_state.players["P1"].field and game_state.players["P2"].field:
            p1_attacker = game_state.players["P1"].field[0]
            p2_target = game_state.players["P2"].field[0]
            p1_actions_round2.append(AttackAction(player_id="P1", attacker_instance_id=p1_attacker.instance_id, target_instance_id=p2_target.instance_id))

        # P2 attacks with first card on field, P1's first card on field (if they exist)
        if game_state.players["P2"].field and game_state.players["P1"].field:
            # Ensure P1 still has a card if P1 played one and it's the only one
            if game_state.players["P1"].field: # Check if P1 has any card on field
                p2_attacker = game_state.players["P2"].field[0]
                p1_target = game_state.players["P1"].field[0]
                p2_actions_round2.append(AttackAction(player_id="P2", attacker_instance_id=p2_attacker.instance_id, target_instance_id=p1_target.instance_id))


        round2_player_actions = RoundActions(
            player1_actions=PlayerTurnActions(player_id="P1", actions=p1_actions_round2),
            player2_actions=PlayerTurnActions(player_id="P2", actions=p2_actions_round2)
        )
        game_state = game_engine.process_round(game_state, round2_player_actions)

        print("\nState after Round 2:")
        print(game_state.players["P1"])
        print(game_state.players["P2"])
        if game_state.winner:
            print(f"\nGAME OVER! Winner: {game_state.winner}")
        
    print("\nFull Action Log:")
    for entry in game_state.action_log:
        print(entry)

def create_mock_politician_card(card_id_num: int, owner_id: str, config: GameConfig) -> PoliticianCard:
    card_id = f"mock_pol_{card_id_num}"
    name = f"Mock Politician {card_id_num}"
    party = random.choice(["Party Alpha", "Party Beta", "Party Gamma"])
    scores = {
        "Strength": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX),
        "Divination": random.randint(config.MOCK_STAT_MIN, config.MOCK_DIVINATION_MAX), # Higher range for Divination
        "Charisma": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX),
        "Rigor": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX),
        "Specificity": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX),
        "Civility": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX),
        "Veracity": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX),
        "Authenticity": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX),
        "Precision": random.randint(config.MOCK_STAT_MIN, config.MOCK_STAT_MAX), # Used for deflection
    }
    return PoliticianCard(card_id, name, party, scores, owner_id)

def generate_mock_deck(player_id: str, num_cards: int, config: GameConfig) -> List[PoliticianCard]:
    deck = []
    for i in range(num_cards):
        deck.append(create_mock_politician_card(i + 1, player_id, config))
    random.shuffle(deck)
    return deck


class RandomPlayerAI:
    def __init__(self, player_id: str, config: GameConfig):
        self.player_id = player_id
        self.config = config

    def choose_action(self, game_state: GameState) -> PlayerAction:
        player = game_state.get_player(self.player_id)
        opponent = game_state.get_opponent(self.player_id)

        # --- PLAY PHASE ---
        if game_state.game_phase == f"{self.player_id}_PLAY":
            # Try to play a card
            playable_cards_in_hand = [
                card for card in player.hand 
                if len(player.field) < player.max_cards_on_field
            ]
            if playable_cards_in_hand and random.random() < 0.75: # 75% chance to play if possible
                card_to_play = random.choice(playable_cards_in_hand)
                return PlayCardAction(player_id=self.player_id, card_instance_id=card_to_play.instance_id)
            else:
                # End PLAY phase
                return EndPhaseAction(player_id=self.player_id)

        # --- ATTACK PHASE ---
        elif game_state.game_phase == f"{self.player_id}_ATTACK_ACTION":
            # Current card to act is determined by game_state.attack_action_queue[game_state.current_attacker_in_queue_idx]
            if game_state.current_attacker_in_queue_idx >= len(game_state.attack_action_queue):
                # Should have been handled by _process_next_in_attack_queue to transition phase
                return EndPhaseAction(player_id=self.player_id) # Safety end phase

            attacker_instance_id, attacker_owner_id = game_state.attack_action_queue[game_state.current_attacker_in_queue_idx]
            
            if attacker_owner_id != self.player_id:
                 # This should not happen if _process_next_in_attack_queue works correctly
                 print(f"AI Error: ATTACK_ACTION phase, but designated attacker {attacker_instance_id} is not mine.")
                 return EndPhaseAction(player_id=self.player_id) # Try to recover

            attacker_card_info = game_state.find_card_on_field(attacker_instance_id)
            if not attacker_card_info or not attacker_card_info[0].can_attack_this_turn:
                # Card is gone or cannot attack, AI should pass this card's turn
                return EndPhaseAction(player_id=self.player_id) 
            
            # Find a target on opponent's field
            if opponent.field:
                if random.random() < 0.85: # 85% chance to attack if possible
                    target_card = random.choice(opponent.field)
                    return AttackAction(player_id=self.player_id, 
                                        attacker_instance_id=attacker_instance_id, 
                                        target_instance_id=target_card.instance_id)
                else: # Chance to not attack with this card
                    return EndPhaseAction(player_id=self.player_id)
            else:
                # No targets, must end this card's action (effectively passing)
                return EndPhaseAction(player_id=self.player_id)
        
        return None # No action decided (e.g. wrong phase for AI logic)




# --- 7. Main Game Loop Example ---
if __name__ == "__main__":
    config = GameConfig()
    engine = GameEngine(config)
    
    current_game_state = engine.initialize_game_state()
    print(current_game_state.players[config.PLAYER_IDS[0]])
    print(current_game_state.players[config.PLAYER_IDS[1]])

    ai_players = {
        config.PLAYER_IDS[0]: RandomPlayerAI(config.PLAYER_IDS[0], config),
        config.PLAYER_IDS[1]: RandomPlayerAI(config.PLAYER_IDS[1], config)
    }

    max_turns = 100 # Prevent infinite loops
    for turn_count in range(max_turns):
        if current_game_state.winner:
            print(f"\n--- GAME OVER ---")
            print(f"Winner: {current_game_state.winner} after {turn_count} actions.")
            break

        active_player_id = current_game_state.current_player_id
        ai = ai_players[active_player_id]
        
        print(f"\n--- Turn {current_game_state.round_number}, Player: {active_player_id}, Phase: {current_game_state.game_phase} ---")
        # print(current_game_state.players[config.PLAYER_IDS[0]]) # Player 1 state
        # print(current_game_state.players[config.PLAYER_IDS[1]]) # Player 2 state


        action = ai.choose_action(current_game_state)

        if action:
            print(f"Action chosen by {active_player_id}: {action}")
            current_game_state = engine.game_step(current_game_state, action)
        else:
            # This might happen if AI logic doesn't cover a state, or it's genuinely no action (e.g. waiting)
            # Forcing an EndPhaseAction if AI returns None and it's their turn to act might be needed
            # depending on strictness. The current AI should always return an action if it's its turn.
            print(f"No action chosen by {active_player_id} (or not their turn/phase to provide one). This might be an issue or waiting.")
            # If stuck, one might auto-EndPhase:
            if current_game_state.current_player_id == active_player_id and not current_game_state.game_phase.endswith("_PREPARE"):
                 print("AI returned no action, forcing EndPhaseAction to attempt to progress.")
                 action = EndPhaseAction(player_id=active_player_id)
                 current_game_state = engine.game_step(current_game_state, action)


        # Simple way to see field state
        p1_field_str = [c.name for c in current_game_state.players[config.PLAYER_IDS[0]].field]
        p2_field_str = [c.name for c in current_game_state.players[config.PLAYER_IDS[1]].field]
        print(f"P1 Field: {p1_field_str}, P2 Field: {p2_field_str}")


        if turn_count == max_turns -1:
            print("\n--- Max turns reached ---")
            current_game_state.log("Max turns reached, game ends in a draw or by current state.")

    print("\nFinal Game Log:")
    for entry in current_game_state.game_log:
        print(entry)
    