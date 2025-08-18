#!/usr/bin/env python3
"""
Script to test and fix GitHub access issues
"""

import requests
from config import GITHUB_CONFIG

def test_github_access():
    """Test GitHub API access and permissions"""
    print("🔍 Testing GitHub API Access...")
    print("=" * 50)
    
    headers = {
        "Authorization": f"Bearer {GITHUB_CONFIG['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    # Test 1: Check token validity
    print("1. Testing token validity...")
    try:
        response = requests.get("https://api.github.com/user", headers=headers)
        if response.status_code == 200:
            user_data = response.json()
            print(f"   ✅ Token valid for user: {user_data.get('login', 'Unknown')}")
        else:
            print(f"   ❌ Token invalid: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error testing token: {e}")
        return False
    
    # Test 2: Check organization access
    print("\\n2. Testing organization access...")
    try:
        org_url = f"https://api.github.com/orgs/{GITHUB_CONFIG['org']}"
        response = requests.get(org_url, headers=headers)
        if response.status_code == 200:
            org_data = response.json()
            print(f"   ✅ Organization accessible: {org_data.get('name', GITHUB_CONFIG['org'])}")
        else:
            print(f"   ❌ Organization not accessible: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing organization: {e}")
        return False
    
    # Test 3: Check members access
    print("\\n3. Testing members access...")
    try:
        members_url = f"https://api.github.com/orgs/{GITHUB_CONFIG['org']}/members"
        response = requests.get(members_url, headers=headers)
        if response.status_code == 200:
            members = response.json()
            print(f"   ✅ Members accessible: {len(members)} members found")
            if members:
                print(f"   First member: {members[0].get('login', 'Unknown')}")
        else:
            print(f"   ❌ Members not accessible: {response.status_code}")
            print(f"   This usually means the token needs 'read:org' permission")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing members: {e}")
        return False
    
    # Test 4: List some repositories
    print("\\n4. Testing repository access...")
    try:
        repos_url = f"https://api.github.com/orgs/{GITHUB_CONFIG['org']}/repos"
        response = requests.get(repos_url, headers=headers, params={"per_page": 5})
        if response.status_code == 200:
            repos = response.json()
            print(f"   ✅ Repositories accessible: {len(repos)} repos found")
            for repo in repos[:3]:
                print(f"   - {repo.get('full_name', 'Unknown')}")
        else:
            print(f"   ❌ Repositories not accessible: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing repositories: {e}")
        return False
    
    print("\\n" + "=" * 50)
    print("✅ All GitHub API tests passed!")
    return True

if __name__ == "__main__":
    test_github_access()