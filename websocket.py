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
                               ProjectionExpression="RoundID, Username")

    return user["Item"]["RoundID"], user["Item"]["Username"]


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
        round_id, _ = _get_user(event)

        # subtract 1 to NumUsers in games table for this round
        games_table = dynamodb.Table("fwsl-games")
        cur_game = games_table.update_item(
            Key={"RoundID": round_id},
            UpdateExpression="SET NumUsers = NumUsers - :inc",
            ExpressionAttributeValues={':inc': 1},
            ReturnValues="ALL_NEW"
        )

        # remove lobby & trailing questions , if lobby is empty
        if cur_game["Attributes"]["NumUsers"] == 0:
            games_table.delete_item(Key={"RoundID": round_id})
            questions_table = dynamodb.Table("fwsl-questions")
            orphaned_questions = questions_table.scan(ProjectionExpression="QuestionID",
                                                      FilterExpression=Key('RoundID').eq(round_id))
            for question in orphaned_questions.get("Items", []):
                logger.debug(f"deleting question: {question['QuestionID']}")
                questions_table.delete_item(Key={"RoundID": round_id,
                                                 "QuestionID": question["QuestionID"]})

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

    games_table = dynamodb.Table("fwsl-games")
    updated_game = games_table.update_item(
        Key={"RoundID": round_id},
        UpdateExpression="SET NumQs = if_not_exists(NumQs, :start) + :inc",
        ExpressionAttributeValues={
            ':inc': 1,
            ':start': 0},
        ReturnValues="ALL_NEW"
    )

    question_table = dynamodb.Table("fwsl-questions")
    question_table.put_item(Item={"RoundID": round_id,
                                  "QuestionID": str(uuid.uuid1()),
                                  "Question": body["question"]})

    # broadcast that a new question has been added
    users_table = dynamodb.Table("fwsl-connections")
    all_users = users_table.scan(ProjectionExpression="ConnectionID",
                                 FilterExpression=Key('RoundID').eq(round_id))
    items = all_users.get("Items", [])
    users_ids = [x["ConnectionID"] for x in items if "ConnectionID" in x]
    message = {"type": "newQuestion",
               "question": body["question"],
               "numQuestions": f'{updated_game["Attributes"]["NumQs"]}',
               "numPlayers": f'{updated_game["Attributes"]["NumUsers"]}'}
    for connectionID in users_ids:
        _send_to_connection(connectionID, message, event)

    return _get_response(200, "Update successful")


def end_round(event, context):
    round_id, _ = _get_user(event)

    # broadcast that the round is over
    users_table = dynamodb.Table("fwsl-connections")
    all_users = users_table.scan(ProjectionExpression="ConnectionID",
                                 FilterExpression=Key('RoundID').eq(round_id))
    items = all_users.get("Items", [])
    users_ids = [x["ConnectionID"] for x in items if "ConnectionID" in x]
    for connection_id in users_ids:
        _send_to_connection(connection_id, {"type": "roundEnd"}, event)
        # reset the user's "HasAnswered" field to false, so they can play again
        users_table.update_item(Key={"ConnectionID": connection_id},
                                UpdateExpression="set HasAnswered = :h",
                                ExpressionAttributeValues={":h": False})

    return _get_response(200, "Round Ended")


def update_user(event, context):
    """
    Sets the user info for that connection
    """
    body = _get_body(event)
    round_id = body["roundID"]
    username = body["username"]

    logger.info("setting user info")
    connection_id = event["requestContext"].get("connectionId")
    table = dynamodb.Table("fwsl-connections")
    response = table.update_item(
        Key={'ConnectionID': connection_id},
        UpdateExpression="set RoundID=:r, Username=:u, HasAnswered=:h",
        ExpressionAttributeValues={
            ':r': round_id,
            ':u': username,
            ':h': False
        },
        ReturnValues="UPDATED_NEW"
    )

    # add 1 to NumUsers in games table for this round
    games_table = dynamodb.Table("fwsl-games")
    games_table.update_item(
        Key={"RoundID": round_id},
        UpdateExpression="SET NumUsers = if_not_exists(NumUsers, :start) + :inc, NumQs = if_not_exists(NumQs, :start)",
        ExpressionAttributeValues={
            ':inc': 1,
            ':start': 0}
    )

    # notify the room that a player has joined
    # Get all current connections in room
    all_users = table.scan(ProjectionExpression="ConnectionID, Username",
                           FilterExpression=Key('RoundID').eq(round_id))
    items = all_users.get("Items", [])
    # get connectionIDs and Usernames for all users
    users_ids = [x["ConnectionID"] for x in items if "ConnectionID" in x]
    users_unames = [x["Username"] for x in items if "Username" in x]

    # Broadcast lobby info to whole round
    message = {"type": "newPlayer", "users": users_unames}
    for connectionID in users_ids:
        _send_to_connection(connectionID, message, event)

    logger.debug(response)
    return _get_response(200, response)


