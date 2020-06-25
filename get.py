import libs.lib_db as db
import libs.lib_handler as handler

def main(event, context):
    user_id = event.get('requestContext').get('identity').get('cognitoIdentityId')
    note_id = event.get('pathParameters').get('id')
    response = db.client.get_item(
        TableName=db.USER_TABLE,
        Key={
            "userId": {"S": user_id},
            "noteId": {"S": note_id}
        },

    )
    if "Item" not in response:
        return handler.handle_response({'success': False})

    return handler.handle_response(response["Item"])