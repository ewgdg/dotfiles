--!nonstrict

local UPDATE_INTERVAL_MS = 500
local COMMAND_TIMEOUT_MS = 2000
local PINNED_WINDOW_SCRIPT = noctalia.expandPath("~/.config/niri/bin/pinned-window.sh")

local requestInFlight = false
local pinned = false
local windowTitle = ""
local appId = ""
local lastError = ""

local function shellQuote(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function displayTitle()
  if windowTitle ~= "" then
    return windowTitle
  end
  if appId ~= "" then
    return appId
  end
  return "Pinned Window"
end

local function render()
  barWidget.setVisible(pinned)
  if not pinned then
    return
  end

  barWidget.setGlyph("pin")
  barWidget.setText(displayTitle())
  barWidget.setTooltip({
    { key = "Pinned window", value = displayTitle() },
    { key = "Application", value = appId },
    { key = "Left click", value = "Summon" },
    { key = "Right click", value = "Clear" },
  })
end

local function hideWithError(message)
  pinned = false
  windowTitle = ""
  appId = ""
  render()

  if message ~= lastError then
    noctalia.log(`Pinned Window: {message}`)
    lastError = message
  end
end

local function applyStatus(result)
  requestInFlight = false

  if result.exitCode ~= 0 then
    hideWithError(`status command exited with {result.exitCode}: {result.stderr}`)
    return
  end

  local status, decodeError = noctalia.json.decode(result.stdout)
  if type(status) ~= "table" then
    hideWithError(`invalid status JSON: {decodeError or "unknown error"}`)
    return
  end

  lastError = ""
  pinned = status.pinned == true
  windowTitle = pinned and tostring(status.title or "") or ""
  appId = pinned and tostring(status.app_id or "") or ""
  render()
end

local function refreshStatus()
  if requestInFlight then
    return
  end
  if not noctalia.fileExists(PINNED_WINDOW_SCRIPT) then
    hideWithError(`helper not found: {PINNED_WINDOW_SCRIPT}`)
    return
  end

  requestInFlight = true
  local started = noctalia.runAsync(
    shellQuote(PINNED_WINDOW_SCRIPT) .. " status-json",
    applyStatus,
    COMMAND_TIMEOUT_MS
  )
  if not started then
    requestInFlight = false
    hideWithError("failed to start status command")
  end
end

local function runAction(action)
  if not noctalia.fileExists(PINNED_WINDOW_SCRIPT) then
    hideWithError(`helper not found: {PINNED_WINDOW_SCRIPT}`)
    return
  end

  noctalia.runAsync(
    shellQuote(PINNED_WINDOW_SCRIPT) .. " " .. action,
    function(_result)
      refreshStatus()
    end,
    COMMAND_TIMEOUT_MS
  )
end

noctalia.setUpdateInterval(UPDATE_INTERVAL_MS)
render()
refreshStatus()

function update()
  refreshStatus()
end

function onClick()
  if pinned then
    runAction("summon")
  end
end

function onRightClick()
  if pinned then
    runAction("clear")
  end
end
