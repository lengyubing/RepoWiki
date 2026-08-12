#!/usr/bin/env bash
# pre-commit hook: block secrets from entering git history.
# Tokens are DATA, not code. This hook refuses any commit that looks like it
# contains a real API key / secret.
set -e

staged=$(git diff --cached --name-only --diff-filter=ACM | grep -iE '\.(py|ts|tsx|js|json|md|ya?ml|toml|env|txt|cfg|ini|sh)$' || true)

if [ -z "$staged" ]; then
    exit 0
fi

# Collect added lines only (strip the leading "+")
added=$(git diff --cached -- $staged | grep -E "^\+" | grep -vE "^\+\+\+")

# whitelist: placeholders, examples, variable names, CLI help text
whitelist='sk-\.\.\.|sk-xxx|sk-fake|sk-test|sk-your|YOUR_KEY|your-api|your_key|placeholder|example|None|null|""|getenv|os\.environ|req\.|cfg\.|settings\.|kwargs|self\.|Header\(|Field\(|import|localStorage|config set'

found=0

# Check each secret pattern. Use grep -e so patterns starting with "-" are safe.
check_pattern() {
    local label="$1"
    local pattern="$2"
    local matches
    matches=$(printf '%s\n' "$added" | grep -E "$pattern" | grep -viE "$whitelist" || true)
    if [ -n "$matches" ]; then
        echo ""
        echo "COMMIT BLOCKED: possible secret detected ($label)"
        printf '%s\n' "$matches" | head -5
        echo ""
        echo "Tokens are data, not code. If this is a false positive, use 'git commit --no-verify'."
        echo "Otherwise, remove the secret and use environment variables or ~/.repowiki/config.json instead."
        found=1
    fi
}

check_pattern "API key (sk-...)"      'sk-[a-zA-Z0-9_-]{20,}'
check_pattern "api_key assignment"    '[aA]pi[_-]?[kK]ey["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][a-zA-Z0-9_-]{20,}'
check_pattern "secret assignment"     '[sS]ecret["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][a-zA-Z0-9_-]{20,}'
check_pattern "token assignment"      '[tT]oken["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][a-zA-Z0-9_-]{20,}'
check_pattern "password assignment"   '[pP]assword["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][a-zA-Z0-9_-]{8,}'
check_pattern "private key (PEM)"     'BEGIN [A-Z ]*PRIVATE KEY'

exit $found
