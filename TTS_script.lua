local translationStatus = {}

function onLoad()
    -- 오브젝트 로드시
    print("번역 시작")
    translateObjects()
end

function urlencode(str)
    -- URL 인코딩
    if str then
        str = string.gsub(str, "\n", "\r\n")
        str = string.gsub(str, "([^%w %-%_%.%~])",
            function(c) return string.format("%%%02X", string.byte(c)) end)
        str = string.gsub(str, " ", "+")
    end
    return str
end

function hasKorean(text)
    -- 한국어 존재 확인
    return text:find("[%z\1-\127\194-\244][\128-\191]")
end

function translateObjects()
    --메인로직
    for _, obj in ipairs(getAllObjects()) do
        if obj then
            --각 오브젝트마다 이름 가져오기
            local name = obj.getName()

            --한국어 있으면 번역 안함
            if name and name ~= "" and not hasKorean(name) then

                -- DFC 체크
                if obj.getStateId() ~= -1 then
                    -- 줄바꿈 이전의 데이터만 다음 함수로 보냄
                    local search_value = name:match("^[^\n]*"):gsub("^%s*(.-)%s*$", "%1")
                    translateDFC(search_value, obj)
                else
                    -- Single 카드와 Split 카드 처리
                    local search_value = name:match("^[^\n]*"):gsub("^%s*(.-)%s*$", "%1")
                    translateSingleOrSplitCard(search_value, obj)
                end
            end
        end
    end
end

function translateDFC(name, obj)
    --양면카드 로직

    local objID = obj.getGUID()
    -- GUID 기준으로 오브젝트 가져옴

    translationStatus[objID] = { translationCount = 0, totalTranslations = 0, data1 = nil, data2 = nil }
    --비동기 처리를 위한 변수생성 및 초기화

    local function onTranslationDone(version)
        local status = translationStatus[objID]
        if status then
            status.translationCount = status.translationCount + 1
            --비동기 처리를 위한 번역 횟수 추가 
            if status.translationCount == status.totalTranslations then
                -- 1번 상태의 번역이 완료 되었다면 해당 로직 실행

                if obj and obj.setState then
                    obj.setState(2)
                end
                -- 오브젝트에 상태가 정상적으로 있는지 검사 후 상태 변경

                for _, obj2 in ipairs(getObjects()) do
                    if obj2 then
                        local name2 = obj2.getName()
                        if name2 and name2 ~= "" and not hasKorean(name2) and obj2.getStateId() == 2 then
                            local search_value2 = name2:match("^[^\n]*"):gsub("^%s*(.-)%s*$", "%1")
                            translateSingleOrSplitCard(search_value2, obj2)

                            -- 이 부분에 obj2.setState(1)를 하고 싶은데 에러발생 
                        end
                    end
                end
                -- 다시 오브젝트를 가져와서 검사 이후 번역 

            end
        end
    end

    if obj.getStateId() == 1 then
        -- 1번상태일때 번역 로직 
        if name:find(" // ") then
            local data1, data2 = name:match("^(.-) // (.-)$")
            if data1 and data2 then
                translationStatus[objID].totalTranslations = 2
                -- 비동기 처리를 위해 변수 세팅
                requestTranslation(data1, obj, "data1", function() onTranslationDone("data1") end)
                requestTranslation(data2, obj, "data2", function() onTranslationDone("data2") end)
                -- 콜백함수 호출
            end
        else
            -- Single card translation request
            translationStatus[objID].totalTranslations = 1
            requestTranslation(name, obj, "single", function() onTranslationDone("single") end)
        end
    end
end

function translateSingleOrSplitCard(name, obj)
    local objID = obj.getGUID()
    translationStatus[objID] = { translationCount = 0, totalTranslations = 0, data1 = nil, data2 = nil }

    if name:find(" // ") then
        -- Handle Split/Adventure cards
        local data1, data2 = name:match("^(.-) // (.-)$")
        if data1 and data2 then
            translationStatus[objID].totalTranslations = 2
            requestTranslation(data1, obj, "data1", function() applySplitTranslation(obj) end)
            requestTranslation(data2, obj, "data2", function() applySplitTranslation(obj) end)
        end
    else
        -- Single card translation request
        translationStatus[objID].totalTranslations = 1
        requestTranslation(name, obj, "single", function() applySingleTranslation(obj) end)
    end
end

