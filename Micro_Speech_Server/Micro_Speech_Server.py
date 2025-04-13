import asyncio
from bleak import BleakScanner, BleakClient
import google.generativeai as genai
import os

api_file = open("GeminiAPIKey/APIKey.txt", "r")
key = api_file.readline()
genai.configure(api_key = key)  # get's your key

model = genai.GenerativeModel(model_name="gemini-1.5-flash")  # replace with your model

prompt_parts = [
  "Give me a riddle with four multiple choice answers where only one is right"  # text prompt (can be before, after, or interleaved)
]
# Replace with your Arduino's BLE name or a part of it
TARGET_DEVICE_NAME = "Nano33BLE"
TARGET_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
TARGET_CHARACTERISTIC_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
once = False

async def main():
    devices = await BleakScanner.discover()
    print("Scanning for devices...")
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
            # Use the `services` property
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
                        # Use the correct method to read the characteristic
                        data = await client.read_gatt_char(target_characteristic.uuid)
                        decoded_data = data.decode('utf-8').strip()  # Assuming data is sent as UTF-8 string
                        print(f"Received: {decoded_data}")
                        await asyncio.sleep(10)  # Adjust delay as needed

                        if (decoded_data == "Command: Yes" and once == False):
                            print("Asking Gemini...")
                            response = model.generate_content(prompt_parts)  # the actual call
                            print(response.text)
                            once == True
                            
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
