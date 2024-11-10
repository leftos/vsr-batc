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

atc_identifiers = [
    "Approach",
    "Apron",
    "Center",
    "Centre",
    "Clearance",
    "Control",
    "Delivery",
    "Departure",
    "Director",
    "Ground",
    "Info",
    "Information",
    "Oceanic",
    "Radar",
    "Radio",
    "Ramp",
    "Tower"
]

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
last_line_index = -1

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

user_callsign = "User"
atc_callsign = "ATC"

while True:
    time.sleep(0.5)
    
    # Read player.log file
    lines = []
    with open(log_path, 'r') as file:
        lines = file.readlines()
        
    if not playback_emulation and last_line_index == -1:
        last_line_index = len(lines)-1
    
    if last_line_index >= len(lines):
        last_line_index = len(lines)-1
        
    if last_line_index == len(lines)-1:
        continue
        
    cur_atc_line = None
    source = None
    
    lines = list(lines[last_line_index+1:])
    for index, line in enumerate(lines):
        if index == len(lines)-1:
            break
        if line.startswith("[lat:"):
            # This assumes the Voice Key is only logged for co-pilot responses            
            if len(lines) > index+2 and lines[index+2].startswith("Voice Key:"):
                source = "User"
                last_line_index += index+2
            else:
                source = "ATC"
                last_line_index += index+1
        elif line.startswith("Speech Transcription Raw:"):
            source = "User"
            last_line_index += index+1
        cur_atc_line = lines[index+1]
        if source:
            break
    
    if not source:
        continue
    
    if not cur_atc_line:
        continue
    
    if source == "User" and not include_user_initiated:
        continue
    
    # Try to determine the user's callsign, by finding the first line that contains the a comma, followed by a name that ends in an ATC control identifier
    for line in reversed(lines):
        if "," in line:
            first_part = line.split(",")[0]
            second_part = line.split(",")[1].split(",")[0]
            
            if first_part.startswith("Contact"):
                continue
            
            if any(first_part.endswith(x) for x in atc_identifiers):
                atc_callsign = first_part
                user_callsign = second_part.split(",")[0]
                break
            
            if second_part.startswith(" contact"):
                continue
            
            if any(second_part.endswith(x) for x in atc_identifiers):
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
