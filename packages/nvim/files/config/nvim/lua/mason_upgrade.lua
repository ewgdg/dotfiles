-- Headless upgrade of every installed Mason package, run by topgrade via
-- `config/topgrade.d/mason.toml`.
--
-- Mason has no built-in headless "upgrade all" (mason.nvim#445), and topgrade's
-- own `:MasonUpdate` call only refreshes registries; it is also skipped because
-- LazyVim lazy-loads mason.nvim, so the command does not exist yet.
local M = {}

-- Generous bound: large servers (e.g. jdtls) download hundreds of MB.
local UPGRADE_TIMEOUT_MS = 30 * 60 * 1000
local POLL_INTERVAL_MS = 200

local function log(message)
	io.stdout:write(message .. "\n")
end

local function wait_for(condition, description)
	if not vim.wait(UPGRADE_TIMEOUT_MS, condition, POLL_INTERVAL_MS) then
		error("timed out waiting for " .. description)
	end
end

local function update_registries(registry)
	local finished, succeeded, result = false, false, nil
	registry.update(function(success, updated_or_error)
		finished, succeeded, result = true, success, updated_or_error
	end)
	wait_for(function()
		return finished
	end, "registry update")
	if not succeeded then
		error("registry update failed: " .. vim.inspect(result))
	end
end

-- Same outdated check as the `:Mason` UI's `U` action.
local function is_outdated(package)
	local latest_version = package:get_latest_version()
	return package:get_installed_version() ~= latest_version and package:is_installable({ version = latest_version })
end

local function upgrade_packages(packages)
	local failures, finished_count = {}, 0
	for _, package in ipairs(packages) do
		log(("Upgrading %s %s -> %s"):format(package.name, package:get_installed_version(), package:get_latest_version()))
		package:install({}, function(success, receipt_or_error)
			if not success then
				table.insert(failures, ("%s: %s"):format(package.name, vim.inspect(receipt_or_error)))
			end
			finished_count = finished_count + 1
		end)
	end
	wait_for(function()
		return finished_count == #packages
	end, "package upgrades")
	if #failures > 0 then
		error("failed to upgrade:\n" .. table.concat(failures, "\n"))
	end
end

local function upgrade_installed_packages()
	-- Load through lazy.nvim so LazyVim's mason opts (registries, paths) apply.
	require("lazy").load({ plugins = { "mason.nvim" } })
	local registry = require("mason-registry")
	update_registries(registry)
	local outdated_packages = vim.tbl_filter(is_outdated, registry.get_installed_packages())
	if #outdated_packages == 0 then
		log("Mason packages are up to date")
		return
	end
	upgrade_packages(outdated_packages)
end

function M.run()
	-- A Lua error in a headless `+lua` command does not exit nvim, so report it
	-- and exit non-zero to let topgrade mark the step as failed instead of hanging.
	local succeeded, error_with_traceback = xpcall(upgrade_installed_packages, debug.traceback)
	if not succeeded then
		io.stderr:write(error_with_traceback .. "\n")
		vim.cmd("cquit 1")
	end
	vim.cmd("qall!")
end

return M
