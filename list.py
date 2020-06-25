from boto3.dynamodb.types import TypeDeserializer

import libs.lib_db as db
import libs.lib_handler as handler

def main(event, context):
    user = event.get('requestContext').get('identity').get('cognitoIdentityId')
    # Get all field entry for a given user
    response = db.client.query(
        TableName=db.USER_TABLE,
        KeyConditionExpression="roundId = :roundId",
        ExpressionAttributeValues={
            ":roundId": {'S': user}
        }
    )
    if "Items" not in response:
        # If there are no objects, Items could be an empty list
        return handler.handle_response({'success': False})

    notes_list = [
        TypeDeserializer().deserialize({"M": item})
        for item in response["Items"]
    ]
    # Return to the user
    return handler.handle_response(notes_list)
