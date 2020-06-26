import boto3
from boto3.dynamodb.conditions import Key
import logging
import json
import random
import uuid

logger = logging.getLogger("websocket_handler_logger")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource("dynamodb")


def _get_response(status_code, body):
    if not isinstance(body, str):
        body = json.dumps(body)
    ret = {"statusCode": status_code, "body": body}
    logger.info(ret)
    return ret


def _get_body(event):
    try:
        return json.loads(event.get("body", ""))
    except:
        logger.debug("event body could not be JSON decoded.")
        return {}


def _get_user(event):
    user_table = dynamodb.Table("fwsl-connections")

    # Get current user's username and roundID
    user = user_table.get_item(Key={'ConnectionID': event["requestContext"]["connectionId"]},
                               ProjectionExpression="roundID, username")

    return user["Item"]["roundID"], user["Item"]["username"]


def _send_to_connection(connection_id, data, event):
    gatewayapi = boto3.client("apigatewaymanagementapi",
                              endpoint_url="https://" + event["requestContext"]["domainName"] +
                                           "/" + event["requestContext"]["stage"])
    try:
        return gatewayapi.post_to_connection(ConnectionId=connection_id,
                                             Data=json.dumps(data).encode('utf-8'))
    except gatewayapi.exceptions.GoneException:
        logger.debug("connection no longer exists, deleting")
        table = dynamodb.Table("fwsl-connections")
        table.delete_item(Key={"ConnectionID": connection_id})


def connection_manager(event, context):
    """
    Handles connecting and disconnecting for the Websocket.
    """
    connectionID = event["requestContext"].get("connectionId")

    if event["requestContext"]["eventType"] == "CONNECT":
        logger.info("Connect requested")

        # Add connectionID to the database
        table = dynamodb.Table("fwsl-connections")
        table.put_item(Item={"ConnectionID": connectionID})
        return _get_response(200, "Connect successful.")

    elif event["requestContext"]["eventType"] == "DISCONNECT":
        logger.info("Disconnect requested")

        # Remove the connectionID from the database
        table = dynamodb.Table("fwsl-connections")
        table.delete_item(Key={"ConnectionID": connectionID})
        return _get_response(200, "Disconnect successful.")

    else:
        logger.error("Connection manager received unrecognized eventType '{}'")
        return _get_response(500, "Unrecognized eventType.")


def store_question(event, context):
    """
    Recieve a question and store it to the DynamoDB
    """
    logger.info("Creating a new question")
    round_id, username = _get_user(event)
    body = _get_body(event)

    # TODO fix this to use an external table to keep track of the # of question for each round, instead of uuid
    #   also fix the return type
    question_table = dynamodb.Table("fwsl-questions")
    question_table.put_item(Item={"roundId": round_id,
                                  "questionId": str(uuid.uuid1()),
                                  "question": body["question"]})
    return _get_response(200, "Update successful")


def update_user(event, context):
    """
    Sets the user info for that connection
    """

    body = _get_body(event)

    logger.info("setting user info")
    connection_id = event["requestContext"].get("connectionId")
    table = dynamodb.Table("fwsl-connections")
    response = table.update_item(
        Key={'ConnectionID': connection_id},
        UpdateExpression="set roundID=:r, username=:u",
        ExpressionAttributeValues={
            ':r': body["roundId"],
            ':u': body["username"]
        },
        ReturnValues="UPDATED_NEW"
    )
    logger.debug(response)
    return _get_response(200, response)


def set_answerer(event, context):
    logger.info("Setting answerer for room")
    logger.info(event)
    round_id, username = _get_user(event)
    body = _get_body(event)

    for attr in ["answerer"]:
        if attr not in body:
            logger.debug(f"Failed: '{attr}' not in message dict.")
            return _get_response(400, f"'{attr}' not in message dict")

    user_table = dynamodb.Table("fwsl-connections")
    # Get all current connections in room
    all_users = user_table.scan(ProjectionExpression="ConnectionID, username",
                                FilterExpression=Key('roundID').eq(round_id))
    items = all_users.get("Items", [])
    # get connectionIDs for all users, except next answerer
    users_except_answerer = \
        [x["ConnectionID"] for x in items if "ConnectionID" in x and x.get("username") != body["answerer"]]

    # Send the "whose next" data to all connections in the room, except next answerer
    message = {"type": "nextAnswerer", "username": username, "answerer": body["answerer"]}
    logger.debug(f"Sending {message} to {users_except_answerer}")
    for connectionID in users_except_answerer:
        _send_to_connection(connectionID, message, event)

    # TODO: see if there is a way to use the db to pick 5 random, so that we dont have to read every single question
    # query the db, select 5 random questions to use
    question_table = dynamodb.Table("fwsl-questions")
    question_items = question_table.scan(ProjectionExpression="questionId",
                                         FilterExpression=Key('roundId').eq(round_id))
    questions = [x['question'] for x in question_items.get("Items", []) if 'question' in x]
    logger.debug(f"questions: {questions}")
    random_questions = random.sample(questions, 5) if len(questions) > 5 else questions
    logger.debug(f"randomized questions: {random_questions}")
    answerer_id = [x["ConnectionID"] for x in items if "ConnectionID" in x and x.get("username") == body["answerer"]][0]
    _send_to_connection(answerer_id, {"type": "pickQuestion", "question_ids": random_questions}, event)

    return _get_response(200, "Message sent to all connections.")


def send_question_to_room(event, context):
    logger.info("Publishing question to room.")
    round_id, username = _get_user(event)
    body = _get_body(event)

    for attr in ["questionID"]:
        if attr not in body:
            logger.debug(f"Failed: '{attr}' not in message dict.")
            return _get_response(400, f"'{attr}' not in message dict")

    # Get all current connections in room
    user_table = dynamodb.Table("fwsl-connections")
    all_users = user_table.scan(ProjectionExpression="ConnectionID",
                                FilterExpression=Key('roundID').eq(round_id))
    items = all_users.get("Items", [])
    connections = [x["ConnectionID"] for x in items if "ConnectionID" in x]

    question_table = dynamodb.Table("fwsl-questions")
    question_item = question_table.delete_item(Key={'roundId': round_id, 'questionId': body["questionID"]},
                                               ReturnValues="ALL_OLD")
    question = question_item["Attributes"]["question"]

    # Send the question data to all connections in the room
    message = {"type": "question", "username": username, "question": question}
    logger.debug(f"Sending {message} to {connections}")
    for connectionID in connections:
        _send_to_connection(connectionID, message, event)

    return _get_response(200, "Message sent to all connections.")


def send_next_answerers(event, context):
    logger.info("Sending potential next answerers")
    logger.debug(context)
    round_id, username = _get_user(event)
    body = _get_body(event)

    user_table = dynamodb.Table("fwsl-connections")
    # Get all users who haven't answered yet
    unanswered_users_item = user_table.scan(ProjectionExpression="username",
                                            FilterExpression=Key('roundID').eq(round_id) & Key('hasAnswered').eq(False))
    items = unanswered_users_item.get("Items", [])
    unanswered_users = [x['username'] for x in items if 'username' in x]

    _send_to_connection(event["requestContext"]["connectionId"],
                        {"type": "pickAnswerer", "options": unanswered_users},
                        event)

    return _get_response(200, "Message sent to picker.")


def default_message(event, context):
    """
    Send back error when unrecognized WebSocket action is received.
    """
    logger.info("Unrecognized WebSocket action received.")
    return _get_response(400, "Unrecognized WebSocket action.")
