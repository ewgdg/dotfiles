--!nonstrict

local STATUS_KEY = "status"
local COMMAND_KEY = "command"

local status = noctalia.state.get(STATUS_KEY) or {
  pinned = false,
  id = "",
}

local function displayTitle()
  local title = tostring(status.title or "")
  if title ~= "" then
    return title
  end
  local appId = tostring(status.app_id or "")
  if appId ~= "" then
    return appId
  end
  return "Pinned Window"
end

local function render()
  local pinned = status.pinned == true
  barWidget.setVisible(pinned)
  if not pinned then
    return
  end

  barWidget.setGlyph("pin")
  barWidget.setText(displayTitle())
  barWidget.setTooltip({
    { key = "Pinned window", value = displayTitle() },
    { key = "Application", value = tostring(status.app_id or "") },
    { key = "Left click", value = "Summon" },
    { key = "Right click", value = "Clear" },
  })
end

local function sendAction(action)
  noctalia.state.set(COMMAND_KEY, { action = action })
end

noctalia.state.watch(STATUS_KEY, function(nextStatus)
  if type(nextStatus) == "table" then
    status = nextStatus
  else
    status = { pinned = false, id = "" }
  end
  render()
end)

render()

function onClick()
  if status.pinned == true then
    sendAction("summon")
  end
end

function onRightClick()
  if status.pinned == true then
    sendAction("clear")
  end
end
