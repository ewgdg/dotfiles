--!nonstrict

local COMMAND_TIMEOUT_MS = 2000
local PINNED_WINDOW_SCRIPT = noctalia.expandPath("~/.config/niri/bin/pinned-window.sh")
local STATUS_KEY = "status"
local COMMAND_KEY = "command"

local pinnedWindowId = ""
local refreshInFlight = false
local refreshQueued = false
local lastError = ""

local function shellQuote(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function logError(message)
  if message ~= lastError then
    noctalia.log(`Pinned Window: {message}`)
    lastError = message
  end
end

local function publishUnpinned()
  pinnedWindowId = ""
  noctalia.state.set(STATUS_KEY, {
    pinned = false,
    id = "",
  })
end

local function publishWindow(window)
  local windowId = tostring(window.id or "")
  if windowId == "" then
    publishUnpinned()
    return
  end

  pinnedWindowId = windowId
  lastError = ""
  noctalia.state.set(STATUS_KEY, {
    pinned = true,
    id = windowId,
    app_id = tostring(window.app_id or ""),
    title = tostring(window.title or ""),
    is_floating = window.is_floating == true,
    workspace_name = tostring(window.workspace_name or ""),
    workspace_id = window.workspace_id,
  })
end

local refreshStatus

local function finishRefresh()
  refreshInFlight = false
  if refreshQueued then
    refreshQueued = false
    refreshStatus()
  end
end

local function applyStatus(result)
  if type(result) ~= "table" or result.exitCode ~= 0 then
    local exitCode = if type(result) == "table" then result.exitCode else "unknown"
    local stderr = if type(result) == "table" then result.stderr else ""
    logError(`status command exited with {exitCode}: {stderr}`)
    publishUnpinned()
    finishRefresh()
    return
  end

  local status, decodeError = noctalia.json.decode(result.stdout)
  if type(status) ~= "table" then
    logError(`invalid status JSON: {decodeError or "unknown error"}`)
    publishUnpinned()
    finishRefresh()
    return
  end

  if status.pinned == true then
    publishWindow(status)
  else
    publishUnpinned()
  end
  finishRefresh()
end

refreshStatus = function()
  if refreshInFlight then
    refreshQueued = true
    return
  end
  if not noctalia.fileExists(PINNED_WINDOW_SCRIPT) then
    logError(`helper not found: {PINNED_WINDOW_SCRIPT}`)
    publishUnpinned()
    return
  end

  refreshInFlight = true
  local started = noctalia.runAsync(
    shellQuote(PINNED_WINDOW_SCRIPT) .. " status-json",
    applyStatus,
    COMMAND_TIMEOUT_MS
  )
  if not started then
    refreshInFlight = false
    logError("failed to start status command")
    publishUnpinned()
  end
end

local function handleWindowsChanged(payload)
  if pinnedWindowId == "" or type(payload.windows) ~= "table" then
    return
  end

  for _, window in payload.windows do
    if type(window) == "table" and tostring(window.id or "") == pinnedWindowId then
      publishWindow(window)
      return
    end
  end

  refreshStatus()
end

local function handleNiriEvent(line)
  local event = noctalia.json.decode(line)
  if type(event) ~= "table" then
    return
  end

  local changed = event.WindowOpenedOrChanged
  if type(changed) == "table" and type(changed.window) == "table" then
    if tostring(changed.window.id or "") == pinnedWindowId then
      publishWindow(changed.window)
    end
    return
  end

  local closed = event.WindowClosed
  if type(closed) == "table" and tostring(closed.id or "") == pinnedWindowId then
    refreshStatus()
    return
  end

  local windowsChanged = event.WindowsChanged
  if type(windowsChanged) == "table" then
    handleWindowsChanged(windowsChanged)
  end
end

local function runAction(action)
  if not noctalia.fileExists(PINNED_WINDOW_SCRIPT) then
    logError(`helper not found: {PINNED_WINDOW_SCRIPT}`)
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

-- A singleton service owns the stream so additional bars render the same state
-- without spawning another Niri subscriber or status poller per output.
if not noctalia.runStream("niri msg -j event-stream", handleNiriEvent) then
  logError("failed to start Niri event stream")
end

noctalia.state.watch(COMMAND_KEY, function(command)
  if type(command) ~= "table" then
    return
  end
  local action = command.action
  if action == "summon" or action == "clear" then
    noctalia.state.set(COMMAND_KEY, nil)
    runAction(action)
  end
end)

function onIpc(event)
  if event == "refresh" then
    refreshStatus()
  end
end

refreshStatus()
