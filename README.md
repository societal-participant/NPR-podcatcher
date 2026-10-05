# NPR Podcatcher
The NPR Podcatcher is a dedicated player appliance for listening to your favorite podcasts from NPR (National Public Radio). The podcatcher downloads your specified NPR broadcasts to your Raspberry Pi Zero W, where you can listen to them. 

## About the Podcatcher
### Hardware Requirements
The following hardware is required to build the podcatcher.

 - [Raspberry Pi Zero WH](https://www.waveshare.com/product/raspberry-pi/boards-kits/raspberry-pi-zero/raspberry-pi-zero-w.htm) (with Wifi and Headers)
 - [Waveshare 2.8inch Capacitive Touch Screen LCD for Raspberry Pi, 480×640, DPI, IPS](https://www.waveshare.com/2.8inch-dpi-lcd.htm)
 - [Adafruit Mono 2.5W Class D Audio Amplifier - PAM8302](https://www.adafruit.com/product/2130)
 - [8 Ohm 2 Watt Speaker w/ Wires - 36mm](https://www.adafruit.com/product/6486)
 - [USB Audio Adapter](https://www.adafruit.com/product/1475) (needs to work with Raspberry Pi)

Additionally, you will need two different colors of 22g wire to solder the amp to the Pi. Two pieces of wire are needed and should measure at least 3 inches in length.

You will also need a basic audio cable with a male jack that will be connected to the USB adapter and be soldered to the amp. The audio cable should measure about 5-6 inches in length.

### Software Requirements
The NPR podcatcher runs on Raspberry Pi Bookworm Lite. There is no graphical desktop UI.

To fully update the system:
    
    
    sudo apt update
    sudo apt upgrade -y
    
    
After updating, install essential system packages:
```
sudo apt update
sudo apt install -y mpv ffmpeg python3-pygame python3-requests python3-feedparser
```

## Assembling the Podcatcher
Assembling the podcatcher requires you to complete the following steps:

 1. Solder header pins to the Raspberry Pi Zero, if they are not already soldered.
 2. Solder one wire to Pin 4 on the Pi. (power)
 3. Solder the other wire to Pin 6 on the Pi. (ground)
 4. Attach the screen to the Pi.
 5. 

## Installing the Podcatcher Files

## Configuring the Podcatcher

## Using the Podcatcher

<!--stackedit_data:
eyJoaXN0b3J5IjpbLTg5NTg0Nzg5NiwzMzI4OTEyMzMsNzY0Mz
g0MjgyLC0xMTQ1OTE4NjYwLDE0MTcyNzA2MDEsLTI4MzYxMjg5
MCwtMTE2MzAxNjc3OCwyMDE1NDA3NDEzLC0xOTAyNDc0ODEsLT
E3NzkzNDk2OTksLTYzNDExMzI1XX0=
-->