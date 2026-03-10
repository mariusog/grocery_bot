#!/bin/bash
# Run ruff on Python files after edit/write.
# Claude Code hook: reads JSON from stdin, non-blocking (exit 0).

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path')

# Only lint Python files
if [[ "$FILE_PATH" == *.py ]]; then
  ruff check "$FILE_PATH" 2>&1 | tail -5
fi

exit 0
