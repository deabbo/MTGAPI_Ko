import sqlite3
import glob
import json
import re
import sys
import string

ANNOTATION_DATA = {}

# annotation_data 딕셔너리 전체를 출력하는 디버깅 코드 예시

# def debug_print_annotation_data(annotation_data, filename="annotation_debug_log.txt"):
#     with open(filename, 'w', encoding='utf-8') as f:
#         f.write("[DEBUG] Annotation Data Dump:\n\n")
#         for key, value in annotation_data.items():
#             f.write(f"Key: {key}\n")
#             # value가 str인 경우
#             if isinstance(value, str):
#                 f.write(f"  koKR: {value}\n\n")
#             # value가 dict인 경우
#             elif isinstance(value, dict):
#                 en_text = value.get("enUS", "<no enUS>")

#                 ko_text = value.get("koKR", "<no koKR>")
#                 f.write(f"  enUS: {en_text}\n")
#                 f.write(f"  koKR: {ko_text}\n\n")
#             else:
#                 f.write(f"  Value: {value}\n\n")
#     print(f"Annotation data dumped to {filename}")



# 사용 예시
# debug_print_annotation_data(annotation_data)

# 위 코드를 실제 실행 위치에서 호출하여 annotation_data 내용을 확인하세요.

def load_localization_data():
    """Load annotation data from the Raw_ClientLocalization_*.mtga file and process koKR text."""
    global ANNOTATION_DATA
    localization_files = glob.glob('Raw_ClientLocalization_*.mtga')
    if not localization_files:
        print("No localization files found.")
        return
    
    localization_file = localization_files[0]  # Use the first localization file found
    try:
        conn = sqlite3.connect(localization_file)
        cursor = conn.cursor()

        # Select all localization data for AbilityHanger/Keyword
        cursor.execute('''
            SELECT Key, koKR 
            FROM loc
            WHERE Key LIKE 'AbilityHanger/Keyword/%'
        ''')
        rows = cursor.fetchall()

        for key, kokr in rows:
            cleaned_kokr = process_kokr_text(kokr)

            # Strip suffixes like _Body, digits, and letters from the end of key base
            base_key = key.replace('_Body', '')
            base_key = re.sub(r'[\dA-Z_]+$', '', base_key)
            normalized_key = base_key.lower()
            no_space_key = re.sub(r'\s+', '', normalized_key)

            # Store under multiple normalized forms
            for k in {normalized_key, no_space_key}:
                if k not in ANNOTATION_DATA:
                    ANNOTATION_DATA[k] = cleaned_kokr.strip()

    except sqlite3.Error as e:
        print(f"Error reading localization data: {e}")
    finally:
        if conn:
            conn.close()
    
    # debug_print_annotation_data(ANNOTATION_DATA)



def process_kokr_text(text):
    """Process koKR text to replace patterns as specified."""
    # Replace {abilityCost} with 비용
    text = re.sub(r'\s*,?\s*\{abilityCost\}\s*,?\s*', '', text)
    
    # Replace {oX} patterns with only the content inside (remove o and braces)
    text = re.sub(r'\{o([A-Za-z0-9]+)\}', r'\1', text)
    
    # Extract name="x?" and replace with the value of ? only
    text = re.sub(r'<[^>]*name="x([A-Za-z0-9])"[^>]*>', r'\1', text)
    
    return text

def clean_ability_name(ability_name):
    """
    Remove trailing numerals or X, trim whitespace, keep {} templates,
    remove most punctuation, and convert to lowercase.
    """
    # Remove trailing space + number or X
    cleaned_name = re.sub(r'\s+(\d+|x)$', '', ability_name.strip(), flags=re.IGNORECASE)
    
    # Remove punctuation except {}
    cleaned_name = re.sub(r'[^\w\s{}]', '', cleaned_name)

    return cleaned_name.lower()

def get_ability_annotation(ability_name):
    cleaned_name = clean_ability_name(ability_name)

    # 비용 포함 형태: 예) "ninjutsu {3BB}" → ability = "ninjutsu", cost = "{3BB}"
    ability_match = re.match(r'(\w+)\s+\{([^}]+)\}', ability_name)
    if ability_match:
        keyword = ability_match.group(1).lower()
        cost = ability_match.group(2)

        # 비용에서 'o' 제거 (예: o3BB -> 3BB)
        cost = remove_o_in_braces('{' + cost + '}').strip('{}')

        # 주석용 키 정규화
        body_key = f"AbilityHanger/Keyword/{keyword}".lower()
        body = ANNOTATION_DATA.get(body_key)

        if body:
            # 주석 본문에서 'o'가 들어간 부분 제거
            body = re.sub(r'o(?=[A-Z0-9])', '', body)
            # 비용 + 설명 (비용은 비용 문자열만, 쉼표 하나만)
            return f"{cost}, {body}"

    # 일반 키워드 처리
    base_key = f"AbilityHanger/Keyword/{cleaned_name}".lower()
    no_space_key = f"AbilityHanger/Keyword/{cleaned_name.replace(' ', '')}".lower()
    if base_key in ANNOTATION_DATA:
        annotation = ANNOTATION_DATA[base_key]
        annotation = re.sub(r'o(?=[A-Z0-9])', '', annotation)
        return annotation
    if no_space_key in ANNOTATION_DATA:
        annotation = ANNOTATION_DATA[no_space_key]
        annotation = re.sub(r'o(?=[A-Z0-9])', '', annotation)
        return annotation

    return None



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

