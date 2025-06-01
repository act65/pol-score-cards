import random
import math
import json
import os
import copy
from dataclasses import dataclass
from dataclasses import field as abs_field
from typing import Optional, List, Dict, Callable, Tuple, Any, Union
import logging

@dataclass
class GameConfig:
    MAX_HP_CARD: int = 100
    INITIAL_HAND_SIZE: int = 3
    CARDS_DRAWN_PER_ROUND: int = 0
    BASE_FIELD_SLOTS: int = 2
    CHARISMA_PER_EXTRA_SLOT: int = 100
    PLAYER_IDS: Tuple[str, str] = ("P1", "P2")
    STARTING_HEALTH_POINTS: int = 1000
    CIVILITY_PIERCE_DIVISOR: int = 10

# use global config
config = GameConfig()

@dataclass
class Attributes:
    strength: int
    divination: int
    charisma: int
    rigor: int
    specificity: int
    civility: int
    authenticity: int
    veracity: int
    forthrightness: int

@dataclass
class PoliticianCard:
    id: str
    name: str
    party: str
    attributes: Attributes
    owner_id: Optional[str] = None
    instance_id: str = abs_field(init=False)
    max_hp: int = abs_field(init=False)
    current_hp: int = abs_field(init=False)
    attack_damage_base: int = abs_field(init=False)
    defense_base: int = abs_field(init=False)

    def __post_init__(self):
        self.instance_id = f"{self.id}_{random.randint(10000, 99999)}"
        
        # Strength mechanic: Multiplies base hp and sets base damage/defense
        self.max_hp = config.MAX_HP_CARD * self.attributes.strength
        self.current_hp = self.max_hp
        
        # Base attack = Strength, Base defense = Strength
        # Rigor is attack multiplier, Veracity is defense multiplier
        self.attack_damage_base = self.attributes.strength * self.attributes.rigor
        self.defense_base = self.attributes.strength * self.attributes.veracity

    def __str__(self):
        owner_str = f" (Owner: {self.owner_id})" if self.owner_id else ""
        return f"{self.name} ({self.party}) [{self.instance_id}]{owner_str} - HP: {self.current_hp}/{self.max_hp} - Div: {self.attributes.divination}"

    def take_damage(self, amount: int):
        # assert amount >= 0 # Damage can be 0 if fully defended
        effective_amount = max(0, amount) # Ensure non-negative damage
        self.current_hp -= effective_amount
        self.current_hp = max(0, self.current_hp)

    def is_defeated(self) -> bool:
        return self.current_hp <= 0

@dataclass
class PlayerState:
    id: str
    deck: List[PoliticianCard] = abs_field(default_factory=list)
    hand: List[PoliticianCard] = abs_field(default_factory=list)
    field: List[PoliticianCard] = abs_field(default_factory=list)
    graveyard: List[PoliticianCard] = abs_field(default_factory=list)
    max_cards_on_field: int = abs_field(init=False)
    health_points: int = abs_field(init=False)

    def __post_init__(self):
        self.health_points = config.STARTING_HEALTH_POINTS
        self.update_max_field_cards() # Initial calculation

    def __str__(self):
        hand_names = [c.name for c in self.hand]
        # Removed c.can_attack_this_turn as it's not defined
        field_names = [f"{c.name}(HP:{c.current_hp})" for c in self.field]
        return (f"Player {self.id} (HP: {self.health_points})\n"
                f"  Hand ({len(self.hand)}): {hand_names}\n"
                f"  Field ({len(self.field)}/{self.max_cards_on_field}): {field_names}\n"
                f"  Deck: {len(self.deck)} cards")

    def update_max_field_cards(self):
        # Charisma mechanic: Limits number of cards in play
        total_charisma_on_field = sum(c.attributes.charisma for c in self.field)
        self.max_cards_on_field = config.BASE_FIELD_SLOTS + math.floor(total_charisma_on_field / config.CHARISMA_PER_EXTRA_SLOT)

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

    def play_card_to_field(self, card_instance_id: str):
        card_to_play = next((c for c in self.hand if c.instance_id == card_instance_id), None)
        if card_to_play:
            if len(self.field) < self.max_cards_on_field:
                self.hand.remove(card_to_play)
                self.field.append(card_to_play)
                self.update_max_field_cards() # Recalculate max field cards
                return True
            # else: self.logger.warning(f"{self.id} cannot play {card_to_play.name}, field is full.")
        # else: self.logger.warning(f"{self.id} tried to play card {card_instance_id} not in hand.")
        return False

    def remove_card_from_field(self, card_instance_id: str, to_graveyard: bool = True):
        card_to_remove = next((c for c in self.field if c.instance_id == card_instance_id), None)
        if card_to_remove:
            self.field.remove(card_to_remove)
            if to_graveyard:
                self.graveyard.append(card_to_remove)
            self.update_max_field_cards() # Recalculate max field cards
            return card_to_remove
        return None

    def discard_from_hand(self, card_instance_id: str):
        card_to_discard = next((c for c in self.hand if c.instance_id == card_instance_id), None)
        if card_to_discard:
            self.hand.remove(card_to_discard)
            self.graveyard.append(card_to_discard)
            return card_to_discard
        return None
    
    def take_direct_damage(self, amount: int):
        self.health_points -= amount
        self.health_points = max(0, self.health_points)


