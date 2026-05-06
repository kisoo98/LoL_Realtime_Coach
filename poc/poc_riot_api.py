import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

data = requests.get("https://127.0.0.1:2999/liveclientdata/allgamedata", verify=False).json()
print(data["gameData"]["gameTime"])
