local A=WoWDanceStudio
local rowsPerPage=14
local function label(parent,text,x,y,width,font)
    local value=parent:CreateFontString(nil,"OVERLAY",font or "GameFontNormal")
    value:SetPoint("TOPLEFT",x,y);value:SetWidth(width);value:SetJustifyH("LEFT");value:SetText(text)
    return value
end
local function button(parent,text,x,y,width,action)
    local value=CreateFrame("Button",nil,parent)
    value:SetWidth(width);value:SetHeight(26);value:SetPoint("TOPLEFT",x,y)
    value:SetBackdrop({bgFile="Interface\\Buttons\\WHITE8X8",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",edgeSize=10,insets={left=2,right=2,top=2,bottom=2}})
    value:SetBackdropColor(0.11,0.105,0.14,1);value:SetBackdropBorderColor(0.46,0.38,0.24,1)
    local caption=value:CreateFontString(nil,"OVERLAY","GameFontNormalSmall")
    caption:SetPoint("CENTER");caption:SetWidth(width-8);caption:SetJustifyH("CENTER")
    value:SetFontString(caption);value:SetText(text)
    value:SetNormalFontObject("GameFontNormalSmall");value:SetDisabledFontObject("GameFontDisableSmall")
    value:SetScript("OnEnter",function(self) self:SetBackdropColor(0.24,0.19,0.12,1);self:SetBackdropBorderColor(0.95,0.76,0.38,1) end)
    value:SetScript("OnLeave",function(self) self:SetBackdropColor(0.11,0.105,0.14,1);self:SetBackdropBorderColor(0.46,0.38,0.24,1) end)
    value:SetScript("OnClick",action)
    return value
end

local icons={"Spell_Shadow_Charm","Spell_Holy_DivineSpirit","Spell_Arcane_StarFire","Spell_Nature_AstralRecal","Spell_Holy_BlessingOfAgility"}
local function danceIcon(id)
    local hash=0
    for i=1,#id do hash=hash+string.byte(id,i) end
    return "Interface\\Icons\\"..icons[hash%#icons+1]
end

function A:UpdateStatus()
    if not self.status then return end
    if self.active then self.status:SetText("Dancing: "..self.active.emote.name..(self.active.repeating and " (repeat)" or " (once)"))
    elseif self.data.audioMode=="addon" then self.status:SetText("Music stops when you move. Music volume follows the Music slider.")
    else self.status:SetText("Native audio pack: movement cannot cancel its sound. Build an addon-managed music pack to enable that.") end
end

function A:FrameCharacter()
    -- Keep the unit's race/appearance, but remove armor and weapon attachments
    -- from this preview only. Repeat after asynchronous unit loading.
    self.model:Undress()
    -- Preserve the M2's upright full-body camera. Its projection scales with
    -- the model, so zoom the render viewport rather than the mesh.
    self.model:SetCamera(1)
    self.model:SetFacing(0)
    self.model:SetPosition(0,0,0)
    self.model:SetModelScale(1)
    if not self.preview then self.model:SetSequence(0) end
    self:ApplyZoom()
end

function A:ApplyZoom()
    local zoom=self.zoom or self.db.previewZoom or 1.6
    self.db.previewZoom=zoom
    local factor=zoom/1.6
    -- The embedded camera uses horizontal FOV. Keep the vertical clipping
    -- area fixed while changing width, so dancing heads/hands remain visible.
    self.model:SetWidth(180*factor)
    self.model:SetHeight(301)
end

function A:AdjustZoom(delta)
    self.zoom=math.max(0.2,math.min(1.6,(self.zoom or 1.6)+delta*0.1))
    self:ApplyZoom()
end

function A:RefreshCharacter()
    self.preview=nil
    self.model:SetUnit("player")
    self.zoom=self.db.previewZoom or 1.6
    self:FrameCharacter()
    self.pendingRefresh=GetTime()+0.2
end

function A:Select(emote)
    self.selected=emote
    self.preview=nil
    local model,reason=self:FindModel(emote)
    self.title:SetText(emote.name)
    if model and model.token then
        self.detail:SetText("/"..emote.id.."   |   "..string.format("%.2f seconds",model.durationMS/1000))
        self.playButton:Enable();self.previewButton:Enable()
    else
        self.detail:SetText(reason or "Missing text emote record in this pack.")
        self.playButton:Disable();self.previewButton:Disable()
    end
    self.favoriteButton:SetText(self.db.favorites[emote.id] and "Unfavorite" or "Favorite")
    self:RefreshList()
end

function A:Preview()
    if not self.selected then return end
    local model,reason=self:FindModel(self.selected)
    if not model then self:Message(reason);return end
    local ok=pcall(self.model.SetSequence,self.model,model.animationID)
    if not ok then self:Message("This client could not preview the selected animation.");return end
    self.preview={animationID=model.animationID,durationMS=model.durationMS,loopStartMS=model.loopStartMS,started=GetTime()}
    self:ApplyZoom()
end

function A:RefreshList()
    local query=string.lower(self.search:GetText() or "")
    local matches={}
    for _,emote in ipairs(self.data.emotes) do
        if (not self.favoritesOnly or self.db.favorites[emote.id]) and
           (string.find(string.lower(emote.name),query,1,true) or string.find(emote.id,query,1,true)) then
            matches[#matches+1]=emote
        end
    end
    self.page=math.max(1,math.min(self.page or 1,math.max(1,math.ceil(#matches/rowsPerPage))))
    if self.countLabel then self.countLabel:SetText(#matches.." dances  |  Your collection") end
    self.pageLabel:SetText(self.page.." / "..math.max(1,math.ceil(#matches/rowsPerPage)))
    for index,row in ipairs(self.rows) do
        local emote=matches[(self.page-1)*rowsPerPage+index]
        row.emote=emote
        if emote then
            local model=self:FindModel(emote)
            local color=model and model.token and "|cffffffff" or "|cff888888"
            row.name:SetText(color..emote.name.."|r")
            row.alias:SetText("/"..emote.id)
            row.icon:SetTexture(danceIcon(emote.id))
            row.availability:SetText(model and model.token and "|cff9ccb98READY|r" or "|cff777584NOT IN PACK|r")
            row.star:SetText(self.db.favorites[emote.id] and "*" or "")
            row:SetBackdropColor(self.selected==emote and 0.23 or 0.085,self.selected==emote and 0.19 or 0.08,self.selected==emote and 0.13 or 0.105,1)
            row:SetBackdropBorderColor(self.selected==emote and 0.85 or 0.25,self.selected==emote and 0.65 or 0.23,self.selected==emote and 0.31 or 0.30,1)
            row:Show()
        else row:Hide() end
    end
end

local function panel(parent,x,y,width,height,r,g,b)
    local frame=CreateFrame("Frame",nil,parent)
    frame:SetPoint("TOPLEFT",x,y);frame:SetWidth(width);frame:SetHeight(height)
    frame:SetBackdrop({bgFile="Interface\\Buttons\\WHITE8X8",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",tile=false,edgeSize=12,insets={left=3,right=3,top=3,bottom=3}})
    frame:SetBackdropColor(r,g,b,0.98);frame:SetBackdropBorderColor(0.30,0.28,0.35,1)
    return frame
end

function A:RefreshWheel()
    for i,slot in ipairs(self.wheel) do
        local emote=self.byID[self.db.wheel[i]]
        slot.emote=emote
        slot.caption:SetText(emote and string.sub(emote.name,1,9) or tostring(i))
        slot:SetBackdropColor(emote and 0.22 or 0.06,emote and 0.15 or 0.055,emote and 0.10 or 0.075,1)
    end
end

function A:AddToWheel()
    if not self.selected then return end
    for i=1,8 do if self.db.wheel[i]==self.selected.id then return end end
    for i=1,8 do
        if not self.byID[self.db.wheel[i]] then self.db.wheel[i]=self.selected.id;self:RefreshWheel();return end
    end
    self:Message("Wheel is full. Right-click a slot to clear it.")
end

function A:CreateCollection()
    local window=CreateFrame("Frame","WoWDanceStudioCollection",UIParent)
    self.window=window
    window:SetWidth(980);window:SetHeight(760);window:SetPoint("CENTER")
    window:SetScale(math.min(1,UIParent:GetWidth()*0.96/980,UIParent:GetHeight()*0.96/760))
    window:SetFrameStrata("DIALOG");window:SetClampedToScreen(true)
    window:SetBackdrop({bgFile="Interface\\Buttons\\WHITE8X8",edgeFile="Interface\\DialogFrame\\UI-DialogBox-Border",tile=false,edgeSize=32,insets={left=11,right=12,top=12,bottom=11}})
    window:SetBackdropColor(0.035,0.032,0.045,1)
    window:SetMovable(true);window:EnableMouse(true);window:RegisterForDrag("LeftButton")
    window:SetScript("OnDragStart",function(self) self:StartMoving() end)
    window:SetScript("OnDragStop",function(self) self:StopMovingOrSizing() end)
    local banner=panel(window,16,-14,948,35,0.09,0.075,0.115)
    label(banner,"W O W   D A N C E   S T U D I O",18,-10,850,"GameFontNormal")
    local close=CreateFrame("Button",nil,window,"UIPanelCloseButton");close:SetPoint("TOPRIGHT",-9,-12)
    panel(window,16,-55,584,648,0.055,0.05,0.07)
    local previewPanel=panel(window,608,-55,356,648,0.025,0.022,0.035)
    label(window,"COLLECTION",32,-69,120)
    self.countLabel=label(window,"",150,-69,400,"GameFontHighlightSmall")
    panel(window,30,-90,300,29,0.025,0.023,0.035)
    self.search=CreateFrame("EditBox",nil,window,"InputBoxTemplate")
    self.search:SetWidth(285);self.search:SetHeight(24);self.search:SetPoint("TOPLEFT",40,-92);self.search:SetAutoFocus(false)
    self.search:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
    self.search:SetScript("OnTextChanged",function() A.page=1;A:RefreshList() end)
    self.filterButton=button(window,"All dances",350,-91,220,function(self)
        A.favoritesOnly=not A.favoritesOnly;self:SetText(A.favoritesOnly and "Favorites" or "All dances");A.page=1;A:RefreshList()
    end)
    self.rows={}
    for i=1,rowsPerPage do
        local column=math.floor((i-1)/7);local line=(i-1)%7
        local row=CreateFrame("Button",nil,window)
        row:SetWidth(274);row:SetHeight(58);row:SetPoint("TOPLEFT",28+column*280,-130-line*62)
        row:SetBackdrop({bgFile="Interface\\Buttons\\WHITE8X8",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",tile=false,edgeSize=10,insets={left=3,right=3,top=3,bottom=3}})
        row:SetBackdropBorderColor(0.30,0.25,0.13,0.6)
        local icon=row:CreateTexture(nil,"ARTWORK");icon:SetWidth(42);icon:SetHeight(42);icon:SetPoint("LEFT",8,0)
        icon:SetTexture("Interface\\Icons\\Spell_Shadow_Charm")
        row.icon=icon
        row.name=label(row,"",60,-9,188,"GameFontNormal")
        row.alias=label(row,"",60,-28,180,"GameFontDisableSmall")
        row.star=label(row,"",252,-9,20)
        row.availability=label(row,"",60,-44,188,"GameFontHighlightSmall")
        row:SetScript("OnEnter",function(self) self:SetBackdropBorderColor(0.9,0.72,0.38,1) end)
        row:SetScript("OnLeave",function() A:RefreshList() end)
        row:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square")
        row:SetScript("OnClick",function(self) A:Select(self.emote);A:Preview() end)
        row:SetScript("OnDoubleClick",function(self) if self.emote then A:Play(self.emote) end end)
        self.rows[i]=row
    end
    button(window,"<",360,-665,40,function() A.page=A.page-1;A:RefreshList() end)
    button(window,">",540,-665,40,function() A.page=A.page+1;A:RefreshList() end)
    self.pageLabel=label(window,"",422,-672,110)
    label(window,"Click to preview  /  Double-click to dance",32,-673,315,"GameFontDisableSmall")
    label(previewPanel,"CHARACTER PREVIEW",16,-10,310,"GameFontDisableSmall")
    self.title=label(previewPanel,"Select a dance",14,-367,328,"GameFontNormalLarge")
    self.detail=label(previewPanel,"Click a card to preview. Double-click to dance.",14,-394,328,"GameFontHighlightSmall")
    self.modelViewport=CreateFrame("Frame",nil,previewPanel)
    self.modelViewport:SetWidth(328);self.modelViewport:SetHeight(301)
    self.modelViewport:SetPoint("TOPLEFT",14,-28)
    self.model=CreateFrame("DressUpModel",nil,self.modelViewport)
    self.model:SetWidth(328);self.model:SetHeight(301)
    self.model:SetPoint("CENTER",self.modelViewport,"CENTER",0,0)
    self.model:EnableMouse(false)
    self.modelViewport:EnableMouse(true);self.modelViewport:EnableMouseWheel(true)
    self.modelViewport:SetScript("OnMouseWheel",function(_,delta) A:AdjustZoom(delta) end)
    self.zoomOutButton=button(previewPanel,"Zoom -",14,-334,90,function() A:AdjustZoom(-1) end)
    self.zoomInButton=button(previewPanel,"Zoom +",114,-334,90,function() A:AdjustZoom(1) end)
    self.resetViewButton=button(previewPanel,"Reset",214,-334,100,function() local preview=A.preview
        A.zoom=1.6;A:FrameCharacter();A:ApplyZoom()
        if preview then A.model:SetSequenceTime(preview.animationID,A:AnimationTime(preview,(GetTime()-preview.started)*1000)) end end)
    self.previewButton=button(previewPanel,"Preview",14,-424,100,function() A:Preview() end)
    self.playButton=button(previewPanel,"DANCE",122,-424,100,function() if A.selected then A:Play(A.selected) end end)
    self.playButton:SetBackdropColor(0.30,0.20,0.075,1)
    button(previewPanel,"Stop",230,-424,100,function() A.preview=nil;A.model:SetSequence(0);A:Stop(true) end)
    self.favoriteButton=button(previewPanel,"Favorite",14,-455,150,function()
        if A.selected then A.db.favorites[A.selected.id]=not A.db.favorites[A.selected.id];A:Select(A.selected) end
    end)
    button(previewPanel,"Add to wheel",178,-455,152,function() A:AddToWheel() end)
    label(previewPanel,"FAVORITES WHEEL",108,-492,220)
    self.wheel={}
    for i=1,8 do
        local angle=(i-1)*math.pi/4
        local slot=CreateFrame("Button",nil,previewPanel)
        slot:SetWidth(55);slot:SetHeight(30);slot:SetPoint("TOPLEFT",150+94*math.sin(angle),-558+48*math.cos(angle))
        slot:SetBackdrop({bgFile="Interface\\Buttons\\WHITE8X8",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",edgeSize=12,insets={left=3,right=3,top=3,bottom=3}})
        slot:SetBackdropColor(0.10,0.08,0.04,1);slot:SetBackdropBorderColor(0.72,0.57,0.22,1)
        slot.caption=label(slot,"",4,-10,49,"GameFontHighlightSmall")
        slot:RegisterForClicks("LeftButtonUp","RightButtonUp")
        local index=i
        slot:SetScript("OnClick",function(self,key)
            if key=="RightButton" then A.db.wheel[index]=nil;A:RefreshWheel()
            elseif self.emote then A:Select(self.emote);A:Play(self.emote)
            elseif A.selected then A.db.wheel[index]=A.selected.id;A:RefreshWheel() end
        end)
        self.wheel[i]=slot
    end
    label(previewPanel,"Click to dance  |  Right-click to clear",32,-625,310,"GameFontDisableSmall")
    self.playButton:Disable();self.previewButton:Disable()
    self.status=label(window,"",28,-724,925,"GameFontHighlightSmall")
    window:SetScript("OnShow",function() A:RefreshCharacter();A:RefreshList();A:RefreshWheel();A:UpdateStatus() end)
    window:SetScript("OnHide",function() A.preview=nil end)
    local previewElapsed=0
    window:SetScript("OnUpdate",function(_,delta)
        if A.pendingRefresh and GetTime()>=A.pendingRefresh then
            local resume=A.preview~=nil
            A:FrameCharacter()
            A.pendingRefresh=nil;A:RefreshList();if A.selected then A:Select(A.selected);if resume then A:Preview() end end
        end
        previewElapsed=previewElapsed+delta
        if A.preview and previewElapsed>=1/30 then
            previewElapsed=0
            local p=A.preview
            local ok=pcall(A.model.SetSequenceTime,A.model,p.animationID,A:AnimationTime(p,(GetTime()-p.started)*1000))
            if not ok then A.preview=nil;A:Message("Preview unavailable in this client.")
            end
        end
    end)
    table.insert(UISpecialFrames,"WoWDanceStudioCollection")
    window:Hide()
end

function A:ToggleCollection()
    if not self.window then self:CreateCollection() end
    if self.window:IsShown() then self.window:Hide() else self.window:Show() end
end
