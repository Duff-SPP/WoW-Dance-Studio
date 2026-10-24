local A = {}
WoWDanceStudio = A
A.data = WoWDanceStudioData or {emotes={}, audioMode="native"}
A.byToken = {}
A.byID = {}
local frame = CreateFrame("Frame")
local elapsed = 0
local silence = "Interface\\AddOns\\WoWDanceStudio\\silence.wav"

local function canonical(path)
    return type(path)=="string" and string.gsub(string.lower(string.gsub(path,"/","\\")),"%.mdx$",".m2") or ""
end

function A:Message(text)
    DEFAULT_CHAT_FRAME:AddMessage("|cff79d6ffDance Studio:|r "..text)
end

function A:Initialize()
    if type(WoWDanceStudioDB)~="table" then WoWDanceStudioDB={} end
    self.db = WoWDanceStudioDB
    if type(self.db.wheel)~="table" then self.db.wheel={} end
    if type(self.db.favorites)~="table" then self.db.favorites={} end
    -- Old mesh-scale zoom is not compatible with viewport zoom units.
    if self.db.previewViewVersion~=2 then self.db.previewZoom=1.6;self.db.previewViewVersion=2 end
    local zoom=self.db.previewZoom
    if type(zoom)~="number" or zoom~=zoom then zoom=1.6 end
    self.db.previewZoom=math.max(0.2,math.min(1.6,zoom))
    if self.db.music == nil then self.db.music = true end
    if self.db.repeatDances == nil then self.db.repeatDances = true end
    for _, emote in ipairs(self.data.emotes) do
        self.byID[emote.id] = emote
        for _, model in ipairs(emote.models) do
            if model.token then self.byToken[string.upper(model.token)] = emote end
        end
    end
    self:RegisterAliases()
    if hooksecurefunc then
        hooksecurefunc("DoEmote", function(token) A:OnEmote(token) end)
        self.hasEmoteHook = true
    end
    self:Message("/wds opens your dance collection.")
end

function A:FindModel(emote)
    local path = self.model and canonical(self.model:GetModel()) or ""
    if path~="" then
        for _, model in ipairs(emote.models) do
            if canonical(model.path)==path then return model end
        end
        return nil,"The loaded character model is not included for this dance."
    end
    local _, race = UnitRace("player")
    race = string.lower(race or "")
    if race=="undead" then race="scourge" end
    local sex = UnitSex("player")==3 and "female" or "male"
    local found
    for _, model in ipairs(emote.models) do
        if model.race==race and model.sex==sex then
            if found then return nil,"Multiple model versions; open the collection so its character model can be identified." end
            found=model
        end
    end
    if found then return found end
    return nil,"Not included for your character model in this pack."
end

function A:StopMusic()
    if self.musicActive then
        -- Legacy 3.3.5 has no StopSound. Replacing scripted music with silence
        -- interrupts it immediately; StopMusic then releases the music channel.
        PlayMusic(silence)
        StopMusic()
        self.musicActive=false
    end
end

function A:AnimationTime(model, elapsedMS)
    local duration=model.durationMS
    local prefix=tonumber(model.loopStartMS) or 0
    if prefix<0 or prefix>=duration then prefix=0 end
    elapsedMS=math.max(0,elapsedMS)
    if elapsedMS<duration then return elapsedMS end
    return prefix+(elapsedMS-prefix)%(duration-prefix)
end

function A:Stop(stopEmote)
    self:StopMusic()
    self.active=nil
    self.pendingOnce=nil
    if stopEmote then DoEmote("STAND") end
    if self.UpdateStatus then self:UpdateStatus() end
end

function A:OnEmote(token)
    local once=self.pendingOnce
    self.pendingOnce=nil
    local emote = type(token)=="string" and self.byToken[string.upper(token)] or nil
    self:Stop(false)
    if not emote then return end
    local model = self:FindModel(emote)
    if not model or not model.token then return end
    local duration=tonumber(model.durationMS)
    if not duration or duration~=duration or duration<=0 or duration>600000 then
        self:Message("Invalid dance duration; rebuild this pack's catalog.");return
    end
    local started=GetTime()
    self.active={emote=emote, model=model, started=started, endsAt=started+duration/1000,
        repeating=not once and self.db.repeatDances and model.loop~=false and duration>=500}
    if self.data.audioMode=="addon" and self.db.music and (model.audio or model.audioIntro) then
        if tonumber(GetCVar("Sound_EnableMusic"))==1 then
            PlayMusic(model.audioIntro or model.audio)
            self.musicActive=true
            if model.audioIntro and model.introMS and model.introMS>0 then
                self.active.musicNext=started+model.introMS/1000
            end
        else self:Message("Enable Music in Sound settings to hear addon-managed soundtracks.") end
    end
    if self.UpdateStatus then self:UpdateStatus() end
end

function A:Play(emote,once)
    local model, reason = self:FindModel(emote)
    if not model then self:Message(reason);return false end
    if not model.token then self:Message("Missing text emote record. Re-export DBCs with Include Text Emote Records.");return false end
    if GetUnitSpeed("player")>0 or UnitIsDeadOrGhost("player") or (IsFalling and IsFalling()) or
        (UnitAffectingCombat and UnitAffectingCombat("player")) or
        (UnitCastingInfo and UnitCastingInfo("player")) or (UnitChannelInfo and UnitChannelInfo("player")) then
        self:Message("Stand still and alive to start a dance.");return false
    end
    self.pendingOnce=once==true
    DoEmote(model.token)
    if not self.hasEmoteHook then self:OnEmote(model.token) end
    return true
