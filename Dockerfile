FROM deepakdotpro/transcoder-base:latest

# Set the working directory in the container to /app
WORKDIR /app

# Copy the local script file to the container at /app
COPY script.py /app

# Run script.py when the container launches
CMD ["python3", "-u", "/app/script.py"]