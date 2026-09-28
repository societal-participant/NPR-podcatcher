# NPR Podcatcher
The NPR Podcatcher is a dedicated player appliance for listening to your favorite podcasts from NPR (National Public Radio). The podcatcher downloads your specified NPR broadcasts to your Raspberry Pi Zero W, where you can listen to them. 

## About the Podcatcher
### Hardware Requirements
The following hardware is required to build the podcatcher.

 - Raspberry Pi Zero WH (with Wifi and Headers)
 - Waveshare 2.8inch Capacitive Touch Screen LCD for Raspberry Pi, 480×640, DPI, IPS

### Software Requirements

1. Base operating system

-   **Raspberry Pi OS**
    -   Debian Trixie Lite

To fully update the system:
    
    
    sudo apt update
    sudo apt upgrade -y
    
    
2. Essential system packages

-   Python 3
-   Git
-   ALSA utilities
-   mpv
-   FFmpeg

Install these with:

```
sudo apt install -y python3 python3-pip git alsa-utils mpv ffmpeg
```

3. Audio system

-   ALSA installed/configured
-   MAX98357A ALSA device recognized
-   Verify with:
    
    ```
    aplay -l
    ```
    

The expected output:

```
card 0: MAX98357A
```

The player specifically targets:

```
alsa/plughw:MAX98357A
```

## Installing the Podcatcher Files

## Configuring the Podcatcher

## Assembling the Podcatcher

## Using the Podcatcher

<!--stackedit_data:
eyJoaXN0b3J5IjpbMTYxNjIxNTg2MCwtMjgzNjEyODkwLC0xMT
YzMDE2Nzc4LDIwMTU0MDc0MTMsLTE5MDI0NzQ4MSwtMTc3OTM0
OTY5OSwtNjM0MTEzMjVdfQ==
-->