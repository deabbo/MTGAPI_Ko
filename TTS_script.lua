local translations = {}

function onSave()
    return JSON.encode(translations)  -- JSON 데이터를 오브젝트 상태로 저장
end

function onLoad(saved_data)
    if saved_data and saved_data ~= "" then
        translations = JSON.decode(saved_data)  -- 오브젝트 상태에서 JSON 데이터를 불러옴
        print("Translations loaded!")
        translate()
    else
        print("No saved data found.")
    end
end


function translate()
    printToAll("start translating...")
    for i, o in ipairs(getAllObjects()) do
        if o ~= self and o.hasTag("Translator") == false then
            local name = o.getName()
            local desc = o.getDescription()
            if checkNotEmptyNameDesc(name) then
                processText(name, o, "name")
            end
            if checkNotEmptyNameDesc(desc) then
                processText(desc, o, "desc")
            end
        end
    end
end

function checkNotEmptyNameDesc(s)
    return s ~= nil and s ~= "" and s ~= " "
end

-- 텍스트를 JSON 데이터와 비교하여 치환하는 함수
function processText(s, o, type)
    if type == "name" then
        local words = splitTextBySpaces(s)  -- 공백으로 분리
        local translatedText = ""
        for _, word in ipairs(words) do
            local translatedWord = getTranslation(word)
            if translatedWord then
                translatedText = translatedText .. translatedWord .. " "
            else
                translatedText = translatedText .. word .. " "
            end
        end
        o.setName(translatedText:sub(1, -2))  -- 마지막 공백 제거
    elseif type == "desc" then
        local sentences = splitTextByNewlines(s)  -- 줄바꿈으로 분리
        local translatedText = ""
        for _, sentence in ipairs(sentences) do
            local translatedSentence = getTranslation(sentence)
            if translatedSentence then
                translatedText = translatedText .. translatedSentence .. "\n"
            else
                translatedText = translatedText .. sentence .. "\n"
            end
        end
        o.setDescription(translatedText:sub(1, -2))  -- 마지막 줄바꿈 제거
    end
end

-- 공백으로 텍스트 분리
function splitTextBySpaces(text)
    local words = {}
    for word in text:gmatch("%S+") do
        table.insert(words, word)
    end
    return words
end

-- 줄바꿈으로 텍스트 분리
function splitTextByNewlines(text)
    local sentences = {}
    for sentence in text:gmatch("[^\n]+") do
        table.insert(sentences, sentence)
    end
    return sentences
end

-- JSON 데이터에서 영어 텍스트에 맞는 한국어 텍스트를 반환하는 함수
function getTranslation(englishText)
    for _, entry in ipairs(translations) do
        if entry.enUS == englishText then
            return entry.koKR
        end
    end
    return nil
end