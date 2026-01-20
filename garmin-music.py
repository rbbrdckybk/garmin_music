# Copyright 2026, Bill Kennedy (https://github.com/rbbrdckybk)
# SPDX-License-Identifier: MIT

# Usage help: python garmin-music.py --help
# Example: python garmin-music.py --input_dir "C:\Music\Playlists" --output_dir "C:\Music\Garmin" --bitrate 320k

from pydub import AudioSegment
from mutagen.easyid3 import EasyID3
from mutagen import File
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TPE1, TALB, TIT2, TRCK
from mutagen.flac import Picture, FLAC
from mutagen.mp3 import MP3
from collections import deque
from os.path import exists
import os
import re
import shutil
import argparse
import mutagen


# for easy reading of playlist files
class TextFile():
    def __init__(self, filename):
        self.lines = deque()
        if exists(filename):
            with open(filename, encoding = 'utf-8') as f:
                l = f.readlines()

            for x in l:
                # remove newline and whitespace
                x = x.strip('\n').strip();
                # remove non-song entries
                x = x.split('#', 1)[0].strip();
                if x != "":
                    # these lines are actual songs
                    self.lines.append(x)

    def next_line(self):
        return self.lines.popleft()

    def lines_remaining(self):
        return len(self.lines)


# retrieves the bitrate of an MP3 file in kbps
def get_mp3_bitrate(file_path):
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        audio = MP3(file_path)
        bitrate_bps = audio.info.bitrate  # Bitrate in bits per second (bps)
        bitrate_kbps = bitrate_bps // 1000 # Convert to kilobits per second (kbps)
        return bitrate_kbps
    except Exception as e:
        return f"Error reading bitrate: {e}"
        
        
# copies all common metadata tags from source -> destination audio file        
def copy_all_tags(source_file, destination_file):
    # Load source tags using EasyID3
    source_audio = mutagen.File(source_file, easy=True)
    
    if source_audio is None:
        print('\tCould not open ' + source_file + ' or determine file type; skipping...')
    else:
        # Load destination file
        destination_audio = mutagen.File(destination_file, easy=True)
        
        if destination_audio is None:
            print(f"Could not open {destination_file} or determine file type.")
        else:
            # Copy all tags from source to destination
            for key, value in source_audio.items():
                try:
                    destination_audio[key] = value
                except mutagen.easyid3.EasyID3KeyError as e:
                    # ignore invalid key errors
                    pass
                except Exception as e:
                    print('\tAn error occurred: ' + str(type(e).__name__) + ' – ' + str(e))

            # Save the destination file
            destination_audio.save()
            print('\tSuccessfully copied metadata tags from ' + source_file + ' to ' + destination_file)
            

# copies album art from source -> destination audio file  
def copy_art(source_path, target_path):
    # Load Source File & Extract Art
    source_audio = File(source_path)
    source_art = None
    if isinstance(source_audio, FLAC):
        # FLAC uses Picture objects
        for pic in source_audio.pictures:
            if pic.type == 3: # PictureType.COVER_FRONT
                source_art = pic
                break
    elif isinstance(source_audio, (MP3, ID3)):
        # MP3 uses APIC frames
        for apic in source_audio.tags.getall('APIC'):
            if apic.type == 3: # APIC.PictureType.FRONT_COVER
                source_art = apic
                break
    else:
        print('\tUnsupported source audio file type for album art extraction: ' + source_path)
        return
        
    if not source_art:
        print('\tNo album cover art found in source audio file: ' + source_path)
        return

    # Load Target File & Prepare for Art Addition
    target_audio = File(target_path)
    if isinstance(target_audio, FLAC):
        target_audio.clear_pictures() # Remove old FLAC pictures
        new_pic = Picture()
        new_pic.type = source_art.type
        new_pic.mime = source_art.mime
        new_pic.desc = source_art.desc
        new_pic.data = source_art.data
        target_audio.add_picture(new_pic)
    elif isinstance(target_audio, (MP3, ID3)):
        # Ensure ID3 tag exists for MP3
        if not target_audio.tags:
            target_audio.add_tags()
        target_audio.tags.delall('APIC') # Remove old MP3 APIC frames
        # Create new APIC frame for MP3
        #target_audio.tags.add(APIC(3, source_art.mime, 3, u'cover', data=source_art.data))
        new_apic = APIC(
            encoding=3, # UTF-8
            mime=source_art.mime,
            type=3, # Front Cover
            desc='Cover',
            data=source_art.data
        )
        target_audio.tags.add(new_apic)
    else:
        print('\tUnsupported target file type: ' + target_path)
        return

    # Save Target File
    target_audio.save()
    print('\tCopied album cover art from ' + os.path.basename(source_path) + ' to ' + os.path.basename(target_path))


