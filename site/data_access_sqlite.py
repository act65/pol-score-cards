import sqlite3

DATABASE_FILE = 'politician_data.db'
USE_DATABASE = True  # Set in app.py

def get_db():
    # ... (same get_db function as in app.py) ...
    pass

def query_db(query, args=(), one=False):
    # ... (same query_db function as in app.py) ...
    pass

def execute_db(query, args=()):
    # ... (same execute_db function as in app.py) ...
    pass

def get_all_politicians():
    return query_db("SELECT id, name, party, slug FROM politicians")

def get_attribute_description(attribute_name):
    result = query_db("SELECT display_name, description FROM attributes WHERE name = ?", [attribute_name], one=True)
    return dict(result) if result else None

def get_score(politician_slug, attribute_name):
    politician = query_db("SELECT id FROM politicians WHERE slug = ?", [politician_slug], one=True)
    if politician:
        result = query_db("SELECT score FROM scores WHERE politician_id = ? AND attribute_name = ?", [politician['id'], attribute_name], one=True)
        return result['score'] if result else None
    return None


def get_examples(politician_slug, attribute_name):
    politician = query_db("SELECT id FROM politicians WHERE slug = ?", [politician_slug], one=True)
    if politician:
        results = query_db("SELECT example_text, source_url FROM examples WHERE politician_id = ? AND attribute_name = ?", [politician['id'], attribute_name])
        return [dict(row) for row in results]
    return

def get_attribute_names():
    return [row['name'] for row in query_db("SELECT name FROM attributes")]