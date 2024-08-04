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
# AWS Configuration
AWS_ACCESS_KEY_ID_1=             # Your AWS access key for transcoding
AWS_SECRET_ACCESS_KEY_1=         # Your AWS secret key for transcoding
AWS_BUCKET_1=                    # The S3 bucket used for transcoding
AWS_SQS_URL=                     # URL of the SQS queue for transcoding
AWS_REGION=                      # AWS region for transcoding resources

# Cloudflare Configuration
AWS_ACCESS_KEY_ID_2=             # Your Cloudflare access key
AWS_SECRET_ACCESS_KEY_2=         # Your Cloudflare secret key
AWS_BUCKET_2=                    # The R2 bucket used for final uploads
AWS_ENDPOINT_2=                  # Endpoint for accessing the R2 bucket

# Webhook Configuration
WEBHOOK_URL=                     # URL for webhook notifications (where Subatic is deployed)
WEBHOOK_TOKEN=                   # Random token for webhook notifications, shared between this and transcoder
```

More detailed documentation will be available soon. For any bugs, please report them using GitHub Issues.

If you have questions, feel free to reach out:

- [Contact on X](https://x.com/orthdron)
