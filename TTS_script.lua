function onLoad()
    -- Begin translation process when the script loads
    translateObjects()
end

function urlencode(str)
    if str then
        str = string.gsub(str, "\n", "\r\n")
        str = string.gsub(str, "([^%w %-%_%.%~])",
            function(c) return string.format("%%%02X", string.byte(c)) end)
        str = string.gsub(str, " ", "+")
    end
    return str	
end

function hasKorean(text)
    -- Check if the string contains Korean characters
    return text:find("[%z\1-\127\194-\244][\128-\191]")
end

function translateObjects()
    -- Fetch all objects on the board
    for _, obj in ipairs(getAllObjects()) do
        -- Get the name of each object
        local name = obj.getName()

        -- Only proceed if the object has a name and doesn't contain Korean characters
        if name and name ~= "" and not hasKorean(name) then
            -- Extract the first line, trimming whitespace
            local search_value = name:match("^[^\n]*"):gsub("^%s*(.-)%s*$", "%1")

            -- Send the API request
            requestTranslation(search_value, obj)
        end
    end
end

function requestTranslation(name, obj)
    local url = "https://mtgapi-ko.onrender.com/translate?search_value=" .. urlencode(name)

    -- Perform a web request to get the translation data
    WebRequest.get(url, function(request)
        handleResponse(request, obj)
    end)
end

function handleResponse(request, obj)
    if request.is_done and not request.is_error then
        local data = JSON.decode(request.text)

        if data and not data.error then
            -- Prepare the formatted name
            local translatedName = data["card_name"] or obj.getName()
            local typeName = data["type"] or ""
            local subType = data["sub_type"] or ""
            local manaValue = data["mana_value"] or ""
            
            -- Concatenate name, type, subtype, and mana value
            local fullName = translatedName .. "\n" .. typeName
            if subType ~= "" then
                fullName = fullName .. " — " .. subType
            end
            if manaValue ~= "" then
                fullName = fullName .. " " .. manaValue .. "CMC"
            end
            
            -- Set the object's name
            obj.setName(fullName)

            -- Prepare the description
            local translatedText = data["text"] or obj.getDescription()
            local power = data["power"] or ""
            local toughness = data["toughness"] or ""
            
            -- Add power/toughness if they exist
            if power ~= "" and toughness ~= "" then
                translatedText = translatedText .. "\n" .. power .. "/" .. toughness
            end
            
            -- Set the object's description
            obj.setDescription(translatedText)
        end
    else
        print("API 요청 실패")
    end
end

-- "매직 한국어 번역기" is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC