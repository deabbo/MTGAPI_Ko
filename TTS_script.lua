function onLoad()
    -- 번역 시작
    translateObjects()
end

function translateObjects()
    -- 전체 오브젝트 가져오기
    for _, obj in ipairs(getAllObjects()) do
        -- 오브젝트 이름 가져오기
        local name = obj.getName()

        if name and name ~= "" and not containsKorean(name) then
            -- 줄바꿈 전까지의 내용을 가져와 공백 제거
            local search_value = name:match("^[^\n]*"):gsub("^%s*(.-)%s*$", "%1")

            -- API 요청 보내기
            requestTranslation(search_value, obj)
        end
    end
end

function requestTranslation(name, obj)
    local url = "https://mtgapi-ko.onrender.com/translate?search_value=" .. urlencode(name)

    WebRequest.get(url, function(request)
        handleResponse(request, obj)
    end)
end

function handleResponse(request, obj)
    if request.is_done and not request.is_error then
        local data = JSON.decode(request.text)

        if data and not data.error then
            -- 번역된 이름과 설명 설정
            local translatedName = data["card_name"] or obj.getName()
            local translatedDesc = data["text"] or obj.getDescription()

            obj.setName(translatedName)
            obj.setDescription(translatedDesc)
        else
            print("번역 데이터가 없습니다: " .. (data.error or ""))
        end
    else
        print("API 요청 실패")
    end
end

-- URL 인코딩 함수
function urlencode(str)
    if str then
        str = string.gsub(str, "\n", "\r\n")
        str = string.gsub(str, "([^%w %-%_%.%~])",
            function(c) return string.format("%%%02X", string.byte(c)) end)
        str = string.gsub(str, " ", "+")
    end
    return str
end

-- 한글 포함 여부를 확인하는 함수
function containsKorean(str)
    return string.find(str, "[\128-\191]") ~= nil
end
