import argparse
import re
import shutil
import urllib.parse
import mutagen

from pathlib import Path
from collections import deque
from pydub import AudioSegment
from mutagen.id3 import APIC, ID3
from mutagen.flac import Picture, FLAC
from mutagen.mp3 import MP3


# for easy reading of playlist files
class TextFile():
    def __init__(self, filepath: Path):
        self.lines = deque()
        if filepath.exists():
            with open(filepath, encoding = 'utf-8') as f:
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
def get_mp3_bitrate(file_path: Path):
    if not file_path.exists():
        return f"Error: File not found at {file_path}"

    try:
        audio = MP3(file_path)
        bitrate_bps = audio.info.bitrate  # Bitrate in bits per second (bps)
        bitrate_kbps = bitrate_bps // 1000 # Convert to kilobits per second (kbps)
        return bitrate_kbps
    except Exception as e:
        return f"Error reading bitrate: {e}"
        
        
# copies all common metadata tags from source -> destination audio file        
def copy_all_tags(source_path: Path, target_path: Path):
    # Load source tags using EasyID3
    source_audio = mutagen.File(source_path, easy=True)
    
    if not source_audio:
        print('\tCould not open ' + source_path + ' or determine file type; skipping...')
    else:
        # Load destination file
        destination_audio = mutagen.File(target_path, easy=True)
        
        if destination_audio is None:
            print(f"Could not open {target_path} or determine file type.")
        else:
            # Copy all tags from source to destination
            for key, value in source_audio.items():
                try:
                    destination_audio[key] = value
                except mutagen.easyid3.EasyID3KeyError as e:
                    # ignore invalid key errors
                    pass
                except ValueError:
                    # Ignore values that might not be set correctly. For instance, had issues with NaN decibel values.
                    pass
                # Let the function fail is something is inherently wrong.

            # Save the destination file
            destination_audio.save()
            print(f"\tSuccessfully copied metadata tags from {source_path} to {target_path}")
            

# copies album art from source -> destination audio file  
def copy_art(source_path: Path, target_path: Path):
    # Load Source File & Extract Art
    source_audio = mutagen.File(source_path)
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
    target_audio = mutagen.File(target_path)
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
    print(f"\tCopied album cover art from {source_path.absolute()} to {target_path.absolute()}")


# converts music files to mp3
def transcode_to_mp3(input_file: Path, output_file: Path, bitrate='320k', audio_format=''):
    input_file_extension = input_file.suffix
    input_file_format = input_file_extension[1:]
    audio_format = "ogg" if input_file_extension == ".ogg" else audio_format
    if not input_file_format:
        print(f"\tCannot determine format for {input_file.absolute()}, skipping...")
        return 'unknown format'
    # try:
    # Load the audio file using the correct format
    sound = AudioSegment.from_file(input_file, format=input_file_format)

    # Export the audio to MP3 format with a specified bitrate
    sound.export(output_file, format="mp3", bitrate=bitrate)
    print(f"\tSuccessfully transcoded {input_file.absolute()} to {output_file.absolute()}")
    copy_all_tags(input_file, output_file)
    copy_art(input_file, output_file)
    return ''


