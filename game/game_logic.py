import random
import math
import json 
import os

# Master list of all card definitions (politician_data + scores_data)
MASTER_CARD_DEFINITIONS: dict[str, dict] = {} 

def load_master_card_definitions():
    global MASTER_CARD_DEFINITIONS; MASTER_CARD_DEFINITIONS.clear()
    SITE_STATIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "static")
    if not os.path.exists(SITE_STATIC_PATH): 
        try: os.makedirs(SITE_STATIC_PATH)
        except OSError as e: print(f"Could not create directory {SITE_STATIC_PATH}: {e}.")
    politicians_jsonl_path = os.path.join(SITE_STATIC_PATH, "politicians.jsonl")
    scores_jsonl_path = os.path.join(SITE_STATIC_PATH, "scores.jsonl")
    if not os.path.exists(politicians_jsonl_path):
        with open(politicians_jsonl_path, 'w', encoding='utf-8') as f:
            f.write('{"id": "pol1", "name": "Polly One", "party": "Party A"}\n'); f.write('{"id": "pol2", "name": "Polly Two", "party": "Party B"}\n')
    if not os.path.exists(scores_jsonl_path):
        with open(scores_jsonl_path, 'w', encoding='utf-8') as f:
            f.write('{"politician_id": "pol1", "Strength":70,"Rigor":60,"Specificity":50,"Civility":80,"Precision":30,"Veracity":70,"Authenticity":50,"Divination":60,"Charisma":120}\n')
            f.write('{"politician_id": "pol2", "Strength":65,"Rigor":70,"Specificity":60,"Civility":70,"Precision":70,"Veracity":60,"Authenticity":60,"Divination":80,"Charisma":80}\n')
    all_politicians_info, all_scores_info = [], []
    try:
        with open(politicians_jsonl_path, 'r', encoding='utf-8') as f:
            for line in f: all_politicians_info.append(json.loads(line))
        with open(scores_jsonl_path, 'r', encoding='utf-8') as f:
            for line in f: all_scores_info.append(json.loads(line))
    except FileNotFoundError as e: print(f"Error loading master card definitions: {e}"); return
    current_definitions = {}; scores_map = {s["politician_id"]: s for s in all_scores_info}
    for pol_data in all_politicians_info:
        if pol_data["id"] in scores_map: current_definitions[pol_data["id"]] = {"politician_data": pol_data, "scores_data": scores_map[pol_data["id"]]}
    if not current_definitions: print("Critical Warning: MASTER_CARD_DEFINITIONS empty.")
    else: MASTER_CARD_DEFINITIONS = current_definitions

class PoliticianCard:
    def __init__(self, politician_data: dict, politician_scores_data: dict):
        self.id: str = politician_data["id"]; self.name: str = politician_data["name"]; self.party: str = politician_data["party"]
        self.scores: dict[str, int] = {k: v for k, v in politician_scores_data.items() if k != "politician_id"}
        self.max_hp: int = 250; self.current_hp: int = self.max_hp
        self.instance_id: str = f"{self.id}_{random.randint(10000, 99999)}"
    def __str__(self): return f"{self.name} ({self.party}) [{self.instance_id}] - HP: {self.current_hp}/{self.max_hp}"
    def calculate_attack_power(self, target_card: 'PoliticianCard'): 
        s=self.scores.get("Strength",0);r=self.scores.get("Rigor",0);sp=self.scores.get("Specificity",0)
        ba=s;ar=random.randint(1,10);spf=math.floor(sp/10);ear=max(ar,spf);rb=ear*(r/10);tap=ba+rb;return tap
    def calculate_defense_power(self):
        s=self.scores.get("Strength",0);v=self.scores.get("Veracity",0);a=self.scores.get("Authenticity",0)
        bd=s;dr=random.randint(1,10);af=math.floor(a/10);edr=max(dr,af);vb=edr*(v/10);tdp=bd+vb;return tdp
    def take_damage(self, amount: int): ea=max(0,amount);self.current_hp-=ea;self.current_hp=max(0,self.current_hp)
    def is_defeated(self) -> bool: return self.current_hp <= 0
    def to_dict(self) -> dict: return {"id":self.id,"instance_id":self.instance_id,"current_hp":self.current_hp}
    @classmethod
    def from_dict(cls, data: dict) -> 'PoliticianCard':
        if not MASTER_CARD_DEFINITIONS:load_master_card_definitions()
        cd=MASTER_CARD_DEFINITIONS.get(data["id"])
        if not cd:raise ValueError(f"Def not found for id: {data['id']}")
        card=cls(cd["politician_data"],cd["scores_data"])
        card.instance_id=data["instance_id"];card.current_hp=data["current_hp"];return card