end

function A:Command(message)
    local command=string.lower(string.match(message or "","^%s*(.-)%s*$"))
    if command=="stop" then self:Stop(true);return end
    if command=="loop" then
        self.db.repeatDances=not self.db.repeatDances
        if self.active then self.active.repeating=self.db.repeatDances and self.active.model.loop~=false and self.active.model.durationMS>=500 end
        if self.active and not self.active.repeating then
            local duration=self.active.model.durationMS/1000
            local prefix=(self.active.model.loopStartMS or 0)/1000
            local period=duration-prefix
            if GetTime()<self.active.started+duration then self.active.endsAt=self.active.started+duration
            else self.active.endsAt=self.active.started+prefix+(math.floor((GetTime()-self.active.started-prefix)/period)+1)*period end
        end
        self:Message("Dance repeat "..(self.db.repeatDances and "enabled." or "disabled; playback ends after this cycle."));return
    end
    local once=string.match(command,"^once%s+([a-z0-9]+)$")
    if once then
        if self.byID[once] then self:Play(self.byID[once],true) else self:Message("Unknown dance: "..once) end
        return
    end
    if command=="music" then
        self.db.music=not self.db.music
        if not self.db.music then self:StopMusic() end
        self:Message("Addon music "..(self.db.music and "enabled." or "disabled."));return
    end
    if command~="" then
        local emote=self.byID[command]
        if emote then self:Play(emote);return end
        self:Message("Use /wds, /wds stop, /wds loop, /wds once <emote>, /wds music or /wds <emote>.");return
    end
    self:ToggleCollection()
end

function A:RegisterAliases()
    local occupied={}
    for key,value in pairs(_G) do
        if type(key)=="string" and string.match(key,"^SLASH_.-%d+$") and type(value)=="string" then occupied[string.lower(value)]=true end
    end
    local index=0
    for _,emote in ipairs(self.data.emotes) do
        local current=emote
        local hasToken=false
        for _,model in ipairs(emote.models) do if model.token then hasToken=true end end
        local alias="/"..emote.id
        if hasToken and string.match(emote.id,"^[a-z][a-z0-9]*$") and not occupied[alias] then
            index=index+1
            local key="WDS_DANCE_"..index
            _G["SLASH_"..key.."1"]=alias
            SlashCmdList[key]=function() A:Play(current) end
            occupied[alias]=true
        end
    end
    SLASH_WOWDANCESTUDIO1="/wds"
    SLASH_WOWDANCESTUDIO2="/wowdancestudio"
    SlashCmdList.WOWDANCESTUDIO=function(message) A:Command(message) end
end

function A:Tick(delta)
    elapsed=elapsed+delta
    if elapsed<0.05 then return end
    elapsed=0
    if self.active then
        if GetUnitSpeed("player")>0 or UnitIsDeadOrGhost("player") or (IsFalling and IsFalling()) then
            self:Stop(false)
        elseif (UnitAffectingCombat and UnitAffectingCombat("player")) or
            (UnitCastingInfo and UnitCastingInfo("player")) or (UnitChannelInfo and UnitChannelInfo("player")) then
            self:Stop(true)
        elseif not self.active.repeating and GetTime()>=self.active.endsAt then
            self:Stop(true)
        elseif self.active.musicNext and GetTime()>=self.active.musicNext then
            self.active.musicNext=nil
            self:StopMusic()
            if self.data.audioMode=="addon" and self.db.music and self.active.model.audio and tonumber(GetCVar("Sound_EnableMusic"))==1 then
                PlayMusic(self.active.model.audio);self.musicActive=true
            end
        end
    end
end

frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LEAVING_WORLD")
frame:RegisterEvent("PLAYER_DEAD")
frame:RegisterEvent("PLAYER_REGEN_DISABLED")
frame:RegisterEvent("UNIT_SPELLCAST_START")
frame:RegisterEvent("UNIT_SPELLCAST_CHANNEL_START")
frame:RegisterEvent("UNIT_MODEL_CHANGED")
frame:RegisterEvent("UNIT_INVENTORY_CHANGED")
frame:SetScript("OnEvent",function(_,event,arg1)
    if event=="ADDON_LOADED" then
        if arg1=="WoWDanceStudio" then A:Initialize() end
    elseif event=="UNIT_MODEL_CHANGED" or event=="UNIT_INVENTORY_CHANGED" then
        if event=="UNIT_MODEL_CHANGED" and arg1=="player" then A:Stop(false) end
        if arg1=="player" and A.window and A.window:IsShown() then A:RefreshCharacter() end
    elseif event=="UNIT_SPELLCAST_START" or event=="UNIT_SPELLCAST_CHANNEL_START" then
        if arg1=="player" then A:Stop(true) end
    elseif event=="PLAYER_REGEN_DISABLED" then A:Stop(true)
    else A:Stop(false) end
end)
frame:SetScript("OnUpdate",function(_,delta) A:Tick(delta) end)
