import requests
import json
import time

BASE = "http://127.0.0.1:5000/api"


def pretty(r):
    try:
        return json.dumps(r.json(), indent=2)
    except Exception:
        return r.text


def main():
    print("Starting tests against", BASE)

    # 1) Register
    reg_payload = {
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123"
    }
    r = requests.post(f"{BASE}/register", json=reg_payload)
    print("REGISTER ->", r.status_code)
    print(pretty(r))

    # 2) Login
    login_payload = {"email": "test@example.com", "password": "password123"}
    r = requests.post(f"{BASE}/login", json=login_payload)
    print("LOGIN ->", r.status_code)
    print(pretty(r))
    if r.status_code != 200:
        print("Login failed, aborting further tests")
        return

    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 3) GET profile (should be 404 initially)
    r = requests.get(f"{BASE}/profile", headers=headers)
    print("GET PROFILE ->", r.status_code)
    print(pretty(r))

    # 4) Create profile
    profile_payload = {
        "weight": 70.5,
        "height": 175.0,
        "body_type": "mesomorph",
        "fitness_goal": "build muscle",
        "activity_level": "moderate"
    }
    r = requests.post(f"{BASE}/profile", headers=headers, json=profile_payload)
    print("POST PROFILE ->", r.status_code)
    print(pretty(r))

    # 5) GET profile again (should be 200)
    r = requests.get(f"{BASE}/profile", headers=headers)
    print("GET PROFILE ->", r.status_code)
    print(pretty(r))


if __name__ == "__main__":
    print("Make sure the Flask app is running on http://127.0.0.1:5000")
    time.sleep(1)
    main()
