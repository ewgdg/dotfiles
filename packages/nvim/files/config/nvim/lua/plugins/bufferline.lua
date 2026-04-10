return {
  {
    "akinsho/bufferline.nvim",
    -- Load bufferline before argv buffers finish startup. The default VeryLazy
    -- timing shifts the initial window view in multi-file sessions.
    lazy = false,
  },
}
