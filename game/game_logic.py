import random
import math
import json
import os
import copy
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Tuple, Any

# --- 1. Game Configuration ---
@dataclass
class GameConfig:
    MAX_HP_CARD: int = 250
    INITIAL_HAND_SIZE: int = 5
    CARDS_DRAWN_PER_ROUND_START: int = 1 # When a player starts their PLAY phase
    BASE_FIELD_SLOTS: int = 2
    CHARISMA_PER_EXTRA_SLOT: int = 100
    PLAYER_IDS: Tuple[str, str] = ("P1", "P2")

    # For mock card generation
    MOCK_STAT_MIN: int = 30
    MOCK_STAT_MAX: int = 90
    MOCK_DIVINATION_MAX: int = 100 # Divination is important for turn order

# --- 2. Core Data Structures ---

class PoliticianCard:
    def __init__(self, card_id: str, name: str, party: str, scores: Dict[str, int], owner_id: Optional[str] = None):
        self.id: str = card_id
        self.name: str = name
        self.party: str = party
        self.scores: Dict[str, int] = scores
        
        self.max_hp: int = GameConfig().MAX_HP_CARD # Default, can be overridden by config if needed
        self.current_hp: int = self.max_hp
        
        # Unique identifier for this specific instance of the card
        self.instance_id: str = f"{self.id}_{random.randint(10000, 99999)}"
        self.owner_id: Optional[str] = owner_id
        self.can_attack_this_turn: bool = True # Reset at start of owner's attack phase

    def __str__(self):
        return f"{self.name} ({self.party}) [{self.instance_id}] (Owner: {self.owner_id}) - HP: {self.current_hp}/{self.max_hp} - Div: {self.scores.get('Divination',0)}"

    def calculate_attack_power(self) -> float: # Target card removed as Civility/Precision are not part of this base calc
        s = self.scores.get("Strength", 0)
        r = self.scores.get("Rigor", 0)
        sp = self.scores.get("Specificity", 0)
        
        base_attack = s
        attack_roll = random.randint(1, 10)
        specificity_floor = math.floor(sp / 10)
        effective_attack_roll = max(attack_roll, specificity_floor)
        rigor_bonus = effective_attack_roll * (r / 10)
        
        total_attack_power = base_attack + rigor_bonus
        return total_attack_power

    def calculate_defense_power(self) -> float:
        s = self.scores.get("Strength", 0)
        v = self.scores.get("Veracity", 0)
        a = self.scores.get("Authenticity", 0) # Rules.md said Devotion, code used Authenticity
        
        base_defense = s
        defense_roll = random.randint(1, 10)
        authenticity_floor = math.floor(a / 10)
        effective_defense_roll = max(defense_roll, authenticity_floor)
        veracity_bonus = effective_defense_roll * (v / 10)
        
        total_defense_power = base_defense + veracity_bonus
        return total_defense_power

    def take_damage(self, amount: int):
        effective_amount = max(0, amount)
        self.current_hp -= effective_amount
        self.current_hp = max(0, self.current_hp)

    def is_defeated(self) -> bool:
        return self.current_hp <= 0

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "name": self.name, "party": self.party,
            "scores": self.scores, "max_hp": self.max_hp, "current_hp": self.current_hp,
            "instance_id": self.instance_id, "owner_id": self.owner_id,
            "can_attack_this_turn": self.can_attack_this_turn
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'PoliticianCard':
        # This simplified from_dict assumes scores are directly provided.
        # For a full system, you'd look up base card data by 'id' from a master list.
        card = cls(data["id"], data["name"], data["party"], data["scores"], data.get("owner_id"))
        card.max_hp = data["max_hp"]
        card.current_hp = data["current_hp"]
        card.instance_id = data["instance_id"]
        card.can_attack_this_turn = data.get("can_attack_this_turn", True)
        return card

    def clone(self) -> 'PoliticianCard':
        # Create a new instance and copy state. Scores dict is copied.
        cloned_card = PoliticianCard(self.id, self.name, self.party, self.scores.copy(), self.owner_id)
        cloned_card.max_hp = self.max_hp
        cloned_card.current_hp = self.current_hp
        cloned_card.instance_id = self.instance_id # Instance ID should be preserved for tracking
        cloned_card.can_attack_this_turn = self.can_attack_this_turn
        return cloned_card

