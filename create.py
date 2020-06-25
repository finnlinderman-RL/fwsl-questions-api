import datetime
import uuid
import json

from boto3.dynamodb.types import TypeSerializer

import libs.lib_db as db
import libs.lib_handler as handler

def main(event, context):

    # Load the json string into a dictionary
    body = json.loads(event.get('body'))

    # hard coding round if for now, need to eventually have this as a parameter
    roundId = "420"

    # Prepare a dynamo db item.
    item = {
        #'userId': {"S": event.get('requestContext').get('identity').get('cognitoIdentityId')},
        'roundId': {"S": body["roundId"]},
        'questionId': {"S": str(uuid.uuid1())},
        'question' : {"S": body["content"]},
        #'attachment': {"S": body["attachment"]},
        #'createdAt': {"S": datetime.date.today().strftime("yyyy-mm-dd")}
    }

    # Add that field entry to the table
    response = db.client.put_item(
        TableName=db.USER_TABLE,
        Item=item
    )

    return handler.handle_response(item)
