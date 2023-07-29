import subprocess
import time


def loop():
    while True:
        try:
            subprocess.run(["python3", "process.py"])
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