@dataclass
class Player:
    id: str
    deck: List[PoliticianCard] = field(default_factory=list)
    hand: List[PoliticianCard] = field(default_factory=list)
    field: List[PoliticianCard] = field(default_factory=list)
    max_cards_on_field: int = 2 # Base, will be updated by Charisma

    def __str__(self):
        hand_names = [c.name for c in self.hand]
        field_names = [f"{c.name}(HP:{c.current_hp}, Atk:{c.can_attack_this_turn})" for c in self.field]
        return (f"Player {self.id}\n"
                f"  Hand ({len(self.hand)}): {hand_names}\n"
                f"  Field ({len(self.field)}/{self.max_cards_on_field}): {field_names}\n"
                f"  Deck: {len(self.deck)} cards")

    def update_max_field_cards(self, config: GameConfig):
        total_charisma = sum(c.scores.get("Charisma", 0) for c in self.field)
        self.max_cards_on_field = config.BASE_FIELD_SLOTS + math.floor(total_charisma / config.CHARISMA_PER_EXTRA_SLOT)

    def draw_cards(self, num: int = 1) -> List[PoliticianCard]:
        drawn_cards = []
        for _ in range(num):
            if self.deck:
                card = self.deck.pop(0)
                card.owner_id = self.id # Ensure owner_id is set
                self.hand.append(card)
                drawn_cards.append(card)
            else:
                break # No cards left to draw
        return drawn_cards

    def play_card_to_field(self, card_instance_id: str, config: GameConfig) -> Optional[PoliticianCard]:
        card_to_play = next((c for c in self.hand if c.instance_id == card_instance_id), None)
        if card_to_play and len(self.field) < self.max_cards_on_field:
            self.hand.remove(card_to_play)
            self.field.append(card_to_play)
            self.update_max_field_cards(config)
            return card_to_play
        return None

    def remove_card_from_field(self, card_instance_id: str, config: GameConfig) -> Optional[PoliticianCard]:
        card_to_remove = next((c for c in self.field if c.instance_id == card_instance_id), None)
        if card_to_remove:
            self.field.remove(card_to_remove)
            # Potentially move to a graveyard if implementing that
            self.update_max_field_cards(config)
            return card_to_remove
        return None
    
    def reset_field_card_attack_status(self):
        for card in self.field:
            card.can_attack_this_turn = True

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "deck": [c.to_dict() for c in self.deck],
            "hand": [c.to_dict() for c in self.hand],
            "field": [c.to_dict() for c in self.field],
            "max_cards_on_field": self.max_cards_on_field
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Player':
        player = cls(id=data["id"])
        player.deck = [PoliticianCard.from_dict(cd) for cd in data["deck"]]
        player.hand = [PoliticianCard.from_dict(cd) for cd in data["hand"]]
        player.field = [PoliticianCard.from_dict(cd) for cd in data["field"]]
        player.max_cards_on_field = data["max_cards_on_field"]
        return player

    def clone(self) -> 'Player':
        cloned_player = Player(id=self.id)
        cloned_player.deck = [card.clone() for card in self.deck]
        cloned_player.hand = [card.clone() for card in self.hand]
        cloned_player.field = [card.clone() for card in self.field]
        cloned_player.max_cards_on_field = self.max_cards_on_field
        return cloned_player

