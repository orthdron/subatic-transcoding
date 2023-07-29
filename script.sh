#!/bin/bash

# Set the input video file name
INPUT_FILE="$1"

# Set the output directory
OUTPUT_DIR="$2"

# Define the resolutions supported by YouTube, including 4K and 8K
# RESOLUTIONS=("854x480" "1280x720" "1920x1080" "2560x1440" "3840x2160" "7680x4320")
RESOLUTIONS=("854" "1280" "1920" "2560" "3840" "7680")

# Define the bit rates for each resolution
# BITRATES=("1200k" "2500k" "4500k" "8000k" "12000k" "24000k")
BITRATES=("1200k" "2500k" "4500k" "8000k" "12000k")

# Define the BANDWIDTH for each resolution
# BANDWIDTHS=("1200000" "2500000" "4500000" "8000000" "12000000" "24000000")
BANDWIDTHS=("1200000" "2500000" "4500000" "8000000" "12000000")

ffmpeg -i "$input_file" -vf "scale=w=min(iw\,3840):h=min(ih\,2160),fps=60" \
  -c:v libx264 -preset medium -crf 23 \
  -c:a aac -b:a 128k -ar 48000 \
  "pre.mp4"

# Function to convert video to HLS format for a given resolution
function convert_to_hls {
  local input_file="$1"
  local output_dir="$2"
  local resolution="$3"

  # Create output directory for the resolution
  mkdir -p "$output_dir"

  # Set the CRF value for variable bitrate
  crf_value="23"

  # Convert video to HLS format for the resolution
  ffmpeg -i "$input_file" -vf "scale=$resolution" -c:v libx264 -preset veryfast -crf "$crf_value" -c:a aac -b:a 256k -ar 48000 \
  -f hls -hls_time 6 -hls_playlist_type vod -hls_segment_filename "$output_dir/%03d.ts" "$output_dir/stream.m3u8"


  echo "Video conversion completed for resolution: $resolution"
}

# Get the maximum resolution of the input file
MAX_RESOLUTION=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$INPUT_FILE")

# Create an array to store the variant streams
VARIANT_STREAMS=()

