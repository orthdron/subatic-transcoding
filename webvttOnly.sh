#!/bin/bash

# Set the input video file name
INPUT_FILE="$1"

# Set the output directory
OUTPUT_DIR="$2"
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
  local frame_width=180
  local frame_height=101
  local sprite_width=$((num_frames * frame_width))
  local sprite_height=$frame_height
  
  # Get the total duration of the video in seconds
  duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input_file")
  echo "Duration: $duration"

  frame_duration_sec=$(echo "scale=6; $duration / $num_frames" | bc)
  
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
    # echo "$start_time_formatted --> $end_time_formatted"
    echo "$start_time_formatted --> $end_time_formatted" >> "$webvtt_file"
    echo "sprite.jpg#xywh=$x,$y,$frame_width,$frame_height" >> "$webvtt_file" # Add coordinates and size to the cue settings line
    echo "" >> "$webvtt_file" # Add an empty line to separate captions
  done

  find "$output_dir" -name 'frame*.jpg' -exec rm {} \;
}


generate_sprite_webvtt_and_gif "$INPUT_FILE" "$OUTPUT_DIR"
