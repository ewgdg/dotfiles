return {
	"ojroques/vim-oscyank",
	event = "VeryLazy",
	config = function()
		-- Only set up OSCYank in SSH sessions or when explicitly needed
		if
			os.getenv("SSH_CLIENT")
			or os.getenv("SSH_TTY")
			or os.getenv("SSH_CONNECTION")
			or vim.fn.has("clipboard_working") == 0
		then
			-- Configure OSCYank
			vim.g.oscyank_silent = false

			-- Auto-sync yanks to system clipboard via OSC52
			-- Handle unnamed (""), + register, and * register
			vim.api.nvim_create_autocmd("TextYankPost", {
				group = vim.api.nvim_create_augroup("oscyank", { clear = true }),
				callback = function()
					local reg = vim.v.event.regname
					if vim.v.event.operator == "y" and (reg == "" or reg == "+" or reg == "*") then
						vim.fn.OSCYank(table.concat(vim.v.event.regcontents, "\n"))
					end
				end,
			})

			vim.notify("OSCYank enabled - yanks will sync to remote clipboard", vim.log.levels.INFO)
		end
	end,
}
