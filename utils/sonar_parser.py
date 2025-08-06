import requests

# Mapping for numeric ratings to letter grades, as per Streamlit app
RATING_MAP = {
    "1.0": "A",
    "2.0": "B",
    "3.0": "C",
    "4.0": "D",
    "5.0": "E",
    "N/A": "N/A"
}

def make_sonar_request(sonar_token, url_path, params=None, log_list=None):
    """
    Helper function to make authenticated GET requests to the SonarCloud API.
    Handles authentication and basic error checking.
    """
    if log_list is None:
        log_list = [] # Fallback if not provided, though app.py should always provide it

    SONAR_BASE_URL = "https://sonarcloud.io"
    auth_tuple = (sonar_token, "") # requests.auth will handle Basic Auth encoding

    full_url = f"{SONAR_BASE_URL}{url_path}"
    try:
        response = requests.get(full_url, auth=auth_tuple, params=params)
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        # log_list.append(f"[INFO] Sonar API: Successfully retrieved data from {url_path} (Status: {response.status_code})")
        return response.json()
    except requests.exceptions.RequestException as e:
        # FIXED: Changed url_url to full_url for accurate logging
        error_msg = f"SonarCloud API Request Error for {full_url}: {e}"
        log_list.append(f"[ERROR] Sonar API: {error_msg}")
        return {"error": error_msg}

def fetch_all_sonar_projects(sonar_token, org_key, log_list):
    """
    Fetches a list of all project keys and names for a given organization from SonarCloud.
    """
    # log_list.append(f"[INFO] Sonar: Discovering all projects for organization: '{org_key}'...")
    url_path = "/api/components/search"
    params = {"organization": org_key, "qualifiers": "TRK", "ps": 500} # TRK for projects, ps for page size
    
    data = make_sonar_request(sonar_token, url_path, params, log_list)
    if "error" in data:
        return {"error": data["error"]}
    
    projects = []
    for component in data.get("components", []):
        projects.append({
            "key": component['key'],
            "name": component['name'],
            "organization": component['organization']
        })
    log_list.append(f"[INFO] Sonar: Found {len(projects)} projects in '{org_key}'.")
    return projects

def fetch_single_project_metrics(sonar_token, project_key, log_list):
    """
    Fetches specific metrics and ratings for a single SonarCloud project.
    Includes logic for mapping coverage rating to A-E.
    """
    # log_list.append(f"[INFO] Sonar: Fetching metrics for project: '{project_key}'...")
    url_path = "/api/measures/component"
    
    metric_keys_to_fetch = [
        "coverage",
        "bugs",
        "reliability_rating",
        "vulnerabilities",
        "security_rating",
        "security_review_rating",
        "code_smells",
        "sqale_rating", # Maintainability Rating
        "duplicated_lines_density",
        "alert_status", # Quality Gate status (OK, ERROR, NONE)
        "ncloc" # Lines of Code
    ]

    params = {
        "component": project_key,
        "metricKeys": ",".join(metric_keys_to_fetch)
    }

    data = make_sonar_request(sonar_token, url_path, params, log_list)
    if "error" in data:
        return {"error": data["error"], "project_key": project_key}

    metrics_map = {item["metric"]: item.get("value", "N/A") for item in data.get("component", {}).get("measures", [])}
    # sort by component key for consistency
    metrics_map = dict(sorted(metrics_map.items()))

    # Prepare metrics with A-E ratings for display
    processed_metrics = {
        "Project Key": project_key,
        "coverage": metrics_map.get("coverage", "N/A"),
        "bugs": metrics_map.get("bugs", "N/A"),
        "code_smells": metrics_map.get("code_smells", "N/A"),
        "vulnerabilities": metrics_map.get("vulnerabilities", "N/A"),
        "duplicated_lines_density": metrics_map.get("duplicated_lines_density", "N/A"),
        "alert_status": metrics_map.get("alert_status", "N/A"),
        "ncloc": metrics_map.get("ncloc", "N/A"),
        
        # Numeric ratings converted to A-E using RATING_MAP
        "Reliability Rating (A-E)": RATING_MAP.get(metrics_map.get("reliability_rating", "N/A"), "N/A"),
        "Security Rating (A-E)": RATING_MAP.get(metrics_map.get("security_rating", "N/A"), "N/A"),
        "Maintainability Rating (A-E)": RATING_MAP.get(metrics_map.get("sqale_rating", "N/A"), "N/A"),
        "Security Hotspot Rating (A-E)": RATING_MAP.get(metrics_map.get("security_review_rating", "N/A"), "N/A"),

    }
    # log_list.append(f"[INFO] Sonar: Metrics processed for '{project_key}'.")
    return processed_metrics

