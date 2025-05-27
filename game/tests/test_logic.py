# --- 4. Mock Data Generation ---
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



# --- 6. Random AI Player ---
class RandomPlayerAI:
    def __init__(self, player_id: str, config: GameConfig):
        self.player_id = player_id
        self.config = config

    def choose_action(self, game_state: GameState) -> Optional[PlayerAction]:
        if game_state.current_player_id != self.player_id or game_state.winner:
            return None # Not my turn or game is over

        player = game_state.get_player(self.player_id)
        opponent = game_state.get_opponent(self.player_id)
        if not player or not opponent: return None


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
    