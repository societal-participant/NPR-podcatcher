# NPR Podcatcher
The NPR Podcatcher is a dedicated player appliance for listening to your favorite podcasts from NPR (National Public Radio). The podcatcher downloads your specified NPR broadcasts to your Raspberry Pi Zero W, where you can listen to them. 

## About the Podcatcher
The NPR Podcatcher is a Raspberry Pi Zero W appliance that downloads NPR show episodes via RSS, plays them back with saved position/resume, and is controlled through a dedicated touchscreen.

### Hardware Requirements
The following hardware is required to build the podcatcher.

 - [Raspberry Pi Zero WH](https://www.waveshare.com/product/raspberry-pi/boards-kits/raspberry-pi-zero/raspberry-pi-zero-w.htm) (with Wifi and Headers)
 - [Waveshare 2.8inch Capacitive Touch Screen LCD for Raspberry Pi, 480×640, DPI, IPS](https://www.waveshare.com/2.8inch-dpi-lcd.htm)
 - [Adafruit Mono 2.5W Class D Audio Amplifier - PAM8302](https://www.adafruit.com/product/2130)
 - [8 Ohm 2 Watt Speaker w/ Wires - 36mm](https://www.adafruit.com/product/6486)
 - [USB Audio Adapter](https://www.adafruit.com/product/1475) (needs to work with Raspberry Pi)

Additionally, you will need two different colors of 22g wire to solder the amp to the Pi. Two pieces of wire are needed and should measure at least 3 inches in length.

You will also need a basic 3.5mm audio cable with a male jack that will be connected to the USB adapter and be soldered to the amp. The audio cable should measure about 5-6 inches in length.

To hold everything together for convenience, you should also 3D print the following Pi Zero stand. It's a simple basic stand designed for the Pi Zero that works really well with this project.

[Raspberry Pi Zero Stand](https://learn.adafruit.com/raspberry-pi-zero-stand/3d-printing)

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

### Assembling the Pi

 1. Solder header pins to the Raspberry Pi Zero, if they are not already soldered.
 2. Solder one wire to Pin 4 on the Pi. (power)
 3. Solder the other wire to Pin 6 on the Pi. (ground)
 4. Attach the screen to the Pi.

### Assembling the Amp
After assembling the Pi, do the following:

 1. Solder the included header pins and terminal to the PAM8302 amp board if they are not already soldered.
 2. Solder the **Ground** wire from the Pi (pin 6) to the **Ground** pin on the amp.
 3. Solder the **Power** wire (pin 4) to the **Vin** pin on the amp.
 4. Cut the audio cable so that the two inner wires are exposed. You should see a red wire and a black wire.
 5. Solder the black wire to the A- pin on the amp.
 6. Solder the red wire to the A+ pin on the amp.
 7. Connect the speaker to the amp by inserting the wires in the terminal on the amp board.

### Connecting Everything Else

After assembling the amp, do the following:

 1. Insert the audio cable into the audio jack on the USB adapter. Be careful to insert it in the correct jack.
 2. Plug the USB adapter into the USB micro-USB port on the Raspberry Pi Zero. If necessary, use a USB to micro-USB adapter to plug in to the Pi.

## Installing the Podcatcher Files
### Getting the Project

To download the project, you have to SSH into the Pi.
```
ssh pi@npr-pi.local
```
Once the operating system loads, you will be on the login screen. Once an internet connection is established, the IP address will be visible at the top of the screen.
```
cd ~
git clone https://github.com/societal-participant/NPR-podcatcher.git npr
cd npr
```

Make sure the folder is named `npr` (the `npr` at the end of the clone command does that). The project's files are:

 - `gui.py`The touchscreen app — this is what runs

 - `player.py` Playback engine (controls mpv)

`downloader.py`

Checks feeds and downloads new episodes

`config.json`

Your shows and settings

The first "Check for New Episodes" creates the episode database (`npr.db`) automatically. Downloaded episodes are stored in the folder set by `audio_directory` in `config.json` (`/home/pi/npr/audio` by default).

## Configuring the Podcatcher

## Using the Podcatcher

<!--stackedit_data:
eyJoaXN0b3J5IjpbNjQyNTM0Njc5LDExMjY1MTgyMDksLTExNT
MwNjk4MzAsLTE1NDM1NTkxNjIsMzMyODkxMjMzLDc2NDM4NDI4
MiwtMTE0NTkxODY2MCwxNDE3MjcwNjAxLC0yODM2MTI4OTAsLT
ExNjMwMTY3NzgsMjAxNTQwNzQxMywtMTkwMjQ3NDgxLC0xNzc5
MzQ5Njk5LC02MzQxMTMyNV19
-->