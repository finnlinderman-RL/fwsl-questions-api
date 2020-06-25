import json
import libs.lib_db as db
import libs.lib_handler as handler

def main(event, context):
    body = json.loads(event.get('body'))
    user_id = event.get('requestContext').get('identity').get('cognitoIdentityId')
    note_id = event.get('pathParameters').get('id')

    response = db.client.update_item(
        TableName=db.USER_TABLE,
        Key={
            'userId': {'S': user_id},
            'noteId': {"S": note_id}
        },
        UpdateExpression="SET content = :content, attachment = :attachment",
        ExpressionAttributeValues={
          ":attachment": {"S": body["attachment"]},
          ":content": {"S": body["content"]},
        },
        ReturnValues="ALL_NEW"
    )
    return handler.handle_response({'success': True})


