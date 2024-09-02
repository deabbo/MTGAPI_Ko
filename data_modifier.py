import sqlite3
import glob
import json
import re
import sys

def remove_o_in_braces(text):
    return re.sub(r'\{[^}]*o[^}]*\}', lambda m: m.group(0).replace('o', ''), text)

def clean_localizations_koKR(cursor):

    cursor.execute('''
        UPDATE Localizations
        SET koKR = ?
        WHERE LocId = ?
    ''', (remove_o_in_braces(koKR), loc_id))

def get_localization_value(cursor, loc_id, lang_col):

    cursor.execute('''
        SELECT {} 
        FROM Localizations
        WHERE LocId = ?
        ORDER BY Formatted ASC
        LIMIT 1
    '''.format(lang_col), (loc_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def process_ability_ids(cursor, ability_ids):
    """
    ability_ids를 처리하여 줄바꿈으로 구분된 koKR 값을 반환합니다.
    """
    text_parts = []
    for ability_id in ability_ids.split(','):

        parts = ability_id.split(':')
        loc_id = parts[-1] 
        
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
            text_parts.append(koKR_value)
    
    return '\n'.join(text_parts)

def fetch_data_and_create_json(file):
    print(f"Processing file: {file}")

    try:
        # 데이터베이스 연결
        conn = sqlite3.connect(file)
        cursor = conn.cursor()

        # Localizations 테이블의 koKR 컬럼에서 중괄호 {} 안의 'o'를 제거
        cursor.execute('SELECT LocId, koKR FROM Localizations')
        rows = cursor.fetchall()
        for loc_id, koKR in rows:
            cleaned_koKR = remove_o_in_braces(koKR)
            cursor.execute('''
                UPDATE Localizations
                SET koKR = ?
                WHERE LocId = ?
            ''', (cleaned_koKR, loc_id))
        
        # 데이터 추출 쿼리
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
        ''')

        rows = cursor.fetchall()

        # JSON 데이터 생성
        data = []
        for row in rows:
            (arena_id, title_id, type_id, subtype_id, mana_value, power, toughness, flavor_text_id, ability_ids) = row

            # TitleId를 통해 card_name을 찾기
            card_name = get_localization_value(cursor, title_id, 'koKR') if title_id else None
            search_value = get_localization_value(cursor, title_id, 'enUS') if title_id else None
            type_name = get_localization_value(cursor, type_id, 'koKR') if type_id else None
            subtype_name = get_localization_value(cursor, subtype_id, 'koKR') if subtype_id else None
            flavor_text = get_localization_value(cursor, flavor_text_id, 'koKR') if flavor_text_id and flavor_text_id == '1' else None
            text = process_ability_ids(cursor, ability_ids) if ability_ids else None

            # 레코드 생성
            record = {
                'arena_id': arena_id,
                'search_value': search_value,
                'card_name': card_name
            }
            if mana_value:
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

        # JSON 파일로 저장
        with open('cards_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"Data has been written to cards_data.json")

    except sqlite3.Error as e:
        print(f"Error occurred: {e}")

    finally:
        if conn:
            conn.close()

# 메인 로직
files = glob.glob('Raw_CardDatabase_*.mtga')

if not files:
    print("No files found. Please ensure that you are running this script in the correct directory.")
    sys.exit()

for file in files:
    fetch_data_and_create_json(file)

print("All files processed.")
