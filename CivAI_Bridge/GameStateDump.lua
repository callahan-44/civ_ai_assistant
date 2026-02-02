-- CivAI Bridge: Game State Logger (LLM-Optimized v3)
-- Dumps compact, actionable game state to Lua.log for external AI advisor

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

local function round(num)
    if num == nil then return 0 end
    return math.floor(num * 10 + 0.5) / 10
end

local function cleanName(str)
    if str == nil then return nil end
    -- Remove all common prefixes
    str = str:gsub("^TERRAIN_", "")
    str = str:gsub("^FEATURE_", "")
    str = str:gsub("^RESOURCE_", "")
    str = str:gsub("^BUILDING_", "")
    str = str:gsub("^DISTRICT_", "")
    str = str:gsub("^IMPROVEMENT_", "")
    str = str:gsub("^UNIT_", "")
    str = str:gsub("^CIVILIZATION_", "")
    str = str:gsub("^LEADER_", "")
    str = str:gsub("^TECH_", "")
    str = str:gsub("^CIVIC_", "")
    -- Convert to Title Case: "GRASS_HILLS" -> "Grass Hills"
    str = str:gsub("_", " ")
    str = str:lower()
    str = str:gsub("(%a)([%w]*)", function(first, rest)
        return first:upper() .. rest
    end)
    return str
end

-- Remove redundant terrain from feature names (e.g., "Floodplains Grassland" -> "Floodplains")
local function cleanFeatureTerrain(featureName, terrainName)
    if featureName == nil then return nil end
    if terrainName == nil then return featureName end
    -- Remove trailing terrain name from feature if present
    local pattern = " " .. terrainName .. "$"
    return featureName:gsub(pattern, "")
end

local function EscapeString(str)
    if str == nil then return "null" end
    str = tostring(str)
    str = str:gsub('\\', '\\\\')
    str = str:gsub('"', '\\"')
    str = str:gsub('\n', '\\n')
    str = str:gsub('\r', '\\r')
    str = str:gsub('\t', '\\t')
    return '"' .. str .. '"'
end

local function ToJSON(value, visited)
    visited = visited or {}
    if value == nil then
        return "null"
    elseif type(value) == "boolean" then
        return value and "true" or "false"
    elseif type(value) == "number" then
        return tostring(value)
    elseif type(value) == "string" then
        return EscapeString(value)
    elseif type(value) == "table" then
        if visited[value] then return '"[circular]"' end
        visited[value] = true
        local isArray = true
        local maxIndex = 0
        for k, v in pairs(value) do
            if type(k) ~= "number" or k < 1 or math.floor(k) ~= k then
                isArray = false
                break
            end
            if k > maxIndex then maxIndex = k end
        end
        local result = {}
        if isArray and maxIndex > 0 then
            for i = 1, maxIndex do
                table.insert(result, ToJSON(value[i], visited))
            end
            return "[" .. table.concat(result, ",") .. "]"
        else
            for k, v in pairs(value) do
                local key = type(k) == "string" and k or tostring(k)
                table.insert(result, EscapeString(key) .. ":" .. ToJSON(v, visited))
            end
            return "{" .. table.concat(result, ",") .. "}"
        end
    else
        return '"[' .. type(value) .. ']"'
    end
end

local function distance(x1, y1, x2, y2)
    local dx = math.abs(x1 - x2)
    local dy = math.abs(y1 - y2)
    return math.max(dx, dy) + math.floor(math.min(dx, dy) / 2)
end

-- ============================================================================
-- GAME DATA HELPERS
-- ============================================================================

local function GetTechName(techIndex)
    if techIndex == nil or techIndex < 0 then return nil end
    local techInfo = GameInfo.Technologies[techIndex]
    return techInfo and Locale.Lookup(techInfo.Name) or nil
end

local function GetCivicName(civicIndex)
    if civicIndex == nil or civicIndex < 0 then return nil end
    local civicInfo = GameInfo.Civics[civicIndex]
    return civicInfo and Locale.Lookup(civicInfo.Name) or nil
end

-- Helper to get game speed multiplier (Standard = 100, Quick = 67, etc.)
local function GetCostMultiplier()
    local speedType = GameConfiguration.GetGameSpeedType()
    local speedInfo = GameInfo.GameSpeeds[speedType]
    return speedInfo and speedInfo.CostMultiplier or 100
end

local function GetProductionInfo(city)
    local success, buildQueue = pcall(function() return city:GetBuildQueue() end)
    if success and buildQueue then
        -- Get the raw type string (e.g., "UNIT_BUILDER")
        -- We need the raw type for database lookups if API fails
        local s2, currentProductionType = pcall(function() return buildQueue:CurrentlyBuilding() end)

        if s2 and currentProductionType then
            -- Get localized name for display
            local s3, name = pcall(function() return Locale.Lookup(currentProductionType) end)
            local prodName = s3 and name or "Unknown"

            local turnsLeft = -1

            -- Method 1: Try native GetTurnsLeft() (often fails in Gameplay context)
            local s4, turns1 = pcall(function() return buildQueue:GetTurnsLeft() end)
            if s4 and turns1 and type(turns1) == "number" and turns1 >= 0 then
                turnsLeft = turns1
            end

            -- Method 2: Try Queue properties (GetProductionCost often returns 0 in Gameplay)
            if turnsLeft < 0 then
                local s5, prodProgress = pcall(function() return buildQueue:GetProductionProgress() end)
                local s6, prodCost = pcall(function() return buildQueue:GetProductionCost() end)

                -- Verify YieldTypes exists, otherwise fallback to index 1 (Production usually)
                local prodYieldType = (YieldTypes and YieldTypes.YIELD_PRODUCTION) or 1
                local s7, cityProd = pcall(function() return city:GetYield(prodYieldType) end)

                if s6 and prodCost and prodCost > 0 and s7 and cityProd and cityProd > 0 then
                    local remaining = prodCost - (prodProgress or 0)
                    turnsLeft = math.ceil(remaining / cityProd)
                end

                -- Method 3: Hard Fallback - Database Lookup
                -- If queue returned 0 cost, look it up in GameInfo and apply Game Speed
                if turnsLeft < 0 and s7 and cityProd and cityProd > 0 then
                    local baseCost = 0

                    -- Check if it's a Unit
                    if GameInfo.Units[currentProductionType] then
                        baseCost = GameInfo.Units[currentProductionType].Cost
                    -- Check if it's a Building
                    elseif GameInfo.Buildings[currentProductionType] then
                        baseCost = GameInfo.Buildings[currentProductionType].Cost
                    -- Check if it's a District
                    elseif GameInfo.Districts[currentProductionType] then
                        baseCost = GameInfo.Districts[currentProductionType].Cost
                    -- Check if it's a Project
                    elseif GameInfo.Projects[currentProductionType] then
                        baseCost = GameInfo.Projects[currentProductionType].Cost
                    end

                    if baseCost > 0 then
                        local multiplier = GetCostMultiplier()
                        local realCost = math.floor(baseCost * (multiplier / 100))
                        local prog = (s5 and prodProgress) or 0
                        turnsLeft = math.ceil((realCost - prog) / cityProd)
                    end
                end
            end

            return prodName, turnsLeft
        end
    end
    return "None", -1