# handles 
def process_playlist(
    playlist_file_path: Path, 
    base_path: Path,
    target_path: Path, 
    invalid_chars: list[str], 
    replacement_char: str, 
    strip_leading_track_numbers: bool,
    bitrate: str,
    overwrite_existing: bool,
    garmin_music_root_path: Path
):

    print(f"\nWorking on {playlist_file_path}:")
    # Read songs from specified playlist file
    playlist_file = TextFile(playlist_file_path)
    total = playlist_file.lines_remaining()
    
    if playlist_file.lines_remaining() == 0:
        print(f"No songs in {playlist_file_path}, aborting!")
        return
    else:
        print(f"Found {total} songs in {playlist_file_path}, starting...")
        
    # create output directory if it does not already exist;
    target_path.mkdir(parents=True, exist_ok=True)
    # create output playlist file
    playlist_file_name = playlist_file_path.stem
    output_playlist_file_path = target_path / f"{playlist_file_name}.m3u8"
    with open(output_playlist_file_path, "w", encoding="utf-8") as output_playlist_file:
        
        # interate through playlist: transcode, rename, and write each song to output dir
        count = 0
        while playlist_file.lines_remaining() > 0:
            count += 1
            song = urllib.parse.unquote(playlist_file.next_line())
            full_path_song = base_path / song
    
            # process each song
            if full_path_song.exists():
                # get the output path; make output folders where necessary
                # replace special chars in song filenames with underscores
                pattern = r'[^a-zA-Z0-9_ -]'
                cleaned_name = re.sub(pattern, replacement_char, full_path_song.stem)
                output_songname = f"{cleaned_name}.mp3"
                if strip_leading_track_numbers:
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
                output_path_song = target_path / output_songname
                
                c = str(count)
                if count <= 9 and total > 9:
                    c = '0' + c
                # transcode
                print(f"[{c}/{total}] Transcoding {full_path_song} to {bitrate} bps MP3")

                # check to see if target file already exists
                already_exists = True if output_path_song.exists() else False
                error = ""
                if already_exists:
                    print('\tDestination file already exists; skipping transcode...')
                else:
                    file_extension = full_path_song.suffix
                    copy_instead = False
                    if file_extension == 'mp3':
                        bitrate = get_mp3_bitrate(full_path_song)
                        try:
                            float(bitrate)
                        except:
                            pass
                        if float(bitrate) <= float(target_bitrate):
                            copy_instead = True

                    if copy_instead:
                        print('\tSource file is already at or under target transcoding bitrate (' + str(bitrate) + 'kbps), copying instead...')
                        shutil.copy2(full_path_song, output_path_song)
                    else:
                        error = transcode_to_mp3(full_path_song, output_path_song, bitrate=bitrate)
                
                # write to the playlist file if no transcoding errors
                if not error:
                    # get the path relative to the playlist file
                    garmin_path = full_path_song.parent / output_songname
                    output_playlist_file.write(f"{garmin_path.absolute()} \n")
            else:
                print(f'Error: specified playlist entry {full_path_song} does not exist!')


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
    ap.add_argument(
        '--overwrite_existing',
        action='store_true',
        default=False,
        help='overwrite existing files in the target directory'
    )
    options = ap.parse_args()
    base_path = Path(options.input_dir)
    target_path = Path(options.output_dir)
    invalid_chars = list(options.invalid_chars) if options.invalid_chars else []
    replacement_char: str = options.replacement_char
    strip_leading_track_numbers: bool = options.strip_leading_track_numbers
    garmin_music_root_path: Path = Path(options.garmin_music_root_path)
    
    # do some sanity checks on input options
    if not base_path.is_dir():
        print(f"Error: specified input folder {base_path} does not exist; aborting!")
        exit(-1)
    
    target_bitrate = options.bitrate.lower().replace('k', '')
    try:
        float(target_bitrate)
    except:
        # Probably better to raise an error.
        print(f"Error: specified bitrate {options.bitrate} is not valid; aborting!")
        exit(-1)
        
    if not options.bitrate.lower().endswith('k'):
        options.bitrate = options.bitrate + 'k'

    print("Input path: " + options.input_dir)
    print("Output path: " + options.output_dir)
    
    # collect playlist files in input directory
    m3u_files = list(base_path.glob("**/*.m3u"))
    m3u8_files = list(base_path.glob("**/*.m3u8"))
    playlist_files = m3u_files + m3u8_files
    
    # process each found playlist
    for playlist_file_path in playlist_files:
        process_playlist(
            playlist_file_path=playlist_file_path,
            base_path=base_path, 
            target_path=target_path, 
            invalid_chars=invalid_chars, 
            replacement_char=replacement_char, 
            strip_leading_track_numbers=strip_leading_track_numbers, 
            bitrate=options.bitrate,
            overwrite_existing=options.overwrite_existing, 
            garmin_music_root_path=garmin_music_root_path
        )

    print('\nDone!')