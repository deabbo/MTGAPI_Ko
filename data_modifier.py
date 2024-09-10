import sqlite3
import glob
import json
import re
import sys

def remove_o_in_braces(text):
    """Remove 'o' characters within braces {}."""
    return re.sub(r'\{[^}]*o[^}]*\}', lambda m: m.group(0).replace('o', ''), text)

def replace_html_tags_with_brackets(text):
    """Replace HTML tags with brackets [] instead of removing them."""
    return re.sub(r'<[^>]*>', lambda m: f'[{m.group(0)}]', text)

def clean_hash_prefix(text):
    """Remove the leading '#' from any word starting with '#'."""
    return re.sub(r'\b#(\S+)', r'\1', text)

def clean_localizations_koKR(cursor, koKR, loc_id):
    """Clean and update the koKR field in the Localizations table."""
    cleaned_koKR = remove_o_in_braces(koKR)
    cleaned_koKR = replace_html_tags_with_brackets(cleaned_koKR)
    cleaned_koKR = clean_hash_prefix(cleaned_koKR)
    cursor.execute('''
        UPDATE Localizations
        SET koKR = ?
        WHERE LocId = ?
    ''', (cleaned_koKR, loc_id))

def delete_wrong_value(cursor):
    """Delete rows where Formatted = 2 from the Localizations table."""
    cursor.execute('''
        DELETE FROM Localizations
        WHERE Formatted = 2 or koKR LIKE '#%'
    ''')
    print("Deleted wrong rows")

def get_localization_value(cursor, loc_id, lang_col):
    """
    Retrieve the localization value from the Localizations table.
    First prioritize the row where Formatted = 0.
    If no row exists with Formatted = 0, then prioritize Formatted = 1.
    """
    cursor.execute(f'''
        SELECT {lang_col}
        FROM Localizations
        WHERE LocId = ?
        ORDER BY Formatted ASC
        LIMIT 1
    ''', (loc_id,))
    
    result = cursor.fetchone()
    return result[0] if result else None

def process_ability_ids(cursor, ability_ids, subtype_id):
    """
    Process ability_ids to return a newline-separated string of koKR values with optional numbering.
    If ability_ids contains 260, it will be included as-is. Other IDs will be numbered sequentially.
    """
    text_parts = []
    ability_id_list = ability_ids.split(',')
    
    # Check if 260 is in the list
    include_260 = '260' in ability_id_list
    
    # Create a list of ability parts
    for idx, ability_id in enumerate(ability_id_list):
        parts = ability_id.split(':')
        loc_id = parts[-1]  # The part after the last ':'
        
        if len(parts) == 1:
            cursor.execute('''
                SELECT TextId 
                FROM abilities 
                WHERE Id = ?
            ''', (loc_id,))
            text_id_result = cursor.fetchone()
            if text_id_result:
                text_id = text_id_result[0]
                loc_id = text_id
        
        koKR_value = get_localization_value(cursor, loc_id, 'koKR')
        
        if koKR_value:
            if subtype_id == 227020:
                if ability_id == '260':
                    text_parts.append(koKR_value)
                else:
                    index = ability_id_list.index(ability_id) + 1
                    if include_260:
                        index = index - 1
                    text_parts.append(f"{index} — {koKR_value}")
            else:
                text_parts.append(koKR_value)
                
    return '\n'.join(text_parts)

def fetch_data_and_create_json(file):
    """Fetch data from the database and create a JSON file."""
    print(f"Processing file: {file}")

    try:
        # Connect to the database
        conn = sqlite3.connect(file)
        cursor = conn.cursor()

        # Delete all rows where Formatted = 2
        delete_wrong_value(cursor)
        conn.commit()  # Commit the delete changes to the database

        # Clean the koKR field in the Localizations table
        cursor.execute('SELECT LocId, koKR FROM Localizations')
        rows = cursor.fetchall()
        for loc_id, koKR in rows:
            clean_localizations_koKR(cursor, koKR, loc_id)
        
        # Fetch data from the Cards table
        cursor.execute('''
            SELECT 
                c.GrpId AS arena_id,
                c.TitleId AS title_id,
                c.TypeTextId AS type_id,
                c.SubtypeTextId AS subtype_id,
                c.Order_CMCWithXLast AS mana_value,
                c.Power AS power,
                c.Toughness AS toughness,
                c.FlavorTextId AS flavor_text_id,
                c.abilityIds AS ability_ids
            FROM Cards c
            WHERE c.GrpId > 10
        ''')

        rows = cursor.fetchall()

        # Create JSON data
        data = []
        for row in rows:
            (arena_id, title_id, type_id, subtype_id, mana_value, power, toughness, flavor_text_id, ability_ids) = row

            # Find card_name using TitleId
            card_name = get_localization_value(cursor, title_id, 'koKR') if title_id else None
            search_value = get_localization_value(cursor, title_id, 'enUS') if title_id else None
            type_name = get_localization_value(cursor, type_id, 'koKR') if type_id else None
            subtype_name = get_localization_value(cursor, subtype_id, 'koKR') if subtype_id else None
            flavor_text = get_localization_value(cursor, flavor_text_id, 'koKR') if flavor_text_id and flavor_text_id != '1' else None
            text = process_ability_ids(cursor, ability_ids, subtype_id) if ability_ids else None

            # Create record
            record = {
                'arena_id': arena_id,
                'search_value': search_value,
                'card_name': card_name
            }
            if mana_value is not None:
                record['mana_value'] = mana_value
            if type_name:
                record['type'] = type_name
            if subtype_name:
                record['sub_type'] = subtype_name
            if power:
                record['power'] = power
            if toughness:
                record['toughness'] = toughness
            if flavor_text:
                record['flavor_text'] = flavor_text
            if text:
                record['text'] = text
            
            data.append(record)

        ping_record = {
            'search_value': 'ping',
            'text': '성공'
        }

        data.append(ping_record)

        # Write data to JSON file
        with open('cards_data_for_api.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"Data has been written to cards_data.json")

    except sqlite3.Error as e:
        print(f"Error occurred: {e}")

    finally:
        if conn:
            conn.close()

# Main logic
files = glob.glob('Raw_CardDatabase_*.mtga')

if not files:
    print("No files found. Please ensure that you are running this script in the correct directory.")
    sys.exit()

for file in files:
    fetch_data_and_create_json(file)

print("All files processed.")
