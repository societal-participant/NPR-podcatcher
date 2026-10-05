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

Additionally, you will need two different colors of 22g wire to solder the amp to the Pi. 

You will also need an audio cable with a male jack that will connect to the USB

### Software Requirements
The NPR podcatcher runs on Raspberry Pi Bookworm Lite. There is no graphical desktop UI.

To fully update the system:
    
    
    sudo apt update
    sudo apt upgrade -y
    
    
After updating, install essential system packages
```
sudo apt update
sudo apt install -y mpv ffmpeg python3-pygame python3-requests python3-feedparser
```


## Installing the Podcatcher Files

## Configuring the Podcatcher

## Assembling the Podcatcher

## Using the Podcatcher

<!--stackedit_data:
eyJoaXN0b3J5IjpbMzU4Nzc1Nzg5LDMzMjg5MTIzMyw3NjQzOD
QyODIsLTExNDU5MTg2NjAsMTQxNzI3MDYwMSwtMjgzNjEyODkw
LC0xMTYzMDE2Nzc4LDIwMTU0MDc0MTMsLTE5MDI0NzQ4MSwtMT
c3OTM0OTY5OSwtNjM0MTEzMjVdfQ==
-->