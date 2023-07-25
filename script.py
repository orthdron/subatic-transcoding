import os
import boto3
import runpod
import subprocess
from concurrent.futures import ThreadPoolExecutor


def handler(event):
    job_input = event["input"]
    file_name = job_input["file"]

    output_folder = "/tmp/upload"

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
    )
    s3_client.download_file(
        os.getenv("AWS_BUCKET_1"), file_name, f"/tmp/{file_name}.video"
    )

    # Invoke bash script here with input = filename and output = output folder
    bash_script = "/app/script.sh"

    final_output = output_folder + "/" + file_name

    subprocess.run([bash_script, f"/tmp/{file_name}.video", final_output], check=True)

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

    return "Processing complete"


def upload_to_s3(local_path, relative_path, s3_client):
    try:
        s3_client.upload_file(local_path, os.getenv("AWS_BUCKET_2"), relative_path)
        print(f"Uploaded {local_path} to S3")
    except Exception as e:
        print(f"Failed to upload {local_path}. Error: {str(e)}")


# input_json = """
# {
#     "input": {
#         "file": "T6s-rRGaT7"
#     }
# }
# """

# result = handler(json.loads(input_json))

runpod.serverless.start({"handler": handler})
