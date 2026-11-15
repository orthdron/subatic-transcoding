<p align="center">
       <a href="https://subatic.com">
          <img src="https://github.com/orthdron/subatic/raw/main/docs/logo/combined/png/transparent.png"/>
      </a>
</p>


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
ENABLE_SQS=false
SQS_URL=YOUR_SQS_URL

# Download bucket configuration

RAWFILES_S3_ENDPOINT=http://localhost:9000
RAWFILES_S3_ACCESS_KEY_ID=YOUR_RAWFILES_S3_ACCESS_KEY_ID
RAWFILES_S3_SECRET_ACCESS_KEY=YOUR_RAWFILES_S3_SECRET_ACCESS_KEY
RAWFILES_S3_REGION=YOUR_RAWFILES_S3_REGION
RAWFILES_S3_BUCKET=YOUR_RAWFILES_BUCKET_NAME

# Upload bucket configuration: Can be same as download if public
PROCESSED_S3_ACCESS_KEY_ID=YOUR_PROCESSED_S3_ACCESS_KEY_ID
PROCESSED_S3_SECRET_ACCESS_KEY=YOUR_PROCESSED_S3_SECRET_ACCESS_KEY
PROCESSED_S3_REGION=YOUR_PROCESSED_S3_REGION
PROCESSED_S3_BUCKET=YOUR_PROCESSED_BUCKET_NAME
PROCESSED_S3_ENDPOINT=YOUR_PROCESSED_S3_ENDPOINT


# Webhook configuration
WEBHOOK_URL=http://localhost:3000/
WEBHOOK_TOKEN=YOUR_WEBHOOK_TOKEN
```

## What it produces

For each upload `uploads/<id>` in the raw bucket, the transcoder writes to `<id>/` in the processed bucket:

- `master.m3u8` plus one H.264/AAC HLS rendition per ladder rung that fits the source (360p up to 2160p, sized by the short side so portrait video keeps its resolution; sources below 360p get one native-size rendition). Segments are 6 s and cut at the same timestamps in every rendition; `BANDWIDTH` values are measured from the actual segments.
- `sprite.jpg` + `sprite.vtt` (seek-preview thumbnails) and `poster.jpg` (full-quality frame from the middle of the video).
- Video-card previews at the thumbnail size (up to 384x216): `short.webp`, an animated WebP of 10 frames shown 5 s each that loops at rest, and `long.mp4`, a muted H.264 clip of all 100 thumbnails at 0.5 s each for hover. Expect about 40-70 KB for `short.webp` and under 200 KB for `long.mp4`, whose bitrate cap keeps it under about 250 KB whatever the content. Videos transcoded before these replaced `short.gif`/`long.gif` only have the GIFs.

The raw upload is deleted only after the web app has accepted the `DONE` status, so a failed status update never loses the source.

## Development

The tests use only the standard library. The pipeline tests also need `ffmpeg` and `ffprobe` on the `PATH` (they are skipped otherwise):

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -t .
```

More detailed documentation will be available soon. For any bugs, please report them using GitHub Issues.

If you have questions, feel free to reach out:

- [Contact on X](https://x.com/orthdron)
