return {
	"saghen/blink.cmp",
	opts = {
		fuzzy = {
			-- use rust will result in a crash, see https://github.com/Saghen/blink.cmp/issues/2155
			implementation = "lua",
		},
		completion = {
			list = {
				selection = {
					auto_insert = false,
				},
			},
		},
		keymap = {
			preset = "enter",
			["<C-i>"] = { "show", "show_documentation", "hide_documentation" },
			["<CR>"] = { "accept", "fallback" },
			["<C-y>"] = { "select_and_accept", "fallback" },
		},
	},
}
