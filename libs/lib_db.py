import os
import boto3

USER_TABLE = os.environ['tableName']

LOCAL_DB = True

client = None

if LOCAL_DB:
    sts_client = boto3.client("sts")
    # Call the assume_role method of the STSConnection object and pass the role
    # ARN and a role session name.
    assumed_role_object = sts_client.assume_role(
        RoleArn="arn:aws:iam::463038042756:role/Developer",
        RoleSessionName="AssumeRoleSession1",
    )
    # From the response that contains the assumed role, get the temporary
    # credentials that can be used to make subsequent API calls
    credentials = assumed_role_object["Credentials"]

    client = boto3.client(
        "dynamodb",
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )
else:
    client = boto3.client('dynamodb')

