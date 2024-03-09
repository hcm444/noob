import requests
import json
import time


def fetch_opensky_data(username, password):
    url = "https://opensky-network.org/api/states/all"
    auth = (username, password)

    try:
        response = requests.get(url, auth=auth)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error occurred while fetching OpenSky data: {e}")
        return None


def send_opensky_data_to_flask(data):
    url = "hhttps://stingray-app-85uqm.ondigitalocean.app/api2"
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, data=json.dumps(data), headers=headers)
        response.raise_for_status()
        print("Data sent successfully")
    except requests.exceptions.RequestException as e:
        print(f"Error occurred while sending data to Flask: {e}")


if __name__ == "__main__":
    username = "Henrymou"
    password = "difzo7-jonmyq-fenFan"

    while True:
        opensky_data = fetch_opensky_data(username, password)

        if opensky_data:
            send_opensky_data_to_flask(opensky_data)

        time.sleep(120)  # Adjust the interval as needed
