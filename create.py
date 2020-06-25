import datetime
import uuid
import json

from boto3.dynamodb.types import TypeSerializer

import libs.lib_db as db
import libs.lib_handler as handler

def main(event, context):

    # Load the json string into a dictionary
    body = json.loads(event.get('body'))

    # Prepare a dynamo db item.
    item = {
        'userId': {"S": event.get('requestContext').get('identity').get('cognitoIdentityId')},
        'noteId': {"S": str(uuid.uuid1())},
        'content' : {"S": body["content"]},
        'attachment': {"S": body["attachment"]},
        'createdAt': {"S": datetime.date.today().strftime("yyyy-mm-dd")}
    }

    # Add that field entry to the table
    response = db.client.put_item(
        TableName=db.USER_TABLE,
        Item=item
    )

    return handler.handle_response(item)