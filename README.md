# NPR Podcatcher Setup Guide

## Overview
The NPR Podcatcher is a dedicated player appliance for listening to your favorite podcasts from NPR. 

This guide will teach you how to build your own podcatcher that downloads NPR (National Public Radio) shows, plays them from a touchscreen, and starts by itself when powered on.

## Installation
This topic shows you the necessary requirements and how to install and assemble the podcatcher.

**Time needed:** about 1–2 hours, plus soldering time if your amp needs
header pins.

### Hardware Requirements
The following hardware and parts are required for assembling the podcatcher:

**Computer and storage**
- [A Raspberry Pi Zero WH](https://www.waveshare.com/product/raspberry-pi/boards-kits/raspberry-pi-zero/raspberry-pi-zero-w.htm)
- microSD card (8 GB or larger; use a name-brand card)
- Reliable 5 V power supply 
- micro-USB OTG adapter (for the audio dongle)

**Screen**
- [Waveshare 2.8" DPI LCD, capacitive touch, 480×640](https://www.waveshare.com/2.8inch-dpi-lcd.htm)

**Audio**
- [Adafruit USB Audio Adapter (#1475)](https://www.adafruit.com/product/1475)
- [Adafruit PAM8302 mono 2.5 W Class D amplifier (#2130)](Adafruit%20Mono%202.5W%20Class%20D%20Audio%20Amplifier%20-%20PAM8302)
- [8 Ohm 2 Watt Speaker w/ Wires - 36mm](https://www.adafruit.com/product/6486)
- A 3.5 mm audio cable you can cut or wire to (bare-wire end, or a
  breakout adapter) and some hookup wire

**For setup**
- A computer with an SD card reader
- WiFi name and password
- A GitHub account is not needed to download the project


### Software Requirements
The podcatcher uses Raspberry Pi Bookworm Lite OS. 

---

## Installing the Operating System

1. On your computer, install **Raspberry Pi Imager**
   (<https://www.raspberrypi.com/software/>).
2. Open the program and choose the device **Raspberry Pi Zero**, and the OS
   **Raspberry Pi OS Lite (32-bit)**, the *Bookworm*-based release.

3. Open the customization settings and set the following settings:

| Setting | Description |
|--|--|
| **Hostname** | Enter `npr-pi`. |
| **Username** | Enter `pi`, and enter a password of your choice. |
| **WiFi** | Enter your network name, password, and country. |
| **Enable SSH** | Select the checkbox to enable SSH. |

4. Write the card, put it in the Pi, and power it on.

> **Note:** The username matters: this guide and the service file assume the user is `pi` and the project lives in `/home/pi/npr`. If you pick a different username, adjust those paths wherever they appear.

---

## Powering on for the First Time

After turning on the Pi, wait a few minutes for the first boot, then from your computer:
1. Enter the following command:

```
ssh pi@npr-pi.local
```

2. When prompted, log in with the password you set when writing the SD card.
3. Enter the following command to update the system:

```
sudo apt update
sudo apt full-upgrade -y
```

> **Note:** The Pi Zero W has a WiFi driver
bug that can cause a kernel panic during large installs. If it crashes during `apt`, add `over_voltage=2` on its own line in  `/boot/firmware/config.txt`, reboot, and try again.

---

## Connecting the Screen

The Waveshare 2.8" DPI LCD plugs onto the Pi's 40-pin GPIO header and uses the DPI (parallel) interface, set up through device tree overlays.

To install and configure the display:
1. Power off the Pi and attach the screen to the header.
2. Power the Pi back on and log back in.
3. Enter the following command to open the config file to edit the boot configuration:

   ```
   sudo nano /boot/firmware/config.txt
   ```

4. Add the display and touch overlay lines from Waveshare's documentation for the *2.8inch DPI LCD*. The project uses these overlays:
`vc4-kms-v3d`, `vc4-kms-dpi-2inch8`, the `waveshare-28dpi-*` overlays, and `waveshare-touch-28dpi`.

   <!-- PASTE YOUR WORKING config.txt BLOCK HERE -->

5. Reboot. The screen should light up (it will be showing the text console at first).

**Rotation** is handled by the software, not the operating system. The app has a `ROTATE` setting near the top of `gui.py`; the project is set to
`90`. If the picture or touch is turned the wrong way on your unit, change that one number and touch will follow.

---

## Wiring the Audio

The signal path is as follows:

**Pi → USB audio adapter → 3.5 mm cable → PAM8302 amp → speaker**

Do all wiring and assembling with the Pi **powered off**.

1. Solder wires from the PAM8302 amp to the Pi.

   | PAM8302 pad | Connects to |
   |---|---|
   | Vin | Pi 5 V (physical pin 4) |
   | GND | Pi GND (physical pin 6) |

2. After soldering those wires, solder the wires from the audio cable to the amp. 

   | 3.5 mm plug part | PAM8302 pad |
   |---|---|
   | Tip (left channel) | Solder the red wire to A+ |
   | Sleeve (ground) | Solder the black wire to A- |
   | Ring (right channel) | not used |
3. Plug the other end of the cable to the USB adapter's audio jack.

4. To attach the speaker, connect its two wires to the amp's screw terminals.

5. Plug the **USB adapter** into the Pi Zero's *data* micro-USB port (the one labelled USB, not PWR IN) with the OTG adapter.

**Wiring cautions**
- Always connect the cable through the adapter's jack; do not solder any wires directly onto the adapter's internal pads.

---

## Installing Software

Complete the following steps to install the software needed for this project:

1. Turn on the Pi.
2. After the Pi boots up, SSH into the Pi with your computer.
3. Run the following command:

```
sudo apt install -y mpv ffmpeg python3-pygame python3-requests python3-feedparser git
```

The following table describes what each component is for:

| Package | Used for |
|---|---|
| `mpv` | Plays the audio |
| `ffmpeg` | Provides `ffprobe`, used to read episode lengths |
| `python3-pygame` | The touchscreen interface |
| `python3-requests` | Fetching feeds and downloading episodes |
| `python3-feedparser` | Reading the RSS feeds |
| `git` | Downloading the project |

Everything else that the project uses comes with Python.

---

## Download the Project

Run the following command. This creates a directory for the project, and downloads the project files into that folder.

```
cd ~
git clone https://github.com/societal-participant/NPR-podcatcher.git npr
cd npr
```

Make sure the folder is named `npr`. 

The following table describes the project's files:

| File | Purpose |
|---|---|
| `gui.py` | The user-interactive touchscreen app |
| `player.py` | The playback engine |
| `downloader.py` | Checks the configured feeds and downloads new episodes |
| `config.json` | The configuration file for your shows and settings |

The first time the app checks for new episodes, the episode database is automatically created. 

Downloaded episodes are stored in the folder set
by `audio_directory` in `config.json` (`/home/pi/npr/audio` by default).

---

## Testing the Audio
Complete the following steps to test the audio:

1. Run the following command to confirm that the Pi sees the USB adapter:

   ```
   aplay -l
   ```

   You should see a card named `USB Audio Device` (usually card 1).

2. Run the following command to play a test tone at low volume:

   ```
   speaker-test -D plughw:1,0 -c1 -t sine -f 440 -l1
   ```

   You should hear a short tone. 

  3. If the volume is too loud or too quiet,
   run `alsamixer`, press **F6**, choose the USB device, and adjust.
   4. Press **Ctrl + C** to stop the tone if it is still playing.

The app plays through `alsa/plughw:CARD=Device,DEV=0`, the adapter's default name. If `aplay -l` shows a different card name, change the `--audio-device=` line in `player.py` to match.

---

## Choosing Your Shows

To choose your shows, run the following command to open `config.json`:
`cd npr`
`sudo nano config.json`

The file has two parts: `settings` and `shows`.

```json
{
  "settings": {
    "initial_downloads": 3,
    "download_timeout": 300,
    "feed_timeout": 15,
    "audio_directory": "/home/pi/npr/audio"
  },

  "shows": {
    "up-first": {
      "name": "Up First",
      "feed": "https://feeds.npr.org/510318/podcast.xml",
      "enabled": true
    }
  }
}
```

The following table describes the editable settings:

| Setting | Meaning |
|---|---|
| `initial_downloads` | How many of the newest episodes to fetch for each show |
| `download_timeout` | Seconds to wait on an episode download |
| `feed_timeout` | Seconds to wait on a feed check |
| `audio_directory` | The directory 	where episodes are saved |

To add a show:
1. Copy one entry under `shows` and change the following settings: 
2. give it a new short id, a display
`name`, and the show's `feed` URL. 
3. Set `enabled` to
`false` to keep a show listed but skip it. Mind the commas: every entry
except the last needs one after its closing brace.

The show list that is included with the project is a starting point; change it to whatever you like.

---

## Testing the App
Test running the app manually by running the following command:

```
cd ~/npr
python3 gui.py
```

Soon after, you should see the splash screen. It stays for about 5 seconds, or longer
if the audio engine is still starting. Then, the main menu. 

## Using the App
The main menu shows the following options:
- **Check for New Episodes:** downloads new episodes. A live log shows
  progress.
- **Listen to Recorded Shows:** pick a show, then tap episodes to check them. **Play (n)** plays the checked episodes back to back, **Delete (n)** removes them, and **Cleanup Played** removes everything you have
already listened to.
- **Now Playing:** play/pause, back 30 seconds, forward 30 seconds, and
the elapsed and total time (for example `0:35 / 2:25`). The Now Playing
button appears on the main menu once something has loaded.
- **Episode lengths:** each episode row shows its length, for example
`NEW - 14:32`, or `2:05 / 14:32` if you are partway through.
- **Shutting down safely:** tap the small **X** in the top-right corner of the
main menu, then **Yes**. The Pi saves your place and shows "Shutting down..."; unplug
the power once the green light stops blinking. This is safer than just
pulling the plug, which can corrupt the SD card.
- Playback position is saved every few seconds, so the Pi resumes where
you left off after a power cut.
- Deleted episodes are remembered and will not download again.

Stop the app with **Ctrl+C**. Only run one copy at a time — never run
`gui.py` by hand while the auto-start service (next step) is running.

---

## Configuring Auto-Start at Boot

The following instructions explain how to make it so the Pi auctomatically runs the podcatcher app after booting.

1. Create the service file:

   ```
   sudo nano /etc/systemd/system/npr-gui.service
   ```

2. Paste the following into the file, then save (Ctrl+O, Enter, Ctrl+X):

   ```
   [Unit]
   Description=NPR Podcatcher GUI
   After=sound.target network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=pi
   Group=pi
   SupplementaryGroups=video render input audio
   WorkingDirectory=/home/pi/npr
   ExecStart=/usr/bin/python3 -u /home/pi/npr/gui.py
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Start the service and enable it at boot:

   ```
   sudo systemctl daemon-reload
   systemd-analyze verify /etc/systemd/system/npr-gui.service
   sudo systemctl start npr-gui
   sudo systemctl enable npr-gui
   ```

   (`systemd-analyze verify` prints nothing if the file is fine.)

4. Reboot and confirm the splash screen appears on its own:

   ```
   sudo reboot
   ```

Because the service waits for WiFi to connect, the screen stays blank for a while at boot. If the screen shows nothing after a couple of minutes, see Troubleshooting.

---

## Troubleshooting

**No sound**
1. Run `aplay -l`. If the USB Audio Device is missing, the adapter has dropped off. Power the Pi off completely, unplug it for a few seconds,
   and start it again.
2. Run the test tone from Testing the App topic. If the tone works but episodes do not, check the log (`journalctl -u npr-gui -n 50 --no-pager`).
3. Check volume in `alsamixer` (F6, pick the USB device).
4. Re-check the amp wiring against step 5.

**A particular episode will not play**
The download may have been empty or cut off. Delete it from the list and run Check for New Episodes. The current version rejects empty downloads automatically, so this should be rare.

**Screen stays blank after boot**
- Wait longer: a Zero W with WiFi, the display and the audio engine starting together can take 2–3 minutes.
- Check the log: `journalctl -u npr-gui -n 50 --no-pager`.
- A message such as `video system not initialized` right at boot is normal if the service recovers a few seconds later on its own (`Restart=on-failure`).

**Check for New Episodes shows errors**
- Check the Pi has internet: `curl -sI https://feeds.npr.org/510318/podcast.xml | head -3` should report `200`.
- Check the clock: `date`. A wrong date breaks secure connections, and the Pi has no clock battery, so it needs WiFi to set the time.
- A one-off connection error often clears on its own; the app retries automatically.

**The shutdown X says "Shutdown failed"**
The `pi` user needs permission to run `shutdown` without a password. Test
with `sudo -n true && echo OK`. Raspberry Pi OS grants this to the first user by default; if yours does not, add it with `sudo visudo -f /etc/sudoers.d/010_pi-nopasswd` and the line `pi ALL=(ALL) NOPASSWD: /usr/sbin/shutdown`.

**Screen or touch is rotated or backwards**
Change the `ROTATE` value near the top of `gui.py` (0, 90, 180 or 270).

**Cannot SSH in right after boot**
The Zero W takes a few minutes to finish booting and join WiFi when the app starts at the same time. Wait 2–3 minutes and try again.

**Emergency: stop the app from starting at boot**
Put the SD card in another computer, open `cmdline.txt` on the boot partition, and add `systemd.mask=npr-gui.service` at the end of the single line (with a space before it). Boot the Pi, SSH in, run `sudo systemctl disable npr-gui`, and then remove the text you added.

---

## Appendix: How the pieces fit

- `gui.py` is the only program you run. It loads `player.py` and `downloader.py` as modules, so there is exactly one place that controls mpv and one that checks feeds.
- Playback uses `mpv`, controlled over a local socket (`/tmp/npr-mpv.sock`). Its own error output goes to `/tmp/npr-mpv.log`.
- Playback state (episodes, played flags, saved positions) is kept in the SQLite database `npr.db` in the project folder.
- The audio equalizer filter that shapes the sound for a small speaker is `DEFAULT_AUDIO_FILTER` near the top of `player.py`. It can be retuned without touching any other code.



> Written with [StackEdit](https://stackedit.io/).
<!--stackedit_data:
eyJoaXN0b3J5IjpbMTk5NDE4MzU0MSw1NTY4NTYwNDksLTE3Mz
k3NjQwNjQsMTYyMDA3OTQwMSwxMTI2NTE4MjA5LC0xMTUzMDY5
ODMwLC0xNTQzNTU5MTYyLDMzMjg5MTIzMyw3NjQzODQyODIsLT
ExNDU5MTg2NjAsMTQxNzI3MDYwMSwtMjgzNjEyODkwLC0xMTYz
MDE2Nzc4LDIwMTU0MDc0MTMsLTE5MDI0NzQ4MSwtMTc3OTM0OT
Y5OSwtNjM0MTEzMjVdfQ==
-->