import sqlite3
import glob
import json
import re
import sys

ANNOTATION_DATA_DETAILED = {}

# 디버깅용 코드
def dump_annotation_data(filename="annotation_detailed_dump.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for core, data in ANNOTATION_DATA_DETAILED.items():
            f.write(f"== Keyword: {core} ==\n")
            for variant in data["variants"]:
                typ = variant["type"]
                en = variant["enUS"]
                ko = variant["koKR"]
                f.write(f" - [{typ}] {en} => {ko}\n")
            f.write("\n")

# 여러 함수들
def replace_html_tags_with_brackets(text):
    """Replace HTML tags with brackets [] instead of removing them."""
    return re.sub(r'<[^>]*>', lambda m: f'[{m.group(0)}]', text)

def clean_hash_prefix(text):
    """Remove the leading '#' from any word starting with '#'."""
    return re.sub(r'\b#(\S+)', r'\1', text)

def clean_localizations_koKR(cursor, koKR, loc_id):
    """Clean and update the koKR field in the Localizations table."""
    # 1. 중괄호 내 o제거 및 T → 탭 치환
    def replace_brace_costs(match):
        inside = match.group(1)  # 예: o1oB, oT
        if inside == "oT":
            return "탭"
        return inside.replace("o", "")

    cleaned_koKR = re.sub(r'\{([^}]+)\}', replace_brace_costs, koKR)

    # 2. HTML 태그 제거
    cleaned_koKR = replace_html_tags_with_brackets(cleaned_koKR)

    # 3. # 해시 prefix 제거
    cleaned_koKR = clean_hash_prefix(cleaned_koKR)
    cursor.execute('''
        UPDATE Localizations_koKR
        SET Loc = ?
        WHERE LocId = ?
    ''', (cleaned_koKR, loc_id))

def delete_wrong_value(cursor):
    """Delete rows where Formatted = 2 from the Localizations table."""
    cursor.execute('''
        DELETE FROM Localizations_koKR
        WHERE Formatted = 2 or Loc LIKE '#%'
    ''')
    print("Deleted wrong rows")

def process_kokr_text(text):
    """Process koKR text to replace patterns as specified."""
    # Replace {abilityCost} with 비용
    text = re.sub(r'\s*,?\s*\{abilityCost\}\s*,?\s*', '', text)
    
    # Replace {oX} patterns with only the content inside (remove o and braces)
    text = re.sub(r'\{o([A-Za-z0-9]+)\}', r'\1', text)
    
    # Extract name="x?" and replace with the value of ? only
    text = re.sub(r'<[^>]*name="x([A-Za-z0-9])"[^>]*>', r'\1', text)
    
    return text

def clean_ability_name_for_matching(ability_name):
    text = re.sub(r'\{[^}]*\}', '', ability_name)  # {o2} 등 제거
    return re.sub(r'\s+', '', text.lower())        # 공백 제거 + 소문자화

def replace_sprite_tags(text):
    def sprite_replacer(match):
        name = match.group(1)

        # 배경색 유색마나
        if name in {"{manaType0}"}:
            return "좌측 배경색의 유색마나"

        if name in {"{manaType2}"}:
            return "우측 배경색의 유색마나"
        
        # 혼합 피렉시아 마나
        if name == "{manaCombined}":
            return "혼합 피렉시아 마나"

        # 유색 피렉시아 마나: xP + WUBRG
        if re.fullmatch(r"xP{color}", name):
            return "유색 피렉시아 마나"

        # 유색마나: x + WUBRG
        if re.fullmatch(r"x{color}", name):
            return "유색마나"

        # 탭: xT
        if re.fullmatch(r"x[0-9A-Z]+", name):
            value = name[1:]
            if value == "T":
                return "탭"
            elif re.fullmatch(r"[WUBRG]{2}", value):
                return f"{value[0]} 또는 {value[1]}"
            else:
                return value

        # 그 외는 name 그대로 반환
        return name

    return re.sub(r'<sprite="[^"]+"\s+name="([^"]+)".*?>', sprite_replacer, text)

def normalize_braced_costs_for_card_text(text):
    """
    카드 텍스트에서 마나 비용 표현을 정제:
    - {oT} → 탭
    - {oU}, {oWB}, {o2} → U, WB, 2
    - {3} → 3
    - 중괄호는 제거
    """
    def replacer(match):
        content = match.group(1)  # 예: oU, 3, oWB 등
        if content.startswith('o'):
            value = content[1:]
            if value == 'T':
                return '탭'
            return value
        return content  # 그냥 숫자 등

    return re.sub(r'\{([^}]+)\}', replacer, text)


def replace_ability_cost_token(text):
    """
    어노테이션용 텍스트에서 {abilityCost} → 비용 치환
    """
    return re.sub(r'\s*,?\s*\{abilityCost\}\s*,?\s*', ' 비용 ', text)




def extract_core_key_and_type(full_key: str):
    """
    Key에서 중심 키워드와 타입(body/title 등)을 추출합니다.
    
    예:
    - 'AbilityHanger/Keyword/CasualtyN_Body' → ('casualty', 'body')
    - 'AbilityHanger/Keyword/Adapt4_Title' → ('adapt', 'title')
    - 'AbilityHanger/Keyword/Exploit' → ('exploit', 'body') ← 접미어 없으면 기본 body
    """
    key_part = full_key.split("AbilityHanger/Keyword/")[-1]
    
    # 중심 키워드 추출: 숫자/X 접미어 및 _Body/_Title 제거
    base_key = re.sub(r'(_Body|_Title)?$', '', key_part)
    base_key = re.sub(r'[\dXx]+$', '', base_key)
    core_keyword = base_key.lower()

    # 키 타입 결정
    if '_Body' in key_part:
        key_type = 'body'
    elif '_Title' in key_part:
        key_type = 'title'
    else:
        key_type = 'body'  # 접미어가 없으면 body로 간주

    return core_keyword, key_type


# 새로 만든 로직
def build_annotation_dictionary_from_file():
    """
    SQLite 파일에서 AbilityHanger/Keyword 관련 localization 데이터를 추출해 주석 사전 구조로 구성합니다
    """
    global ANNOTATION_DATA_DETAILED

    localization_files = glob.glob('Raw_ClientLocalization_*.mtga')
    if not localization_files:
        print("No localization files found.")
        return
    
    file_path = localization_files[0]  # Use the first localization file found

    try:
        conn = sqlite3.connect(file_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT Key, enUS, koKR 
            FROM loc
            WHERE Key LIKE 'AbilityHanger/Keyword/%'
        ''')
        rows = cursor.fetchall()

        for key, enus, kokr in rows:
            # flavor나 reminder 키는 아예 무시
            if '_FlavorText' in key or '_ReminderText' in key:
                continue

            core, key_type = extract_core_key_and_type(key)
            last_segment = key.split('/')[-1]
            kokr = replace_sprite_tags(kokr)
            kokr = replace_ability_cost_token(kokr)
            kokr = normalize_braced_costs_for_card_text(kokr)
            kokr = re.sub(r'\bo(\d)(?![\dA-Z])', r'\1', kokr)
            entry = {
                "key": key,
                "type": key_type,
                "enUS": enus.strip() if enus else "",
                "koKR": kokr.strip() if kokr else ""
            }
            if core not in ANNOTATION_DATA_DETAILED:
                ANNOTATION_DATA_DETAILED[core] = {"variants": []}
            ANNOTATION_DATA_DETAILED[core]["variants"].append(entry)

            if key_type == 'body' and '_Body' not in key:
                title_entry = {
                    "key": key,
                    "type": "title", 
                    "enUS": last_segment,  # crew1, amassorcs2 등
                    "koKR": kokr.strip() if kokr else ""
                }
                ANNOTATION_DATA_DETAILED[core]["variants"].append(title_entry)

    except sqlite3.Error as e:
        print(f"Error reading localization data: {e}")
    finally:
        if conn:
            conn.close()
    

def get_ability_annotation(ability_name):
    cleaned_name = clean_ability_name_for_matching(ability_name)

    # Step 1: title 매칭 → index 기준으로 바로 앞 body를 가져오기
    for core, data in ANNOTATION_DATA_DETAILED.items():
        variants = data["variants"]
        for idx, variant in enumerate(variants):
            if variant["type"] == "title":
                title_en = variant["enUS"].strip().lower()
                cleaned_title = re.sub(r'\s+', '', title_en)

                if cleaned_title and cleaned_title in cleaned_name:
                    # 정확한 짝: title의 바로 앞 index에 있는 body
                    if idx > 0 and variants[idx - 1]["type"] == "body":
                        body_koKR = variants[idx - 1]["koKR"]
                        if body_koKR:
                            return body_koKR

                    # fallback (혹시 잘못된 순서가 있다면)
                    for j in range(len(variants)):
                        if variants[j]["type"] == "body" and variants[j]["koKR"]:
                            return variants[j]["koKR"]

    # Step 2: core 키워드 매칭
    for core, data in ANNOTATION_DATA_DETAILED.items():
        if core in cleaned_name:
            body_entry = next(
                (v for v in data["variants"] if v["type"] == "body" and v["koKR"]),
                None
            )
            if body_entry:
                return body_entry["koKR"]

    return None





# 디버그용
def debug_get_ability_annotation(ability_name, debug_log_file="annotation_debug_log.txt"):
    cleaned_name = clean_ability_name_for_matching(ability_name)

    with open(debug_log_file, "a", encoding="utf-8") as log:
        log.write("{\n")
        log.write(f'  "input": "{ability_name}",\n')
        log.write(f'  "cleaned": "{cleaned_name}",\n')

        # Step 1: title 매칭
        for core, data in ANNOTATION_DATA_DETAILED.items():
            for variant in data["variants"]:
                if variant["type"] == "title":
                    title_en = variant["enUS"].strip().lower()
                    cleaned_title = re.sub(r'\s+', '', title_en)

                    if cleaned_title and cleaned_title in cleaned_name:
                        for core, data in ANNOTATION_DATA_DETAILED.items():
                            for variant in data["variants"]:
                                if variant["type"] == "title":
                                    title_en = variant["enUS"].strip().lower()
                                    cleaned_title = re.sub(r'\s+', '', title_en)

                                    if cleaned_title and cleaned_title in cleaned_name:
                                        if variant["koKR"]:  # ✅ 이거 바로 반환해야 함
                                            log.write('  "matched": {\n')
                                            log.write('    "type": "title",\n')
                                            log.write(f'    "key": "{title_en}",\n')
                                            log.write(f'    "koKR": "{variant["koKR"]}"\n')
                                            log.write('  }\n')
                                            log.write("}\n\n")
                                            return variant["koKR"]

        # Step 2: core 매칭
        for core, data in ANNOTATION_DATA_DETAILED.items():
            if core in cleaned_name:
                body_entry = next(
                    (v for v in data["variants"] if v["type"] == "body" and v["koKR"]),
                    None
                )
                if body_entry:
                    log.write('  "matched": {\n')
                    log.write('    "type": "core",\n')
                    log.write(f'    "key": "{core}",\n')
                    log.write(f'    "koKR": "{body_entry["koKR"]}"\n')
                    log.write('  }\n')
                    log.write("}\n\n")
                    return body_entry["koKR"]

        # 매칭 실패
        log.write('  "matched": null\n')
        log.write("}\n\n")
    return None


# 카드 데이터 베이스 처리 존

def get_localization_value(cursor, loc_id, lang_col):
    """
    Retrieve the localization value from the Localizations table.
    First prioritize the row where Formatted = 0.
    If no row exists with Formatted = 0, then prioritize Formatted = 1.
    """

    if lang_col == "koKR":
        cursor.execute(f'''
            SELECT Loc
            FROM Localizations_koKR
            WHERE LocId = ?
            ORDER BY Formatted ASC
            LIMIT 1
        ''', (loc_id,))
        
        result = cursor.fetchone()
    else:
        cursor.execute(f'''
            SELECT Loc
            FROM Localizations_enUS
            WHERE LocId = ?
            ORDER BY Formatted ASC
            LIMIT 1
        ''', (loc_id,))
        
        result = cursor.fetchone()
    
    return result[0] if result else None


def process_ability_ids(cursor, ability_ids, subtype_id):

    text_parts = []
    annotationed_parts = []
    ability_id_list = ability_ids.split(',')
    
    # Check if 260 is in the list 미리읽기일 경우 
    is_prelude_first = ability_id_list and ability_id_list[0].split(':')[-1] == '614628'
    
    # Create a list of ability parts
    for idx, ability_id in enumerate(ability_id_list):

        parts = ability_id.split(':')
        loyalty_cost = None
        loc_id = parts[-1]  # The part after the last ':'
        
        cursor.execute('''
            SELECT LoyaltyCost
            FROM Abilities 
            WHERE textId = ?
        ''', (loc_id,))
        result = cursor.fetchone()
        loyalty_cost = result[0] if result else None
        
        enUS_value = get_localization_value(cursor, loc_id, 'enUS')
        koKR_value = get_localization_value(cursor, loc_id, 'koKR')
        annotation = get_ability_annotation(enUS_value) if enUS_value else None
        
        if koKR_value:
            if subtype_id == 227020:  # 서사시
                if loc_id == '614628':
                    text_parts.append(koKR_value)
                    annotationed_parts.append(koKR_value)
                else:
                    base_index = ability_id_list.index(ability_id)
                    if is_prelude_first:
                        base_index -= 1
                    index = base_index + 1
                    numbered_text = f"{index} — {koKR_value}"

                    annotated_text = numbered_text
                    if annotation and annotation != "X":
                        annotated_text += f" [sup][{annotation}][/sup]"

                    text_parts.append(numbered_text)
                    annotationed_parts.append(annotated_text)
            elif loyalty_cost is not None:
                formatted_text = f"{loyalty_cost} : {koKR_value}"
                annotated_text = formatted_text
                if annotation and annotation != "X":
                    annotated_text += f" [sup][{annotation}][/sup]"
                text_parts.append(formatted_text)
                annotationed_parts.append(annotated_text)
            else:  # 그 이외 능력일시
                plain_text = koKR_value
                annotationed_text = koKR_value
                if annotation and annotation != "X":
                    annotationed_text += f" [sup][{annotation}][/sup]"
                annotationed_parts.append(annotationed_text)

                text_parts.append(plain_text)
                
                

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

        build_annotation_dictionary_from_file()
        # 디버깅용
        dump_annotation_data(filename="annotation_detailed_dump.txt") 
        # Delete all rows where Formatted = 2
        delete_wrong_value(cursor)
        conn.commit()  # Commit the delete changes to the database

        # Clean the koKR field in the Localizations table
        cursor.execute('SELECT LocId, Loc FROM Localizations_koKR')
        rows = cursor.fetchall()
        for loc_id, Loc in rows:
            clean_localizations_koKR(cursor, Loc, loc_id)
        
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
