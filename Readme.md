![Subatic](https://github.com/orthdron/subatic/raw/main/public/logo.webp)

## Subatic Transcoder

Subatic Transcoder is a tool designed for media transcoding. It offers flexibility in deployment, allowing you to use either a Docker container or Ansible to deploy it on your servers. This README provides the necessary information to get started with both methods.

## Deployment Options

### 1. Docker Container

To deploy Subatic Transcoder using Docker, follow these steps:

1. Clone the repository:

   ```sh
   git clone https://github.com/orthdron/subatic-transcoder.git
   cd subatic-transcoder
   ```

2. Build the Docker image:

   ```sh
   docker build -t subatic-transcoder .
   ```

3. Run the Docker container:
   ```sh
   docker run -d --env-file .env subatic-transcoder
   ```

### 2. Ansible Deployment

To deploy Subatic Transcoder using Ansible, follow these steps:

1. Clone the repository:

   ```sh
   git clone https://github.com/orthdron/subatic-transcoder.git
   cd subatic-transcoder/ansible
   ```

2. Update the `hosts` file with your server details.

3. Run the Ansible playbook:
   ```sh
   ansible-playbook -i hosts playbook.yml
   ```

## Configuration

A sample environment file is provided below. Update it with your specific details and save it as `.env` in the root directory of your project.

```plaintext
# Enable or disable SQS
SQS_ENABLED=false
SQS_URL=YOUR_SQS_URL

# Download bucket configuration
DOWNLOAD_S3_ENDPOINT=http://localhost:9000
DOWNLOAD_S3_ACCESS_KEY_ID=YOUR_DOWNLOAD_S3_ACCESS_KEY_ID
DOWNLOAD_S3_SECRET_ACCESS_KEY=YOUR_DOWNLOAD_S3_SECRET_ACCESS_KEY
DOWNLOAD_S3_REGION=YOUR_DOWNLOAD_S3_REGION
DOWNLOAD_S3_BUCKET=YOUR_DOWNLOAD_BUCKET_NAME

# Upload bucket configuration: Can be same as download if public
UPLOAD_S3_ACCESS_KEY_ID=YOUR_UPLOAD_S3_ACCESS_KEY_ID
UPLOAD_S3_SECRET_ACCESS_KEY=YOUR_UPLOAD_S3_SECRET_ACCESS_KEY
UPLOAD_S3_REGION=YOUR_UPLOAD_S3_REGION
UPLOAD_S3_BUCKET=YOUR_UPLOAD_BUCKET_NAME
UPLOAD_S3_ENDPOINT=YOUR_UPLOAD_S3_ENDPOINT

# Webhook configuration
WEBHOOK_URL=http://localhost:3000/
WEBHOOK_TOKEN=YOUR_WEBHOOK_TOKEN
```

More detailed documentation will be available soon. For any bugs, please report them using GitHub Issues.

If you have questions, feel free to reach out:

- [Contact on X](https://x.com/orthdron)
