# First stage: Build ffmpeg
FROM linuxserver/ffmpeg:latest AS ffmpeg

# Second stage: Python application
FROM python:3.12-slim

# Copy ffmpeg binaries from the first stage
COPY --from=ffmpeg /usr/local/bin/ffmpeg /usr/local/bin/
COPY --from=ffmpeg /usr/local/bin/ffprobe /usr/local/bin/

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python scripts into the container
COPY main.py .
COPY src/ ./src/

# Run main.py
CMD ["python", "main.py"]
