#!/usr/bin/env bash

# Rename the executable
git mv dotfiles/bin/dotmanage dotfiles/bin/dotman

# Rename the prompt tests
git mv tests/test_dotmanage_update_prompt.py tests/test_dotman_update_prompt.py

# Rename the archived shell script
git mv scripts/dotmanage.sh.archived scripts/dotman.sh.archived

# Rename the python script
git mv scripts/dotmanage.py scripts/dotman.py

echo "Rename complete. Please review the changes using git diff / git status."
