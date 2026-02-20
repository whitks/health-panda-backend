import requests
import json
import os

BASE = "http://127.0.0.1:5000/api"
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "how-to-cook-rice.jpg")

def main():
    # login
    login_payload = {"email": "test@example.com", "password": "password123"}
    r = requests.post(f"{BASE}/login", json=login_payload)
    print("LOGIN ->", r.status_code)
    print(r.text)
    if r.status_code != 200:
        return
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # upload image
    with open(IMAGE_PATH, "rb") as f:
        files = {"image": (os.path.basename(IMAGE_PATH), f, "image/jpeg")}
        r = requests.post(f"{BASE}/food", headers=headers, files=files)
        print("UPLOAD ->", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2))
        except Exception:
            print(r.text)

if __name__ == "__main__":
    main()
