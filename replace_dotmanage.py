import os
import sys

workspace = "."
files_to_update = [
    "init.sh",
    "README.md",
    "docs/dotdrop-vs-chezmoi-vs-ansible.md",
    "docs/dotdrop-template-update.md",
    "docs/dotdrop-bootstrap.md",
    "tests/test_dotmanage_update_prompt.py",
    "dotfiles/bin/dotmanage",
    "scripts/dotmanage.sh.archived",
    "scripts/dotmanage.py"
]

for f in files_to_update:
    path = os.path.join(workspace, f)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fp:
            content = fp.read()
        
        new_content = content.replace("dotmanage", "dotman").replace("DOTMANAGE", "DOTMAN").replace("Dotmanage", "Dotman")
        
        if content != new_content:
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(new_content)
            print(f"Updated {f}")
