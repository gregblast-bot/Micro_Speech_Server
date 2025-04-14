/* Copyright 2022 The TensorFlow Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
==============================================================================*/

#if defined(ARDUINO) && !defined(ARDUINO_ARDUINO_NANO33BLE)
#define ARDUINO_EXCLUDE_CODE
#endif  // defined(ARDUINO) && !defined(ARDUINO_ARDUINO_NANO33BLE)

#ifndef ARDUINO_EXCLUDE_CODE

#include "Arduino.h"
#include "command_responder.h"
#include "tensorflow/lite/micro/micro_log.h"
#include <ArduinoBLE.h>  // Include the ArduinoBLE library


// Toggles the built-in LED every inference, and lights a colored LED depending
// on which word was detected.
void colorWriteCallback(BLEDevice central, BLECharacteristic characteristic) {
  if (characteristic.written()) {
    byte colorCode = characteristic.value()[0]; // Get the first byte of the written value
    Serial.print("Received color code from: ");
    Serial.print(central.address()); // You can now access the central device's address
    Serial.print(", Color code: ");
    Serial.println(colorCode);

    digitalWrite(LEDR, HIGH);
    digitalWrite(LEDG, HIGH);
    digitalWrite(LEDB, HIGH);

    // Control your LED based on the colorCode
    if (colorCode == 1) {
      // Turn LED green
      digitalWrite(LEDG, LOW);   // Green for yes
    } else if (colorCode == 2) {
      // Turn LED red
      digitalWrite(LEDR, LOW);   // Red for no
    } else if (colorCode == 3) {
      // Turn LED blue
      digitalWrite(LEDB, LOW);   //  Blue for unknown
    }
  }
}

void RespondToCommand(int32_t current_time, const char* found_command,
                      uint8_t score, bool is_new_command) {
  static bool is_initialized = false;
  static bool ble_initialized = false;
  static int first = 0;
  static BLEService bleService("0000180d-0000-1000-8000-00805f9b34fb"); // Service UUID
  static BLEStringCharacteristic bleCharacteristic("00002a37-0000-1000-8000-00805f9b34fb", BLERead | BLEWrite | BLENotify, 20); // Characteristic UUID
  static BLECharacteristic colorWriteCharacteristic("f0001111-0451-4000-b000-000000000000", BLERead | BLEWrite | BLENotify, 1); // Full custom UUID

  if (!is_initialized) {
    pinMode(LED_BUILTIN, OUTPUT);
    // Pins for the built-in RGB LEDs on the Arduino Nano 33 BLE Sense
    pinMode(LEDR, OUTPUT);
    pinMode(LEDG, OUTPUT);
    pinMode(LEDB, OUTPUT);
    // Ensure the LED is off by default.
    // Note: The RGB LEDs on the Arduino Nano 33 BLE
    // Sense are on when the pin is LOW, off when HIGH.
    digitalWrite(LEDR, HIGH);
    digitalWrite(LEDG, HIGH);
    digitalWrite(LEDB, HIGH);
    is_initialized = true;
  }
  static int32_t last_command_time = 0;
  static int count = 0;

  if (ble_initialized){
    MicroPrintf("BLE advertising...");
    BLE.advertise();
    if (first > 0 && first < 50){
      bleCharacteristic.writeValue("Command: PlayGame");
      first++;
    }
  }

  if (is_new_command) {
    MicroPrintf("Heard %s (%d) @%dms", found_command, score, current_time);
    // If we hear a command, light up the appropriate LED
    digitalWrite(LEDR, HIGH);
    digitalWrite(LEDG, HIGH);
    digitalWrite(LEDB, HIGH);

    if (found_command[0] == 'y') {
      //digitalWrite(LEDG, LOW);   // Green for yes

      // Initialize BLE if not already done
      if (!ble_initialized) {
        if (!BLE.begin()) {
          MicroPrintf("Starting BLE failed!");
          return;
        }
        if (first == 0){
          BLE.setLocalName("Nano33BLE");
          BLE.setAdvertisedService(bleService);
          bleService.addCharacteristic(bleCharacteristic);   // Add characteristic to the service
          bleService.addCharacteristic(colorWriteCharacteristic);
          BLE.addService(bleService);   // Add the service to BLE
          colorWriteCharacteristic.setEventHandler(BLEWritten, colorWriteCallback);
          BLE.advertise();
          MicroPrintf("BLE initialized and advertising...");
          // Send data over BLE
          ble_initialized = true;
          first++;
        }
      }

      MicroPrintf("Yes");
      // Send data over BLE
      bleCharacteristic.writeValue("Yes");
    }
    else if (found_command[0] == 'n') {
      //digitalWrite(LEDR, LOW);   // Red for no
      // MicroPrintf("BLE disconnecting...");
      // BLE.disconnect();
      // ble_initialized = false;
      // Send data over BLE
      MicroPrintf("No");
      bleCharacteristic.writeValue("No");
    } else if (found_command[0] == 'u') {
      //digitalWrite(LEDB, LOW);   // Blue for unknown
      MicroPrintf("Unknown");
      bleCharacteristic.writeValue("Unknown");
    } else {
      // silence
    }

    last_command_time = current_time;
  }

  // If last_command_time is non-zero but was >3 seconds ago, zero it
  // and switch off the LED.
  if (last_command_time != 0) {
    if (last_command_time < (current_time - 3000)) {
      last_command_time = 0;
      digitalWrite(LEDR, HIGH);
      digitalWrite(LEDG, HIGH);
      digitalWrite(LEDB, HIGH);
    }
  }

  // Otherwise, toggle the LED every time an inference is performed.
  ++count;
  if (count & 1) {
    digitalWrite(LED_BUILTIN, HIGH);
  } else {
    digitalWrite(LED_BUILTIN, LOW);
  }
}

#endif  // ARDUINO_EXCLUDE_CODE
