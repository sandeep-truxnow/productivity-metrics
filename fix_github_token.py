#!/usr/bin/env python3
"""
Script to help fix GitHub token issues
"""

def fix_github_token():
    print("🔧 GitHub Token Fix Instructions")
    print("=" * 50)
    print()
    print("Your GitHub token is invalid or expired. Here's how to fix it:")
    print()
    print("1. Go to GitHub.com and sign in")
    print("2. Go to Settings > Developer settings > Personal access tokens > Tokens (classic)")
    print("3. Click 'Generate new token (classic)'")
    print("4. Set expiration to 'No expiration' or a long period")
    print("5. Select these scopes:")
    print("   ✅ repo (Full control of private repositories)")
    print("   ✅ read:org (Read org and team membership)")
    print("   ✅ user:email (Access user email addresses)")
    print("6. Generate token and copy it")
    print("7. Update config.py with the new token")
    print()
    print("Current config.py location:")
    print("   /Users/truxx/Sandeep/Project/tools/productivity-metrics/config.py")
    print()
    print("Replace the 'token' value in GITHUB_CONFIG with your new token.")
    print()
    print("Alternative: Use environment variable")
    print("   export GITHUB_TOKEN='your_new_token_here'")
    print("   Then update config.py to use: os.getenv('GITHUB_TOKEN', 'fallback_token')")
    print()
    print("=" * 50)

if __name__ == "__main__":
    fix_github_token()