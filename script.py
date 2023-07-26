import os
import boto3
import subprocess
from concurrent.futures import ThreadPoolExecutor
import time
from dotenv import load_dotenv
import json
import shutil


def main():
    load_dotenv()
    sqs_session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
        region_name=os.getenv("AWS_REGION"),
    )

    sqs_client = sqs_session.client("sqs")

    queue_url = os.getenv("AWS_SQS_URL")

    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20
            )
            messages = response.get("Messages", [])
            if not messages:
                print("No messages in the queue. Waiting...")
                continue

            message = messages[0]

            message_data = message.get("Body")
            if message_data:
                print("Received this message")
                print(message_data)
                try:
                    parsed_message = json.loads(message_data)
                    records = parsed_message.get("Records", [])
                    for record in records:
                        event_name = record.get("eventName")
                        if event_name == "ObjectCreated:Put":
                            object_key = record["s3"]["object"]["key"]
                            if object_key:
                                try:
                                    handler(object_key)
                                except Exception as e:
                                    print("Error processing message:", str(e))
                            else:
                                print(message_data)
                except Exception as e:
                    print("Error parsing message:", str(e))

            print("Sleeping for 5 seconds...")
            time.sleep(5)

            # Delete the processed message from the queue
            sqs_client.delete_message(
                QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
            )

        except Exception as e:
            print("Error:", str(e))
            continue


def handler(file_name):
    output_folder = "./upload"

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
    )
    s3_client.download_file(
        os.getenv("AWS_BUCKET_1"), file_name, f"./{file_name}.video"
    )

    # Invoke bash script here with input = filename and output = output folder
    bash_script = "./script.sh"

    final_output = output_folder + "/" + file_name

    subprocess.run([bash_script, f"./{file_name}.video", final_output], check=True)

    # Upload the output folder to a different s3 compatible storage
    s3_client_2 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_2"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_2"),
        endpoint_url=os.getenv("AWS_ENDPOINT_2"),
    )

    # Use ThreadPoolExecutor for multi-threaded file upload
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for root, dirs, files in os.walk(output_folder):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, output_folder)
                future = executor.submit(
                    upload_to_s3, local_path, relative_path, s3_client_2
                )
                futures.append(future)

        # Wait for all upload tasks to complete
        for future in futures:
            future.result()
    os.remove(f"./{file_name}.video")
    shutil.rmtree(output_folder)
    return "Processing complete"


def upload_to_s3(local_path, relative_path, s3_client):
    try:
        s3_client.upload_file(local_path, os.getenv("AWS_BUCKET_2"), relative_path)
        print(f"Uploaded {local_path} to S3")
    except Exception as e:
        print(f"Failed to upload {local_path}. Error: {str(e)}")


if __name__ == "__main__":
    main()
