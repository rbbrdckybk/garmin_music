# Garmin Music Utility
Simple CLI utility for cleanly transferring music onto your Garmin watch. Handles transcoding, avoids Garmin character/filename issues, and preserves metadata & album art. No need to install or use Garmin Connect.

I created this after being frustrated with Garmin's embarrassing lack of support for self-hosted audio libraries. Often, my music files would not be available on my Garmin devices after copying them with Garmin Connect due to various long-standing bugs [such as this one](https://forums.garmin.com/outdoor-recreation/outdoor-recreation/f/fenix-6-series/195023/problem-with-all-songs-in-playlists-that-have-accented-characters-in-the-artist-or-song-name). 

# Features
 * Converts your playlists to Garmin-friendly .m3u8 files, including the device root and proper path separators.
 * Transcodes all referenced audio files to .mp3 format at your specified bitrate (audio files that are already at or lower than your target bitrate will be directly copied instead of transcoded).
 * Replaces all problematic Garmin characters in filenames with underscores (or whatever character you choose).
 * Copies over metadata from the source audio files.
 * Copies over album cover art from the source audio files (currently only supported for FLAC and .mp3 source files).
 * Handles replacing invalid characters in playlist files due to mixed-OS environments (e.g.: audio files from Navidrome on Linux downloaded to a Windows computer may have characters such as "?" replaced with a "_" due to OS filename restrictions, leaving playlist file references broken). This utility should find and correct these.
 * Does not touch your original playlist/audio files at all. Everything is created as a copy in a location of your choice.

# Usage

I've tested this with a Forerunner 265 and Vivoactive 4, mainly with music (90% FLAC, 10% other formats) downloaded from a personal Navidrome instance to a Windows computer without any issues.

You'll need [Python 3.10+](https://www.python.org/downloads/) installed.

**[1]** Install [FFMpeg](https://www.ffmpeg.org/) and add it to your path (Windows example below, assuming you installed it to C:\Applications\ffmpeg). You may need to open an elevated command prompt ("run as administrator") if you get an error about not being able to edit the registry here:
```
setx /m PATH "C:\Applications\ffmpeg\bin;%PATH%"
```
Close and re-open your command prompt and type ```ffmpeg -help``` to ensure that it is working properly.

**[2]** Clone this repository and navigate to it:
```
git clone https://github.com/rbbrdckybk/garmin_music
cd garmin_music
```

**[3]** Install a couple required Python packages:
```
pip install requirements.txt
```

**[4]** Run the utility:
```
python garmin-music.py --playlist "C:\Music\Running\Running 2026.m3u" --output "C:\Music\Garmin" --bitrate 320k
```
Assuming you have a playlist named 'Running 2026.m3u' in **C:\Music\Running**, this will create a folder at **C:\Music\Garmin** with a 'Running_2026.m3u8' playlist and all of your music transcoded to 320kbps .mp3, with internal folder structure preserved. You can then simply copy the contents of **C:\Music\Garmin** to the **/Music** folder on your Garmin device (just plug it into your computer via USB and copy via Windows Explorer; no need for Garmin Connect). On your Garmin device, you should see a **Running 2026** playlist in your "Local Music" (exact name may vary between Garmin models).

You can get additional options with:
```
python garmin-music.py --help
```
