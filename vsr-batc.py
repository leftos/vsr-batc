import argparse
import json
import os
import requests
import time
import uuid

# To: isn't used but needs to be set, you can use the user's callsign if you have it, 
# From is typically the aircraft's or ATC callsign (important for BATC messages).  
# Originating ID is important as it tells user where it came from (BATC for example) - so it displays in UI as FROM@NETWORK - the example json is shown in the VSR screenshot. 
# originating user id isn't used for this, but is mandatory (for instance its your VATSIM CID), you can user anything (maybe a UUID) - 
# then the message is in the text field. Avoid HTML to start with, frequencies get formatted automatically as links

os.chdir(os.path.dirname(os.path.abspath(__file__)))

url = 'http://localhost:1228/incoming_message'

# generate a random uuid for this session
uuid = uuid.uuid4()

json_data = """
{
    "Headers": {
        "To": "User",
        "From": "Unknown"
    },
    "Metadata": {
        "OriginatingNetwork": "BATC",
        "OriginatingNetworkUserIdentifier": "",
        "MessageClass": 22
    },
    "MessageContent": {
        "Text": ""
    }
}
"""

# Parse the json_data into a json object
json_data = json.loads(json_data)

json_data["Metadata"]["OriginatingNetworkUserIdentifier"] = str(uuid)

last_atc_line = ""

playback_emulation = False
playback_emulation_idx = 330

include_user_initiated = False

# Set to the equivalent of %userprofile%\AppData\LocalLow\Skirmish Mode Games, Inc\BeyondATC\Player.log for the current user
log_path = os.path.expanduser("~") + "\\AppData\\LocalLow\\Skirmish Mode Games, Inc\\BeyondATC\\Player.log"

# Implement argparse for playback_emulation and include_user_initiated
parser = argparse.ArgumentParser()
parser.add_argument("-e", "--playback_emulation", help="Enable playback emulation mode", action="store_true")
parser.add_argument("-u", "--include_user_initiated", help="Include user initiated messages", action="store_true")
parser.add_argument("-l", "--log_path", help="Path to the player.log file", default=log_path)
args = parser.parse_args()

if args.playback_emulation:
    playback_emulation = True
    
if args.include_user_initiated:
    include_user_initiated = True
    
log_path = args.log_path

while True:
    time.sleep(0.5)
    
    # Read player.log file
    lines = []
    with open(log_path, 'r') as file:
        lines = file.readlines()
        
    # If we are in playback emulation mode, only read the first playback_emulation_idx lines, and increment
    if playback_emulation:
        if playback_emulation_idx > len(lines):
            playback_emulation = False
            print("Playback emulation complete, resuming normal operation")
        else:
            lines = lines[:playback_emulation_idx]
            playback_emulation_idx += 1
            print(f"Playback Emulation: {playback_emulation_idx}")
        
    cur_atc_line = None
    source = None
    # Scan the lines from the bottom for the last line that starts with [lat: and then capture the line after that in the buffer into cur_atc_line
    for line in reversed(lines):
        if line.startswith("[lat:"):
            source = "ATC"
            break
        if line.startswith("Speech Transcription Raw:"):
            source = "User"
            break
        cur_atc_line = line
    
    if not source:
        continue
    
    if not cur_atc_line:
        continue
    
    if source == "User" and not include_user_initiated:
        continue
    
    # Try to determine the user's callsign, by finding the first line that contains the a comma, followed by a name that ends in an ATC control identifier
    user_callsign = "User"
    atc_callsign = "ATC"
    for line in reversed(lines):
        if "," in line:
            rest_of_line = line.split(",")[1]
            if rest_of_line.startswith(" contact"):
                continue
            if any(x in rest_of_line for x in ["Radar", "Tower", "Ground", "Center", "Centre", "Approach", "Departure", "Control", "Delivery", "Clearance", "Director", "Info", "Information", "Ramp", "Apron"]):
                user_callsign = line.split(",")[0]
                atc_callsign = line.split(",")[1].split(",")[0]                
                break
    
    # If the last ATC line is different from the current ATC line, send a message
    if last_atc_line != cur_atc_line:
        last_atc_line = cur_atc_line
        
        if source == "ATC":
            json_data["Headers"]["To"] = user_callsign
            json_data["Headers"]["From"] = atc_callsign
        else:
            json_data["Headers"]["To"] = atc_callsign
            json_data["Headers"]["From"] = user_callsign
            cur_atc_line = cur_atc_line.replace("Speech Transcription Processed: ", "")
            # Surround the cur_atc_line in an HTML color tag with a light purple color
            cur_atc_line = f"<font color='#D8BFD8'>{cur_atc_line}</font>"
        
        json_data["MessageContent"]["Text"] = cur_atc_line
        
        # Make the POST request with JSON body
        response = requests.post(url, json=json_data)

        # Output the response status code and content
        print(f"Status Code: {response.status_code}")
        print(f"Response Content: {response.text}")
