import asyncio
from bleak import BleakScanner, BleakClient
import google.generativeai as genai
import os
import random

api_file = open("GeminiAPIKey/APIKey.txt", "r")
key = api_file.readline()
genai.configure(api_key=key)  # get's your key

model = genai.GenerativeModel(model_name="gemini-1.5-flash")  # replace with your model

# Replace with your Arduino's BLE name or a part of it
TARGET_DEVICE_NAME = "Nano33BLE"
TARGET_SERVICE_UUID = "f0001110-0451-4000-b000-000000000000"
TARGET_CHARACTERISTIC_UUID = "f0001111-0451-4000-b000-000000000000"
TARGET_CHARACTERISTIC_UUID_WRITE = "f0001112-0451-4000-b000-000000000000"

# Ensure this UUID exists and has "write" property on your Arduino's BLE service.

async def play_color_word_game(client):
    colors = ["green", "red", "blue"]
    words = ["GO", "STOP", "WATER"] # Corresponding words
    score = 0

    print("Let's play the color-word game!")
    print("I will tell you a color, and you say the corresponding word.")

    for _ in range(5): # Play 5 rounds
        chosen_color = random.choice(colors)
        color_index = colors.index(chosen_color)
        correct_word = words[color_index]

        print(f"Gemini says: The LED will be {chosen_color}.")

        # Send the color to the Arduino
        if client.is_connected and TARGET_CHARACTERISTIC_UUID_WRITE:
            color_byte = 0
            if chosen_color == "green":
                color_byte = 1
            elif chosen_color == "red":
                color_byte = 2
            elif chosen_color == "blue":
                color_byte = 3

            try:
                # Pack the color_byte into a single byte
                await client.write_gatt_char(TARGET_CHARACTERISTIC_UUID_WRITE, struct.pack("<B", color_byte), response=True)
                print(f"Sent color code '{color_byte}' ({chosen_color}) to Arduino.")
            except Exception as e:
                print(f"Error writing color to Arduino: {e}")
                return # Exit the game if writing fails

        user_input = input("Your word: ").strip().upper()

        if user_input == correct_word:
            print("Correct!")
            score += 1
        else:
            print(f"Incorrect. The correct word was '{correct_word}'.")

        await asyncio.sleep(1) # Small delay between rounds

    print(f"\nGame over! Your final score is {score}/5.")

async def main():
    devices = await BleakScanner.discover()
    print("Scanning for devices...")
    target_device = None
    for d in devices:
        print(f"Discovered device: {d.name} ({d.address})")
        if d.name and TARGET_DEVICE_NAME in d.name:
            target_device = d
            break

    if target_device is None:
        print(f"Could not find device with name containing '{TARGET_DEVICE_NAME}'")
        return

    async with BleakClient(target_device.address) as client:
        print(f"Connected: {client.is_connected}")

        try:
            services = client.services
            for service in services:
                print(f"[Service] {service.uuid}: {service.description}")
                for char in service.characteristics:
                    print(f"  [Characteristic] {char.uuid}: {char.description} ({char.properties})")

            # Find the target characteristic
            target_characteristic = None
            for service in services:
                if service.uuid == TARGET_SERVICE_UUID:
                    for char in service.characteristics:
                        if char.uuid == TARGET_CHARACTERISTIC_UUID and "read" in char.properties:
                            target_characteristic = char
                            break
                    if target_characteristic:
                        break

            if target_characteristic:
                while True:
                    try:
                        data = await client.read_gatt_char(target_characteristic.uuid)
                        decoded_data = data.decode('utf-8').strip()  # Assuming data is sent as UTF-8 string
                        print(f"Received from Arduino: {decoded_data}")
                        await asyncio.sleep(1)  # Adjust delay as needed

                        if decoded_data == "Command: PlayGame":
                            print("Arduino wants to play a game!")
                            await play_color_word_game(client)
                            # Optionally, you might want to send a message back to the Arduino
                            # indicating the game is finished.

                        elif decoded_data == "Command: Riddle":
                            print("Arduino wants a riddle!")
                            prompt_parts = [
                                "Give me a riddle with four multiple choice answers where only one is right"
                            ]
                            response = model.generate_content(prompt_parts)  # the actual call
                            print(f"Gemini's riddle:\n{response.text}")

                    except Exception as e:
                        print(f"Error reading characteristic: {e}")
                        break
            else:
                print(f"Could not find readable characteristic with UUID: {TARGET_CHARACTERISTIC_UUID} in service {TARGET_SERVICE_UUID}")

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(main())