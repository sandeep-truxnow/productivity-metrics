from collections import OrderedDict

# Team Configuration
TEAMS_DATA = OrderedDict([
    ("A Team", "34e068f6-978d-4ad9-4aef-3bf5eec72f65"),
    ("Avengers", "8d39d512-0220-4711-9ad0-f14fbf74a50e"),
    ("Jarvis", "1ec8443e-a42c-4613-bc88-513ee29203d0"),
    ("Mavrix", "1d8f251a-8fd9-4385-8f5f-6541c28bda19"),
    ("Phoenix", "ac9cc58b-b860-4c4d-8a4e-5a64f50c5122"),
    ("Quantum", "99b45e3f-49de-446c-b28d-25ef8e915ad6")
])

# JIRA Configuration
JIRA_CONFIG = {
    "url": "https://truxinc.atlassian.net",
    "email": "devops@truxnow.com",
    "token": "ATATT3xFfGF0jW8QvPl3S5MyCZPa1CJt9WmUbTPn0MOr_O5Eh1aePI6tXkdIxrcJKUKa7z7iHLawm3YvYU_zjrAoSPAQkXWZN5V1YekPnBwmjw6tqu_RtmrkDDtnyocECiCBAKN5T6waGfFgm1tRCYfig-xpuO9GvookawoD57V3TRLxQ0qXMvw=0BBD706D"
}

import os

# GitHub Configuration
GITHUB_CONFIG = {
    "org": "truxinc",
    "token": "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"
}

# SonarCloud Configuration
SONAR_CONFIG = {
    "url": "https://sonarcloud.io",
    "token": "2e530c992cce1823f6855c2fbb002f65dd76d383",
    "org": "truxinc"
}

# Tempo Configuration
TEMPO_CONFIG = {
    "token": "NNU9sybMEP1fK7KzlGeek1Quv6GzgH-us"
}

# Sprint Duration Options
DURATION_OPTIONS = OrderedDict([
    ("Current Sprint", "openSprints()"),
    ("Year to Date", "startOfYear()")
])

