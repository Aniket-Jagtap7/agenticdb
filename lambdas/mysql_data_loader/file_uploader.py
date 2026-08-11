# Uploads ZIP file to S3 bucket

import boto3

s3 = boto3.client("s3")

try:
    s3.upload_file("lambda.zip", "aws-lambda-functions-bucket1", "lambda.zip")

except Exception as e:
    print(str(e))