# converts music files to mp3
def transcode_to_mp3(input_file, output_file, bitrate='320k', audio_format=''):
    
    input_format = audio_format.lower().strip()
    if input_format == '':
        # Determine the input format from the file extension
        input_format = os.path.splitext(input_file)[1].strip('.').lower()
        if not input_format:
            print('\tCannot determine format for ' + input_file + ', skipping...')
            return 'unknown format'

    try:
        # Load the audio file using the correct format
        sound = AudioSegment.from_file(input_file, format=input_format)

        # Export the audio to MP3 format with a specified bitrate
        sound.export(output_file, format="mp3", bitrate=bitrate)
        print('\tSuccessfully transcoded ' + input_file + ' to ' + output_file)

    except Exception as e:
        # if this is an opus file, try forcing ogg format
        if input_format == 'opus':
            print('\tAn error occurred during transcoding of .opus source file, retrying as .ogg...')
            transcode_to_mp3(input_file, output_file, bitrate=bitrate, audio_format='ogg')
            return 'opus second attempt'

        print('\tAn error occurred: ' + str(type(e).__name__) + ' – ' + str(e))
        print('\tMake sure FFmpeg is installed and in your system''s PATH!')
        return str(e)
    else:
        # copy metadata tags to the new file
        copy_all_tags(input_file, output_file)
        copy_art(input_file, output_file)
    return ''


# handles 
def process_playlist(playlist, options):
    print('\nWorking on "' + playlist + '":')
    # Read songs from specified playlist file
    pf = TextFile(playlist)
    total = pf.lines_remaining()
    
    if pf.lines_remaining() == 0:
        print('No songs in "' + playlist + '", aborting!')
        return
    else:
        print('Found ' + str(total) + ' songs in "' + playlist + '", starting...')
        
    # create output directory if it does not already exist;
    # create output playlist file
    os.makedirs(options.output_dir, exist_ok=True)
    n, e = os.path.splitext(os.path.basename(playlist))
    output_filename = os.path.join(options.output_dir, n + '.m3u8')
    output_file = open(output_filename, "w", encoding = 'utf-8')
            
    invalid_chars = []
    if options.invalid_chars != '':
        invalid_chars = list(options.invalid_chars)
        
    # interate through playlist: transcode, rename, and write each song to output dir
    count = 0
    while pf.lines_remaining() > 0:
        count += 1
        song = pf.next_line()
        
        # replace any invalid OS characters in song names from the playlist before starting processing
        for c in invalid_chars:
            if c in song:
                print('\tReplaced invalid "' + str(c) + '" character(s) in "' + song + '"...')
                song = song.replace(c, options.replacement_char)
        
        full_path_song = os.path.join(options.input_dir, song)
        
        # process each song
        if exists(full_path_song):
            # get the output path; make output folders where necessary
            # replace special chars in song filenames with underscores
            n, e = os.path.splitext(os.path.basename(song))
            pattern = r'[^a-zA-Z0-9_ -]'
            cleaned_name = re.sub(pattern, options.replacement_char, n)
            output_songname = cleaned_name + '.mp3'
            if options.strip_leading_track_numbers:
                # attempt to strip leading track numbers if requested
                try:
                    track_num = output_songname.split(' - ', 1)[0].strip()
                    int(track_num)
                except:
                    # not a track number, do nothing
                    pass
                else:
                    # looks like a track number, remove it
                    output_songname = output_songname.split(' - ', 1)[1]    
            output_path_song = os.path.join(options.output_dir, os.path.dirname(song))
            output_path_song = os.path.join(output_path_song, output_songname)
            os.makedirs(os.path.dirname(output_path_song), exist_ok=True)
            
            # transcode
            print('[' + str(count) + '/' + str(total) + '] Transcoding "' + full_path_song + '" to ' + options.bitrate + 'bps MP3...')
            
            format = os.path.splitext(full_path_song)[1].strip('.').lower()
            copy_instead = False
            bitrate = 0
            if format == 'mp3':
                bitrate = get_mp3_bitrate(full_path_song)
                try:
                    float(bitrate)
                except:
                    pass
                else:
                    if float(bitrate) <= float(target_bitrate):
                        copy_instead = True

            error = ''
            if copy_instead:
                print('\tSource file is already at or under target transcoding bitrate (' + str(bitrate) + 'kbps), copying instead...')
                shutil.copy2(full_path_song, output_path_song)
            else:
                error = transcode_to_mp3(full_path_song, output_path_song, bitrate=options.bitrate)
            
            # write to the playlist file if no transcoding errors
            if error == '':
                # get the path relative to the playlist file
                relative_path_song = full_path_song
                if options.input_dir != '':
                    relative_path_song = full_path_song.replace(options.input_dir, '', 1)
                    if not options.input_dir.startswith(os.sep):
                        if relative_path_song.startswith(os.sep):
                            relative_path_song = relative_path_song[1:]
                relative_path_song = os.path.dirname(relative_path_song)
                relative_path_song = os.path.join(relative_path_song, output_songname)
                            
                # write the song to the output playlist
                garmin_path = relative_path_song.replace(os.sep, "/")
                output_file.write(options.garmin_music_root_path + garmin_path + '\n')
        else:
            print('Error: specified playlist entry "' + full_path_song + '" does not exist!')
    output_file.close()


