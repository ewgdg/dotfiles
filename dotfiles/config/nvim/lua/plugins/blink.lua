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
			["<C-e>"] = { "show", "cancel", "fallback" },
			["<CR>"] = { "accept", "fallback" },
			["<C-y>"] = { "select_and_accept", "fallback" },
		},
	},
}