@dataclass
class GameState:
    players: Dict[str, PlayerState]
    round_number: int = 0
    game_phase: str = "INITIALIZING" # e.g., INITIALIZING, ONGOING, GAME_OVER
    winner: Optional[str] = None
    action_log: List[str] = abs_field(default_factory=list) # For game events

    def log_event(self, message: str):
        self.action_log.append(f"R{self.round_number}: {message}")
        # In a real app, this would go to a proper logger
        print(f"R{self.round_number}: {message}")


    def find_card_on_field(self, instance_id: str) -> Optional[Tuple[PoliticianCard, PlayerState]]: # Fixed type hint
        for player in self.players.values():
            for card in player.field:
                if card.instance_id == instance_id:
                    return card, player
        return None

    def all_cards_on_field(self) -> List[Tuple[PoliticianCard, PlayerState]]:
        return [(card, player)
                for player in self.players.values()
                for card in player.field]
    
    def get_opponent(self, player_id: str) -> PlayerState:
        for pid, player in self.players.items():
            if pid != player_id:
                return player
        raise ValueError("Opponent not found") # Should not happen in a 2-player game

@dataclass
class BaseAction:
    player_id: str

@dataclass
class PlayCardAction(BaseAction):
    card_instance_id: str # From hand to field

@dataclass
class AttackAction(BaseAction):
    attacker_instance_id: str
    target_instance_id: str

# Union of all possible action types
PlayerActionType = Union[PlayCardAction, AttackAction]

@dataclass
class PlayerTurnActions:
    player_id: str
    actions: List[PlayerActionType]

@dataclass
class RoundActions:
    player1_actions: PlayerTurnActions
    player2_actions: PlayerTurnActions

