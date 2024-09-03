from flask import Flask, request, jsonify, Response
import requests
import json

api = Flask(__name__)

def load_translations():
    url = "https://www.dropbox.com/scl/fi/f9owyp4m25ewq4lq1kl9f/cards_data.json?rlkey=kdg8hvf6unumvrsi0lxvmorfa&st=y2y2eq4h&dl=1"  
    response = requests.get(url)

    if response.status_code != 200:
            print(f"Failed to fetch JSON. Status code: {response.status_code}")
            return {}

    try:
        response.encoding = 'utf-8'
        return response.json()
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

