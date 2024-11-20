from flask import Flask, request, jsonify, Response
import requests
import json

api = Flask(__name__)

def load_translations():
    local_file = "cached_translations.json"
    try:
        # 파일이 이미 로컬에 있다면 캐시된 데이터를 사용
        with open(local_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # 로컬에 없으면 원격에서 가져옴
        url = "https://github.com/deabbo/MTGAPI_Ko/raw/main/cards_data_for_api.json"  
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MyAPI/1.0)"
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"JSON 파일을 불러오는데 실패했습니다. 에러코드: {response.status_code}")
            return {}
        
        try:
            response.encoding = 'utf-8'
            data = response.json()
            # JSON 데이터를 로컬에 저장
            with open(local_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return data
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Response content: {response.text}")
            return {}



translations = load_translations()

@api.route('/translate', methods=['GET'])

def translate():

    search_value = request.args.get('search_value')

    if not search_value:
        return jsonify({"error": "텍스트 입력없음"}), 400
    
    matching_data = None
    for item in translations:
        if item.get("search_value") == search_value:
            matching_data = item
            break
    
    if matching_data:
        response_data = matching_data  
    else:
        response_data = {"error": "카드를 찾을 수 없습니다."}

    response = Response(
        response=json.dumps(response_data, ensure_ascii=False),
        mimetype='application/json'
    )
    
    return response


if __name__ == '__main__':
    api.run(host='0.0.0.0', port=5000)

