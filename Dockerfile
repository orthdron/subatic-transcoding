FROM nvidia/cuda:11.2.2-base-ubuntu20.04

# Install FFmpeg and Python
RUN apt-get update && \
    apt-get install -y ffmpeg python3.9 python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container to /app
WORKDIR /app

# Copy the local requirements.txt file to the container at /app
COPY requirements.txt /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the local script file to the container at /app
COPY script.py /app

# Run script.py when the container launches
CMD ["python3", "-u", "/app/script.py"]
