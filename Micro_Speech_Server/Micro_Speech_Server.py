import asyncio
from bleak import BleakScanner, BleakClient
import google.generativeai as genai
import random
import struct
import time


# Get the API key from the file. Not a good method for storing an API key.
api_file = open("GeminiAPIKey/APIKey.txt", "r")
key = api_file.readline()
genai.configure(api_key=key)

# Initialize the Generative Model.
model = genai.GenerativeModel(model_name="gemini-1.5-flash")

# Define bluetooth target device and characteristics.
TARGET_DEVICE_NAME = "Nano33BLE"
TARGET_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
TARGET_CHARACTERISTIC_UUID_SPEECH_READ = "00002a37-0000-1000-8000-00805f9b34fb"
TARGET_CHARACTERISTIC_UUID_COLOR_WRITE = "f0001111-0451-4000-b000-000000000000"

# Maximum number of retry attempts and delay in seconds between retries.
MAX_RETRIES = 3 
RETRY_DELAY = 1 

# Use a global variable to store the latest user response. 
latest_user_response = None


# Asynchronous method for finding the characteristic for some bluetooth service.
async def find_characteristic(client, service_uuid, characteristic_uuid, property_name):
    for service in client.services:
        if service.uuid == service_uuid:
            for char in service.characteristics:
                if char.uuid == characteristic_uuid and property_name in char.properties:
                    return char
    return None


# Asynchronous method for finding the characteristic for some bluetooth service
async def handle_user_input(command_characteristic, data):
    # Decode and remove any whitespace.
    user_response = data.decode('utf-8').strip()
    print(f"Arduino responded: {user_response}")

    # This global variable is a simple way of interacting with the game logic.
    global latest_user_response 
    latest_user_response = user_response


# Asynchronous method for playing the color-word game.
async def play_color_word_game(client, command_characteristic, color_write_characteristic):
    colors = ["green", "red", "blue"]
    words = ["Yes", "No", "Unknown"]
    score = 0

    print("Let's play the color-word game!")
    print("Gemini will tell you a color, and you say the corresponding word into the Arduino.")

    print("The corresponding colors and words are: green:Yes, red:No, blue:anything. Remember this!", end='\r')
    time.sleep(10)

    # ANSI escape code to clear the line. Clears to the right of the cursor.
    print("\033[K", end='\r')

    print("3...")
    time.sleep(1)
    print("2..")
    time.sleep(1)
    print("1.")
    time.sleep(1)

    # Subscribe to notifications for user input.
    await client.start_notify(command_characteristic, handle_user_input)

    # Begin game loop and randomize choices.
    for _ in range(5):
        chosen_color = random.choice(colors)
        color_index = colors.index(chosen_color)
        correct_word = words[color_index]
        global latest_user_response
        latest_user_response = None
        timeout = 15

        print(f"Gemini says: The LED will be {chosen_color}. Respond on the Arduino.")

        # Convert color into a byte for sending to the Arduino.
        color_byte = 0
        if chosen_color == "green":
            color_byte = 1
        elif chosen_color == "red":
            color_byte = 2
        elif chosen_color == "blue":
            color_byte = 3

        # Try to pack the integer into a byte and send it to the Arduino. Wait for an acknowledgment.
        try:
            await client.write_gatt_char(color_write_characteristic.uuid, struct.pack("<B", color_byte), response=True)
            print(f"Sent color '{chosen_color}' to Arduino.")
        except Exception as e:
            print(f"Error writing color: {e}")
            break

        # Wait for a response from the Arduino, using the notification callback.
        start_time = asyncio.get_event_loop().time()
        while latest_user_response is None and (asyncio.get_event_loop().time() - start_time) < timeout:
            await asyncio.sleep(0.1)

        if latest_user_response is not None:
            print(f"Your input: {latest_user_response}")
            if latest_user_response.lower() == correct_word.lower():
                print("Correct!")
                score += 1
            else:
                print(f"Incorrect. The correct word was '{correct_word}'.")
        else:
            print("No response received from Arduino in time.")

        # Short delay between rounds.
        await asyncio.sleep(2)

    # Subscribe to notifications for user input when the game ends.
    await client.stop_notify(command_characteristic)
    print(f"\nGame Over! Your final score is: {score}/{len(range(5))}")


# Main function to discover devices and connect to the target device.
async def main():
    devices = await BleakScanner.discover()
    target_device = None
    print("Scanning for devices...")

    # Print discovered devices and check for the target device.
    for d in devices:
        print(f"Discovered device: {d.name} ({d.address})")
        if d.name and TARGET_DEVICE_NAME in d.name:
            target_device = d
            break

    # If the target device is not found, print a message and exit.
    if not target_device:
        print(f"Could not find device with name containing '{TARGET_DEVICE_NAME}'")
        return

    # Establish a connection to the target device and process commands.
    async with BleakClient(target_device.address) as client:
        print(f"Connected: {client.is_connected}")

        command_characteristic = None
        color_write_characteristic = None
        retries = 0
        found_all = False

        # Check for services and characteristics on the bluetooth device. Implement retries.
        while retries < MAX_RETRIES and not found_all:
            try:
                services = client.services
                for service in services:
                    print(f"[Service] {service.uuid}: {service.description}")
                    for char in service.characteristics:
                        print(f"  [Characteristic] {char.uuid}: {char.description} ({char.properties})")

                command_characteristic = await find_characteristic(client, TARGET_SERVICE_UUID, TARGET_CHARACTERISTIC_UUID_SPEECH_READ, "read")
                color_write_characteristic = await find_characteristic(client, TARGET_SERVICE_UUID, TARGET_CHARACTERISTIC_UUID_COLOR_WRITE, "write")

                # Ensure that all required characteristics were found.
                if command_characteristic and color_write_characteristic:
                    print("Found required characteristics.")
                    found_all = True
                    break
                else:
                    print(f"Not all characteristics found. Retrying in {RETRY_DELAY} seconds...")
                    retries += 1
                    await asyncio.sleep(RETRY_DELAY)

            except Exception as e:
                print(f"Error during characteristic discovery: {e}")
                retries += 1
                await asyncio.sleep(RETRY_DELAY)

        if not command_characteristic:
            print(f"Failed to find readable command characteristic after {MAX_RETRIES} retries.")
            return
        if not color_write_characteristic:
            print(f"Failed to find writable color characteristic after {MAX_RETRIES} retries.")
            return

        # Check for commands indefinitely.
        while True:
            try:
                data = await client.read_gatt_char(command_characteristic.uuid)
                decoded_data = data.decode('utf-8').strip()
                print(f"Received command: {decoded_data}")

                # Check for specific commands. The main functionality is to enable the game play with Gemini.
                if decoded_data == "Command: PlayGame":
                    await play_color_word_game(client, command_characteristic, color_write_characteristic)

                # The riddle command was used as a test case for talking to Gemini. Leaving this in for future use.
                elif decoded_data == "Command: Riddle":
                    print("Asking Gemini...")
                    prompt_parts = [
                        "Give me a riddle with four multiple choice answers where only one is right."
                    ]
                    response = model.generate_content(prompt_parts)
                    print(response.text)

                await asyncio.sleep(1)

            except Exception as e:
                print(f"Error reading characteristic: {e}")
                break

        print("Disconnected.")


# Entry point for the script. This is where the program starts executing.
if __name__ == "__main__":
    asyncio.run(main())