end

local function GetTerrainName(terrainIndex)
    if terrainIndex == nil then return nil end
    local terrainInfo = GameInfo.Terrains[terrainIndex]
    return terrainInfo and cleanName(terrainInfo.TerrainType) or nil
end

local function GetFeatureName(featureIndex)
    if featureIndex == nil or featureIndex < 0 then return nil end
    local featureInfo = GameInfo.Features[featureIndex]
    return featureInfo and cleanName(featureInfo.FeatureType) or nil
end

local function GetResourceName(resourceIndex)
    if resourceIndex == nil or resourceIndex < 0 then return nil end
    local resourceInfo = GameInfo.Resources[resourceIndex]
    return resourceInfo and cleanName(resourceInfo.ResourceType) or nil
end

-- Check if resource is visible to local player (prevents fog-of-war spoilers)
-- Strategic resources like Iron, Horses, Niter, etc. are only visible after researching the required tech
local function IsResourceVisible(plot, localPlayerID)
    if plot == nil then return false end

    -- First check if there even is a resource
    local s1, resourceType = pcall(function() return plot:GetResourceType() end)
    if not s1 or resourceType == nil or resourceType < 0 then
        return false
    end

    -- Check resource visibility for this player
    -- GetResourceVisibility returns ResourceVisibilityTypes enum:
    -- HIDDEN = resource is not visible (tech not researched)
    -- REVEALED = resource is visible to player
    local s2, visibility = pcall(function() return plot:GetResourceVisibility(localPlayerID) end)
    if s2 and visibility then
        -- ResourceVisibilityTypes.REVEALED is typically 1 or greater
        -- ResourceVisibilityTypes.HIDDEN is -1 or 0
        return visibility >= 1
    end

    -- Fallback: if we can't determine visibility, don't show strategic resources
    -- but do show bonus/luxury (they're always visible)
    local resourceInfo = GameInfo.Resources[resourceType]
    if resourceInfo then
        local resourceClass = resourceInfo.ResourceClassType
        -- RESOURCECLASS_STRATEGIC should be hidden if we can't verify visibility
        -- RESOURCECLASS_BONUS and RESOURCECLASS_LUXURY are always visible
        if resourceClass == "RESOURCECLASS_BONUS" or resourceClass == "RESOURCECLASS_LUXURY" then
            return true
        end
    end

    return false
end

local function GetImprovementName(improvementIndex)
    if improvementIndex == nil or improvementIndex < 0 then return nil end
    local improvementInfo = GameInfo.Improvements[improvementIndex]
    return improvementInfo and cleanName(improvementInfo.ImprovementType) or nil
end

local function GetDistrictName(districtIndex)
    if districtIndex == nil or districtIndex < 0 then return nil end
    local districtInfo = GameInfo.Districts[districtIndex]
    return districtInfo and cleanName(districtInfo.DistrictType) or nil
end

local function GetUnitName(unitTypeIndex)
    if unitTypeIndex == nil then return "Unknown" end
    local unitInfo = GameInfo.Units[unitTypeIndex]
    return unitInfo and cleanName(unitInfo.UnitType) or "Unknown"
end

local function GetCivName(playerID)
    local playerConfig = PlayerConfigurations[playerID]
    if playerConfig then
        local civTypeName = playerConfig:GetCivilizationTypeName()
        return cleanName(civTypeName)
    end
    return "Unknown"
end

local function GetDiplomaticState(localPlayerID, otherPlayerID)
    local success, localDiplomacy = pcall(function() return Players[localPlayerID]:GetDiplomacy() end)
    if success and localDiplomacy then
        local s1, atWar = pcall(function() return localDiplomacy:IsAtWarWith(otherPlayerID) end)
        if s1 and atWar then return "War" end
        local s2, alliance = pcall(function() return localDiplomacy:HasAllied(otherPlayerID) end)
        if s2 and alliance then return "Alliance" end
        local s3, friend = pcall(function() return localDiplomacy:HasDeclaredFriendship(otherPlayerID) end)
        if s3 and friend then return "Friend" end
        local s4, denounceTurn = pcall(function() return localDiplomacy:GetDenounceTurn(otherPlayerID) end)
        if s4 and denounceTurn and denounceTurn >= 0 then return "Denounced" end
        local s5, met = pcall(function() return localDiplomacy:HasMet(otherPlayerID) end)
        if s5 and met then return "Neutral" end
    end
    return "Unknown"
end

-- ============================================================================
-- MAIN DUMP FUNCTION
-- ============================================================================

local function DumpGameState()
    local localPlayerID = Game.GetLocalPlayer()
    if localPlayerID == nil or localPlayerID < 0 then return end

    local player = Players[localPlayerID]
    if player == nil then return end

    local gs = {} -- gameState

    -- Get barbarian player ID (varies by game setup, NOT always 63)
    local barbarianPlayerID = -1
    local sBarbID, barbID = pcall(function()
        return PlayerManager.GetAliveBarbariansID()
    end)
    if sBarbID and barbID and barbID >= 0 then
        barbarianPlayerID = barbID
    else
        -- Fallback: scan players for barbarian civ type
        for pid = 0, 63 do
            local pConfig = PlayerConfigurations[pid]
            if pConfig then
                local sCiv, civType = pcall(function() return pConfig:GetCivilizationTypeName() end)
                if sCiv and civType and civType == "CIVILIZATION_BARBARIAN" then
                    barbarianPlayerID = pid
                    break
                end
            end
        end
    end

    -- Basic Info
    local s1, turn = pcall(function() return Game.GetCurrentGameTurn() end)
    gs.turn = s1 and turn or 0

    local s2, era = pcall(function() return Game.GetEras():GetCurrentEra() end)
    gs.era = s2 and era or 0

    gs.civ = GetCivName(localPlayerID)

    -- Leader (e.g., "LEADER_HAMMURABI", "LEADER_T_ROOSEVELT_ROUGHRIDER")
    local playerConfig = PlayerConfigurations[localPlayerID]
    if playerConfig then
        local sLeader, leaderType = pcall(function() return playerConfig:GetLeaderTypeName() end)
        if sLeader and leaderType then
            gs.leader = leaderType
        end
    end

    -- Treasury
    local sTreas, treasury = pcall(function() return player:GetTreasury() end)
    if sTreas and treasury then
        local s1, bal = pcall(function() return treasury:GetGoldBalance() end)
        if s1 and bal then gs.gold = round(bal) end
        local s2, yield = pcall(function() return treasury:GetGoldYield() end)
        local s3, maint = pcall(function() return treasury:GetTotalMaintenance() end)
        if s2 and s3 and yield and maint then gs.gpt = round(yield - maint) end
    end

    -- Science + Tech Choice Detection
    gs.needsTech = false
    local sTechs, techs = pcall(function() return player:GetTechs() end)
    if sTechs and techs then
        local s1, sciYield = pcall(function() return techs:GetScienceYield() end)
        if s1 and sciYield then gs.sci = round(sciYield) end
        local s2, curTech = pcall(function() return techs:GetResearchingTech() end)
        if s2 and curTech and curTech >= 0 then
            gs.tech = GetTechName(curTech)
            local s3, cost = pcall(function() return techs:GetResearchCost(curTech) end)
            local s4, prog = pcall(function() return techs:GetResearchProgress(curTech) end)
            if not s4 or not prog then s4, prog = pcall(function() return techs:GetResearchProgress() end) end
            if s3 and s4 and cost and cost > 0 and prog then
                gs.techPct = math.floor((prog / cost) * 100)
            end
        else
            gs.needsTech = true
        end
    end

    -- Culture + Civic Choice Detection
    gs.needsCivic = false
    local sCult, culture = pcall(function() return player:GetCulture() end)
    if sCult and culture then
        local s1, cultYield = pcall(function() return culture:GetCultureYield() end)
        if s1 and cultYield then gs.cul = round(cultYield) end
        local s2, curCivic = pcall(function() return culture:GetProgressingCivic() end)
        if s2 and curCivic and curCivic >= 0 then
            gs.civic = GetCivicName(curCivic)
            local s3, cost = pcall(function() return culture:GetCultureCost() end)
            local s4, prog = pcall(function() return culture:GetCulturalProgress() end)
            if not s3 or not cost then s3, cost = pcall(function() return culture:GetCultureCost(curCivic) end) end
            if not s4 or not prog then s4, prog = pcall(function() return culture:GetCulturalProgress(curCivic) end) end
            if s3 and s4 and cost and cost > 0 and prog then
                gs.civicPct = math.floor((prog / cost) * 100)
            end
        else
            gs.needsCivic = true
        end
    end

    -- Completed Technologies (for AI situational awareness)
    gs.completed_techs = {}
    if sTechs and techs then
        for tech in GameInfo.Technologies() do
            local sHas, hasTech = pcall(function() return techs:HasTech(tech.Index) end)
            if sHas and hasTech then
                table.insert(gs.completed_techs, {
                    name = cleanName(tech.TechnologyType),
                    cost = tech.Cost or 0
                })
            end
        end
    end
    -- Only include if we have any (nil means empty, saves JSON space)
    if #gs.completed_techs == 0 then gs.completed_techs = nil end

    -- Completed Civics (for AI situational awareness)
    gs.completed_civics = {}
    if sCult and culture then
        for civic in GameInfo.Civics() do
            local sHas, hasCivic = pcall(function() return culture:HasCivic(civic.Index) end)
            if sHas and hasCivic then
                table.insert(gs.completed_civics, {
                    name = cleanName(civic.CivicType),
                    cost = civic.Cost or 0
                })
            end
        end
    end
    -- Only include if we have any
    if #gs.completed_civics == 0 then gs.completed_civics = nil end

    -- Faith
    local sRel, religion = pcall(function() return player:GetReligion() end)
    if sRel and religion then
        local s1, faithYield = pcall(function() return religion:GetFaithYield() end)
        if s1 and faithYield and faithYield > 0 then gs.faith = round(faithYield) end
        local s2, faithBal = pcall(function() return religion:GetFaithBalance() end)
        if s2 and faithBal and faithBal > 0 then gs.faithBal = round(faithBal) end
    end

    -- Find capital for distance sorting
    local capitalX, capitalY = 0, 0
    local playerCities = player:GetCities()
    if playerCities then
        for i, city in playerCities:Members() do
            local sC, isCap = pcall(function() return city:IsCapital() end)
            if sC and isCap then
                local sX, x = pcall(function() return city:GetX() end)
                local sY, y = pcall(function() return city:GetY() end)
                capitalX = sX and x or 0
                capitalY = sY and y or 0
                break
            end
        end
    end

    -- Build list of civs we are at war with (for threat detection)
    local atWarWith = {}
    local sDip, localDiplomacy = pcall(function() return player:GetDiplomacy() end)
    if sDip and localDiplomacy then
        for otherPlayerID = 0, 62 do
            if otherPlayerID ~= localPlayerID then
                local s1, atWar = pcall(function() return localDiplomacy:IsAtWarWith(otherPlayerID) end)
                if s1 and atWar then
                    atWarWith[otherPlayerID] = true
                end
            end
        end
    end

    -- Cities (with production turns and needsProduction)
    gs.cities = {}
    gs.needsProd = false
    local cityList = {}
    if playerCities then
        for i, city in playerCities:Members() do
            local c = {}
            local sN, name = pcall(function() return city:GetName() end)
            c.n = sN and name and Locale.Lookup(name) or "?"
            local sX, x = pcall(function() return city:GetX() end)
            local sY, y = pcall(function() return city:GetY() end)
            local cityX = sX and x or 0
            local cityY = sY and y or 0
            c.xy = cityX .. "," .. cityY
            local sP, pop = pcall(function() return city:GetPopulation() end)
            c.pop = sP and pop or 0

            local prodName, turnsLeft = GetProductionInfo(city)
            c.bld = prodName
            -- Always include turns (use -1 if unknown, Python will display "?")
            c.turns = turnsLeft
            if prodName == "None" or prodName == "" then
                gs.needsProd = true
            end

            local sG, cityGrowth = pcall(function() return city:GetGrowth() end)
            if sG and cityGrowth then
                local s1, turns = pcall(function() return cityGrowth:GetTurnsUntilGrowth() end)
                if s1 and turns then c.grow = turns end
            end

            -- Get districts in this city
            -- Note: city:GetDistricts():Members() may not be available in all contexts
            -- Use HasDistrict() as a reliable fallback
            local districts = {}
            local sCityDistricts, cityDistricts = pcall(function() return city:GetDistricts() end)
            if sCityDistricts and cityDistricts then
                -- Try Members() first (works in UI context)
                local hasMembers = type(cityDistricts.Members) == "function"
                if hasMembers then
                    local sIter, iterResult = pcall(function()
                        for j, district in cityDistricts:Members() do
                            local sType, distType = pcall(function() return district:GetType() end)
                            if sType and distType and distType >= 0 then
                                local distName = GetDistrictName(distType)
                                if distName and distName ~= "City Center" then
                                    local sComplete, isComplete = pcall(function() return district:IsComplete() end)
                                    if sComplete and isComplete then
                                        table.insert(districts, distName)
                                    else
                                        table.insert(districts, distName .. "*")
                                    end
                                end
                            end
                        end
                    end)
                end

                -- Fallback: check for common district types using HasDistrict()
                if #districts == 0 and cityDistricts.HasDistrict then
                    local districtTypes = {
                        "DISTRICT_CAMPUS", "DISTRICT_HOLY_SITE", "DISTRICT_THEATER",
                        "DISTRICT_COMMERCIAL_HUB", "DISTRICT_HARBOR", "DISTRICT_INDUSTRIAL_ZONE",
                        "DISTRICT_ENTERTAINMENT_COMPLEX", "DISTRICT_ENCAMPMENT", "DISTRICT_AERODROME",
                        "DISTRICT_SPACEPORT", "DISTRICT_GOVERNMENT", "DISTRICT_DIPLOMATIC_QUARTER",
                        "DISTRICT_CANAL", "DISTRICT_DAM", "DISTRICT_AQUEDUCT", "DISTRICT_NEIGHBORHOOD",
                        "DISTRICT_PRESERVE", "DISTRICT_WATER_ENTERTAINMENT_COMPLEX"
                    }
                    for _, distType in ipairs(districtTypes) do
                        local distInfo = GameInfo.Districts[distType]
                        if distInfo then
                            local sHas, hasIt = pcall(function() return cityDistricts:HasDistrict(distInfo.Index) end)
                            if sHas and hasIt then
                                table.insert(districts, cleanName(distType))
                            end
                        end
                    end
                end
            end
            if #districts > 0 then c.districts = districts end

            -- Get buildings in this city (includes wonders)
            local buildings = {}
            local wonders = {}  -- Wonders with locations for adjacency planning
            local sCityBuildings, cityBuildings = pcall(function() return city:GetBuildings() end)
            if sCityBuildings and cityBuildings then
                -- Iterate through all possible buildings
                for buildingInfo in GameInfo.Buildings() do
                    local sBld, hasBuilding = pcall(function() return cityBuildings:HasBuilding(buildingInfo.Index) end)
                    if sBld and hasBuilding then
                        local buildingName = cleanName(buildingInfo.BuildingType)
                        -- Check if it's a wonder (wonders have IsWonder = true)
                        if buildingInfo.IsWonder then
                            -- Get wonder location for adjacency planning
                            local sLoc, plotIndex = pcall(function() return cityBuildings:GetBuildingLocation(buildingInfo.Index) end)
                            if sLoc and plotIndex and plotIndex >= 0 then
                                local sPlot, plot = pcall(function() return Map.GetPlotByIndex(plotIndex) end)
                                if sPlot and plot then
                                    local sX, wx = pcall(function() return plot:GetX() end)
                                    local sY, wy = pcall(function() return plot:GetY() end)
                                    if sX and sY then
                                        table.insert(wonders, buildingName .. " " .. wx .. "," .. wy)
                                    else
                                        table.insert(wonders, buildingName)
                                    end
                                else
                                    table.insert(wonders, buildingName)
                                end
                            else
                                table.insert(wonders, buildingName)
                            end
                            table.insert(buildings, buildingName .. "!")  -- ! = wonder
                        else
                            table.insert(buildings, buildingName)
                        end
                    end
                end
            end
            if #buildings > 0 then c.buildings = buildings end
            if #wonders > 0 then c.wonders = wonders end  -- Separate wonders list with coords

            c._dist = distance(cityX, cityY, capitalX, capitalY)
            table.insert(cityList, c)
        end
    end
    -- Sort cities by distance from capital
    table.sort(cityList, function(a, b) return a._dist < b._dist end)
    for _, c in ipairs(cityList) do
        c._dist = nil
        table.insert(gs.cities, c)
    end

    -- Units (format: "UnitName x,y HPh Moves")
    gs.units = {}
    local unitList = {}
    local sUnits, playerUnits = pcall(function() return player:GetUnits() end)
    if sUnits and playerUnits then
        for i, unit in playerUnits:Members() do
            local s1, unitType = pcall(function() return unit:GetType() end)
            local name = s1 and GetUnitName(unitType) or "?"
            local s2, x = pcall(function() return unit:GetX() end)
            local s3, y = pcall(function() return unit:GetY() end)
            local unitX = s2 and x or 0
            local unitY = s3 and y or 0
            local s4, maxDmg = pcall(function() return unit:GetMaxDamage() end)
            local s5, dmg = pcall(function() return unit:GetDamage() end)
            local healthPct = 100
            if s4 and s5 and maxDmg and maxDmg > 0 then
                healthPct = math.floor(((maxDmg - dmg) / maxDmg) * 100)
            end
            local s6, movesRemaining = pcall(function() return unit:GetMovesRemaining() end)
            local s7, maxMoves = pcall(function() return unit:GetMaxMoves() end)
            local movesLeft = s6 and movesRemaining and math.floor(movesRemaining / 96) or 0 -- Civ6 uses fixed point
            local maxMovesVal = s7 and maxMoves and math.floor(maxMoves / 96) or 2

            -- Format: "Warrior 18,18 100hp 2/2m"
            local unitStr = name .. " " .. unitX .. "," .. unitY .. " " .. healthPct .. "hp " .. movesLeft .. "/" .. maxMovesVal .. "m"
            table.insert(unitList, {str = unitStr, x = unitX, y = unitY, dist = distance(unitX, unitY, capitalX, capitalY)})
        end
    end
    -- Sort units by distance from capital
    table.sort(unitList, function(a, b) return a.dist < b.dist end)
    for _, u in ipairs(unitList) do
        table.insert(gs.units, u.str)
    end

    -- Threat Radar: Scan for hostile units
    gs.threats = {}
    local sMap, mapWidth, mapHeight = pcall(function()
        local w, h = Map.GetGridSize()
        return w, h
    end)

    if sMap and mapWidth and mapHeight then
        local visibilityMgr = PlayersVisibility[localPlayerID]

        for x = 0, mapWidth - 1 do
            for y = 0, mapHeight - 1 do
                local sVis, isVisible = pcall(function()
                    return visibilityMgr and visibilityMgr:IsVisible(x, y)
                end)

                if sVis and isVisible then
                    -- Check for units on this tile
                    local sPlot, plot = pcall(function() return Map.GetPlot(x, y) end)
                    if sPlot and plot then
                        local sUC, unitCount = pcall(function() return plot:GetUnitCount() end)
                        if sUC and unitCount and unitCount > 0 then
                            for ui = 0, unitCount - 1 do
                                local sUnit, unit = pcall(function() return plot:GetUnit(ui) end)
                                if sUnit and unit then
                                    local sOwner, owner = pcall(function() return unit:GetOwner() end)
                                    if sOwner and owner then
                                        local isBarbarian = (owner == barbarianPlayerID)
                                        local isHostileMajor = atWarWith[owner] == true
                                        if isBarbarian or isHostileMajor then
                                            local sUT, unitType = pcall(function() return unit:GetType() end)
                                            local unitName = sUT and GetUnitName(unitType) or "?"
                                            local threatDist = distance(x, y, capitalX, capitalY)
                                            local ownerName = isBarbarian and "Barb" or GetCivName(owner)
                                            -- Format: "Warrior (Barb) 18,18 d5"
                                            local threatStr = unitName .. " (" .. ownerName .. ") " .. x .. "," .. y .. " d" .. threatDist
                                            table.insert(gs.threats, {str = threatStr, dist = threatDist})
                                        end
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end
    -- Sort threats by distance (closest first)
    table.sort(gs.threats, function(a, b) return a.dist < b.dist end)
    local threatStrings = {}
    for _, t in ipairs(gs.threats) do
        table.insert(threatStrings, t.str)
    end
    gs.threats = #threatStrings > 0 and threatStrings or nil

    -- Diplomacy with full scoreboard stats (only if non-empty)
    local diplomacy = {}
    if sDip and localDiplomacy then
        for otherPlayerID = 0, 62 do
            if otherPlayerID ~= localPlayerID then
                local otherPlayer = Players[otherPlayerID]
                if otherPlayer then
                    local s1, isAlive = pcall(function() return otherPlayer:IsAlive() end)
                    local s2, isMajor = pcall(function() return otherPlayer:IsMajor() end)
                    local s3, hasMet = pcall(function() return localDiplomacy:HasMet(otherPlayerID) end)
                    if s1 and isAlive and s2 and isMajor and s3 and hasMet then
                        local civEntry = {}
                        civEntry.civ = GetCivName(otherPlayerID)
                        civEntry.status = GetDiplomaticState(localPlayerID, otherPlayerID)

                        -- Get leader type
                        local otherConfig = PlayerConfigurations[otherPlayerID]
                        if otherConfig then
                            local sLeader, leaderType = pcall(function() return otherConfig:GetLeaderTypeName() end)
                            if sLeader and leaderType then
                                civEntry.leader = leaderType
                            end
                        end

                        -- Get score from Players API
                        local sScore, score = pcall(function() return otherPlayer:GetScore() end)
                        if sScore and score then civEntry.score = round(score) end

                        -- Military strength
                        local sMil, milStrength = pcall(function() return otherPlayer:GetMilitaryStrength() end)
                        if sMil and milStrength then civEntry.military = round(milStrength) end

                        -- Get yields per turn from stats
                        local sStats, otherStats = pcall(function() return otherPlayer:GetStats() end)
                        if sStats and otherStats then
                            local sSci, sciYield = pcall(function() return otherStats:GetNumTechsResearched() end)
                            -- Note: GetNumTechsResearched gives techs, not per turn. Try culture/science from yields
                        end

                        -- Try to get culture/science yields
                        local sOtherCulture, otherCulture = pcall(function() return otherPlayer:GetCulture() end)
                        if sOtherCulture and otherCulture then
                            local sCY, cultureYield = pcall(function() return otherCulture:GetCultureYield() end)
                            if sCY and cultureYield then civEntry.culture_pt = round(cultureYield) end
                        end

                        -- Science per turn
                        local sOtherTechs, otherTechs = pcall(function() return otherPlayer:GetTechs() end)
                        if sOtherTechs and otherTechs then
                            local sRR, researchRate = pcall(function() return otherTechs:GetScienceYield() end)
                            if sRR and researchRate then civEntry.science_pt = round(researchRate) end
                        end

                        -- Tourism (accumulated)
                        local sTourism, tourismVal = pcall(function()
                            local culture = otherPlayer:GetCulture()
                            if culture then return culture:GetTourism() end
                            return nil
                        end)
                        if sTourism and tourismVal then civEntry.tourism = round(tourismVal) end

                        -- Gold balance and GPT (if visible)
                        local sOtherTreasury, otherTreasury = pcall(function() return otherPlayer:GetTreasury() end)
                        if sOtherTreasury and otherTreasury then
                            local sGold, goldBal = pcall(function() return otherTreasury:GetGoldBalance() end)
                            if sGold and goldBal then civEntry.gold = round(goldBal) end
                        end

                        table.insert(diplomacy, civEntry)
                    end
                end
            end
        end
    end
    if #diplomacy > 0 then gs.diplo = diplomacy end

    -- City States (only if non-empty)
    local cityStates = {}
    local sInf, influence = pcall(function() return player:GetInfluence() end)
    for otherPlayerID = 0, 62 do
        local otherPlayer = Players[otherPlayerID]
        if otherPlayer then
            local s1, isAlive = pcall(function() return otherPlayer:IsAlive() end)
            local s2, isMajor = pcall(function() return otherPlayer:IsMajor() end)
            if s1 and isAlive and s2 and not isMajor then
                local s3, hasMet = pcall(function() return localDiplomacy and localDiplomacy:HasMet(otherPlayerID) end)
                if s3 and hasMet then
                    local otherConfig = PlayerConfigurations[otherPlayerID]
                    if otherConfig then
                        local s4, desc = pcall(function() return otherConfig:GetCivilizationDescription() end)
                        local csName = s4 and desc and Locale.Lookup(desc) or "?"
                        local envoys = 0
                        local isSuz = false
                        if sInf and influence then
                            local s5, e = pcall(function() return influence:GetTokensReceived(otherPlayerID) end)
                            if s5 and e then envoys = e end
                            local s6, suz = pcall(function() return influence:GetSuzerain(otherPlayerID) end)
                            if s6 then isSuz = (suz == localPlayerID) end
                        end
                        local csStr = csName .. ":" .. envoys .. (isSuz and "*" or "")
                        table.insert(cityStates, csStr)
                    end
                end
            end
        end
    end
    if #cityStates > 0 then gs.cs = cityStates end

    -- Trade Routes (only if non-empty)
    local tradeRoutes = {}
    local sTrade, trade = pcall(function() return player:GetTrade() end)
    if sTrade and trade then
        local s1, routes = pcall(function() return trade:GetOutgoingRoutes() end)
        if s1 and routes then
            for i, route in ipairs(routes) do
                local s2, originCity = pcall(function() return CityManager.GetCity(route.OriginCityPlayer, route.OriginCityID) end)
                local s3, destCity = pcall(function() return CityManager.GetCity(route.DestinationCityPlayer, route.DestinationCityID) end)
                local fromName, toName = "?", "?"
                if s2 and originCity then
                    local s4, n = pcall(function() return originCity:GetName() end)
                    if s4 and n then fromName = Locale.Lookup(n) end
                end
                if s3 and destCity then
                    local s5, n = pcall(function() return destCity:GetName() end)
                    if s5 and n then toName = Locale.Lookup(n) end
                end
                table.insert(tradeRoutes, fromName .. "->" .. toName)
            end
        end
    end
    if #tradeRoutes > 0 then gs.trade = tradeRoutes end

    -- Foreign Cities and Districts (city centers + encampments of met civs)
    local foreignCities = {}
    if sDip and localDiplomacy and sMap and mapWidth and mapHeight then
        local visibilityMgr = PlayersVisibility[localPlayerID]

        for otherPlayerID = 0, 62 do
            if otherPlayerID ~= localPlayerID then
                local otherPlayer = Players[otherPlayerID]
                if otherPlayer then
                    local s1, isAlive = pcall(function() return otherPlayer:IsAlive() end)
                    local s2, isMajor = pcall(function() return otherPlayer:IsMajor() end)
                    local s3, hasMet = pcall(function() return localDiplomacy:HasMet(otherPlayerID) end)

                    if s1 and isAlive and s2 and isMajor and s3 and hasMet then
                        local ownerName = GetCivName(otherPlayerID)
                        local sOtherCities, otherCities = pcall(function() return otherPlayer:GetCities() end)

                        if sOtherCities and otherCities then
                            for _, otherCity in otherCities:Members() do
                                local sCityX, cityX = pcall(function() return otherCity:GetX() end)
                                local sCityY, cityY = pcall(function() return otherCity:GetY() end)

                                if sCityX and sCityY then
                                    -- Check if we can see this city tile (revealed/visible)
                                    local sRevealed, isRevealed = pcall(function()
                                        return visibilityMgr and (visibilityMgr:IsRevealed(cityX, cityY) or visibilityMgr:IsVisible(cityX, cityY))
                                    end)

                                    if sRevealed and isRevealed then
                                        local sCityName, cityName = pcall(function() return otherCity:GetName() end)
                                        local displayName = sCityName and cityName and Locale.Lookup(cityName) or "?"
                                        local sPop, pop = pcall(function() return otherCity:GetPopulation() end)
                                        local popVal = sPop and pop or 0

                                        -- Check for capital
                                        local sCapital, isCapital = pcall(function() return otherCity:IsCapital() end)
                                        local capitalMark = (sCapital and isCapital) and "*" or ""

                                        -- Get districts for this city (looking for encampments specifically)
                                        local hasEncampment = false
                                        local sCityDistricts, cityDistricts = pcall(function() return otherCity:GetDistricts() end)
                                        if sCityDistricts and cityDistricts and cityDistricts.HasDistrict then
                                            local encampmentInfo = GameInfo.Districts["DISTRICT_ENCAMPMENT"]
                                            if encampmentInfo then
                                                local sHas, hasIt = pcall(function() return cityDistricts:HasDistrict(encampmentInfo.Index) end)
                                                if sHas and hasIt then hasEncampment = true end
                                            end
                                        end

                                        local distFromCap = distance(cityX, cityY, capitalX, capitalY)
                                        -- Format: "CivName: CityName* pop3 xy (d5) [Encampment]"
                                        local cityStr = ownerName .. ": " .. displayName .. capitalMark .. " pop" .. popVal .. " " .. cityX .. "," .. cityY .. " (d" .. distFromCap .. ")"
                                        if hasEncampment then
                                            cityStr = cityStr .. " [Encampment]"
                                        end

                                        table.insert(foreignCities, {str = cityStr, dist = distFromCap})
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end
    -- Sort by distance
    table.sort(foreignCities, function(a, b) return a.dist < b.dist end)
    local foreignCityStrings = {}
    for _, fc in ipairs(foreignCities) do
        table.insert(foreignCityStrings, fc.str)
    end
    if #foreignCityStrings > 0 then gs.foreign_cities = foreignCityStrings end

    -- Foreign Tiles (discovered tiles owned by other civs - owner + districts/unique improvements only, no yields)
    local foreignTiles = {}
    local maxForeignTiles = 100
    if sMap and mapWidth and mapHeight then
        local visibilityMgr = PlayersVisibility[localPlayerID]

        for x = 0, mapWidth - 1 do
            for y = 0, mapHeight - 1 do
                -- Check if tile is revealed (not necessarily currently visible)
                local sRevealed, isRevealed = pcall(function()
                    return visibilityMgr and visibilityMgr:IsRevealed(x, y)
                end)

                if sRevealed and isRevealed then
                    local sPlot, plot = pcall(function() return Map.GetPlot(x, y) end)
                    if sPlot and plot then
                        -- Check ownership
                        local sOwner, ownerID = pcall(function() return plot:GetOwner() end)
                        if sOwner and ownerID and ownerID >= 0 and ownerID ~= localPlayerID and ownerID ~= 63 then
                            -- Check if we've met this player and they're a major civ
                            local ownerPlayer = Players[ownerID]
                            if ownerPlayer then
                                local s1, isMajor = pcall(function() return ownerPlayer:IsMajor() end)
                                local s2, hasMet = pcall(function() return localDiplomacy and localDiplomacy:HasMet(ownerID) end)

                                if s1 and isMajor and s2 and hasMet then
                                    local s3, district = pcall(function() return plot:GetDistrictType() end)
                                    local s4, improvement = pcall(function() return plot:GetImprovementType() end)

                                    local districtName = s3 and district and district >= 0 and GetDistrictName(district) or nil
                                    local improvementName = s4 and improvement and improvement >= 0 and GetImprovementName(improvement) or nil

                                    -- Only include tiles with districts or unique improvements
                                    if districtName or improvementName then
                                        local ownerName = GetCivName(ownerID)
                                        local tileDist = distance(x, y, capitalX, capitalY)

                                        -- Format: "x,y: Owner [District/Improvement]"
                                        local parts = {x .. "," .. y .. ":"}
                                        table.insert(parts, ownerName)
                                        if districtName then
                                            table.insert(parts, "[" .. districtName .. "]")
                                        elseif improvementName then
                                            table.insert(parts, "[" .. improvementName .. "]")
                                        end

                                        table.insert(foreignTiles, {str = table.concat(parts, " "), dist = tileDist})
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end
    -- Sort by distance, limit count
    table.sort(foreignTiles, function(a, b) return a.dist < b.dist end)
    local foreignTileStrings = {}
    local ftCount = 0
    for _, ft in ipairs(foreignTiles) do
        table.insert(foreignTileStrings, ft.str)
        ftCount = ftCount + 1
        if ftCount >= maxForeignTiles then break end
    end
    if #foreignTileStrings > 0 then gs.foreign_tiles = foreignTileStrings end

    -- Visible Tiles (format: "x,y: Terrain Feature Resource (3f,2p,1g)" with improved flag)
    local tileList = {}
    local maxTiles = 150

    if sMap and mapWidth and mapHeight then
        local visibilityMgr = PlayersVisibility[localPlayerID]

        for x = 0, mapWidth - 1 do
            for y = 0, mapHeight - 1 do
                local sVis, isVisible = pcall(function()
                    return visibilityMgr and visibilityMgr:IsVisible(x, y)
                end)

                if sVis and isVisible then
                    local sPlot, plot = pcall(function() return Map.GetPlot(x, y) end)
                    if sPlot and plot then
                        local s1, terrain = pcall(function() return plot:GetTerrainType() end)
                        local s2, feature = pcall(function() return plot:GetFeatureType() end)
                        local s3, resource = pcall(function() return plot:GetResourceType() end)
                        local s4, improvement = pcall(function() return plot:GetImprovementType() end)
                        local s5, district = pcall(function() return plot:GetDistrictType() end)

                        local terrainName = s1 and GetTerrainName(terrain) or nil
                        local featureName = s2 and feature and feature >= 0 and GetFeatureName(feature) or nil

                        -- Only include resource if it's visible to the player (prevents fog-of-war spoilers)
                        local resourceName = nil
                        if s3 and resource and resource >= 0 then
                            if IsResourceVisible(plot, localPlayerID) then
                                resourceName = GetResourceName(resource)
                            end
                        end

                        -- Get actual improvement and district names
                        local improvementName = s4 and improvement and improvement >= 0 and GetImprovementName(improvement) or nil
                        local districtName = s5 and district and district >= 0 and GetDistrictName(district) or nil

                        -- Clean up redundant terrain in feature name
                        if featureName and terrainName then
                            featureName = cleanFeatureTerrain(featureName, terrainName)
                        end

                        -- Get yields
                        local s6, food = pcall(function() return plot:GetYield(YieldTypes.YIELD_FOOD) end)
                        local s7, prod = pcall(function() return plot:GetYield(YieldTypes.YIELD_PRODUCTION) end)
                        local s8, gold = pcall(function() return plot:GetYield(YieldTypes.YIELD_GOLD) end)
                        local s9, science = pcall(function() return plot:GetYield(YieldTypes.YIELD_SCIENCE) end)
                        local s10, culture = pcall(function() return plot:GetYield(YieldTypes.YIELD_CULTURE) end)
                        local s11, faith = pcall(function() return plot:GetYield(YieldTypes.YIELD_FAITH) end)

                        food = s6 and food or 0
                        prod = s7 and prod or 0
                        gold = s8 and gold or 0
                        science = s9 and science or 0
                        culture = s10 and culture or 0
                        faith = s11 and faith or 0

                        -- Only include interesting tiles
                        if resourceName or districtName or improvementName or food > 2 or prod > 2 then
                            -- Build compact string: "x,y: Terrain Feature Resource [Improvement/District] (yields)"
                            local parts = {x .. "," .. y .. ":"}
                            if terrainName then table.insert(parts, terrainName) end
                            if featureName then table.insert(parts, featureName) end
                            if resourceName then table.insert(parts, resourceName) end

                            -- Add improvement or district name in brackets
                            if districtName then
                                table.insert(parts, "[" .. districtName .. "]")
                            elseif improvementName then
                                table.insert(parts, "[" .. improvementName .. "]")
                            end

                            -- Build yield string (lowercase, comma-separated)
                            local yields = {}
                            if food > 0 then table.insert(yields, math.floor(food) .. "f") end
                            if prod > 0 then table.insert(yields, math.floor(prod) .. "p") end
                            if gold > 0 then table.insert(yields, math.floor(gold) .. "g") end
                            if science > 0 then table.insert(yields, math.floor(science) .. "s") end
                            if culture > 0 then table.insert(yields, math.floor(culture) .. "c") end
                            if faith > 0 then table.insert(yields, math.floor(faith) .. "h") end

                            if #yields > 0 then
                                table.insert(parts, "(" .. table.concat(yields, ",") .. ")")
                            end

                            local tileDist = distance(x, y, capitalX, capitalY)
                            table.insert(tileList, {str = table.concat(parts, " "), dist = tileDist})
                        end
                    end
                end
            end
        end
    end

    -- Sort tiles by distance from capital (closest first)
    table.sort(tileList, function(a, b) return a.dist < b.dist end)
    gs.tiles = {}
    local tileCount = 0
    for _, t in ipairs(tileList) do
        table.insert(gs.tiles, t.str)
        tileCount = tileCount + 1
        if tileCount >= maxTiles then break end
    end

    -- Output the JSON
    local jsonOutput = ToJSON(gs)
    print(">>>GAMESTATE>>>" .. jsonOutput .. "<<<END<<<")
end

-- ============================================================================
-- EVENT REGISTRATION (with turn deduplication)
-- ============================================================================

-- Track last dumped turn to prevent duplicate dumps
local g_iLastDumpTurn = -1

local function SafeDumpGameState()
    -- Check if we should dump (turn changed or first load)
    local iCurrentTurn = Game.GetCurrentGameTurn()
    local iLocalPlayer = Game.GetLocalPlayer()

    -- Don't dump if observer or still loading
    if iLocalPlayer == nil or iLocalPlayer < 0 then
        return
    end

    -- Only dump if turn changed from last dump
    if iCurrentTurn == g_iLastDumpTurn then
        return  -- Already dumped this turn
    end

    -- Update tracking and perform dump
    g_iLastDumpTurn = iCurrentTurn

    local success, err = pcall(DumpGameState)
    if not success then
        print("CivAI Bridge Error: " .. tostring(err))
    end
end

-- Hook only essential events - deduplication prevents spam
if Events.LocalPlayerTurnBegin then
    Events.LocalPlayerTurnBegin.Add(SafeDumpGameState)
    print("CivAI Bridge: Registered LocalPlayerTurnBegin")
end

if Events.LoadScreenClose then
    Events.LoadScreenClose.Add(SafeDumpGameState)
    print("CivAI Bridge: Registered LoadScreenClose (initial load)")
end

print("CivAI Bridge: LLM-Optimized Logger v4 initialized (with turn deduplication)")