class GameEngine:
    def __init__(self, player1_deck: List[PoliticianCard], player2_deck: List[PoliticianCard]):
        
        # Initialize players with their decks and config
        # Deepcopy decks to prevent modification of original deck lists if they are reused
        p1_id, p2_id = config.PLAYER_IDS
        self.player1_state = PlayerState(id=p1_id, deck=copy.deepcopy(player1_deck))
        self.player2_state = PlayerState(id=p2_id, deck=copy.deepcopy(player2_deck))

        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)


    def initialize_game_state(self) -> GameState:
        initial_state = GameState(
            players={
                self.player1_state.id: self.player1_state,
                self.player2_state.id: self.player2_state
            },
            game_phase="INITIALIZING"
        )
        initial_state.log_event("Game starting...")

        # Initial draw for both players
        for p_id in initial_state.players:
            drawn_count = len(initial_state.players[p_id].draw_cards(config.INITIAL_HAND_SIZE))
            initial_state.log_event(f"{p_id} drew {drawn_count} cards.")
        
        initial_state.game_phase = "ONGOING"
        initial_state.round_number = 1
        return initial_state

    def _check_game_over(self, state: GameState) -> Optional[str]:
        p1 = state.players[config.PLAYER_IDS[0]]
        p2 = state.players[config.PLAYER_IDS[1]]

        p1_lost = p1.health_points <= 0
        p2_lost = p2.health_points <= 0

        if p1_lost and p2_lost:
            return "DRAW" # Both players lost simultaneously
        elif p1_lost:
            return p2.id # P2 wins
        elif p2_lost:
            return p1.id # P1 wins
        
        # Could add other conditions like deck out, etc.
        return None


    def process_round(self, current_state: GameState, round_actions: RoundActions) -> GameState:
        if current_state.game_phase != "ONGOING":
            self.logger.warning("Attempted to process round when game is not ongoing.")
            return current_state

        current_state.log_event(f"Starting Round {current_state.round_number} processing.")

        # Step 1: Draw cards (as per CARDS_DRAWN_PER_ROUND)
        for p_id, player_state in current_state.players.items():
            drawn_count = len(player_state.draw_cards(config.CARDS_DRAWN_PER_ROUND))
            if drawn_count > 0:
                current_state.log_event(f"{p_id} drew {drawn_count} card(s).")
            else:
                current_state.log_event(f"{p_id} has no cards left to draw.")


        # Step 2: Play Cards
        # Process P1 plays, then P2 plays. Or interleave? For simplicity, P1 then P2.
        # The order might matter if playing a card affects the other player's ability to play.
        # For now, assume simultaneous intent, sequential resolution.
        
        actions_to_process = [
            (round_actions.player1_actions.player_id, round_actions.player1_actions.actions),
            (round_actions.player2_actions.player_id, round_actions.player2_actions.actions)
        ]

        for p_id, p_actions in actions_to_process:
            player_state = current_state.players[p_id]
            for action in p_actions:
                if isinstance(action, PlayCardAction):
                    card_to_play = next((c for c in player_state.hand if c.instance_id == action.card_instance_id), None)
                    if card_to_play:
                        if player_state.play_card_to_field(action.card_instance_id):
                            current_state.log_event(f"{p_id} played {card_to_play.name} to the field.")
                        else:
                            current_state.log_event(f"{p_id} failed to play {card_to_play.name} (field full or card not found).")
                    else:
                        current_state.log_event(f"{p_id} tried to play card {action.card_instance_id} not in hand.")
        
        # Step 3: Process Attacks (ordered by Divination)
        all_attack_actions: List[Tuple[AttackAction, PoliticianCard]] = []
        
        # Collect all valid attack actions and their corresponding attacker cards
        for p_id, p_actions in actions_to_process:
            player_state = current_state.players[p_id]
            for action in p_actions:
                if isinstance(action, AttackAction):
                    attacker_card, _ = current_state.find_card_on_field(action.attacker_instance_id)
                    if attacker_card and attacker_card.owner_id == p_id and not attacker_card.is_defeated():
                        all_attack_actions.append((action, attacker_card))
                    # else: current_state.log_event(f"Invalid attack: Attacker {action.attacker_instance_id} not found or not valid for {p_id}.")

        # Sort attacks by Divination (higher Divination acts first)
        all_attack_actions.sort(key=lambda x: x[1].attributes.divination, reverse=True)

        current_state.log_event(f"Processing {len(all_attack_actions)} attacks.")
        for attack_action, attacker_card in all_attack_actions:
            if attacker_card.is_defeated(): # Attacker might have been defeated by a prior attack
                current_state.log_event(f"Attacker {attacker_card.name} [{attacker_card.instance_id}] was already defeated. Skipping attack.")
                continue

            attacker_player_state = current_state.players[attacker_card.owner_id]
            target_card_info = current_state.find_card_on_field(attack_action.target_instance_id)

            if not target_card_info:
                current_state.log_event(f"Attack by {attacker_card.name}: Target {attack_action.target_instance_id} not found on field. Attack fizzles.")
                continue
            
            target_card, target_player_state = target_card_info

            if target_card.is_defeated():
                current_state.log_event(f"Attack by {attacker_card.name}: Target {target_card.name} [{target_card.instance_id}] is already defeated. Attack fizzles.")
                continue

            current_state.log_event(f"Attack: {attacker_card.name} [{attacker_card.instance_id}] ({attacker_player_state.id}) -> {target_card.name} [{target_card.instance_id}] ({target_player_state.id})")
            # Authenticity: Chance to randomly attack a different card than intended
            # Retargets only to opponent's cards currently on field
            auth_roll = random.random()
            retarget_chance = (100 - attacker_card.attributes.authenticity) / 100.0
            if auth_roll < retarget_chance and attacker_card.attributes.authenticity < 100:
                opponent_cards_on_field = [
                    c for c in current_state.get_opponent(attacker_player_state.id).field if not c.is_defeated() and c.instance_id != target_card.instance_id
                ]
                if opponent_cards_on_field:
                    original_target_name = target_card.name
                    new_target_card = random.choice(opponent_cards_on_field)
                    target_card = new_target_card
                    target_player_state = current_state.players[new_target_card.owner_id]
                    current_state.log_event(f"  Authenticity Check: {attacker_card.name} retargeted from {original_target_name} to {target_card.name}!")
                else:
                    current_state.log_event(f"  Authenticity Check: {attacker_card.name} failed to retarget (no other valid opponent cards). Attack continues on {target_card.name}.")


            # Specificity: True strike (with 100 specificity). Otherwise you have a miss chance.
            spec_roll = random.random()
            miss_chance = (100 - attacker_card.attributes.specificity) / 100.0
            if attacker_card.attributes.specificity < 100 and spec_roll < miss_chance:
                current_state.log_event(f"  Specificity Check: {attacker_card.name}'s attack MISSED {target_card.name}!")
                continue # Attack ends here

            # Calculate Damage
            # Base attack = Strength * Rigor (from PoliticianCard.attack_damage_base)
            # Base defense = Strength * Veracity (from PoliticianCard.defense_base)
            calculated_attack = attacker_card.attack_damage_base
            calculated_defense = target_card.defense_base
            
            damage_to_card = max(0, calculated_attack - calculated_defense)
            target_card.take_damage(damage_to_card)
            current_state.log_event(f"  {attacker_card.name} deals {damage_to_card} damage to {target_card.name}. ({target_card.name} HP: {target_card.current_hp}/{target_card.max_hp})")


            # Forthrightness: Chance to block attack.
            reflected_dmg = calculated_attack * target_card.attributes.forthrightness // 100
            attacker_card.take_damage(reflected_dmg)
            current_state.log_event(f"  {attacker_card.name}'s attack is partly relected and takes {reflected_dmg} from {target_card.name}.")

            # Civility: Attacks pierce through cards and deal extra civility/X damage to player.
            if config.CIVILITY_PIERCE_DIVISOR > 0:
                civility_damage_to_player = math.floor(attacker_card.attributes.civility / config.CIVILITY_PIERCE_DIVISOR)
                if civility_damage_to_player > 0:
                    target_player_state.take_direct_damage(civility_damage_to_player)
                    current_state.log_event(f"  Civility: {attacker_card.name} deals {civility_damage_to_player} direct damage to Player {target_player_state.id} (HP: {target_player_state.health_points}).")

            # Check if target card is defeated
            if target_card.is_defeated():
                target_player_state.remove_card_from_field(target_card.instance_id, to_graveyard=True)
                current_state.log_event(f"  {target_card.name} has been defeated and moved to {target_player_state.id}'s graveyard.")
            
            # Check for game over after each attack's resolution (due to civility damage)
            winner = self._check_game_over(current_state)
            if winner:
                current_state.winner = winner
                current_state.game_phase = "GAME_OVER"
                current_state.log_event(f"Game Over! Winner: {current_state.winner}")
                return current_state # End round processing immediately

        # Step 4: End of Round Cleanup (e.g., remove defeated cards not handled by attacks, though they should be)
        # This is mostly handled, but good to have a phase for it.
        # For example, if cards had "at end of round" effects.

        # Final game over check for the round (e.g. if a player decked out and lost, not yet implemented)
        if not current_state.winner:
            winner = self._check_game_over(current_state)
            if winner:
                current_state.winner = winner
                current_state.game_phase = "GAME_OVER"
                current_state.log_event(f"Game Over at end of round! Winner: {current_state.winner}")
        
        if current_state.game_phase == "ONGOING":
            current_state.round_number += 1
            current_state.log_event("Round ended.")
        
        return current_state