@dataclass
class GameState:
    players: Dict[str, Player]
    current_player_id: str
    game_phase: str  # e.g., "P1_PLAY", "P1_ATTACK_SELECT_CARD", "P1_ATTACK_SELECT_TARGET", "P2_PLAY", ...
    game_log: List[str] = field(default_factory=list)
    
    # For Divination-based attack ordering
    # Stores (card_instance_id, owner_id) tuples, sorted by Divination
    attack_action_queue: List[Tuple[str, str]] = field(default_factory=list) 
    current_attacker_in_queue_idx: int = 0 # Index into attack_action_queue

    round_number: int = 1
    winner: Optional[str] = None

    def get_player(self, player_id: str) -> Optional[Player]:
        return self.players.get(player_id)

    def get_opponent(self, player_id: str) -> Optional[Player]:
        for pid, player in self.players.items():
            if pid != player_id:
                return player
        return None
    
    def get_opponent_id(self, player_id: str) -> Optional[str]:
        for pid in self.players.keys():
            if pid != player_id:
                return pid
        return None

    def find_card_on_field(self, instance_id: str) -> Optional[Tuple[PoliticianCard, Player]]:
        for player in self.players.values():
            for card in player.field:
                if card.instance_id == instance_id:
                    return card, player
        return None
        
    def find_card_anywhere(self, instance_id: str) -> Optional[Tuple[PoliticianCard, Player, str]]: # card, player, location
        for player in self.players.values():
            for card_list, loc_name in [(player.field, "field"), (player.hand, "hand"), (player.deck, "deck")]:
                for card in card_list:
                    if card.instance_id == instance_id:
                        return card, player, loc_name
        return None

    def log(self, message: str):
        self.game_log.append(message)
        print(f"[GameLog] {message}") # Also print for immediate feedback

    def clone(self) -> 'GameState':
        cloned_players = {pid: p.clone() for pid, p in self.players.items()}
        # attack_action_queue contains tuples of basic types, shallow copy is fine
        cloned_state = GameState(
            players=cloned_players,
            current_player_id=self.current_player_id,
            game_phase=self.game_phase,
            game_log=list(self.game_log), # Shallow copy of list of strings
            attack_action_queue=list(self.attack_action_queue),
            current_attacker_in_queue_idx=self.current_attacker_in_queue_idx,
            round_number=self.round_number,
            winner=self.winner
        )
        return cloned_state

    def to_dict(self) -> Dict:
        return {
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "current_player_id": self.current_player_id,
            "game_phase": self.game_phase,
            "game_log": self.game_log,
            "attack_action_queue": self.attack_action_queue,
            "current_attacker_in_queue_idx": self.current_attacker_in_queue_idx,
            "round_number": self.round_number,
            "winner": self.winner,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'GameState':
        players = {pid: Player.from_dict(pdata) for pid, pdata in data["players"].items()}
        return cls(
            players=players,
            current_player_id=data["current_player_id"],
            game_phase=data["game_phase"],
            game_log=data["game_log"],
            attack_action_queue=data["attack_action_queue"],
            current_attacker_in_queue_idx=data["current_attacker_in_queue_idx"],
            round_number=data["round_number"],
            winner=data.get("winner")
        )

# --- 3. Player Actions ---
@dataclass
class PlayerAction:
    player_id: str # The player initiating the action

@dataclass
class PlayCardAction(PlayerAction):
    card_instance_id: str # From hand to field

@dataclass
class AttackAction(PlayerAction):
    attacker_instance_id: str
    target_instance_id: str

@dataclass
class EndPhaseAction(PlayerAction): # To end PLAY phase or ATTACK sub-turn
    pass

# --- 5. Game Logic Engine ---
class GameEngine:
    def __init__(self, config: GameConfig, player1, player2):
        self.config = config
        player1.update_max_field_cards(self.config)
        player2.update_max_field_cards(self.config)

        self.player1 = player1
        self.player2 = player2


    def initialize_game_state(self) -> GameState:
        p1_id, p2_id = self.config.PLAYER_IDS
        
        players = {p1_id: self.player1, p2_id: self.player2}

        initial_state = GameState(
            players=players,
            current_player_id=p1_id,
            game_phase=f"{p1_id}_PLAY" # P1 starts with PLAY phase
        )
        initial_state.log("Game initialized.")

        # Initial draw for both players
        for p_id in players:
            drawn = initial_state.players[p_id].draw_cards(self.config.INITIAL_HAND_SIZE)
            initial_state.log(f"{p_id} drew {len(drawn)} cards.")
        
        # P1 draws one more card for starting the game (or adjust rule as needed)
        # Current rule: CARDS_DRAWN_PER_ROUND_START is when player *starts their PLAY phase*
        # So P1 already gets this effectively. If P2 starts, they'd draw.
        # Let's make it explicit: first player draws at start of their first play phase.
        drawn_p1_start = initial_state.players[p1_id].draw_cards(self.config.CARDS_DRAWN_PER_ROUND_START)
        initial_state.log(f"{p1_id} draws {len(drawn_p1_start)} card(s) for starting their turn.")

        return initial_state

    def _check_game_over(self, state: GameState) -> Optional[str]:
        for p_id, player in state.players.items():
            # Player loses if they have no cards on field, in hand, AND in deck
            # (and it's their turn and they can't do anything - more complex condition)
            # Simplified: if a player cannot make any move or has no cards left.
            # A more common win condition: opponent has no cards on field and cannot play any.
            # Or, opponent's "hero" (not present here) is defeated.
            # For now, let's use: if a player has no cards on field AND no cards in hand to play.
            
            opponent_id = state.get_opponent_id(p_id)
            opponent = state.get_opponent(p_id)

            if not player.field and not player.hand and not player.deck:
                state.log(f"{p_id} has no cards left anywhere. {opponent_id} wins!")
                return opponent_id

            # If a player has no cards on field, and it's their turn to play but has no cards in hand
            if state.current_player_id == p_id and state.game_phase.endswith("_PLAY"):
                if not player.field and not player.hand:
                     state.log(f"{p_id} has no cards on field or in hand during PLAY phase. {opponent_id} wins!")
                     return opponent_id
            
            # If a player has no cards on field during their ATTACK phase (cannot attack)
            if state.current_player_id == p_id and state.game_phase.endswith("_ATTACK_ACTION"):
                 if not player.field:
                    state.log(f"{p_id} has no cards on field to attack with. {opponent_id} wins!")
                    return opponent_id
        return None

    def _transition_to_attack_phase(self, state: GameState, player_id: str):
        state.game_phase = f"{player_id}_ATTACK_PREPARE"
        state.log(f"Transitioning to {state.game_phase} for {player_id}.")
        
        # Reset attack status for current player's cards
        current_player_obj = state.get_player(player_id)
        if current_player_obj:
            current_player_obj.reset_field_card_attack_status()

        # Determine attack order based on Divination for ALL cards on field
        all_field_cards: List[Tuple[PoliticianCard, Player]] = []
        for p_obj in state.players.values():
            for card in p_obj.field:
                all_field_cards.append((card, p_obj))
        
        # Sort by Divination (higher first), then by a tie-breaker (e.g. original player turn order, or random)
        all_field_cards.sort(key=lambda x: x[0].scores.get("Divination", 0), reverse=True)
        
        state.attack_action_queue = [(card.instance_id, p_obj.id) for card, p_obj in all_field_cards]
        state.current_attacker_in_queue_idx = 0
        state.log(f"Attack action queue determined (Divination sort): {[cid for cid, _ in state.attack_action_queue]}")
        
        # Move to the actual attack action sub-phase
        self._process_next_in_attack_queue(state)


    def _process_next_in_attack_queue(self, state: GameState):
        player_id = state.current_player_id # Player whose turn it is overall

        if state.current_attacker_in_queue_idx >= len(state.attack_action_queue):
            # All cards in queue have had a chance to act or been skipped
            state.log(f"Attack queue exhausted for {player_id}'s turn.")
            self._end_attack_phase(state, player_id)
            return

        card_instance_id, card_owner_id = state.attack_action_queue[state.current_attacker_in_queue_idx]
        
        card_info = state.find_card_on_field(card_instance_id)
        if not card_info: # Card might have been defeated
            state.log(f"Card {card_instance_id} from queue no longer on field. Skipping.")
            state.current_attacker_in_queue_idx += 1
            self._process_next_in_attack_queue(state) # Recursive call for next
            return

        acting_card, _ = card_info

        if card_owner_id == player_id and acting_card.can_attack_this_turn:
            # This card belongs to the current player and can act
            state.game_phase = f"{player_id}_ATTACK_ACTION" # Player needs to provide AttackAction
            state.log(f"{player_id}'s turn to act with {acting_card.name} ({acting_card.instance_id}). Waiting for AttackAction or EndPhaseAction.")
        else:
            # Card belongs to opponent, or has already acted, or cannot act. Skip.
            state.log(f"Skipping {acting_card.name} ({acting_card.instance_id}) in attack queue (Owner: {card_owner_id}, CanAttack: {acting_card.can_attack_this_turn}).")
            state.current_attacker_in_queue_idx += 1
            self._process_next_in_attack_queue(state) # Recursive call for next

    def _end_attack_phase(self, state: GameState, player_id_who_finished_attack: str):
        state.log(f"{player_id_who_finished_attack} ends their ATTACK phase.")
        opponent_id = state.get_opponent_id(player_id_who_finished_attack)
        if not opponent_id: # Should not happen in 2 player game
            state.winner = player_id_who_finished_attack
            state.game_phase = "GAME_OVER"
            state.log(f"Error: Opponent not found. {player_id_who_finished_attack} wins by default.")
            return

        state.current_player_id = opponent_id
        state.game_phase = f"{opponent_id}_PLAY"
        state.round_number += (1 if opponent_id == self.config.PLAYER_IDS[0] else 0) # Increment round if P1 starts again
        
        # Opponent draws a card at the start of their PLAY phase
        opponent_player_obj = state.get_player(opponent_id)
        if opponent_player_obj:
            drawn_cards = opponent_player_obj.draw_cards(self.config.CARDS_DRAWN_PER_ROUND_START)
            state.log(f"{opponent_id} draws {len(drawn_cards)} card(s) for starting their turn. Phase: {state.game_phase}")
        else:
            state.log(f"Error: Could not find player {opponent_id} to draw card.")


    def game_step(self, current_state: GameState, action: PlayerAction) -> GameState:
        state = current_state.clone() # Work on a copy

        if state.winner:
            state.log(f"Game is over. Winner: {state.winner}. No more actions.")
            return state

        # --- Action Validation (Basic) ---
        if action.player_id != state.current_player_id:
            state.log(f"Invalid action: It's {state.current_player_id}'s turn, not {action.player_id}'s.")
            return state # Return original cloned state without changes

        # --- Process Actions based on Game Phase ---
        current_player = state.get_player(state.current_player_id)
        opponent_player = state.get_opponent(state.current_player_id)
        if not current_player or not opponent_player:
             state.log(f"Critical error: Player object not found for {state.current_player_id} or opponent.")
             state.winner = "Error" # Or handle appropriately
             state.game_phase = "GAME_OVER"
             return state

        # --- PLAY PHASE ---
        if state.game_phase == f"{action.player_id}_PLAY":
            if isinstance(action, PlayCardAction):
                card = current_player.play_card_to_field(action.card_instance_id, self.config)
                if card:
                    state.log(f"{action.player_id} played {card.name} ({card.instance_id}) to field.")
                else:
                    state.log(f"{action.player_id} failed to play card {action.card_instance_id}.")
            elif isinstance(action, EndPhaseAction):
                state.log(f"{action.player_id} ends PLAY phase.")
                self._transition_to_attack_phase(state, action.player_id)
            else:
                state.log(f"Invalid action type {type(action)} during {state.game_phase}.")
        
        # --- ATTACK PHASE (Card selected by queue, player chooses target or ends turn for this card) ---
        elif state.game_phase == f"{action.player_id}_ATTACK_ACTION":
            # Check if the action's attacker_instance_id matches the one from queue
            if not state.attack_action_queue or \
               state.current_attacker_in_queue_idx >= len(state.attack_action_queue):
                state.log("Error: Attack queue is empty or index out of bounds during ATTACK_ACTION.")
                self._end_attack_phase(state, action.player_id) # Attempt to recover
                return state

            expected_attacker_id, owner = state.attack_action_queue[state.current_attacker_in_queue_idx]

            if isinstance(action, AttackAction):
                if action.attacker_instance_id != expected_attacker_id:
                    state.log(f"Invalid Attack: Expected {expected_attacker_id} to attack, but got {action.attacker_instance_id}.")
                    return state # No change, player needs to use the correct card or EndPhase

                attacker_info = state.find_card_on_field(action.attacker_instance_id)
                target_info = state.find_card_on_field(action.target_instance_id)

                if not attacker_info or attacker_info[1].id != action.player_id:
                    state.log(f"Attack failed: Attacker {action.attacker_instance_id} not found or not owned by {action.player_id}.")
                    return state
                if not target_info or target_info[1].id == action.player_id: # Cannot target own card
                    state.log(f"Attack failed: Target {action.target_instance_id} not found or is friendly.")
                    return state

                attacker_card, _ = attacker_info
                target_card, target_owner_player = target_info
                
                if not attacker_card.can_attack_this_turn:
                    state.log(f"Attack failed: {attacker_card.name} cannot attack this turn (already attacked or effect).")
                    return state

                state.log(f"{attacker_card.name} ({action.player_id}) attacks {target_card.name} ({target_owner_player.id}).")

                # Civility Check (Accuracy)
                # Rule: "Civility gives attack accuracy. When a card attacks, roll a d10. If roll > Civility/10 then attack hits, with prob 50%."
                # Code Impl: hit_chance = (50 + Civility/2) / 100. Higher Civility = better hit chance.
                civility = attacker_card.scores.get("Civility", 0)
                hit_chance_from_civility = (50 + civility / 2) / 100.0
                if random.random() > hit_chance_from_civility:
                    state.log(f"Attack by {attacker_card.name} misses due to Civility (Roll > {hit_chance_from_civility:.2f}).")
                else:
                    # Precision Check (Deflection by Target)
                    # Rule: "Forthrightness ... If roll < Forthrightness/10 then deflected, prob 50%."
                    # Code Impl: Uses "Precision". if random.randint(1,10) < Precision/10 and random.random() < 0.5
                    precision = target_card.scores.get("Precision", 0)
                    deflection_threshold_roll = precision / 10.0 # e.g., Precision 30 -> threshold 3. Roll 1,2 deflects.
                    if random.randint(1, 10) < deflection_threshold_roll and random.random() < 0.5:
                        state.log(f"Attack by {attacker_card.name} was deflected by {target_card.name} (Precision).")
                    else:
                        # Attack Hits, Calculate Damage
                        potential_damage = attacker_card.calculate_attack_power()
                        defense_power = target_card.calculate_defense_power()
                        actual_damage = max(0, math.floor(potential_damage - defense_power))
                        
                        state.log(f"{attacker_card.name} deals {actual_damage} damage to {target_card.name} (Atk:{potential_damage:.1f} vs Def:{defense_power:.1f}).")
                        target_card.take_damage(actual_damage)

                        if target_card.is_defeated():
                            state.log(f"{target_card.name} ({target_owner_player.id}) is defeated!")
                            target_owner_player.remove_card_from_field(target_card.instance_id, self.config)
                            # Check for game over immediately after a card is defeated
                            winner_check = self._check_game_over(state)
                            if winner_check:
                                state.winner = winner_check
                                state.game_phase = "GAME_OVER"
                                state.log(f"Game Over! Winner: {state.winner}")
                                return state
                
                attacker_card.can_attack_this_turn = False # Card has used its attack for this turn's queue spot
                state.current_attacker_in_queue_idx += 1
                self._process_next_in_attack_queue(state) # Move to next card in queue or end attack phase

            elif isinstance(action, EndPhaseAction):
                # Player chooses to not use the current card's attack or end their involvement in attack phase
                state.log(f"{action.player_id} chose to not attack with {expected_attacker_id} (or end turn).")
                # If it was their card, mark it as "passed" for this turn if needed, or just move on.
                # For simplicity, we just move to the next in queue. If they want to skip their card, it's skipped.
                state.current_attacker_in_queue_idx += 1
                self._process_next_in_attack_queue(state)
            else:
                state.log(f"Invalid action type {type(action)} during {state.game_phase}.")
        else:
            state.log(f"Invalid action: Action {type(action)} not handled in phase {state.game_phase}.")


        # Final game over check if not already set
        if not state.winner:
            winner_check = self._check_game_over(state)
            if winner_check:
                state.winner = winner_check
                state.game_phase = "GAME_OVER"
                state.log(f"Game Over! Winner: {state.winner}")
        
        return state


    # Example of serialization/deserialization
    # state_dict = current_game_state.to_dict()
    # print("\nSerialized state (sample):")
    # print(json.dumps({"current_player_id": state_dict["current_player_id"], "game_phase": state_dict["game_phase"]}, indent=2))
    # reconstructed_state = GameState.from_dict(state_dict)
    # assert reconstructed_state.current_player_id == current_game_state.current_player_id
    # print("Serialization/Deserialization basic check passed.")