function requestTranslation(name, obj, version, callback)
    local url = "https://mtgapi-ko.onrender.com/translate?search_value=" .. urlencode(name)
    WebRequest.get(url, function(request)
        handleResponse(request, obj, version, callback)
    end)
end

function handleResponse(request, obj, version, callback)
    local objID = obj.getGUID()
    if request.is_done and not request.is_error then
        local data = JSON.decode(request.text)
        if data and not data.error then
            local status = translationStatus[objID]
            if status then
                if version == "single" then
                    applySingleTranslation(obj, data)
                elseif version == "data1" or version == "data2" then
                    status[version] = data
                    if status.data1 and status.data2 then
                        applySplitTranslation(obj)
                        translationStatus[objID] = nil -- Clear results for next object
                    end
                end
                if callback then
                    callback()
                end
            end
        end
    else
        print("서버에 응답이 없습니다.")
    end
end

function applySingleTranslation(obj, data)
    -- Apply translation data for single cards

    if not data or not data.card_name then
        return
    end

    local name = data.card_name or obj.getName()
    local typeName = data.type or ""
    local subType = data.sub_type or ""

    -- Format name and type information
    local fullName = name .. "\n" .. typeName

    if subType ~= "" then
        fullName = fullName .. " — " .. subType
    end

    local originalName = obj.getName()
    local manaValueNumber = originalName:match("(%d+)%s*CMC")
    if manaValueNumber ~= "" then
        fullName = fullName .. "\n" .. manaValueNumber .. "CMC"
    end

    if obj and obj.setName then
        obj.setName(fullName)
    end

    -- Set description with translated text, power, and toughness
    local translatedText = data.text or obj.getDescription()
    local power = data.power or ""
    local toughness = data.toughness or ""
    local flavorText = data.flavor_text or ""

    if power ~= "" and toughness ~= "" then
        translatedText = translatedText .. "\n" .. power .. "/" .. toughness
    end

    if power == "" and toughness ~= "" then
        translatedText = translatedText .. "\n" .. "충성도 : " .. toughness
    end

    translatedText = translatedText .. "\n [sup][i]" .. flavorText .. "[/i][/sup]"

    if obj and obj.setDescription then
        obj.setDescription(translatedText)
    end
end

function applySplitTranslation(obj)
    local objID = obj.getGUID()
    local status = translationStatus[objID]
    if not status then return end

    local data1 = status.data1
    local data2 = status.data2

    if not data1 or not data2 then
        return
    end

    -- Apply translation data for split/adventure cards
    local name1 = data1.card_name or ""
    local name2 = data2.card_name or ""
    local typeName1 = data1.type or ""
    local typeName2 = data2.type or ""
    local subType1 = data1.sub_type or ""
    local subType2 = data2.sub_type or ""
    local manaValue1 = data1.mana_value or ""
    local manaValue2 = data2.mana_value or ""
    local names = name1 .. "//" .. name2

    if subType1 ~= "" then
        typeName1 = typeName1 .. " — " .. subType1
    end
    if subType2 ~= "" then
        typeName2 = typeName2 .. " — " .. subType2
    end

    local typeNames = typeName1 .. "//" .. typeName2

    local originalName = obj.getName()
    local manaValueNumber = originalName:match("(%d+)%s*CMC")
    local manaValue = manaValueNumber ~= "" and (manaValueNumber .. "CMC") or ""

    local fullName = names .. "\n" .. typeNames .. "\n" .. manaValue
    if obj and obj.setName then
        obj.setName(fullName)
    end

    local translatedText1 = data1.text or obj.getDescription()
    local power1 = data1.power or ""
    local toughness1 = data1.toughness or ""
    local translatedText2 = data2.text or obj.getDescription()
    local power2 = data2.power or ""
    local toughness2 = data2.toughness or ""

    if power1 ~= "" and toughness1 ~= "" then
        translatedText1 = translatedText1 .. "\n" .. power1 .. "/" .. toughness1
    end

    if power2 ~= "" and toughness2 ~= "" then
        translatedText2 = translatedText2 .. "\n" .. power2 .. "/" .. toughness2
    end

    if obj and obj.setDescription then
        obj.setDescription(name1 .. "\n----------\n" .. (translatedText1 or "") .. "\n\n" .. name2 .. "\n----------\n" .. (translatedText2 or ""))
    end
end

-- "매직 한국어 번역기" is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC