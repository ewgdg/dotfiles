return {
	{
		"nvim-treesitter/nvim-treesitter",
		build = ":TSUpdate",
		config = function()
			local configs = require("nvim-treesitter.configs")

			configs.setup({
				ensure_installed = {
					"c",
					"python",
					"javascript",
					"html",
					"lua",
					"vim",
					"vimdoc",
					"bash",
					"query",
					"markdown",
					"markdown_inline",
				},

				sync_install = false,
				auto_install = true,
				highlight = { enable = true },
				indent = { enable = true },
			})
		end,
	},
}
