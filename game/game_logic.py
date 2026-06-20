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
    rarity: str = "#4b5563"   # TCG rarity colour; assigned over the deck at load

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
    action_log: List[str] = abs_field(default_factory=list) # Human-readable log
    # Structured, machine-readable events for the most recent round. The frontend
    # replays these in order to animate resolution (no fragile log parsing). Reset
    # at the start of each round.
    events: List[Dict[str, Any]] = abs_field(default_factory=list)

    def log_event(self, message: str):
        self.action_log.append(f"R{self.round_number}: {message}")
        # In a real app, this would go to a proper logger
        print(f"R{self.round_number}: {message}")

    def emit(self, event_type: str, **fields):
        """Append a structured event for the frontend to replay."""
        event = {"type": event_type, "round": self.round_number}
        event.update(fields)
        self.events.append(event)


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

        current_state.events = []  # fresh structured events for this round
        current_state.emit("round_start")
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
                            current_state.emit("play", player=p_id, card=card_to_play.name, instance_id=card_to_play.instance_id)
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
        # Announce resolution order (Divination decides who acts first).
        current_state.emit("attack_order", order=[
            {"instance_id": c.instance_id, "name": c.name, "player": c.owner_id,
             "divination": c.attributes.divination}
            for _, c in all_attack_actions
        ])

        def _card_ref(card):
            return {"instance_id": card.instance_id, "name": card.name, "player": card.owner_id}

        def _finish_if_over():
            winner = self._check_game_over(current_state)
            if winner:
                current_state.winner = winner
                current_state.game_phase = "GAME_OVER"
                current_state.emit("game_over", winner=winner)
                current_state.log_event(f"Game Over! Winner: {winner}")
                return True
            return False

        for attack_action, attacker_card in all_attack_actions:
            if attacker_card.is_defeated():  # may have died to an earlier reflect
                current_state.log_event(f"Attacker {attacker_card.name} was already defeated. Skipping attack.")
                continue

            attacker_player_state = current_state.players[attacker_card.owner_id]
            opponent_state = current_state.get_opponent(attacker_player_state.id)
            living_opponent_cards = [c for c in opponent_state.field if not c.is_defeated()]

            # Resolve the target. A "base attack" hits the opponent's HP directly:
            # either the action explicitly targets a player id, or it targeted a card
            # that is gone while the opposing field is empty (so there's nothing to
            # block for them) -> the blow lands on the base.
            target_is_base = attack_action.target_instance_id in current_state.players
            target_card_info = None if target_is_base else current_state.find_card_on_field(attack_action.target_instance_id)
            if not target_is_base and (target_card_info is None or target_card_info[0].is_defeated()):
                if not living_opponent_cards:
                    target_is_base = True
                else:
                    current_state.log_event(f"Attack by {attacker_card.name}: target gone, opponent still has cards. Fizzles.")
                    current_state.emit("fizzle", attacker=_card_ref(attacker_card))
                    continue

            calculated_attack = attacker_card.attack_damage_base

            # --- Base attack -------------------------------------------------
            if target_is_base:
                base_player = current_state.players.get(attack_action.target_instance_id, opponent_state)
                if base_player.id == attacker_player_state.id:  # never hit your own base
                    base_player = opponent_state
                current_state.emit("attack", attacker=_card_ref(attacker_card),
                                   target={"kind": "base", "player": base_player.id})
                current_state.log_event(f"Attack: {attacker_card.name} ({attacker_player_state.id}) -> {base_player.id}'s base")

                # Specificity miss still applies to base attacks.
                if attacker_card.attributes.specificity < 100 and random.random() < (100 - attacker_card.attributes.specificity) / 100.0:
                    current_state.emit("miss", attacker=_card_ref(attacker_card), target={"kind": "base", "player": base_player.id})
                    current_state.log_event(f"  Specificity Check: {attacker_card.name}'s attack on the base MISSED!")
                    continue

                base_player.take_direct_damage(calculated_attack)
                current_state.emit("base_attack", attacker=_card_ref(attacker_card),
                                   target_player=base_player.id, amount=calculated_attack,
                                   player_hp=base_player.health_points)
                current_state.log_event(f"  {attacker_card.name} hits {base_player.id}'s base for {calculated_attack}. (Player HP: {base_player.health_points})")
                if _finish_if_over():
                    return current_state
                continue

            # --- Card attack -------------------------------------------------
            target_card, target_player_state = target_card_info
            current_state.emit("attack", attacker=_card_ref(attacker_card), target={"kind": "card", **_card_ref(target_card)})
            current_state.log_event(f"Attack: {attacker_card.name} ({attacker_player_state.id}) -> {target_card.name} ({target_player_state.id})")

            # Authenticity: chance to randomly hit a different enemy card than intended.
            if attacker_card.attributes.authenticity < 100 and random.random() < (100 - attacker_card.attributes.authenticity) / 100.0:
                others = [c for c in living_opponent_cards if c.instance_id != target_card.instance_id]
                if others:
                    original_target_name = target_card.name
                    target_card = random.choice(others)
                    target_player_state = current_state.players[target_card.owner_id]
                    current_state.emit("retarget", attacker=_card_ref(attacker_card),
                                       from_name=original_target_name, target=_card_ref(target_card))
                    current_state.log_event(f"  Authenticity: {attacker_card.name} retargeted from {original_target_name} to {target_card.name}!")

            # Specificity: 100 = always hits, otherwise miss chance.
            if attacker_card.attributes.specificity < 100 and random.random() < (100 - attacker_card.attributes.specificity) / 100.0:
                current_state.emit("miss", attacker=_card_ref(attacker_card), target={"kind": "card", **_card_ref(target_card)})
                current_state.log_event(f"  Specificity Check: {attacker_card.name}'s attack MISSED {target_card.name}!")
                continue

            # Damage = attack (strength*rigor) minus defense (strength*veracity), floored at 0.
            damage_to_card = max(0, calculated_attack - target_card.defense_base)
            target_card.take_damage(damage_to_card)
            current_state.emit("damage", source=_card_ref(attacker_card), target=_card_ref(target_card),
                               amount=damage_to_card, current_hp=target_card.current_hp, max_hp=target_card.max_hp)
            current_state.log_event(f"  {attacker_card.name} deals {damage_to_card} damage to {target_card.name}. ({target_card.name} HP: {target_card.current_hp}/{target_card.max_hp})")

            # Forthrightness: target reflects attack*forthrightness/100 back to the attacker.
            reflected_dmg = calculated_attack * target_card.attributes.forthrightness // 100
            if reflected_dmg > 0:
                attacker_card.take_damage(reflected_dmg)
                current_state.emit("reflect", source=_card_ref(target_card), target=_card_ref(attacker_card),
                                   amount=reflected_dmg, current_hp=attacker_card.current_hp, max_hp=attacker_card.max_hp)
                current_state.log_event(f"  {attacker_card.name}'s attack is partly reflected and takes {reflected_dmg} from {target_card.name}.")

            # Civility: pierce damage to the target's owner.
            if config.CIVILITY_PIERCE_DIVISOR > 0:
                civility_damage = math.floor(attacker_card.attributes.civility / config.CIVILITY_PIERCE_DIVISOR)
                if civility_damage > 0:
                    target_player_state.take_direct_damage(civility_damage)
                    current_state.emit("civility", attacker=_card_ref(attacker_card),
                                       target_player=target_player_state.id, amount=civility_damage,
                                       player_hp=target_player_state.health_points)
                    current_state.log_event(f"  Civility: {attacker_card.name} deals {civility_damage} direct damage to Player {target_player_state.id} (HP: {target_player_state.health_points}).")

            # Remove any cards that died this exchange — target AND attacker (reflect can kill).
            if target_card.is_defeated():
                target_player_state.remove_card_from_field(target_card.instance_id, to_graveyard=True)
                current_state.emit("defeat", card=_card_ref(target_card))
                current_state.log_event(f"  {target_card.name} has been defeated and moved to {target_player_state.id}'s graveyard.")
            if attacker_card.is_defeated():
                attacker_player_state.remove_card_from_field(attacker_card.instance_id, to_graveyard=True)
                current_state.emit("defeat", card=_card_ref(attacker_card))
                current_state.log_event(f"  {attacker_card.name} was defeated by reflected damage and moved to {attacker_player_state.id}'s graveyard.")

            if _finish_if_over():
                return current_state

        # Step 4: End-of-round sweep — guarantee no defeated card lingers on a field.
        for player_state in current_state.players.values():
            for card in list(player_state.field):
                if card.is_defeated():
                    player_state.remove_card_from_field(card.instance_id, to_graveyard=True)
                    current_state.emit("defeat", card=_card_ref(card))
                    current_state.log_event(f"  {card.name} removed from {player_state.id}'s field (defeated).")

        # Final game-over check for the round.
        if not current_state.winner and _finish_if_over():
            return current_state

        if current_state.game_phase == "ONGOING":
            current_state.round_number += 1
            current_state.log_event("Round ended.")

        return current_state