# Loop through the resolutions and convert the video to HLS format
for resolution in "${RESOLUTIONS[@]}"
do
  # Get the width and height of the current resolution
  width=${resolution%x*}
  height=${resolution#*x}

  # Get the width and height of the maximum resolution
  max_width=${MAX_RESOLUTION%x*}
  max_height=${MAX_RESOLUTION#*x}

  # Skip the resolution if it is greater than the maximum resolution
  if (( width > max_width || height > max_height )); then
    continue
  fi

  # Create output directory path for the resolution
  output_dir="$OUTPUT_DIR/$resolution"

  # Convert video to HLS format for the resolution
  convert_to_hls "$INPUT_FILE" "$output_dir" "$resolution"

  # Add variant stream to the array
  VARIANT_STREAMS+=("$resolution/stream.m3u8")
done

# Generate the master playlist file
MASTER_FILE="$OUTPUT_DIR/master.m3u8"
echo "#EXTM3U" > "$MASTER_FILE"

# Loop through the resolutions and variant streams
for ((i = 0; i < ${#RESOLUTIONS[@]}; i++)); do
  # Get the resolution and variant stream
  resolution=${RESOLUTIONS[i]}
  variant_stream=${VARIANT_STREAMS[i]}

  # Get the width and height of the current resolution
  width=${resolution%x*}
  height=${resolution#*x}

  # Get the width and height of the maximum resolution
  max_width=${MAX_RESOLUTION%x*}
  max_height=${MAX_RESOLUTION#*x}

  # Skip writing variant stream if the resolution is greater than the maximum resolution
  if (( width > max_width || height > max_height )); then
    continue
  fi

  # Get the BANDWIDTH for the resolution
  bandwidth=${BANDWIDTHS[i]}

  # Write the EXT-X-STREAM-INF tag to the master playlist file
  echo "#EXT-X-STREAM-INF:BANDWIDTH=$bandwidth,RESOLUTION=$resolution" >> "$MASTER_FILE"
  echo "$variant_stream" >> "$MASTER_FILE"
done


echo "Video conversion for all resolutions completed."
echo "Master playlist generated: $MASTER_FILE"

seconds_to_hhmmss() {
    local input=$1

    local seconds=$(printf "%.0f" $input)
    local hours=$((seconds / 3600))
    local minutes=$(( (seconds % 3600) / 60 ))
    local seconds=$((seconds % 60))

    printf "%02d:%02d:%02d" $hours $minutes $seconds
}


function generate_sprite_webvtt_and_gif {
  local input_file="$1"
  local output_dir="$2"

  local num_frames=100
  local frame_width=384
  local frame_height=216
  local sprite_width=$((num_frames * frame_width))
  local sprite_height=$frame_height
  
  # Get the total duration of the video in seconds
  duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input_file")
  echo "Duration: $duration"
  
  # Calculate the duration of each frame in seconds
  fps=$(echo "scale=5; $num_frames / $duration" | bc)
  frame_duration_sec=$(echo "scale=6; $duration / $num_frames" | bc)
  
  # Extract individual frames and save them as images with the specified resolution
  #ffmpeg -i "$input_file" -vf "fps=$fps,scale=$frame_width:$frame_height" -q:v 2 "$output_dir/frame%03d.jpg"
  ffmpeg -i "$input_file" -vf "fps=$fps,scale=$frame_width:$frame_height" "$output_dir/frame%03d.jpg"

  # Concatenate frames into a grid (10x10) to create a sprite image
  montage "$output_dir/frame*.jpg" -tile 10x10 -geometry +0+0 -background none "$output_dir/sprite_original.jpg"
  convert "$output_dir/sprite_original.jpg" -quality 80 "$output_dir/sprite.jpg"
  rm "$output_dir/sprite_original.jpg"
  
  # Create the WebVTT file with the appropriate content
  local webvtt_file="$output_dir/sprite.vtt"
  echo "WEBVTT" > "$webvtt_file"
  echo "" >> "$webvtt_file"

  # Loop through the number of frames to add captions with timestamps
  for ((i = 0; i < $num_frames; i++)); do
    start_time=$(echo "$i * $frame_duration_sec" | bc)
    end_time=$(echo "($i + 1) * $frame_duration_sec" | bc)

    start_time_formatted=$(seconds_to_hhmmss $start_time)
    end_time_formatted=$(seconds_to_hhmmss $end_time)


    # Calculate the frame's position in the sprite
    row=$(($i / 10))
    col=$(($i % 10))

    # Calculate the frame's coordinates in the sprite
    x=$(($col * $frame_width))
    y=$(($row * $frame_height))

    # Write the caption entry to the WebVTT file
    echo "$start_time_formatted --> $end_time_formatted" >> "$webvtt_file"
    echo "sprite.jpg#xywh=$x,$y,$frame_width,$frame_height" >> "$webvtt_file" # Add coordinates and size to the cue settings line
    echo "" >> "$webvtt_file" # Add an empty line to separate captions
  done

  # Create an empty string to store the filenames
  frame_files=""

  # Loop through the frame files
  for ((i = 1; i < $num_frames; i+=10)); do
    # Append the filename to the string, padded with zeros
    frame_files+="$output_dir/frame$(printf "%03d" $i).jpg "
  done

  # Create the GIF from the selected frame files using ImageMagick
  convert -delay 10x10 -loop 0 $frame_files "$output_dir/short.gif"

  # Create the GIF from the individual frame files using ImageMagick
  convert -delay 1x10 -loop 0 "$output_dir/frame*.jpg" "$output_dir/long.gif"

  find "$output_dir" -name 'frame*.jpg' -exec rm {} \;
}


generate_sprite_webvtt_and_gif "$INPUT_FILE" "$OUTPUT_DIR"
