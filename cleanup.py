import boto3
from botocore.client import Config

# Provided credentials
ACCESS_KEY = '6d85dc33e59153f1b1760fec4d3d113e'
SECRET_KEY = 'ec0a2971cd1bea507d51d367bae24e322c0201344cb52e8a6dcb9b156d97bb83'
BUCKET_NAME = 'subatic'
ENDPOINT_URL = 'https://1883359cec2736b7b8507acfe1ca21e5.r2.cloudflarestorage.com'
REGION_NAME = 'auto'

# Initialize S3 client with custom settings
s3 = boto3.client(
    's3',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    endpoint_url=ENDPOINT_URL,
    region_name=REGION_NAME,
    config=Config(signature_version='s3v4')
)

# List of folders and files to keep
folders_to_keep = [
    'v9i1ycc0lc', 'shb8avds9z', '6w5mckuhsv', '9cz5y7gj1r',
    'a1waathn7a', 'yiuw41e4gm', 'fzhhw4ik89', 'oqdtuufvxl',
    'r7b4cy6gma', '27lwx89kpm', 'hijdwq6q11', 'dr5p2ml52h',
    'c4z9xkpj3i', 'jv7rox5hdk', 'ven621m10d', 'dt9sqz5exp',
    'czcpkmf6xi', '9ppkw2qeqk', '8a8i53j5sy', '4e08816sca',
    '0ifx13tufk', 'video', 'logo.png'
]

# List objects in the bucket
response = s3.list_objects_v2(Bucket=BUCKET_NAME, Delimiter='/')

# Iterate over the folders
if 'CommonPrefixes' in response:
    for prefix in response['CommonPrefixes']:
        folder_name = prefix['Prefix'].rstrip('/')
        
        # If the folder is not in the keep list, delete it
        if folder_name not in folders_to_keep:
            print(f"Deleting folder: {folder_name}")
            
            # List all objects within the folder to delete
            objects_to_delete = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=folder_name + '/')
            
            # Delete all objects in the folder
            if 'Contents' in objects_to_delete:
                delete_keys = {'Objects': [{'Key': obj['Key']} for obj in objects_to_delete['Contents']]}
                s3.delete_objects(Bucket=BUCKET_NAME, Delete=delete_keys)
            
            # Optionally, you can delete the empty folder itself (S3 doesn't have folders per se, just keys)
            s3.delete_object(Bucket=BUCKET_NAME, Key=folder_name + '/')
else:
    print("No folders found in the bucket.")
