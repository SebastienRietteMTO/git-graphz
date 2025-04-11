#!/usr/bin/bash

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Remove old build
rm -rf html/
mkdir html

# Mainpage
cat ../README.md | sed '/# Example Graphs/a --> [Current git graph](current_tree.html) <--\n\n' > html/README.md

# Generate html output
../src/gitgraphz/gitgraphz.py -o html/current_tree.html -u https://github.com/SebastienRietteMTO/git-graphz

doxygen Doxyfile
