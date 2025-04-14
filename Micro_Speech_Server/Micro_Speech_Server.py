import asyncio
from bleak import BleakScanner, BleakClient
import google.generativeai as genai
import os
import random
import struct

api_file = open("GeminiAPIKey/APIKey.txt", "r")
key = api_file.readline()
genai.configure(api_key=key)

model = genai.GenerativeModel(model_name="gemini-1.5-flash")

TARGET_DEVICE_NAME = "Nano33BLE"
TARGET_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
TARGET_CHARACTERISTIC_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
TARGET_CHARACTERISTIC_UUID_COLOR_WRITE = "f0001111-0451-4000-b000-000000000000"

MAX_RETRIES = 3  # Maximum number of retry attempts
RETRY_DELAY = 1  # Delay in seconds between retries

async def find_characteristic(client, service_uuid, characteristic_uuid, property_name):
    for service in client.services:
        if service.uuid == service_uuid:
            for char in service.characteristics:
                if char.uuid == characteristic_uuid and property_name in char.properties:
                    return char
    return None

async def handle_user_input(characteristic, data):
    """Callback function to handle received user input."""
    user_response = data.decode('utf-8').strip()
    print(f"Arduino responded: {user_response}")
    # You'll need a way to correlate this response with the current game state
    # (e.g., using a global variable or passing state).
    global latest_user_response
    latest_user_response = user_response

latest_user_response = None

async def play_color_word_game(client, command_characteristic, color_write_characteristic):
    colors = ["green", "red", "blue"]
    words = ["Yes", "No", "Unknown"]
    score = 0

    print("Let's play the color-word game!")
    print("I will tell you a color, and you say the corresponding word on the Arduino.")

    if not color_write_characteristic or not command_characteristic:
        print("Error: Could not find the required characteristics.")
        return

    # Subscribe to notifications for user input
    await client.start_notify(command_characteristic, handle_user_input)

    for _ in range(5):
        chosen_color = random.choice(colors)
        color_index = colors.index(chosen_color)
        correct_word = words[color_index]
        global latest_user_response
        latest_user_response = None # Reset for each round

        print(f"Gemini says: The LED will be {chosen_color}. Respond on the Arduino.")

        color_byte = 0
        if chosen_color == "green":
            color_byte = 1
        elif chosen_color == "red":
            color_byte = 2
        elif chosen_color == "blue":
            color_byte = 3

        try:
            await client.write_gatt_char(color_write_characteristic.uuid, struct.pack("<B", color_byte), response=True)
            print(f"Sent color '{chosen_color}' to Arduino.")
        except Exception as e:
            print(f"Error writing color: {e}")
            break

        # Wait for a response from the Arduino (using the notification callback)
        timeout = 15  # Set a reasonable timeout
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

        await asyncio.sleep(2) # Short delay between rounds

    await client.stop_notify(command_characteristic)
    print(f"\nGame Over! Your final score is: {score}/{len(range(5))}")

async def main():
    devices = await BleakScanner.discover()
    print("Scanning for devices...")
    target_device = None
    for d in devices:
        print(f"Discovered device: {d.name} ({d.address})")
        if d.name and TARGET_DEVICE_NAME in d.name:
            target_device = d
            break

    if not target_device:
        print(f"Could not find device with name containing '{TARGET_DEVICE_NAME}'")
        return

    async with BleakClient(target_device.address) as client:
        print(f"Connected: {client.is_connected}")

        command_characteristic = None
        color_write_characteristic = None
        retries = 0
        found_all = False

        while retries < MAX_RETRIES and not found_all:
            try:
                services = client.services
                for service in services:
                    print(f"[Service] {service.uuid}: {service.description}")
                    for char in service.characteristics:
                        print(f"  [Characteristic] {char.uuid}: {char.description} ({char.properties})")

                command_characteristic = await find_characteristic(
                    client, TARGET_SERVICE_UUID, TARGET_CHARACTERISTIC_UUID, "read"
                )
                color_write_characteristic = await find_characteristic(
                    client, TARGET_SERVICE_UUID, TARGET_CHARACTERISTIC_UUID_COLOR_WRITE, "write"
                )

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

        while True:
            try:
                data = await client.read_gatt_char(command_characteristic.uuid)
                decoded_data = data.decode('utf-8').strip()
                print(f"Received command: {decoded_data}")

                if decoded_data == "Command: PlayGame":
                    await play_color_word_game(client, command_characteristic, color_write_characteristic)

                elif decoded_data == "Command: Riddle":
                    print("Asking Gemini...")
                    prompt_parts = [
                        "Give me a riddle with four multiple choice answers where only one is right"
                    ]
                    response = model.generate_content(prompt_parts)
                    print(response.text)

                await asyncio.sleep(1)

            except Exception as e:
                print(f"Error reading characteristic: {e}")
                break

        print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(main())