import json
from src.logging_config import logger
from src.config import load_config
from src.process import process_video

config = load_config()


def process_sqs_message(sqs_client, queue_url):
    try:
        response = sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20
        )
        messages = response.get("Messages", [])
        if not messages:
            logger.info("No messages in the queue. Waiting...")
            return

        message = messages[0]
        message_data = message.get("Body")
        if not message_data:
            logger.warning("Received empty message body")
            return

        logger.info(f"Received message: {message_data}")
        parsed_message = json.loads(message_data)
        records = parsed_message.get("Records", [])
        for record in records:
            event_name = record.get("eventName")
            if event_name == "ObjectCreated:Put":
                object_key = record["s3"]["object"]["key"]
                if object_key:
                    try:
                        process_video(object_key)
                        pass
                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
                        # Call send_webhook function here
                        # For example: send_webhook(object_key, "FAILED")
                else:
                    logger.warning(f"Invalid object key in message: {message_data}")

        # Delete the processed message from the queue
        sqs_client.delete_message(
            QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
        )
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