class Player:
    def __init__(self, player_id: str, initial_deck: list[PoliticianCard] | None = None):
        self.id: str = player_id; self.deck: list[PoliticianCard] = []; self.hand: list[PoliticianCard] = []
        self.field: list[PoliticianCard] = []; self.max_cards_on_field: int = 2
        if initial_deck is not None: self.deck = list(initial_deck); random.shuffle(self.deck)
        self.update_max_field_cards()
    def __str__(self):
        hn=[c.name for c in self.hand];fn=[f"{c.name}(C:{c.scores.get('Charisma',0)})" for c in self.field]
        return (f"Player {self.id}\n  Hand ({len(self.hand)}): {hn}\n  Field ({len(self.field)}/{self.max_cards_on_field}): {fn}\n  Deck: {len(self.deck)} cards")
    def update_max_field_cards(self):
        tc=sum(c.scores.get("Charisma",0) for c in self.field) if self.field else 0;self.max_cards_on_field=2+math.floor(tc/100)
    def draw_card(self, num: int = 1) -> list[PoliticianCard]:
        d,h=[],self.hand;dk=self.deck
        for _ in range(num):
            if dk:c=dk.pop(0);h.append(c);d.append(c)
            else:break
        return d
    def play_card_to_field(self,cid:str)->bool:
        c=next((c for c in self.hand if c.instance_id==cid),None)
        if not c or len(self.field)>=self.max_cards_on_field:return False
        self.hand.remove(c);self.field.append(c);self.update_max_field_cards();return True
    def remove_card_from_field(self,cid:str):
        c=next((c for c in self.field if c.instance_id==cid),None)
        if c:self.field.remove(c);self.update_max_field_cards()
    def to_dict(self)->dict:return{"id":self.id,"deck":[c.to_dict() for c in self.deck],"hand":[c.to_dict() for c in self.hand],"field":[c.to_dict() for c in self.field]}
    @classmethod
    def from_dict(cls,data:dict)->'Player':
        p=cls(data["id"],None)
        p.deck=[PoliticianCard.from_dict(cd) for cd in data["deck"]]
        p.hand=[PoliticianCard.from_dict(cd) for cd in data["hand"]]
        p.field=[PoliticianCard.from_dict(cd) for cd in data["field"]]
        p.update_max_field_cards();return p

