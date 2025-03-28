-- Set indentation to 4 spaces
vim.opt.tabstop = 4      -- Number of spaces that a <Tab> counts for
vim.opt.shiftwidth = 4   -- Number of spaces to use for indentation
vim.opt.expandtab = true -- Use spaces instead of tabs
vim.opt.autoindent = true -- Copy indentation from the previous line
vim.opt.smartindent = true -- Smart auto-indentation

vim.wo.number = true

-- vim.opt.clipboard = "unnamedplus"

-- lazy.nvim plugin manager
require("config.lazy")

