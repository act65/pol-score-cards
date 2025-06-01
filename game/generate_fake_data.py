import json # Standard library for JSON
import random
from typing import Optional
from dataclasses import dataclass, asdict # For creating data classes and converting to dict
from game_logic import Attributes, PoliticianCard

# --- Configuration & Mock Data Constants ---
MOCK_STAT_MIN = 0
MOCK_STAT_MAX = 100

FIRST_NAMES = [
    "Aisha", "Boris", "Chandra", "Darius", "Elena", "Finn", "Gabriela", "Hiroshi",
    "Isabelle", "Jamal", "Katerina", "Liam", "Mei", "Nabil", "Olivia", "Pavel",
    "Quintessa", "Raj", "Sofia", "Tariq", "Uma", "Viktor", "Willow", "Xavier",
    "Yara", "Zane", "Eleanor", "Marcus", "Vivian", "Oscar", "Amelia", "Benjamin",
    "Clara", "Daniel", "Eva", "Felix", "Grace", "Henry", "Iris", "Jack"
]
LAST_NAMES = [
    "Khan", "Petrov", "Singh", "Rodriguez", "Volkov", "O'Connell", "Kim", "Silva",
    "Andersson", "Dubois", "Schmidt", "Nakamura", "Kowalski", "Chen", "Hassan",
    "Ramos", "Müller", "Ivanov", "Smith", "Jones", "Patel", "Garcia", "Williams",
    "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas"
]
PARTIES = [
    "Innovate Party", "Heritage Alliance", "Green Future Coalition",
    "People's Voice", "Centrist Union", "Liberty Front", "Progressive Path",
    "Common Ground Party", "New Horizons", "The Independents"
]

# --- MOCK DATA GENERATION FUNCTIONS (Your existing functions, slightly adapted) ---

def create_mock_attributes(
    strength: Optional[int] = None,
    divination: Optional[int] = None,
    charisma: Optional[int] = None,
    rigor: Optional[int] = None,
    specificity: Optional[int] = None,
    civility: Optional[int] = None,
    authenticity: Optional[int] = None,
    veracity: Optional[int] = None,
    forthrightness: Optional[int] = None,
) -> Attributes:
    # Instantiate GameConfig here or pass it if it's more complex/stateful
    return Attributes(
        strength=strength if strength is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX),
        divination=divination if divination is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX),
        charisma=charisma if charisma is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX), # Range for charisma
        rigor=rigor if rigor is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX),
        specificity=specificity if specificity is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX), # Usually want some specificity
        civility=civility if civility is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX),
        authenticity=authenticity if authenticity is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX), # Usually want some authenticity
        veracity=veracity if veracity is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX), # Veracity as a stat
        forthrightness=forthrightness if forthrightness is not None else random.randint(MOCK_STAT_MIN, MOCK_STAT_MAX),
    )

def generate_random_name() -> str:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}"

def create_mock_politician_card(
    card_id_num: int, # Used for ensuring unique IDs, especially if names could collide
    attributes: Optional[Attributes] = None
) -> PoliticianCard:
    name = generate_random_name()
    # Create a simple slug from the name for the ID
    name_slug = "".join(c if c.isalnum() or c == ' ' else '' for c in name).lower().replace(' ', '_')
    # Ensure slug is not empty if name was all symbols (unlikely with current names)
    if not name_slug:
        name_slug = "politician"
    card_id = f"pol_{name_slug}_{card_id_num}"
    party = random.choice(PARTIES)
    
    attrs = attributes if attributes else create_mock_attributes()
    
    return PoliticianCard(id=card_id, name=name, party=party, attributes=attrs)


# --- SCRIPT TO WRITE TO JSONL ---

def generate_politicians_jsonl(num_politicians: int, output_file: str):
    """
    Generates a specified number of mock politicians and writes them to a JSONL file.
    """
    politician_cards_data = []
    for i in range(num_politicians):
        politician_card = create_mock_politician_card(card_id_num=i)
        # Convert the dataclass instance to a dictionary for JSON serialization
        politician_cards_data.append(asdict(politician_card))

    # Try to use the 'jsonl' library if available (as per user's import)
    try:
        import jsonl # The library user specified
        # Common API for python-jsonl: open file and write records one by one
        with jsonl.open(output_file, mode='w') as writer:
            for record in politician_cards_data:
                writer.write(record)
            # Some jsonl libraries might also have: writer.write_all(politician_cards_data)
        print(f"Successfully wrote {num_politicians} politicians to {output_file} using 'jsonl' library.")

    except ImportError:
        print(f"'jsonl' library not found. Writing to {output_file} using standard 'json' library (manual JSONL format).")
        # Fallback to manual JSONL writing (one JSON object per line)
        with open(output_file, 'w') as f:
            for record in politician_cards_data:
                json.dump(record, f)
                f.write('\n')
        print(f"Successfully wrote {num_politicians} politicians to {output_file} (manual JSONL).")
    except Exception as e:
        # Catch other potential errors if 'jsonl' library is present but has an unexpected API
        print(f"An error occurred while using 'jsonl' library: {e}. Falling back to manual JSONL writing.")
        with open(output_file, 'w') as f:
            for record in politician_cards_data:
                json.dump(record, f)
                f.write('\n')
        print(f"Successfully wrote {num_politicians} politicians to {output_file} (manual JSONL after fallback).")


if __name__ == "__main__":
    NUMBER_OF_POLITICIANS_TO_GENERATE = 50  # You can change this number
    OUTPUT_FILENAME = "mock_politicians.jsonl" # Output file name
    
    print(f"Generating {NUMBER_OF_POLITICIANS_TO_GENERATE} mock politicians...")
    generate_politicians_jsonl(
        num_politicians=NUMBER_OF_POLITICIANS_TO_GENERATE,
        output_file=OUTPUT_FILENAME
    )
    print(f"Generation complete. Data saved to '{OUTPUT_FILENAME}'.")