class Game:
    INITIAL_HAND_SIZE=5;PLAYER1_ID="Player1";PLAYER2_ID="Player2"
    def __init__(self, _reconstructing: bool = False): # Added _reconstructing flag
        if not MASTER_CARD_DEFINITIONS:load_master_card_definitions()
        # Only raise error if not reconstructing and master definitions are still empty
        if not MASTER_CARD_DEFINITIONS and not _reconstructing:
            raise RuntimeError("MASTER_CARD_DEFINITIONS empty and not reconstructing.")

        if not _reconstructing:
            p1_deck,p2_deck=[],[]
            # Ensure MASTER_CARD_DEFINITIONS is not empty before iterating
            if MASTER_CARD_DEFINITIONS:
                for _,definition in MASTER_CARD_DEFINITIONS.items():
                    p1_deck.append(PoliticianCard(definition["politician_data"],definition["scores_data"]))
                    p2_deck.append(PoliticianCard(definition["politician_data"],definition["scores_data"]))
            else: # Handle case where MASTER_CARD_DEFINITIONS might be empty (e.g. file load issue)
                print("Warning: MASTER_CARD_DEFINITIONS is empty during game setup. Players will have empty decks.")


            self.players={self.PLAYER1_ID:Player(self.PLAYER1_ID,p1_deck),self.PLAYER2_ID:Player(self.PLAYER2_ID,p2_deck)}
            for player in self.players.values():player.draw_card(self.INITIAL_HAND_SIZE)
            self.game_state=f"{self.PLAYER1_ID}_TURN_PLAY";self.game_log=["Game started."];self.current_player_id=self.PLAYER1_ID
            self.current_round_action_queue=[]
        else: # For reconstruction by from_dict: initialize attributes to be populated by from_dict
            self.players={};self.game_state="";self.game_log=[];self.current_player_id="";self.current_round_action_queue=[]

    def get_player(self,p_id:str):return self.players.get(p_id)
    def get_opponent_id(self,p_id:str):return self.PLAYER2_ID if p_id==self.PLAYER1_ID else self.PLAYER1_ID
    def log_action(self,msg:str):self.game_log.append(msg)
    def get_card_by_instance_id(self,inst_id:str): # Used by from_dict to reconstruct action queue
        for p in self.players.values(): # Check current players (being reconstructed)
            for card_list in [p.field,p.hand,p.deck]: 
                for c in card_list:
                    if c.instance_id==inst_id:return c
        return None
    def player_play_card_action(self,p_id:str,card_inst_id:str):
        player=self.get_player(p_id)
        if not player or p_id!=self.current_player_id or not self.game_state.endswith("PLAY"):self.log_action(f"Play denied for {p_id} in state {self.game_state}.");return False
        success=player.play_card_to_field(card_inst_id);card=self.get_card_by_instance_id(card_inst_id)
        self.log_action(f"{p_id} {'played' if success else 'failed to play'} {card.name if card else 'card'}.");return success
    def process_card_attack(self,att_p_id:str,att_inst_id:str,tar_inst_id:str):
        if att_p_id!=self.current_player_id or not self.game_state.endswith("ATTACK"):self.log_action(f"Attack denied for {att_p_id} in state {self.game_state}.");return False
        attacker=next((c for c in self.get_player(att_p_id).field if c.instance_id==att_inst_id),None)
        tar_p_id=self.get_opponent_id(att_p_id);target=next((c for c in self.get_player(tar_p_id).field if c.instance_id==tar_inst_id),None)
        if not attacker or not target:self.log_action(f"Attack fail: {attacker.name if attacker else 'Attacker'} or {target.name if target else 'Target'} not on field.");return False
        self.log_action(f"{attacker.name}({att_p_id}) attacks {target.name}({tar_p_id}).")
        hit_c=(50+attacker.scores.get("Civility",0)/2)/100.0
        if random.random()>hit_c:self.log_action(f"Attack by {attacker.name} misses (Civility: Roll>{hit_c:.2f}).");return True
        prec=target.scores.get("Precision",0);defl_thresh=prec/10.0
        if random.randint(1,10)<defl_thresh and random.random()<0.5:self.log_action(f"Attack by {attacker.name} deflected by {target.name} (Precision).");return True
        pot_dmg=attacker.calculate_attack_power(target);def_pow=target.calculate_defense_power();act_dmg=max(0,math.floor(pot_dmg-def_pow))
        self.log_action(f"{attacker.name} deals {act_dmg} dmg to {target.name} (Atk:{pot_dmg:.1f} vs Def:{def_pow:.1f}).");target.take_damage(act_dmg)
        if target.is_defeated():self.log_action(f"{target.name} defeated!");self.get_player(tar_p_id).remove_card_from_field(target.instance_id);self.check_game_over(); return True
        return True
    def determine_card_action_order(self):
        cards=[c for p in self.players.values() for c in p.field];self.current_round_action_queue=sorted(cards,key=lambda c:c.scores.get("Divination",0),reverse=True)
        self.log_action(f"Action order: {[c.name for c in self.current_round_action_queue]}")
    def advance_game_state(self):
        if self.check_game_over():return
        if self.game_state.endswith("PLAY"):self.game_state=f"{self.current_player_id}_TURN_ATTACK";self.determine_card_action_order()
        elif self.game_state.endswith("ATTACK"):self.current_player_id=self.get_opponent_id(self.current_player_id);self.get_player(self.current_player_id).draw_card(1);self.game_state=f"{self.current_player_id}_TURN_PLAY"
        self.log_action(f"State: {self.game_state}. Player: {self.current_player_id}")
    def check_game_over(self):
        for p_id,p in self.players.items():
            if not p.field and not p.hand and not p.deck:opp_id=self.get_opponent_id(p_id);self.game_state=f"GAME_OVER_{opp_id}_WINS";self.log_action(f"Game Over! {opp_id} wins.");return True
        return False
    def to_dict(self) -> dict:
        return {"player1_data":self.players[self.PLAYER1_ID].to_dict(),"player2_data":self.players[self.PLAYER2_ID].to_dict(),
                "game_state":self.game_state,"game_log":list(self.game_log),"current_player_id":self.current_player_id,
                "current_round_action_queue_instance_ids":[card.instance_id for card in self.current_round_action_queue]}
    @classmethod
    def from_dict(cls, data: dict) -> 'Game':
        game=cls(_reconstructing=True) # Call __init__ with flag to skip normal setup
        game.players={cls.PLAYER1_ID:Player.from_dict(data["player1_data"]),cls.PLAYER2_ID:Player.from_dict(data["player2_data"])}
        game.game_state=data["game_state"];game.game_log=list(data["game_log"]);game.current_player_id=data["current_player_id"]
        game.current_round_action_queue=[] # Rebuild queue from instance IDs
        for iid in data.get("current_round_action_queue_instance_ids", []): # Use .get for safety
            card=game.get_card_by_instance_id(iid) # Search in newly reconstructed players
            if card:game.current_round_action_queue.append(card)
            else:print(f"Warning: Card with instance_id {iid} not found during Game.from_dict queue reconstruction.")
        return game

