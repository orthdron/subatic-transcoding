import subprocess
import time
import os


def loop():
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Construct the full path to process.py
    process_path = os.path.join(script_dir, "process.py")

    # Path to the Python interpreter within the virtual environment
    venv_path = ".venv/bin/python3"

    # Check if the virtual environment's Python interpreter exists
    if not os.path.isfile(venv_path):
        print("Virtual environment not found. Using system Python.")
        venv_path = "python3"

    while True:
        try:
            # Run the process.py script using the determined Python interpreter
            subprocess.run([venv_path, process_path], check=True)
        except KeyboardInterrupt:
            print("Loop interrupted by user.")
            break
        except Exception as e:
            print(f"Error occurred: {e}")

        # Adjust the sleep time (in seconds) to control the frequency of script calls.
        time.sleep(1)
        print("Sleeping 1 Second")


if __name__ == "__main__":
    loop()
