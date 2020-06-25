import libs.lib_db as db
import libs.lib_handler as handler

def main(event, context):
    round_id = event.get('pathParameters').get('roundId')
    question_id = event.get('pathParameters').get('questionId')
    response = db.client.get_item(
        TableName=db.USER_TABLE,
        Key={
            "roundId": {"S": round_id},
            "questionId": {"S": question_id}
        },

    )
    if "Item" not in response:
        return handler.handle_response({'success': False})

    return handler.handle_response(response["Item"])
