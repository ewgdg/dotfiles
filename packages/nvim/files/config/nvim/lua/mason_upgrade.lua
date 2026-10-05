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

local function is_any_installing(packages)
	return vim.iter(packages):any(function(package)
		return package:is_installing()
	end)
end

local function upgrade_installed_packages()
	-- Load through lazy.nvim so LazyVim's mason opts (registries, paths) apply.
	require("lazy").load({ plugins = { "mason.nvim" } })
	local registry = require("mason-registry")
	local installed_count, failures = 0, {}
	-- Registry-wide, so these also report installs LazyVim starts. Installs
	-- complete asynchronously, so subscribing after load misses none.
	registry:on("package:install:success", function(package, receipt)
		installed_count = installed_count + 1
		log(("Installed %s %s"):format(package.name, receipt:get_installed_package_version()))
	end)
	registry:on("package:install:failed", function(package, error)
		table.insert(failures, ("%s: %s"):format(package.name, vim.inspect(error)))
	end)
	update_registries(registry)

	local outdated_packages = vim.tbl_filter(is_outdated, registry.get_installed_packages())
	for _, package in ipairs(outdated_packages) do
		log(("Upgrading %s %s -> %s"):format(package.name, package:get_installed_version(), package:get_latest_version()))
		package:install()
	end

	-- LazyVim's mason config installs missing `ensure_installed` tools from its
	-- registry refresh callback. Mason resumes callbacks synchronously, so those
	-- installs have started by the time `update_registries` returns; wait for
	-- them too, since exiting nvim aborts in-flight installs.
	local all_packages = registry.get_all_packages()
	wait_for(function()
		return not is_any_installing(all_packages)
	end, "package installs")
	if #failures > 0 then
		error("failed to install:\n" .. table.concat(failures, "\n"))
	end
	if installed_count == 0 then
		log("Mason packages are up to date")
	end
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