# entry point
if __name__ == '__main__':
    print('\nStarting...\n')
    
    # define command-line args
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--input_dir',
        type=str,
        required=True,
        help='the input folder; all playlists found in this folder will be processed'
    )
    ap.add_argument(
        '--output_dir',
        type=str,
        default='output',
        help='the output directory'
    )
    ap.add_argument(
        '--bitrate',
        type=str,
        default='320k',
        help='bitrate of encoded mp3 files, e.g.: 160k, 256k, 320k, etc'
    )
    ap.add_argument(
        '--invalid_chars',
        type=str,
        default='<>":|?*',
        help='invalid OS chars that may be present in playlist files'
    )
    ap.add_argument(
        '--replacement_char',
        type=str,
        default='_',
        help='replace all invalid characters with this character'
    )
    ap.add_argument(
        '--garmin_music_root_path',
        type=str,
        default='Music/',
        help='root path your Garmin device expects to find your music; will be prepended to all playlist songs'
    )
    ap.add_argument(
        '--strip_leading_track_numbers',
        action='store_true',
        default=False,
        help='attempt to remove leading track numbers; useful you use Navidrome and it auto-adds them during playlist downloads'
    )
    options = ap.parse_args()
    
    # do some sanity checks on input options
    if not os.path.isdir(options.input_dir):
        print('Error: specified input folder "' + options.input_dir + '" does not exist; aborting!')
        exit(-1)
    
    target_bitrate = options.bitrate.lower().replace('k', '')
    try:
        float(target_bitrate)
    except:
        print('Error: specified bitrate (' + options.bitrate + ') is not valid; aborting!')
        exit(-1)
        
    if not options.bitrate.lower().endswith('k'):
        options.bitrate = options.bitrate + 'k'

    print("Input path: " + options.input_dir)
    print("Output path: " + options.output_dir)
    
    # collect playlist files in input directory
    files = []
    for item_name in os.listdir(options.input_dir):
        full_path = os.path.join(options.input_dir, item_name)
        if os.path.isfile(full_path):
            if full_path.lower().endswith('.m3u') or full_path.lower().endswith('.m3u8'):
                files.append(full_path)
    
    print('\nFound ' + str(len(files)) + ' playlist(s) in "' + options.input_dir + '".')
    
    # process each found playlist
    for file in files:
        process_playlist(file, options)

    print('\nDone!')