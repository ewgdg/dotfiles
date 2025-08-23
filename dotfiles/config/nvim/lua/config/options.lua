-- This file is automatically loaded by plugins.core
-- Options are automatically loaded before lazy.nvim startup
-- Default options that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/options.lua
-- Add any additional options here

vim.opt.wrap = true

-- Configure clipboard to only sync yanks, not deletions
vim.opt.clipboard = ""  -- Disable automatic clipboard sync
-- Create autocmd to sync only yanks to system clipboard
vim.api.nvim_create_autocmd("TextYankPost", {
  pattern = "*",
  callback = function()
    if vim.v.event.operator == "y" then
      vim.fn.setreg("+", vim.fn.getreg('"'))
    end
  end,
})
