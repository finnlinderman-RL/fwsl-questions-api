import libs.lib_db as db
import libs.lib_handler as handler

def main(event, context):
    round_id = event.get('pathParameters').get('roundId')
    question_id = event.get('pathParameters').get('userId')

    db.client.delete_item(
        TableName=db.USER_TABLE,
        Key={
            'roundId': {"S": round_id},
            'questionId': {"S": question_id}
        }
    )

    return handler.handle_response({'success': True})


