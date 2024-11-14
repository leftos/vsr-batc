import argparse
import json
import os
import re
import requests
import time
import uuid

version = "0.2.6"

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
        "OriginatingNetwork": "BATC</span>",
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

less_compact = False

# Set to the equivalent of %userprofile%\AppData\LocalLow\Skirmish Mode Games, Inc\BeyondATC\Player.log for the current user
log_path = os.path.expanduser("~") + "\\AppData\\LocalLow\\Skirmish Mode Games, Inc\\BeyondATC\\Player.log"

# Implement argparse for playback_emulation and include_user_initiated
parser = argparse.ArgumentParser()
parser.add_argument("-e", "--playback_emulation", help="Enable playback emulation mode", action="store_true")
parser.add_argument("-u", "--include_user_initiated", help="Include user initiated messages", action="store_true")
parser.add_argument("-l", "--log_path", help="Path to the player.log file", default=log_path)
parser.add_argument("-lc", "--less_compact", help="Use less information dense mode", action="store_true")
args = parser.parse_args()

if args.playback_emulation:
    playback_emulation = True
    
if args.include_user_initiated:
    include_user_initiated = True
    
if args.less_compact:
    less_compact = True
    
log_path = args.log_path

user_callsign = "User"
atc_callsign = "ATC"

print(f"VSR BATC Integration v{version}")
print("GitHub: https://github.com/leftos/vsr-batc")
print("Discord: https://discord.gg/UdHpHzxCNr")
print("=====================================")
print("You can minimize this window, but do not close it.")
print("This integration will run in the background without need for interaction from you.")
print("Make sure the ATC App Messages filter is enabled in VSR's settings.")
print("=====================================")
print("Options:")
print(f"Playback Emulation: {playback_emulation}")
print(f"Include User Initiated: {include_user_initiated}")
print(f"Log Path: {log_path}")
print(f"Less Compact: {less_compact}")
print("=====================================")

def is_likely_callsign(string):
    # if the string is at least 2 words long and the last word is a number, it's likely a callsign
    if (len(string.split(' ')) >= 2):
        last_callsign_part = string.split(' ')[-1]
        if last_callsign_part.isnumeric():
            return True
        # if the last callsign part matches the regex [0-9]+[A-Z]+ and it's a total length of 3 characters, then it's likely a european callsign
        if len(last_callsign_part) == 3 and re.match(r'[0-9]+[A-Z]+', last_callsign_part):
            return True
    # if the string is 5 to 6 characters, all caps, optionally with a dash somewhere in the middle, it's likely a callsign
    if len(string) >= 5 and len(string) <= 6 and string.isupper() and string.isalnum() and (string.count('-') == 0 or string.count('-') == 1):
        return True
    return False
    
# Callsign tests
assert(is_likely_callsign("N12345"))
assert(is_likely_callsign("N123RK"))
assert(is_likely_callsign("United 2678"))
assert(is_likely_callsign("Speedbird 9AJ"))
assert(not is_likely_callsign("New York"))
assert(not is_likely_callsign("N**523"))

while True:
    time.sleep(0.5)
    
    # Read player.log file
    if not os.path.exists(log_path):
        continue    
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
    
    # Try to determine the user's callsign, by finding the first line that contains the a comma, followed by a name that ends in an ATC control identifier,
    # and vice-versa
    if not "ATIS" in cur_atc_line and not "METAR" in cur_atc_line and ',' in cur_atc_line:
        first_part = cur_atc_line.split(",")[0]
        second_part = cur_atc_line.split(",")[1].split(",")[0]
        
        if not first_part.startswith("Contact") and any(first_part.endswith(x) for x in atc_identifiers):
            if is_likely_callsign(second_part):
                atc_callsign = first_part
                user_callsign = second_part
        
        if not second_part.startswith(" contact") and any(second_part.endswith(x) for x in atc_identifiers):
            if is_likely_callsign(first_part):
                user_callsign = first_part
                atc_callsign = second_part
    
    # If the last ATC line is different from the current ATC line, send a message
    if last_atc_line != cur_atc_line:
        print()
        print(f"Sending new line: {cur_atc_line}")
        
        last_atc_line = cur_atc_line
        
        if source == "ATC":
            json_data["Headers"]["To"] = user_callsign
            json_data["Headers"]["From"] = atc_callsign
        else:
            json_data["Headers"]["To"] = atc_callsign
            json_data["Headers"]["From"] = user_callsign
            cur_atc_line = cur_atc_line.replace("Speech Transcription Processed: ", "")
            # Surround the cur_atc_line in an HTML color tag with a light purple color to discern user initiated messages
            cur_atc_line = f"<span style='color:#D8BFD8'>{cur_atc_line}</font>"
        
        json_data["Headers"]["From"] += " <span style='font-size: 8px; color:#f5f5f5'>"
        if less_compact:
            json_data["Headers"]["From"] += "<br>"
        json_data["MessageContent"]["Text"] = cur_atc_line
        
        # Make the POST request with JSON body
        response = requests.post(url, json=json_data)

        # Output the response status code and content
        if response.status_code != 200:
            print("Failed to send message to VSR")
            print(f"Status Code: {response.status_code}")
            print(f"Response Content: {response.text}")
        else:
            print("Message sent to VSR successfully")