def annotate_inline_keywords(text: str) -> str:
    if not text:
        return text

    annotated_keywords = set()

    for keyword_en, annotation in ANNOTATION_DATA.items():
        base_keyword = re.sub(r'\W+', '', keyword_en.lower())

        # 키워드가 포함된 단어들까지 포괄적으로 감지 (예: 'mobilize 2', 'gains mobilize 2')
        pattern = re.compile(rf'(?<!\w)({keyword_en}\s*\d*)(?!\w)', re.IGNORECASE)

        def replacer(match):
            full_keyword = match.group(1)
            keyword_part = full_keyword.split()[0]  # mobilize
            key_base = re.sub(r'\W+', '', keyword_part.lower())

            if key_base == base_keyword and key_base not in annotated_keywords:
                annotated_keywords.add(key_base)
                return f"{full_keyword} ({annotation})"
            return full_keyword

        text = pattern.sub(replacer, text)

    return text

def process_ability_ids(cursor, ability_ids, subtype_id):

    text_parts = []
    annotationed_parts = []
    ability_id_list = ability_ids.split(',')
    
    # Check if 260 is in the list 미리읽기일 경우 
    include_260 = '260' in ability_id_list
    
    # Create a list of ability parts
    for idx, ability_id in enumerate(ability_id_list):

        parts = ability_id.split(':')
        loyalty_cost = None
        loc_id = parts[-1]  # The part after the last ':'
        
        if len(parts) == 1: # : 로 나뉘어져있지 않다면 
            cursor.execute('''
                SELECT TextId, LoyaltyCost
                FROM abilities 
                WHERE Id = ?
            ''', (loc_id,))
            text_id_result = cursor.fetchone()
            if text_id_result:
                text_id = text_id_result[0]
                loyalty_cost = text_id_result[1]
                loc_id = text_id
        
        enUS_value = get_localization_value(cursor, loc_id, 'enUS')
        koKR_value = get_localization_value(cursor, loc_id, 'koKR')
        annotation = get_ability_annotation(enUS_value) if enUS_value else None

        if koKR_value:
            if subtype_id == 227020:  # 서사시라면
                if ability_id == '260':  # 미리읽기라면
                    text_parts.append(koKR_value)
                    annotationed_parts.append(koKR_value)
                else:
                    index = ability_id_list.index(ability_id) + 1
                    if include_260:
                        index -= 1
                    numbered_text = f"{index} — {koKR_value}"
                    text_parts.append(numbered_text)
                    annotationed_parts.append(numbered_text)
            elif loyalty_cost:  # 플레인즈워커라면
                formatted_text = f"{loyalty_cost} : {koKR_value}"
                text_parts.append(formatted_text)
                annotationed_parts.append(formatted_text)
            else:  # 그 이외 능력일시
                plain_text = koKR_value
                annotationed_text = koKR_value
                if annotation:
                    annotationed_text += f" [sup][{annotation}][/sup]"
                annotationed_text = annotate_inline_keywords(annotationed_text)

                text_parts.append(plain_text)
                annotationed_parts.append(annotationed_text)
                

    plain_text = '\n'.join(text_parts)
    annotationed_text = '\n'.join(annotationed_parts)
    return plain_text, annotationed_text

def fetch_data_and_create_json(file):
    """Fetch data from the database and create a JSON file."""
    print(f"Processing file: {file}")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(file)
        cursor = conn.cursor()

        load_localization_data()
        
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
                c.abilityIds AS ability_ids,
                c.Order_MythicToCommon AS rarity_number,
                c.Colors AS colors
            FROM Cards c
            WHERE c.GrpId > 10
        ''')

        rows = cursor.fetchall()

        # Create JSON data
        data = []
        seen_search_values = set()

        for row in rows:
            (arena_id, title_id, type_id, subtype_id, mana_value, power, toughness, flavor_text_id, ability_ids, rarity_number, colors) = row

            # Find card_name using TitleId
            card_name = get_localization_value(cursor, title_id, 'koKR') if title_id else None
            search_value = get_localization_value(cursor, title_id, 'enUS') if title_id else None
            type_name = get_localization_value(cursor, type_id, 'koKR') if type_id else None
            subtype_name = get_localization_value(cursor, subtype_id, 'koKR') if subtype_id else None
            flavor_text = get_localization_value(cursor, flavor_text_id, 'koKR') if flavor_text_id and flavor_text_id != '1' else None
            rarity = None
            color = None

            if rarity_number is not None:
                if rarity_number == 0:
                    rarity = "미식레어"
                elif rarity_number == 1:
                    rarity = "레어"
                elif rarity_number == 2:
                    rarity = "언커먼"
                elif rarity_number >= 3:
                    rarity = "커먼"
            else:
                rarity = "커먼"

            if colors is not None:
                color_list = colors.split(',')
                if len(color_list) > 1:
                    color = "다색"
                elif len(color_list) == 1:
                    color_number = color_list[0]
                    if color_number == "1":
                        color = "백색"
                    elif color_number == "2":
                        color = "청색"
                    elif color_number == "3":
                        color = "흑색"
                    elif color_number == "4":
                        color = "적색"
                    elif color_number == "5":
                        color = "녹색"
                else:
                    color = "무색"
            else: 
                color = "무색"

            # Process ability text
            if ability_ids:
                plain_text, annotationed_text = process_ability_ids(cursor, ability_ids, subtype_id)
            else:
                plain_text = annotationed_text = None

            if search_value in seen_search_values:
                continue
            seen_search_values.add(search_value)
            
            # Create record
            record = {
                'arena_id': arena_id,
                'search_value': search_value,
                'card_name': card_name,
                'rarity': rarity,
                'color': color
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
            if plain_text:
                record['text'] = plain_text
            if annotationed_text:
                record['annotationed_text'] = annotationed_text
            
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