def start_game(event, context):
    """
    start game if everyone has submitted a question
    """
    round_id, username = _get_user(event)
    connection_id = event["requestContext"].get("connectionId")
    logger.info(f"Attempting to start game: {round_id}")

    games_table = dynamodb.Table("fwsl-games")
    game = games_table.get_item(Key={"RoundID": round_id},
                                ProjectionExpression="NumUsers, NumQs")
    if game["Item"]["NumUsers"] == game["Item"]["NumQs"]:
        logger.info("ready to start game")
        # start the game
        users_table = dynamodb.Table("fwsl-connections")
        user_items = users_table.scan(ProjectionExpression="Username",
                                      FilterExpression=Key('RoundID').eq(round_id))
        users = [x['Username'] for x in user_items.get("Items", []) if 'Username' in x]
        logger.debug(f"users: {users}")
        random_user = random.choice(users)
        logger.debug(f"randomized user: {random_user}")
        send_answerer_to_room(round_id, "TRVY", random_user, event)
    else:
        # waiting for more questions, send error msg
        question_mismatch = game["Item"]["NumUsers"] - game["Item"]["NumQs"]
        _send_to_connection(connection_id, {"type": "startError", "waitingFor": f"{question_mismatch}"}, event)

    return _get_response(200, "start request received")


def set_answerer(event, context):
    logger.info("Setting answerer for room")
    logger.info(event)
    round_id, username = _get_user(event)
    body = _get_body(event)

    for attr in ["answerer"]:
        if attr not in body:
            logger.debug(f"Failed: '{attr}' not in message dict.")
            return _get_response(400, f"'{attr}' not in message dict")

    return send_answerer_to_room(round_id, username, body["answerer"], event)


def send_answerer_to_room(round_id, username, answerer, event):
    user_table = dynamodb.Table("fwsl-connections")
    # Get all current connections in room
    all_users = user_table.scan(ProjectionExpression="ConnectionID, Username",
                                FilterExpression=Key('RoundID').eq(round_id))
    items = all_users.get("Items", [])
    # get connectionIDs for all users, except next answerer
    users_except_answerer = \
        [x["ConnectionID"] for x in items if "ConnectionID" in x and x.get("Username") != answerer]

    # Send the "whose next" data to all connections in the room, except next answerer
    message = {"type": "nextAnswerer", "username": username, "answerer": answerer}
    logger.debug(f"Sending {message} to {users_except_answerer}")
    for connectionID in users_except_answerer:
        _send_to_connection(connectionID, message, event)

    # TODO: see if there is a way to use the db to pick 5 random, so that we dont have to read every single question
    # query the db, select 5 random questions to use
    question_table = dynamodb.Table("fwsl-questions")
    question_items = question_table.scan(ProjectionExpression="QuestionID",
                                         FilterExpression=Key('RoundID').eq(round_id))
    questions = [x['QuestionID'] for x in question_items.get("Items", []) if 'QuestionID' in x]
    logger.debug(f"questions: {questions}")
    random_questions = random.sample(questions, 5) if len(questions) > 5 else questions
    logger.debug(f"randomized questions: {random_questions}")
    answerer_id = [x["ConnectionID"] for x in items if "ConnectionID" in x and x.get("Username") == answerer][0]
    _send_to_connection(answerer_id, {"type": "pickQuestion", "questionIDs": random_questions}, event)

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
                                FilterExpression=Key('RoundID').eq(round_id))
    items = all_users.get("Items", [])
    connections = [x["ConnectionID"] for x in items if "ConnectionID" in x]

    # delete question and send to the room
    question_table = dynamodb.Table("fwsl-questions")
    question_item = question_table.delete_item(Key={'RoundID': round_id, 'QuestionID': body["questionID"]},
                                               ReturnValues="ALL_OLD")
    question = question_item["Attributes"]["Question"]

    # decrement NumQuestions in game
    games_table = dynamodb.Table("fwsl-games")
    updated_game = games_table.update_item(
        Key={"RoundID": round_id},
        UpdateExpression="SET NumQs = NumQs - :inc",
        ExpressionAttributeValues={':inc': 1},
        ReturnValues="UPDATED_NEW"
    )

    # mark user as having answered
    user_table.update_item(Key={"ConnectionID": event["requestContext"]["connectionId"]},
                           UpdateExpression="SET HasAnswered = :h",
                           ExpressionAttributeValues={":h": True})

    if updated_game["Attributes"]["NumQs"] == 0:
        # TODO notify users to restart
        logger.debug("out of questions")
        pass

    # Send the question data to all connections in the room
    message = {"type": "question",
               "username": username,
               "question": question,
               "questionsRemaining": f'{updated_game["Attributes"]["NumQs"]}'}
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
    unanswered_users_item = user_table.scan(ProjectionExpression="Username",
                                            FilterExpression=Key('RoundID').eq(round_id) & Key('HasAnswered').eq(False))
    items = unanswered_users_item.get("Items", [])
    unanswered_users = [x['Username'] for x in items if 'Username' in x]

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
