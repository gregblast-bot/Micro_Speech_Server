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
model = genai.GenerativeModel(model_name="gemini-2.0-flash")

generation_config = genai.types.GenerationConfig(
    temperature=1.0,
    top_p=0.95,
)

# Define bluetooth target device and characteristics.
TARGET_DEVICE_NAME = "Nano33BLE"
TARGET_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
TARGET_CHARACTERISTIC_UUID_SPEECH_READ = "00002a37-0000-1000-8000-00805f9b34fb"
TARGET_CHARACTERISTIC_UUID_COLOR_WRITE = "f0001111-0451-4000-b000-000000000000"
TARGET_CHARACTERISTIC_UUID_METRICS = "f0002222-0451-4000-b000-000000000000"

# Maximum number of retry attempts and delay in seconds between retries.
MAX_RETRIES = 3 
RETRY_DELAY = 1 
# Global variable to store BLE round-trip start time
ble_round_trip_start_time = None

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

async def handle_metrics(characteristic, data):
    """Callback function to handle received metrics."""
    metric = data.decode('utf-8').strip()
    print(f"Received metric: {metric}")
    if metric.startswith("wake_latency:"):
        latency = float(metric.split(":")[1])
        print(f"Wake word detection latency: {latency:.2f} ms")
    elif metric.startswith("ble_write_latency:"):
        latency = float(metric.split(":")[1])
        print(f"BLE write latency (Arduino->Server): {latency:.2f} ms")
        global ble_round_trip_start_time
        if ble_round_trip_start_time is not None:
            round_trip_time = (asyncio.get_event_loop().time() - ble_round_trip_start_time) * 1000
            print(f"BLE round-trip latency: {round_trip_time:.2f} ms")
            ble_round_trip_start_time = None # Reset

# Asynchronous method for finding the characteristic for some bluetooth service
async def handle_user_input(command_characteristic, data):
    # Decode and remove any whitespace.
    user_response = data.decode('utf-8').strip()
    print(f"Arduino responded: {user_response}")

    # This global variable is a simple way of interacting with the game logic.
    global latest_user_response 
    latest_user_response = user_response

async def get_gemini_color():
    prompt_parts = ["Respond only with 1, 2, or 3. Pick one randomly."]
    generation_config = genai.types.GenerationConfig(
        temperature=0.9,
        top_p=0.75,
    )
    start_time = time.time()  # Record start time before calling Gemini
    response = await asyncio.to_thread( model.generate_content, prompt_parts, generation_config=generation_config)
    response = (response.text).strip()
    end_time = time.time()  # Record end time after receiving response
    latency = end_time - start_time
    print(f"Gemini color response latency: {latency:.4f} seconds")

    # Doing numbers instead of colors to prevent model bias.
    if response == "1":
        response = "green"
    elif response == "2":
        response = "red"
    elif response == "3":
        response = "blue"

    # Extract the text response and clean it
    return response

async def ask_gemini(num_colors=10):
    colors = []
    for _ in range(num_colors):
        color = await get_gemini_color()
        if color:
            colors.append(color)
        else:
            print("Warning: Could not get a valid color from Gemini.")
    return colors

# Asynchronous method for playing the color-word game.
async def play_color_word_game(client, command_characteristic, color_write_characteristic, metrics_characteristic):
    colors = ["green", "red", "blue"]
    words = ["Yes", "No", "Unknown"]
    score = 0
    i = 0

    print("Let's play the color-word game!")
    print("Gemini will tell you a color, and you say the corresponding word into the Arduino.")

    print("The corresponding colors and words are: green:Yes, red:No, blue:anything. Remember this!", end='\r')
    time.sleep(30)

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
    # Subscribe to notifications for metrics.
    await client.start_notify(metrics_characteristic, handle_metrics)

    response = await ask_gemini()

    print(f"chosen colors: {response}")

    # Begin game loop and randomize choices.
    for _ in range(10):
        global latest_user_response
        latest_user_response = None
        timeout = 15

        print("Asking Gemini...")
        color_index = colors.index(response[i])
        correct_word = words[color_index]

        print(f"Gemini says: The LED will be {response[i]}. Respond on the Arduino.")

        # Convert color into a byte for sending to the Arduino.
        color_byte = 0
        if response[i] == "green":
            color_byte = 1
        elif response[i] == "red":
            color_byte = 2
        elif response[i] == "blue":
            color_byte = 3

        # Try to pack the integer into a byte and send it to the Arduino. Wait for an acknowledgment.
        try:
            await client.write_gatt_char(color_write_characteristic.uuid, struct.pack("<B", color_byte), response=True)
            print(f"Sent color '{response[i]}' to Arduino.")
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

        i += 1

        # Short delay between rounds.
        await asyncio.sleep(2)

    # Subscribe to notifications for user input when the game ends.
    await client.stop_notify(command_characteristic)
    finalscore = score/len(range(10))
    print(f"\nGame Over! Your final score is: {finalscore}")

    if (finalscore > 0.69):
        print("You received a passing score! ^_^")
    else:
        print("You did not receive a passing score. :'(")


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
                metrics_characteristic = await find_characteristic(client, TARGET_SERVICE_UUID, TARGET_CHARACTERISTIC_UUID_METRICS, "notify")

                # Ensure that all required characteristics were found.
                if command_characteristic and color_write_characteristic and metrics_characteristic:
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
        if not metrics_characteristic:
            print(f"Failed to find notifyable metrics characteristic after {MAX_RETRIES} retries.")
            return

        # Check for commands indefinitely.
        while True:
            try:
                data = await client.read_gatt_char(command_characteristic.uuid)
                decoded_data = data.decode('utf-8').strip()
                print(f"Received command: {decoded_data}")

                # Check for specific commands. The main functionality is to enable the game play with Gemini.
                if decoded_data == "Command: PlayGame":
                    await play_color_word_game(client, command_characteristic, color_write_characteristic, metrics_characteristic)

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