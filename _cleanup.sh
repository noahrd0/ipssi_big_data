#!/bin/bash
cd /mnt/c/Users/33650/Downloads/ipssi_big_data_entreprise/big_data_entreprise
git rm -f .git_commit_gold.sh 2>/dev/null || true
git add -A
git diff --cached --quiet || git commit -m "Retire script git temporaire"
git push