if __name__ == '__main__':
    load_master_card_definitions()
    print(f"MAIN: MASTER_CARD_DEFINITIONS loaded with {len(MASTER_CARD_DEFINITIONS)} types.")

    # Test Game to_dict and from_dict
    game1 = Game()
    # Simulate some gameplay for a more complex state
    p1_game1 = game1.get_player(Game.PLAYER1_ID)
    p2_game1 = game1.get_player(Game.PLAYER2_ID)

    if p1_game1 and p1_game1.hand: game1.player_play_card_action(Game.PLAYER1_ID, p1_game1.hand[0].instance_id)
    game1.advance_game_state() # P1 Play -> P1 Attack
    
    if p2_game1 and p2_game1.hand: # P2 plays for setup
        # Temporarily switch context for P2 to play
        original_current_player_id = game1.current_player_id
        original_game_state = game1.game_state
        game1.current_player_id = Game.PLAYER2_ID
        game1.game_state = f"{Game.PLAYER2_ID}_TURN_PLAY"
        game1.player_play_card_action(Game.PLAYER2_ID, p2_game1.hand[0].instance_id)
        # Restore context
        game1.current_player_id = original_current_player_id
        game1.game_state = original_game_state # Should be P1_ATTACK now
    
    if p1_game1 and p1_game1.field and p2_game1 and p2_game1.field:
        game1.process_card_attack(Game.PLAYER1_ID, p1_game1.field[0].instance_id, p2_game1.field[0].instance_id)
    
    # Ensure action queue is populated for serialization
    game1.determine_card_action_order() # This is normally called by advance_game_state to ATTACK phase

    print(f"\nOriginal Game Log (length {len(game1.game_log)}):")
    # for log_entry in game1.game_log[-5:]: print(f"  {log_entry}") # Print last 5 log entries
    
    game1_dict = game1.to_dict()
    print(f"\nGame Serialized (sample keys): state='{game1_dict.get('game_state')}', current_player='{game1_dict.get('current_player_id')}', log_len={len(game1_dict.get('game_log',[]))}")
    # print(f"Full Serialized Game: {json.dumps(game1_dict, indent=2)}") # Can be very verbose

    reconstructed_game = Game.from_dict(game1_dict)
    print(f"\nReconstructed Game State: {reconstructed_game.game_state}")
    print(f"Reconstructed Current Player: {reconstructed_game.current_player_id}")
    
    recon_p1 = reconstructed_game.get_player(Game.PLAYER1_ID)
    recon_p2 = reconstructed_game.get_player(Game.PLAYER2_ID)

    print(f"Reconstructed P1 Hand Size: {len(recon_p1.hand) if recon_p1 else 'N/A'}")
    print(f"Reconstructed P1 Field Size: {len(recon_p1.field) if recon_p1 else 'N/A'}")
    if recon_p1 and recon_p1.field: print(f"  Recon P1 Field Card0 HP: {recon_p1.field[0].current_hp}")
    
    print(f"Reconstructed Action Queue Size: {len(reconstructed_game.current_round_action_queue)}")
    if reconstructed_game.current_round_action_queue: print(f"  Recon Action Queue Card0 Name: {reconstructed_game.current_round_action_queue[0].name}")

    assert reconstructed_game.game_state == game1.game_state, "Game state mismatch."
    assert reconstructed_game.current_player_id == game1.current_player_id, "Current player ID mismatch."
    assert len(reconstructed_game.game_log) == len(game1.game_log), "Game log length mismatch."
    assert reconstructed_game.game_log == game1.game_log, "Game log content mismatch."
    
    assert len(recon_p1.field) == len(p1_game1.field), "P1 field card count mismatch."
    if p1_game1.field and recon_p1.field: # Ensure cards on field match by instance_id and HP
        assert recon_p1.field[0].instance_id == p1_game1.field[0].instance_id, "P1 field card instance_id mismatch."
        assert recon_p1.field[0].current_hp == p1_game1.field[0].current_hp, "P1 field card HP mismatch."

    assert len(recon_p2.field) == len(p2_game1.field), "P2 field card count mismatch."

    assert len(reconstructed_game.current_round_action_queue) == len(game1.current_round_action_queue), "Action queue length mismatch."
    if game1.current_round_action_queue and reconstructed_game.current_round_action_queue:
         assert reconstructed_game.current_round_action_queue[0].instance_id == game1.current_round_action_queue[0].instance_id, "Action queue card mismatch."

    print("\nGame to_dict/from_dict test PASSED.")
    print("\nGame serialization test complete.")
