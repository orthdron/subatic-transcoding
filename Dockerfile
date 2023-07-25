FROM deepakdotpro/transcoder-base:latest

# Set the working directory in the container to /app
WORKDIR /app

# Copy the local script file to the container at /app
COPY script.sh /app
COPY script.py /app

# Make script.sh executable
RUN chmod +x /app/script.sh

# Run script.py when the container launches
CMD ["python3", "-u", "/app/script.py"]